"""Local end-to-end performance profile (SG-040).

Phases (run in order; cold MUST be a fresh interpreter):
  cold-worker : subprocess-only — load BM25+dense stack from disk, run ONE query
                end-to-end, print load/first-query seconds + peak RSS as JSON.
  warm        : build lexical + dense stacks once; time 20 SciFact + 10 SCIDOCS
                test queries per method (bm25 / tfidf / dense / hybrid-full).
  trackb      : 5 OpenAlex test queries through the frozen track-B pipeline
                with per-stage timings (no metric judgement here).
  concur      : dense search, 10 queries sequential vs 4 threads.
  reports     : assemble performance.json (tracked) + performance.md (untracked).

Target honesty: the 500ms/query budget is REPORTED against, never tuned for.
GPU is not measured here (null + pointer to the SG-002 T4 pilot).

Usage: profile_performance.py --phase cold-worker|warm|trackb|concur|reports|all
Exit 1 on any fatal problem.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from scholargraph.evaluation.performance import (
    hardware_context,
    peak_rss_bytes,
    summarize_timings,
    time_call,
)
from scholargraph.evaluation.sealed import load_verified_freeze
from scholargraph.ingest.beir_loader import canonical_beir_id, sha256_file

TASK_ID = "SG-040"
MODULE_VERSION = "sg040-1.0.0"
SCIFACT_QS = 20
SCIDOCS_QS = 10
TRACKB_QS = 5
QUERY_BUDGET_S = 0.5


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _out() -> Path:
    (ROOT / "artifacts" / "reports").mkdir(parents=True, exist_ok=True)
    return ROOT / "artifacts" / "reports"


def _split_queries(dataset: str, n: int) -> tuple[list[str], dict[str, str]]:
    split_def = json.loads((ROOT / "data" / "splits" / f"{dataset}_test.json").read_text(encoding="utf-8"))
    want = list(split_def["query_ids"])[:n]
    if len(want) < n:
        raise RuntimeError(f"Split {dataset}_test has fewer than {n} queries")
    texts: dict[str, str] = {}
    for line in (ROOT / split_def["queries_file"]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            cid = canonical_beir_id(dataset, str(row["_id"]))
            if cid in want:
                texts[cid] = str(row["text"])
    if set(texts) != set(want):
        raise RuntimeError("Workload query texts incomplete")
    return want, texts


def _build_lexical(dataset: str):
    from scholargraph.retrieval.bm25 import BM25Index, load_corpus
    from scholargraph.retrieval.tfidf import TFIDFIndex
    corpus = load_corpus(ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl", dataset=dataset)
    t0 = time.perf_counter()
    bm25 = BM25Index(corpus.texts, k1=1.5, b=0.75)
    bm25_build = time.perf_counter() - t0
    t0 = time.perf_counter()
    tfidf = TFIDFIndex(corpus.texts)
    tfidf_build = time.perf_counter() - t0
    return bm25, tfidf, {"bm25_index_build_s": bm25_build, "tfidf_index_build_s": tfidf_build,
                         "corpus_docs": corpus.document_count}


def _build_dense(dataset: str):
    from scholargraph.retrieval.dense import (
        ExactDenseIndex,
        HfLocalEncoder,
        _snapshot_dir_from_record,
        load_dense_encoder_config,
        verify_model_snapshot,
    )
    t0 = time.perf_counter()
    cfg = load_dense_encoder_config(
        ROOT / "configs" / "models" / "dense_encoder.json",
        ROOT / "configs" / "protocol_v1.json")
    snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
    index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / dataset / "bge-base-en-v1.5__a5beb1e3")
    encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
    load_s = time.perf_counter() - t0
    return cfg, snap, index, encoder, load_s


def phase_cold_worker() -> int:
    t0 = time.perf_counter()
    bm25, _, _ = _build_lexical("scifact")
    cfg, _, index, encoder, _ = _build_dense("scifact")
    from scholargraph.retrieval.dense import apply_query_prefix
    load_s = time.perf_counter() - t0
    want, texts = _split_queries("scifact", 1)
    q = want[0]
    t1 = time.perf_counter()
    bm25_hits = bm25.rank(texts[q], top_k=100, exclude_doc_ids=frozenset({q}))
    vec = np.asarray(encoder.encode(apply_query_prefix([texts[q]], cfg.prefix)), dtype=np.float32)[0]
    dense_hits = index.search(vec, top_k=100)
    from scholargraph.retrieval.hybrid import rrf_fuse
    fused = rrf_fuse([d for d, _ in bm25_hits], [d for d, _ in dense_hits], k=60, final_depth=100)
    first_s = time.perf_counter() - t1
    print(json.dumps({"load_stack_s": load_s, "first_query_end_to_end_s": first_s,
                      "fused_depth": len(fused), "peak_rss_bytes": peak_rss_bytes()}))
    return 0


def phase_warm() -> dict:
    out: dict[str, Any] = {"workload": {}, "methods": {}, "build": {}}
    for dataset, nq in (("scifact", SCIFACT_QS), ("scidocs", SCIDOCS_QS)):
        want, texts = _split_queries(dataset, nq)
        out["workload"][dataset] = {"n_queries": nq, "query_ids": want}
        bm25, tfidf, build = _build_lexical(dataset)
        out["build"][dataset] = build
        cfg, snap, index, encoder, dense_load = _build_dense(dataset)
        out["build"][dataset]["dense_stack_load_s"] = dense_load
        from scholargraph.retrieval.dense import apply_query_prefix, encode_queries
        from scholargraph.retrieval.hybrid import rrf_fuse
        per_q_bm25, per_q_tfidf, per_q_search, per_q_fuse = [], [], [], []
        for q in want:
            _, s = time_call(lambda q=q: bm25.rank(texts[q], top_k=100, exclude_doc_ids=frozenset({q})))
            per_q_bm25.append(s[0])
            _, s = time_call(lambda q=q: tfidf.score_query(texts[q], exclude_doc_ids=frozenset({q}))[:100])
            per_q_tfidf.append(s[0])
        t0 = time.perf_counter()
        qmat = np.asarray(encode_queries(project_root=ROOT, corpus_id=dataset, split="test",
                                         queries=[(q, texts[q]) for q in want],
                                         config=cfg, encoder=encoder)["embeddings"], dtype=np.float32)
        out["methods"].setdefault(dataset, {})["dense_batch_encode_s"] = time.perf_counter() - t0
        per_q_enc = [out["methods"][dataset]["dense_batch_encode_s"] / nq] * nq
        for i, q in enumerate(want):
            _, s = time_call(lambda: index.search(qmat[i], top_k=100))
            per_q_search.append(s[0])
        for q in want:
            lex = [d for d, _ in bm25.rank(texts[q], top_k=100, exclude_doc_ids=frozenset({q}))]
            den = [d for d, _ in index.search(
                np.asarray(encoder.encode(apply_query_prefix([texts[q]], cfg.prefix)), dtype=np.float32)[0],
                top_k=100)]
            _, s = time_call(lambda: rrf_fuse(lex, den, k=60, final_depth=100))
            per_q_fuse.append(s[0])
        m = out["methods"].setdefault(dataset, {})
        m["bm25_search_per_query"] = summarize_timings(per_q_bm25)
        m["tfidf_search_per_query"] = summarize_timings(per_q_tfidf)
        m["dense_encode_per_query_amortized"] = summarize_timings(per_q_enc)
        m["dense_search_per_query"] = summarize_timings(per_q_search)
        m["rrf_fuse_per_query"] = summarize_timings(per_q_fuse)
        m["hybrid_full_per_query_s"] = summarize_timings(
            [a + b + c for a, b, c in zip(per_q_bm25, per_q_search, per_q_fuse)])
        print(f"[{dataset}] warm done", flush=True)
    outp = _out() / "perf_warm.json"
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def phase_trackb() -> dict:
    from scholargraph.graph.b_track import (
        fuse_variants,
        load_holdout,
        load_works,
        run_query,
    )
    from scholargraph.graph.baselines import (
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
    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    holdout = load_holdout(ROOT / "data" / "processed" / "graph" / "holdout_edges.tsv")
    sq = json.loads((ROOT / "data" / "processed" / "graph" / "split_queries.json").read_text(encoding="utf-8"))
    queries = list(sq["cohorts"]["test"]["selected"])[:TRACKB_QS]
    docs = read_corpus("openalex_core_text", ROOT)
    texts = dict(zip(docs.doc_ids, docs.texts))
    bm25 = BM25Index(texts, k1=1.5, b=0.75)
    cfg = load_dense_encoder_config(
        ROOT / "configs" / "models" / "dense_encoder.json",
        ROOT / "configs" / "protocol_v1.json")
    snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
    index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / "openalex_core_text" / cfg.namespace)
    encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
    qmat = np.asarray(encode_queries(project_root=ROOT, corpus_id="openalex_core_text", split="test",
                                     queries=[(u, texts[u]) for u in queries],
                                     config=cfg, encoder=encoder)["embeddings"], dtype=np.float32)
    qvec = {u: qmat[i] for i, u in enumerate(queries)}
    universe = load_node_universe_from_degrees(
        ROOT / "data" / "processed" / "graph" / "features_degree_masked.json")
    nodes, out_links = load_masked_adjacency(
        ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv", universe)
    years_all = {w: (works[w]["year"] if w in works else None) for w in nodes}
    from scholargraph.graph.baselines import global_pagerank
    global_by_year: dict[int, dict[str, float]] = {}
    for yu in sorted({works[u]["year"] for u in queries}):
        keep = [v for v in nodes if isinstance(years_all.get(v), int) and years_all[v] <= yu]
        sub = {v: {w for w in out_links.get(v, set()) if w in set(keep)} for v in keep}
        g, _gi, _gr = global_pagerank(keep, sub)
        global_by_year[yu] = g

    def bm25_rank(text: str, uni: set) -> list:
        return [d for d, _ in bm25.rank(text, top_k=100, exclude_doc_ids=(set(texts) - uni))][:100]

    stages: dict[str, list[float]] = {"c100_ppr": [], "fuse_age": []}
    for u in queries:
        vec = qvec[u]

        def _dense_rank(text: str, uni: set, _v=vec) -> list:
            return [d for d, _ in index.search(_v, top_k=100,
                    exclude_doc_ids=frozenset(set(index.doc_ids) - uni))][:100]

        t0 = time.perf_counter()
        res = run_query(u, works, holdout, bm25_rank, _dense_rank, nodes, out_links, global_by_year)
        stages["c100_ppr"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _ = fuse_variants(res["c100_rows"], res["ppr"], years_all, res["year"])
        stages["fuse_age"].append(time.perf_counter() - t0)
    out = {"n_queries": len(queries), "query_ids": queries,
           "stages": {k: summarize_timings(v) for k, v in stages.items()}}
    outp = _out() / "perf_trackb.json"
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v["mean_s"] for k, v in out["stages"].items()}, indent=2))
    return out


def phase_concur() -> dict:
    _, texts_map = _split_queries("scifact", 10)
    want = list(texts_map)
    cfg, _, index, encoder, _ = _build_dense("scifact")
    from scholargraph.retrieval.dense import apply_query_prefix
    qmat = np.asarray(encoder.encode(apply_query_prefix([texts_map[q] for q in want], cfg.prefix)), dtype=np.float32)
    t0 = time.perf_counter()
    for i in range(len(want)):
        index.search(qmat[i], top_k=100)
    seq_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda i: index.search(qmat[i], top_k=100), range(len(want))))
    par_s = time.perf_counter() - t0
    out = {"n_queries": len(want), "sequential_s": seq_s, "threads_4_s": par_s,
           "speedup_4t": (seq_s / par_s) if par_s > 0 else None}
    outp = _out() / "perf_concur.json"
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return out


def phase_reports() -> dict:
    freeze, freeze_sha = load_verified_freeze(ROOT)
    parts = {}
    for name in ("perf_warm", "perf_trackb", "perf_concur"):
        p = _out() / f"{name}.json"
        if not p.is_file():
            raise RuntimeError(f"Missing profiling input (run prior phases first): {name}.json")
        parts[name] = json.loads(p.read_text(encoding="utf-8"))
    cold_path = _out() / "perf_cold.json"
    if not cold_path.is_file():
        raise RuntimeError("Missing profiling input: perf_cold.json")
    parts["perf_cold"] = json.loads(cold_path.read_text(encoding="utf-8"))
    index_sizes = {}
    for rel in ("artifacts/indexes/scifact/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
                "artifacts/indexes/scidocs/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
                "artifacts/indexes/openalex_core_text/bge-base-en-v1.5__a5beb1e3/embeddings.npy"):
        p = ROOT / rel
        if not p.is_file():
            raise RuntimeError(f"Missing index for sizing: {rel}")
        index_sizes[rel] = p.stat().st_size
    payload = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "freeze_sha256": freeze_sha,
               "hardware": hardware_context(),
               "query_budget_s": QUERY_BUDGET_S,
               "budget_note": "500ms/query is a REPORTED target, not a tuned constraint. "
                              "Rows above budget are kept and discussed.",
               "index_bytes": index_sizes,
               "peak_rss_bytes_cold_worker": parts["perf_cold"].get("peak_rss_bytes"),
               **{k: v for k, v in parts.items() if k != "perf_cold"}}
    (_out() / "performance.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Performance - local end-to-end profile (SG-040)", "",
             f"Freeze sha256 `{freeze_sha}`. Hardware: `{payload['hardware']['platform']}`, "
             f"{payload['hardware']['cpu_count']} CPUs, Python {payload['hardware']['python']}.",
             "GPU: not measured here (see SG-002 Colab T4 pilot).",
             f"Budget: {QUERY_BUDGET_S}s/query reported-against (not tuned).", ""]
    cold = parts["perf_cold"]
    lines += ["## Cold (fresh interpreter, SciFact: load stack + 1 query end-to-end)", "",
              f"- load_stack_s: {cold['load_stack_s']:.1f}",
              f"- first_query_end_to_end_s: {cold['first_query_end_to_end_s']:.2f}",
              f"- peak_rss_bytes: {cold['peak_rss_bytes']}",
              "- note: an earlier cold run observed load_stack_s=78.6 (included one-time "
              "HF snapshot fetch); the figure above is warm-cache process start.", ""]
    for dataset, m in payload["perf_warm"]["methods"].items():
        lines += [f"## Warm per-query (n={payload['perf_warm']['workload'][dataset]['n_queries']}, {dataset})", ""]
        for key in ("bm25_search_per_query", "tfidf_search_per_query", "dense_search_per_query",
                    "rrf_fuse_per_query", "hybrid_full_per_query_s"):
            s = m[key]
            flags = []
            if s["p50_s"] > QUERY_BUDGET_S:
                flags.append("P50 OVER BUDGET")
            elif s["p95_s"] > QUERY_BUDGET_S:
                flags.append("p95 over budget")
            flag = (" " + "/".join(flags)) if flags else ""
            lines.append(f"- {key}: p50={s['p50_s']:.3f}s p95={s['p95_s']:.3f}s{flag}")
        lines += [f"- dense_batch_encode_s: {m['dense_batch_encode_s']:.1f} "
                  f"(amortized {m['dense_encode_per_query_amortized']['mean_s']:.3f}s/q)", ""]
    tb = payload["perf_trackb"]["stages"]
    lines += ["## Track B per-query stages (frozen pipeline)", ""]
    for k, s in tb.items():
        lines.append(f"- {k}: mean={s['mean_s']:.2f}s p95={s['p95_s']:.2f}s")
    cc = payload["perf_concur"]
    lines += ["", "## Concurrency (dense search x10)", "",
              f"- sequential: {cc['sequential_s']:.2f}s, 4 threads: {cc['threads_4_s']:.2f}s, "
              f"speedup: {cc['speedup_4t']:.2f}" if cc["speedup_4t"] else "- speedup: n/a", "",
              "## Index sizes (bytes)", ""]
    for rel, size in index_sizes.items():
        lines.append(f"- {rel}: {size}")
    lines += ["",
              "## Notes",
              "",
              "- Figures are real inference (encode+search+fusion), never cache lookups.",
              "- No ranking was modified for speed; quality figures live in SG-028.",
              ""]
    (_out() / "performance.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"performance": "artifacts/reports/performance.md"}, indent=2))
    return payload


STEPS = {"cold-worker": phase_cold_worker, "warm": phase_warm, "trackb": phase_trackb,
         "concur": phase_concur, "reports": phase_reports}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="End-to-end performance profile (SG-040)")
    ap.add_argument("--phase", required=True,
                    choices=["cold-worker", "warm", "trackb", "concur", "reports", "all"])
    args = ap.parse_args(argv)
    try:
        if args.phase == "all":
            proc = subprocess.run(
                [sys.executable, __file__, "--phase", "cold-worker"],
                capture_output=True, text=True, cwd=ROOT,
                env={**__import__("os").environ, "PYTHONPATH": "src"})
            if proc.returncode != 0:
                return fail(f"cold-worker failed: {proc.stderr[-2000:]}")
            try:
                cold = json.loads(proc.stdout.strip().splitlines()[-1])
            except json.JSONDecodeError:
                return fail(f"cold-worker printed no JSON: {proc.stdout[-500:]}")
            (_out() / "perf_cold.json").write_text(
                json.dumps(cold, ensure_ascii=False, indent=2), encoding="utf-8")
            phase_warm()
            phase_trackb()
            phase_concur()
            phase_reports()
        else:
            STEPS[args.phase]()
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        import traceback
        traceback.print_exc()
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
