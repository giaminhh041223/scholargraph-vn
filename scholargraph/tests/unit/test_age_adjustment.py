"""SG-024 age adjustment tests: formula + policy + CLI."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.graph.age_adjustment import (
    AgeDataError,
    age_weight,
    apply_age,
    exposure_at_10,
    exposure_by_gap,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)


def test_formula_hand_computed() -> None:
    assert age_weight(2025, 2020, 0.05) == pytest.approx(math.exp(-0.25))
    assert age_weight(2025, 2025, 0.1) == pytest.approx(1.0)
    assert age_weight(2020, 2025, 0.1) == pytest.approx(1.0)  # future: no penalty
    assert age_weight(2025, 2000, 0.0) == pytest.approx(1.0)  # lambda 0 = control


def test_lambda_grid_enforced() -> None:
    with pytest.raises(AgeDataError):
        age_weight(2025, 2020, 0.02)
    with pytest.raises(AgeDataError):
        age_weight(2025, 2020, float("inf"))


def test_missing_year_never_imputed() -> None:
    with pytest.raises(AgeDataError):
        apply_age([{"doc_id": "d", "fused": 1.0}], {"d": None}, 2025, 0.05)
    with pytest.raises(AgeDataError):
        apply_age([{"doc_id": "d", "fused": 1.0}], {}, 2025, 0.05)


def test_year_range_and_types() -> None:
    for bad in (True, "2020", 1899, 2101, None):
        with pytest.raises(AgeDataError):
            age_weight(2025, bad, 0.05)  # type: ignore[arg-type]


def test_apply_resorts_and_reports() -> None:
    rows = apply_age([{"doc_id": "old", "fused": 1.0}, {"doc_id": "new", "fused": 0.9}],
                     {"old": 2000, "new": 2025}, 2025, 0.1)
    assert rows[0]["doc_id"] == "new"  # freshness flips the order here
    assert rows[0]["age_weight"] == pytest.approx(1.0)
    assert rows[1]["age_gap"] == 25


def test_nonfinite_fused_fails() -> None:
    with pytest.raises(AgeDataError):
        apply_age([{"doc_id": "d", "fused": float("nan")}], {"d": 2020}, 2025, 0.05)


def test_exposure_descriptive() -> None:
    rows = [{"doc_id": "a", "fused_age": 3.0, "age_gap": 1},
            {"doc_id": "b", "fused_age": 1.0, "age_gap": 20}]
    e = exposure_by_gap(rows, 2)
    assert e["mass_shares"]["0-2y"] == pytest.approx(0.75)
    assert e["mass_shares"][">10y"] == pytest.approx(0.25)


def test_exposure_at_10_protocol63() -> None:
    import math
    e = exposure_at_10(["a", "b"], {"a": 1, "b": 20})
    d1, d2 = 1 / math.log2(2), 1 / math.log2(3)
    assert e["exposure"]["0-2y"] == pytest.approx(d1 / (d1 + d2))
    assert e["exposure"][">=11y"] == pytest.approx(d2 / (d1 + d2))
    assert e["results"] == 2
    assert exposure_at_10([], {})["exposure"]["0-2y"] == 0.0
    with pytest.raises(AgeDataError):
        exposure_at_10(["ghost"], {"a": 1})


def test_empty_fused_and_duplicates_fail() -> None:
    with pytest.raises(AgeDataError):
        apply_age([], {"a": 2020}, 2025, 0.05)
    with pytest.raises(AgeDataError):
        apply_age([{"doc_id": "a", "fused": 1.0}, {"doc_id": "a", "fused": 0.5}],
                  {"a": 2020}, 2025, 0.05)
    with pytest.raises(AgeDataError):
        exposure_by_gap([], 10)
    with pytest.raises(AgeDataError):
        exposure_by_gap([{"doc_id": "a", "fused_age": 1.0, "age_gap": 1}], 0)


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH="src")
    return subprocess.run([str(PYTHON), "-m", "scholargraph.graph.age_adjustment", *args],
                          capture_output=True, text=True, cwd=PROJECT_ROOT, env=env)


def test_cli_grid_synthetic(tmp_path: Path) -> None:
    fused = tmp_path / "f.json"
    fused.write_text(json.dumps({"q1": [{"doc_id": "a", "fused": 1.0}, {"doc_id": "b", "fused": 0.8}]}), encoding="utf-8")
    (tmp_path / "y.json").write_text(json.dumps({"a": 2020, "b": 2025}), encoding="utf-8")
    (tmp_path / "qy.json").write_text(json.dumps({"q1": 2025}), encoding="utf-8")
    out = tmp_path / "o.json"
    r = _run_cli(["--fused", str(fused), "--years", str(tmp_path / "y.json"),
                  "--query-years", str(tmp_path / "qy.json"), "--output", str(out)])
    assert r.returncode == 0, r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert set(d["per_lambda"]) == {"0.0", "0.01", "0.03", "0.05", "0.1"}
    # lambda 0 keeps order; large lambda favors the new doc
    assert d["per_lambda"]["0.1"]["mean_top10_mass_shares"]["0-2y"] >= d["per_lambda"]["0.0"]["mean_top10_mass_shares"]["0-2y"]


def test_cli_missing_year_exit_1(tmp_path: Path) -> None:
    fused = tmp_path / "f.json"
    fused.write_text(json.dumps({"q1": [{"doc_id": "a", "fused": 1.0}]}), encoding="utf-8")
    (tmp_path / "y.json").write_text(json.dumps({"a": None}), encoding="utf-8")
    (tmp_path / "qy.json").write_text(json.dumps({"q1": 2025}), encoding="utf-8")
    r = _run_cli(["--fused", str(fused), "--years", str(tmp_path / "y.json"),
                  "--query-years", str(tmp_path / "qy.json"), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_missing_file_exit_1(tmp_path: Path) -> None:
    r = _run_cli(["--fused", str(tmp_path / "nope"), "--years", str(tmp_path / "y.json"),
                  "--query-years", str(tmp_path / "qy.json"), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1


def test_cli_query_mismatch_exit_1(tmp_path: Path) -> None:
    fused = tmp_path / "f.json"
    fused.write_text(json.dumps({"q1": [{"doc_id": "a", "fused": 1.0}]}), encoding="utf-8")
    (tmp_path / "y.json").write_text(json.dumps({"a": 2020}), encoding="utf-8")
    (tmp_path / "qy.json").write_text(json.dumps({"q2": 2025}), encoding="utf-8")
    r = _run_cli(["--fused", str(fused), "--years", str(tmp_path / "y.json"),
                  "--query-years", str(tmp_path / "qy.json"), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_malformed_json_exit_1(tmp_path: Path) -> None:
    fused = tmp_path / "f.json"
    fused.write_text("{oops", encoding="utf-8")
    (tmp_path / "y.json").write_text(json.dumps({"a": 2020}), encoding="utf-8")
    (tmp_path / "qy.json").write_text(json.dumps({"q1": 2025}), encoding="utf-8")
    r = _run_cli(["--fused", str(fused), "--years", str(tmp_path / "y.json"),
                  "--query-years", str(tmp_path / "qy.json"), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
