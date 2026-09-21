"""Sealed final runs on locked TEST splits (SG-028).

Runs ONLY frozen methods with frozen configs (configs/frozen_main.json, SG-027 DONE):

- Track A SciFact test (300 queries): bm25_positive_idf, tfidf_protocol,
  dense_bge-base, hybrid_rrf_k60.
- Track A SCIDOCS test (1000 queries): bm25_positive_idf, dense_bge-base,
  hybrid_rrf_k60 (no TF-IDF per freeze).
- Track B graph test (200 queries): ppr_age_best_g0.3_l0.0 + global_pagerank_control
  at the SAME frozen weights (gamma=0.3, lambda=0.0). No test tuning: the variant
  set is fixed by the SG-026 dev selection recorded in the freeze; nothing is
  selected, compared, or dropped on test.
- Track C VN: NOT run here — human labels arrive at SG-033. Reported as unmeasured.

BM25/TF-IDF sealed runs go through their own CLIs (RunStore RUN dirs).
This script covers: dense, hybrid, track-B sealed runs, policy checks, and the
final registry + results table assembly.

Usage:
  run_final.py --only dense-scifact | dense-scidocs | hybrid-scifact |
                   hybrid-scidocs | trackB | registry
Exit 1 on any fatal problem (freeze drift, missing resource, policy violation).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from scholargraph.data.schemas import RankedDocument, RankingResult
from scholargraph.evaluation.metrics import EVALUATOR_VERSION, ProtocolEvaluator
from scholargraph.evaluation.runner import RunStore
from scholargraph.evaluation.sealed import (
    TRACK_A_LEAKAGE_NOTES,
    build_final_test_evidence,
    load_verified_freeze,
)
from scholargraph.ingest.beir_loader import canonical_beir_id, sha256_file
from scholargraph.retrieval.candidates import load_qrels_grades
from scholargraph.retrieval.dense import (
    ExactDenseIndex,
    HfLocalEncoder,
    _snapshot_dir_from_record,
    encode_queries,
    load_dense_encoder_config,
    verify_model_snapshot,
)
from scholargraph.retrieval.hybrid import rrf_fuse

TASK_ID = "SG-028"
MODULE_VERSION = "sg028-1.0.0"
FROZEN_GAMMA = 0.3
FROZEN_LAMBDA = 0.0
TOP_K = 100


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def git_head() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0 or len(out.stdout.strip()) != 40:
        raise RuntimeError("Cannot resolve git HEAD")
    return out.stdout.strip()


def load_split(dataset: str, split: str) -> dict:
    mpath = ROOT / "data" / "splits" / f"{dataset}_{split}.json"
    if not mpath.is_file():
        raise RuntimeError(f"Missing split manifest: {mpath}")
    split_def = json.loads(mpath.read_text(encoding="utf-8"))
    for key in ("query_ids", "queries_file", "queries_sha256", "qrels_file", "qrels_sha256"):
        if key not in split_def:
            raise RuntimeError(f"Split manifest lacks {key}")
    if sha256_file(ROOT / split_def["queries_file"]) != split_def["queries_sha256"]:
        raise RuntimeError("queries sha256 mismatch")
    if sha256_file(ROOT / split_def["qrels_file"]) != split_def["qrels_sha256"]:
        raise RuntimeError("qrels sha256 mismatch")
    split_def["_manifest_path"] = str(mpath.relative_to(ROOT))
    split_def["_manifest_sha256"] = sha256_file(mpath)
    return split_def


def read_query_texts(dataset: str, split_def: dict) -> dict[str, str]:
    want = list(split_def["query_ids"])
    texts: dict[str, str] = {}
    for line in (ROOT / split_def["queries_file"]).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise RuntimeError("Blank line in queries file")
        row = json.loads(line)
        cid = canonical_beir_id(dataset, str(row["_id"]))
        if cid in want:
            if not str(row.get("text", "")).strip():
                raise RuntimeError(f"Empty query text: {cid}")
            texts[cid] = str(row["text"])
    missing = [q for q in want if q not in texts]
    if missing:
        raise RuntimeError(f"{len(missing)} split queries absent from queries file")
    return {q: texts[q] for q in want}


def read_corpus_ids(dataset: str) -> list[str]:
    cpath = ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl"
    ids: list[str] = []
    for line in cpath.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise RuntimeError("Blank line in corpus file")
        ids.append(canonical_beir_id(dataset, str(json.loads(line)["_id"])))
    if not ids:
        raise RuntimeError("Empty corpus")
    return ids


def policy_check(runs: dict[str, RankingResult], want: list[str], corpus_ids: list[str],
                 method: str) -> dict[str, int]:
    """NaN/query/candidate policies — fail loudly, never substitute."""
    universe = set(corpus_ids)
    if set(runs) != set(want):
        raise RuntimeError(f"{method}: rankings queries != split queries")
    dup_docs = 0
    for qid in want:
        cands = runs[qid].candidates
        if not cands:
            raise RuntimeError(f"{method}: empty ranking for {qid}")
        seen: set[str] = set()
        for i, c in enumerate(cands):
            if not math.isfinite(c.score):
                raise RuntimeError(f"{method}: non-finite score {qid}/{c.doc_id}")
            if c.rank != i + 1:
                raise RuntimeError(f"{method}: bad rank order {qid}/{c.doc_id}")
            if c.doc_id in seen:
                dup_docs += 1
            seen.add(c.doc_id)
            if c.doc_id not in universe:
                raise RuntimeError(f"{method}: candidate outside corpus universe: {c.doc_id}")
    if dup_docs:
        raise RuntimeError(f"{method}: {dup_docs} duplicate doc IDs")
    return {"queries": len(want), "corpus_size": len(universe), "duplicate_docs": 0}


def write_sealed_run(method: str, dataset: str, split: str, runs: dict[str, RankingResult],
                     evaluation: dict, inputs: dict, freeze: dict, freeze_sha: str, head: str,
                     resolved_config: dict, model: dict, protocol_path: Path,
                     extra_hash_sources: dict | None = None) -> dict:
    """Seal a track-A test run through RunStore + the final-test gate.

    Rankings are recorded BEFORE qrels are touched by the caller (the caller
    evaluates after this returns the run manifest summary). Actually the flow
    here: rankings recorded -> evaluated -> per-query recorded -> completed.
    On any failure after create, the run is marked FAILED with evidence kept.
    """
    from scholargraph.evaluation.runner import FinalTestGateError  # noqa: F401 (re-export check)
    store = RunStore(ROOT / "artifacts" / "runs")
    corpus_path = ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl"
    split_path = ROOT / "data" / "splits" / f"{dataset}_{split}.json"
    evidence = build_final_test_evidence(
        project_root=ROOT, freeze=freeze, freeze_sha256=freeze_sha,
        track="A", method=method, dataset=dataset, split=split,
        resolved_config=resolved_config, data_source=corpus_path,
        split_definition=split_path, model=model,
        evaluator_revision=EVALUATOR_VERSION, leakage_notes=TRACK_A_LEAKAGE_NOTES)
    handle = store.create(
        method=method, dataset=dataset, split=split,
        resolved_config=resolved_config, data_source=corpus_path,
        split_definition=split_path, code_source=Path(__file__),
        model=model, seed=20260915,
        command=[sys.executable, "scripts/run_final.py", "--only", f"{method}-{dataset}"],
        protocol_source=protocol_path, synthetic=False,
        final_test=True, freeze_evidence=evidence,
        extra_hash_sources=extra_hash_sources or {})
    try:
        handle.record_rankings([runs[qid] for qid in sorted(runs)])
        per_query = {qid: {k: float(v) for k, v in evaluation["per_query"][qid].items()}
                     for qid in sorted(runs)}
        handle.record_per_query(per_query)
        post = {k: sha256_file(ROOT / v) for k, v in
                (("corpus", f"data/raw/beir/{dataset}/corpus.jsonl"),
                 ("queries", inputs["queries_file"]),
                 ("qrels", inputs["qrels_file"]))}
        for key in ("queries_sha256", "qrels_sha256"):
            short = key.replace("_sha256", "")
            if post[short] != inputs[key]:
                raise RuntimeError(f"Input {short} changed during the run; refusing to seal.")
        if post["corpus"] != inputs["corpus_sha256"]:
            raise RuntimeError("Corpus changed during the run; refusing to seal.")
        handle.append_log(f"post-run input hash check OK freeze={freeze_sha[:12]} head={head[:12]}")
        aggregate = {k: float(v) for k, v in evaluation["aggregate"].items()}
        completed = handle.complete(aggregate)
    except BaseException as exc:
        handle.fail(exc)
        raise
    return {"run_id": completed["run_id"],
            "run_dir": str((ROOT / "artifacts" / "runs" / completed["run_id"]).relative_to(ROOT)),
            "manifest_sha256": sha256_file(ROOT / "artifacts" / "runs" / completed["run_id"] / "manifest.json"),
            "aggregate_metrics": aggregate, "status": completed["status"]}


def read_rankings_orders(run_dir: Path) -> dict[str, list[str]]:
    orders: dict[str, list[str]] = {}
    for line in (run_dir / "rankings.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise RuntimeError(f"Blank line in {run_dir}/rankings.jsonl")
        o = json.loads(line)
        orders[o["query_id"]] = [c["doc_id"] for c in o["candidates"]]
    return orders


def _is_sealed_test_run(m: dict) -> bool:
    return (m.get("final_test") is True and m.get("status") == "COMPLETED"
            and str(m.get("split", "")).strip().lower() == "test")


def find_sealed_component_runs(dataset: str) -> tuple[Path, Path]:
    """Latest sealed COMPLETED bm25 + dense RUN dirs for dataset test (this task)."""
    latest: dict[str, Path] = {}
    for child in sorted((ROOT / "artifacts" / "runs").iterdir()):
        if not child.is_dir():
            continue
        mpath = child / "manifest.json"
        if not mpath.is_file():
            continue
        try:
            m = json.loads(mpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if (_is_sealed_test_run(m) and m.get("dataset") == dataset
                and str(m.get("method", "")) in ("bm25", "dense")):
            latest[str(m["method"])] = child
    if set(latest) != {"bm25", "dense"}:
        raise RuntimeError(f"Sealed bm25+dense test runs missing for {dataset}: {sorted(latest)}")
    return latest["bm25"], latest["dense"]


def step_dense(dataset: str) -> dict:
    from scholargraph.evaluation.sealed import load_verified_freeze as _lvf
    freeze, freeze_sha = _lvf(ROOT)
    head = git_head()
    split_def = load_split(dataset, "test")
    texts = read_query_texts(dataset, split_def)
    want = list(split_def["query_ids"])
    cfg = load_dense_encoder_config(
        ROOT / "configs" / "models" / "dense_encoder.json",
        ROOT / "configs" / "protocol_v1.json")
    snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
    namespace = "bge-base-en-v1.5__a5beb1e3"
    index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / dataset / namespace)
    if index.corpus_id != dataset:
        raise RuntimeError("Index corpus mismatch")
    print(f"[{dataset}] encoding {len(want)} test queries...", flush=True)
    t0 = time.time()
    encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
    pairs = [(qid, texts[qid]) for qid in want]
    qmat = np.asarray(encode_queries(project_root=ROOT, corpus_id=dataset, split="test",
                                     queries=pairs, config=cfg, encoder=encoder)["embeddings"],
                      dtype=np.float32)
    if qmat.shape != (len(want), cfg.embedding_dimension):
        raise RuntimeError(f"Query matrix shape {qmat.shape} unexpected")
    print(f"[{dataset}] searching...", flush=True)
    runs: dict[str, RankingResult] = {}
    for i, qid in enumerate(want):
        hits = index.search(qmat[i], top_k=TOP_K)
        runs[qid] = RankingResult(query_id=qid, candidates=[
            RankedDocument(doc_id=d, score=float(s), rank=r + 1) for r, (d, s) in enumerate(hits)])
    corpus_ids = list(index.doc_ids)
    policy_check(runs, want, corpus_ids, f"dense-{dataset}")
    qrels = load_qrels_grades(ROOT / split_def["qrels_file"], dataset)
    evaluation = ProtocolEvaluator().evaluate(runs, qrels, query_ids=want,
                                              corpus_ids=corpus_ids, track="A")
    inputs = {
        "queries_file": split_def["queries_file"], "qrels_file": split_def["qrels_file"],
        "queries_sha256": split_def["queries_sha256"], "qrels_sha256": split_def["qrels_sha256"],
        "corpus_sha256": sha256_file(ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl"),
        "split_manifest": {"path": split_def["_manifest_path"], "sha256": split_def["_manifest_sha256"]},
        "index_manifest": dict(index.manifest), "model_snapshot": snap,
        "encode_seconds": time.time() - t0,
    }
    resolved_config = {
        "resolved": True, "method": "dense", "dataset": dataset, "split": "test",
        "track": "A", "protocol_id": "scholargraph-research-v1",
        "model_id": cfg.model_id, "model_revision": cfg.revision,
        "namespace": namespace, "top_k": TOP_K,
        "prefix_scope": cfg.prefix_scope, "query_only_prefix": True,
        "index_manifest": dict(index.manifest),
        "ranking_reads_qrels": False, "module_version": MODULE_VERSION,
    }
    model = {"id": cfg.model_id, "revision": cfg.revision}
    manifest = write_sealed_run("dense", dataset, "test", runs, evaluation, inputs,
                                freeze, freeze_sha, head, resolved_config, model,
                                ROOT / "configs" / "protocol_v1.json",
                                {"index_manifest": dict(index.manifest)})
    print(json.dumps({"run": manifest["run_dir"], "metrics": manifest["aggregate_metrics"]}, indent=2))
    return manifest


def step_hybrid(dataset: str) -> dict:
    from scholargraph.evaluation.sealed import load_verified_freeze as _lvf
    freeze, freeze_sha = _lvf(ROOT)
    head = git_head()
    split_def = load_split(dataset, "test")
    want = list(split_def["query_ids"])
    bm25_dir, dense_dir = find_sealed_component_runs(dataset)
    lex_orders = read_rankings_orders(bm25_dir)
    den_orders = read_rankings_orders(dense_dir)
    if set(lex_orders) != set(want) or set(den_orders) != set(want):
        raise RuntimeError("Component run queries != split queries")
    import hashlib as _hl
    hcfg_path = ROOT / "configs" / "hybrid.json"
    from scholargraph.retrieval.hybrid import load_hybrid_config
    load_hybrid_config(hcfg_path)  # pins k=60/depths, fails loudly otherwise
    runs: dict[str, RankingResult] = {}
    for qid in want:
        rows = rrf_fuse(lex_orders[qid], den_orders[qid], k=60, final_depth=100)
        runs[qid] = RankingResult(query_id=qid, candidates=[
            RankedDocument(doc_id=r["doc_id"], score=float(r["rrf"]), rank=i + 1)
            for i, r in enumerate(rows)])
    corpus_ids = read_corpus_ids(dataset)
    policy_check(runs, want, corpus_ids, f"hybrid-{dataset}")
    qrels = load_qrels_grades(ROOT / split_def["qrels_file"], dataset)
    evaluation = ProtocolEvaluator().evaluate(runs, qrels, query_ids=want,
                                              corpus_ids=corpus_ids, track="A")
    inputs = {
        "queries_file": split_def["queries_file"], "qrels_file": split_def["qrels_file"],
        "queries_sha256": split_def["queries_sha256"], "qrels_sha256": split_def["qrels_sha256"],
        "corpus_sha256": sha256_file(ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl"),
        "split_manifest": {"path": split_def["_manifest_path"], "sha256": split_def["_manifest_sha256"]},
        "lexical_run": str(bm25_dir.relative_to(ROOT)),
        "dense_run": str(dense_dir.relative_to(ROOT)),
        "hybrid_config_sha256": _hl.sha256(hcfg_path.read_bytes()).hexdigest(),
    }
    from scholargraph.retrieval.hybrid import MODULE_VERSION as HYBRID_MODULE_VERSION
    resolved_config = {
        "resolved": True, "method": "hybrid", "dataset": dataset, "split": "test",
        "track": "A", "protocol_id": "scholargraph-research-v1",
        "rrf_k": 60, "final_depth": 100, "per_retriever_depth": 100,
        "lexical_run": str(bm25_dir.relative_to(ROOT)),
        "dense_run": str(dense_dir.relative_to(ROOT)),
        "ranking_reads_qrels": False, "module_version": HYBRID_MODULE_VERSION,
    }
    model = {"id": "hybrid-rrf-k60", "revision": HYBRID_MODULE_VERSION}
    manifest = write_sealed_run("hybrid", dataset, "test", runs, evaluation, inputs,
                                freeze, freeze_sha, head, resolved_config, model,
                                ROOT / "configs" / "protocol_v1.json")
    print(json.dumps({"run": manifest["run_dir"], "metrics": manifest["aggregate_metrics"]}, indent=2))
    return manifest


def step_trackB() -> dict:
    from scholargraph.graph.b_track import (
        BTrackDataError,
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
    from scholargraph.retrieval.dense import read_corpus

    freeze, freeze_sha = load_verified_freeze(ROOT)
    head = git_head()
    sel = freeze["tuning_selection"]["track_B_best"]
    if sel["gamma"] != FROZEN_GAMMA or sel["lambda"] != FROZEN_LAMBDA:
        raise RuntimeError("Freeze selection moved; refusing test run without new freeze version")
    t_start = time.time()
    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    holdout = load_holdout(ROOT / "data" / "processed" / "graph" / "holdout_edges.tsv")
    sq = json.loads((ROOT / "data" / "processed" / "graph" / "split_queries.json").read_text(encoding="utf-8"))
    queries = list(sq["cohorts"]["test"]["selected"])
    if len(queries) != 200:
        raise RuntimeError(f"Expected 200 test queries, got {len(queries)}")
    docs = read_corpus("openalex_core_text", ROOT)
    texts = dict(zip(docs.doc_ids, docs.texts))
    bm25 = BM25Index(texts, k1=1.5, b=0.75)
    cfg = load_dense_encoder_config(
        ROOT / "configs" / "models" / "dense_encoder.json",
        ROOT / "configs" / "protocol_v1.json")
    snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
    index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / "openalex_core_text" / cfg.namespace)
    encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
    qtexts = []
    for u in queries:
        if u not in texts:
            raise RuntimeError(f"Query {u} outside dense text universe")
        qtexts.append((u, texts[u]))
    qmat = np.asarray(encode_queries(project_root=ROOT, corpus_id="openalex_core_text", split="test",
                                     queries=qtexts, config=cfg, encoder=encoder)["embeddings"],
                      dtype=np.float32)
    qvec = {u: qmat[i] for i, u in enumerate(queries)}
    universe = load_node_universe_from_degrees(
        ROOT / "data" / "processed" / "graph" / "features_degree_masked.json")
    nodes, out = load_masked_adjacency(
        ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv", universe)
    years_all = {w: (works[w]["year"] if w in works else None) for w in nodes}
    global_by_year: dict[int, dict[str, float]] = {}
    for yu in sorted({works[u]["year"] for u in queries}):
        keep = [v for v in nodes if isinstance(years_all.get(v), int) and years_all[v] <= yu]
        sub = {v: {w for w in out.get(v, set()) if w in set(keep)} for v in keep}
        g, gi, _gr = global_pagerank(keep, sub)
        global_by_year[yu] = g
        print(f"global PR year<={yu}: {len(keep)} nodes, {gi} iters", flush=True)

    def bm25_rank(text: str, uni: set) -> list:
        return [d for d, _ in bm25.rank(text, top_k=100, exclude_doc_ids=(set(texts) - uni))][:100]

    per_q: dict[str, dict] = {}
    universes: dict[str, set] = {}
    want_tag = f"g{FROZEN_GAMMA}_l{FROZEN_LAMBDA}"
    for i, u in enumerate(queries):
        vec = qvec[u]

        def _dense_rank(text: str, uni: set, _v=vec) -> list:
            return [d for d, _ in index.search(_v, top_k=100,
                    exclude_doc_ids=frozenset(set(index.doc_ids) - uni))][:100]

        t0 = time.time()
        try:
            res = run_query(u, works, holdout, bm25_rank, _dense_rank, nodes, out, global_by_year)
        except Exception as exc:
            per_q[u] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
            continue
        v_ppr = fuse_variants(res["c100_rows"], res["ppr"], years_all, res["year"])
        v_glo = fuse_variants(res["c100_rows"], res["global"], years_all, res["year"])
        # Frozen-only: exactly the dev-selected weights, both graph sources.
        per_q[u] = {"status": "COMPLETED", "seconds": time.time() - t0,
                    "heldout": res["heldout"], "universe_size": res["universe_size"],
                    "ppr_best": v_ppr[want_tag], "global_control": v_glo[want_tag]}
        refs = internal_refs(u, works, res["year"])
        universes[u] = query_universe(u, works, res["year"], set(refs) - set(res["heldout"]))
        print(f"[{i + 1}/{len(queries)}] {u} H={len(res['heldout'])}", flush=True)
    ok = {q: v for q, v in per_q.items() if v.get("status") == "COMPLETED"}
    failed = {q: v.get("error") for q, v in per_q.items() if v.get("status") != "COMPLETED"}
    if failed:
        raise RuntimeError(f"{len(failed)} test queries FAILED (refusing partial sealed run): "
                           + str(list(failed)[:5]))
    # Policy: finite scores, coverage, universe membership.
    for q, v in ok.items():
        for arm in ("ppr_best", "global_control"):
            seen: set[str] = set()
            for i, r in enumerate(v[arm]):
                if not math.isfinite(float(r["score"])):
                    raise RuntimeError(f"Non-finite score {q}/{arm}")
                if r["doc_id"] in seen:
                    raise RuntimeError(f"Duplicate candidate {q}/{arm}")
                seen.add(r["doc_id"])
                if r["doc_id"] not in universes[q]:
                    raise RuntimeError(f"Candidate outside universe {q}/{arm}")
    ev_p = evaluate_variants({q: {"best": ok[q]["ppr_best"]} for q in ok},
                             {q: holdout[q] for q in ok},
                             {q: universes[q] for q in ok}, {q: q for q in ok}, nodes)
    ev_g = evaluate_variants({q: {"control": ok[q]["global_control"]} for q in ok},
                             {q: holdout[q] for q in ok},
                             {q: universes[q] for q in ok}, {q: q for q in ok}, nodes)
    payload = {
        "schema_version": 1, "task_id": TASK_ID, "split": "test",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sealed_run": True, "status": "COMPLETED",
        "frozen_manifest": "configs/frozen_main.json", "freeze_sha256": freeze_sha,
        "git_head": head,
        "frozen_weights": {"gamma": FROZEN_GAMMA, "lambda": FROZEN_LAMBDA,
                           "source": "SG-026 dev selection via freeze (no test tuning)"},
        "arms": {
            "ppr_age_best_g0.3_l0.0": ev_p["best"],
            "global_pagerank_control": ev_g["control"],
        },
        "queries": len(queries), "completed_queries": len(ok),
        "failed_queries": failed,
        "per_query_rankings": {q: {"ppr_best": v["ppr_best"], "global_control": v["global_control"],
                                   "heldout": v["heldout"]} for q, v in ok.items()},
        "elapsed_seconds": time.time() - t_start,
    }
    outp = ROOT / "artifacts" / "reports" / "b_trials_test.json"
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(outp.relative_to(ROOT)),
                      "arms": payload["arms"]}, indent=2))
    return payload


def collect_sealed_runs(freeze_sha: str) -> list[dict]:
    runs: list[dict] = []
    for child in sorted((ROOT / "artifacts" / "runs").iterdir()):
        if not child.is_dir():
            continue
        mpath = child / "manifest.json"
        if not mpath.is_file():
            continue
        try:
            m = json.loads(mpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not _is_sealed_test_run(m):
            continue
        if m.get("dataset") not in ("scifact", "scidocs"):
            continue
        if m.get("method") not in ("bm25", "tfidf", "dense", "hybrid"):
            continue
        ev = m.get("freeze_evidence", {})
        fa = ev.get("freeze_artifact", {})
        # The recorded sha256 covers the artifact file itself; the binding to
        # the live freeze lives INSIDE the artifact (frozen_manifest_sha256).
        try:
            fa_doc = json.loads(Path(fa.get("path", "")).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if fa_doc.get("frozen_manifest_sha256") != freeze_sha:
            continue  # sealed on an older freeze, not this one
        if sha256_file(child / "manifest.json") != json.loads(
                (child / "seal.json").read_text(encoding="utf-8"))["manifest_sha256"]:
            raise RuntimeError(f"Seal broken for {child.name}")
        m["_run_dir"] = str(child.relative_to(ROOT))
        runs.append(m)
    # Latest run per (method, dataset).
    latest: dict[tuple[str, str], dict] = {}
    for m in runs:
        latest[(m["method"], m["dataset"])] = m
    return sorted(latest.values(), key=lambda m: (m["dataset"], m["method"]))


def step_registry() -> dict:
    from scholargraph.evaluation.sealed import load_verified_freeze as _lvf
    freeze, freeze_sha = _lvf(ROOT)
    head = git_head()
    if head != freeze.get("git_head", head):
        print(f"NOTE: code moved past freeze HEAD {freeze.get('git_head', '')[:12]} "
              f"-> {head[:12]}; inputs/configs verified unchanged above.", flush=True)
    runs = collect_sealed_runs(freeze_sha)
    need = {("bm25", "scifact"), ("tfidf", "scifact"), ("dense", "scifact"), ("hybrid", "scifact"),
            ("bm25", "scidocs"), ("dense", "scidocs"), ("hybrid", "scidocs")}
    have = {(m["method"], m["dataset"]) for m in runs}
    if have != need:
        raise RuntimeError(f"Sealed track-A set incomplete: have {sorted(have)}")
    # Re-verify policy on every sealed run (defense in depth at registry time).
    for m in runs:
        dataset = m["dataset"]
        split_def = load_split(dataset, "test")
        corpus_ids = read_corpus_ids(dataset)
        orders_runs: dict[str, RankingResult] = {}
        for line in (ROOT / m["_run_dir"] / "rankings.jsonl").read_text(encoding="utf-8").splitlines():
            o = json.loads(line)
            orders_runs[o["query_id"]] = RankingResult(
                query_id=o["query_id"],
                candidates=[RankedDocument(doc_id=c["doc_id"], score=float(c["score"]), rank=i + 1)
                            for i, c in enumerate(o["candidates"])])
        policy_check(orders_runs, list(split_def["query_ids"]), corpus_ids,
                     f'{m["method"]}-{dataset}')
    bpath = ROOT / "artifacts" / "reports" / "b_trials_test.json"
    if not bpath.is_file():
        raise RuntimeError("Missing sealed track-B report b_trials_test.json")
    btest = json.loads(bpath.read_text(encoding="utf-8"))
    if btest.get("sealed_run") is not True or btest.get("freeze_sha256") != freeze_sha:
        raise RuntimeError("Track-B report is not sealed on this freeze")
    registry = {
        "schema_version": 1, "task_id": TASK_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen_manifest": "configs/frozen_main.json", "freeze_sha256": freeze_sha,
        "git_head": head,
        "track_A_runs": [
            {"method": m["method"], "dataset": m["dataset"], "split": "test",
             "run_id": m["run_id"], "run_dir": m["_run_dir"],
             "manifest_sha256": sha256_file(ROOT / m["_run_dir"] / "manifest.json"),
             "metrics": {k: float(v) for k, v in m["aggregate_metrics"].items()},
             "status": m["status"]} for m in runs
        ],
        "track_B": {
            "report": "artifacts/reports/b_trials_test.json",
            "report_sha256": sha256_file(bpath),
            "frozen_weights": btest["frozen_weights"],
            "arms": btest["arms"],
            "queries": btest["queries"], "completed_queries": btest["completed_queries"],
            "status": btest["status"],
        },
        "track_C_vn": {"status": "chua do", "reason": "Human labels arrive at SG-033; no scores reported."},
    }
    reg_path = ROOT / "artifacts" / "reports" / "main_run_registry.json"
    reg_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    def row(method: str, dataset: str) -> dict:
        return next(r for r in registry["track_A_runs"]
                    if r["method"] == method and r["dataset"] == dataset)

    def fmt(metrics: dict) -> str:
        keys = ["nDCG@10", "Recall@100", "MRR@10", "MAP@100", "P@5"]
        return " | ".join(f"{metrics.get(k, float('nan')):.4f}" for k in keys)

    lines = ["# Main results - sealed final runs (SG-028)",
             "",
             f"Freeze: `configs/frozen_main.json` sha256 `{freeze_sha}`.",
             f"Generated: {registry['generated_at']}. All runs final_test=true, status COMPLETED.",
             "Track C (VN): **chua do** - human labels arrive at SG-033; no scores reported or imputed.",
             "",
             "## Track A - SciFact test (300 queries / 339 qrels / 5.183 docs)",
             "",
             "| method | nDCG@10 | Recall@100 | MRR@10 | MAP@100 | P@5 | run_id |",
             "|---|---|---|---|---|---|---|"]
    for meth in ("bm25", "tfidf", "dense", "hybrid"):
        r = row(meth, "scifact")
        lines.append(f"| {meth} | {fmt(r['metrics'])} | {r['run_id']} |")
    lines += ["",
              "## Track A - SCIDOCS test (1000 queries / 29.928 qrels / 25.657 docs)",
              "",
              "| method | nDCG@10 | Recall@100 | MRR@10 | MAP@100 | P@5 | run_id |",
              "|---|---|---|---|---|---|---|"]
    for meth in ("bm25", "dense", "hybrid"):
        r = row(meth, "scidocs")
        lines.append(f"| {meth} | {fmt(r['metrics'])} | {r['run_id']} |")
    lines += ["",
              "## Track B - OpenAlex graph test (200 queries, frozen g=0.3/l=0.0, no test tuning)",
              "",
              "| arm | nDCG@10 | Recall@100 | MRR@10 | MAP@100 | P@5 |",
              "|---|---|---|---|---|---|"]
    for arm in ("ppr_age_best_g0.3_l0.0", "global_pagerank_control"):
        lines.append(f"| {arm} | {fmt(btest['arms'][arm])} |")
    lines += ["",
              "Report: `artifacts/reports/b_trials_test.json` "
              f"(sha256 `{registry['track_B']['report_sha256']}`).",
              "",
              "## Notes",
              "",
              "- Every table row links a sealed COMPLETED run (see `main_run_registry.json`).",
              "- Low scores are kept as measured (negative results have value under a tight protocol).",
              "- Graph/custom tables are separate from the BEIR text benchmark (ADR-003).",
              "- No tuning on test: track-B arms are the frozen dev selection; track-A methods use frozen defaults.",
              ""]
    md_path = ROOT / "artifacts" / "reports" / "main_results.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"registry": str(reg_path.relative_to(ROOT)),
                      "results": str(md_path.relative_to(ROOT)),
                      "track_A_runs": len(runs)}, indent=2))
    return registry


STEPS = {
    "dense-scifact": lambda: step_dense("scifact"),
    "dense-scidocs": lambda: step_dense("scidocs"),
    "hybrid-scifact": lambda: step_hybrid("scifact"),
    "hybrid-scidocs": lambda: step_hybrid("scidocs"),
    "trackB": step_trackB,
    "registry": step_registry,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sealed final runs on TEST splits (SG-028)")
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
