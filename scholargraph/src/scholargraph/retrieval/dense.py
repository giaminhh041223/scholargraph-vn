"""Sharded dense encoding and exact nearest-neighbour index — task SG-019.

Contract implemented (docs/TASKS.md SG-019, docs/MODEL_CARD.md §4/§10,
configs/models/dense_encoder.json and ``configs/protocol_v1.json`` ->
``retrieval.dense``):

- **Encoder pin (SG-017):** ``BAAI/bge-base-en-v1.5`` at revision
  ``a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`` (re-verified when weights are
  downloaded: the local snapshot directory name must equal the pinned commit
  and the HF API ``sha`` must match when the network is reachable), CLS
  pooling, L2-normalized float32 vectors, ``max_length=512``, no adapter.
- **Prefix:** documents are encoded **without** any instruction; queries are
  encoded **with** the query-only prefix
  ``"Represent this sentence for searching relevant passages: "`` taken from
  the model config (``prefix_scope="query_only"``).
- **Similarity:** cosine on L2-normalized vectors (so cosine == dot product).
  The module refuses any config whose protocol block deviates from
  ``similarity="cosine"``, ``l2_normalize=true``,
  ``missing_embedding="fail_not_drop_document"``.
- **No silent bypass:** a corpus document whose text (title + abstract under
  the corpus rules) is empty is a hard error naming the document; the CLI
  exits 1. A missing config field, an empty revision, ``normalize != true``
  or a protocol deviation are hard errors, exit 1 (SG-017 review P2-2).
- **Sharding with resume:** documents are ordered by canonical ID ascending;
  shards are contiguous slices of ``shard_size`` documents (default 1000).
  Each completed shard stores ``shard-NNNNN.npy`` under
  ``artifacts/indexes/<corpus>/<namespace>/shards/`` and a manifest
  ``shard-NNNNN.json`` under ``data/manifests/encoding_shards/<corpus>/<namespace>/``
  with the exact doc-ID list, the SHA-256 of the ``.npy`` file, the model and
  tokenizer revisions, the config hash and timing/RAM measurements. A re-run
  skips a shard only when its manifest says ``COMPLETED`` and the checksum,
  doc-ID list and config fields all match. A shard written under a different
  config/model/revision is REFUSED (no config mixing; exit 1). An orphan
  ``.npy`` without a manifest is never trusted and is re-encoded.
- **Namespace:** ``<model_short>__<revision8>`` (COMPUTE_PLAN §7: dataset +
  model revision). Different model revisions get separate directories and can
  never mix. A config change within the same model revision lands in the same
  namespace, where the manifest-level ``config_hash`` check REFUSES to resume
  (exit 1) instead of silently mixing configs. An orphan
  ``.npy`` without a manifest is never trusted and is re-encoded.
- **Exact index (no ANN):** all completed shards are checksum-verified and
  concatenated in doc-ID order into ``embeddings.npy`` plus ``doc_ids.json``
  and an ``index.json`` manifest recording hashes. ``ExactDenseIndex.search``
  returns the deterministic cosine ranking (score descending, doc ID
  ascending on ties). No ANN is used, so no recall audit is applicable.
- **Honest measurements:** throughput, encode seconds, model load time and
  peak process RAM are measured per run; the GPU fields are recorded as
  ``"gpu": "not_measured_local"`` because this machine has no CUDA device.
  Nothing measured is replaced by 0 or fabricated (ADR-013/014).

Leakage boundary: encoding reads only the corpus files pinned by the data
manifests. Qrels and query relevance are never read here. The corpus source
SHA-256 is verified against the frozen manifest before encoding (BEIR) and
recorded in every shard manifest.

CLI example (from the project root):

    PYTHONPATH=src ./.venv/Scripts/python.exe -m scholargraph.retrieval.dense \\
        encode --corpus scifact --batch-size 16

Subcommands: ``encode``, ``index``, ``verify``, ``encode-queries``,
``profile``. Every failure path prints ``FAIL: ...`` to stderr and returns
exit code 1.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from scholargraph.ingest.beir_loader import canonical_beir_id, sha256_file
from scholargraph.ingest.openalex import canonical_openalex_work_id

MODULE_VERSION = "sg019-1.0.0"
SCHEMA_VERSION = 1
SHARD_SIZE_DEFAULT = 1000
BATCH_SIZE_DEFAULT = 16
QUERY_BATCH_SIZE_DEFAULT = 32
SIMILARITY = "cosine"
L2_NORMALIZE_REQUIRED = True
MISSING_EMBEDDING_REQUIRED = "fail_not_drop_document"
POOLING_REQUIRED = "cls"
PREFIX_SCOPE_REQUIRED = "query_only"
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_WORK_ID_RE = re.compile(r"^W\d+$")

CORPUS_SPECS: Mapping[str, Mapping[str, Any]] = {
    "scifact": {
        "kind": "beir",
        "dataset": "scifact",
        "corpus_path": "data/raw/beir/scifact/corpus.jsonl",
        "manifest_path": "data/manifests/beir_scifact.json",
        "text_fields": ("title", "text"),
    },
    "openalex_core": {
        "kind": "openalex",
        "corpus_path": "data/processed/openalex/works.jsonl",
        "manifest_path": "data/manifests/openalex_core.json",
        "text_fields": ("title", "abstract_inverted_index"),
    },
    "openalex_core_text": {
        "kind": "openalex",
        "corpus_path": "data/processed/openalex/works_text.jsonl",
        "manifest_path": "data/manifests/openalex_core_text.json",
        "text_fields": ("title", "abstract_inverted_index"),
    },
    "scidocs": {
        "kind": "beir",
        "dataset": "scidocs",
        "corpus_path": "data/raw/beir/scidocs/corpus.jsonl",
        "manifest_path": "data/manifests/beir_scidocs.json",
        "text_fields": ("title", "text"),
    },
}


class DenseConfigError(ValueError):
    """Raised when the dense encoder config deviates from the required contract."""


class DenseDataError(ValueError):
    """Raised when a mandatory input resource is missing or ill-formed."""


class DenseResumeError(ValueError):
    """Raised when resuming would mix configs or trust an unverifiable shard."""


class DenseEncodingError(ValueError):
    """Raised when produced embeddings violate the contract."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    _atomic_write_bytes(path, text.encode("utf-8"))


