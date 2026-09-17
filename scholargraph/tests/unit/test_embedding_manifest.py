"""Adversarial and positive tests for SG-019 sharded dense encoding (offline).

All tests are OFFLINE and synthetic: no HuggingFace weights are downloaded and
no torch model is loaded. A deterministic mock encoder object implements the
same interface as ``HfLocalEncoder`` (this is a legitimate test double for the
*manifest/resume/index logic*; measured throughputs in
``artifacts/reports/encoding_profile.json`` come from real runs and are never
taken from these mocks).

Covers:
1. Manifest schema: every completed shard manifest carries the exact doc-ID
   list, checksum, model/tokenizer revision, config hash and status.
2. Doc-ID order: shard rows reproduce the canonical-ID-ascending corpus order
   (verified against text-dependent mock vectors, so row i is provably the
   embedding of doc_ids[i]).
3. Checksum verification: a corrupted ``.npy`` is refused on resume, on
   ``verify`` and blocks index building (never silently reused).
4. Resume semantics: completed shards with matching checksum/config are
   skipped (encoder never constructed); an orphan ``.npy`` without a manifest
   is re-encoded; a changed config/model/corpus pin is REFUSED (exit 1 via
   CLI subprocess, no config mixing).
5. Fail-loud config CLI (SG-017 review P2-2): missing mandatory field, empty
   revision, ``normalize=false``, wrong prefix scope and protocol drift all
   exit 1 before any model work.
6. ``missing_embedding=fail_not_drop_document``: a corpus document with
   neither title nor text is a hard error naming the document; nothing is
   dropped; CLI exits 1.
7. Prefix contract: documents are encoded without prefix, queries with the
   config prefix (query_only).
8. Exact index: doc-ID order, hashes, cosine search by hand computation, and
   refusal to build over an incomplete shard set.
9. Profile assembly: totals must come from summaries; the GPU field stays
   ``"not_measured_local"``.
10. Notebook validity for ``notebooks/encode_corpus.ipynb``.

Fixtures live only in ``tmp_path``; nothing is written under ``data/`` of the
real project. CLI tests run through ``subprocess`` and assert exit codes per
ADR-013.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scholargraph.retrieval import dense
from scholargraph.retrieval.dense import (
    DenseConfig,
    DenseConfigError,
    DenseDataError,
    DenseEncodingError,
    DenseResumeError,
    apply_query_prefix,
    build_exact_index,
    build_encoding_profile,
    encode_queries,
    load_dense_encoder_config,
    plan_shards,
    run_encoding,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
MODEL_ID = "BAAI/bge-base-en-v1.5"
PREFIX = "Represent this sentence for searching relevant passages: "

BEIR_DOCS = [
    {"_id": "d3", "title": "Diffusion models for protein design", "text": "We study protein backbones.", "metadata": {}},
    {"_id": "d1", "title": "Graph neural networks", "text": "Message passing over citation graphs.", "metadata": {}},
    {"_id": "d2", "title": "Zooplankton ecology", "text": "Seasonal dynamics of plankton.", "metadata": {}},
]


# ---------------------------------------------------------------------------
# Fixture builders (tmp_path only)
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _write_config(root: Path, **mutations: Any) -> Path:
    raw = json.loads((PROJECT_ROOT / "configs" / "models" / "dense_encoder.json").read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    for dotted, value in mutations.items():
        section, _, key = dotted.partition("__")
        if not key:
            raise ValueError("Mutations must look like 'selection__key' or 'protocol_reference__key'.")
        raw[section][key] = value
    path = root / "configs" / "models" / "dense_encoder.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


def _write_protocol(root: Path, **mutations: Any) -> Path:
    protocol: dict[str, Any] = {
        "retrieval": {
            "dense": {
                "similarity": "cosine",
                "l2_normalize": True,
                "missing_embedding": "fail_not_drop_document",
                "selection_gate": "SG-017",
            }
        }
    }
    for dotted, value in mutations.items():
        section, _, key = dotted.partition("__")
        if section != "dense":
            raise ValueError("Protocol mutations must target the 'dense' block.")
        protocol["retrieval"]["dense"][key] = value
    path = root / "configs" / "protocol_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    return path


def _write_beir_corpus(root: Path, rows: list[dict[str, Any]], *, dataset: str = "scifact") -> Path:
    corpus_path = root / "data" / "raw" / "beir" / dataset / "corpus.jsonl"
    _write_jsonl(corpus_path, rows)
    sha = _sha256(corpus_path)
    manifest = {
        "storage": {"files": {"corpus.jsonl": sha}},
        "counts": {"corpus": len(rows)},
    }
    manifest_path = root / "data" / "manifests" / f"beir_{dataset}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return corpus_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MockEncoder:
    """Deterministic offline encoder double with the HfLocalEncoder interface.

    Row content depends on the text (first coordinate scales with text length,
    second is constant), which makes the doc-ID/row-order correspondence
    checkable without any real model.
    """

    def __init__(self, config: DenseConfig) -> None:
        self.config = config
        self.model_id = config.model_id
        self.model_revision = config.revision
        self.tokenizer_revision = config.revision
        self.embedding_dimension = config.embedding_dimension
        self.max_length = config.max_length
        self.pooling = config.pooling
        self.device = "cpu"
        self.impl_name = "mock_encoder_for_tests"
        self.seen_texts: list[str] = []

    def encode(self, texts: list[str]) -> np.ndarray:
        self.seen_texts.extend(texts)
        out = np.zeros((len(texts), self.embedding_dimension), dtype=np.float32)
        for index, text in enumerate(texts):
            out[index, 0] = float(len(text))
            out[index, 1] = 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return (out / norms).astype(np.float32)

    def token_lengths(self, texts: list[str]) -> list[int]:
        return [len(text.split()) + 2 for text in texts]


def _mock_factory(config: DenseConfig) -> MockEncoder:
    return MockEncoder(config)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A minimal synthetic project root: pinned config + a tiny BEIR corpus."""

    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    return root


