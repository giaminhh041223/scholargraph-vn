"""Validate SG-008 against hand-derived fixtures and the compiled trec_eval.

Only synthetic inputs are used. Run with the project's Python environment:
    .venv/Scripts/python.exe scripts/validate_metrics.py
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import platform
import random
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.data.schemas import RankedDocument, RankingResult, Qrel
from scholargraph.evaluation.metrics import ProtocolEvaluator

FIXTURE = ROOT / "tests/fixtures/metric_golden.json"
REFERENCE_VERSION = "0.5.10"
TOLERANCE = 1e-12
RANDOM_SEED = 20260916
METRIC_MAP = {
    "nDCG@10": "ndcg_cut_10",
    "Recall@100": "recall_100",
    "MAP@100": "map_cut_100",
    "P@5": "P_5",
}
METRICS = (*METRIC_MAP, "MRR@10")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_metadata() -> dict:
    import pytrec_eval
    import pytrec_eval_ext

    version = importlib.metadata.version("pytrec-eval-terrier")
    if version != REFERENCE_VERSION:
        raise RuntimeError(f"Reference version must be {REFERENCE_VERSION}, got {version}")
    binary = Path(pytrec_eval_ext.__file__)
    wrapper = Path(pytrec_eval.__file__)
    return {
        "package": "pytrec-eval-terrier", "version": version,
        "implementation": "compiled C trec_eval via pytrec_eval_ext",
        "binary_filename": binary.name, "binary_sha256": sha256(binary),
        "wrapper_sha256": sha256(wrapper),
        "package_source": "https://pypi.org/project/pytrec-eval-terrier/0.5.10/",
        "mrr_mapping": "recip_rank on serialized run truncated to top 10",
        "locked_query_adapter": "Fill absent empty-qrel/reference results with zero; macro over all locked IDs.",
    }


def reference_evaluate(runs: dict, qrels: dict, query_ids: list[str]) -> dict:
    """Use actual trec_eval; adaptation only preserves contract query denominator.

    Parsing the TREC text exercises production score serialization. C trec_eval
    ignores qids with empty judgments; the protocol explicitly retains zero rows.
    No local metric formula is used by this reference adapter.
    """
    import pytrec_eval

    lines = [line for ranking in runs.values() for line in ranking.to_trec_lines()]
    parsed = pytrec_eval.parse_run(io.StringIO("\n".join(lines)))
    parsed = {qid: parsed.get(qid, {}) for qid in query_ids}
    judged = {qid: labels for qid, labels in qrels.items() if labels}
    full = pytrec_eval.RelevanceEvaluator(
        judged, {"ndcg_cut.10", "recall.100", "map_cut.100", "P.5"}
    ).evaluate(parsed) if judged else {}
    cut_lines = [line for ranking in runs.values() for line in ranking.to_trec_lines()[:10]]
    cut = pytrec_eval.parse_run(io.StringIO("\n".join(cut_lines)))
    cut = {qid: cut.get(qid, {}) for qid in query_ids}
    rr = pytrec_eval.RelevanceEvaluator(judged, {"recip_rank"}).evaluate(cut) if judged else {}
    per_query = {}
    for qid in query_ids:
        row = {name: full.get(qid, {}).get(trec, 0.0) for name, trec in METRIC_MAP.items()}
        row["MRR@10"] = rr.get(qid, {}).get("recip_rank", 0.0)
        per_query[qid] = row
    return {
        "per_query": per_query,
        "aggregate": {m: math.fsum(row[m] for row in per_query.values()) / len(query_ids) for m in METRICS},
    }


def load_golden_cases() -> list[dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("synthetic") is not True:
        raise ValueError("Only explicitly synthetic validation fixtures are allowed")
    cases = []
    for source in fixture["cases"]:
        case = dict(source)
        generator = case.get("generator")
        if generator:
            docs = [f"d{i:03d}" for i in range(1, generator["corpus_size"] + 1)]
            case.update(query_ids=["q"], corpus_ids=docs)
            if generator["kind"] == "all_positive":
                case["qrels"] = {"q": {d: 1 for d in docs}}
            elif generator["kind"] == "single_positive":
                case["qrels"] = {"q": {docs[generator["positive_rank"] - 1]: 1}}
            else:
                raise ValueError("Unknown synthetic generator")
            case["runs"] = {"q": [[d, float(len(docs) - i)] for i, d in enumerate(docs[:generator["ranking_size"]])]}
        case["runs"] = {
            qid: RankingResult.create_sorted(qid, [(d, score, None) for d, score in rows])
            for qid, rows in case["runs"].items()
        }
        cases.append(case)
    return cases


def randomized_case(seed: int = RANDOM_SEED, query_count: int = 40) -> dict:
    rng = random.Random(seed)
    docs = [f"d{i:03d}" for i in range(160)]
    qids = [f"q{i:03d}" for i in range(query_count)]
    qrels, runs = {}, {}
    for i, qid in enumerate(qids):
        qrels[qid] = {d: rng.randrange(3) for d in rng.sample(docs, rng.randrange(161))}
        if i % 7 == 0:
            continue
        chosen = rng.sample(docs, [0, 1, 5, 10, 11, 100, 101, 160][i % 8])
        runs[qid] = RankingResult.create_sorted(qid, [(d, float(rng.randrange(-3, 4)), None) for d in chosen])
    return {"id": "randomized", "runs": runs, "qrels": qrels, "query_ids": qids, "corpus_ids": docs}


def evaluate_case(case: dict) -> dict:
    return ProtocolEvaluator().evaluate(case["runs"], case["qrels"], query_ids=case["query_ids"], corpus_ids=case["corpus_ids"])


def negative_cases() -> dict[str, dict]:
    """Independent invalid input contracts, including corruption after construction."""
    def base():
        return dict(runs={"q": RankingResult.create_sorted("q", [("a", 2.0, None), ("b", 1.0, None)])},
                    qrels={"q": {"a": 1}}, query_ids=["q"], corpus_ids=["a", "b", "q"])

    cases = {}
    def changed(name, **kwargs):
        case = base()
        case.update(kwargs)
        cases[name] = case

    changed("duplicate_locked_queries", query_ids=["q", "q"])
    changed("empty_locked_queries", query_ids=[])
    changed("unknown_run_query", runs={"other": RankingResult(query_id="other")})
    changed("unknown_qrel_query", qrels={"other": {"a": 1}})
    changed("ranking_query_mismatch", runs={"q": RankingResult(query_id="other")})
    changed("ranking_outside_corpus", corpus_ids=["a"])
    changed("qrel_outside_corpus_even_zero", qrels={"q": {"outside": 0}})
    changed("positive_outside_eligible", eligible_ids={"q": {"b"}})
    changed("ranking_outside_eligible", qrels={"q": {"a": 1}}, eligible_ids={"q": {"a"}})
    changed("eligible_outside_corpus", eligible_ids={"q": {"a", "b", "outside"}})
    changed("missing_eligible_query", eligible_ids={})
    changed("duplicate_qrels", qrels=[Qrel(query_id="q", doc_id="a", score=1, synthetic=True)] * 2)
    changed("conflicting_qrels", qrels=[Qrel(query_id="q", doc_id="a", score=1, synthetic=True), Qrel(query_id="q", doc_id="a", score=2, synthetic=True)])
    for grade in [-1, 3, 1.5, True, "1", float("nan")]:
        changed(f"invalid_grade_{grade}", qrels={"q": {"a": grade}})
    changed("invalid_track", track="unknown")
    changed("raw_ranking_is_not_schema", runs={"q": [("a", 2.0)]})
    changed("noncanonical_query_id", query_ids=[" q"], runs={}, qrels={})
    changed("noncanonical_doc_id", corpus_ids=["a", " b"])
    changed("automatic_track_a_self_ranking", runs={"q": RankingResult.create_sorted("q", [("q", 1.0, None)])})
    changed("automatic_track_a_positive_self_qrel", qrels={"q": {"q": 1}})
    changed("explicit_source_self_ranking", query_document_ids={"q": "b"})
    changed("explicit_source_positive_self_qrel", runs={"q": RankingResult(query_id="q")}, query_document_ids={"q": "a"})
    changed("source_outside_corpus", query_document_ids={"q": "outside"})
    changed("track_b_missing_source_and_eligible", track="B")
    changed("track_b_missing_source", track="B", eligible_ids={"q": {"a", "b"}})
    changed("track_b_missing_eligible", track="B", query_document_ids={"q": "q"})
    for name, candidates in {
        "mutable_duplicate": [RankedDocument(doc_id="a", score=2, rank=1), RankedDocument(doc_id="a", score=1, rank=2)],
        "mutable_rank_gap": [RankedDocument(doc_id="a", score=2, rank=2)],
        "mutable_score_order": [RankedDocument(doc_id="a", score=1, rank=1), RankedDocument(doc_id="b", score=2, rank=2)],
        "mutable_tie_order": [RankedDocument(doc_id="b", score=1, rank=1), RankedDocument(doc_id="a", score=1, rank=2)],
        "mutable_nan": [RankedDocument.model_construct(doc_id="a", score=float("nan"), rank=1)],
        "mutable_inf": [RankedDocument.model_construct(doc_id="a", score=float("inf"), rank=1)],
        "mutable_noncanonical_id": [RankedDocument.model_construct(doc_id=" a", score=1, rank=1)],
    }.items():
        case = base()
        case["runs"]["q"].candidates[:] = candidates
        cases[name] = case
    return cases


def comparison(actual: dict, expected: dict, name: str) -> dict:
    diffs = {m: abs(actual[m] - expected[m]) for m in METRICS}
    passed = all(math.isfinite(v) and v <= TOLERANCE for v in diffs.values())
    return {"name": name, "passed": passed, "actual": actual, "expected": expected, "absolute_errors": diffs}


def build_report() -> dict:
    metadata = reference_metadata()
    checks, evaluator_version = [], None
    cases = load_golden_cases() + [randomized_case()]
    for case in cases:
        actual = evaluate_case(case)
        evaluator_version = actual["evaluator_version"]
        reference = reference_evaluate(case["runs"], case["qrels"], case["query_ids"])
        for qid in case["query_ids"]:
            checks.append(comparison(actual["per_query"][qid], reference["per_query"][qid], f"reference/{case['id']}/{qid}"))
            if "expected" in case:
                checks.append(comparison(actual["per_query"][qid], case["expected"][qid], f"hand/{case['id']}/{qid}"))
        checks.append(comparison(actual["aggregate"], reference["aggregate"], f"macro/{case['id']}"))
    negatives = []
    for name, kwargs in negative_cases().items():
        try:
            ProtocolEvaluator().evaluate(**kwargs)
        except ValueError as exc:
            negatives.append({"name": name, "passed": True, "error_type": type(exc).__name__})
        else:
            negatives.append({"name": name, "passed": False, "error_type": None})
    files = [FIXTURE, Path(__file__), ROOT / "src/scholargraph/evaluation/metrics.py",
             ROOT / "src/scholargraph/data/schemas.py", ROOT / "tests/unit/test_metrics_reference.py",
             ROOT / "requirements/sg008-verification.txt", ROOT / "docs/RESEARCH_PROTOCOL.md"]
    return {
        "schema_version": 1, "task_id": "SG-008", "synthetic": True,
        "scope": "Evaluator verification only; no real benchmark run or retrieval-quality claim.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation_passed": all(c["passed"] for c in checks + negatives),
        "evaluator_version": evaluator_version, "reference_evaluator": metadata,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "tolerance_absolute": TOLERANCE, "random_seed": RANDOM_SEED,
        "random_query_count": 40, "golden_case_count": len(cases) - 1,
        "comparison_count": len(checks), "negative_case_count": len(negatives),
        "max_absolute_error": max(v for c in checks for v in c["absolute_errors"].values()),
        "checks": checks, "negative_checks": negatives,
        "file_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in files},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/reports/metric_validation.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "artifacts/reports"):
        parser.error("Validation output must remain inside ScholarGraph artifacts/reports")
    report = build_report()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"validation_passed": report["validation_passed"], "comparisons": report["comparison_count"],
                      "negative_cases": report["negative_case_count"], "max_absolute_error": report["max_absolute_error"], "output": str(output)}))
    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
