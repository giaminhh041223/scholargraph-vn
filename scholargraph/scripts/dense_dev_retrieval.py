"""Dense retrieval on a BEIR dev split with the frozen SG-017/SG-019 stack.

Reads the split manifest (query IDs + qrels/queries paths + hashes), verifies
the exact dense index + pinned model revision, encodes split queries with the
query-only prefix on CPU, searches top-k exact cosine, evaluates track A with
ProtocolEvaluator, and writes rankings + metrics with provenance.

Writes (dev-selection evidence, NOT a sealed final run):
  artifacts/runs/dense_dev_<dataset>/rankings.jsonl
  artifacts/reports/dense_dev_<dataset>.json (metrics + provenance)
Exit 1 on any missing/malformed resource or verification failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from scholargraph.data.schemas import RankedDocument, RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator
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


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dense dev retrieval (SG-026 evidence)")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--split-manifest", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--top-k", type=int, default=100)
    args = ap.parse_args(argv)
    try:
        split = json.loads(Path(args.split_manifest).read_text(encoding="utf-8"))
        for key in ("query_ids", "queries_file", "queries_sha256", "qrels_file", "qrels_sha256"):
            if key not in split:
                return fail(f"Split manifest lacks {key}")
        qpath = ROOT / split["queries_file"]
        qrels_path = ROOT / split["qrels_file"]
        if sha256_file(qpath) != split["queries_sha256"]:
            return fail("queries sha256 mismatch")
        if sha256_file(qrels_path) != split["qrels_sha256"]:
            return fail("qrels sha256 mismatch")
        cfg = load_dense_encoder_config(
            ROOT / "configs" / "models" / "dense_encoder.json",
            ROOT / "configs" / "protocol_v1.json")
        snap = verify_model_snapshot(ROOT, cfg, verify_remote=False)
        index = ExactDenseIndex.load(ROOT / "artifacts" / "indexes" / args.dataset / args.namespace)
        if index.corpus_id != args.dataset:
            return fail("Index corpus mismatch")
        want = list(split["query_ids"])
        texts: dict[str, str] = {}
        for line in qpath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                return fail("Blank line in queries file")
            row = json.loads(line)
            cid = canonical_beir_id(args.dataset, str(row["_id"]))
            if cid in want:
                if not str(row.get("text", "")).strip():
                    return fail(f"Empty query text: {cid}")
                texts[cid] = str(row["text"])
        missing = [q for q in want if q not in texts]
        if missing:
            return fail(f"{len(missing)} split queries absent from queries file")
        encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap), config=cfg, device="cpu")
        t0 = time.time()
        pairs = [(qid, texts[qid]) for qid in want]
        manifest = encode_queries(project_root=ROOT, corpus_id=args.dataset, split="dev",
                                  queries=pairs, config=cfg, encoder=encoder)
        qmat = np.asarray(manifest["embeddings"], dtype=np.float32)
        if qmat.shape != (len(want), cfg.embedding_dimension):
            return fail(f"Query matrix shape {qmat.shape} unexpected")
        run_dir = ROOT / "artifacts" / "runs" / f"dense_dev_{args.dataset}"
        run_dir.mkdir(parents=True, exist_ok=True)
        rankings_path = run_dir / "rankings.jsonl"
        runs: dict[str, RankingResult] = {}
        with open(rankings_path, "w", encoding="utf-8") as f:
            for i, qid in enumerate(want):
                hits = index.search(qmat[i], top_k=args.top_k)
                cands = [RankedDocument(doc_id=d, score=float(s), rank=r + 1)
                         for r, (d, s) in enumerate(hits)]
                runs[qid] = RankingResult(query_id=qid, candidates=cands)
                f.write(json.dumps({"query_id": qid,
                                    "candidates": [c.model_dump() for c in cands]},
                                   ensure_ascii=False) + "\n")
        corpus_ids = list(index.doc_ids)
        qrels = load_qrels_grades(qrels_path, args.dataset)
        evaluation = ProtocolEvaluator().evaluate(runs, qrels, query_ids=want,
                                                  corpus_ids=corpus_ids, track="A")
        report = {
            "schema_version": 1, "task_id": "SG-026",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": args.dataset, "split": "dev", "top_k": args.top_k,
            "sealed_run": False,
            "note": "Dev-selection evidence only; sealed final runs belong to SG-028.",
            "inputs": {
                "split_manifest": {"path": args.split_manifest,
                                   "sha256": sha256_file(ROOT / args.split_manifest)},
                "index_manifest": dict(index.manifest),
                "model_snapshot": snap,
                "encode_seconds": time.time() - t0,
            },
            "metrics": evaluation["aggregate"],
            "rankings": str(rankings_path.relative_to(ROOT)),
            "rankings_sha256": sha256_file(rankings_path),
        }
        outp = ROOT / "artifacts" / "reports" / f"dense_dev_{args.dataset}.json"
        outp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(outp), "metrics": evaluation["aggregate"]}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
