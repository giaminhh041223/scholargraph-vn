"""SG-026 tuning harness tests: selection + adversarial."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholargraph.evaluation.tuning import (
    TuningDataError,
    load_registry,
    select_best,
    validate_space,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _trial(tid: str, ndcg: float, gamma: float = 0.0, lamb: float = 0.0,
           status: str = "COMPLETED") -> dict:
    return {"trial_id": tid, "track": "B", "config": {"gamma": gamma, "lambda": lamb},
            "status": status, "metrics": {"nDCG@10": ndcg} if status == "COMPLETED" else {}}


def test_select_max_dev() -> None:
    best = select_best([_trial("a", 0.5), _trial("b", 0.7), _trial("c", 0.6)])
    assert best["best_trial_id"] == "b"


def test_tie_smaller_gamma_lambda() -> None:
    best = select_best([_trial("a", 0.7, gamma=0.2), _trial("b", 0.7, gamma=0.1),
                        _trial("c", 0.7, gamma=0.1, lamb=0.05), _trial("d", 0.7, gamma=0.1, lamb=0.01)])
    assert best["best_trial_id"] == "b"  # smaller gamma, then smallest lambda (0.0)


def test_failed_excluded_with_count() -> None:
    best = select_best([_trial("a", 0.9), _trial("bad", 0.0, status="FAILED")])
    assert best["best_trial_id"] == "a"
    assert best["failed_excluded"] == 1 and best["failed_ids"] == ["bad"]


def test_all_failed_refuses() -> None:
    with pytest.raises(TuningDataError):
        select_best([_trial("bad", 0.0, status="FAILED")])


def test_empty_registry_refuses(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"trials": []}), encoding="utf-8")
    with pytest.raises(TuningDataError):
        load_registry(p)


def test_duplicate_trial_rejected(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"trials": [_trial("a", 0.5), _trial("a", 0.6)]}), encoding="utf-8")
    with pytest.raises(TuningDataError):
        load_registry(p)


def test_test_metric_rejected(tmp_path: Path) -> None:
    t = _trial("a", 0.5)
    t["metrics"]["test_nDCG@10"] = 0.9
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"trials": [t]}), encoding="utf-8")
    with pytest.raises(TuningDataError):
        load_registry(p)


def test_missing_primary_rejected(tmp_path: Path) -> None:
    t = {"trial_id": "a", "track": "B", "config": {}, "status": "COMPLETED", "metrics": {}}
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"trials": [t]}), encoding="utf-8")
    with pytest.raises(TuningDataError):
        load_registry(p)


def test_space_frozen_20_points() -> None:
    space = json.loads((PROJECT_ROOT / "configs" / "tuning_space.json").read_text(encoding="utf-8"))
    assert validate_space(space)["b_trials"] == 20


def test_space_rejects_offgrid() -> None:
    with pytest.raises(TuningDataError):
        validate_space({"track_B_grid": [{"gamma": 0.5, "lambda": 0.0}] * 12})


def test_offgrid_trial_rejected(tmp_path: Path) -> None:
    t = _trial("rogue", 0.99, gamma=0.5)
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"trials": [t]}), encoding="utf-8")
    with pytest.raises(TuningDataError):
        load_registry(p)


def test_missing_grid_fields_rejected(tmp_path: Path) -> None:
    t = {"trial_id": "x", "track": "B", "config": {}, "status": "COMPLETED",
         "metrics": {"nDCG@10": 0.5}}
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"trials": [t]}), encoding="utf-8")
    with pytest.raises(TuningDataError):
        load_registry(p)
