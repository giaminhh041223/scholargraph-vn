"""Run track-B dev trials over the frozen 20-point gamma×lambda grid (SG-026).

Pipeline per dev query (see scholargraph.graph.b_track): BM25 + dense top-100
over U(u), RRF C100, PPR/global on the cutoff masked subgraph, 20 fused
variants, track-B evaluation vs held-out qrels. Writes the trial registry
(every trial incl. FAILED), metrics per variant, and the select_best outcome.

Outputs (dev-selection evidence, NOT sealed final runs):
  artifacts/reports/b_trials_dev.json
Exit 1 on any fatal problem. Reused by SG-028 for frozen final runs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from scholargraph.evaluation.tuning import select_best
from scholargraph.graph.b_track import (
    evaluate_variants,
    fuse_variants,
    internal_refs,
    load_holdout,
    load_works,
    query_universe,
    run_query,
)
from scholargraph.graph.baselines import global_pagerank, load_masked_adjacency, load_node_universe_from_degrees
from scholargraph.retrieval.bm25 import BM25Index
from scholargraph.retrieval.dense import (
    ExactDenseIndex,
    HfLocalEncoder,
    _snapshot_dir_from_record,
    encode_queries,
    load_dense_encoder_config,
    verify_model_snapshot,
)


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Track-B dev trials (SG-026)")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--output", default="artifacts/reports/b_trials_dev.json")
    ap.add_argument("--max-queries", type=int, default=None)
    args = ap.parse_args(argv)
    t_start = time.time()
    try:
        from scholargraph.retrieval.dense import read_corpus
        print("loading works...", flush=True)
        works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
        print(f"works: {len(works)}", flush=True)
        holdout = load_holdout(ROOT / "data" / "processed" / "graph" / "holdout_edges.tsv")
        sq = json.loads((ROOT / "data" / "processed" / "graph" / "split_queries.json").read_text(encoding="utf-8"))
        cohort = sq["cohorts"][args.split]
        queries = list(cohort["selected"])
        if args.max_queries:
            queries = queries[: args.max_queries]
        print(f"queries: {len(queries)}", flush=True)
        print("loading text corpus + BM25 index...", flush=True)
        docs = read_corpus("openalex_core_text", ROOT)
        texts = dict(zip(docs.doc_ids, docs.texts))
        bm25 = BM25Index(texts, k1=1.5, b=0.75)
        print("loading dense stack...", flush=True)
        cfg = load_dense_encoder_config(
            ROOT / "configs" / "models" / "dense_encoder.json",
            ROOT / "configs" / "protocol_v1.json")
        snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
        index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / "openalex_core_text" / cfg.namespace)
        encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
        qtexts = []
        for u in queries:
            if u not in texts:
                return fail(f"Query {u} outside dense text universe")
            qtexts.append((u, texts[u]))
        from scholargraph.retrieval.dense import encode_queries as _eq
        qmat = np.asarray(_eq(project_root=ROOT, corpus_id="openalex_core_text", split=args.split,
                              queries=qtexts, config=cfg, encoder=encoder)["embeddings"], dtype=np.float32)
        qvec = {u: qmat[i] for i, u in enumerate(queries)}
        print("loading masked graph + global PR per year...", flush=True)
        universe = load_node_universe_from_degrees(
            ROOT / "data" / "processed" / "graph" / "features_degree_masked.json")
        nodes, out = load_masked_adjacency(
            ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv", universe)
        years_all = {w: (works[w]["year"] if w in works else None) for w in nodes}
        global_by_year: dict[int, dict[str, float]] = {}
        for yu in sorted({works[u]["year"] for u in queries}):
            keep = [v for v in nodes if isinstance(years_all.get(v), int) and years_all[v] <= yu]
            sub = {v: {w for w in out.get(v, set()) if w in set(keep)} for v in keep}
            g, gi, gr = global_pagerank(keep, sub)
            global_by_year[yu] = g
            print(f"global PR year<={yu}: {len(keep)} nodes, {gi} iters", flush=True)

        def bm25_rank(text: str, uni: set) -> list:
            return [d for d, _ in bm25.rank(text, top_k=100, exclude_doc_ids=(set(texts) - uni))][:100]

        per_q: dict[str, Any] = {}
        universes: dict[str, set] = {}
        sources: dict[str, str] = {}
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
            variants = fuse_variants(res["c100_rows"], res["ppr"], years_all, res["year"])
            variants_g = fuse_variants(res["c100_rows"], res["global"], years_all, res["year"])
            per_q[u] = {"status": "COMPLETED", "seconds": time.time() - t0,
                        "heldout": res["heldout"], "universe_size": res["universe_size"],
                        "v_ppr": variants, "v_global": variants_g}
            refs = internal_refs(u, works, res["year"])
            obs = set(refs) - set(res["heldout"])
            universes[u] = query_universe(u, works, res["year"], obs)
            sources[u] = u
            print(f"[{i + 1}/{len(queries)}] {u} C100={len(res['c100'])} H={len(res['heldout'])}", flush=True)

        def _parse_variant(tag: str) -> tuple[float, float]:
            gpart, lpart = tag[1:].split("_l")
            return float(gpart), float(lpart)

        ok = {q: v for q, v in per_q.items() if v.get("status") == "COMPLETED"}
        failed = {q: v for q, v in per_q.items() if v.get("status") != "COMPLETED"}
        metrics: dict[str, Any] = {}
        trials: list[dict[str, Any]] = []
        if ok:
            variant_tags = list(next(iter(v["v_ppr"] for v in ok.values())))
            for tag in variant_tags:
                gval, lval = _parse_variant(tag)
                ev_p = evaluate_variants({q: {tag: ok[q]["v_ppr"][tag]} for q in ok},
                                         {q: holdout[q] for q in ok},
                                         {q: universes[q] for q in ok}, {q: q for q in ok}, nodes)
                metrics[f"hybrid_ppr_{tag}"] = ev_p[tag]
                trials.append({"trial_id": f"hybrid_ppr_{tag}", "track": "B",
                               "config": {"gamma": gval, "lambda": lval}, "status": "COMPLETED",
                               "metrics": ev_p[tag]})
            for tag in variant_tags:
                gval, lval = _parse_variant(tag)
                ev_g = evaluate_variants({q: {tag: ok[q]["v_global"][tag]} for q in ok},
                                         {q: holdout[q] for q in ok},
                                         {q: universes[q] for q in ok}, {q: q for q in ok}, nodes)
                metrics[f"hybrid_global_{tag}"] = ev_g[tag]
        for q, v in failed.items():
            trials.append({"trial_id": f"query_{q}", "track": "B", "config": {},
                           "status": "FAILED", "metrics": {}, "error": v.get("error")})
        selection = None
        sel_error = None
        try:
            selection = select_best([t for t in trials if t["track"] == "B" and t["status"] == "COMPLETED"])
        except Exception as exc:
            sel_error = f"{type(exc).__name__}: {exc}"
        payload = {"schema_version": 1, "task_id": "SG-026", "split": args.split,
                   "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                   "sealed_run": False, "queries": len(queries),
                   "completed_queries": len(ok), "failed_queries": {q: v.get("error") for q, v in failed.items()},
                   "metrics": metrics, "trials": trials,
                   "selection": selection, "selection_error": sel_error,
                   "elapsed_seconds": time.time() - t_start}
        outp = ROOT / args.output
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(outp), "completed": len(ok), "failed": len(failed),
                          "selection": selection}, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        import traceback
        traceback.print_exc()
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