def _load_strict_json(path: Path) -> Any:
    """Parse JSON while rejecting duplicate keys and NaN/Infinity constants."""

    if not path.is_file():
        raise DenseDataError(f"Missing JSON file: {path}")

    def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise DenseDataError(f"Duplicate JSON key {key!r} in {path}.")
            seen.add(key)
        return dict(pairs)

    def _reject_constant(name: str) -> Any:
        raise DenseDataError(f"Non-finite JSON constant {name!r} in {path}.")

    with path.open("r", encoding="utf-8") as handle:
        try:
            return json.load(handle, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
        except json.JSONDecodeError as exc:
            raise DenseDataError(f"Invalid JSON in {path}: {exc.msg}") from exc


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DenseDataError(f"Missing corpus JSONL file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise DenseDataError(f"Blank line in {path} at line {line_number}.")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DenseDataError(f"Invalid JSON in {path} at line {line_number}: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise DenseDataError(f"JSONL row in {path} at line {line_number} is not an object.")
            rows.append(row)
    return rows


def _peak_rss_bytes() -> int | None:
    """Best-effort peak process RSS in bytes; ``None`` only if the OS API fails."""

    if sys.platform.startswith("win"):
        try:

            class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_uint32),
                    ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            psapi = ctypes.WinDLL("psapi.dll", use_last_error=True)  # type: ignore[attr-defined]
            kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)  # type: ignore[attr-defined]
            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            # The current-process pseudo-handle is rejected in some sandboxed
            # environments (GetProcessMemoryInfo fails with ERROR_INVALID_HANDLE),
            # so open a real handle to our own PID first.
            process_query_information = 0x0400
            process_vm_read = 0x0010
            handle = kernel32.OpenProcess(
                process_query_information | process_vm_read, False, os.getpid()
            )
            if not handle:
                return None
            try:
                if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return None
            finally:
                kernel32.CloseHandle(handle)
            return int(counters.PeakWorkingSetSize)
        except Exception:  # noqa: BLE001 - measurement must not break encoding
            return None
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Config loading (fail-loud per SG-017 review P2-2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DenseConfig:
    """Validated, immutable view of ``configs/models/dense_encoder.json``."""

    config_id: str
    model_id: str
    revision: str
    pooling: str
    normalize: bool
    max_length: int
    prefix: str
    prefix_scope: str
    embedding_dimension: int
    license: str
    similarity: str
    l2_normalize: bool
    missing_embedding: str
    selection_gate: str
    config_sha256: str
    config_hash: str

    @property
    def namespace(self) -> str:
        # COMPUTE_PLAN §7: shards are namespaced by dataset and model revision.
        # The config hash is NOT part of the namespace on purpose: a changed
        # config within the same model revision must hit the existing manifests
        # and be REFUSED on resume (no config mixing) instead of silently
        # branching into a parallel directory tree.
        model_short = self.model_id.split("/")[-1]
        return f"{model_short}__{self.revision[:8]}"


def load_dense_encoder_config(
    config_path: Path | str,
    protocol_path: Path | str,
) -> DenseConfig:
    """Load and strictly validate the pinned dense encoder config.

    Every deviation is a :class:`DenseConfigError` (CLI exit 1): a missing
    mandatory field, an empty/non-sha revision, ``normalize != true``, a
    prefix scope other than ``query_only``, or a protocol block that does not
    match ``retrieval.dense`` of the protocol file.
    """

    config_path = Path(config_path)
    protocol_path = Path(protocol_path)
    raw = _load_strict_json(config_path)
    if not isinstance(raw, Mapping):
        raise DenseConfigError(f"Dense encoder config {config_path} must be a JSON object.")

    selection = raw.get("selection")
    if not isinstance(selection, Mapping):
        raise DenseConfigError(f"Config {config_path} lacks the mandatory 'selection' object.")

    protocol_reference = raw.get("protocol_reference")
    if not isinstance(protocol_reference, Mapping):
        raise DenseConfigError(f"Config {config_path} lacks the mandatory 'protocol_reference' object.")

    def _required(selection_key: str, context: str) -> Any:
        if selection_key not in selection:
            raise DenseConfigError(f"Config {config_path} is missing mandatory field 'selection.{selection_key}'.")
        return selection[selection_key]

    model_id = _required("model_id", "model_id")
    revision = _required("revision", "revision")
    pooling = _required("pooling", "pooling")
    normalize = _required("normalize", "normalize")
    max_length = _required("max_length", "max_length")
    prefix = _required("prefix", "prefix")
    prefix_scope = _required("prefix_scope", "prefix_scope")
    embedding_dimension = _required("embedding_dimension", "embedding_dimension")
    license_name = _required("license", "license")

    if not isinstance(model_id, str) or not model_id.strip():
        raise DenseConfigError(f"'selection.model_id' must be a non-empty string, got {model_id!r}.")
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision.strip().lower()):
        raise DenseConfigError(
            f"'selection.revision' must be a 40-character hex commit SHA, got {revision!r}."
        )
    if pooling != POOLING_REQUIRED:
        raise DenseConfigError(
            f"'selection.pooling' must be {POOLING_REQUIRED!r} for the pinned encoder, got {pooling!r}."
        )
    if normalize is not L2_NORMALIZE_REQUIRED:
        raise DenseConfigError(
            f"'selection.normalize' must be boolean true (protocol l2_normalize), got {normalize!r}."
        )
    if not isinstance(max_length, int) or isinstance(max_length, bool) or max_length <= 0:
        raise DenseConfigError(f"'selection.max_length' must be a positive integer, got {max_length!r}.")
    if not isinstance(prefix, str):
        raise DenseConfigError(f"'selection.prefix' must be a string (query-only instruction), got {prefix!r}.")
    if prefix_scope != PREFIX_SCOPE_REQUIRED:
        raise DenseConfigError(
            f"'selection.prefix_scope' must be {PREFIX_SCOPE_REQUIRED!r} (documents must not be prefixed), "
            f"got {prefix_scope!r}."
        )
    if not isinstance(embedding_dimension, int) or isinstance(embedding_dimension, bool) or embedding_dimension <= 0:
        raise DenseConfigError(f"'selection.embedding_dimension' must be a positive integer, got {embedding_dimension!r}.")
    if not isinstance(license_name, str) or not license_name.strip():
        raise DenseConfigError(f"'selection.license' must be a non-empty string, got {license_name!r}.")

    similarity = protocol_reference.get("similarity")
    l2_normalize = protocol_reference.get("l2_normalize")
    missing_embedding = protocol_reference.get("missing_embedding")
    if similarity != SIMILARITY:
        raise DenseConfigError(
            f"'protocol_reference.similarity' must be {SIMILARITY!r}, got {similarity!r}."
        )
    if l2_normalize is not True:
        raise DenseConfigError(
            f"'protocol_reference.l2_normalize' must be boolean true, got {l2_normalize!r}."
        )
    if missing_embedding != MISSING_EMBEDDING_REQUIRED:
        raise DenseConfigError(
            f"'protocol_reference.missing_embedding' must be {MISSING_EMBEDDING_REQUIRED!r}, "
            f"got {missing_embedding!r}."
        )
    selection_gate = protocol_reference.get("selection_gate")
    if not isinstance(selection_gate, str) or not selection_gate.strip():
        raise DenseConfigError(
            f"'protocol_reference.selection_gate' must be a non-empty string, got {selection_gate!r}."
        )

    # Cross-check the pinned protocol file: the config must not drift from it.
    protocol = _load_strict_json(protocol_path)
    dense_block = protocol.get("retrieval", {}).get("dense") if isinstance(protocol, Mapping) else None
    if not isinstance(dense_block, Mapping):
        raise DenseConfigError(f"Protocol file {protocol_path} lacks the 'retrieval.dense' block.")
    if dense_block.get("similarity") != similarity:
        raise DenseConfigError(
            f"Protocol similarity {dense_block.get('similarity')!r} does not match config {similarity!r}."
        )
    if dense_block.get("l2_normalize") is not l2_normalize:
        raise DenseConfigError(
            f"Protocol l2_normalize {dense_block.get('l2_normalize')!r} does not match config {l2_normalize!r}."
        )
    if dense_block.get("missing_embedding") != missing_embedding:
        raise DenseConfigError(
            f"Protocol missing_embedding {dense_block.get('missing_embedding')!r} does not match config "
            f"{missing_embedding!r}."
        )

    config_id = raw.get("config_id")
    if not isinstance(config_id, str) or not config_id.strip():
        raise DenseConfigError(f"Config {config_path} lacks a non-empty 'config_id'.")

    # Hash over the exact validated contract; recorded in every shard manifest
    # so a resume can detect any config change deterministically.
    canonical = {
        "config_id": config_id,
        "model_id": model_id.strip(),
        "revision": revision.strip().lower(),
        "pooling": pooling,
        "normalize": normalize,
        "max_length": max_length,
        "prefix": prefix,
        "prefix_scope": prefix_scope,
        "embedding_dimension": embedding_dimension,
        "license": license_name,
        "similarity": similarity,
        "l2_normalize": l2_normalize,
        "missing_embedding": missing_embedding,
        "selection_gate": selection_gate,
        "module_version": MODULE_VERSION,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return DenseConfig(
        config_id=config_id,
        model_id=model_id.strip(),
        revision=revision.strip().lower(),
        pooling=pooling,
        normalize=normalize,
        max_length=max_length,
        prefix=prefix,
        prefix_scope=prefix_scope,
        embedding_dimension=embedding_dimension,
        license=license_name,
        similarity=similarity,
        l2_normalize=l2_normalize,
        missing_embedding=missing_embedding,
        selection_gate=selection_gate,
        config_sha256=_sha256_bytes(Path(config_path).read_bytes()),
        config_hash=hashlib.sha256(payload).hexdigest(),
    )


def apply_query_prefix(texts: Sequence[str], prefix: str) -> list[str]:
    """Apply the query-only instruction to every query text (documents never)."""

    return [f"{prefix}{text}" for text in texts]


# ---------------------------------------------------------------------------
# Corpus reading (documents only; qrels never touched)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusDocs:
    """Documents of one corpus in canonical ID ascending order."""

    corpus_id: str
    doc_ids: tuple[str, ...]
    texts: tuple[str, ...]
    source_path: Path
    source_sha256: str
    manifest_path: Path
    expected_count: int
    missing_title_count: int
    missing_abstract_count: int


def _beir_document_text(row: Mapping[str, Any], raw_id: str, path: Path, line_number: int) -> tuple[str, bool, bool]:
    title = row.get("title")
    text = row.get("text")
    if title is not None and not isinstance(title, str):
        raise DenseDataError(f"Corpus row '{raw_id}' in {path} at line {line_number} has a non-string title.")
    if text is not None and not isinstance(text, str):
        raise DenseDataError(f"Corpus row '{raw_id}' in {path} at line {line_number} has a non-string text.")
    title_str = (title or "").strip()
    text_str = (text or "").strip()
    missing_title = not title_str
    missing_abstract = not text_str
    combined = " ".join(part for part in (title_str, text_str) if part)
    if not combined:
        # missing_embedding=fail_not_drop_document: a document with no text at
        # all can never receive an embedding, so this is a hard failure.
        raise DenseDataError(
            f"missing_embedding=fail_not_drop_document: corpus row '{raw_id}' in {path} at line "
            f"{line_number} has neither title nor text; encoding would silently drop it."
        )
    return combined, missing_title, missing_abstract


def _openalex_document_text(
    row: Mapping[str, Any], doc_id: str, path: Path, line_number: int
) -> tuple[str, bool, bool]:
    title = row.get("title")
    if title is not None and not isinstance(title, str):
        raise DenseDataError(f"Work '{doc_id}' in {path} at line {line_number} has a non-string title.")
    title_str = (title or "").strip()
    inverted = row.get("abstract_inverted_index")
    abstract_str = ""
    if inverted is not None:
        if not isinstance(inverted, Mapping):
            raise DenseDataError(
                f"Work '{doc_id}' in {path} at line {line_number} has a non-object 'abstract_inverted_index'."
            )
        positions: list[tuple[int, str]] = []
        for word, word_positions in inverted.items():
            if not isinstance(word_positions, list) or not word_positions:
                raise DenseDataError(
                    f"Work '{doc_id}' in {path} at line {line_number} has an invalid inverted-index entry "
                    f"for word {word!r}."
                )
            for position in word_positions:
                if not isinstance(position, int) or isinstance(position, bool) or position < 0:
                    raise DenseDataError(
                        f"Work '{doc_id}' in {path} at line {line_number} has an invalid position {position!r} "
                        f"for word {word!r}."
                    )
                positions.append((position, str(word)))
        positions.sort(key=lambda item: item[0])
        for index in range(1, len(positions)):
            if positions[index][0] == positions[index - 1][0]:
                raise DenseDataError(
                    f"Work '{doc_id}' in {path} at line {line_number} has two words sharing abstract position "
                    f"{positions[index][0]}."
                )
        abstract_str = " ".join(word for _, word in positions)
    missing_title = not title_str
    missing_abstract = not abstract_str
    combined = " ".join(part for part in (title_str, abstract_str) if part)
    if not combined:
        raise DenseDataError(
            f"missing_embedding=fail_not_drop_document: work '{doc_id}' in {path} at line {line_number} has "
            "neither title nor abstract; encoding would silently drop it."
        )
    return combined, missing_title, missing_abstract


def _read_beir_corpus(corpus_id: str, spec: Mapping[str, Any], project_root: Path) -> CorpusDocs:
    corpus_path = project_root / spec["corpus_path"]
    manifest_path = project_root / spec["manifest_path"]
    dataset = spec["dataset"]

    if not corpus_path.is_file():
        raise DenseDataError(f"Missing corpus JSONL file: {corpus_path}")
    manifest = _load_strict_json(manifest_path)
    pinned_sha256 = (
        manifest.get("storage", {}).get("files", {}).get("corpus.jsonl")
        if isinstance(manifest, Mapping)
        else None
    )
    if not isinstance(pinned_sha256, str) or not pinned_sha256.strip():
        raise DenseDataError(f"Manifest {manifest_path} does not pin a sha256 for corpus.jsonl.")
    actual_sha256 = sha256_file(corpus_path)
    if actual_sha256 != pinned_sha256.strip().lower():
        raise DenseDataError(
            f"Corpus sha256 mismatch for {corpus_path}: manifest pins {pinned_sha256}, file hashes {actual_sha256}."
        )

    pinned_count = manifest.get("counts", {}).get("corpus") if isinstance(manifest, Mapping) else None
    if not isinstance(pinned_count, int) or pinned_count <= 0:
        raise DenseDataError(f"Manifest {manifest_path} lacks a positive integer counts.corpus.")

    docs: dict[str, str] = {}
    missing_title = 0
    missing_abstract = 0
    for line_number, row in enumerate(_read_jsonl_rows(corpus_path), start=1):
        raw_id = row.get("_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise DenseDataError(f"Missing or empty '_id' in {corpus_path} at line {line_number}.")
        canonical_id = canonical_beir_id(dataset, raw_id)
        if canonical_id in docs:
            raise DenseDataError(f"Duplicate corpus ID '{raw_id}' in {corpus_path} at line {line_number}.")
        text, miss_title, miss_abstract = _beir_document_text(row, raw_id, corpus_path, line_number)
        docs[canonical_id] = text
        missing_title += int(miss_title)
        missing_abstract += int(miss_abstract)

    if len(docs) != pinned_count:
        raise DenseDataError(
            f"Corpus {corpus_path} has {len(docs)} documents but manifest {manifest_path} pins {pinned_count}."
        )
    ordered_ids = tuple(sorted(docs))
    return CorpusDocs(
        corpus_id=corpus_id,
        doc_ids=ordered_ids,
        texts=tuple(docs[doc_id] for doc_id in ordered_ids),
        source_path=corpus_path,
        source_sha256=actual_sha256,
        manifest_path=manifest_path,
        expected_count=pinned_count,
        missing_title_count=missing_title,
        missing_abstract_count=missing_abstract,
    )


def _read_openalex_corpus(corpus_id: str, spec: Mapping[str, Any], project_root: Path) -> CorpusDocs:
    corpus_path = project_root / spec["corpus_path"]
    manifest_path = project_root / spec["manifest_path"]

    if not corpus_path.is_file():
        raise DenseDataError(f"Missing corpus JSONL file: {corpus_path}")
    manifest = _load_strict_json(manifest_path)
    postprocess = manifest.get("postprocess") if isinstance(manifest, Mapping) else None
    if not isinstance(postprocess, Mapping) or postprocess.get("processed_works") is None:
        raise DenseDataError(f"Manifest {manifest_path} lacks 'postprocess.processed_works'.")
    pinned_count = postprocess["processed_works"]
    if not isinstance(pinned_count, int) or pinned_count <= 0:
        raise DenseDataError(f"Manifest {manifest_path} pins a non-positive processed_works count.")
    if postprocess.get("output_order") != "canonical ID ascending":
        raise DenseDataError(
            f"Manifest {manifest_path} does not pin canonical-ID-ascending order; refusing to assume an order."
        )
    artifacts = manifest.get("artifacts") if isinstance(manifest, Mapping) else None
    works_artifact = artifacts.get("works_jsonl") if isinstance(artifacts, Mapping) else None
    pinned_sha256: str | None = None
    if isinstance(works_artifact, Mapping):
        recorded_path = works_artifact.get("path")
        if recorded_path is not None and Path(recorded_path) != Path(spec["corpus_path"]):
            raise DenseDataError(
                f"Manifest {manifest_path} artifact 'works_jsonl' points at {recorded_path!r}, expected "
                f"{spec['corpus_path']!r}."
            )
        pinned_value = works_artifact.get("sha256")
        if isinstance(pinned_value, str) and pinned_value.strip():
            pinned_sha256 = pinned_value.strip().lower()
    if pinned_sha256 is None:
        raise DenseDataError(
            f"Manifest {manifest_path} does not pin a sha256 for {spec['corpus_path']}; "
            "a missing input hash is never acceptable."
        )

    actual_sha256 = sha256_file(corpus_path)
    if actual_sha256 != pinned_sha256:
        raise DenseDataError(
            f"Corpus sha256 mismatch for {corpus_path}: manifest pins {pinned_sha256}, file hashes {actual_sha256}."
        )

    docs: dict[str, str] = {}
    missing_title = 0
    missing_abstract = 0
    for line_number, row in enumerate(_read_jsonl_rows(corpus_path), start=1):
        raw_id_value = row.get("id")
        if not isinstance(raw_id_value, str) or not raw_id_value.strip():
            raise DenseDataError(f"Missing or empty 'id' in {corpus_path} at line {line_number}.")
        try:
            canonical_id = canonical_openalex_work_id(raw_id_value)
        except ValueError as exc:
            raise DenseDataError(f"{corpus_path} at line {line_number}: {exc}") from exc
        if canonical_id in docs:
            raise DenseDataError(f"Duplicate work ID '{canonical_id}' in {corpus_path} at line {line_number}.")
        text, miss_title, miss_abstract = _openalex_document_text(row, canonical_id, corpus_path, line_number)
        docs[canonical_id] = text
        missing_title += int(miss_title)
        missing_abstract += int(miss_abstract)

    if len(docs) != pinned_count:
        raise DenseDataError(
            f"Corpus {corpus_path} has {len(docs)} documents but manifest {manifest_path} pins {pinned_count}."
        )
    ordered_ids = tuple(sorted(docs))
    return CorpusDocs(
        corpus_id=corpus_id,
        doc_ids=ordered_ids,
        texts=tuple(docs[doc_id] for doc_id in ordered_ids),
        source_path=corpus_path,
        source_sha256=actual_sha256,
        manifest_path=manifest_path,
        expected_count=pinned_count,
        missing_title_count=missing_title,
        missing_abstract_count=missing_abstract,
    )


def read_corpus(corpus_id: str, project_root: Path | str) -> CorpusDocs:
    """Read and verify one pinned corpus; documents ordered by canonical ID."""

    if corpus_id not in CORPUS_SPECS:
        raise DenseDataError(f"Unknown corpus '{corpus_id}'. Known corpora: {sorted(CORPUS_SPECS)}.")
    spec = CORPUS_SPECS[corpus_id]
    project_root = Path(project_root)
    if spec["kind"] == "beir":
        return _read_beir_corpus(corpus_id, spec, project_root)
    return _read_openalex_corpus(corpus_id, spec, project_root)


# ---------------------------------------------------------------------------
# Encoder interface
# ---------------------------------------------------------------------------


class Encoder:
    """Duck-typed encoder used by the shard runner.

    Implementations must expose the pinned attributes and:
    - ``encode(texts) -> np.ndarray`` float32 of shape ``(len(texts), dim)``,
      L2-normalized rows, finite values;
    - ``token_lengths(texts) -> list[int]`` with special tokens included.
    """

    model_id: str
    model_revision: str
    tokenizer_revision: str
    embedding_dimension: int
    max_length: int
    pooling: str
    device: str
    impl_name: str

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError

    def token_lengths(self, texts: Sequence[str]) -> list[int]:  # pragma: no cover - interface
        raise NotImplementedError


def validate_embeddings(matrix: np.ndarray, expected_rows: int, dimension: int, l2_normalized: bool) -> None:
    if not isinstance(matrix, np.ndarray) or matrix.dtype != np.float32:
        raise DenseEncodingError(f"Embeddings must be a float32 numpy array, got {type(matrix)} {getattr(matrix, 'dtype', None)}.")
    if matrix.ndim != 2 or matrix.shape != (expected_rows, dimension):
        raise DenseEncodingError(
            f"Embeddings shape {matrix.shape} does not match expected {(expected_rows, dimension)}."
        )
    if not np.isfinite(matrix).all():
        raise DenseEncodingError("Embeddings contain non-finite values.")
    if l2_normalized:
        norms = np.linalg.norm(matrix, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-3):
            raise DenseEncodingError(
                f"Embeddings are not L2-normalized within 1e-3: min norm {norms.min():.6f}, max {norms.max():.6f}."
            )


class HfLocalEncoder:
    """Transformers encoder over a local, revision-verified model snapshot.

    torch/transformers are imported lazily so the module stays importable for
    offline tests that inject a mock encoder instead.
    """

    def __init__(
        self,
        *,
        snapshot_dir: Path,
        config: DenseConfig,
        device: str = "cpu",
        num_threads: int | None = None,
        encode_batch_size: int = 32,
    ) -> None:
        import torch  # local import: heavy dependency only needed for real encoding
        from transformers import AutoModel, AutoTokenizer

        if not snapshot_dir.is_dir():
            raise DenseDataError(f"Model snapshot directory does not exist: {snapshot_dir}")
        if encode_batch_size <= 0:
            raise DenseDataError(f"encode_batch_size must be positive, got {encode_batch_size}.")
        self._torch = torch
        self.snapshot_dir = Path(snapshot_dir)
        self.model_id = config.model_id
        self.model_revision = config.revision
        self.tokenizer_revision = config.revision
        self.embedding_dimension = config.embedding_dimension
        self.max_length = config.max_length
        self.pooling = config.pooling
        self.device = device
        self.impl_name = "transformers.AutoModel"
        self.encode_batch_size = encode_batch_size

        if num_threads is not None and num_threads > 0:
            torch.set_num_threads(num_threads)
        self._tokenizer = AutoTokenizer.from_pretrained(str(snapshot_dir), local_files_only=True)
        self._model = AutoModel.from_pretrained(str(snapshot_dir), local_files_only=True)
        self._model.to(device)
        self._model.eval()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        torch = self._torch
        output = np.empty((len(texts), self.embedding_dimension), dtype=np.float32)
        with torch.inference_mode():
            for start in range(0, len(texts), self.encode_batch_size):
                batch = list(texts[start : start + self.encode_batch_size])
                if any(not isinstance(text, str) or not text.strip() for text in batch):
                    raise DenseEncodingError("Encountered an empty or non-string text inside the encode batch.")
                encoded = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                hidden = self._model(**encoded).last_hidden_state
                cls = hidden[:, 0]
                if self.pooling != "cls":
                    raise DenseEncodingError(f"Unsupported pooling {self.pooling!r} in HfLocalEncoder.")
                normalized = torch.nn.functional.normalize(cls, p=2, dim=1)
                output[start : start + len(batch)] = (
                    normalized.to(torch.float32).cpu().numpy().astype(np.float32, copy=False)
                )
        return output

    def token_lengths(self, texts: Sequence[str]) -> list[int]:
        lengths: list[int] = []
        batch_size = 256
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            encoded = self._tokenizer(batch, padding=False, truncation=False, add_special_tokens=True)
            lengths.extend(len(ids) for ids in encoded["input_ids"])
        return lengths


def _env_batch_size(default: int) -> int:
    raw = os.environ.get("SCHOLARGRAPH_BATCH_SIZE")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise DenseDataError(f"SCHOLARGRAPH_BATCH_SIZE must be an integer, got {raw!r}.") from exc
    if value <= 0:
        raise DenseDataError(f"SCHOLARGRAPH_BATCH_SIZE must be positive, got {value}.")
    return value


# ---------------------------------------------------------------------------
# Model snapshot download + revision re-verification (SG-017 review)
# ---------------------------------------------------------------------------


def model_cache_dir(project_root: Path) -> Path:
    return Path(project_root) / "artifacts" / "cache"


def verify_model_snapshot(
    project_root: Path | str,
    config: DenseConfig,
    *,
    verify_remote: bool = True,
) -> dict[str, Any]:
    """Download (or reuse) the pinned snapshot and re-verify the revision.

    Returns the verification record stored into run summaries and profiles:
    snapshot path, snapshot commit, file hashes, tokenizer file presence and
    whether the remote HF API sha matched.
    """

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - environment error
        raise DenseDataError(
            "huggingface_hub is not installed; install transformers (it pulls huggingface_hub) to encode."
        ) from exc

    cache_dir = model_cache_dir(project_root)
    allow_patterns = [
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
        "special_tokens_map.json",
        "added_tokens.json",
        "1_Pooling/*",
        "sentence_bert_config.json",
        "modules.json",
    ]
    snapshot_path = Path(
        snapshot_download(
            repo_id=config.model_id,
            revision=config.revision,
            cache_dir=str(cache_dir),
            allow_patterns=allow_patterns,
        )
    )
    # The snapshot directory inside the hub cache is named by the resolved
    # commit SHA. Requesting a pinned sha must resolve to exactly that commit;
    # anything else means the pin did not hold and this run must not proceed.
    if snapshot_path.name != config.revision:
        raise DenseDataError(
            f"Snapshot directory {snapshot_path.name!r} does not equal the pinned revision "
            f"{config.revision!r}; refusing to encode with an unverified revision."
        )

    required_files = (
        "config.json",
        "tokenizer_config.json",
        "vocab.txt",
    )
    missing = [name for name in required_files if not (snapshot_path / name).is_file()]
    if missing:
        raise DenseDataError(f"Snapshot {snapshot_path} is missing tokenizer/model files: {missing}.")
    tokenizer_files = [
        name
        for name in ("tokenizer.json", "tokenizer_config.json", "vocab.txt", "special_tokens_map.json", "added_tokens.json")
        if (snapshot_path / name).is_file()
    ]
    if not tokenizer_files:
        raise DenseDataError(f"Snapshot {snapshot_path} contains no tokenizer files at all.")

    weights_file: str | None = None
    for candidate in ("model.safetensors", "pytorch_model.bin"):
        if (snapshot_path / candidate).is_file():
            weights_file = candidate
            break
    if weights_file is None:
        raise DenseDataError(f"Snapshot {snapshot_path} contains no model weights file.")

    files_block: dict[str, Any] = {}
    for item in sorted(snapshot_path.iterdir()):
        if item.is_file():
            files_block[item.name] = sha256_file(item)

    remote_status = "not_attempted"
    remote_sha: str | None = None
    if verify_remote:
        try:
            from huggingface_hub import HfApi

            info = HfApi().model_info(config.model_id, revision=config.revision, timeout=30)
            remote_sha = getattr(info, "sha", None)
            remote_status = "match" if remote_sha == config.revision else "mismatch"
            if remote_status == "mismatch":
                raise DenseDataError(
                    f"HF API sha {remote_sha!r} does not match pinned revision {config.revision!r}."
                )
        except DenseDataError:
            raise
        except Exception as exc:  # noqa: BLE001 - offline runs still verify locally by snapshot commit
            remote_status = f"skipped_remote_unavailable: {type(exc).__name__}: {exc}"

    return {
        "snapshot_path": str(snapshot_path),
        "snapshot_commit": snapshot_path.name,
        "weights_file": weights_file,
        "tokenizer_files_present": tokenizer_files,
        "files_sha256": files_block,
        "remote_api_sha_verification": remote_status,
        "remote_api_sha": remote_sha,
        "verified_at": _now_iso(),
    }


def _snapshot_dir_from_record(record: Mapping[str, Any]) -> Path:
    path = record.get("snapshot_path")
    if not isinstance(path, str) or not path.strip():
        raise DenseDataError("Snapshot verification record lacks 'snapshot_path'.")
    return Path(path)


# ---------------------------------------------------------------------------
# Shard planning, manifests and resume
# ---------------------------------------------------------------------------


def shard_layout(project_root: Path, corpus_id: str, namespace: str) -> tuple[Path, Path]:
    """Return (npy directory, manifest directory) for one corpus namespace."""

    root = Path(project_root)
    npy_dir = root / "artifacts" / "indexes" / corpus_id / namespace / "shards"
    manifest_dir = root / "data" / "manifests" / "encoding_shards" / corpus_id / namespace
    return npy_dir, manifest_dir


def plan_shards(doc_count: int, shard_size: int) -> list[tuple[int, int]]:
    if shard_size <= 0:
        raise DenseDataError(f"shard_size must be positive, got {shard_size}.")
    return [(start, min(start + shard_size, doc_count)) for start in range(0, doc_count, shard_size)]


def shard_name(index: int) -> str:
    return f"shard-{index:05d}"


def _shard_manifest_payload(
    *,
    corpus: CorpusDocs,
    config: DenseConfig,
    namespace: str,
    shard_index: int,
    shard_start: int,
    shard_end: int,
    npy_rel_path: str,
    npy_sha256: str,
    matrix: np.ndarray,
    encoder: Encoder,
    batch_size: int,
    encode_seconds: float,
    started_at: str,
    finished_at: str,
    peak_rss: int | None,
    reordered_within_shard: bool,
) -> dict[str, Any]:
    doc_ids = list(corpus.doc_ids[shard_start:shard_end])
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "dense_embedding_shard",
        "module_version": MODULE_VERSION,
        "corpus_id": corpus.corpus_id,
        "namespace": namespace,
        "shard_name": shard_name(shard_index),
        "shard_index": shard_index,
        "doc_ids": doc_ids,
        "doc_count": len(doc_ids),
        "doc_id_first": doc_ids[0],
        "doc_id_last": doc_ids[-1],
        "embeddings": {
            "path": npy_rel_path,
            "sha256": npy_sha256,
            "dtype": "float32",
            "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        },
        "model": {
            "id": encoder.model_id,
            "revision": encoder.model_revision,
            "tokenizer_revision": encoder.tokenizer_revision,
            "pooling": encoder.pooling,
            "embedding_dimension": int(matrix.shape[1]),
        },
        "encoding": {
            "max_length": config.max_length,
            "l2_normalized": config.l2_normalize,
            "similarity": config.similarity,
            "missing_embedding": config.missing_embedding,
            "document_prefix": "",
            "prefix_scope": config.prefix_scope,
            "batch_size": int(batch_size),
            "device": encoder.device,
            "encoder_impl": encoder.impl_name,
            "sorted_by_length_within_shard": bool(reordered_within_shard),
        },
        "config_hash": config.config_hash,
        "corpus": {
            "source_path": str(corpus.source_path),
            "source_sha256": corpus.source_sha256,
            "manifest_path": str(corpus.manifest_path),
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "encode_seconds": round(float(encode_seconds), 6),
            "docs_per_second": (
                round(len(doc_ids) / float(encode_seconds), 4) if encode_seconds > 0 else None
            ),
        },
        "ram": {
            "peak_rss_bytes": int(peak_rss) if peak_rss is not None else None,
            "measurement": "process peak working set (Windows psapi) or ru_maxrss" if peak_rss is not None else "unavailable_on_platform",
        },
        "status": "COMPLETED",
    }


def inspect_shard(
    *,
    project_root: Path,
    corpus: CorpusDocs,
    config: DenseConfig,
    namespace: str,
    shard_index: int,
    shard_start: int,
    shard_end: int,
    encoder: Encoder | None,
) -> tuple[str, dict[str, Any] | None]:
    """Classify one shard for resume: ``absent``, ``completed`` or ``orphan``.

    ``completed`` requires the manifest to say COMPLETED and to match every
    pinned field including the ``.npy`` checksum; any deviation raises
    :class:`DenseResumeError` (refuse to mix configs). All pins except the
    tokenizer revision are checked from the config and corpus alone, so a
    pure-resume run (no encoder) still rejects foreign revisions and models.
    An orphan ``.npy`` without a manifest is reported for re-encoding, never
    trusted.
    """

    npy_dir, manifest_dir = shard_layout(project_root, corpus.corpus_id, namespace)
    name = shard_name(shard_index)
    manifest_path = manifest_dir / f"{name}.json"
    npy_path = npy_dir / f"{name}.npy"
    manifest_exists = manifest_path.is_file()
    npy_exists = npy_path.is_file()
    if not manifest_exists and not npy_exists:
        return "absent", None
    if not manifest_exists and npy_exists:
        return "orphan", None
    manifest = _load_strict_json(manifest_path)
    if manifest.get("status") != "COMPLETED":
        raise DenseResumeError(
            f"Shard manifest {manifest_path} exists with status {manifest.get('status')!r} instead of "
            "COMPLETED; refusing to resume from unknown state."
        )
    manifest_model = manifest.get("model")
    manifest_encoding = manifest.get("encoding")
    manifest_corpus = manifest.get("corpus")
    if not all(isinstance(block, Mapping) for block in (manifest_model, manifest_encoding, manifest_corpus)):
        raise DenseResumeError(
            f"Shard manifest {manifest_path} lacks the 'model'/'encoding'/'corpus' blocks."
        )
    expected: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "corpus_id": corpus.corpus_id,
        "namespace": namespace,
        "shard_name": name,
        "config_hash": config.config_hash,
        "doc_ids": list(corpus.doc_ids[shard_start:shard_end]),
        # Model pins from the config: verified even without an encoder.
        "model_id": config.model_id,
        "model_revision": config.revision,
        "pooling": config.pooling,
        "max_length": config.max_length,
        "embedding_dimension": config.embedding_dimension,
        "l2_normalized": config.l2_normalize,
        "source_sha256": corpus.source_sha256,
    }
    if encoder is not None:
        expected["tokenizer_revision"] = encoder.tokenizer_revision
        expected["device"] = encoder.device
    actual: dict[str, Any] = {
        "schema_version": manifest.get("schema_version"),
        "corpus_id": manifest.get("corpus_id"),
        "namespace": manifest.get("namespace"),
        "shard_name": manifest.get("shard_name"),
        "config_hash": manifest.get("config_hash"),
        "doc_ids": manifest.get("doc_ids"),
        "model_id": manifest_model.get("id"),
        "model_revision": manifest_model.get("revision"),
        "pooling": manifest_model.get("pooling"),
        "max_length": manifest_encoding.get("max_length"),
        "embedding_dimension": manifest_model.get("embedding_dimension"),
        "l2_normalized": manifest_encoding.get("l2_normalized"),
        "source_sha256": manifest_corpus.get("source_sha256"),
    }
    if encoder is not None:
        actual["tokenizer_revision"] = manifest_model.get("tokenizer_revision")
        actual["device"] = manifest_encoding.get("device")
    for key in expected:
        if actual.get(key) != expected[key]:
            raise DenseResumeError(
                f"Shard manifest {manifest_path} has {key}={actual.get(key)!r} but this run pins "
                f"{expected[key]!r}; refusing to mix configs (no silent resume across config changes)."
            )
    if not npy_exists:
        raise DenseResumeError(
            f"Shard manifest {manifest_path} says COMPLETED but {npy_path} is missing; refusing to continue."
        )
    embeddings_block = manifest.get("embeddings")
    if not isinstance(embeddings_block, Mapping):
        raise DenseResumeError(f"Shard manifest {manifest_path} lacks the 'embeddings' block.")
    doc_count = manifest.get("doc_count")
    dimension = manifest_model.get("embedding_dimension")
    if not isinstance(doc_count, int) or not isinstance(dimension, int):
        raise DenseResumeError(f"Shard manifest {manifest_path} lacks integer doc_count/embedding_dimension.")
    actual_sha = sha256_file(npy_path)
    if actual_sha != embeddings_block.get("sha256"):
        raise DenseResumeError(
            f"Checksum mismatch for {npy_path}: manifest pins {embeddings_block.get('sha256')!r}, file hashes "
            f"{actual_sha!r}; refusing to reuse a corrupted shard."
        )
    matrix = np.load(npy_path, allow_pickle=False)
    if matrix.dtype != np.float32 or matrix.shape != (doc_count, dimension):
        raise DenseResumeError(
            f"Shard {npy_path} has dtype/shape {matrix.dtype}/{matrix.shape}, manifest pins float32/"
            f"({doc_count}, {dimension})."
        )
    return "completed", manifest


def _encode_one_shard(
    *,
    project_root: Path,
    corpus: CorpusDocs,
    config: DenseConfig,
    namespace: str,
    shard_index: int,
    shard_start: int,
    shard_end: int,
    encoder: Encoder,
    batch_size: int,
) -> dict[str, Any]:
    npy_dir, manifest_dir = shard_layout(project_root, corpus.corpus_id, namespace)
    npy_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    name = shard_name(shard_index)
    npy_path = npy_dir / f"{name}.npy"
    manifest_path = manifest_dir / f"{name}.json"

    doc_ids = corpus.doc_ids[shard_start:shard_end]
    texts = corpus.texts[shard_start:shard_end]

    started_at = _now_iso()
    started_clock = time.perf_counter()
    order: list[int] | None = None
    reordered = False
    try:
        lengths = encoder.token_lengths(texts)
        if lengths is not None and len(lengths) == len(texts):
            order = sorted(range(len(texts)), key=lambda i: (lengths[i], i))
            reordered = True
    except (AttributeError, NotImplementedError):
        order = None
    if order is not None:
        encode_texts = [texts[i] for i in order]
    else:
        encode_texts = list(texts)

    rows: list[np.ndarray] = []
    for batch_start in range(0, len(encode_texts), batch_size):
        batch = encode_texts[batch_start : batch_start + batch_size]
        rows.append(np.asarray(encoder.encode(batch), dtype=np.float32))
    encode_seconds = time.perf_counter() - started_clock
    if rows:
        matrix = np.concatenate(rows, axis=0) if len(rows) > 1 else rows[0]
    else:
        matrix = np.empty((0, config.embedding_dimension), dtype=np.float32)
    if order is not None:
        restored = np.empty_like(matrix)
        restored[order] = matrix  # exact reassembly to canonical doc order
        matrix = restored
    validate_embeddings(matrix, len(doc_ids), config.embedding_dimension, config.l2_normalize)

    payload = _atomic_write_npy(npy_path, matrix)
    npy_rel_path = Path("artifacts") / "indexes" / corpus.corpus_id / namespace / "shards" / f"{name}.npy"
    peak_rss = _peak_rss_bytes()
    manifest = _shard_manifest_payload(
        corpus=corpus,
        config=config,
        namespace=namespace,
        shard_index=shard_index,
        shard_start=shard_start,
        shard_end=shard_end,
        npy_rel_path=npy_rel_path.as_posix(),
        npy_sha256=payload,
        matrix=matrix,
        encoder=encoder,
        batch_size=batch_size,
        encode_seconds=encode_seconds,
        started_at=started_at,
        finished_at=_now_iso(),
        peak_rss=peak_rss,
        reordered_within_shard=reordered,
    )
    # The manifest is the commit marker: written only after the .npy is final.
    _atomic_write_json(manifest_path, manifest)
    return manifest


def _atomic_write_npy(path: Path, matrix: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("wb") as handle:
        np.save(handle, matrix, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(partial, path)
    return sha256_file(path)


def _load_token_lengths_for_corpus(
    encoder: Encoder, corpus: CorpusDocs, max_length: int
) -> dict[str, Any]:
    """Measure real token lengths over the whole corpus (truncation reporting)."""

    started = time.perf_counter()
    lengths = encoder.token_lengths(corpus.texts)
    elapsed = time.perf_counter() - started
    arr = np.asarray(lengths, dtype=np.int64)
    if arr.shape[0] != len(corpus.doc_ids):
        raise DenseEncodingError(
            f"token_lengths returned {arr.shape[0]} entries for {len(corpus.doc_ids)} documents."
        )
    over = int((arr > max_length).sum())
    return {
        "max_length": int(max_length),
        "documents_measured": int(arr.shape[0]),
        "documents_over_limit": over,
        "truncation_rate": round(float(over) / float(arr.shape[0]), 6) if arr.shape[0] else None,
        "token_length": {
            "min": int(arr.min()),
            "mean": round(float(arr.mean()), 3),
            "p50": int(np.percentile(arr, 50)),
            "p95": int(np.percentile(arr, 95)),
            "p99": int(np.percentile(arr, 99)),
            "max": int(arr.max()),
        },
        "measurement_seconds": round(float(elapsed), 4),
    }


def pending_shard_indices(
    *,
    project_root: Path | str,
    corpus_id: str,
    config: DenseConfig,
    shard_size: int = SHARD_SIZE_DEFAULT,
) -> list[int]:
    """Return shard indices that still need encoding (absent or orphan)."""

    project_root = Path(project_root)
    corpus = read_corpus(corpus_id, project_root)
    namespace = config.namespace
    pending: list[int] = []
    for shard_index, (start, end) in enumerate(plan_shards(len(corpus.doc_ids), shard_size)):
        state, _ = inspect_shard(
            project_root=project_root,
            corpus=corpus,
            config=config,
            namespace=namespace,
            shard_index=shard_index,
            shard_start=start,
            shard_end=end,
            encoder=None,
        )
        if state in ("absent", "orphan"):
            pending.append(shard_index)
    return pending


def run_encoding(
    *,
    project_root: Path | str,
    corpus_id: str,
    config: DenseConfig,
    encoder: Encoder | None = None,
    encoder_factory: Callable[[DenseConfig], Encoder] | None = None,
    snapshot_record: Mapping[str, Any] | None = None,
    shard_size: int = SHARD_SIZE_DEFAULT,
    batch_size: int | None = None,
    max_shards: int | None = None,
    verify_remote_revision: bool = True,
) -> dict[str, Any]:
    """Encode one corpus into checksummed shards with resume.

    ``encoder`` (or ``encoder_factory``) is only constructed when at least one
    shard still needs encoding, so a pure-resume run never loads the model.
    """

    project_root = Path(project_root)
    corpus = read_corpus(corpus_id, project_root)
    namespace = config.namespace
    npy_dir, manifest_dir = shard_layout(project_root, corpus_id, namespace)
    npy_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    plan = plan_shards(len(corpus.doc_ids), shard_size)
    batch = batch_size if batch_size is not None else _env_batch_size(BATCH_SIZE_DEFAULT)
    if batch <= 0:
        raise DenseDataError(f"batch_size must be positive, got {batch}.")

    shard_states: list[tuple[int, tuple[str, dict[str, Any] | None]]] = []
    pending: list[int] = []
    for shard_index, (start, end) in enumerate(plan):
        state, manifest = inspect_shard(
            project_root=project_root,
            corpus=corpus,
            config=config,
            namespace=namespace,
            shard_index=shard_index,
            shard_start=start,
            shard_end=end,
            encoder=None,
        )
        shard_states.append((shard_index, (state, manifest)))
        if state in ("absent", "orphan"):
            pending.append(shard_index)

    skipped_completed = sum(1 for _, (state, _) in shard_states if state == "completed")
    orphan_count = sum(1 for _, (state, _) in shard_states if state == "orphan")

    selected_pending = pending if max_shards is None else pending[: max_shards]
    truncated = len(selected_pending) < len(pending)

    encoded_manifests: dict[int, dict[str, Any]] = {}
    encode_started = time.perf_counter()
    model_load_seconds: float | None = None
    if selected_pending:
        if encoder is None and encoder_factory is not None:
            load_started = time.perf_counter()
            encoder = encoder_factory(config)
            model_load_seconds = time.perf_counter() - load_started
        if encoder is None:
            raise DenseDataError("No encoder provided and no encoder_factory given; cannot encode pending shards.")
        # Encoder pins must match the config pins exactly.
        if encoder.model_id != config.model_id:
            raise DenseDataError(
                f"Encoder model_id {encoder.model_id!r} does not match config {config.model_id!r}."
            )
        if encoder.model_revision != config.revision:
            raise DenseDataError(
                f"Encoder revision {encoder.model_revision!r} does not match config {config.revision!r}."
            )
        if encoder.embedding_dimension != config.embedding_dimension:
            raise DenseDataError(
                f"Encoder dimension {encoder.embedding_dimension} does not match config {config.embedding_dimension}."
            )
        if encoder.max_length != config.max_length:
            raise DenseDataError(
                f"Encoder max_length {encoder.max_length} does not match config {config.max_length}."
            )
        if encoder.pooling != config.pooling:
            raise DenseDataError(f"Encoder pooling {encoder.pooling!r} does not match config {config.pooling!r}.")
        for shard_index in selected_pending:
            start, end = plan[shard_index]
            encoded_manifests[shard_index] = _encode_one_shard(
                project_root=project_root,
                corpus=corpus,
                config=config,
                namespace=namespace,
                shard_index=shard_index,
                shard_start=start,
                shard_end=end,
                encoder=encoder,
                batch_size=batch,
            )

    # Post-run verification of every shard in the plan.
    completed = 0
    checksums_verified = 0
    first_incomplete: int | None = None
    for shard_index, (start, end) in enumerate(plan):
        if shard_index in encoded_manifests:
            completed += 1
            checksums_verified += 1
            continue
        state, _ = inspect_shard(
            project_root=project_root,
            corpus=corpus,
            config=config,
            namespace=namespace,
            shard_index=shard_index,
            shard_start=start,
            shard_end=end,
            encoder=None,
        )
        if state == "completed":
            completed += 1
            checksums_verified += 1
        elif first_incomplete is None:
            first_incomplete = shard_index

    if first_incomplete is not None:
        status = "INTERRUPTED"
        resume_point = {
            "next_shard_index": first_incomplete,
            "next_shard_name": shard_name(first_incomplete),
            "remaining_shards": len(plan) - first_incomplete,
            "remaining_documents": len(corpus.doc_ids) - plan[first_incomplete][0],
        }
        encoded_documents = plan[first_incomplete][0]
    else:
        status = "COMPLETED"
        resume_point = None
        encoded_documents = len(corpus.doc_ids)

    total_encode_seconds = time.perf_counter() - encode_started
    docs_encoded_this_run = sum(manifest["doc_count"] for manifest in encoded_manifests.values())
    docs_per_second = (
        round(docs_encoded_this_run / total_encode_seconds, 4)
        if total_encode_seconds > 0 and docs_encoded_this_run > 0
        else None
    )

    summary_path = Path(project_root) / "artifacts" / "indexes" / corpus_id / namespace / "encode_summary.json"
    existing: dict[str, Any] = {}
    if summary_path.is_file():
        try:
            loaded = _load_strict_json(summary_path)
            if isinstance(loaded, Mapping):
                existing = dict(loaded)
        except DenseDataError:
            existing = {}

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "dense_encode_summary",
        "module_version": MODULE_VERSION,
        "corpus_id": corpus_id,
        "namespace": namespace,
        "config_hash": config.config_hash,
        "status": status,
        "expected_documents": len(corpus.doc_ids),
        "encoded_documents": encoded_documents,
        "shard_size": shard_size,
        "shards_total": len(plan),
        "shards_completed": completed,
        "shards_skipped_resume": skipped_completed,
        "shards_reencoded_orphan": orphan_count,
        "checksums_verified": checksums_verified,
        "resume_point": resume_point,
        "batch_size": batch,
        "timing": {
            "encode_seconds_total_this_run": round(float(total_encode_seconds), 6),
            "model_load_seconds": round(float(model_load_seconds), 6) if model_load_seconds is not None else None,
            "docs_per_second_this_run": docs_per_second,
        },
        "ram": {
            "peak_rss_bytes": _peak_rss_bytes(),
            "measurement": "process peak working set (Windows psapi) or ru_maxrss",
        },
        "corpus": {
            "source_path": str(corpus.source_path),
            "source_sha256": corpus.source_sha256,
            "manifest_path": str(corpus.manifest_path),
            "expected_count_manifest": corpus.expected_count,
            "missing_title_count": corpus.missing_title_count,
            "missing_abstract_count": corpus.missing_abstract_count,
        },
        "device": encoder.device if encoder is not None else "not_loaded_resume_only",
        "gpu": "not_measured_local",
        "encoder_impl": encoder.impl_name if encoder is not None else "not_loaded_resume_only",
        "truncation": (
            _load_token_lengths_for_corpus(encoder, corpus, config.max_length)
            if encoder is not None
            else existing.get("truncation")
        ),
        "truncated_by_max_shards": truncated,
        "runs": [
            {
                "finished_at": _now_iso(),
                "encoded_shards": sorted(encoded_manifests),
                "skipped_completed_shards": skipped_completed,
                "reencoded_orphan_shards": orphan_count,
            }
        ],
    }
    if snapshot_record is not None:
        summary["model_snapshot"] = dict(snapshot_record)

    prior_runs = existing.get("runs")
    if isinstance(prior_runs, list):
        summary["runs"] = list(prior_runs) + summary["runs"]
    _atomic_write_json(summary_path, summary)
    return summary


# ---------------------------------------------------------------------------
# Exact index (no ANN)
# ---------------------------------------------------------------------------


def build_exact_index(
    *,
    project_root: Path | str,
    corpus_id: str,
    config: DenseConfig,
) -> dict[str, Any]:
    """Concatenate completed shards into the exact index with hashes."""

    project_root = Path(project_root)
    corpus = read_corpus(corpus_id, project_root)
    namespace = config.namespace
    npy_dir, manifest_dir = shard_layout(project_root, corpus_id, namespace)
    index_dir = npy_dir.parent

    plan = plan_shards(len(corpus.doc_ids), _shard_size_from_manifests(manifest_dir, len(corpus.doc_ids)))
    shard_entries: list[dict[str, Any]] = []
    matrices: list[np.ndarray] = []
    doc_ids: list[str] = []
    for shard_index, (start, end) in enumerate(plan):
        state, manifest = inspect_shard(
            project_root=project_root,
            corpus=corpus,
            config=config,
            namespace=namespace,
            shard_index=shard_index,
            shard_start=start,
            shard_end=end,
            encoder=None,
        )
        if state != "completed" or manifest is None:
            raise DenseDataError(
                f"Cannot build index: shard {shard_name(shard_index)} is {state}; encode all shards first."
            )
        shard_npy = npy_dir / f"{shard_name(shard_index)}.npy"
        matrix = np.load(shard_npy, allow_pickle=False)
        matrices.append(matrix)
        doc_ids.extend(manifest["doc_ids"])
        shard_entries.append(
            {
                "shard_name": manifest["shard_name"],
                "doc_count": manifest["doc_count"],
                "sha256": manifest["embeddings"]["sha256"],
                "manifest_sha256": _sha256_bytes((manifest_dir / f"{shard_name(shard_index)}.json").read_bytes()),
            }
        )

    if len(doc_ids) != len(corpus.doc_ids):
        raise DenseDataError(
            f"Shards cover {len(doc_ids)} documents but corpus has {len(corpus.doc_ids)}."
        )
    if doc_ids != list(corpus.doc_ids):
        raise DenseDataError("Shard doc-ID order does not reproduce the canonical corpus order.")

    matrix = np.concatenate(matrices, axis=0) if len(matrices) > 1 else matrices[0]
    validate_embeddings(matrix, len(doc_ids), config.embedding_dimension, config.l2_normalize)

    embeddings_path = index_dir / "embeddings.npy"
    doc_ids_path = index_dir / "doc_ids.json"
    _atomic_write_npy(embeddings_path, matrix)
    _atomic_write_json(doc_ids_path, {"schema_version": SCHEMA_VERSION, "corpus_id": corpus_id, "doc_ids": doc_ids})

    index_manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "dense_exact_index",
        "module_version": MODULE_VERSION,
        "corpus_id": corpus_id,
        "namespace": namespace,
        "doc_count": len(doc_ids),
        "embedding_dimension": config.embedding_dimension,
        "dtype": "float32",
        "l2_normalized": config.l2_normalize,
        "similarity": config.similarity,
        "ann": {"used": False, "recall_audit": "not_applicable_exact_index"},
        "model": {
            "id": config.model_id,
            "revision": config.revision,
            "pooling": config.pooling,
            "max_length": config.max_length,
        },
        "config_hash": config.config_hash,
        "corpus": {
            "source_path": str(corpus.source_path),
            "source_sha256": corpus.source_sha256,
            "manifest_path": str(corpus.manifest_path),
        },
        "shards": shard_entries,
        "artifacts": {
            "embeddings": {
                "path": embeddings_path.as_posix(),
                "sha256": sha256_file(embeddings_path),
            },
            "doc_ids": {
                "path": doc_ids_path.as_posix(),
                "sha256": sha256_file(doc_ids_path),
            },
        },
        "created_at": _now_iso(),
        "status": "COMPLETED",
    }
    _atomic_write_json(index_dir / "index.json", index_manifest)
    return index_manifest


def _shard_size_from_manifests(manifest_dir: Path, doc_count: int) -> int:
    """Recover the shard size from contiguous manifests and check full coverage.

    Strict on purpose: index/verify must refuse to run when shard manifests
    have gaps, unequal sizes, or do not cover the whole corpus.
    """

    manifests = sorted(manifest_dir.glob("shard-*.json"))
    if not manifests:
        raise DenseDataError(f"No shard manifests found in {manifest_dir}; run encode first.")
    actual_names = [path.stem for path in manifests]
    expected_names = [shard_name(i) for i in range(len(manifests))]
    if actual_names != expected_names:
        raise DenseDataError(
            f"Shard manifests under {manifest_dir} are not contiguous: found {actual_names[:3]}...; "
            "expected a gapless shard-00000.. sequence."
        )
    counts = []
    for path in manifests:
        manifest = _load_strict_json(path)
        count = manifest.get("doc_count")
        if not isinstance(count, int) or count <= 0:
            raise DenseDataError(f"Shard manifest {path} lacks a positive integer doc_count.")
        counts.append(count)
    size = max(counts)
    for position, count in enumerate(counts[:-1]):
        if count != size:
            raise DenseDataError(
                f"Shard manifest {manifests[position].name} covers {count} documents but the shard size is {size}."
            )
    if sum(counts) != doc_count:
        raise DenseDataError(
            f"Shard manifests under {manifest_dir} cover {sum(counts)} documents but the corpus has {doc_count}; "
            "encode all shards first."
        )
    return size


@dataclass(frozen=True)
class ExactDenseIndex:
    """Read-only exact index: memmap matrix + ordered doc IDs."""

    corpus_id: str
    matrix: np.memmap
    doc_ids: tuple[str, ...]
    manifest: Mapping[str, Any]

    @classmethod
    def load(cls, index_dir: Path | str) -> "ExactDenseIndex":
        index_dir = Path(index_dir)
        manifest = _load_strict_json(index_dir / "index.json")
        if manifest.get("artifact_kind") != "dense_exact_index":
            raise DenseDataError(f"{index_dir / 'index.json'} is not a dense exact index manifest.")
        if manifest.get("status") != "COMPLETED":
            raise DenseDataError(f"Index at {index_dir} is not COMPLETED.")
        embeddings_sha = sha256_file(index_dir / "embeddings.npy")
        if embeddings_sha != manifest["artifacts"]["embeddings"]["sha256"]:
            raise DenseDataError(
                f"Index embeddings checksum mismatch at {index_dir}: expected "
                f"{manifest['artifacts']['embeddings']['sha256']}, file hashes {embeddings_sha}."
            )
        doc_ids_sha = sha256_file(index_dir / "doc_ids.json")
        if doc_ids_sha != manifest["artifacts"]["doc_ids"]["sha256"]:
            raise DenseDataError(f"Index doc_ids checksum mismatch at {index_dir}.")
        doc_rows = _load_strict_json(index_dir / "doc_ids.json")
        doc_ids = tuple(doc_rows["doc_ids"])
        matrix = np.load(index_dir / "embeddings.npy", allow_pickle=False, mmap_mode="r")
        if matrix.shape != (len(doc_ids), int(manifest["embedding_dimension"])):
            raise DenseDataError(
                f"Index matrix shape {matrix.shape} does not match doc count {len(doc_ids)} and dimension "
                f"{manifest['embedding_dimension']}."
            )
        return cls(corpus_id=manifest["corpus_id"], matrix=matrix, doc_ids=doc_ids, manifest=manifest)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        exclude_doc_ids: frozenset[str] | set[str] = frozenset(),
    ) -> list[tuple[str, float]]:
        """Deterministic cosine ranking (vectors are L2-normalized)."""

        if top_k <= 0:
            raise DenseDataError(f"top_k must be positive, got {top_k}.")
        query = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        if query.shape[0] != self.matrix.shape[1]:
            raise DenseDataError(
                f"Query dimension {query.shape[0]} does not match index dimension {self.matrix.shape[1]}."
            )
        if self.manifest.get("l2_normalized") is not True:
            raise DenseDataError("Dot-product cosine requires l2_normalized=true in the index manifest.")
        query_norm = float(np.linalg.norm(query))
        if not math.isclose(query_norm, 1.0, rel_tol=0.0, abs_tol=1e-3):
            raise DenseDataError(f"Query embedding is not L2-normalized (norm {query_norm:.6f}).")
        scores = np.asarray(self.matrix, dtype=np.float32) @ query
        order = np.argsort(-scores, kind="stable")
        results: list[tuple[str, float]] = []
        for index in order:
            doc_id = self.doc_ids[int(index)]
            if doc_id in exclude_doc_ids:
                continue
            results.append((doc_id, float(scores[int(index)])))
            if len(results) >= top_k:
                break
        return results


