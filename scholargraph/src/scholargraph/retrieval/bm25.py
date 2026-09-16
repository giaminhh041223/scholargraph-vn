"""Deterministic BM25 retrieval per Research Protocol v1 — task SG-012 pilot.

Contract implemented (docs/RESEARCH_PROTOCOL.md section 5.1 and
``configs/protocol_v1.json`` -> ``retrieval.lexical``):

- Tokenizer: **the protocol defines the tokenizer explicitly**, so no fallback
  choice was needed: unicode ``casefold`` + token regex ``(?u)\\b\\w+\\b``, no
  stopword removal, no stemming. The same tokenizer is used for corpus and
  queries.
- Corpus text: ``title + " " + abstract`` (``field_joiner=" "``); a missing
  field becomes the empty string and its coverage is counted and reported
  (``missing_field="empty_string_report_coverage"``).
- BM25: ``k1=1.5``, ``b=0.75``; ``idf = ln(1 + (N - df + 0.5) / (df + 0.5))``
  which is strictly positive for every ``0 <= df <= N``; scores are accumulated
  over **unique query tokens** multiplied by the saturation factor
  ``f * (k1 + 1) / (f + k1 * (1 - b + b * |d| / avgdl))``. This is the
  positive-IDF variant chosen by the protocol; it is intentionally NOT the
  default formula of any off-the-shelf package (e.g. ``rank_bm25`` floors
  negative IDFs and is therefore not used here).
- Empty corpus or an empty tokenizer vocabulary: hard input error
  (``empty_corpus="fail"``).
- Ranking order: score descending, ties broken by canonical doc ID ascending
  (Unicode code points). A query whose text yields zero tokens after
  tokenization is a loud error, never a silently dropped or arbitrarily
  ranked query.

Leakage boundary (Protocol v1 ``data_access.ranker_forbidden``): the ranking
path reads only the corpus and the query texts. Qrels are opened exactly once,
after rankings have been recorded, and only to feed
``scholargraph.evaluation.metrics.ProtocolEvaluator``. The split manifest is
verified by SHA-256 (queries and qrels files) before any use; a hash mismatch
or any missing/ill-formed mandatory resource fails the CLI with exit code 1.
Ranking provenance is stored through ``scholargraph.evaluation.runner.RunStore``
(run ID, hashes, command, artifacts, terminal seal); completed runs are never
overwritten — a re-run allocates a new run ID.

CLI example (from the project root):

    PYTHONPATH=src ./.venv/Scripts/python.exe -m scholargraph.retrieval.bm25 \
        --dataset scifact --split dev --output-dir artifacts/runs
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator
from scholargraph.evaluation.runner import RunStore
from scholargraph.ingest.beir_loader import (
    BeirDataError,
    canonical_beir_id,
    sha256_file,
)

MODULE_VERSION = "sg012-1.0.0"
EVALUATOR_SOURCE_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "metrics.py"
# Protocol-wide default seed (configs/protocol_v1.json -> statistics.bootstrap.seed).
# BM25 is fully deterministic; the seed is recorded for provenance only.
PROTOCOL_SEED = 20260915

# Exact lexical contract this module supports; any protocol deviation fails loudly.
SUPPORTED_TOKENIZER_CASE = "unicode_casefold"
SUPPORTED_TOKEN_PATTERN = r"(?u)\b\w+\b"
SUPPORTED_TEXT_FIELDS = ("title", "abstract")
SUPPORTED_FIELD_JOINER = " "
SUPPORTED_MISSING_FIELD = "empty_string_report_coverage"
SUPPORTED_BM25_IDF_FORMULA = "ln(1+(N-df+0.5)/(df+0.5))"
SUPPORTED_QUERY_TERMS = "unique_tokens"
SUPPORTED_EMPTY_CORPUS = "fail"

QRELS_HEADER = ("query-id", "corpus-id", "score")

TOKEN_PATTERN = re.compile(SUPPORTED_TOKEN_PATTERN)


class BM25ConfigError(ValueError):
    """Raised when the protocol file deviates from the supported lexical contract."""


class BM25DataError(ValueError):
    """Raised when a mandatory input resource is missing or ill-formed."""


class BM25EmptyQueryError(ValueError):
    """Raised when a query yields zero tokens after protocol tokenization."""


# ---------------------------------------------------------------------------
# Protocol configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BM25ProtocolConfig:
    """Resolved lexical configuration pinned to the exact Protocol v1 strings."""

    k1: float
    b: float
    top_k: int
    tokenizer_case: str
    token_pattern: str
    text_fields: tuple[str, ...]
    field_joiner: str
    missing_field: str
    idf_formula: str
    query_terms: str
    empty_corpus: str


def _load_strict_json(path: Path) -> Any:
    """Parse JSON while rejecting duplicate keys and NaN/Infinity constants."""
    if not path.is_file():
        raise BM25DataError(f"Missing JSON file: {path}")

    def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise BM25DataError(f"Duplicate JSON key {key!r} in {path}.")
            seen.add(key)
        return dict(pairs)

    def _reject_constant(name: str) -> Any:
        raise BM25DataError(f"Non-finite JSON constant {name!r} in {path}.")

    with path.open("r", encoding="utf-8") as handle:
        try:
            return json.load(handle, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
        except json.JSONDecodeError as exc:
            raise BM25DataError(f"Invalid JSON in {path}: {exc.msg}") from exc


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BM25ConfigError(f"Protocol section {context} must be an object.")
    return value


def _require_string(value: Any, context: str) -> str:
    # Whitespace-only strings stay valid here (field_joiner is " "); every
    # caller compares the result against an exact supported constant anyway.
    if not isinstance(value, str) or value == "":
        raise BM25ConfigError(f"Protocol value {context} must be a non-empty string.")
    return value


def _require_finite_number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BM25ConfigError(f"Protocol value {context} must be a finite number.")
    return float(value)


def load_protocol_lexical_config(path: Path | str) -> BM25ProtocolConfig:
    """Read and pin the lexical retrieval contract from the protocol file.

    Every supported value must match the exact protocol strings; deviations
    raise :class:`BM25ConfigError` instead of being silently ignored.
    """
    protocol_path = Path(path)
    data = _load_strict_json(protocol_path)
    retrieval = _require_mapping(_require_section(data, "retrieval"), "retrieval")
    lexical = _require_mapping(_require_section(retrieval, "lexical"), "retrieval.lexical")
    bm25 = _require_mapping(_require_section(lexical, "bm25"), "retrieval.lexical.bm25")
    tokenizer = _require_mapping(_require_section(lexical, "tokenizer"), "retrieval.lexical.tokenizer")

    text_fields = _require_section(lexical, "text_fields")
    if not isinstance(text_fields, Sequence) or isinstance(text_fields, (str, bytes)):
        raise BM25ConfigError("retrieval.lexical.text_fields must be a list.")
    if tuple(text_fields) != SUPPORTED_TEXT_FIELDS:
        raise BM25ConfigError(
            f"Unsupported text_fields {tuple(text_fields)!r}; this module implements "
            f"{SUPPORTED_TEXT_FIELDS!r} only."
        )
    joiner = _require_string(_require_section(lexical, "field_joiner"), "retrieval.lexical.field_joiner")
    if joiner != SUPPORTED_FIELD_JOINER:
        raise BM25ConfigError(
            f"Unsupported field_joiner {joiner!r}; expected {SUPPORTED_FIELD_JOINER!r}."
        )
    missing_field = _require_string(
        _require_section(lexical, "missing_field"), "retrieval.lexical.missing_field"
    )
    if missing_field != SUPPORTED_MISSING_FIELD:
        raise BM25ConfigError(
            f"Unsupported missing_field {missing_field!r}; expected {SUPPORTED_MISSING_FIELD!r}."
        )

    case = _require_string(_require_section(tokenizer, "case"), "tokenizer.case")
    if case != SUPPORTED_TOKENIZER_CASE:
        raise BM25ConfigError(
            f"Unsupported tokenizer case {case!r}; expected {SUPPORTED_TOKENIZER_CASE!r}."
        )
    pattern = _require_string(_require_section(tokenizer, "pattern"), "tokenizer.pattern")
    if pattern != SUPPORTED_TOKEN_PATTERN:
        raise BM25ConfigError(
            f"Unsupported token pattern {pattern!r}; expected {SUPPORTED_TOKEN_PATTERN!r}."
        )
    stopwords = _require_section(tokenizer, "stopwords")
    stemming = _require_section(tokenizer, "stemming")
    for flag, name in ((stopwords, "tokenizer.stopwords"), (stemming, "tokenizer.stemming")):
        if flag is not False:
            raise BM25ConfigError(f"{name} must be false; this module implements no stemming/stopwords.")

    idf_formula = _require_string(_require_section(bm25, "idf"), "bm25.idf")
    if idf_formula != SUPPORTED_BM25_IDF_FORMULA:
        raise BM25ConfigError(
            f"Unsupported idf formula {idf_formula!r}; expected {SUPPORTED_BM25_IDF_FORMULA!r}."
        )
    query_terms = _require_string(_require_section(bm25, "query_terms"), "bm25.query_terms")
    if query_terms != SUPPORTED_QUERY_TERMS:
        raise BM25ConfigError(
            f"Unsupported query_terms {query_terms!r}; expected {SUPPORTED_QUERY_TERMS!r}."
        )
    empty_corpus = _require_string(_require_section(bm25, "empty_corpus"), "bm25.empty_corpus")
    if empty_corpus != SUPPORTED_EMPTY_CORPUS:
        raise BM25ConfigError(
            f"Unsupported empty_corpus policy {empty_corpus!r}; expected {SUPPORTED_EMPTY_CORPUS!r}."
        )

    k1 = _require_finite_number(_require_section(bm25, "k1"), "bm25.k1")
    b = _require_finite_number(_require_section(bm25, "b"), "bm25.b")
    if k1 <= 0:
        raise BM25ConfigError(f"bm25.k1 must be positive; received {k1}.")
    if not 0.0 <= b <= 1.0:
        raise BM25ConfigError(f"bm25.b must be within [0, 1]; received {b}.")

    depth = _require_section(retrieval, "per_retriever_depth")
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise BM25ConfigError(f"retrieval.per_retriever_depth must be a positive integer; received {depth!r}.")

    return BM25ProtocolConfig(
        k1=k1,
        b=b,
        top_k=depth,
        tokenizer_case=case,
        token_pattern=pattern,
        text_fields=tuple(text_fields),
        field_joiner=joiner,
        missing_field=missing_field,
        idf_formula=idf_formula,
        query_terms=query_terms,
        empty_corpus=empty_corpus,
    )


def _require_section(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping:
        raise BM25ConfigError(f"Protocol section {key!r} is missing.")
    return mapping[key]


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Tokenize with the Protocol v1 lexical tokenizer (casefold + ``\\w+``)."""
    if not isinstance(text, str):
        raise BM25DataError("Tokenizer input must be a string.")
    return TOKEN_PATTERN.findall(text.casefold())


