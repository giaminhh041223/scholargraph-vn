from __future__ import annotations

import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "compute_smoke.ipynb"
REPORT_PATH = PROJECT_ROOT / "artifacts" / "reports" / "compute_pilot.json"


def test_compute_notebook_is_a_plain_python_sg002_pilot() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))

    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["scholargraph"]["task_id"] == "SG-002"
    assert notebook["metadata"]["scholargraph"]["synthetic_fallback"] is True

    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    assert "N_DOCS = 1000" in code
    assert "GPU throughput and peak VRAM remain unverified" in code
    assert not any(line.lstrip().startswith(("%", "!")) for line in code.splitlines())


def test_compute_report_is_consistent_and_device_metrics_are_truthful() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    measurement = report["measurement"]

    assert report["task_id"] == "SG-002"
    assert report["input"]["documents"] == 1000
    assert report["input"]["synthetic"] is True
    assert measurement["documents_per_second"] > 0
    assert measurement["embedding_shape"][0] == 1000
    assert measurement["embedding_dtype"] == "float32"
    assert math.isclose(
        measurement["documents_per_second"],
        report["input"]["documents"] / measurement["encode_seconds"],
        rel_tol=1e-12,
    )

    if report["environment"]["device"] == "cpu":
        assert report["status"] == "completed_local_cpu_gpu_pending"
        assert report["cloud_gpu"]["status"] == "not_run"
        assert measurement["gpu_peak_allocated_bytes"] is None
        assert measurement["gpu_peak_reserved_bytes"] is None
    else:
        assert report["environment"]["device"] == "cuda"
        assert report["environment"]["cuda_available"] is True
        assert report["environment"]["gpu_name"]
        assert report["environment"]["gpu_total_memory_bytes"] > 0
        assert report["status"] == "completed_gpu"
        assert report["cloud_gpu"]["status"] == "measured_in_this_run"
        assert measurement["gpu_peak_allocated_bytes"] > 0
        assert measurement["gpu_peak_reserved_bytes"] >= measurement["gpu_peak_allocated_bytes"]


def test_preserved_cpu_baseline_remains_distinct_from_gpu_result() -> None:
    cpu_report_path = REPORT_PATH.with_name("compute_pilot.local_cpu.json")
    cpu_report = json.loads(cpu_report_path.read_text(encoding="utf-8"))
    gpu_report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    assert cpu_report["environment"]["device"] == "cpu"
    assert cpu_report["status"] == "completed_local_cpu_gpu_pending"
    assert gpu_report["environment"]["device"] == "cuda"
    assert gpu_report["status"] == "completed_gpu"
    assert cpu_report["input"]["sha256"] == gpu_report["input"]["sha256"]
    assert cpu_report["model"]["resolved_revision"] == gpu_report["model"]["resolved_revision"]


def test_report_estimates_apply_the_documented_overhead() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    rate = report["measurement"]["documents_per_second"]

    for count in (10_000, 20_000, 50_000):
        estimate = report["estimates_from_this_run"][f"{count}_documents"]
        assert math.isclose(estimate["seconds_raw"], count / rate, rel_tol=1e-12)
        assert math.isclose(
            estimate["seconds_with_25pct_overhead"],
            count / rate * 1.25,
            rel_tol=1e-12,
        )
