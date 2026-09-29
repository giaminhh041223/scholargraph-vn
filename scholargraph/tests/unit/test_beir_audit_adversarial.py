"""SG-010 adversarial checks: all destructive inputs are synthetic temp files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scholargraph.ingest.beir_audit import audit_raw_qrels

PROJECT = Path(__file__).resolve().parents[2]
HEADER = "query-id\tcorpus-id\tscore\n"


def write_rows(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def synthetic_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic_raw"
    for dataset in ("scifact", "scidocs"):
        directory = root / dataset
        (directory / "qrels").mkdir(parents=True)
        write_rows(directory / "corpus.jsonl", [
            {"_id": "d1", "title": "Alpha paper", "text": "Body one", "synthetic": True},
            {"_id": "d2", "title": "Beta paper", "text": "Body two", "synthetic": True},
            {"_id": "qtest", "title": "Source paper", "text": "Self source", "synthetic": True},
        ])
        write_rows(directory / "queries.jsonl", [
            {"_id": "qtrain", "text": "Training claim", "synthetic": True},
            {"_id": "qtest", "text": "Held out claim", "synthetic": True},
            {"_id": "qzero", "text": "Unrelated claim", "synthetic": True},
        ])
        (directory / "qrels/test.tsv").write_text(HEADER + "qtest\td1\t1\nqzero\td2\t0\n", encoding="utf-8")
        if dataset == "scifact":
            (directory / "qrels/train.tsv").write_text(HEADER + "qtrain\td1\t1\n", encoding="utf-8")
    return root


def cli(root: Path, output: Path) -> tuple[subprocess.CompletedProcess, dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT / "src")
    process = subprocess.run(
        [sys.executable, "-m", "scholargraph.ingest.beir_audit", str(root), str(output)],
        cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert output.is_file(), f"CLI must persist diagnostic report: {process.stderr}"
    return process, json.loads(output.read_text(encoding="utf-8"))


MISSING = [
    ("scifact/corpus.jsonl", "corpus_audit", "total_documents"),
    ("scifact/queries.jsonl", "queries_audit", "total_queries"),
    ("scifact/qrels/train.tsv", "train", "total_rows"),
    ("scifact/qrels/test.tsv", "test", "total_rows"),
    ("scidocs/qrels/test.tsv", "test", "total_rows"),
]


@pytest.mark.parametrize("relative,component,total", MISSING)
def test_missing_required_resource_cli_fails_without_fake_measurements(tmp_path, relative, component, total):
    root = synthetic_snapshot(tmp_path)
    (root / relative).unlink()
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    assert report["errors"]
    dataset = report["datasets"][relative.split("/")[0]]
    part = dataset[component] if component.endswith("_audit") else dataset["splits_audit"][component]
    assert part["status"] == "FAIL"
    assert part["error"]
    assert part[total] is None, "A missing resource was not measured; zero is a false observation"
    if component in ("corpus_audit", "queries_audit"):
        for split in dataset["required_splits"]:
            dependent = dataset["splits_audit"][split]
            assert dependent["status"] == "FAIL"
            assert dependent["referential_integrity"] is None  # whole dependent measurement unavailable
    if relative.startswith("scifact/") and "corpus" not in relative:
        overlap = report["cross_split_checks"]["scifact_train_vs_test"]
        assert overlap["status"] == "FAIL"
        assert overlap["query_id_overlap_count"] is None
        assert overlap["query_text_exact_overlap_count"] is None
        assert report["anomalies_summary"]["scifact_train_test_query_leakage"]["query_id_overlap_count"] is None


@pytest.mark.parametrize("resource", ["corpus.jsonl", "queries.jsonl", "qrels/test.tsv"])
def test_malformed_resource_preserves_failure_not_zero_stats(tmp_path, resource):
    root = synthetic_snapshot(tmp_path)
    (root / "scifact" / resource).write_text("{not-valid-json\n" if resource.endswith("jsonl") else "bad\theader\n", encoding="utf-8")
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    data = report["datasets"]["scifact"]
    component, total = (data["corpus_audit"], "total_documents") if resource == "corpus.jsonl" else (
        (data["queries_audit"], "total_queries") if resource == "queries.jsonl" else (data["splits_audit"]["test"], "total_rows")
    )
    assert component["status"] == "FAIL"
    assert component["error"]
    assert component[total] is None


@pytest.mark.parametrize("resource,field,bad_value", [
    ("corpus.jsonl", "_id", None), ("corpus.jsonl", "_id", 17),
    ("corpus.jsonl", "_id", " d1"), ("corpus.jsonl", "_id", "d 1"),
    ("corpus.jsonl", "title", []), ("corpus.jsonl", "text", {"text": "hidden"}),
    ("corpus.jsonl", "title", 0), ("corpus.jsonl", "text", False),
    ("queries.jsonl", "_id", None), ("queries.jsonl", "_id", " qtest"),
    ("queries.jsonl", "text", None), ("queries.jsonl", "text", 123),
    ("queries.jsonl", "text", []), ("queries.jsonl", "text", "   "),
])
def test_bad_types_or_ids_fail_component_and_cli(tmp_path, resource, field, bad_value):
    root = synthetic_snapshot(tmp_path)
    path = root / "scidocs" / resource
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0][field] = bad_value
    write_rows(path, rows)
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    component = report["datasets"]["scidocs"]["corpus_audit" if resource == "corpus.jsonl" else "queries_audit"]
    assert component["status"] == "FAIL", "Raw audit must not coerce bad types and rely solely on loader failure"
    assert component["error"]


@pytest.mark.parametrize("row", [
    "qtest\td1\t-1\n", "qtest\td1\t3\n", "qtest\td1\t1.5\n", "qtest\td1\tnan\n",
    " qtest\td1\t1\n", "qtest\t d1\t1\n", "qtest\td1\t1\textra\n",
])
def test_malformed_qrels_fail_raw_split_and_cli(tmp_path, row):
    root = synthetic_snapshot(tmp_path)
    (root / "scidocs/qrels/test.tsv").write_text(HEADER + row, encoding="utf-8")
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    part = report["datasets"]["scidocs"]["splits_audit"]["test"]
    assert part["status"] == "FAIL"
    assert part["error"]
    assert part["total_rows"] is None


def test_positive_self_qrel_cannot_pass_cli_gate(tmp_path):
    root = synthetic_snapshot(tmp_path)
    (root / "scidocs/qrels/test.tsv").write_text(HEADER + "qtest\tqtest\t1\n", encoding="utf-8")
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    assert any("self" in error.lower() for error in report["errors"])


def test_query_id_leakage_across_splits_fails_cli(tmp_path):
    root = synthetic_snapshot(tmp_path)
    (root / "scifact/qrels/train.tsv").write_text(HEADER + "qtest\td1\t1\n", encoding="utf-8")
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    overlap = report["cross_split_checks"]["scifact_train_vs_test"]
    assert overlap["status"] == "FAIL"
    assert overlap["query_id_overlap_count"] == 1


def test_valid_title_only_text_only_and_shared_document_are_not_rejected(tmp_path):
    root = synthetic_snapshot(tmp_path)
    for dataset in ("scifact", "scidocs"):
        write_rows(root / dataset / "corpus.jsonl", [
            {"_id": "d1", "title": "Title only", "text": "", "synthetic": True},
            {"_id": "d2", "title": "", "text": "Text only", "synthetic": True},
            {"_id": "qtest", "title": "Full title", "text": "Full body", "synthetic": True},
        ])
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 0, process.stderr
    assert report["audit_passed"] is True
    for data in report["datasets"].values():
        missingness = data["corpus_audit"]["missingness"]
        assert missingness["empty_or_missing_title_count"] == 1
        assert missingness["empty_or_missing_text_count"] == 1
        assert missingness["empty_both_count"] == 0
    overlap = report["cross_split_checks"]["scifact_train_vs_test"]
    assert overlap["query_id_overlap_count"] == 0
    assert overlap["shared_relevant_documents_count"] == 1
    assert overlap["status"] == "PASS", "Using the same corpus document in two splits is not query leakage"


def test_zero_positive_queries_are_included_in_sparsity_distribution(tmp_path):
    qrels = tmp_path / "synthetic.tsv"
    qrels.write_text(HEADER + "qpositive\td1\t1\nqpositive\td2\t2\nqzero\td1\t0\n", encoding="utf-8")
    report = audit_raw_qrels(qrels, {"d1", "d2"}, {"qpositive", "qzero", "not_in_split"}, set())
    sparsity = report["relevance_sparsity"]
    assert sparsity["queries_with_zero_positive_count"] == 1
    assert sparsity["queries_with_zero_positive"] == ["qzero"]
    stats = sparsity["positives_per_query_stats"]
    assert stats["count"] == 2
    assert stats["min"] == 0
    assert stats["max"] == 2
    assert stats["mean"] == 1
    assert stats["median"] == 1
    assert stats["std"] == 1


@pytest.mark.parametrize("resource", ["corpus.jsonl", "queries.jsonl", "qrels/test.tsv"])
def test_empty_required_resource_cli_fails(tmp_path, resource):
    root = synthetic_snapshot(tmp_path)
    (root / "scidocs" / resource).write_text(HEADER if resource.endswith("tsv") else "", encoding="utf-8")
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    assert report["errors"]


def test_missing_entire_snapshot_reports_unmeasured_counts(tmp_path):
    root = tmp_path / "absent_synthetic_raw"
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    assert report["errors"]
    for data in report["datasets"].values():
        assert data["corpus_audit"]["status"] == "FAIL"
        assert data["corpus_audit"]["total_documents"] is None
        assert data["queries_audit"]["total_queries"] is None
    assert report["cross_split_checks"]["scifact_train_vs_test"]["query_id_overlap_count"] is None


def test_both_text_fields_missing_is_error_with_correct_mixed_counts(tmp_path):
    root = synthetic_snapshot(tmp_path)
    write_rows(root / "scidocs/corpus.jsonl", [
        {"_id": "d1", "title": "Title only", "text": "", "synthetic": True},
        {"_id": "d2", "title": "", "text": "Text only", "synthetic": True},
        {"_id": "qtest", "title": "", "text": "", "synthetic": True},
    ])
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    counts = report["datasets"]["scidocs"]["corpus_audit"]["missingness"]
    assert counts["empty_or_missing_title_count"] == 2
    assert counts["empty_or_missing_text_count"] == 2
    assert counts["empty_both_count"] == 1
    assert any("both" in error.lower() for error in report["errors"])
    explanation = report["anomalies_summary"]["scidocs_empty_abstract_documents"]["explanation"].lower()
    assert "title only" not in explanation or "1 document" in explanation


@pytest.mark.parametrize("row", [
    {"_id": "d1", "title": "Title without text key", "synthetic": True},
    {"_id": "d1", "text": "Text without title key", "synthetic": True},
])
def test_one_valid_text_field_can_be_present_without_other_key(tmp_path, row):
    root = synthetic_snapshot(tmp_path)
    write_rows(root / "scidocs/corpus.jsonl", [row, {"_id": "d2", "text": "Another body", "synthetic": True}])
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 0, process.stderr
    assert report["audit_passed"] is True


@pytest.mark.parametrize("row", [
    '{"_id":"d1","title":"valid","text":"ok","_id":"d2"}',
    '{"_id":"d1","title":"valid","text":"ok","metadata":{"year":NaN}}',
    '["d1","title","body"]',
])
def test_json_duplicate_fields_nonfinite_and_nonobject_rejected(tmp_path, row):
    root = synthetic_snapshot(tmp_path)
    (root / "scidocs/corpus.jsonl").write_text(row + "\n", encoding="utf-8")
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 1
    assert report["audit_passed"] is False
    assert report["datasets"]["scidocs"]["corpus_audit"]["total_documents"] is None


@pytest.mark.parametrize("text_field", [{}, {"text": None}, {"text": "   "}, {"text": ""}])
def test_title_only_narrative_does_not_invent_raw_empty_string(tmp_path, text_field):
    root = synthetic_snapshot(tmp_path)
    write_rows(root / "scidocs/corpus.jsonl", [
        {"_id": "d1", "title": "Title", "synthetic": True, **text_field},
        {"_id": "d2", "title": "Other", "text": "Body", "synthetic": True},
    ])
    process, report = cli(root, tmp_path / "report.json")
    assert process.returncode == 0
    narrative = report["anomalies_summary"]["scidocs_empty_abstract_documents"]["explanation"]
    assert "abstract/text is missing, null or blank" in narrative
    assert "is empty string" not in narrative


def test_output_cannot_overwrite_raw_corpus(tmp_path):
    root = synthetic_snapshot(tmp_path)
    output = root / "scidocs/corpus.jsonl"
    original = output.read_bytes()
    env = dict(os.environ, PYTHONPATH=str(PROJECT / "src"))
    process = subprocess.run(
        [sys.executable, "-m", "scholargraph.ingest.beir_audit", str(root), str(output)],
        env=env, capture_output=True, text=True, cwd=PROJECT, timeout=30,
    )
    assert process.returncode == 1
    assert "AUDIT FAILED" in process.stderr
    assert output.read_bytes() == original


def test_all_text_overlap_pairs_retained_and_report_deterministic(tmp_path):
    root = synthetic_snapshot(tmp_path)
    write_rows(root / "scifact/queries.jsonl", [
        {"_id": "qtrain", "text": "Shared wording", "synthetic": True},
        {"_id": "qtrain2", "text": "SHARED WORDING", "synthetic": True},
        {"_id": "qtest", "text": "Shared wording", "synthetic": True},
        {"_id": "qzero", "text": "Different", "synthetic": True},
    ])
    (root / "scifact/qrels/train.tsv").write_text(HEADER + "qtrain\td1\t1\nqtrain2\td2\t1\n", encoding="utf-8")
    p1, r1 = cli(root, tmp_path / "first.json")
    p2, r2 = cli(root, tmp_path / "second.json")
    assert p1.returncode == p2.returncode == 0
    overlap = r1["cross_split_checks"]["scifact_train_vs_test"]
    assert overlap["query_text_exact_overlap_count"] == 1  # distinct normalized texts
    assert len(overlap["query_text_exact_overlap_details"]) == 2  # every matching pair
    assert r1["input_integrity"]["unchanged_during_audit"] is True
    r1.pop("audit_timestamp")
    r2.pop("audit_timestamp")
    assert r1 == r2
