"""Synthetic end-to-end boundary: evaluator output survives SG-007 storage."""

import json
from pathlib import Path

import pytest

from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.metrics import EVALUATOR_VERSION, ProtocolEvaluator
from scholargraph.evaluation.runner import RunStore, sha256_path


def test_evaluated_metrics_roundtrip_with_missing_query_and_raw_ties(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    runs = {"fixture:q": RankingResult.create_sorted(
        "fixture:q", [("fixture:b", 0.5, None), ("fixture:a", 0.5, None)]
    )}
    query_ids = ["fixture:q", "fixture:missing"]
    qrels = {"fixture:q": {"fixture:a": 2, "fixture:b": 0},
             "fixture:missing": {"fixture:b": 1}}
    result = ProtocolEvaluator().evaluate(
        runs, qrels, query_ids=query_ids, corpus_ids=["fixture:a", "fixture:b"]
    )
    handle = RunStore(tmp_path / "runs").create(
        method="metric-fixture", dataset="synthetic-sg008", split="dev",
        resolved_config={"evaluator_revision": EVALUATOR_VERSION, "track": "A"},
        data_source={"synthetic": True, "qrels": qrels},
        split_definition={"synthetic": True, "query_ids": query_ids},
        code_source={"commit": None, "source_hashes": {
            "metrics.py": sha256_path(root / "src/scholargraph/evaluation/metrics.py")}},
        model={"id": "synthetic-fixed-ranking", "revision": "1"}, seed=20260915,
        command=["pytest", "tests/unit/test_metrics_runner.py"], synthetic=True,
    )
    ranking_path = handle.record_rankings(list(runs.values()))
    query_path = handle.record_per_query(result["per_query"])
    manifest = handle.complete(result["aggregate"])
    handle.verify_integrity()
    stored_run = RankingResult.model_validate_json(ranking_path.read_text(encoding="utf-8"))
    stored_metrics = json.loads(query_path.read_text(encoding="utf-8"))
    assert [doc.score for doc in stored_run.candidates] == [0.5, 0.5]
    assert [doc.doc_id for doc in stored_run.candidates] == ["fixture:a", "fixture:b"]
    assert set(stored_metrics) == set(query_ids)
    assert stored_metrics["fixture:missing"]["MRR@10"] == 0.0
    assert manifest["aggregate_metrics"]["nDCG@10"] == pytest.approx(0.5)
    assert manifest["aggregate_metrics"]["MAP@100"] == pytest.approx(0.5)
    assert manifest["synthetic"] is True
