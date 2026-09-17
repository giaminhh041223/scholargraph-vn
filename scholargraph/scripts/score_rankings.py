"""Score a rankings JSONL file with ProtocolEvaluator (committed, reusable).

Inputs: rankings JSONL ({query_id, candidates:[{doc_id, rank, score}]}),
  split manifest (query IDs + corpus + qrels paths + hashes), track.
Writes a metrics JSON with input hashes + provenance. Exit 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.data.schemas import RankedDocument, RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator
from scholargraph.ingest.beir_loader import canonical_beir_id, sha256_file
from scholargraph.retrieval.candidates import load_qrels_grades


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score rankings (SG-026/SG-028)")
    ap.add_argument("--rankings", required=True)
    ap.add_argument("--split-manifest", required=True)
    ap.add_argument("--track", default="A", choices=["A", "B", "C"])
    ap.add_argument("--namespace", default="scifact")
    ap.add_argument("--corpus-file", required=True, help="Corpus JSONL for the universe")
    ap.add_argument("--output", required=True)
    ap.add_argument("--task-id", default="SG-026")
    args = ap.parse_args(argv)
    try:
        split = json.loads(Path(args.split_manifest).read_text(encoding="utf-8"))
        for key in ("query_ids", "qrels_file", "queries_sha256", "qrels_sha256"):
            if key not in split:
                return fail(f"Split manifest lacks {key}")
        want = list(split["query_ids"])
        rpath = Path(args.rankings)
        runs: dict[str, RankingResult] = {}
        seen: set[str] = set()
        for line in rpath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                return fail("Blank line in rankings file")
            o = json.loads(line)
            qid = o.get("query_id")
            if qid in seen:
                return fail(f"Duplicate query {qid}")
            seen.add(qid)
            cands = [RankedDocument(doc_id=c["doc_id"], score=float(c["score"]), rank=i + 1)
                     for i, c in enumerate(o.get("candidates", []))]
            runs[qid] = RankingResult(query_id=qid, candidates=cands)
        if set(runs) != set(want):
            return fail("Rankings queries != split queries")
        corpus_ids: list[str] = []
        cpath = ROOT / args.corpus_file
        if not cpath.is_file():
            return fail(f"Missing corpus file: {args.corpus_file}")
        for line in cpath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                return fail("Blank line in corpus file")
            corpus_ids.append(canonical_beir_id(args.namespace, str(json.loads(line)["_id"])))
        qrels = load_qrels_grades(ROOT / split["qrels_file"], args.namespace)
        ev = ProtocolEvaluator().evaluate(runs, qrels, query_ids=want, corpus_ids=corpus_ids, track=args.track)
        outp = Path(args.output)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps({
            "schema_version": 1, "task_id": args.task_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "track": args.track,
            "inputs": {"rankings": {"path": args.rankings, "sha256": sha256_file(rpath)},
                       "split_manifest": {"path": args.split_manifest,
                                          "sha256": sha256_file(ROOT / args.split_manifest)}},
            "metrics": ev["aggregate"], "per_query": ev["per_query"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(outp), "metrics": ev["aggregate"]}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
