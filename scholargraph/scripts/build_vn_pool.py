"""Blinded VN relevance pools + labeling scaffolding (SG-033 tooling part).

Pool: top-10 from 3 frozen methods (translated_bm25, multilingual_dense_e5,
vn_hybrid_rrf k=60) over the OpenAlex text-subset (18.250 works), deduped,
shuffled with seed 20260915. The pool file carries NO method/score provenance
(blinding); provenance is sealed separately for SG-034 analysis and must never
be shown during labeling.

Human part (NOT this script): 2 members judge dev pools first (SG-034 selects
the default method), then test pools. Labels, kappa, adjudication belong to
the members; the agent must never fabricate relevance labels.

Outputs:
  data/annotations/vn_pool.json            (blinded pools + metadata)
  data/annotations/vn_pool_provenance.json  (sealed method mapping, SG-034 only)
  data/annotations/vn_labels.jsonl          (empty template for the members)
Usage: build_vn_pool.py [--depth 10] [--seed 20260915]
Exit 1 on any fatal problem (unapproved manifest, incomplete cache, drift).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

TASK_ID = "SG-033"
MODULE_VERSION = "sg033-1.0.0"
POOL_METHODS = ("translated_bm25", "multilingual_dense_e5", "vn_hybrid_rrf")
POOL_SEED = 20260915


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _sha(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Missing required file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs() -> tuple[list[dict], dict[str, dict], dict]:
    from scholargraph.retrieval.cross_lingual import load_approved_manifest

    manifest = load_approved_manifest(ROOT / "data/annotations/vn_query_manifest.json")
    if manifest.get("status") != "approved_no_edits":
        raise RuntimeError(
            f"Query manifest not human-approved (status={manifest.get('status')!r}); refusing pool.")
    queries = manifest["queries"]
    if len(queries) != 30:
        raise RuntimeError(f"Expected 30 approved queries, got {len(queries)}")
    cache = json.loads((ROOT / "data/processed/vn/translations_cache.json").read_text(encoding="utf-8"))
    entries = cache.get("entries", {})
    missing = [q["query_id"] for q in queries if q["query_id"] not in entries
               or not str(entries[q["query_id"]].get("text_en", "")).strip()]
    if missing:
        raise RuntimeError(f"Translation cache incomplete for {len(missing)} queries")
    for q in queries:
        if not str(q.get("text_vi", "")).strip():
            raise RuntimeError(f"Empty text_vi for {q['query_id']}")
    return queries, entries, manifest


def retrieve_translated_bm25(queries: list[dict], entries: dict) -> tuple[dict[str, list[str]], dict]:
    from scholargraph.graph.b_track import load_works
    from scholargraph.retrieval.bm25 import BM25Index

    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    texts = {w: f"{info['title']} {info['abstract']}".strip() for w, info in works.items()}
    textless = sorted(w for w, t in texts.items() if not t)
    # ADR-017: textless works are excluded from every retrieval universe (they can
    # never enter a pool); recorded here, never silently dropped from the counts.
    texts = {w: t for w, t in texts.items() if t}
    if not texts:
        raise RuntimeError("Empty OpenAlex text universe")
    t0 = time.time()
    bm25 = BM25Index(texts, k1=1.5, b=0.75)
    build_s = time.time() - t0
    out: dict[str, list[str]] = {}
    for q in queries:
        en = str(entries[q["query_id"]]["text_en"])
        hits = bm25.rank(en, top_k=100)
        if not hits:
            raise RuntimeError(f"Empty BM25 ranking for {q['query_id']}")
        out[q["query_id"]] = [d for d, _ in hits]
    return out, {"index_build_s": build_s, "corpus_docs": len(texts),
                 "textless_excluded": textless}


def retrieve_multilingual_dense(queries: list[dict]) -> tuple[dict[str, list[str]], dict]:
    from scholargraph.retrieval.cross_lingual import MultilingualEncoder, _load_multilingual_config

    cfg_path = ROOT / "configs" / "models" / "multilingual_candidate_e5.json"
    cfg = _load_multilingual_config(cfg_path)
    if cfg["model_id"] != "intfloat/multilingual-e5-base":
        raise RuntimeError("Pinned multilingual model moved; refusing pool without re-pin")
    snap = ROOT / cfg["snapshot_local"] / "snapshots" / cfg["revision"] if cfg.get("snapshot_local") else None
    index_dir = ROOT / "artifacts" / "indexes" / "multilingual" / "e5_openalex_core_text"
    ids = json.loads((index_dir / "doc_ids.json").read_text(encoding="utf-8"))
    matrix = np.load(index_dir / "embeddings.npy")
    if matrix.shape[0] != len(ids):
        raise RuntimeError("e5 OpenAlex index misaligned")
    encoder = MultilingualEncoder(cfg, snap)
    t0 = time.time()
    vectors = encoder.encode([q["text_vi"] for q in queries], is_query=True)
    encode_s = time.time() - t0
    out: dict[str, list[str]] = {}
    for q, vec in zip(queries, vectors):
        v = np.asarray(vec, dtype=np.float32)
        n = float(np.linalg.norm(v))
        if not np.isfinite(n) or n == 0.0:
            raise RuntimeError(f"Bad query vector for {q['query_id']}")
        scores = matrix @ v
        if not np.all(np.isfinite(scores)):
            raise RuntimeError(f"Non-finite dense scores for {q['query_id']}")
        order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), ids[i]))[:100]
        out[q["query_id"]] = [ids[i] for i in order]
    return out, {"query_encode_s": encode_s, "index_docs": len(ids),
                 "model_id": cfg["model_id"], "revision": cfg["revision"]}


def build_pools(depth: int, seed: int) -> dict:
    if depth < 1 or depth > 100:
        raise RuntimeError(f"Pool depth must be within [1, 100], got {depth!r}")
    queries, entries, manifest = load_inputs()
    bm25_orders, bm25_info = retrieve_translated_bm25(queries, entries)
    dense_orders, dense_info = retrieve_multilingual_dense(queries)
    from scholargraph.retrieval.hybrid import rrf_fuse
    hybrid_orders: dict[str, list[str]] = {}
    for q in queries:
        qid = q["query_id"]
        rows = rrf_fuse(bm25_orders[qid][:100], dense_orders[qid][:100], k=60, final_depth=100)
        hybrid_orders[qid] = [r["doc_id"] for r in rows]
    # Work metadata for the pool file (title/year only — no scores, no methods).
    from scholargraph.graph.b_track import load_works
    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    rng = random.Random(seed)
    pools: list[dict] = []
    provenance: dict[str, dict[str, list[str]]] = {}
    total_unique = 0
    for q in sorted(queries, key=lambda r: r["query_id"]):
        qid = q["query_id"]
        per_method = {"translated_bm25": bm25_orders[qid][:depth],
                      "multilingual_dense_e5": dense_orders[qid][:depth],
                      "vn_hybrid_rrf": hybrid_orders[qid][:depth]}
        union: list[str] = list(dict.fromkeys(
            d for m in POOL_METHODS for d in per_method[m]))
        if not union:
            raise RuntimeError(f"Empty pool for {qid}")
        provenance[qid] = {d: sorted(m for m in POOL_METHODS if d in per_method[m]) for d in union}
        blinded = list(union)
        rng.shuffle(blinded)
        rows = []
        for pos, d in enumerate(blinded, start=1):
            info = works.get(d)
            if info is None:
                raise RuntimeError(f"Pooled doc outside works universe: {d}")
            rows.append({"position": pos, "doc_id": d,
                         "title": info["title"][:300], "year": info["year"]})
        total_unique += len(union)
        pools.append({"query_id": qid, "split": q["split"], "intent_family": q["intent_family"],
                      "text_vi": q["text_vi"], "text_en": str(entries[qid]["text_en"]),
                      "pool_size": len(union), "candidates": rows})
    return {"queries": queries, "pools": pools, "provenance": provenance,
            "total_unique_pairs": total_unique, "bm25_info": bm25_info,
            "dense_info": dense_info, "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build blinded VN pools (SG-033 tooling)")
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--seed", type=int, default=POOL_SEED)
    args = ap.parse_args(argv)
    try:
        if args.seed != POOL_SEED:
            raise RuntimeError(f"Pool seed pinned to {POOL_SEED}; refusing {args.seed}")
        t0 = time.time()
        built = build_pools(args.depth, args.seed)
        outdir = ROOT / "data" / "annotations"
        for name in ("vn_pool.json", "vn_pool_provenance.json", "vn_labels.jsonl"):
            if (outdir / name).exists():
                raise RuntimeError(
                    f"Refusing to overwrite {name} (labels may already be filled); "
                    "move it aside with a versioned name first.")
        manifest_sha = _sha(ROOT / "data/annotations/vn_query_manifest.json")
        cache_sha = _sha(ROOT / "data/processed/vn/translations_cache.json")
        meta = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "methods": list(POOL_METHODS), "depth": args.depth, "seed": args.seed,
                "dedup": True, "blinded": True,
                "blinding_note": "Pool rows carry no method/score provenance. "
                                 "Provenance lives ONLY in vn_pool_provenance.json, "
                                 "which must stay hidden until SG-034 analysis.",
                "inputs": {"vn_query_manifest_sha256": manifest_sha,
                           "translations_cache_sha256": cache_sha},
                "counts": {"queries": len(built["pools"]),
                           "dev": sum(1 for p in built["pools"] if p["split"] == "dev"),
                           "test": sum(1 for p in built["pools"] if p["split"] == "test"),
                           "unique_pairs": built["total_unique_pairs"]},
                "retrieval": {"translated_bm25": built["bm25_info"],
                              "multilingual_dense_e5": built["dense_info"]},
                "elapsed_seconds": time.time() - t0}
        pool_doc = {**meta, "pools": built["pools"]}
        (outdir / "vn_pool.json").write_text(
            json.dumps(pool_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        prov_doc = {"schema_version": 1, "task_id": TASK_ID,
                    "generated_at": meta["generated_at"],
                    "sealed_for": "SG-034 analysis only — hidden during labeling",
                    "seed": args.seed, "depth": args.depth,
                    "provenance": built["provenance"]}
        (outdir / "vn_pool_provenance.json").write_text(
            json.dumps(prov_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        # Empty label template: one row per pair, to be filled by member A and B.
        with open(outdir / "vn_labels.jsonl", "w", encoding="utf-8") as f:
            for p in built["pools"]:
                for cand in p["candidates"]:
                    f.write(json.dumps({"query_id": p["query_id"], "doc_id": cand["doc_id"],
                                        "label": None, "annotator": None,
                                        "round": "independent", "note": None},
                                       ensure_ascii=False) + "\n")
        print(json.dumps({"pools": len(built["pools"]), "unique_pairs": built["total_unique_pairs"],
                          "dev": meta["counts"]["dev"], "test": meta["counts"]["test"],
                          "elapsed_s": round(meta["elapsed_seconds"], 1)}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        import traceback
        traceback.print_exc()
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