# ---------------------------------------------------------------------------
# Strict input readers (ranking path never reads qrels)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusData:
    """Full corpus texts plus missing-field coverage counters.

    A document with neither title nor text is a hard error and never enters
    the index, so ``missing_both`` needs no counter: it is 0 by construction.
    """

    texts: Mapping[str, str]
    missing_title_count: int
    missing_abstract_count: int

    @property
    def document_count(self) -> int:
        return len(self.texts)


@dataclass(frozen=True)
class SplitManifestData:
    """Verified split manifest with resolved file paths."""

    dataset: str
    split: str
    role: str
    query_ids: tuple[str, ...]
    query_count: int
    qrel_count: int
    queries_path: Path
    queries_sha256: str
    qrels_path: Path
    qrels_sha256: str
    manifest_sha256: str


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file strictly: no blank lines, non-object rows or bad JSON."""
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise BM25DataError(f"Blank line in {path} at line {line_number}.")
            try:
                row = _load_strict_json_line(line, path, line_number)
            except BM25DataError:
                raise
            if not isinstance(row, dict):
                raise BM25DataError(f"JSONL row in {path} at line {line_number} is not an object.")
            rows.append(row)
    return rows


def _load_strict_json_line(line: str, path: Path, line_number: int) -> Any:
    def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise BM25DataError(f"Duplicate JSON key {key!r} in {path} at line {line_number}.")
            seen.add(key)
        return dict(pairs)

    def _reject_constant(name: str) -> Any:
        raise BM25DataError(f"Non-finite JSON constant {name!r} in {path} at line {line_number}.")

    try:
        return json.loads(line, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise BM25DataError(f"Invalid JSON in {path} at line {line_number}: {exc.msg}") from exc


def _corpus_field(row: Mapping[str, Any], field: str, raw_id: str, path: Path, line_number: int) -> str:
    """Read an optional corpus text field: absent/None becomes ``""`` (protocol)."""
    if field not in row:
        return ""
    value = row[field]
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BM25DataError(f"Corpus row {raw_id!r} in {path} at line {line_number} has non-string {field!r}.")
    return value


def load_corpus(path: Path | str, *, dataset: str) -> CorpusData:
    """Load the full BEIR corpus strictly; an empty corpus is a hard failure."""
    corpus_path = Path(path)
    if not corpus_path.is_file():
        raise BM25DataError(f"Missing corpus file: {corpus_path}")
    texts: dict[str, str] = {}
    missing_title = 0
    missing_abstract = 0
    for line_number, row in enumerate(_read_jsonl_rows(corpus_path), start=1):
        raw_id = row.get("_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise BM25DataError(f"Corpus row in {corpus_path} at line {line_number} lacks a valid '_id'.")
        doc_id = canonical_beir_id(dataset, raw_id)
        if doc_id in texts:
            raise BM25DataError(f"Duplicate corpus ID {raw_id!r} in {corpus_path} at line {line_number}.")
        title = _corpus_field(row, "title", raw_id, corpus_path, line_number)
        abstract = _corpus_field(row, "text", raw_id, corpus_path, line_number)
        has_title = bool(title.strip())
        has_abstract = bool(abstract.strip())
        if not has_title and not has_abstract:
            raise BM25DataError(
                f"Corpus row {raw_id!r} in {corpus_path} at line {line_number} has neither title nor text."
            )
        if not has_title:
            missing_title += 1
        if not has_abstract:
            missing_abstract += 1
        texts[doc_id] = title + SUPPORTED_FIELD_JOINER + abstract
    if not texts:
        raise BM25DataError(f"BEIR corpus is empty: {corpus_path}")
    return CorpusData(
        texts=texts,
        missing_title_count=missing_title,
        missing_abstract_count=missing_abstract,
    )


def load_queries(path: Path | str, *, dataset: str) -> Mapping[str, str]:
    """Load all BEIR queries strictly (canonical ID -> text)."""
    queries_path = Path(path)
    if not queries_path.is_file():
        raise BM25DataError(f"Missing queries file: {queries_path}")
    queries: dict[str, str] = {}
    for line_number, row in enumerate(_read_jsonl_rows(queries_path), start=1):
        raw_id = row.get("_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise BM25DataError(f"Query row in {queries_path} at line {line_number} lacks a valid '_id'.")
        query_id = canonical_beir_id(dataset, raw_id)
        if query_id in queries:
            raise BM25DataError(f"Duplicate query ID {raw_id!r} in {queries_path} at line {line_number}.")
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise BM25DataError(
                f"Query row {raw_id!r} in {queries_path} at line {line_number} has missing or empty text."
            )
        queries[query_id] = text
    if not queries:
        raise BM25DataError(f"BEIR queries are empty: {queries_path}")
    return queries


def _resolve_manifest_path(value: Any, context: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BM25DataError(f"Split manifest field {context!r} must be a non-empty path string.")
    resolved = Path(value)
    if not resolved.is_absolute():
        # Manifest paths are written relative to the project root (the CLI's cwd).
        resolved = Path.cwd() / resolved
    return resolved


def _manifest_field(data: Mapping[str, Any], key: str, manifest_path: Path) -> Any:
    if key not in data:
        raise BM25DataError(f"Split manifest {manifest_path} is missing required field {key!r}.")
    return data[key]


def load_split_manifest(
    path: Path | str,
    *,
    dataset: str,
    split: str,
) -> SplitManifestData:
    """Load and verify a locked split manifest, including SHA-256 of its inputs.

    The queries and qrels files referenced by the manifest are hashed and
    compared against ``queries_sha256`` / ``qrels_sha256`` before any use.
    A mismatch is a hard failure (exit code 1 through the CLI).
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise BM25DataError(f"Missing split manifest: {manifest_path}")
    manifest_sha256 = sha256_file(manifest_path)
    data = _load_strict_json(manifest_path)
    if not isinstance(data, Mapping):
        raise BM25DataError(f"Split manifest {manifest_path} must contain a JSON object.")
    manifest_dataset = _manifest_field(data, "dataset", manifest_path)
    manifest_split = _manifest_field(data, "split", manifest_path)
    if manifest_dataset != dataset or manifest_split != split:
        raise BM25DataError(
            f"Split manifest {manifest_path} describes dataset/split "
            f"({manifest_dataset!r}, {manifest_split!r}) but ({dataset!r}, {split!r}) was requested."
        )
    query_ids_value = _manifest_field(data, "query_ids", manifest_path)
    if not isinstance(query_ids_value, list) or not query_ids_value:
        raise BM25DataError(f"Split manifest {manifest_path} has an empty or invalid query_ids list.")
    if any(not isinstance(qid, str) or not qid.strip() for qid in query_ids_value):
        raise BM25DataError(f"Split manifest {manifest_path} contains invalid query IDs.")
    query_ids = tuple(sorted(query_ids_value))
    if len(set(query_ids)) != len(query_ids):
        raise BM25DataError(f"Split manifest {manifest_path} contains duplicate query IDs.")
    query_count = _manifest_field(data, "query_count", manifest_path)
    qrel_count = _manifest_field(data, "qrel_count", manifest_path)
    if isinstance(query_count, bool) or not isinstance(query_count, int) or query_count != len(query_ids):
        raise BM25DataError(
            f"Split manifest {manifest_path} query_count {query_count!r} does not match "
            f"{len(query_ids)} query_ids entries."
        )
    if isinstance(qrel_count, bool) or not isinstance(qrel_count, int) or qrel_count < 1:
        raise BM25DataError(f"Split manifest {manifest_path} has invalid qrel_count {qrel_count!r}.")

    queries_path = _resolve_manifest_path(_manifest_field(data, "queries_file", manifest_path), "queries_file")
    qrels_path = _resolve_manifest_path(_manifest_field(data, "qrels_file", manifest_path), "qrels_file")
    queries_sha256 = _manifest_field(data, "queries_sha256", manifest_path)
    qrels_sha256 = _manifest_field(data, "qrels_sha256", manifest_path)
    for name, value in (("queries_sha256", queries_sha256), ("qrels_sha256", qrels_sha256)):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise BM25DataError(f"Split manifest field {name!r} is not a SHA-256 hex digest.")
    if not queries_path.is_file():
        raise BM25DataError(f"Missing queries file referenced by manifest: {queries_path}")
    if not qrels_path.is_file():
        raise BM25DataError(f"Missing qrels file referenced by manifest: {qrels_path}")
    actual_queries_sha256 = sha256_file(queries_path)
    actual_qrels_sha256 = sha256_file(qrels_path)
    if actual_queries_sha256 != queries_sha256.lower():
        raise BM25DataError(
            f"queries.jsonl SHA-256 mismatch: manifest {queries_sha256.lower()} != "
            f"actual {actual_queries_sha256} for {queries_path}."
        )
    if actual_qrels_sha256 != qrels_sha256.lower():
        raise BM25DataError(
            f"qrels SHA-256 mismatch: manifest {qrels_sha256.lower()} != actual "
            f"{actual_qrels_sha256} for {qrels_path}."
        )
    role = _manifest_field(data, "role", manifest_path)
    return SplitManifestData(
        dataset=dataset,
        split=split,
        role=str(role),
        query_ids=query_ids,
        query_count=query_count,
        qrel_count=qrel_count,
        queries_path=queries_path,
        queries_sha256=actual_queries_sha256,
        qrels_path=qrels_path,
        qrels_sha256=actual_qrels_sha256,
        manifest_sha256=manifest_sha256,
    )


