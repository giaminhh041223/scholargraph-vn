"""Synthetic SG-008 golden, compiled-reference and negative-contract checks."""

import importlib.util
import io
import math
from pathlib import Path

import pytest
import pytrec_eval

from scholargraph.data.schemas import Qrel, RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("sg008_validation", ROOT / "scripts/validate_metrics.py")
validation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validation)


@pytest.mark.parametrize("case", validation.load_golden_cases(), ids=lambda c: c["id"])
def test_hand_derived_golden_and_compiled_reference(case):
    actual = validation.evaluate_case(case)
    reference = validation.reference_evaluate(case["runs"], case["qrels"], case["query_ids"])
    for qid in case["query_ids"]:
        assert actual["per_query"][qid] == pytest.approx(case["expected"][qid], rel=0, abs=validation.TOLERANCE)
        assert actual["per_query"][qid] == pytest.approx(reference["per_query"][qid], rel=0, abs=validation.TOLERANCE)
    expected_macro = {m: math.fsum(row[m] for row in case["expected"].values()) / len(case["query_ids"]) for m in validation.METRICS}
    assert actual["aggregate"] == pytest.approx(expected_macro, rel=0, abs=validation.TOLERANCE)


def test_randomized_fixed_seed_against_compiled_reference():
    case = validation.randomized_case()
    actual = validation.evaluate_case(case)
    reference = validation.reference_evaluate(case["runs"], case["qrels"], case["query_ids"])
    for qid in case["query_ids"]:
        assert actual["per_query"][qid] == pytest.approx(reference["per_query"][qid], rel=0, abs=validation.TOLERANCE)
    assert actual["aggregate"] == pytest.approx(reference["aggregate"], rel=0, abs=validation.TOLERANCE)


@pytest.mark.parametrize("name,kwargs", validation.negative_cases().items())
def test_invalid_inputs_fail_before_aggregation(name, kwargs):
    with pytest.raises(ValueError):
        ProtocolEvaluator().evaluate(**kwargs)


def test_locked_macro_keeps_missing_and_no_positive_queries():
    result = ProtocolEvaluator().evaluate(
        {"hit": RankingResult.create_sorted("hit", [("a", 1.0, None)]), "empty": RankingResult(query_id="empty")},
        {"hit": {"a": 1}, "empty": {"a": 1}, "missing": {"a": 1}, "unjudged": {}},
        query_ids=["hit", "empty", "missing", "unjudged"], corpus_ids=["a"],
    )
    assert result["aggregate"] == pytest.approx({"nDCG@10": .25, "Recall@100": .25, "MRR@10": .25, "MAP@100": .25, "P@5": .05})
    assert result["audit"]["missing_ranking_count"] == 2
    assert result["audit"]["empty_ranking_count"] == 1
    assert result["audit"]["no_positive_qrels_count"] == 1
    assert result["audit"]["query_count"] == 4


def test_all_empty_qrels_and_runs_are_zero():
    result = ProtocolEvaluator().evaluate({}, {}, query_ids=["q1", "q2"], corpus_ids=[])
    assert set(result["per_query"]) == {"q1", "q2"}
    assert all(value == 0.0 for value in result["aggregate"].values())
    assert result["audit"]["no_positive_qrels_count"] == 2


def test_unjudged_audit_distinguishes_judged_zero():
    case = validation.load_golden_cases()[0]
    result = validation.evaluate_case(case)
    assert result["audit"]["unjudged_counts"] == {"q": 1}
    assert result["audit"]["judged_zero_counts"] == {"q": 1}
    assert result["audit"]["returned_counts"] == {"q": 4}


def test_trec_strict_scores_prevent_reference_tie_reversal():
    ranking = RankingResult.create_sorted("q", [("b", 5.0, None), ("a", 5.0, None)])
    strict = pytrec_eval.parse_run(io.StringIO("\n".join(ranking.to_trec_lines())))
    raw = pytrec_eval.parse_run(io.StringIO("\n".join(ranking.to_trec_lines(strictly_decreasing_scores=False))))
    evaluator = pytrec_eval.RelevanceEvaluator({"q": {"a": 0, "b": 2}}, {"recip_rank"})
    assert strict["q"] == {"a": 2.0, "b": 1.0}
    assert evaluator.evaluate(strict)["q"]["recip_rank"] == .5
    assert evaluator.evaluate(raw)["q"]["recip_rank"] == 1.0
    assert [d.score for d in ranking.candidates] == [5.0, 5.0]


def test_track_c_labels_pooled_recall_and_map():
    case = validation.load_golden_cases()[0]
    result = ProtocolEvaluator().evaluate(case["runs"], case["qrels"], query_ids=case["query_ids"], corpus_ids=case["corpus_ids"], track="C")
    for rows in (result["aggregate"], result["per_query"]["q"]):
        assert "Recall@100" not in rows and "MAP@100" not in rows
        assert rows["pooled Recall@100"] == pytest.approx(2 / 3)
        assert rows["pooled MAP@100"] == pytest.approx(5 / 9)


def test_track_b_valid_eligible_universe_and_source_mapping():
    result = ProtocolEvaluator().evaluate(
        {"query": RankingResult.create_sorted("query", [("a", 2.0, None)])},
        {"query": {"a": 1, "b": 1, "source": 0}},
        query_ids=["query"], corpus_ids=["a", "b", "source"],
        eligible_ids={"query": {"a", "b"}}, query_document_ids={"query": "source"}, track="B",
    )
    assert result["aggregate"]["Recall@100"] == .5
    assert result["aggregate"]["MAP@100"] == .5


def test_qrel_sequence_agrees_with_mapping():
    case = validation.load_golden_cases()[0]
    rows = [Qrel(query_id=qid, doc_id=doc, score=grade, synthetic=True) for qid, labels in case["qrels"].items() for doc, grade in labels.items()]
    actual = ProtocolEvaluator().evaluate(case["runs"], rows, query_ids=case["query_ids"], corpus_ids=case["corpus_ids"])
    assert actual == validation.evaluate_case(case)


def test_reference_is_pinned_compiled_trec_eval():
    metadata = validation.reference_metadata()
    assert metadata["version"] == "0.5.10"
    assert len(metadata["binary_sha256"]) == 64
    assert metadata["binary_filename"].endswith((".pyd", ".so"))
