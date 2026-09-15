"""Unit tests for BEIR dataset integrity, quality auditor and Data Card consistency (SG-010).

Covers:
1. Unit tests for auditor functions (tokenize_text, compute_distribution_stats).
2. Negative unit tests on synthetic corrupted fixtures (duplicate IDs, orphan qrels,
   conflicting scores, missing text, split query ID collisions, failing gates).
3. Active live execution of run_full_beir_audit on real BEIR raw data.
4. Consistency tests between docs/DATA_CARD.md, manifests and live audit results.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

from scholargraph.ingest.beir_audit import (
    audit_raw_corpus,
    audit_raw_qrels,
    audit_raw_queries,
    audit_scifact_train_test_overlap,
    compute_distribution_stats,
    run_full_beir_audit,
    tokenize_text,
)
from scholargraph.ingest.beir_loader import (
    BeirDataError,
    BeirLoader,
    canonical_beir_id,
    raw_beir_id,
    sha256_file,
)

RAW_BEIR_DIR = Path("data/raw/beir")
MANIFEST_DIR = Path("data/manifests")
REPORT_PATH = Path("artifacts/reports/beir_data_audit.json")
DATA_CARD_PATH = Path("docs/DATA_CARD.md")


# ============================================================================
# 1. Pure Unit Tests
# ============================================================================


def test_tokenizer_protocol_compliance() -> None:
    r"""Test standard tokenizer complies with Protocol v1 (?u)\b\w+\b and casefold."""
    text = "Machine Learning in COVID-19: A Systematic Review (2020)!"
    tokens = tokenize_text(text)
    assert tokens == [
        "machine",
        "learning",
        "in",
        "covid",
        "19",
        "a",
        "systematic",
        "review",
        "2020",
    ]
    assert tokenize_text("") == []


def test_compute_distribution_stats() -> None:
    """Verify summary statistics calculations including percentiles."""
    stats = compute_distribution_stats([10, 20, 30, 40, 50])
    assert stats["count"] == 5
    assert stats["min"] == 10.0
    assert stats["max"] == 50.0
    assert stats["mean"] == 30.0
    assert stats["median"] == 30.0
    assert stats["p25"] == 20.0
    assert stats["p75"] == 40.0

    empty_stats = compute_distribution_stats([])
    assert empty_stats["count"] == 0
    assert empty_stats["mean"] == 0.0


def test_canonical_id_roundtrip() -> None:
    """Ensure canonical ID prefixing and raw ID recovery are strictly lossless."""
    datasets = ["scifact", "scidocs"]
    sample_ids = ["doc1", "paper-12345", "001ffbeb63dfa6d52e9379dae46e68aea2d9407e", "q_999"]

    for d in datasets:
        for sid in sample_ids:
            cid = canonical_beir_id(d, sid)
            assert cid == f"beir:{d}:{sid}"
            recovered = raw_beir_id(d, cid)
            assert recovered == sid

    with pytest.raises(BeirDataError):
        raw_beir_id("scifact", "beir:scidocs:12345")


# ============================================================================
# 2. Negative Tests on Synthetic Corrupted Fixtures
# ============================================================================


def test_auditor_detects_duplicate_corpus_id(tmp_path: Path) -> None:
    """Negative test: Auditor must flag duplicate raw document IDs in corpus.jsonl."""
    corpus_file = tmp_path / "corpus.jsonl"
    corpus_file.write_text(
        json.dumps({"_id": "doc1", "title": "Title 1", "text": "Text 1"}) + "\n"
        + json.dumps({"_id": "doc1", "title": "Title 1 duplicate", "text": "Text 2"}) + "\n"
        + json.dumps({"_id": "doc2", "title": "Title 2", "text": "Text 3"}) + "\n",
        encoding="utf-8",
    )
    result = audit_raw_corpus(corpus_file, "synthetic")
    assert result["total_documents"] == 3
    assert result["unique_raw_ids"] == 2
    assert result["duplicate_raw_ids_count"] == 1
    assert "doc1" in result["duplicate_raw_ids"]


def test_auditor_detects_missing_both_title_and_text(tmp_path: Path) -> None:
    """Negative test: Auditor must flag documents with neither title nor text."""
    corpus_file = tmp_path / "corpus.jsonl"
    corpus_file.write_text(
        json.dumps({"_id": "doc1", "title": "", "text": "   "}) + "\n"
        + json.dumps({"_id": "doc2", "title": "Title 2", "text": ""}) + "\n",
        encoding="utf-8",
    )
    result = audit_raw_corpus(corpus_file, "synthetic")
    assert result["missingness"]["empty_both_count"] == 1
    assert result["missingness"]["empty_or_missing_text_count"] == 2


def test_auditor_detects_orphan_and_conflicting_qrels(tmp_path: Path) -> None:
    """Negative test: Auditor must catch orphan IDs, duplicate pairs, and conflicting scores."""
    qrels_file = tmp_path / "test.tsv"
    qrels_file.write_text(
        "query-id\tcorpus-id\tscore\n"
        "q1\tdoc1\t1\n"
        "q1\tdoc1\t0\n"  # conflicting duplicate pair
        "q_unknown\tdoc1\t1\n"  # orphan query
        "q1\tdoc_unknown\t1\n",  # orphan document
        encoding="utf-8",
    )
    corpus_ids = {"doc1"}
    query_ids = {"q1"}
    empty_text_ids = set()

    result = audit_raw_qrels(qrels_file, corpus_ids, query_ids, empty_text_ids)
    ref = result["referential_integrity"]
    assert ref["orphan_query_ids_count"] == 1
    assert "q_unknown" in ref["orphan_query_ids"]
    assert ref["orphan_corpus_ids_count"] == 1
    assert "doc_unknown" in ref["orphan_corpus_ids"]
    assert ref["duplicate_pairs_count"] == 1
    assert ref["conflicting_scores_count"] == 1


def test_auditor_fails_gate_on_corrupted_dataset(tmp_path: Path) -> None:
    """Negative test: run_full_beir_audit must set audit_passed=False when data has errors."""
    synth_root = tmp_path / "raw"
    synth_scifact = synth_root / "scifact"
    synth_scidocs = synth_root / "scidocs"
    synth_scifact.mkdir(parents=True)
    synth_scidocs.mkdir(parents=True)
    (synth_scifact / "qrels").mkdir()
    (synth_scidocs / "qrels").mkdir()

    # Corrupted SciFact: duplicate corpus ID + orphan qrel
    (synth_scifact / "corpus.jsonl").write_text(
        json.dumps({"_id": "d1", "title": "T1", "text": "B1"}) + "\n"
        + json.dumps({"_id": "d1", "title": "T1 dup", "text": "B2"}) + "\n",
        encoding="utf-8",
    )
    (synth_scifact / "queries.jsonl").write_text(
        json.dumps({"_id": "q1", "text": "Q1"}) + "\n",
        encoding="utf-8",
    )
    (synth_scifact / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq1\td_missing\t1\n",
        encoding="utf-8",
    )
    (synth_scifact / "qrels" / "train.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq1\td1\t1\n",
        encoding="utf-8",
    )

    # Valid minimal SCIDOCS
    (synth_scidocs / "corpus.jsonl").write_text(
        json.dumps({"_id": "sd1", "title": "ST1", "text": "SB1"}) + "\n",
        encoding="utf-8",
    )
    (synth_scidocs / "queries.jsonl").write_text(
        json.dumps({"_id": "sq1", "text": "SQ1"}) + "\n",
        encoding="utf-8",
    )
    (synth_scidocs / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nsq1\tsd1\t1\n",
        encoding="utf-8",
    )

    report_out = tmp_path / "audit_output.json"
    report = run_full_beir_audit(synth_root, report_out)

    assert report["audit_passed"] is False
    assert len(report["errors"]) >= 2
    assert report["anomalies_summary"]["referential_integrity_status"].startswith("FAIL:")
    assert report["protocol_compliance"]["all_integrity_checks_passed"] is False


def test_auditor_detects_cross_split_id_overlap(tmp_path: Path) -> None:
    """Negative test: scifact train-test overlap must report FAIL if query IDs collide."""
    scifact_dir = tmp_path / "scifact"
    scifact_dir.mkdir(parents=True)
    (scifact_dir / "qrels").mkdir()

    (scifact_dir / "queries.jsonl").write_text(
        json.dumps({"_id": "q1", "text": "Query 1"}) + "\n"
        + json.dumps({"_id": "q2", "text": "Query 2"}) + "\n",
        encoding="utf-8",
    )
    # q1 appears in both train and test!
    (scifact_dir / "qrels" / "train.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq1\td1\t1\n",
        encoding="utf-8",
    )
    (scifact_dir / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq1\td1\t1\n",
        encoding="utf-8",
    )

    overlap = audit_scifact_train_test_overlap(tmp_path)
    assert overlap["status"] == "FAIL"
    assert overlap["query_id_overlap_count"] == 1
    assert "FAIL:" in overlap["verdict"]


# ============================================================================
# 3. Live Active Execution on Real BEIR Benchmark Data
# ============================================================================


@pytest.fixture(scope="module")
def live_real_audit(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Actively run the full auditor on actual frozen BEIR data to a fresh temporary path."""
    tmp_out = tmp_path_factory.mktemp("live_audit") / "beir_data_audit.json"
    return run_full_beir_audit(RAW_BEIR_DIR, tmp_out)


