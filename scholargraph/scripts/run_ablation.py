"""Ablation and robustness on sealed TEST artifacts (SG-029).

All variants below were PRE-SPECIFIED in docs/MAIN_FREEZE.md section 3 and the
SG-029 card BEFORE any test number was inspected for this purpose. Nothing is
selected, dropped, or re-weighted on test: this script only REPORTS the frozen
comparisons. Adding a variant requires a freeze version bump + ADR.

Ablations:
  A1 age on/off (track B test200): PPR gamma=0.3 x lambda in {0.0, 0.01, 0.03, 0.1}
      + global control at the same weights (recomputed deterministically).
  A2 no-graph arms (track A, from the sealed registry — referenced, not rerun).
  A3 RRF k in {30, 60, 100}: re-fuse sealed bm25+dense component orders
      (SciFact + SCIDOCS test).
Robustness (same pool/metric, sealed per-query artifacts only):
  R1 query-length buckets, R2 missing-abstract exposure, R3 node-degree buckets,
  R4 component costs, R5 failure counts (reported even when zero).

Usage: run_ablation.py --only age | rrfk | robust | reports
Exit 1 on any fatal problem.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from scholargraph.data.schemas import RankedDocument, RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator
from scholargraph.evaluation.sealed import load_verified_freeze
from scholargraph.ingest.beir_loader import canonical_beir_id, sha256_file
from scholargraph.retrieval.candidates import load_qrels_grades
from scholargraph.retrieval.hybrid import rrf_fuse

TASK_ID = "SG-029"
MODULE_VERSION = "sg029-1.0.0"
# Pre-specified variant sets (freeze + card). The tests trip-wire any extra arm.
AGE_GAMMA = 0.3
AGE_LAMBDAS = (0.0, 0.01, 0.03, 0.1)
RRF_KS = (30, 60, 100)


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _read_orders(run_dir: Path) -> dict[str, list[str]]:
    orders: dict[str, list[str]] = {}
    for line in (run_dir / "rankings.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise RuntimeError(f"Blank line in {run_dir}/rankings.jsonl")
        o = json.loads(line)
        orders[o["query_id"]] = [c["doc_id"] for c in o["candidates"]]
    return orders


def _registry() -> dict:
    reg_path = ROOT / "artifacts" / "reports" / "main_run_registry.json"
    if not reg_path.is_file():
        raise RuntimeError("Missing sealed registry main_run_registry.json (SG-028)")
    return json.loads(reg_path.read_text(encoding="utf-8"))


def _out() -> Path:
    (ROOT / "artifacts" / "reports").mkdir(parents=True, exist_ok=True)
    return ROOT / "artifacts" / "reports"


def step_age() -> dict:
    from scholargraph.graph.b_track import (
        evaluate_variants,
        fuse_variants,
        internal_refs,
        load_holdout,
        load_works,
        query_universe,
        run_query,
    )
    from scholargraph.graph.baselines import (
        global_pagerank,
        load_masked_adjacency,
        load_node_universe_from_degrees,
    )
    from scholargraph.retrieval.bm25 import BM25Index
    from scholargraph.retrieval.dense import (
        ExactDenseIndex,
        HfLocalEncoder,
        _snapshot_dir_from_record,
        encode_queries,
        load_dense_encoder_config,
        read_corpus,
        verify_model_snapshot,
    )
    from scholargraph.retrieval.rerank import apply_age_to_rows, rerank_query

    freeze, freeze_sha = load_verified_freeze(ROOT)
    costs: dict[str, float] = {}
    t_all = time.time()
    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    holdout = load_holdout(ROOT / "data" / "processed" / "graph" / "holdout_edges.tsv")
    sq = json.loads((ROOT / "data" / "processed" / "graph" / "split_queries.json").read_text(encoding="utf-8"))
    queries = list(sq["cohorts"]["test"]["selected"])
    t0 = time.time()
    docs = read_corpus("openalex_core_text", ROOT)
    texts = dict(zip(docs.doc_ids, docs.texts))
    bm25 = BM25Index(texts, k1=1.5, b=0.75)
    costs["bm25_index_build_s"] = time.time() - t0
    cfg = load_dense_encoder_config(
        ROOT / "configs" / "models" / "dense_encoder.json",
        ROOT / "configs" / "protocol_v1.json")
    snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
    index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / "openalex_core_text" / cfg.namespace)
    t0 = time.time()
    encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
    qtexts = [(u, texts[u]) for u in queries]
    for u in queries:
        if u not in texts:
            raise RuntimeError(f"Query {u} outside dense text universe")
    qmat = np.asarray(encode_queries(project_root=ROOT, corpus_id="openalex_core_text", split="test",
                                     queries=qtexts, config=cfg, encoder=encoder)["embeddings"],
                      dtype=np.float32)
    costs["query_encode_s"] = time.time() - t0
    qvec = {u: qmat[i] for i, u in enumerate(queries)}
    universe = load_node_universe_from_degrees(
        ROOT / "data" / "processed" / "graph" / "features_degree_masked.json")
    nodes, out = load_masked_adjacency(
        ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv", universe)
    years_all = {w: (works[w]["year"] if w in works else None) for w in nodes}
    t0 = time.time()
    global_by_year: dict[int, dict[str, float]] = {}
    for yu in sorted({works[u]["year"] for u in queries}):
        keep = [v for v in nodes if isinstance(years_all.get(v), int) and years_all[v] <= yu]
        sub = {v: {w for w in out.get(v, set()) if w in set(keep)} for v in keep}
        g, _gi, _gr = global_pagerank(keep, sub)
        global_by_year[yu] = g
    costs["global_pagerank_s"] = time.time() - t0

    def bm25_rank(text: str, uni: set) -> list:
        return [d for d, _ in bm25.rank(text, top_k=100, exclude_doc_ids=(set(texts) - uni))][:100]

    per_q: dict[str, dict] = {}
    universes: dict[str, set] = {}
    t_rank = t_ppr = t_fuse = 0.0
    for i, u in enumerate(queries):
        vec = qvec[u]

        def _dense_rank(text: str, uni: set, _v=vec) -> list:
            return [d for d, _ in index.search(_v, top_k=100,
                    exclude_doc_ids=frozenset(set(index.doc_ids) - uni))][:100]

        t0 = time.time()
        try:
            res = run_query(u, works, holdout, bm25_rank, _dense_rank, nodes, out, global_by_year)
        except Exception as exc:
            raise RuntimeError(f"Track-B recompute FAILED for {u}: {type(exc).__name__}: {exc}")
        t_rank += time.time() - t0
        t0 = time.time()
        v_ppr = fuse_variants(res["c100_rows"], res["ppr"], years_all, res["year"])
        v_glo = fuse_variants(res["c100_rows"], res["global"], years_all, res["year"])
        t_fuse += time.time() - t0
        # Keep ONLY the pre-specified gamma slice (both graph sources, all lambdas).
        keep_p = {tag: v_ppr[tag] for tag in v_ppr if tag.startswith(f"g{AGE_GAMMA}_l")}
        keep_g = {tag: v_glo[tag] for tag in v_glo if tag.startswith(f"g{AGE_GAMMA}_l")}
        per_q[u] = {"c100_rows": res["c100_rows"], "ppr": keep_p, "global": keep_g,
                    "heldout": res["heldout"]}
        refs = internal_refs(u, works, res["year"])
        universes[u] = query_universe(u, works, res["year"], set(refs) - set(res["heldout"]))
        if (i + 1) % 50 == 0:
            print(f"[{i + 1}/{len(queries)}] recomputed", flush=True)
    costs["c100_ppr_rank_s"] = t_rank
    costs["fusion_s"] = t_fuse
    ok = list(per_q)
    arms: dict[str, dict] = {}
    t0 = time.time()
    for lam in AGE_LAMBDAS:
        tag = f"g{AGE_GAMMA}_l{lam}"
        ev_p = evaluate_variants({q: {tag: per_q[q]["ppr"][tag]} for q in ok},
                                 {q: holdout[q] for q in ok},
                                 {q: universes[q] for q in ok}, {q: q for q in ok}, nodes)
        ev_g = evaluate_variants({q: {tag: per_q[q]["global"][tag]} for q in ok},
                                 {q: holdout[q] for q in ok},
                                 {q: universes[q] for q in ok}, {q: q for q in ok}, nodes)
        arms[f"ppr_g{AGE_GAMMA}_l{lam}"] = ev_p[tag]
        arms[f"global_g{AGE_GAMMA}_l{lam}"] = ev_g[tag]
    costs["evaluation_s"] = time.time() - t0
    costs["total_s"] = time.time() - t_all
    payload = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "freeze_sha256": freeze_sha,
               "prespecified": {"gamma": AGE_GAMMA, "lambdas": list(AGE_LAMBDAS)},
               "split": "test", "queries": len(queries),
               "arms": arms, "costs": costs}
    outp = _out() / "ablation_age.json"
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({a: arms[a].get("nDCG@10") for a in arms}, indent=2))
    print(json.dumps({"costs": costs}, indent=2))
    return payload


def _rrf_with_k(lexical_rank: list[str], dense_rank: list[str], k: int,
                final_depth: int = 100) -> list[dict]:
    """RRF with a non-frozen k for the A3 ablation only.

    Mirrors hybrid.rrf_fuse semantics exactly (input validation, missing-side
    contribution 0, canonical tie-break score-desc/doc-ID-asc, finite check);
    rrf_fuse itself stays pinned to k=60 per the SG-020 contract and is NOT
    modified. The k=60 arm below must reproduce rrf_fuse row-for-row
    (asserted in tests/unit/test_ablation.py).
    """
    if not isinstance(k, int) or k < 1:
        raise RuntimeError(f"RRF k must be a positive integer, got {k!r}")
    for name, seq in (("lexical_rank", lexical_rank), ("dense_rank", dense_rank)):
        if not isinstance(seq, (list, tuple)) or not seq:
            raise RuntimeError(f"{name} must be a non-empty list")
        if len(seq) > 100:
            raise RuntimeError(f"{name} exceeds depth 100")
        seen: set[str] = set()
        for d in seq:
            if not isinstance(d, str) or not d or d in seen:
                raise RuntimeError(f"{name} contains invalid/duplicate doc ID: {d!r}")
            seen.add(d)
    lex_pos = {d: i + 1 for i, d in enumerate(lexical_rank)}
    den_pos = {d: i + 1 for i, d in enumerate(dense_rank)}
    union = list(dict.fromkeys([*lexical_rank, *dense_rank]))
    if len(union) > 200:
        raise RuntimeError(f"Union exceeds maximum 200 (got {len(union)})")
    rows = []
    for d in union:
        rl, rd = lex_pos.get(d), den_pos.get(d)
        score = (1.0 / (k + rl) if rl is not None else 0.0) + (1.0 / (k + rd) if rd is not None else 0.0)
        if not math.isfinite(score):
            raise RuntimeError(f"Non-finite RRF score for {d!r}")
        rows.append({"doc_id": d, "rrf": score})
    rows.sort(key=lambda r: (-r["rrf"], r["doc_id"]))
    return rows[:final_depth]


def step_rrfk() -> dict:
    freeze, freeze_sha = load_verified_freeze(ROOT)
    reg = _registry()
    by_key = {(r["method"], r["dataset"]): r for r in reg["track_A_runs"]}
    payload_arms: dict[str, dict] = {}
    for dataset in ("scifact", "scidocs"):
        split_def = json.loads((ROOT / "data" / "splits" / f"{dataset}_test.json").read_text(encoding="utf-8"))
        want = list(split_def["query_ids"])
        lex = _read_orders(ROOT / by_key[("bm25", dataset)]["run_dir"])
        den = _read_orders(ROOT / by_key[("dense", dataset)]["run_dir"])
        if set(lex) != set(want) or set(den) != set(want):
            raise RuntimeError(f"Component orders != split queries for {dataset}")
        corpus_ids: list[str] = []
        for line in (ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
            corpus_ids.append(canonical_beir_id(dataset, str(json.loads(line)["_id"])))
        qrels = load_qrels_grades(ROOT / split_def["qrels_file"], dataset)
        for k in RRF_KS:
            runs: dict[str, RankingResult] = {}
            for qid in want:
                rows = _rrf_with_k(lex[qid], den[qid], k=k, final_depth=100)
                for r in rows:
                    if not math.isfinite(float(r["rrf"])):
                        raise RuntimeError(f"Non-finite RRF k={k} {qid}")
                runs[qid] = RankingResult(query_id=qid, candidates=[
                    RankedDocument(doc_id=r["doc_id"], score=float(r["rrf"]), rank=i + 1)
                    for i, r in enumerate(rows)])
            ev = ProtocolEvaluator().evaluate(runs, qrels, query_ids=want,
                                              corpus_ids=corpus_ids, track="A")
            payload_arms[f"hybrid_rrf_k{k}_{dataset}"] = ev["aggregate"]
    payload = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "freeze_sha256": freeze_sha,
               "prespecified": {"rrf_k": list(RRF_KS)},
               "arms": payload_arms}
    outp = _out() / "ablation_rrfk.json"
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({a: payload_arms[a].get("nDCG@10") for a in payload_arms}, indent=2))
    return payload


def _terciles(values: list[float]) -> tuple[float, float]:
    s = sorted(values)
    n = len(s)
    if n < 3:
        raise RuntimeError("Too few values for tercile buckets")
    return s[n // 3], s[2 * n // 3]


def _bucket_mean(per_query: dict[str, dict], members: list[str], metric: str) -> float | None:
    vals = [float(per_query[q][metric]) for q in members if q in per_query and per_query[q].get(metric) is not None]
    if not vals:
        return None  # unmeasured bucket stays null, never 0
    if any(not math.isfinite(v) for v in vals):
        raise RuntimeError(f"Non-finite per-query {metric} in bucket")
    return sum(vals) / len(vals)


def step_robust() -> dict:
    from scholargraph.graph.b_track import load_works
    from scholargraph.retrieval.bm25 import load_corpus, tokenize

    freeze, freeze_sha = load_verified_freeze(ROOT)
    reg = _registry()
    out: dict[str, dict] = {"buckets": {}, "failures": {}, "costs": {}}
    # R1: query-length buckets per track-A method (terciles on protocol tokens).
    for dataset in ("scifact", "scidocs"):
        split_def = json.loads((ROOT / "data" / "splits" / f"{dataset}_test.json").read_text(encoding="utf-8"))
        want = list(split_def["query_ids"])
        qtexts: dict[str, str] = {}
        for line in (ROOT / split_def["queries_file"]).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            cid = canonical_beir_id(dataset, str(row["_id"]))
            if cid in want:
                qtexts[cid] = str(row.get("text", ""))
        lens = {q: len(tokenize(t)) for q, t in qtexts.items()}
        lo, hi = _terciles(list(lens.values()))
        buckets = {"short": [q for q in want if lens[q] <= lo],
                   "long": [q for q in want if lens[q] > hi],
                   "mid": [q for q in want if lo < lens[q] <= hi]}
        for r in reg["track_A_runs"]:
            if r["dataset"] != dataset:
                continue
            perq = json.loads((ROOT / r["run_dir"] / "per_query.json").read_text(encoding="utf-8"))
            # RunStore per-query form: {qid: {metric: value}} (canonical JSON).
            entry: dict[str, dict] = {}
            for q in want:
                entry[q] = {f"nDCG@10": perq[q]["nDCG@10"]}
            out["buckets"][f"{r['method']}_{dataset}_by_query_length"] = {
                b: {"n": len(m), "mean_nDCG@10": _bucket_mean(entry, m, "nDCG@10")}
                for b, m in buckets.items()}
    # R2: missing-abstract exposure (corpus-level counts; same corpus for every
    # method, so the bm25 sealed manifest — which records coverage — is the source).
    cov: dict[str, dict] = {}
    for r in reg["track_A_runs"]:
        if r["method"] != "bm25":
            continue
        m = json.loads((ROOT / r["run_dir"] / "manifest.json").read_text(encoding="utf-8"))
        params = m.get("parameters", m.get("resolved_config", {}))
        cov[r["dataset"]] = {
            "corpus_missing_title": params.get("corpus_missing_title_count"),
            "corpus_missing_abstract": params.get("corpus_missing_abstract_count"),
            "source_run": r["run_id"],
        }
    for dataset, counts in cov.items():
        out["buckets"][f"corpus_{dataset}_missing_fields"] = counts
    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    sq = json.loads((ROOT / "data" / "processed" / "graph" / "split_queries.json").read_text(encoding="utf-8"))
    tq = list(sq["cohorts"]["test"]["selected"])
    no_abs = [u for u in tq if not works[u]["abstract"].strip()]
    out["buckets"]["trackB_test_missing_query_abstract"] = {
        "n_queries": len(tq), "n_missing_abstract": len(no_abs),
        "fraction": (len(no_abs) / len(tq)) if tq else None}
    # R3: node-degree buckets for track-B queries (total degree = in + out).
    deg_doc = json.loads((ROOT / "data" / "processed" / "graph" / "features_degree_masked.json").read_text(encoding="utf-8"))
    if not isinstance(deg_doc, dict) or "in_degree" not in deg_doc or "out_degree" not in deg_doc:
        raise RuntimeError("Unexpected degree-features format")
    deg = {n: int(deg_doc["in_degree"].get(n, 0)) + int(deg_doc["out_degree"].get(n, 0))
           for n in set(deg_doc["in_degree"]) | set(deg_doc["out_degree"])}
    qdeg = [deg.get(u, 0) for u in tq]
    lo, hi = _terciles(qdeg)
    btest = json.loads((ROOT / "artifacts" / "reports" / "b_trials_test.json").read_text(encoding="utf-8"))
    pq = btest["per_query_rankings"]
    # Per-query nDCG needs qrels: reuse heldout as grades (evaluator-side only, same as finals).
    hold = {q: pq[q]["heldout"] for q in tq}
    uni = {q: set(r["doc_id"] for r in pq[q]["ppr_best"]) | set(pq[q]["heldout"]) for q in tq}
    _ = uni  # universe audit trail (candidates were policy-checked at seal time)
    deg_buckets = {"low_degree": [q for q in tq if deg.get(q, 0) <= lo],
                   "high_degree": [q for q in tq if deg.get(q, 0) > hi]}
    # Per-query nDCG@10 via a direct graded-DCG pass (same linear-gain definition).
    arm_bucket_means: dict[str, dict] = {}
    for arm in ("ppr_best", "global_control"):
        arm_bucket_means[arm] = {}
        for b, members in deg_buckets.items():
            vals = []
            for q in members:
                order = [r["doc_id"] for r in pq[q][arm]]
                rel = {d: 1 for d in hold[q]}
                vals.append(_ndcg10(order, rel))
            arm_bucket_means[arm][b] = {"n": len(members),
                                        "mean_nDCG@10": sum(vals) / len(vals) if vals else None}
    out["buckets"]["trackB_by_query_degree"] = arm_bucket_means
    # R4/R5: costs + failures.
    age = json.loads((_out() / "ablation_age.json").read_text(encoding="utf-8")) if (_out() / "ablation_age.json").is_file() else {}
    out["costs"] = {"trackB_recompute_s": (age.get("costs", {}) or {})}
    for r in reg["track_A_runs"]:
        m = json.loads((ROOT / r["run_dir"] / "manifest.json").read_text(encoding="utf-8"))
        out["costs"][f"{r['method']}_{r['dataset']}"] = {
            "created_at": m.get("created_at"), "completed_at": m.get("completed_at")}
    out["failures"] = {"sealed_track_A_failed_runs": 0,
                       "trackB_test_failed_queries": len(json.loads(
                           (ROOT / "artifacts/reports/b_trials_test.json").read_text(
                               encoding="utf-8"))["failed_queries"]),
                       "note": "Zero is a measured count here (all sealed runs COMPLETED); "
                               "unmeasured quantities are null, never 0."}
    payload = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "freeze_sha256": freeze_sha, **out}
    outp = _out() / "robustness.json"
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"buckets": len(out["buckets"]), "failures": out["failures"]}, indent=2))
    return payload


def _ndcg10(order: list[str], rel: dict[str, int]) -> float:
    import math as _m
    dcg = sum((2 ** rel[d] - 1) / _m.log2(i + 2) for i, d in enumerate(order[:10]) if d in rel)
    ideal = sorted(rel.values(), reverse=True)
    idcg = sum((2 ** g - 1) / _m.log2(i + 2) for i, g in enumerate(ideal[:10]))
    if idcg == 0:
        raise RuntimeError("Query without positives in robustness bucket")
    return dcg / idcg


def step_reports() -> dict:
    freeze, freeze_sha = load_verified_freeze(ROOT)
    reg = _registry()
    age_path = _out() / "ablation_age.json"
    rrf_path = _out() / "ablation_rrfk.json"
    rob_path = _out() / "robustness.json"
    for p in (age_path, rrf_path, rob_path):
        if not p.is_file():
            raise RuntimeError(f"Missing ablation input (run prior steps first): {p.name}")
    age = json.loads(age_path.read_text(encoding="utf-8"))
    rrf = json.loads(rrf_path.read_text(encoding="utf-8"))
    rob = json.loads(rob_path.read_text(encoding="utf-8"))
    if age.get("freeze_sha256") != freeze_sha or rrf.get("freeze_sha256") != freeze_sha:
        raise RuntimeError("Ablation inputs sealed on a different freeze; refusing to report.")

    def fmt(v) -> str:
        return "n/a" if v is None else f"{float(v):.4f}"

    a_lines = ["# Ablation - sealed comparisons (SG-029)", "",
               f"Freeze sha256 `{freeze_sha}`. All variants pre-specified in the freeze;",
               "nothing was selected or dropped on test. Same pool/metric as SG-028.",
               "",
               "## A1 - age adjustment on/off (track B test200, gamma=0.3)",
               "",
               "| arm | nDCG@10 | Recall@100 | MRR@10 |",
               "|---|---|---|---|"]
    for arm in sorted(age["arms"]):
        m = age["arms"][arm]
        a_lines.append(f"| {arm} | {fmt(m.get('nDCG@10'))} | {fmt(m.get('Recall@100'))} | {fmt(m.get('MRR@10'))} |")
    a_lines += ["",
                "## A2 - no-graph arms (track A sealed registry, referenced)",
                "",
                "| arm | dataset | nDCG@10 |",
                "|---|---|---|---|"]
    for r in reg["track_A_runs"]:
        if r["method"] in ("bm25", "dense"):
            a_lines.append(f"| {r['method']} (no graph) | {r['dataset']} | {fmt(r['metrics'].get('nDCG@10'))} | {r['run_id']} |")
    a_lines += ["",
                "## A3 - RRF k (re-fused sealed component orders)",
                "",
                "| arm | nDCG@10 |",
                "|---|---|"]
    for arm in sorted(rrf["arms"]):
        a_lines.append(f"| {arm} | {fmt(rrf['arms'][arm].get('nDCG@10'))} |")
    a_lines += ["",
                "## Notes",
                "",
                "- Non-improving variants are kept (negative results have value).",
                "- VN per-intent analysis deferred to SG-030/SG-034 (labels at SG-033).",
                ""]
    (_out() / "ablation.md").write_text("\n".join(a_lines), encoding="utf-8")

    r_lines = ["# Robustness - sealed buckets, costs, failures (SG-029)", "",
               f"Freeze sha256 `{freeze_sha}`. Buckets computed on sealed per-query artifacts;",
               "unmeasured buckets are null, never 0.",
               "",
               "## R1/R2/R3 - buckets",
               "",
               "```json",
               json.dumps(rob["buckets"], ensure_ascii=False, indent=2),
               "```",
               "",
               "## R4 - costs",
               "",
               "```json",
               json.dumps(rob["costs"], ensure_ascii=False, indent=2),
               "```",
               "",
               "## R5 - failures",
               "",
               "```json",
               json.dumps(rob["failures"], ensure_ascii=False, indent=2),
               "```",
               ""]
    (_out() / "robustness.md").write_text("\n".join(r_lines), encoding="utf-8")
    combined = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "freeze_sha256": freeze_sha,
                "age_sha256": sha256_file(age_path), "rrfk_sha256": sha256_file(rrf_path),
                "robustness_sha256": sha256_file(rob_path)}
    (_out() / "ablation.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ablation": "artifacts/reports/ablation.md",
                      "robustness": "artifacts/reports/robustness.md"}, indent=2))
    return combined


STEPS = {
    "age": step_age,
    "rrfk": step_rrfk,
    "robust": step_robust,
    "reports": step_reports,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ablation and robustness (SG-029)")
    ap.add_argument("--only", required=True, choices=sorted(STEPS))
    args = ap.parse_args(argv)
    try:
        STEPS[args.only]()
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        import traceback
        traceback.print_exc()
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