def _load_config(root: Path) -> DenseConfig:
    return load_dense_encoder_config(
        root / "configs" / "models" / "dense_encoder.json",
        root / "configs" / "protocol_v1.json",
    )


def _encode(root: Path, **kwargs: Any) -> dict[str, Any]:
    config = _load_config(root)
    return run_encoding(
        project_root=root,
        corpus_id="scifact",
        config=config,
        encoder_factory=_mock_factory,
        **kwargs,
    )


def _manifests(root: Path, namespace: str) -> list[dict[str, Any]]:
    manifest_dir = root / "data" / "manifests" / "encoding_shards" / "scifact" / namespace
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(manifest_dir.glob("shard-*.json"))]


# ---------------------------------------------------------------------------
# Config loading: fail-loud contract (SG-017 P2-2)
# ---------------------------------------------------------------------------


def test_valid_config_loads_with_pinned_revision(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    config = _load_config(root)
    assert config.model_id == MODEL_ID
    assert config.revision == REVISION
    assert config.pooling == "cls"
    assert config.normalize is True
    assert config.max_length == 512
    assert config.embedding_dimension == 768
    assert config.prefix == PREFIX
    assert config.prefix_scope == "query_only"
    assert config.missing_embedding == "fail_not_drop_document"
    assert config.similarity == "cosine"
    assert len(config.config_hash) == 64
    assert config.namespace.startswith("bge-base-en-v1.5__a5beb1e3")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", ""),
        ("revision", "not-a-sha"),
        ("revision", ""),
        ("pooling", "mean"),
        ("normalize", False),
        ("max_length", 0),
        ("embedding_dimension", -1),
        ("prefix_scope", "both"),
        ("license", ""),
    ],
)
def test_invalid_selection_field_is_rejected(tmp_path: Path, field: str, value: Any) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root, **{f"selection__{field}": value})
    _write_protocol(root)
    with pytest.raises(DenseConfigError, match=field):
        _load_config(root)


def test_missing_mandatory_selection_field_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    path = root / "configs" / "models" / "dense_encoder.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["selection"]["revision"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DenseConfigError, match="revision"):
        _load_config(root)


def test_empty_revision_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root, **{"selection__revision": "   "})
    _write_protocol(root)
    with pytest.raises(DenseConfigError, match="revision"):
        _load_config(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("similarity", "dot"),
        ("l2_normalize", False),
        ("missing_embedding", "drop_document"),
    ],
)
def test_protocol_reference_drift_is_rejected(tmp_path: Path, field: str, value: Any) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root, **{f"dense__{field}": value})
    with pytest.raises(DenseConfigError, match=field):
        _load_config(root)


def test_config_drift_from_protocol_file_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root, **{"dense__l2_normalize": False})
    with pytest.raises(DenseConfigError, match="l2_normalize"):
        _load_config(root)


