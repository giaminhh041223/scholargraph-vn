"""Unit and adversarial/destructive tests for scripts/run_vn_eval.py (SG-034).

All tests operate exclusively inside tmp_path and never touch PROJECT_ROOT
annotations or configs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_vn_eval.py"


def _write_synthetic_vn_fixture(
    tmp_path: Path,
    *,
    null_dev_label: bool = False,
    unadjudicated_conflict: bool = False,
    leak_provenance: bool = False,
) -> dict[str, Path]:
    pool_path = tmp_path / "vn_pool.json"
    labels_path = tmp_path / "vn_labels.jsonl"
    methods_path = tmp_path / "vn_methods.json"
    rankings_path = tmp_path / "rankings.json"
    frozen_path = tmp_path / "frozen_vn.json"
    report_dir = tmp_path / "reports"

    pool_doc = {
        "schema_version": 1,
        "pools": [
            {
                "query_id": "vn:dev:001",
                "split": "dev",
                "intent_family": "cardio",
                "text_vi": "aspirin tim mach",
                "text_en": "aspirin cardiovascular",
                "pool_size": 2,
                "candidates": [
                    {"position": 1, "doc_id": "openalex:W1", "title": "Doc 1", "year": 2020},
                    {"position": 2, "doc_id": "openalex:W2", "title": "Doc 2", "year": 2021},
                ],
            },
            {
                "query_id": "vn:test:001",
                "split": "test",
                "intent_family": "neuro",
                "text_vi": "giac ngu nao bo",
                "text_en": "sleep brain",
                "pool_size": 2,
                "candidates": [
                    {"position": 1, "doc_id": "openalex:W3", "title": "Doc 3", "year": 2022},
                    {"position": 2, "doc_id": "openalex:W4", "title": "Doc 4", "year": 2023},
                ],
            },
        ],
    }
    pool_path.write_text(json.dumps(pool_doc), encoding="utf-8")

    methods_doc = {
        "schema_version": 1,
        "multilingual_dense": {"decision": {"pinned_model_id": "intfloat/multilingual-e5-base"}},
        "translation": {"model_id": "Helsinki-NLP/opus-mt-vi-en"},
    }
    methods_path.write_text(json.dumps(methods_doc), encoding="utf-8")

    rows = [
        {"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": None if null_dev_label else 2, "annotator": "A", "round": "independent"},
        {"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": 1 if unadjudicated_conflict else 2, "annotator": "B", "round": "independent"},
        {"query_id": "vn:dev:001", "doc_id": "openalex:W2", "label": 0, "annotator": "A", "round": "independent"},
        {"query_id": "vn:dev:001", "doc_id": "openalex:W2", "label": 0, "annotator": "B", "round": "independent"},
        {"query_id": "vn:test:001", "doc_id": "openalex:W3", "label": 2, "annotator": "A", "round": "independent"},
        {"query_id": "vn:test:001", "doc_id": "openalex:W3", "label": 2, "annotator": "B", "round": "independent"},
        {"query_id": "vn:test:001", "doc_id": "openalex:W4", "label": 0, "annotator": "A", "round": "independent"},
        {"query_id": "vn:test:001", "doc_id": "openalex:W4", "label": 0, "annotator": "B", "round": "independent"},
    ]
    if leak_provenance:
        rows[0]["system"] = "multilingual_dense"
    labels_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    rankings_doc = {
        "translated_bm25": {
            "vn:dev:001": ["openalex:W2", "openalex:W1"],
            "vn:test:001": ["openalex:W4", "openalex:W3"],
        },
        "multilingual_dense": {
            "vn:dev:001": ["openalex:W1", "openalex:W2"],
            "vn:test:001": ["openalex:W3", "openalex:W4"],
        },
        "vn_hybrid_rrf": {
            "vn:dev:001": ["openalex:W1", "openalex:W2"],
            "vn:test:001": ["openalex:W3", "openalex:W4"],
        },
        "original_vi_bm25": {
            "vn:dev:001": ["openalex:W2"],
            "vn:test:001": ["openalex:W4"],
        },
    }
    rankings_path.write_text(json.dumps(rankings_doc), encoding="utf-8")

    return {
        "pool": pool_path,
        "labels": labels_path,
        "methods": methods_path,
        "rankings": rankings_path,
        "frozen": frozen_path,
        "report_dir": report_dir,
    }


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_vn_eval_freeze_dev_and_eval_test_happy_path(tmp_path: Path) -> None:
    fx = _write_synthetic_vn_fixture(tmp_path)

    # 1. freeze-dev selects multilingual_dense (tie with vn_hybrid_rrf broken lexicographically)
    res_dev = _run_cli(
        [
            "--phase", "freeze-dev",
            "--labels", str(fx["labels"]),
            "--pool", str(fx["pool"]),
            "--methods-config", str(fx["methods"]),
            "--frozen-out", str(fx["frozen"]),
            "--rankings-json", str(fx["rankings"]),
        ]
    )
    assert res_dev.returncode == 0, res_dev.stderr
    frozen = json.loads(fx["frozen"].read_text(encoding="utf-8"))
    assert frozen["selected_default_method"] == "multilingual_dense"
    assert frozen["human_approved"] is False

    # 2. eval-test MUST fail with exit 1 while human_approved is False
    res_unapproved = _run_cli(
        [
            "--phase", "eval-test",
            "--labels", str(fx["labels"]),
            "--pool", str(fx["pool"]),
            "--methods-config", str(fx["methods"]),
            "--frozen-out", str(fx["frozen"]),
            "--report-dir", str(fx["report_dir"]),
            "--rankings-json", str(fx["rankings"]),
        ]
    )
    assert res_unapproved.returncode == 1
    assert "human_approved=true" in res_unapproved.stderr

    # 3. Simulate human owner approval and run eval-test
    frozen["human_approved"] = True
    fx["frozen"].write_text(json.dumps(frozen), encoding="utf-8")
    res_test = _run_cli(
        [
            "--phase", "eval-test",
            "--labels", str(fx["labels"]),
            "--pool", str(fx["pool"]),
            "--methods-config", str(fx["methods"]),
            "--frozen-out", str(fx["frozen"]),
            "--report-dir", str(fx["report_dir"]),
            "--rankings-json", str(fx["rankings"]),
        ]
    )
    assert res_test.returncode == 0, res_test.stderr
    vn_json = json.loads((fx["report_dir"] / "vn_results.json").read_text(encoding="utf-8"))
    assert vn_json["selected_default_method"] == "multilingual_dense"
    assert vn_json["methods"]["multilingual_dense"]["aggregate"]["nDCG@10"] == 1.0
    assert (fx["report_dir"] / "vn_results.md").is_file()


def test_vn_eval_rejects_null_labels_exit_1(tmp_path: Path) -> None:
    fx = _write_synthetic_vn_fixture(tmp_path, null_dev_label=True)
    res = _run_cli(
        [
            "--phase", "freeze-dev",
            "--labels", str(fx["labels"]),
            "--pool", str(fx["pool"]),
            "--methods-config", str(fx["methods"]),
            "--frozen-out", str(fx["frozen"]),
            "--rankings-json", str(fx["rankings"]),
        ]
    )
    assert res.returncode == 1
    assert "null label" in res.stderr


def test_vn_eval_rejects_unadjudicated_conflict_exit_1(tmp_path: Path) -> None:
    fx = _write_synthetic_vn_fixture(tmp_path, unadjudicated_conflict=True)
    res = _run_cli(
        [
            "--phase", "freeze-dev",
            "--labels", str(fx["labels"]),
            "--pool", str(fx["pool"]),
            "--methods-config", str(fx["methods"]),
            "--frozen-out", str(fx["frozen"]),
            "--rankings-json", str(fx["rankings"]),
        ]
    )
    assert res.returncode == 1
    assert "without an adjudicated row" in res.stderr


def test_vn_eval_rejects_provenance_leak_exit_1(tmp_path: Path) -> None:
    fx = _write_synthetic_vn_fixture(tmp_path, leak_provenance=True)
    res = _run_cli(
        [
            "--phase", "freeze-dev",
            "--labels", str(fx["labels"]),
            "--pool", str(fx["pool"]),
            "--methods-config", str(fx["methods"]),
            "--frozen-out", str(fx["frozen"]),
            "--rankings-json", str(fx["rankings"]),
        ]
    )
    assert res.returncode == 1
    assert "leaks system provenance" in res.stderr


def test_vn_eval_missing_input_exits_1(tmp_path: Path) -> None:
    res = _run_cli(
        [
            "--phase", "freeze-dev",
            "--labels", str(tmp_path / "nonexistent.jsonl"),
            "--pool", str(tmp_path / "nonexistent_pool.json"),
        ]
    )
    assert res.returncode == 1
    assert "Missing required input file" in res.stderr