def load_qrels(
    path: Path | str,
    *,
    dataset: str,
    corpus_ids: Mapping[str, str] | set[str],
    query_ids: set[str],
) -> tuple[Mapping[str, Mapping[str, int]], int]:
    """Load qrels strictly. **Evaluator-only input; never used for ranking.**"""
    qrels_path = Path(path)
    if not qrels_path.is_file():
        raise BM25DataError(f"Missing qrels file: {qrels_path}")
    qrels: dict[str, dict[str, int]] = {}
    row_count = 0
    with qrels_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise BM25DataError(f"Qrels file is empty: {qrels_path}") from exc
        if header != QRELS_HEADER:
            raise BM25DataError(f"Unexpected qrels header in {qrels_path}: {header!r}; expected {QRELS_HEADER!r}.")
        for line_number, fields in enumerate(reader, start=2):
            if len(fields) != 3:
                raise BM25DataError(
                    f"Qrels row in {qrels_path} at line {line_number} has {len(fields)} fields; expected 3."
                )
            raw_query_id, raw_doc_id, raw_score = fields
            if not raw_query_id.strip() or not raw_doc_id.strip():
                raise BM25DataError(f"Qrels row in {qrels_path} at line {line_number} has an empty ID.")
            try:
                score = int(raw_score)
            except ValueError as exc:
                raise BM25DataError(
                    f"Non-integer qrel score in {qrels_path} at line {line_number}: {raw_score!r}."
                ) from exc
            if score < 0 or score > 2:
                raise BM25DataError(f"Qrel score {score} in {qrels_path} at line {line_number} is outside [0, 2].")
            query_id = canonical_beir_id(dataset, raw_query_id)
            doc_id = canonical_beir_id(dataset, raw_doc_id)
            if query_id not in query_ids:
                raise BM25DataError(
                    f"Qrels query {raw_query_id!r} in {qrels_path} at line {line_number} is outside "
                    "the locked split query set."
                )
            if doc_id not in corpus_ids:
                raise BM25DataError(
                    f"Qrels document {raw_doc_id!r} in {qrels_path} at line {line_number} is outside "
                    "the corpus universe."
                )
            per_query = qrels.setdefault(query_id, {})
            if doc_id in per_query:
                raise BM25DataError(
                    f"Duplicate qrel ({raw_query_id!r}, {raw_doc_id!r}) in {qrels_path} at line {line_number}."
                )
            per_query[doc_id] = score
            row_count += 1
    if not qrels:
        raise BM25DataError(f"Qrels file has no rows: {qrels_path}")
    return qrels, row_count


