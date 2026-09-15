"""Unit tests for BEIR dataset integrity and quality audit (SG-010).

Verifies:
1. ID uniqueness, referential integrity and zero-orphan constraints.
2. Exact counts of documents, queries, and qrels for SciFact and SCIDOCS.
3. SCIDOCS empty-abstract anomaly (exactly 344 documents, 115 positive in test qrels).
4. SciFact train vs test disjointness.
5. Protocol v1 compliance (immutable benchmarks, no hidden filtering).
6. Audit report existence, validity and schema.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scholargraph.ingest.beir_audit import (
    compute_distribution_stats,
    tokenize_text,
    run_full_beir_audit,
)
from scholargraph.ingest.beir_loader import (
    BeirDataError,
    BeirLoader,
    canonical_beir_id,
    raw_beir_id,
)

RAW_BEIR_DIR = Path("data/raw/beir")
REPORT_PATH = Path("artifacts/reports/beir_data_audit.json")


@pytest.fixture(scope="module")
def audit_report() -> dict:
    """Load or generate the BEIR audit report."""
    if not REPORT_PATH.is_file():
        return run_full_beir_audit(RAW_BEIR_DIR, REPORT_PATH)
    with REPORT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_audit_report_structure(audit_report: dict) -> None:
    """Verify top-level structure of the data audit report."""
    assert audit_report["schema_version"] == 1
    assert audit_report["task"] == "SG-010"
    assert "datasets" in audit_report
    assert "scifact" in audit_report["datasets"]
    assert "scidocs" in audit_report["datasets"]
    assert "cross_split_checks" in audit_report
    assert "anomalies_summary" in audit_report
    assert "protocol_compliance" in audit_report


def test_scifact_corpus_integrity(audit_report: dict) -> None:
    """Verify SciFact corpus size, ID uniqueness and non-empty texts."""
    scifact_corpus = audit_report["datasets"]["scifact"]["corpus_audit"]
    assert scifact_corpus["total_documents"] == 5183
    assert scifact_corpus["unique_raw_ids"] == 5183
    assert scifact_corpus["duplicate_raw_ids_count"] == 0
    assert scifact_corpus["missingness"]["empty_or_missing_title_count"] == 0
    assert scifact_corpus["missingness"]["empty_or_missing_text_count"] == 0
    assert scifact_corpus["missingness"]["empty_both_count"] == 0


def test_scifact_splits_and_qrels_integrity(audit_report: dict) -> None:
    """Verify SciFact splits (train as dev, test as official test) and qrels."""
    splits = audit_report["datasets"]["scifact"]["splits_audit"]
    assert "train" in splits
    assert "test" in splits

    train = splits["train"]
    assert train["unique_queries_in_qrels"] == 809
    assert train["total_rows"] == 919
    assert train["referential_integrity"]["orphan_query_ids_count"] == 0
    assert train["referential_integrity"]["orphan_corpus_ids_count"] == 0
    assert train["referential_integrity"]["duplicate_pairs_count"] == 0
    assert train["referential_integrity"]["conflicting_scores_count"] == 0
    assert train["score_distribution"] == {"1": 919}

    test = splits["test"]
    assert test["unique_queries_in_qrels"] == 300
    assert test["total_rows"] == 339
    assert test["referential_integrity"]["orphan_query_ids_count"] == 0
    assert test["referential_integrity"]["orphan_corpus_ids_count"] == 0
    assert test["referential_integrity"]["duplicate_pairs_count"] == 0
    assert test["referential_integrity"]["conflicting_scores_count"] == 0
    assert test["score_distribution"] == {"1": 339}


def test_scifact_train_test_disjointness(audit_report: dict) -> None:
    """Verify SciFact split disjointness: disjoint ID space and exact upstream text duplicates."""
    overlap = audit_report["cross_split_checks"]["scifact_train_vs_test"]
    assert overlap["train_queries_count"] == 809
    assert overlap["test_queries_count"] == 300
    # Query IDs are strictly disjoint
    assert overlap["query_id_overlap_count"] == 0
    # Upstream anomaly: exactly 2 queries in official test share identical text with queries in train
    assert overlap["query_text_exact_overlap_count"] == 2
    details = overlap["query_text_exact_overlap_details"]
    assert len(details) == 2
    test_ids = {d["test_query_id"] for d in details}
    train_ids = {d["train_query_id"] for d in details}
    assert test_ids == {"870", "1292"}
    assert train_ids == {"871", "1291"}


def test_scidocs_corpus_integrity_and_empty_text_anomaly(audit_report: dict) -> None:
    """Verify SCIDOCS corpus size and precisely 344 empty-abstract documents."""
    scidocs_corpus = audit_report["datasets"]["scidocs"]["corpus_audit"]
    assert scidocs_corpus["total_documents"] == 25657
    assert scidocs_corpus["unique_raw_ids"] == 25657
    assert scidocs_corpus["duplicate_raw_ids_count"] == 0
    assert scidocs_corpus["missingness"]["empty_or_missing_title_count"] == 0
    # The known anomaly: exactly 344 documents have empty abstract/text
    assert scidocs_corpus["missingness"]["empty_or_missing_text_count"] == 344
    assert scidocs_corpus["missingness"]["empty_both_count"] == 0


def test_scidocs_qrels_and_anomaly_impact(audit_report: dict) -> None:
    """Verify SCIDOCS test qrels and impact of the 344 empty-abstract docs."""
    splits = audit_report["datasets"]["scidocs"]["splits_audit"]
    assert "test" in splits
    test = splits["test"]

    assert test["unique_queries_in_qrels"] == 1000
    assert test["total_rows"] == 29928
    assert test["referential_integrity"]["orphan_query_ids_count"] == 0
    assert test["referential_integrity"]["orphan_corpus_ids_count"] == 0
    assert test["referential_integrity"]["duplicate_pairs_count"] == 0
    assert test["referential_integrity"]["conflicting_scores_count"] == 0
    assert test["score_distribution"] == {"0": 25000, "1": 4928}

    # All 344 empty-abstract documents appear in qrels, 115 are positive relevant
    impact = test["empty_text_docs_impact"]
    assert impact["empty_text_docs_in_qrels_count"] == 344
    assert impact["empty_text_docs_positive_count"] == 115
    assert len(impact["empty_text_docs_positive"]) == 115


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

    # Cross-dataset rejection
    with pytest.raises(BeirDataError):
        raw_beir_id("scifact", "beir:scidocs:12345")


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


def test_compute_distribution_stats() -> None:
    """Verify summary statistics calculations."""
    stats = compute_distribution_stats([10, 20, 30, 40, 50])
    assert stats["count"] == 5
    assert stats["min"] == 10.0
    assert stats["max"] == 50.0
    assert stats["mean"] == 30.0
    assert stats["median"] == 30.0
    assert stats["p25"] == 20.0
    assert stats["p75"] == 40.0


def test_loader_offline_behavior() -> None:
    """Verify BeirLoader correctly loads offline datasets and rejects non-existent splits."""
    loader = BeirLoader(RAW_BEIR_DIR)
    assert set(loader.available_splits("scifact")) == {"test", "train"}
    assert set(loader.available_splits("scidocs")) == {"test"}

    # Loading SCIDOCS dev must fail because official BEIR has no dev split for SCIDOCS
    with pytest.raises(BeirDataError, match="Missing BEIR qrels split"):
        loader.load("scidocs", "dev")

    # Loading official test succeeds
    scifact_test = loader.load("scifact", "test")
    assert len(scifact_test.corpus) == 5183
    assert len(scifact_test.queries) == 300
    assert len(scifact_test.qrel_records) == 339