def test_live_audit_gate_passed(live_real_audit: dict) -> None:
    """Verify live audit on real snapshot passes all integrity gates with zero errors."""
    assert live_real_audit["audit_passed"] is True
    assert live_real_audit["errors"] == []
    assert live_real_audit["protocol_compliance"]["all_integrity_checks_passed"] is True
    assert "100% PASS" in live_real_audit["anomalies_summary"]["referential_integrity_status"]


def test_scifact_live_corpus_and_qrels(live_real_audit: dict) -> None:
    """Verify live SciFact counts and referential integrity."""
    scifact = live_real_audit["datasets"]["scifact"]
    c_audit = scifact["corpus_audit"]
    assert c_audit["total_documents"] == 5183
    assert c_audit["unique_raw_ids"] == 5183
    assert c_audit["duplicate_raw_ids_count"] == 0
    assert c_audit["missingness"]["empty_or_missing_text_count"] == 0

    splits = scifact["splits_audit"]
    assert splits["train"]["total_rows"] == 919
    assert splits["train"]["unique_queries_in_qrels"] == 809
    assert splits["train"]["score_distribution"] == {"1": 919}

    assert splits["test"]["total_rows"] == 339
    assert splits["test"]["unique_queries_in_qrels"] == 300
    assert splits["test"]["score_distribution"] == {"1": 339}

    # Cross-split check: Disjoint ID namespace, exactly 2 upstream text duplicates
    overlap = live_real_audit["cross_split_checks"]["scifact_train_vs_test"]
    assert overlap["status"] == "PASS"
    assert overlap["query_id_overlap_count"] == 0
    assert overlap["query_text_exact_overlap_count"] == 2
    assert len(overlap["query_text_exact_overlap_details"]) == 2