# ---------------------------------------------------------------------------
# BM25 index
# ---------------------------------------------------------------------------


class BM25Index:
    """Protocol v1 positive-IDF BM25 over a full corpus (deterministic)."""

    def __init__(self, documents: Mapping[str, str], *, k1: float, b: float) -> None:
        if not documents:
            raise BM25DataError("BM25 index requires a non-empty corpus (empty_corpus=fail).")
        if not math.isfinite(k1) or k1 <= 0:
            raise BM25DataError(f"k1 must be a positive finite number; received {k1!r}.")
        if not math.isfinite(b) or not 0.0 <= b <= 1.0:
            raise BM25DataError(f"b must be a finite number within [0, 1]; received {b!r}.")
        self.k1 = float(k1)
        self.b = float(b)

        document_count = len(documents)
        postings: dict[str, list[tuple[str, int]]] = {}
        doc_lengths: dict[str, int] = {}
        for doc_id in sorted(documents):
            tokens = tokenize(documents[doc_id])
            doc_lengths[doc_id] = len(tokens)
            term_frequencies: dict[str, int] = {}
            for token in tokens:
                term_frequencies[token] = term_frequencies.get(token, 0) + 1
            for term in sorted(term_frequencies):
                postings.setdefault(term, []).append((doc_id, term_frequencies[term]))
        total_length = sum(doc_lengths.values())
        if total_length == 0:
            raise BM25DataError(
                "Tokenizer produced an empty vocabulary over the whole corpus (empty_corpus=fail)."
            )
        self.average_document_length = total_length / document_count
        self.document_count = document_count
        self._doc_lengths = doc_lengths
        self._postings = postings
        self._inverse_document_frequency: dict[str, float] = {
            term: self._positive_idf(len(entry), document_count) for term, entry in postings.items()
        }
        self.vocabulary_size = len(postings)

    @staticmethod
    def _positive_idf(df: int, document_count: int) -> float:
        """idf = ln(1 + (N - df + 0.5) / (df + 0.5)); strictly positive."""
        value = math.log(1.0 + (document_count - df + 0.5) / (df + 0.5))
        if not math.isfinite(value) or value <= 0.0:
            raise BM25DataError(f"Non-positive idf computed for df={df}, N={document_count}.")
        return value

    @property
    def idf(self) -> Mapping[str, float]:
        """Read-only view of the term -> positive-IDF table."""
        return dict(self._inverse_document_frequency)

    def score_query(self, query_text: str, *, exclude_doc_ids: frozenset[str] | set[str] = frozenset()) -> list[tuple[str, float]]:
        """Score every document sharing at least one query token.

        Contributions are accumulated per document in sorted-term order and
        summed with :func:`math.fsum`, so results are deterministic.
        Documents matching no query token score nothing and stay unranked.
        """
        tokens = tokenize(query_text)
        if not tokens:
            raise BM25EmptyQueryError(
                "Query produced zero tokens under the Protocol v1 tokenizer; refusing to rank."
            )
        contributions: dict[str, list[float]] = {}
        for term in sorted(set(tokens)):
            if term not in self._postings:
                continue  # out-of-vocabulary query terms contribute 0 by definition
            idf_value = self._inverse_document_frequency[term]
            for doc_id, term_frequency in self._postings[term]:
                normalization = 1.0 - self.b + self.b * self._doc_lengths[doc_id] / self.average_document_length
                saturation = term_frequency * (self.k1 + 1.0) / (term_frequency + self.k1 * normalization)
                contributions.setdefault(doc_id, []).append(idf_value * saturation)
        scored = [
            (doc_id, math.fsum(values))
            for doc_id, values in contributions.items()
            if doc_id not in exclude_doc_ids
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored

    def rank(
        self,
        query_text: str,
        *,
        top_k: int,
        exclude_doc_ids: frozenset[str] | set[str] = frozenset(),
    ) -> list[tuple[str, float]]:
        """Return the top-``top_k`` documents in canonical order (score desc, ID asc)."""
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise BM25DataError(f"top_k must be a positive integer; received {top_k!r}.")
        return self.score_query(query_text, exclude_doc_ids=exclude_doc_ids)[:top_k]


# ---------------------------------------------------------------------------
# Pilot pipeline
# ---------------------------------------------------------------------------


def _verify_locked_queries_covered(query_ids: Sequence[str], queries: Mapping[str, str]) -> None:
    """Every locked split query must exist in queries.jsonl; no silent drop."""
    missing = [qid for qid in query_ids if qid not in queries]
    if missing:
        raise BM25DataError(
            f"{len(missing)} locked split query IDs are absent from queries.jsonl "
            f"(first 5: {sorted(missing)[:5]})."
        )


def run_bm25_pilot(
    *,
    dataset: str,
    split: str,
    data_root: Path | str,
    splits_dir: Path | str,
    protocol_path: Path | str,
    output_dir: Path | str,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Run the full BM25 pilot for one dataset split and return a run summary.

    Stages: (1) pin the protocol lexical contract, (2) verify the split
    manifest and SHA-256 of its input files, (3) load the full corpus and the
    locked queries, (4) build the BM25 index and rank every locked query
    (qrels are not read at any point so far), (5) record rankings in a fresh
    immutable run, (6) load qrels and evaluate with :class:`ProtocolEvaluator`,
    (7) seal the run with aggregate metrics. Failures after stage (5) mark the
    run FAILED with a preserved error; any failure exits the CLI with code 1.
    ``synthetic=True`` marks the run manifest as fixture data (tests only);
    it must never be set for benchmark measurements.
    """
    config = load_protocol_lexical_config(Path(protocol_path))
    manifest = load_split_manifest(
        Path(splits_dir) / f"{dataset}_{split}.json",
        dataset=dataset,
        split=split,
    )
    corpus = load_corpus(Path(data_root) / dataset / "corpus.jsonl", dataset=dataset)
    queries = load_queries(manifest.queries_path, dataset=dataset)
    _verify_locked_queries_covered(manifest.query_ids, queries)
    query_texts = {qid: queries[qid] for qid in manifest.query_ids}
    corpus_sha256 = sha256_file(Path(data_root) / dataset / "corpus.jsonl")

    index = BM25Index(corpus.texts, k1=config.k1, b=config.b)

    store = RunStore(Path(output_dir))
    command = [sys.executable, "-m", "scholargraph.retrieval.bm25", *sys.argv[1:]]
    resolved_config: dict[str, Any] = {
        "method": "bm25",
        "dataset": dataset,
        "split": split,
        "track": "A",
        "protocol_id": "scholargraph-research-v1",
        "protocol_source": str(Path(protocol_path)),
        "k1": config.k1,
        "b": config.b,
        "idf_formula": config.idf_formula,
        "query_terms": config.query_terms,
        "empty_corpus": config.empty_corpus,
        "tokenizer": {
            "case": config.tokenizer_case,
            "pattern": config.token_pattern,
            "stopwords": False,
            "stemming": False,
        },
        "text_fields": list(config.text_fields),
        "field_joiner": config.field_joiner,
        "missing_field_policy": config.missing_field,
        "top_k": config.top_k,
        "full_corpus_index": True,
        "corpus_file": str(Path(data_root) / dataset / "corpus.jsonl"),
        "corpus_sha256": corpus_sha256,
        "queries_file": str(manifest.queries_path),
        "queries_sha256": manifest.queries_sha256,
        "qrels_file": str(manifest.qrels_path),
        "qrels_sha256": manifest.qrels_sha256,
        "split_manifest_sha256": manifest.manifest_sha256,
        "corpus_count": corpus.document_count,
        "query_count": manifest.query_count,
        "qrel_count": manifest.qrel_count,
        "corpus_missing_title_count": corpus.missing_title_count,
        "corpus_missing_abstract_count": corpus.missing_abstract_count,
        "index_vocabulary_size": index.vocabulary_size,
        "ranking_reads_qrels": False,
        "module_version": MODULE_VERSION,
    }
    handle = store.create(
        method="bm25",
        dataset=dataset,
        split=split,
        resolved_config=resolved_config,
        data_source=Path(data_root) / dataset / "corpus.jsonl",
        split_definition=Path(splits_dir) / f"{dataset}_{split}.json",
        code_source=Path(__file__),
        model={"id": "bm25-protocol-v1", "revision": MODULE_VERSION},
        seed=PROTOCOL_SEED,
        command=command,
        protocol_source=Path(protocol_path),
        synthetic=synthetic,
        extra_hash_sources={
            "queries_file": manifest.queries_path,
            "qrels_file": manifest.qrels_path,
            "evaluator_source": EVALUATOR_SOURCE_PATH,
        },
    )
    try:
        # ---- Ranking path: corpus + query text only. Qrels are NOT read here. ----
        rankings: list[RankingResult] = []
        for query_id in manifest.query_ids:
            hits = index.rank(
                query_texts[query_id],
                top_k=config.top_k,
                # Track A self policy: exclude a document whose canonical ID
                # equals the query ID (BEIR convention).
                exclude_doc_ids=frozenset({query_id}),
            )
            rankings.append(
                RankingResult.create_sorted(query_id, [(doc_id, score, None) for doc_id, score in hits])
            )
        handle.record_rankings(rankings)

        # ---- Evaluation path: qrels consumed only here, after rankings are recorded. ----
        qrels, qrel_row_count = load_qrels(
            manifest.qrels_path,
            dataset=dataset,
            corpus_ids=corpus.texts,
            query_ids=set(manifest.query_ids),
        )
        if qrel_row_count != manifest.qrel_count:
            raise BM25DataError(
                f"Qrels row count {qrel_row_count} does not match manifest qrel_count "
                f"{manifest.qrel_count} for {manifest.qrels_path}."
            )
        evaluator = ProtocolEvaluator()
        evaluation = evaluator.evaluate(
            {result.query_id: result for result in rankings},
            qrels,
            query_ids=list(manifest.query_ids),
            corpus_ids=list(corpus.texts.keys()),
            track="A",
        )
        handle.record_per_query(evaluation["per_query"])
        aggregate_metrics = {name: float(value) for name, value in evaluation["aggregate"].items()}
    except BaseException as exc:  # noqa: BLE001 - preserve failure evidence then re-raise
        handle.fail(exc)
        raise

    # Input files must be unchanged after the run (before/after hash check).
    post_queries_sha256 = sha256_file(manifest.queries_path)
    post_qrels_sha256 = sha256_file(manifest.qrels_path)
    post_corpus_sha256 = sha256_file(Path(data_root) / dataset / "corpus.jsonl")
    if (post_queries_sha256, post_qrels_sha256, post_corpus_sha256) != (
        manifest.queries_sha256,
        manifest.qrels_sha256,
        corpus_sha256,
    ):
        raise BM25DataError("Input files changed during the run; refusing to seal a completed run.")
    handle.append_log(
        "post-run input hash check OK: "
        f"corpus={corpus_sha256}, queries={post_queries_sha256}, qrels={post_qrels_sha256}"
    )
    completed = handle.complete(aggregate_metrics)

    return {
        "module_version": MODULE_VERSION,
        "evaluator_version": evaluation["evaluator_version"],
        "run_id": completed["run_id"],
        "run_dir": str(handle.path),
        "status": completed["status"],
        "dataset": dataset,
        "split": split,
        "counts": {
            "corpus": corpus.document_count,
            "queries": manifest.query_count,
            "qrels": manifest.qrel_count,
            "qrels_rows_loaded": qrel_row_count,
            "locked_ranked_queries": len(rankings),
        },
        "coverage": {
            "corpus_missing_title": corpus.missing_title_count,
            "corpus_missing_abstract": corpus.missing_abstract_count,
        },
        "config": {
            "k1": config.k1,
            "b": config.b,
            "idf_formula": config.idf_formula,
            "query_terms": config.query_terms,
            "tokenizer": {
                "case": config.tokenizer_case,
                "pattern": config.token_pattern,
                "stopwords": False,
                "stemming": False,
            },
            "top_k": config.top_k,
        },
        "aggregate_metrics": aggregate_metrics,
        "evaluation_audit": {
            "no_positive_qrels_count": evaluation["audit"]["no_positive_qrels_count"],
            "missing_ranking_count": evaluation["audit"]["missing_ranking_count"],
            "empty_ranking_count": evaluation["audit"]["empty_ranking_count"],
        },
        "artifact_hashes": {
            "rankings.jsonl": completed["artifacts"]["rankings.jsonl"]["sha256"],
            "per_query.json": completed["artifacts"]["per_query.json"]["sha256"],
        },
        "input_sha256": {
            "corpus.jsonl": corpus_sha256,
            "queries.jsonl": manifest.queries_sha256,
            "qrels": manifest.qrels_sha256,
            "split_manifest": manifest.manifest_sha256,
        },
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the module CLI."""
    parser = argparse.ArgumentParser(
        prog="scholargraph.retrieval.bm25",
        description=(
            "Deterministic BM25 pilot per Research Protocol v1 (SG-012). "
            "Ranks the locked split queries over the full corpus; qrels are read "
            "only by the evaluator after rankings are recorded."
        ),
    )
    parser.add_argument("--dataset", required=True, choices=["scifact", "scidocs"], help="BEIR dataset name.")
    parser.add_argument("--split", required=True, help="Locked split name from data/splits (e.g. dev).")
    parser.add_argument("--data-root", default="data/raw/beir", help="Root of the frozen BEIR snapshot.")
    parser.add_argument("--splits-dir", default="data/splits", help="Directory of locked split manifests.")
    parser.add_argument("--protocol", default="configs/protocol_v1.json", help="Protocol JSON file.")
    parser.add_argument("--output-dir", default="artifacts/runs", help="RunStore root for run directories.")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Mark the run manifest synthetic=True (fixture/testing use only; never for benchmarks).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns process exit code (0 success, 1 failure)."""
    args = build_argument_parser().parse_args(argv)
    try:
        summary = run_bm25_pilot(
            dataset=args.dataset,
            split=args.split,
            data_root=Path(args.data_root),
            splits_dir=Path(args.splits_dir),
            protocol_path=Path(args.protocol),
            output_dir=Path(args.output_dir),
            synthetic=args.synthetic,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report and fail loudly
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
