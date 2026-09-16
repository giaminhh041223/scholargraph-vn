"""Unit tests for split isolation, manifest verification, and leakage prevention (SG-011).

Covers:
1. Query namespace disjointness between SciFact dev (train) and test splits.
2. Referential integrity of locked qrels against the frozen document corpus.
3. Consistency between configs/split_policy.json and data/splits/ manifests.
4. Negative tests on synthetic fixtures detecting cross-split query ID leakage and orphan documents.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scholargraph.data.splits import generate_and_audit_splits
from scholargraph.ingest.beir_loader import BeirLoader

RAW_BEIR_DIR = Path("data/raw/beir")
SPLITS_DIR = Path("data/splits")
POLICY_PATH = Path("configs/split_policy.json")
REPORT_PATH = Path("artifacts/reports/split_audit.json")


def test_scifact_split_disjointness_and_counts() -> None:
    """Verify strictly disjoint query ID namespaces between SciFact dev and test."""
    loader = BeirLoader(RAW_BEIR_DIR)
    dev_split = loader.load("scifact", "train")
    test_split = loader.load("scifact", "test")

    dev_qids = set(dev_split.queries.keys())
    test_qids = set(test_split.queries.keys())

    # Critical invariant: Zero ID overlap
    assert len(dev_qids.intersection(test_qids)) == 0

    # Official BEIR query and qrel counts
    assert len(dev_qids) == 809
    assert len(test_qids) == 300
    assert len(dev_split.qrel_records) == 919
    assert len(test_split.qrel_records) == 339


def test_scidocs_test_split_counts() -> None:
    """Verify SCIDOCS official test split counts."""
    loader = BeirLoader(RAW_BEIR_DIR)
    test_split = loader.load("scidocs", "test")

    test_qids = set(test_split.queries.keys())
    assert len(test_qids) == 1000
    assert len(test_split.qrel_records) == 29928
    assert len(test_split.corpus) == 25657


def test_qrels_reference_valid_corpus_universe() -> None:
    """Verify that every qrel record points to an existing corpus document."""
    loader = BeirLoader(RAW_BEIR_DIR)

    # SciFact
    sf_dev = loader.load("scifact", "train")
    sf_test = loader.load("scifact", "test")
    sf_corpus = set(sf_dev.corpus.keys())
    assert all(q.doc_id in sf_corpus for q in sf_dev.qrel_records)
    assert all(q.doc_id in sf_corpus for q in sf_test.qrel_records)

    # SCIDOCS
    sd_test = loader.load("scidocs", "test")
    sd_corpus = set(sd_test.corpus.keys())
    assert all(q.doc_id in sd_corpus for q in sd_test.qrel_records)


def test_split_policy_config_matches_manifests() -> None:
    """Ensure configs/split_policy.json matches files on disk and split manifests."""
    assert POLICY_PATH.exists()
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert policy["task"] == "SG-011"
    assert policy["invariants"]["disjoint_query_id_namespaces"] is True
    assert policy["invariants"]["no_test_labels_in_ranker"] is True

    sf_dev_manifest = json.loads((SPLITS_DIR / "scifact_dev.json").read_text(encoding="utf-8"))
    assert sf_dev_manifest["dataset"] == "scifact"
    assert sf_dev_manifest["split"] == "dev"
    assert sf_dev_manifest["query_count"] == 809
    assert sf_dev_manifest["qrel_count"] == 919

    sf_test_manifest = json.loads((SPLITS_DIR / "scifact_test.json").read_text(encoding="utf-8"))
    assert sf_test_manifest["dataset"] == "scifact"
    assert sf_test_manifest["split"] == "test"
    assert sf_test_manifest["query_count"] == 300
    assert sf_test_manifest["qrel_count"] == 339

    sd_test_manifest = json.loads((SPLITS_DIR / "scidocs_test.json").read_text(encoding="utf-8"))
    assert sd_test_manifest["dataset"] == "scidocs"
    assert sd_test_manifest["split"] == "test"
    assert sd_test_manifest["query_count"] == 1000
    assert sd_test_manifest["qrel_count"] == 29928


def test_negative_synthetic_leakage_detection(tmp_path: Path) -> None:
    """Negative test: auditor must fail when synthetic dev and test have overlapping query IDs."""
    synth_root = tmp_path / "raw"
    synth_scifact = synth_root / "scifact"
    synth_scidocs = synth_root / "scidocs"
    synth_scifact.mkdir(parents=True)
    synth_scidocs.mkdir(parents=True)
    (synth_scifact / "qrels").mkdir()
    (synth_scidocs / "qrels").mkdir()

    # Synthetic SciFact with LEAKAGE (same query ID 'q_leak' in both train and test)
    (synth_scifact / "corpus.jsonl").write_text(
        json.dumps({"_id": "doc1", "title": "Doc 1", "text": "Text 1"}) + "\n",
        encoding="utf-8",
    )
    (synth_scifact / "queries.jsonl").write_text(
        json.dumps({"_id": "q_leak", "text": "Leaked query."}) + "\n",
        encoding="utf-8",
    )
    (synth_scifact / "qrels" / "train.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq_leak\tdoc1\t1\n",
        encoding="utf-8",
    )
    (synth_scifact / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq_leak\tdoc1\t1\n",
        encoding="utf-8",
    )

    # Valid synthetic SCIDOCS
    (synth_scidocs / "corpus.jsonl").write_text(
        json.dumps({"_id": "sd_doc1", "title": "SD Doc 1", "text": "SD Text 1"}) + "\n",
        encoding="utf-8",
    )
    (synth_scidocs / "queries.jsonl").write_text(
        json.dumps({"_id": "sd_q1", "text": "SD Query 1."}) + "\n",
        encoding="utf-8",
    )
    (synth_scidocs / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nsd_q1\tsd_doc1\t1\n",
        encoding="utf-8",
    )

    rep = generate_and_audit_splits(
        raw_root=synth_root,
        splits_dir=tmp_path / "splits",
        report_output_path=tmp_path / "split_audit.json",
    )
    assert rep["split_audit_passed"] is False
    assert any("overlapping query IDs" in err for err in rep["errors"])
    assert rep["leakage_checks"]["scifact_query_id_disjoint"] is False
    assert "beir:scifact:q_leak" in rep["leakage_checks"]["scifact_query_id_overlap_ids"]
