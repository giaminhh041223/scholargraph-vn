"""Candidate recall audit — task SG-021 (evaluator-side analysis).

Reads frozen retrieval runs (BM25, TF-IDF, optionally dense) plus dev qrels and
measures, per method and for the union (oracle pool):

- Recall@100, answerable rate (queries with >=1 relevant in pool),
- oracle nDCG@10: nDCG@10 of the ideal rerank restricted to the pool
  (relevant-in-pool first by grade desc, linear gain, log2 discount),
- candidate-miss vs rank-error breakdown + 10 real query examples.

This module is EVALUATOR-SIDE analysis: reading qrels here is authorized
(qrels never flow back into any ranker). Dense numbers are reported only when
a dense run file is supplied; otherwise dense is ``null`` (chua_do), never 0.

Failure contract (ADR-013/014): missing/malformed resources, duplicate IDs,
query-set mismatch or empty pools fail loudly; CLI exits 1.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.ingest.beir_loader import canonical_beir_id

MODULE_VERSION = "sg021-1.1.0"
SCHEMA_VERSION = 1


class CandidateDataError(Exception):
    """Fatal candidate-audit input problem."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CandidateDataError(f"Missing required file: {path}")
    except OSError as exc:
        raise CandidateDataError(f"Cannot read file {path}: {exc}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except FileNotFoundError:
        raise CandidateDataError(f"Missing required file: {path}")
    return h.hexdigest()


def load_qrels_grades(qrels_path: Path, namespace: str = "scifact") -> dict[str, dict[str, int]]:
    text = _read_text(qrels_path)
    lines = text.splitlines()
    if not lines:
        raise CandidateDataError(f"Empty qrels file: {qrels_path}")
    reader = csv.DictReader(lines, delimiter="\t")
    if reader.fieldnames != ["query-id", "corpus-id", "score"]:
        raise CandidateDataError(f"Unexpected qrels header in {qrels_path}: {reader.fieldnames}")
    out: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(reader, start=2):
        q, d, s = row["query-id"], row["corpus-id"], row["score"]
        if q is None or d is None or s is None or not str(q).strip() or not str(d).strip():
            raise CandidateDataError(f"Malformed qrels row {i} in {qrels_path}")
        try:
            grade = int(str(s).strip())
        except ValueError:
            raise CandidateDataError(f"Non-integer qrels score at row {i} in {qrels_path}: {s!r}")
        if grade < 0:
            raise CandidateDataError(f"Negative qrels score at row {i}: {grade}")
        if grade == 0:
            continue  # grade 0 = explicitly non-relevant, not a positive
        cq = canonical_beir_id(namespace, str(q).strip())
        cd = canonical_beir_id(namespace, str(d).strip())
        if (cq, cd) in seen:
            raise CandidateDataError(f"Duplicate qrels entry at row {i}: {cq} / {cd}")
        seen.add((cq, cd))
        out.setdefault(cq, {})[cd] = grade
    if not out:
        raise CandidateDataError(f"No positive qrels rows in {qrels_path}")
    return out


def load_rank_pools(rankings_path: Path, max_depth: int = 100) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {}
    raw_lines = _read_text(rankings_path).splitlines()
    for lineno, line in enumerate(raw_lines, start=1):
        if not line.strip():
            raise CandidateDataError(f"Blank line {lineno} in {rankings_path} (rejected, not skipped)")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CandidateDataError(f"Malformed rankings JSON line {lineno} in {rankings_path}: {exc}")
        if not isinstance(obj, dict) or "query_id" not in obj or "candidates" not in obj:
            raise CandidateDataError(f"Rankings line {lineno} lacks query_id/candidates")
        qid = obj["query_id"]
        cands = obj["candidates"]
        if not isinstance(qid, str) or not qid or not isinstance(cands, list) or not cands:
            raise CandidateDataError(f"Invalid rankings entry line {lineno}")
        if len(cands) > max_depth:
            raise CandidateDataError(f"Query {qid} exceeds depth {max_depth}")
        ids: list[str] = []
        seen: set[str] = set()
        for c in cands:
            if not isinstance(c, dict) or not isinstance(c.get("doc_id"), str) or not c["doc_id"]:
                raise CandidateDataError(f"Invalid candidate for {qid} line {lineno}")
            if c["doc_id"] in seen:
                raise CandidateDataError(f"Duplicate doc {c['doc_id']} for {qid}")
            seen.add(c["doc_id"])
            ids.append(c["doc_id"])
        if qid in pools:
            raise CandidateDataError(f"Duplicate query {qid} in {rankings_path}")
        pools[qid] = ids
    if not pools:
        raise CandidateDataError(f"No pools in {rankings_path}")
    return pools


def _dcg(grades_desc: Sequence[int], k: int) -> float:
    total = 0.0
    for i, g in enumerate(list(grades_desc)[:k]):
        total += g / math.log2(i + 2)
    return total


def oracle_ndcg_at_10(pool: Sequence[str], relevant: Mapping[str, int]) -> float | None:
    """Ideal nDCG@10 restricted to pool; None when query has no relevant docs."""
    if not relevant:
        return None
    in_pool = sorted(
        [d for d in pool if d in relevant],
        key=lambda d: (-relevant[d], d),
    )
    idcg = _dcg(sorted(relevant.values(), reverse=True), 10)
    if idcg == 0:
        return None
    return _dcg([relevant[d] for d in in_pool], 10) / idcg


def recall_at_k(pool: Sequence[str], relevant: Mapping[str, int], k: int = 100) -> float | None:
    if not relevant:
        return None
    hit = sum(1 for d in list(pool)[:k] if d in relevant)
    return hit / len(relevant)


def audit_pools(
    pools_by_method: dict[str, dict[str, list[str]]],
    qrels: dict[str, dict[str, int]],
) -> dict[str, Any]:
    query_ids = set(qrels.keys())
    for name, pools in pools_by_method.items():
        if set(pools.keys()) != query_ids:
            raise CandidateDataError(
                f"Method {name} covers {len(pools)} queries, qrels has {len(query_ids)}"
            )
    per_method: dict[str, Any] = {}
    union_pools = {q: sorted(set(sum((list(pools_by_method[m][q]) for m in pools_by_method), []))) for q in query_ids}
    for name, pools in pools_by_method.items():
        recs, oracles, missed = [], [], 0
        for q in sorted(query_ids):
            r = recall_at_k(pools[q], qrels[q])
            o = oracle_ndcg_at_10(pools[q], qrels[q])
            assert r is not None and o is not None
            recs.append(r)
            oracles.append(o)
            if r == 0:
                missed += 1
        per_method[name] = {
            "queries": len(query_ids),
            "mean_recall_at_100": sum(recs) / len(recs),
            "mean_oracle_ndcg_at_10": sum(oracles) / len(oracles),
            "answerable_rate": (len(query_ids) - missed) / len(query_ids),
            "fully_missed_queries": missed,
        }
    recs_u, oracles_u, missed_u = [], [], 0
    for q in sorted(query_ids):
        # Union oracle considers the FULL union set (up to 200 docs), not an
        # alphabetical top-100 slice: presence anywhere in the union counts.
        r = recall_at_k(union_pools[q], qrels[q], k=len(union_pools[q]))
        o = oracle_ndcg_at_10(union_pools[q], qrels[q])
        assert r is not None and o is not None
        recs_u.append(r)
        oracles_u.append(o)
        if r == 0:
            missed_u += 1
    return {"per_method": per_method, "union_oracle": {
        "queries": len(query_ids),
        "pool_depth": "full_union_up_to_200_not_top100",
        "mean_recall_full_union": sum(recs_u) / len(recs_u),
        "mean_oracle_ndcg_at_10": sum(oracles_u) / len(oracles_u),
        "answerable_rate": (len(query_ids) - missed_u) / len(query_ids),
        "fully_missed_queries": missed_u,
    }}


def pick_examples(
    pools: dict[str, list[str]],
    qrels: dict[str, dict[str, int]],
    per_query_ndcg: Mapping[str, float] | None = None,
    n_miss: int = 5,
    n_rank_error: int = 5,
) -> list[dict[str, Any]]:
    misses = [q for q in sorted(qrels) if recall_at_k(pools[q], qrels[q]) == 0]
    rank_errors = [q for q in sorted(qrels) if (recall_at_k(pools[q], qrels[q]) or 0) > 0]
    if per_query_ndcg:
        rank_errors.sort(key=lambda q: per_query_ndcg.get(q, 1.0))
    examples: list[dict[str, Any]] = []
    for q in misses[:n_miss]:
        rel = sorted(qrels[q])
        examples.append({"query_id": q, "case": "candidate_miss",
                         "reason": f"0/{len(rel)} relevant docs in pool; reranker cannot recover papers never retrieved.",
                         "relevant_docs": rel, "pool_size": len(pools[q])})
    for q in rank_errors[:n_rank_error]:
        rel = sorted(qrels[q])
        in_pool = sorted([d for d in pools[q] if d in qrels[q]])
        examples.append({"query_id": q, "case": "rank_error_candidate_present",
                         "reason": f"{len(in_pool)}/{len(rel)} relevant docs in pool but ranked low; reranking/fusion can help.",
                         "relevant_docs": rel, "relevant_in_pool": in_pool, "pool_size": len(pools[q])})
    return examples


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Candidate recall audit (SG-021, evaluator-side)")
    p.add_argument("--bm25-rankings", required=True)
    p.add_argument("--tfidf-rankings", required=True)
    p.add_argument("--dense-rankings", default=None)
    p.add_argument("--qrels", required=True)
    p.add_argument("--namespace", default="scifact")
    p.add_argument("--per-query", default=None, help="Optional per_query.json for rank-error ordering")
    p.add_argument("--output-md", required=True)
    p.add_argument("--output-json", required=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        qrels = load_qrels_grades(Path(args.qrels), args.namespace)
        methods = {
            "bm25": load_rank_pools(Path(args.bm25_rankings)),
            "tfidf": load_rank_pools(Path(args.tfidf_rankings)),
        }
        dense_status: str | None = None
        if args.dense_rankings:
            methods["dense"] = load_rank_pools(Path(args.dense_rankings))
            dense_status = "measured"
        stats = audit_pools(methods, qrels)
        stats["dense"] = "measured" if args.dense_rankings else None
        bm25_pools = methods["bm25"]
        union_sets = {q: set(bm25_pools[q]) | set(methods["tfidf"][q]) for q in qrels}
        rescued = sorted(q for q in qrels
                         if recall_at_k(bm25_pools[q], qrels[q]) == 0
                         and recall_at_k(sorted(union_sets[q]), qrels[q], k=len(union_sets[q])) > 0)
        stats["union_rescued_examples"] = [
            {"query_id": q,
             "relevant_docs": sorted(qrels[q]),
             "relevant_in_union": sorted(set(qrels[q]) & union_sets[q])}
            for q in rescued[:6]
        ]
        stats["inputs"] = {
            "bm25_rankings": {"path": str(args.bm25_rankings), "sha256": _sha256(Path(args.bm25_rankings))},
            "tfidf_rankings": {"path": str(args.tfidf_rankings), "sha256": _sha256(Path(args.tfidf_rankings))},
            "qrels": {"path": str(args.qrels), "sha256": _sha256(Path(args.qrels))},
            "per_query": {"path": str(args.per_query), "sha256": _sha256(Path(args.per_query))} if args.per_query else None,
            "dense_rankings": {"path": str(args.dense_rankings), "sha256": _sha256(Path(args.dense_rankings))} if args.dense_rankings else None,
        }
        per_q = None
        if args.per_query:
            # Missing nDCG@10 for a query defaults to 1.0 (only affects
            # rank-error example ordering, never any metric).
            per_q = {k: float(v.get("nDCG@10", 1.0)) for k, v in json.loads(Path(args.per_query).read_text(encoding="utf-8")).items() if isinstance(v, dict)}
        stats["examples"] = pick_examples(methods["bm25"], qrels, per_q)
        stats["meta"] = {"schema_version": SCHEMA_VERSION, "module_version": MODULE_VERSION,
                         "task_id": "SG-021", "generated_at": datetime.now(timezone.utc).isoformat(),
                         "dense": "chua_do_thieu_dense_run" if not args.dense_rankings else dense_status}
        out_json = Path(args.output_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Candidate recall audit (SG-021)", "",
                 f"Generated: {stats['meta']['generated_at']}",
                 f"Inputs: BM25 {args.bm25_rankings} (sha256 {stats['inputs']['bm25_rankings']['sha256'][:16]}...), "
                 f"TF-IDF {args.tfidf_rankings} (sha256 {stats['inputs']['tfidf_rankings']['sha256'][:16]}...), "
                 f"qrels {args.qrels} (sha256 {stats['inputs']['qrels']['sha256'][:16]}...)", ""]
        for m, s in stats["per_method"].items():
            lines += [f"## {m}", f"- queries: {s['queries']}",
                      f"- mean Recall@100: {s['mean_recall_at_100']:.4f}",
                      f"- mean oracle nDCG@10: {s['mean_oracle_ndcg_at_10']:.4f}",
                      f"- answerable rate: {s['answerable_rate']:.4f}",
                      f"- fully missed: {s['fully_missed_queries']}", ""]
        u = stats["union_oracle"]
        lines += ["## union oracle (bm25+tfidf, FULL union pool up to 200 docs — not top-100)",
                  f"- mean recall (full union): {u['mean_recall_full_union']:.4f}",
                  f"- mean oracle nDCG@10: {u['mean_oracle_ndcg_at_10']:.4f}",
                  f"- answerable rate: {u['answerable_rate']:.4f}",
                  f"- fully missed: {u['fully_missed_queries']}", "",
                  "## dense: chua_do (thieu dense run dev queries)", "",
                  "## 10 query examples"]
        for e in stats["examples"]:
            lines += [f"- {e['query_id']} [{e['case']}]: {e['reason']}"]
        if stats.get("union_rescued_examples"):
            lines += ["", "## BM25-missed queries rescued by TF-IDF in union"]
            for e in stats["union_rescued_examples"]:
                lines += [f"- {e['query_id']}: BM25 pool 0 relevant, union holds {len(e['relevant_in_union'])}/{len(e['relevant_docs'])}"]
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({"output_json": str(out_json), "output_md": str(out_md),
                          "queries": len(qrels)}, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
