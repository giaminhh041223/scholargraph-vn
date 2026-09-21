"""SG-030 statistics — positive + adversarial tests (synthetic first)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.evaluation.statistics import (
    StatisticsError,
    ndcg_at_10,
    paired_bootstrap_ci,
)


def test_ci_excludes_zero_on_clear_delta():
    t = {f"q{i}": 0.8 for i in range(60)}
    c = {f"q{i}": 0.2 for i in range(60)}
    out = paired_bootstrap_ci(t, c, resamples=1000, seed=7)
    assert out["delta_absolute"] == pytest.approx(0.6)
    assert out["ci_excludes_zero"] is True
    assert out["ci_low"] > 0.0
    assert out["delta_relative"] == pytest.approx(3.0)


def test_ci_contains_zero_on_identical_runs():
    v = {f"q{i}": float(i % 3) / 2 for i in range(60)}
    out = paired_bootstrap_ci(v, dict(v), resamples=1000, seed=7)
    assert out["delta_absolute"] == pytest.approx(0.0)
    assert out["ci_excludes_zero"] is False
    assert out["ci_low"] <= 0.0 <= out["ci_high"]


def test_seed_reproducibility():
    t = {f"q{i}": (i * 0.37) % 1.0 for i in range(50)}
    c = {f"q{i}": (i * 0.11) % 1.0 for i in range(50)}
    a = paired_bootstrap_ci(t, c, resamples=1000, seed=20260915)
    b = paired_bootstrap_ci(t, c, resamples=1000, seed=20260915)
    assert a == b
    d = paired_bootstrap_ci(t, c, resamples=1000, seed=1)
    assert (a["ci_low"], a["ci_high"]) != (d["ci_low"], d["ci_high"])


def test_relative_delta_undefined_on_zero_control():
    t = {f"q{i}": 0.5 for i in range(30)}
    c = {f"q{i}": 0.0 for i in range(30)}
    out = paired_bootstrap_ci(t, c, resamples=500, seed=3)
    assert out["delta_relative"] is None  # undefined, never 0 or inf
    assert out["delta_absolute"] == pytest.approx(0.5)


def test_groups_respected_and_validated():
    t = {f"q{i}": 0.9 if i < 10 else 0.1 for i in range(20)}
    c = {f"q{i}": 0.1 for i in range(20)}
    groups = {f"q{i}": ("g1" if i < 10 else "g2") for i in range(20)}
    out = paired_bootstrap_ci(t, c, resamples=500, seed=5, groups=groups)
    assert out["n_groups"] == 2 and out["n_queries"] == 20
    bad = dict(groups)
    del bad["q0"]
    with pytest.raises(StatisticsError, match="groups missing"):
        paired_bootstrap_ci(t, c, resamples=500, seed=5, groups=bad)


def test_invalid_configs_fail_loudly():
    t = {"q1": 0.5, "q2": 0.6}
    c = {"q1": 0.4, "q2": 0.4}
    with pytest.raises(StatisticsError):
        paired_bootstrap_ci(t, c, resamples=50, seed=1)
    with pytest.raises(StatisticsError):
        paired_bootstrap_ci(t, c, resamples=500, seed=True)
    with pytest.raises(StatisticsError):
        paired_bootstrap_ci(t, c, resamples=500, seed=1, level=1.5)
    with pytest.raises(StatisticsError):
        paired_bootstrap_ci(t, {"q1": 0.4}, resamples=500, seed=1)
    with pytest.raises(StatisticsError):
        paired_bootstrap_ci({}, {}, resamples=500, seed=1)
    bad = dict(t)
    bad["q1"] = float("nan")
    with pytest.raises(StatisticsError, match="non-finite"):
        paired_bootstrap_ci(bad, c, resamples=500, seed=1)


def test_ndcg10_definitions():
    import math
    assert ndcg_at_10(["a", "b"], {"a": 1, "b": 1}) == pytest.approx(1.0)
    assert ndcg_at_10(["x", "a"], {"a": 2}) == pytest.approx(1.0 / math.log2(3))
    with pytest.raises(StatisticsError, match="without positives"):
        ndcg_at_10(["x"], {})


def test_live_statistics_consistent_with_registry():
    spath = ROOT / "artifacts" / "reports" / "statistics.json"
    if not spath.is_file():
        pytest.skip("Statistics not built yet in this checkout")
    s = json.loads(spath.read_text(encoding="utf-8"))
    reg = json.loads((ROOT / "artifacts" / "reports" / "main_run_registry.json").read_text(encoding="utf-8"))
    assert s["freeze_sha256"] == reg["freeze_sha256"]
    assert s["protocol"] == {"resamples": 10000, "seed": 20260915, "level": 0.95,
                             "paired": True, "unit": "query_group", "p_values": False}
    assert len(s["comparisons"]) == 8 * 3
    assert s["n_packets"] == 24
    for r in s["comparisons"]:
        assert r["n_queries"] in (300, 1000, 200)
        assert r["ci_low"] <= r["ci_high"]
        assert isinstance(r["ci_excludes_zero"], bool)
        assert (r["ci_low"] > 0.0 or r["ci_high"] < 0.0) == r["ci_excludes_zero"]
