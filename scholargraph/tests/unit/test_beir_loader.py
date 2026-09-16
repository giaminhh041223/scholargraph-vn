import hashlib
import json
from pathlib import Path

import pytest

from scholargraph.ingest.beir_loader import (
    BeirDataError,
    BeirLoader,
    canonical_beir_id,
    raw_beir_id,
    sha256_file,
    verify_sha256,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _make_snapshot(root: Path) -> Path:
    dataset = root / "scifact"
    (dataset / "qrels").mkdir(parents=True)
    _write_jsonl(
        dataset / "corpus.jsonl",
        [
            {"_id": "doc-a", "title": "Title A", "text": "Abstract A", "metadata": {}},
            {"_id": "doc-b", "title": "", "text": "Text-only title", "metadata": {"year": "2020"}},
        ],
    )
    _write_jsonl(
        dataset / "queries.jsonl",
        [
            {"_id": "q-train", "text": "Train query", "metadata": {}},
            {"_id": "q-test", "text": "Test query", "metadata": {}},
        ],
    )
    (dataset / "qrels" / "train.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq-train\tdoc-a\t1\n", encoding="utf-8"
    )
    (dataset / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq-test\tdoc-b\t2\n", encoding="utf-8"
    )
    return root


def test_loads_only_requested_split_and_namespaces_ids(tmp_path: Path) -> None:
    snapshot_root = _make_snapshot(tmp_path)
    loaded = BeirLoader(snapshot_root).load("scifact", "test")

    assert loaded.name == "scifact"
    assert loaded.split == "test"
    assert list(loaded.queries) == ["beir:scifact:q-test"]
    assert list(loaded.qrels) == ["beir:scifact:q-test"]
    assert loaded.qrels["beir:scifact:q-test"] == {"beir:scifact:doc-b": 2}
    assert loaded.corpus["beir:scifact:doc-b"].title == "Text-only title"
    assert loaded.corpus["beir:scifact:doc-b"].text_content() == "Text-only title"
    assert loaded.corpus["beir:scifact:doc-b"].year == 2020
    assert loaded.queries["beir:scifact:q-test"].metadata["beir_raw_id"] == "q-test"
    assert len(loaded.qrel_records) == 1


def test_available_splits_and_lossless_id_mapping(tmp_path: Path) -> None:
    snapshot_root = _make_snapshot(tmp_path)
    loader = BeirLoader(snapshot_root)

    assert loader.available_splits("scifact") == ("test", "train")
    assert canonical_beir_id("scifact", " raw-id ") == "beir:scifact:raw-id"
    assert raw_beir_id("scifact", "beir:scifact:raw-id") == "raw-id"
    with pytest.raises(BeirDataError, match="does not belong"):
        raw_beir_id("scifact", "beir:scidocs:raw-id")


def test_rejects_qrel_outside_snapshot_universe(tmp_path: Path) -> None:
    snapshot_root = _make_snapshot(tmp_path)
    (snapshot_root / "scifact" / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq-test\tmissing-doc\t1\n", encoding="utf-8"
    )

    with pytest.raises(BeirDataError, match="absent from corpus"):
        BeirLoader(snapshot_root).load("scifact", "test")


def test_rejects_duplicate_qrels_and_never_creates_missing_split(tmp_path: Path) -> None:
    snapshot_root = _make_snapshot(tmp_path)
    (snapshot_root / "scifact" / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq-test\tdoc-a\t1\nq-test\tdoc-a\t1\n", encoding="utf-8"
    )

    with pytest.raises(BeirDataError, match="Duplicate qrel"):
        BeirLoader(snapshot_root).load("scifact", "test")
    with pytest.raises(BeirDataError, match="Missing BEIR qrels split"):
        BeirLoader(snapshot_root).load("scifact", "dev")


def test_checksum_helpers_are_strict_and_deterministic(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.bin"
    payload.write_bytes(b"frozen BEIR snapshot")
    expected = hashlib.sha256(b"frozen BEIR snapshot").hexdigest()

    assert sha256_file(payload) == expected
    assert verify_sha256(payload, expected.upper())
    assert not verify_sha256(payload, "0" * 64)
    with pytest.raises(ValueError, match="64-character"):
        verify_sha256(payload, "not-a-hash")