# ---------------------------------------------------------------------------
# Query encoding (prefix applied) and per-corpus query artifacts
# ---------------------------------------------------------------------------


def encode_queries(
    *,
    project_root: Path | str,
    corpus_id: str,
    split: str,
    queries: Sequence[tuple[str, str]],
    config: DenseConfig,
    encoder: Encoder,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Encode ``(query_id, text)`` pairs with the query-only prefix.

    Returns the artifact manifest; the caller writes it. Kept separate from
    corpus sharding because query sets are small and order is caller-defined.
    """

    if config.prefix_scope != PREFIX_SCOPE_REQUIRED:
        raise DenseDataError(f"Unexpected prefix scope {config.prefix_scope!r}; queries need the query-only prefix.")
    if not queries:
        raise DenseDataError("Refusing to encode an empty query set.")
    ids = [query_id for query_id, _ in queries]
    if len(set(ids)) != len(ids):
        raise DenseDataError("Duplicate query IDs in query set.")
    texts = [text for _, text in queries]
    if any(not text.strip() for text in texts):
        raise DenseDataError("Empty query text encountered; queries must all have text.")
    prefixed = apply_query_prefix(texts, config.prefix)
    batch = batch_size if batch_size is not None else _env_batch_size(QUERY_BATCH_SIZE_DEFAULT)
    rows: list[np.ndarray] = []
    for start in range(0, len(prefixed), batch):
        rows.append(np.asarray(encoder.encode(prefixed[start : start + batch]), dtype=np.float32))
    matrix = np.concatenate(rows, axis=0) if len(rows) > 1 else rows[0]
    validate_embeddings(matrix, len(ids), config.embedding_dimension, config.l2_normalize)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "dense_query_embeddings",
        "module_version": MODULE_VERSION,
        "corpus_id": corpus_id,
        "split": split,
        "query_ids": ids,
        "prefix_applied": config.prefix,
        "prefix_scope": config.prefix_scope,
        "query_count": len(ids),
        "embeddings": matrix,
        "model": {
            "id": encoder.model_id,
            "revision": encoder.model_revision,
            "tokenizer_revision": encoder.tokenizer_revision,
        },
        "config_hash": config.config_hash,
    }


# ---------------------------------------------------------------------------
# Profile assembly
# ---------------------------------------------------------------------------


def find_namespaces(project_root: Path | str, corpus_id: str) -> list[str]:
    root = Path(project_root) / "artifacts" / "indexes" / corpus_id
    if not root.is_dir():
        return []
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir())


def load_encode_summary(project_root: Path | str, corpus_id: str, namespace: str) -> dict[str, Any]:
    path = Path(project_root) / "artifacts" / "indexes" / corpus_id / namespace / "encode_summary.json"
    if not path.is_file():
        raise DenseDataError(f"Missing encode summary for {corpus_id}/{namespace}: {path}")
    loaded = _load_strict_json(path)
    if not isinstance(loaded, Mapping):
        raise DenseDataError(f"Encode summary {path} is not a JSON object.")
    return dict(loaded)


def build_encoding_profile(
    *,
    project_root: Path | str,
    corpus_namespaces: Mapping[str, str],
    snapshot_record: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose ``artifacts/reports/encoding_profile.json`` from run summaries."""

    project_root = Path(project_root)
    config = load_dense_encoder_config(
        project_root / "configs" / "models" / "dense_encoder.json",
        project_root / "configs" / "protocol_v1.json",
    )
    corpora_block: dict[str, Any] = {}
    totals = {
        "documents_expected": 0,
        "documents_encoded": 0,
        "shards_total": 0,
        "shards_completed": 0,
        "encode_seconds_total": 0.0,
    }
    for corpus_id, namespace in corpus_namespaces.items():
        summary = load_encode_summary(project_root, corpus_id, namespace)
        index_manifest: dict[str, Any] | None = None
        index_path = project_root / "artifacts" / "indexes" / corpus_id / namespace / "index.json"
        if index_path.is_file():
            loaded = _load_strict_json(index_path)
            if isinstance(loaded, Mapping):
                index_manifest = dict(loaded)
        corpora_block[corpus_id] = {
            "namespace": namespace,
            "status": summary.get("status"),
            "resume_point": summary.get("resume_point"),
            "expected_documents": summary.get("expected_documents"),
            "encoded_documents": summary.get("encoded_documents"),
            "shards": {
                "size": summary.get("shard_size"),
                "total": summary.get("shards_total"),
                "completed": summary.get("shards_completed"),
                "skipped_resume_verified": summary.get("shards_skipped_resume"),
                "reencoded_orphans": summary.get("shards_reencoded_orphan"),
                "checksums_verified": summary.get("checksums_verified"),
            },
            "throughput": summary.get("timing"),
            "batch_size": summary.get("batch_size"),
            "ram": summary.get("ram"),
            "device": summary.get("device"),
            "gpu": summary.get("gpu"),
            "truncation": summary.get("truncation"),
            "corpus": summary.get("corpus"),
            "runs": summary.get("runs"),
            "index": (
                {
                    "path": index_manifest["artifacts"]["embeddings"]["path"],
                    "sha256": index_manifest["artifacts"]["embeddings"]["sha256"],
                    "doc_ids_sha256": index_manifest["artifacts"]["doc_ids"]["sha256"],
                    "doc_count": index_manifest["doc_count"],
                    "ann_used": index_manifest["ann"]["used"],
                }
                if index_manifest is not None
                else None
            ),
        }
        def _summary_int(key: str) -> int:
            value = summary.get(key)
            if not isinstance(value, int):
                raise DenseDataError(
                    f"Encode summary for {corpus_id}/{namespace} lacks integer '{key}' (got {value!r})."
                )
            return value

        totals["documents_expected"] += _summary_int("expected_documents")
        totals["documents_encoded"] += _summary_int("encoded_documents")
        totals["shards_total"] += _summary_int("shards_total")
        totals["shards_completed"] += _summary_int("shards_completed")
        timing = summary.get("timing")
        if not isinstance(timing, Mapping) or not isinstance(timing.get("encode_seconds_total_this_run"), (int, float)):
            raise DenseDataError(
                f"Encode summary for {corpus_id}/{namespace} lacks numeric timing.encode_seconds_total_this_run."
            )
        totals["encode_seconds_total"] += float(timing["encode_seconds_total_this_run"])

    profile: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "encoding_profile",
        "task_id": "SG-019",
        "module_version": MODULE_VERSION,
        "generated_at": _now_iso(),
        "protocol": {
            "similarity": config.similarity,
            "l2_normalize": config.l2_normalize,
            "missing_embedding": config.missing_embedding,
        },
        "encoder": {
            "config_id": config.config_id,
            "config_path": "configs/models/dense_encoder.json",
            "config_sha256": config.config_sha256,
            "config_hash": config.config_hash,
            "model_id": config.model_id,
            "revision": config.revision,
            "tokenizer_revision": config.revision,
            "pooling": config.pooling,
            "embedding_dimension": config.embedding_dimension,
            "max_length": config.max_length,
            "prefix": config.prefix,
            "prefix_scope": config.prefix_scope,
            "license": config.license,
        },
        "model_snapshot": dict(snapshot_record) if snapshot_record is not None else None,
        "environment": {
            "device": "cpu",
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy_version": np.__version__,
            "torch_version": _optional_module_version("torch"),
            "transformers_version": _optional_module_version("transformers"),
            "gpu": "not_measured_local",
            "gpu_note": (
                "This machine has no CUDA-capable PyTorch build; VRAM was not measured and no GPU number is "
                "fabricated."
            ),
        },
        "order_policy": (
            "Documents sorted by canonical ID ascending; shards are contiguous slices of shard_size; row order "
            "in every .npy equals the manifest doc_ids order; the exact index concatenates shards in that order."
        ),
        "corpora": corpora_block,
        "totals": totals,
    }
    if extra:
        profile.update(extra)
    return profile