def test_config_hash_changes_with_max_length(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    _write_config(root_a)
    _write_config(root_b, **{"selection__max_length": 256})
    _write_protocol(root_a)
    _write_protocol(root_b)
    assert _load_config(root_a).config_hash != _load_config(root_b).config_hash


# ---------------------------------------------------------------------------
# Corpus reading: missing_embedding = fail_not_drop_document
# ---------------------------------------------------------------------------


def test_beir_document_without_title_and_text_fails_loudly(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    rows = copy.deepcopy(BEIR_DOCS) + [{"_id": "d9", "title": "", "text": "", "metadata": {}}]
    _write_beir_corpus(root, rows)
    with pytest.raises(DenseDataError, match="d9"):
        dense.read_corpus("scifact", root)


def test_missing_corpus_file_fails(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    (root / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl").unlink()
    with pytest.raises(DenseDataError, match="Missing corpus JSONL"):
        dense.read_corpus("scifact", root)


def test_corpus_sha_mismatch_against_manifest_fails(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    corpus_path = _write_beir_corpus(root, BEIR_DOCS)
    corpus_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in BEIR_DOCS[:-1]),
        encoding="utf-8",
    )
    with pytest.raises(DenseDataError, match="sha256 mismatch"):
        dense.read_corpus("scifact", root)


def test_corpus_count_mismatch_fails(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    manifest_path = root / "data" / "manifests" / "beir_scifact.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["corpus"] = len(BEIR_DOCS) + 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DenseDataError, match="manifest"):
        dense.read_corpus("scifact", root)


def test_duplicate_corpus_id_fails(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS + [copy.deepcopy(BEIR_DOCS[0])])
    with pytest.raises(DenseDataError, match="Duplicate corpus ID"):
        dense.read_corpus("scifact", root)


def test_openalex_text_reconstruction_and_missing_title(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    rows = [
        {
            "id": "https://openalex.org/W2",
            "title": None,
            "abstract_inverted_index": {"b": [1], "a": [0]},
        },
        {
            "id": "https://openalex.org/W1",
            "title": "Only a title",
            "abstract_inverted_index": None,
        },
    ]
    corpus_path = root / "data" / "processed" / "openalex" / "works.jsonl"
    _write_jsonl(corpus_path, rows)
    manifest = {
        "postprocess": {"processed_works": len(rows), "output_order": "canonical ID ascending"},
        "artifacts": {"works_jsonl": {"path": "data/processed/openalex/works.jsonl", "sha256": _sha256(corpus_path)}},
    }
    manifest_path = root / "data" / "manifests" / "openalex_core.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    corpus = dense.read_corpus("openalex_core", root)
    assert corpus.doc_ids == ("openalex:W1", "openalex:W2")
    texts = dict(zip(corpus.doc_ids, corpus.texts))
    # W1: title only (missing abstract); W2: abstract reconstructed in position order.
    assert texts["openalex:W1"] == "Only a title"
    assert texts["openalex:W2"] == "a b"
    assert corpus.missing_abstract_count == 1
    assert corpus.missing_title_count == 1


def test_openalex_work_without_title_and_abstract_fails(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    rows = [
        {"id": "https://openalex.org/W1", "title": "T", "abstract_inverted_index": {"a": [0]}},
        {"id": "https://openalex.org/W2", "title": None, "abstract_inverted_index": None},
    ]
    corpus_path = root / "data" / "processed" / "openalex" / "works.jsonl"
    _write_jsonl(corpus_path, rows)
    manifest = {
        "postprocess": {"processed_works": len(rows), "output_order": "canonical ID ascending"},
        "artifacts": {"works_jsonl": {"path": "data/processed/openalex/works.jsonl", "sha256": _sha256(corpus_path)}},
    }
    manifest_path = root / "data" / "manifests" / "openalex_core.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DenseDataError, match="openalex:W2"):
        dense.read_corpus("openalex_core", root)


def test_openalex_manifest_without_input_hash_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    rows = [{"id": "https://openalex.org/W1", "title": "T", "abstract_inverted_index": None}]
    corpus_path = root / "data" / "processed" / "openalex" / "works.jsonl"
    _write_jsonl(corpus_path, rows)
    manifest = {"postprocess": {"processed_works": 1, "output_order": "canonical ID ascending"}, "artifacts": {}}
    manifest_path = root / "data" / "manifests" / "openalex_core.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DenseDataError, match="does not pin a sha256"):
        dense.read_corpus("openalex_core", root)


# ---------------------------------------------------------------------------
# Shard planning, manifests, doc-ID order
# ---------------------------------------------------------------------------


def test_plan_shards_is_contiguous_and_covers_all() -> None:
    assert plan_shards(7, 3) == [(0, 3), (3, 6), (6, 7)]
    assert plan_shards(0, 3) == []
    with pytest.raises(DenseDataError):
        plan_shards(5, 0)


def test_encoded_manifest_schema_and_doc_id_order(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    manifests = _manifests(project, config.namespace)
    assert [m["shard_name"] for m in manifests] == ["shard-00000", "shard-00001"]
    all_doc_ids: list[str] = []
    for manifest in manifests:
        assert manifest["schema_version"] == 1
        assert manifest["status"] == "COMPLETED"
        assert manifest["config_hash"] == config.config_hash
        assert manifest["model"]["id"] == MODEL_ID
        assert manifest["model"]["revision"] == REVISION
        assert manifest["model"]["tokenizer_revision"] == REVISION
        assert manifest["model"]["pooling"] == "cls"
        assert manifest["model"]["embedding_dimension"] == 768
        assert manifest["encoding"]["max_length"] == 512
        assert manifest["encoding"]["l2_normalized"] is True
        assert manifest["encoding"]["prefix_scope"] == "query_only"
        assert manifest["embeddings"]["dtype"] == "float32"
        assert manifest["doc_count"] == len(manifest["doc_ids"]) > 0
        assert manifest["doc_id_first"] == manifest["doc_ids"][0]
        assert manifest["doc_id_last"] == manifest["doc_ids"][-1]
        assert manifest["embeddings"]["sha256"] == _sha256(project / manifest["embeddings"]["path"])
        assert manifest["timing"]["docs_per_second"] is not None and manifest["timing"]["docs_per_second"] > 0
        all_doc_ids.extend(manifest["doc_ids"])

    corpus = dense.read_corpus("scifact", project)
    # Canonical ID ascending order, split across shards without gaps.
    assert all_doc_ids == list(corpus.doc_ids)

    # Row i of shard matrix is provably the embedding of doc_ids[i]:
    # the mock vector is (len(text), 1)/norm so coordinate 0 is recoverable.
    for manifest in manifests:
        matrix = np.load(project / manifest["embeddings"]["path"], allow_pickle=False)
        for row, doc_id in zip(matrix, manifest["doc_ids"]):
            text = corpus.texts[corpus.doc_ids.index(doc_id)]
            expected0 = np.float32(len(text) / np.sqrt(len(text) ** 2 + 1.0))
            assert row[0] == pytest.approx(expected0, abs=1e-6)
            assert row[1] == pytest.approx(1.0 / np.sqrt(len(text) ** 2 + 1.0), abs=1e-6)


def test_vectors_are_l2_normalized_and_index_search_is_cosine(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    index = build_exact_index(project_root=project, corpus_id="scifact", config=config)
    assert index["doc_count"] == 3
    assert index["ann"] == {"used": False, "recall_audit": "not_applicable_exact_index"}
    loaded = dense.ExactDenseIndex.load(project / "artifacts" / "indexes" / "scifact" / config.namespace)
    matrix = np.asarray(loaded.matrix)
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-3)

    # Hand-computed cosine: mock vector of doc 0 is (len0, 1, 0, ...)/norm.
    corpus = dense.read_corpus("scifact", project)
    text0 = corpus.texts[0]
    length0 = float(len(text0))
    dim = config.embedding_dimension
    query = np.zeros(dim, dtype=np.float32)
    query[0] = length0
    query[1] = 1.0
    query /= np.linalg.norm(query)
    results = loaded.search(query, top_k=3)
    assert results[0][0] == corpus.doc_ids[0]
    assert results[0][1] == pytest.approx(1.0, abs=1e-5)
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    unnormalized = np.zeros(dim, dtype=np.float32)
    unnormalized[0] = 2.0
    unnormalized[1] = 3.0
    with pytest.raises(DenseDataError, match="not L2-normalized"):
        loaded.search(unnormalized, top_k=1)


def test_index_artifacts_record_hashes_and_doc_order(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    build_exact_index(project_root=project, corpus_id="scifact", config=config)
    index_dir = project / "artifacts" / "indexes" / "scifact" / config.namespace
    manifest = json.loads((index_dir / "index.json").read_text(encoding="utf-8"))
    assert manifest["artifact_kind"] == "dense_exact_index"
    assert manifest["status"] == "COMPLETED"
    assert manifest["artifacts"]["embeddings"]["sha256"] == _sha256(index_dir / "embeddings.npy")
    assert manifest["artifacts"]["doc_ids"]["sha256"] == _sha256(index_dir / "doc_ids.json")
    doc_rows = json.loads((index_dir / "doc_ids.json").read_text(encoding="utf-8"))
    corpus = dense.read_corpus("scifact", project)
    assert doc_rows["doc_ids"] == list(corpus.doc_ids)
    assert manifest["model"]["revision"] == REVISION
    assert manifest["config_hash"] == config.config_hash


def test_index_refuses_incomplete_shard_set(project: Path) -> None:
    _encode(project, shard_size=2, max_shards=1)
    config = _load_config(project)
    with pytest.raises(DenseDataError, match="encode all shards first|cover"):
        build_exact_index(project_root=project, corpus_id="scifact", config=config)


def test_index_refuses_when_manifest_gaps_exist(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    manifest_dir = project / "data" / "manifests" / "encoding_shards" / "scifact" / config.namespace
    sorted_manifests = sorted(manifest_dir.glob("shard-*.json"))
    # Renaming shard-00000 away leaves a gapless-sequence violation.
    sorted_manifests[0].rename(manifest_dir / "shard-00009.json")
    with pytest.raises(DenseDataError, match="contiguous"):
        build_exact_index(project_root=project, corpus_id="scifact", config=config)


# ---------------------------------------------------------------------------
# Resume semantics
# ---------------------------------------------------------------------------


def test_resume_skips_completed_shards_without_encoder(project: Path) -> None:
    first = _encode(project, shard_size=2)
    assert first["shards_completed"] == 2
    config = _load_config(project)
    # encoder_factory provided but must NOT be called when nothing is pending.
    calls: list[int] = []

    def counting_factory(config: DenseConfig) -> MockEncoder:
        calls.append(1)
        return MockEncoder(config)

    second = run_encoding(
        project_root=project,
        corpus_id="scifact",
        config=config,
        encoder_factory=counting_factory,
        shard_size=2,
    )
    assert calls == []
    assert second["status"] == "COMPLETED"
    assert second["shards_skipped_resume"] == 2
    assert second["checksums_verified"] == 2
    assert second["encoder_impl"] == "not_loaded_resume_only"


def test_resume_reencodes_orphan_npy_without_manifest(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    npy_dir = project / "artifacts" / "indexes" / "scifact" / config.namespace / "shards"
    # A COMPLETED manifest whose .npy disappeared must never resume silently.
    (npy_dir / "shard-00001.npy").unlink()
    with pytest.raises(DenseResumeError, match="missing"):
        run_encoding(project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2)

    # A true orphan: npy present, manifest deleted -> re-encode, never trusted.
    manifest_path = (
        project / "data" / "manifests" / "encoding_shards" / "scifact" / config.namespace / "shard-00001.json"
    )
    manifest_path.unlink()
    (npy_dir / "shard-00001.npy").write_bytes(b"orphan leftovers")
    summary = run_encoding(
        project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2
    )
    assert summary["status"] == "COMPLETED"
    assert summary["shards_reencoded_orphan"] == 1
    assert summary["shards_skipped_resume"] == 1


def test_resume_refuses_tampered_shard_checksum(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    npy_dir = project / "artifacts" / "indexes" / "scifact" / config.namespace / "shards"
    matrix = np.load(npy_dir / "shard-00000.npy", allow_pickle=False)
    matrix[0, 0] = np.float32(matrix[0, 0] + 0.5)
    np.save(npy_dir / "shard-00000.npy", matrix, allow_pickle=False)
    with pytest.raises(DenseResumeError, match="Checksum mismatch"):
        run_encoding(project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2)


def test_resume_refuses_config_change(project: Path) -> None:
    """Config change within the same model revision must refuse to resume.

    The namespace is model+revision (COMPUTE_PLAN §7), so a changed config
    hits the existing manifests, whose config_hash no longer matches: the run
    is refused instead of silently mixing configs.
    """

    _encode(project, shard_size=2)
    namespace_before = _load_config(project).namespace
    _write_config(project, **{"selection__max_length": 256})
    config = _load_config(project)
    assert config.namespace == namespace_before  # same model revision namespace
    with pytest.raises(DenseResumeError, match="refusing to mix configs"):
        run_encoding(project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2)


def test_revision_change_never_reuses_old_namespace(project: Path) -> None:
    """A different model revision gets its own namespace; old files are not mixed."""

    _encode(project, shard_size=2)
    old_config = _load_config(project)
    old_npy = project / "artifacts" / "indexes" / "scifact" / old_config.namespace / "shards" / "shard-00000.npy"
    old_sha = _sha256(old_npy)

    _write_config(project, **{"selection__revision": "b" * 40})
    new_config = _load_config(project)
    assert new_config.namespace != old_config.namespace
    summary = run_encoding(
        project_root=project, corpus_id="scifact", config=new_config, encoder_factory=_mock_factory, shard_size=2
    )
    assert summary["status"] == "COMPLETED"
    # Old namespace artifacts remain untouched; new namespace is separate.
    assert _sha256(old_npy) == old_sha
    assert (project / "artifacts" / "indexes" / "scifact" / new_config.namespace / "shards" / "shard-00000.npy").is_file()


def test_resume_refuses_manifest_with_foreign_config_hash(project: Path) -> None:
    """A manifest inside the namespace pinning another config is refused."""

    _encode(project, shard_size=2)
    config = _load_config(project)
    manifest_dir = project / "data" / "manifests" / "encoding_shards" / "scifact" / config.namespace
    manifest = json.loads((manifest_dir / "shard-00000.json").read_text(encoding="utf-8"))
    manifest["config_hash"] = "f" * 64
    (manifest_dir / "shard-00000.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DenseResumeError, match="refusing to mix configs"):
        run_encoding(project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2)


def test_resume_refuses_manifest_with_foreign_revision(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    manifest_dir = project / "data" / "manifests" / "encoding_shards" / "scifact" / config.namespace
    manifest = json.loads((manifest_dir / "shard-00001.json").read_text(encoding="utf-8"))
    manifest["model"]["revision"] = "c" * 40
    (manifest_dir / "shard-00001.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DenseResumeError, match="revision"):
        run_encoding(project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2)


def test_resume_refuses_changed_corpus_source(project: Path) -> None:
    _encode(project, shard_size=2)
    corpus_path = project / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl"
    rows = copy.deepcopy(BEIR_DOCS)
    rows[0]["text"] = rows[0]["text"] + " Changed."
    _write_beir_corpus(project, rows)
    config = _load_config(project)
    with pytest.raises(DenseResumeError, match="source_sha256"):
        run_encoding(project_root=project, corpus_id="scifact", config=config, encoder_factory=_mock_factory, shard_size=2)


def test_interrupted_run_records_resume_point(project: Path) -> None:
    summary = _encode(project, shard_size=2, max_shards=1)
    assert summary["status"] == "INTERRUPTED"
    assert summary["resume_point"] == {
        "next_shard_index": 1,
        "next_shard_name": "shard-00001",
        "remaining_shards": 1,
        "remaining_documents": 1,
    }
    assert summary["encoded_documents"] == 2
    assert summary["truncated_by_max_shards"] is True
    # Continuation completes the corpus and keeps run history.
    final = run_encoding(
        project_root=project,
        corpus_id="scifact",
        config=_load_config(project),
        encoder_factory=_mock_factory,
        shard_size=2,
    )
    assert final["status"] == "COMPLETED"
    assert len(final["runs"]) == 2


# ---------------------------------------------------------------------------
# Prefix contract: documents bare, queries prefixed
# ---------------------------------------------------------------------------


def test_apply_query_prefix() -> None:
    assert apply_query_prefix(["a", "b"], "P: ") == ["P: a", "P: b"]


def test_documents_are_encoded_without_prefix(project: Path) -> None:
    encoder = MockEncoder(_load_config(project))
    run_encoding(
        project_root=project,
        corpus_id="scifact",
        config=_load_config(project),
        encoder=encoder,
        shard_size=2,
    )
    corpus = dense.read_corpus("scifact", project)
    for text in encoder.seen_texts:
        assert text in corpus.texts
        assert not text.startswith(PREFIX)


def test_encode_queries_applies_prefix_and_keeps_order(project: Path) -> None:
    _encode(project, shard_size=2)  # ensure summary exists; queries are independent
    config = _load_config(project)
    encoder = MockEncoder(config)
    queries = [("q2", "second claim"), ("q1", "first claim")]
    result = encode_queries(
        project_root=project,
        corpus_id="scifact",
        split="dev",
        queries=queries,
        config=config,
        encoder=encoder,
    )
    assert encoder.seen_texts == [f"{PREFIX}second claim", f"{PREFIX}first claim"]
    assert result["query_ids"] == ["q2", "q1"]
    assert result["prefix_applied"] == PREFIX
    assert result["embeddings"].shape == (2, 768)
    assert np.allclose(np.linalg.norm(result["embeddings"], axis=1), 1.0, atol=1e-3)


def test_encode_queries_rejects_empty_text_and_duplicates(project: Path) -> None:
    config = _load_config(project)
    encoder = MockEncoder(config)
    with pytest.raises(DenseDataError, match="Empty query text"):
        encode_queries(
            project_root=project, corpus_id="scifact", split="dev", queries=[("q1", " ")],
            config=config, encoder=encoder,
        )
    with pytest.raises(DenseDataError, match="Duplicate query IDs"):
        encode_queries(
            project_root=project, corpus_id="scifact", split="dev", queries=[("q1", "a"), ("q1", "b")],
            config=config, encoder=encoder,
        )


# ---------------------------------------------------------------------------
# Truncation measurement (mock token lengths)
# ---------------------------------------------------------------------------


def test_truncation_stats_are_measured_per_corpus(project: Path) -> None:
    summary = _encode(project, shard_size=2)
    truncation = summary["truncation"]
    assert truncation["documents_measured"] == 3
    assert truncation["documents_over_limit"] == 0
    assert truncation["truncation_rate"] == 0.0
    assert truncation["token_length"]["max"] >= truncation["token_length"]["min"]


# ---------------------------------------------------------------------------
# Encoding validation
# ---------------------------------------------------------------------------


def test_non_finite_embeddings_are_rejected(project: Path) -> None:
    config = _load_config(project)

    class BrokenEncoder(MockEncoder):
        def encode(self, texts: list[str]) -> np.ndarray:
            out = super().encode(texts)
            out[0, 0] = np.float32("nan")
            return out

    with pytest.raises(DenseEncodingError, match="non-finite"):
        run_encoding(
            project_root=project, corpus_id="scifact", config=config, encoder=BrokenEncoder(config), shard_size=2
        )


def test_unnormalized_embeddings_are_rejected(project: Path) -> None:
    config = _load_config(project)

    class UnnormalizedEncoder(MockEncoder):
        def encode(self, texts: list[str]) -> np.ndarray:
            return np.ones((len(texts), self.embedding_dimension), dtype=np.float32) * 3.0

    with pytest.raises(DenseEncodingError, match="L2-normalized"):
        run_encoding(
            project_root=project,
            corpus_id="scifact",
            config=config,
            encoder=UnnormalizedEncoder(config),
            shard_size=2,
        )


def test_encoder_config_pin_mismatch_is_refused(project: Path) -> None:
    config = _load_config(project)

    class WrongRevisionEncoder(MockEncoder):
        def __init__(self) -> None:
            super().__init__(config)
            self.model_revision = "c" * 40

    with pytest.raises(DenseDataError, match="revision"):
        run_encoding(
            project_root=project, corpus_id="scifact", config=config, encoder=WrongRevisionEncoder(), shard_size=2
        )


# ---------------------------------------------------------------------------
# Profile assembly
# ---------------------------------------------------------------------------


def test_profile_totals_and_gpu_field(project: Path) -> None:
    summary = _encode(project, shard_size=2)
    config = _load_config(project)
    profile = build_encoding_profile(
        project_root=project,
        corpus_namespaces={"scifact": config.namespace},
    )
    assert profile["encoder"]["revision"] == REVISION
    assert profile["encoder"]["tokenizer_revision"] == REVISION
    assert profile["environment"]["gpu"] == "not_measured_local"
    assert profile["corpora"]["scifact"]["status"] == "COMPLETED"
    assert profile["totals"]["documents_expected"] == 3
    assert profile["totals"]["documents_encoded"] == 3
    assert profile["totals"]["shards_completed"] == 2
    assert profile["protocol"]["missing_embedding"] == "fail_not_drop_document"
    assert profile["protocol"]["l2_normalize"] is True
    assert summary["status"] == "COMPLETED"


def test_profile_requires_summary_fields(project: Path) -> None:
    _encode(project, shard_size=2)
    config = _load_config(project)
    summary_path = project / "artifacts" / "indexes" / "scifact" / config.namespace / "encode_summary.json"
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    del loaded["expected_documents"]
    summary_path.write_text(json.dumps(loaded), encoding="utf-8")
    with pytest.raises(DenseDataError, match="expected_documents"):
        build_encoding_profile(project_root=project, corpus_namespaces={"scifact": config.namespace})


# ---------------------------------------------------------------------------
# CLI subprocess tests (exit codes per ADR-013)
# ---------------------------------------------------------------------------


def run_cli(args: list[str], *, cwd: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=600,
        check=False,
    )


MOCK_ENCODER_MODULE = '''
import numpy as np


class MockEncoder:
    def __init__(self, config):
        self.config = config
        self.model_id = config.model_id
        self.model_revision = config.revision
        self.tokenizer_revision = config.revision
        self.embedding_dimension = config.embedding_dimension
        self.max_length = config.max_length
        self.pooling = config.pooling
        self.device = "cpu"
        self.impl_name = "mock_encoder_for_tests"

    def encode(self, texts):
        out = np.zeros((len(texts), self.embedding_dimension), dtype=np.float32)
        for index, text in enumerate(texts):
            out[index, 0] = float(len(text))
            out[index, 1] = 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return (out / norms).astype(np.float32)

    def token_lengths(self, texts):
        return [len(text.split()) + 2 for text in texts]


def create_encoder(config):
    return MockEncoder(config)
'''


def test_cli_end_to_end_with_mock_encoder_exit_0(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    mock_path = tmp_path / "sg019_mock_encoder.py"
    mock_path.write_text(MOCK_ENCODER_MODULE, encoding="utf-8")
    env = {"PYTHONPATH": str(PROJECT_ROOT / "src") + os.pathsep + str(tmp_path)}

    encode_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scholargraph.retrieval.dense",
            "--encoder-module",
            "sg019_mock_encoder:create_encoder",
            "encode",
            "--corpus",
            "scifact",
            "--shard-size",
            "2",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, **env},
        timeout=600,
        check=False,
    )
    assert encode_result.returncode == 0, encode_result.stderr

    index_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scholargraph.retrieval.dense",
            "--encoder-module",
            "sg019_mock_encoder:create_encoder",
            "index",
            "--corpus",
            "scifact",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, **env},
        timeout=600,
        check=False,
    )
    assert index_result.returncode == 0, index_result.stderr

    verify_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scholargraph.retrieval.dense",
            "verify",
            "--corpus",
            "scifact",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, **env},
        timeout=600,
        check=False,
    )
    assert verify_result.returncode == 0, verify_result.stderr
    verify_payload = json.loads(verify_result.stdout)
    assert verify_payload["status"] == "PASS"
    assert verify_payload["shards_verified_completed"] == 2


def test_cli_encode_resume_without_model_download_exit_0(tmp_path: Path) -> None:
    """A fully-completed corpus resumes via CLI with no model loading (exit 0)."""

    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    mock_path = tmp_path / "sg019_mock_encoder.py"
    mock_path.write_text(MOCK_ENCODER_MODULE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src") + os.pathsep + str(tmp_path)}

    first = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_mock_encoder:create_encoder",
         "encode", "--corpus", "scifact", "--shard-size", "2"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert first.returncode == 0, first.stderr

    # The broken module would explode if it were ever imported; a pure-resume
    # run must not construct any encoder at all.
    broken_path = tmp_path / "sg019_broken_encoder.py"
    broken_path.write_text("raise RuntimeError('encoder must not be loaded during resume')\n", encoding="utf-8")
    resume = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_broken_encoder:create_encoder",
         "encode", "--corpus", "scifact", "--shard-size", "2"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert resume.returncode == 0, resume.stderr
    payload = json.loads(resume.stdout)
    assert payload["shards_skipped_resume"] == 2
    assert payload["status"] == "COMPLETED"


def test_cli_missing_config_field_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    config_path = root / "configs" / "models" / "dense_encoder.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    del raw["selection"]["model_id"]
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    result = run_cli(["encode", "--corpus", "scifact"], cwd=root)
    assert result.returncode == 1
    assert "FAIL" in result.stderr
    assert "model_id" in result.stderr


def test_cli_empty_revision_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root, **{"selection__revision": ""})
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    result = run_cli(["encode", "--corpus", "scifact"], cwd=root)
    assert result.returncode == 1
    assert "revision" in result.stderr


def test_cli_normalize_false_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root, **{"selection__normalize": False})
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    result = run_cli(["encode", "--corpus", "scifact"], cwd=root)
    assert result.returncode == 1
    assert "normalize" in result.stderr


def test_cli_protocol_drift_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root, **{"dense__similarity": "dot"})
    _write_beir_corpus(root, BEIR_DOCS)
    result = run_cli(["encode", "--corpus", "scifact"], cwd=root)
    assert result.returncode == 1
    assert "similarity" in result.stderr


def test_cli_missing_corpus_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    (root / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl").unlink()
    mock_path = tmp_path / "sg019_mock_encoder.py"
    mock_path.write_text(MOCK_ENCODER_MODULE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src") + os.pathsep + str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_mock_encoder:create_encoder",
         "encode", "--corpus", "scifact"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert result.returncode == 1
    assert "FAIL" in result.stderr


def test_cli_missing_embedding_document_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    rows = copy.deepcopy(BEIR_DOCS) + [{"_id": "d_empty", "title": "  ", "text": None, "metadata": {}}]
    _write_beir_corpus(root, rows)
    mock_path = tmp_path / "sg019_mock_encoder.py"
    mock_path.write_text(MOCK_ENCODER_MODULE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src") + os.pathsep + str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_mock_encoder:create_encoder",
         "encode", "--corpus", "scifact"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert result.returncode == 1
    assert "d_empty" in result.stderr
    assert "fail_not_drop_document" in result.stderr
    # Nothing was encoded for the broken corpus.
    assert not list((root / "data" / "manifests" / "encoding_shards").glob("**/shard-*.json"))


def test_cli_resume_config_mismatch_exit_1_without_model(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    mock_path = tmp_path / "sg019_mock_encoder.py"
    mock_path.write_text(MOCK_ENCODER_MODULE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src") + os.pathsep + str(tmp_path)}

    first = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_mock_encoder:create_encoder",
         "encode", "--corpus", "scifact", "--shard-size", "2"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert first.returncode == 0, first.stderr

    # Change max_length: resume must refuse (exit 1) BEFORE any model work,
    # even when the "encoder" module is broken (it must never be imported).
    _write_config(root, **{"selection__max_length": 256})
    broken_path = tmp_path / "sg019_broken_encoder.py"
    broken_path.write_text("raise RuntimeError('must not be imported')\n", encoding="utf-8")
    second = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_broken_encoder:create_encoder",
         "encode", "--corpus", "scifact", "--shard-size", "2"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert second.returncode == 1
    assert "mix configs" in second.stderr


def test_cli_verify_tampered_shard_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root)
    _write_protocol(root)
    _write_beir_corpus(root, BEIR_DOCS)
    mock_path = tmp_path / "sg019_mock_encoder.py"
    mock_path.write_text(MOCK_ENCODER_MODULE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src") + os.pathsep + str(tmp_path)}

    first = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "--encoder-module", "sg019_mock_encoder:create_encoder",
         "encode", "--corpus", "scifact", "--shard-size", "2"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert first.returncode == 0, first.stderr

    config = _load_config(root)
    npy_path = root / "artifacts" / "indexes" / "scifact" / config.namespace / "shards" / "shard-00000.npy"
    payload = bytearray(npy_path.read_bytes())
    payload[-1] ^= 0xFF
    npy_path.write_bytes(bytes(payload))

    result = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.dense", "verify", "--corpus", "scifact"],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=600, check=False,
    )
    assert result.returncode == 1
    assert "Checksum mismatch" in result.stderr


# ---------------------------------------------------------------------------
# Notebook validity
# ---------------------------------------------------------------------------


def test_encode_corpus_notebook_is_valid_nbformat() -> None:
    notebook_path = PROJECT_ROOT / "notebooks" / "encode_corpus.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["scholargraph"]["task_id"] == "SG-019"
    code = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"] if cell.get("cell_type") == "code"
    )
    assert not any(line.lstrip().startswith(("%", "!")) for line in code.splitlines())
    # The notebook must drive the module CLI and estimate remaining time.
    assert "scholargraph.retrieval.dense" in code
    assert "estimate_remaining" in code
    assert "docs_per_second" in code