def test_scidocs_live_corpus_and_empty_text_anomaly(live_real_audit: dict) -> None:
    """Verify live SCIDOCS counts, exactly 344 empty-abstract docs, and qrel impact."""
    scidocs = live_real_audit["datasets"]["scidocs"]
    c_audit = scidocs["corpus_audit"]
    assert c_audit["total_documents"] == 25657
    assert c_audit["unique_raw_ids"] == 25657
    assert c_audit["duplicate_raw_ids_count"] == 0
    assert c_audit["missingness"]["empty_or_missing_text_count"] == 344
    assert c_audit["missingness"]["empty_both_count"] == 0

    splits = scidocs["splits_audit"]
    assert splits["test"]["total_rows"] == 29928
    assert splits["test"]["unique_queries_in_qrels"] == 1000
    assert splits["test"]["score_distribution"] == {"0": 25000, "1": 4928}

    impact = splits["test"]["empty_text_docs_impact"]
    assert impact["empty_text_docs_in_qrels_count"] == 344
    assert impact["empty_text_docs_positive_count"] == 115


# ============================================================================
# 4. Manifest and Data Card Consistency Tests (Regression Guards)
# ============================================================================


def test_manifest_hashes_match_raw_disk_files() -> None:
    """Ensure SHA-256 hashes in data/manifests exactly match disk files."""
    scifact_manifest = json.loads((MANIFEST_DIR / "beir_scifact.json").read_text(encoding="utf-8"))
    for rel_file, expected_hash in scifact_manifest["storage"]["files"].items():
        actual_hash = sha256_file(RAW_BEIR_DIR / "scifact" / rel_file)
        assert actual_hash == expected_hash, f"Hash mismatch for scifact {rel_file}"

    scidocs_manifest = json.loads((MANIFEST_DIR / "beir_scidocs.json").read_text(encoding="utf-8"))
    for rel_file, expected_hash in scidocs_manifest["storage"]["files"].items():
        actual_hash = sha256_file(RAW_BEIR_DIR / "scidocs" / rel_file)
        assert actual_hash == expected_hash, f"Hash mismatch for scidocs {rel_file}"


def test_datacard_sha256_and_stats_consistency(live_real_audit: dict) -> None:
    """Ensure docs/DATA_CARD.md contains the exact verified SHA-256 hashes and stats."""
    datacard_text = DATA_CARD_PATH.read_text(encoding="utf-8")

    # Hashes from manifests
    scifact_manifest = json.loads((MANIFEST_DIR / "beir_scifact.json").read_text(encoding="utf-8"))
    scidocs_manifest = json.loads((MANIFEST_DIR / "beir_scidocs.json").read_text(encoding="utf-8"))

    # Check SciFact hashes present in DATA_CARD.md
    assert scifact_manifest["storage"]["archive_sha256"] in datacard_text
    assert scifact_manifest["storage"]["files"]["corpus.jsonl"] in datacard_text
    assert scifact_manifest["storage"]["files"]["queries.jsonl"] in datacard_text

    # Check SCIDOCS hashes present in DATA_CARD.md
    assert scidocs_manifest["storage"]["archive_sha256"] in datacard_text
    assert scidocs_manifest["storage"]["files"]["corpus.jsonl"] in datacard_text
    assert scidocs_manifest["storage"]["files"]["queries.jsonl"] in datacard_text

    # Check that licenses are properly documented (not CC0)
    assert "ODC-By 1.0" in datacard_text
    assert "CC BY 4.0" in datacard_text
    assert "Apache-2.0" in datacard_text

    # Check token stats accuracy:
    # SciFact query min: 3, max: 41, mean: 12,904
    assert "Min: 3 | Max: 41" in datacard_text
    # SCIDOCS abstract min: 0, max: 1.919, mean: 172,230
    assert "Min: 0 (344 docs) | Max: 1.919" in datacard_text
    # SCIDOCS combined min: 2, max: 1.923, mean: 182,179
    assert "Min: 2 | Max: 1.923" in datacard_text
    # SCIDOCS query min: 2, max: 30, mean: 9,976
    assert "Min: 2 | Max: 30" in datacard_text