def _optional_module_version(name: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(name)
    except Exception:  # noqa: BLE001 - optional reporting
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scholargraph.retrieval.dense",
        description="Sharded dense encoding and exact index (SG-019).",
    )
    parser.add_argument(
        "--project-root",
        default=os.environ.get("SCHOLARGRAPH_PROJECT_ROOT") or str(Path.cwd()),
        help="Project root (default: $SCHOLARGRAPH_PROJECT_ROOT or cwd).",
    )
    parser.add_argument(
        "--encoder-module",
        default=None,
        help=(
            "Optional 'module:function' factory returning an Encoder; intended for offline tests. "
            "Production runs must omit it to use the pinned HuggingFace snapshot."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode = subparsers.add_parser("encode", help="Encode a corpus into checksummed shards with resume.")
    encode.add_argument("--corpus", required=True, choices=sorted(CORPUS_SPECS))
    encode.add_argument("--shard-size", type=int, default=SHARD_SIZE_DEFAULT)
    encode.add_argument("--batch-size", type=int, default=None)
    encode.add_argument("--max-shards", type=int, default=None, help="Stop after encoding N pending shards.")
    encode.add_argument("--no-remote-verify", action="store_true", help="Skip the HF API revision re-check.")

    index = subparsers.add_parser("index", help="Build the exact index from completed shards.")
    index.add_argument("--corpus", required=True, choices=sorted(CORPUS_SPECS))

    verify = subparsers.add_parser("verify", help="Re-verify shard manifests and checksums.")
    verify.add_argument("--corpus", required=True, choices=sorted(CORPUS_SPECS))

    profile = subparsers.add_parser("profile", help="Write artifacts/reports/encoding_profile.json.")
    profile.add_argument("--output", default="artifacts/reports/encoding_profile.json")
    profile.add_argument(
        "--corpus-namespace",
        action="append",
        required=True,
        metavar="CORPUS=NAMESPACE",
        help="Corpus namespace to include; repeat per corpus.",
    )

    return parser


def _resolve_encoder_from_cli(args: argparse.Namespace) -> Encoder | None:
    if not args.encoder_module:
        return None
    module_name, sep, function_name = args.encoder_module.partition(":")
    if not sep or not module_name or not function_name:
        raise DenseDataError("--encoder-module must look like 'module:function'.")
    import importlib

    module = importlib.import_module(module_name)
    factory = getattr(module, function_name)
    config = load_dense_encoder_config(
        Path(args.project_root) / "configs" / "models" / "dense_encoder.json",
        Path(args.project_root) / "configs" / "protocol_v1.json",
    )
    return factory(config)


def _cli_encode(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root)
    config = load_dense_encoder_config(
        project_root / "configs" / "models" / "dense_encoder.json",
        project_root / "configs" / "protocol_v1.json",
    )
    # Resume scan first: a pure-resume run must not import any encoder module
    # or download/load weights, and a config-mismatch must fail before both.
    pending = pending_shard_indices(
        project_root=project_root, corpus_id=args.corpus, config=config, shard_size=args.shard_size
    )
    encoder: Encoder | None = None
    snapshot_record: dict[str, Any] | None = None
    if pending:
        encoder = _resolve_encoder_from_cli(args)
        if encoder is None:
            # Real run: re-verify the pinned revision before creating the encoder.
            snapshot_record = verify_model_snapshot(project_root, config, verify_remote=not args.no_remote_verify)
            snapshot_dir = _snapshot_dir_from_record(snapshot_record)
            encoder = HfLocalEncoder(
                snapshot_dir=snapshot_dir,
                config=config,
                device="cpu",
            )
    return run_encoding(
        project_root=project_root,
        corpus_id=args.corpus,
        config=config,
        encoder=encoder,
        shard_size=args.shard_size,
        batch_size=args.batch_size,
        max_shards=args.max_shards,
        snapshot_record=snapshot_record,
    )


def _cli_index(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root)
    config = load_dense_encoder_config(
        project_root / "configs" / "models" / "dense_encoder.json",
        project_root / "configs" / "protocol_v1.json",
    )
    return build_exact_index(project_root=project_root, corpus_id=args.corpus, config=config)


def _cli_verify(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root)
    config = load_dense_encoder_config(
        project_root / "configs" / "models" / "dense_encoder.json",
        project_root / "configs" / "protocol_v1.json",
    )
    corpus = read_corpus(args.corpus, project_root)
    namespace = config.namespace
    manifest_dir = shard_layout(project_root, args.corpus, namespace)[1]
    manifest_paths = sorted(manifest_dir.glob("shard-*.json"))
    if not manifest_paths:
        raise DenseDataError(f"No shard manifests found under {manifest_dir}.")
    plan = plan_shards(len(corpus.doc_ids), _shard_size_from_manifests(manifest_dir, len(corpus.doc_ids)))
    verified = 0
    for shard_index, (start, end) in enumerate(plan):
        state, _ = inspect_shard(
            project_root=project_root,
            corpus=corpus,
            config=config,
            namespace=namespace,
            shard_index=shard_index,
            shard_start=start,
            shard_end=end,
            encoder=None,
        )
        if state == "completed":
            verified += 1
    return {
        "corpus_id": args.corpus,
        "namespace": namespace,
        "shards_total": len(plan),
        "shards_verified_completed": verified,
        "status": "PASS" if verified == len(plan) else "PARTIAL",
    }


def _cli_profile(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root)
    namespaces: dict[str, str] = {}
    for item in args.corpus_namespace:
        corpus, sep, namespace = item.partition("=")
        if not sep or not corpus or not namespace:
            raise DenseDataError(f"--corpus-namespace must look like CORPUS=NAMESPACE, got {item!r}.")
        namespaces[corpus] = namespace
    snapshot_record: dict[str, Any] | None = None
    for corpus_id, namespace in namespaces.items():
        try:
            summary = load_encode_summary(project_root, corpus_id, namespace)
        except DenseDataError:
            continue
        candidate = summary.get("model_snapshot")
        if isinstance(candidate, Mapping) and candidate:
            snapshot_record = dict(candidate)
            break
    profile = build_encoding_profile(
        project_root=project_root,
        corpus_namespaces=namespaces,
        snapshot_record=snapshot_record,
    )
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / output_path
    _atomic_write_json(output_path, profile)
    return {"output": str(output_path), "corpora": sorted(namespaces)}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns process exit code (0 success, 1 failure)."""

    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "encode":
            result = _cli_encode(args)
        elif args.command == "index":
            result = _cli_index(args)
        elif args.command == "verify":
            result = _cli_verify(args)
        elif args.command == "profile":
            result = _cli_profile(args)
        else:  # pragma: no cover - argparse enforces choices
            raise DenseDataError(f"Unknown command {args.command!r}.")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report and fail loudly
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
