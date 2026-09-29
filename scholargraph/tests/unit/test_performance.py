"""SG-040 performance helpers — positive + adversarial tests (synthetic first)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.evaluation.performance import (
    PerformanceError,
    hardware_context,
    peak_rss_bytes,
    percentile,
    summarize_timings,
    time_call,
)


def test_percentile_linear_known_values():
    assert percentile([0.0, 10.0], 50.0) == pytest.approx(5.0)
    assert percentile([1.0, 2.0, 3.0, 4.0], 95.0) == pytest.approx(3.85)
    assert percentile([7.0], 95.0) == pytest.approx(7.0)


def test_percentile_rejects_bad_input():
    with pytest.raises(PerformanceError):
        percentile([], 50.0)
    with pytest.raises(PerformanceError):
        percentile([1.0, 2.0], 101.0)
    with pytest.raises(PerformanceError):
        percentile([1.0, float("nan")], 50.0)


def test_summarize_timings_values_and_rejections():
    s = summarize_timings([0.1, 0.2, 0.3, 0.4])
    assert s["n"] == 4
    assert s["mean_s"] == pytest.approx(0.25)
    assert s["min_s"] == pytest.approx(0.1) and s["max_s"] == pytest.approx(0.4)
    assert s["p50_s"] == pytest.approx(0.25)
    with pytest.raises(PerformanceError):
        summarize_timings([])
    with pytest.raises(PerformanceError):
        summarize_timings([0.1, -0.2])


def test_peak_rss_honest_shape():
    rss = peak_rss_bytes()
    assert rss is None or (isinstance(rss, int) and rss > 0)


def test_hardware_context_keys():
    hw = hardware_context()
    assert hw["cpu_count"] and hw["python"]
    assert hw["gpu_measured_here"] is False


def test_time_call_repeat_validation():
    _, samples = time_call(lambda: 1, repeat=3)
    assert len(samples) == 3 and all(v >= 0 for v in samples)
    with pytest.raises(PerformanceError):
        time_call(lambda: 1, repeat=0)


def test_live_performance_report_consistent():
    ppath = ROOT / "artifacts" / "reports" / "performance.json"
    if not ppath.is_file():
        pytest.skip("Performance report not built yet in this checkout")
    p = json.loads(ppath.read_text(encoding="utf-8"))
    from scholargraph.evaluation.sealed import _sha_file
    assert p["freeze_sha256"] == _sha_file(ROOT / "configs" / "frozen_main.json")
    assert p["query_budget_s"] == 0.5
    assert p["peak_rss_bytes_cold_worker"] is None or p["peak_rss_bytes_cold_worker"] > 0
    for dataset in ("scifact", "scidocs"):
        m = p["perf_warm"]["methods"][dataset]
        for key in ("bm25_search_per_query", "dense_search_per_query", "hybrid_full_per_query_s"):
            assert m[key]["n"] in (20, 10)
            assert m[key]["p50_s"] <= m[key]["p95_s"]
    # Workload IDs must be the head of the locked test splits (no cherry-picking).
    for dataset in ("scifact", "scidocs"):
        split_def = json.loads((ROOT / "data" / "splits" / f"{dataset}_test.json").read_text(encoding="utf-8"))
        n = p["perf_warm"]["workload"][dataset]["n_queries"]
        assert p["perf_warm"]["workload"][dataset]["query_ids"] == list(split_def["query_ids"])[:n]
