"""Deterministic TF-IDF retrieval per Research Protocol v1 — task SG-018.

Contract implemented (``configs/protocol_v1.json`` -> ``retrieval.lexical``):

- Tokenizer and corpus fields are **reused verbatim from the SG-012 BM25
  module** through imports (``scholargraph.retrieval.bm25``), so TF-IDF and
  BM25 consume exactly the same inputs: unicode ``casefold`` + token regex
  ``(?u)\\b\\w+\\b``, no stopwords, no stemming, ``title + " " + abstract``,
  missing field -> empty string with coverage counters. The full lexical
  contract (including the sibling ``bm25`` block) is validated by the shared
  loader, so the two baselines can never drift apart on inputs.
- TF-IDF (block ``retrieval.lexical.tfidf``):
  ``tf = 1 + ln(f)`` for ``f > 0`` (logarithmic, unbounded growth),
  ``idf = ln((N + 1) / (df + 1)) + 1`` (>= 1, strictly positive for every
  ``0 <= df <= N``), ``normalization = l2`` on query and document vectors,
  ``similarity = cosine``.
- Vector space: the corpus vocabulary. A query term outside the corpus
  vocabulary is dropped from the query vector before l2 normalization (it has
  no document component anywhere, so it cannot contribute to any dot product);
  the number of dropped OOV tokens is counted per query and reported in the
  diagnostics. This never changes the ranking: keeping OOV mass in the query
  norm would only scale every score of that query by one per-query constant.
- ``empty_vector_score = 0``: every document of the corpus receives a cosine
  score for every query. A document whose token list is empty has a zero
  vector; its score is defined as 0.0 and it is **not dropped** — it stays in
  the canonical ranking, tie-broken by canonical document ID. Documents that
  share no query term are orthogonal to the query (cosine exactly 0.0) and are
  ranked the same way. The tail of a TF-IDF ranking is therefore a score-0 tie
  broken by doc ID, unlike BM25 which leaves non-matching documents unranked;
  the run diagnostics quantify these "padded" top-k slots.
- A query with zero tokens after tokenization is a loud error (same policy as
  BM25, so both baselines fail identically on the same inputs). A query whose
  tokens are all out-of-vocabulary yields the all-zero score vector and is
  counted in the diagnostics (never silently hidden).
- Ranking order: score descending, ties broken by canonical doc ID ascending
  (Unicode code points); all accumulation uses :func:`math.fsum` in sorted
  term order, so results are deterministic across runs.

Leakage boundary (identical to SG-012 BM25, Protocol v1
``data_access.ranker_forbidden``): the ranking path reads only the corpus and
the query texts. Qrels are opened exactly once, after rankings have been
recorded, and only to feed
``scholargraph.evaluation.metrics.ProtocolEvaluator``. The split manifest is
verified by SHA-256 (queries and qrels files) before any use; a hash mismatch
or any missing/ill-formed mandatory resource fails the CLI with exit code 1.
Ranking provenance is stored through ``scholargraph.evaluation.runner.RunStore``
(run ID, index hash, input hashes, seed, command, artifacts, terminal seal);
completed runs are never overwritten — a re-run allocates a new run ID.

CLI example (from the project root):

    PYTHONPATH=src ./.venv/Scripts/python.exe -m scholargraph.retrieval.tfidf \
        --dataset scifact --split dev --output-dir artifacts/runs
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator
from scholargraph.evaluation.runner import RunStore, sha256_value
from scholargraph.ingest.beir_loader import sha256_file
from scholargraph.retrieval.bm25 import (
    BM25ConfigError,
    BM25DataError,
    BM25EmptyQueryError,  # noqa: F401  (re-exported contract twin of TFIDFEmptyQueryError)
    EVALUATOR_SOURCE_PATH,
    PROTOCOL_SEED,
    _load_strict_json,
    _verify_locked_queries_covered,
    load_corpus,
    load_protocol_lexical_config,
    load_qrels,
    load_queries,
    load_split_manifest,
    tokenize,
)

MODULE_VERSION = "sg018-1.0.0"

# Exact lexical contract this module supports; any protocol deviation fails loudly.
SUPPORTED_TF_FORMULA = "1+ln(f) for f>0"
SUPPORTED_TFIDF_IDF_FORMULA = "ln((N+1)/(df+1))+1"
SUPPORTED_NORMALIZATION = "l2"
SUPPORTED_SIMILARITY = "cosine"
SUPPORTED_EMPTY_VECTOR_SCORE = 0


class TFIDFConfigError(ValueError):
    """Raised when the protocol file deviates from the supported TF-IDF contract."""


class TFIDFDataError(ValueError):
    """Raised when a mandatory input resource is missing or ill-formed."""


class TFIDFEmptyQueryError(ValueError):
    """Raised when a query yields zero tokens after protocol tokenization."""


def _wrap_data_error(exc: BM25DataError) -> TFIDFDataError:
    """Translate a shared-loader error into this module's error type, 1:1."""
    return TFIDFDataError(str(exc))


# ---------------------------------------------------------------------------
# Protocol configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TFIDFProtocolConfig:
    """Resolved TF-IDF configuration pinned to the exact Protocol v1 strings."""

    top_k: int
    tokenizer_case: str
    token_pattern: str
    text_fields: tuple[str, ...]
    field_joiner: str
    missing_field: str
    tf_formula: str
    idf_formula: str
    normalization: str
    similarity: str
    empty_vector_score: int


def load_protocol_tfidf_config(path: Path | str) -> TFIDFProtocolConfig:
    """Read and pin the TF-IDF retrieval contract from the protocol file.

    The tokenizer/text-field contract (and the sibling ``bm25`` block that
    pins the shared inputs) is validated by ``load_protocol_lexical_config``;
    the ``tfidf`` block itself must match the exact protocol strings or
    :class:`TFIDFConfigError` is raised. No value is silently defaulted.
    """
    try:
        shared = load_protocol_lexical_config(path)
    except (BM25ConfigError, BM25DataError) as exc:
        raise TFIDFConfigError(str(exc)) from exc

    try:
        data = _load_strict_json(Path(path))
    except BM25DataError as exc:
        raise TFIDFConfigError(str(exc)) from exc
    try:
        tfidf = data["retrieval"]["lexical"]["tfidf"]
    except (KeyError, TypeError) as exc:
        raise TFIDFConfigError(f"Protocol section retrieval.lexical.tfidf is missing or invalid: {exc!r}") from exc
    if not isinstance(tfidf, Mapping):
        raise TFIDFConfigError("Protocol section retrieval.lexical.tfidf must be an object.")

    def _require(key: str) -> Any:
        if key not in tfidf:
            raise TFIDFConfigError(f"Protocol section tfidf.{key!r} is missing.")
        return tfidf[key]

    def _require_exact_string(value: Any, context: str, supported: str) -> str:
        if not isinstance(value, str) or value == "":
            raise TFIDFConfigError(f"Protocol value {context} must be a non-empty string.")
        if value != supported:
            raise TFIDFConfigError(f"Unsupported {context} {value!r}; expected {supported!r}.")
        return value

    tf_formula = _require_exact_string(_require("tf"), "tfidf.tf", SUPPORTED_TF_FORMULA)
    idf_formula = _require_exact_string(_require("idf"), "tfidf.idf", SUPPORTED_TFIDF_IDF_FORMULA)
    normalization = _require_exact_string(
        _require("normalization"), "tfidf.normalization", SUPPORTED_NORMALIZATION
    )
    similarity = _require_exact_string(_require("similarity"), "tfidf.similarity", SUPPORTED_SIMILARITY)
    empty_vector_score = _require("empty_vector_score")
    if isinstance(empty_vector_score, bool) or not isinstance(empty_vector_score, (int, float)):
        raise TFIDFConfigError(
            f"Protocol value tfidf.empty_vector_score must be the number 0; received {empty_vector_score!r}."
        )
    if float(empty_vector_score) != float(SUPPORTED_EMPTY_VECTOR_SCORE):
        raise TFIDFConfigError(f"Unsupported empty_vector_score {empty_vector_score!r}; expected 0.")

    return TFIDFProtocolConfig(
        top_k=shared.top_k,
        tokenizer_case=shared.tokenizer_case,
        token_pattern=shared.token_pattern,
        text_fields=shared.text_fields,
        field_joiner=shared.field_joiner,
        missing_field=shared.missing_field,
        tf_formula=tf_formula,
        idf_formula=idf_formula,
        normalization=normalization,
        similarity=similarity,
        empty_vector_score=int(empty_vector_score),
    )


# ---------------------------------------------------------------------------
# TF-IDF index
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryVectorStats:
    """Measured per-query token statistics (diagnostics; never used to rank)."""

    token_count: int
    unique_token_count: int
    oov_token_count: int
    in_vocab_term_count: int
    empty_query_vector: bool


class TFIDFIndex:
    """Protocol v1 l2-normalized log TF-IDF index over a full corpus (deterministic)."""

    def __init__(self, documents: Mapping[str, str]) -> None:
        if not documents:
            raise TFIDFDataError("TF-IDF index requires a non-empty corpus (empty_corpus=fail).")

        document_count = len(documents)
        postings: dict[str, list[tuple[str, int]]] = {}
        doc_lengths: dict[str, int] = {}
        doc_term_frequencies: dict[str, dict[str, int]] = {}
        zero_token_docs: list[str] = []
        for doc_id in sorted(documents):
            tokens = tokenize(documents[doc_id])
            doc_lengths[doc_id] = len(tokens)
            term_frequencies: dict[str, int] = {}
            for token in tokens:
                term_frequencies[token] = term_frequencies.get(token, 0) + 1
            doc_term_frequencies[doc_id] = term_frequencies
            if not term_frequencies:
                zero_token_docs.append(doc_id)
            for term in sorted(term_frequencies):
                postings.setdefault(term, []).append((doc_id, term_frequencies[term]))
        total_length = sum(doc_lengths.values())
        if total_length == 0:
            raise TFIDFDataError(
                "Tokenizer produced an empty vocabulary over the whole corpus; "
                "no TF-IDF vector could be normalized."
            )
        self.document_count = document_count
        self._doc_lengths = doc_lengths
        self._postings = postings
        self._inverse_document_frequency: dict[str, float] = {
            term: self._log_idf(len(entry), document_count) for term, entry in postings.items()
        }
        self.vocabulary_size = len(postings)
        self.total_token_count = total_length
        self.zero_token_document_ids = tuple(zero_token_docs)

        # l2 norm of every document vector: sqrt(sum_t ((1+ln tf_td) * idf_t)^2)
        # with math.fsum over sorted terms for bitwise determinism. A zero-token
        # document has norm 0.0 (empty vector; score fixed at 0.0 by contract).
        self._doc_norms: dict[str, float] = {}
        for doc_id in sorted(documents):
            frequencies = doc_term_frequencies[doc_id]
            norm_squared = math.fsum(
                self._term_weight(frequencies[term], self._inverse_document_frequency[term]) ** 2
                for term in sorted(frequencies)
            )
            self._doc_norms[doc_id] = math.sqrt(norm_squared)

    @staticmethod
    def _term_weight(term_frequency: int, idf_value: float) -> float:
        """Protocol tf weight: (1 + ln f) * idf for f > 0."""
        return (1.0 + math.log(term_frequency)) * idf_value

    @staticmethod
    def _log_idf(df: int, document_count: int) -> float:
        """idf = ln((N + 1) / (df + 1)) + 1; >= 1 and strictly positive."""
        value = math.log((document_count + 1) / (df + 1)) + 1.0
        if not math.isfinite(value) or value < 1.0:
            raise TFIDFDataError(f"Non-finite or sub-unit idf computed for df={df}, N={document_count}.")
        return value

    @property
    def idf(self) -> Mapping[str, float]:
        """Read-only copy of the term -> log-idf table."""
        return dict(self._inverse_document_frequency)

    def document_frequency(self, term: str) -> int:
        """Document frequency of one term (0 when outside the vocabulary)."""
        entry = self._postings.get(term)
        return len(entry) if entry is not None else 0

    def has_document(self, doc_id: str) -> bool:
        """True when ``doc_id`` is part of the indexed corpus."""
        return doc_id in self._doc_lengths

    def state_hash(self, *, corpus_sha256: str, config: TFIDFProtocolConfig) -> str:
        """SHA-256 of the full index state plus its configuration.

        Covers document frequencies of every vocabulary term, every document
        length and norm, aggregate counters and the resolved protocol config,
        so two indexes hash identically only when they are interchangeable
        given the same hashed corpus.
        """
        state = {
            "method": "tfidf",
            "module_version": MODULE_VERSION,
            "config": {
                "tf_formula": config.tf_formula,
                "idf_formula": config.idf_formula,
                "normalization": config.normalization,
                "similarity": config.similarity,
                "empty_vector_score": config.empty_vector_score,
                "tokenizer_case": config.tokenizer_case,
                "token_pattern": config.token_pattern,
                "text_fields": list(config.text_fields),
                "field_joiner": config.field_joiner,
                "missing_field": config.missing_field,
                "top_k": config.top_k,
            },
            "corpus_sha256": corpus_sha256,
            "document_count": self.document_count,
            "vocabulary_size": self.vocabulary_size,
            "total_token_count": self.total_token_count,
            "document_frequencies": {term: len(entry) for term, entry in sorted(self._postings.items())},
            "document_lengths": dict(sorted(self._doc_lengths.items())),
            "document_norms": {doc_id: repr(norm) for doc_id, norm in sorted(self._doc_norms.items())},
        }
        return sha256_value(state)

    def query_vector_stats(self, query_text: str) -> QueryVectorStats:
        """Measured statistics of one query under the protocol tokenizer."""
        tokens = tokenize(query_text)
        if not tokens:
            raise TFIDFEmptyQueryError(
                "Query produced zero tokens under the Protocol v1 tokenizer; refusing to rank."
            )
        unique = set(tokens)
        in_vocab = [term for term in unique if term in self._postings]
        oov_token_count = sum(1 for token in tokens if token not in self._postings)
        return QueryVectorStats(
            token_count=len(tokens),
            unique_token_count=len(unique),
            oov_token_count=oov_token_count,
            in_vocab_term_count=len(in_vocab),
            empty_query_vector=len(in_vocab) == 0,
        )

    def _normalized_query_vector(self, query_text: str) -> tuple[dict[str, float], QueryVectorStats]:
        """l2-normalized query TF-IDF vector over the corpus vocabulary.

        Out-of-vocabulary query tokens are dropped (counted in the returned
        stats): they have no document component anywhere in the space. An
        all-OOV query yields an empty vector; every document then scores 0.0
        by the ``empty_vector_score = 0`` contract.
        """
        tokens = tokenize(query_text)
        if not tokens:
            raise TFIDFEmptyQueryError(
                "Query produced zero tokens under the Protocol v1 tokenizer; refusing to rank."
            )
        stats = self.query_vector_stats(query_text)
        term_frequencies: dict[str, int] = {}
        for token in tokens:
            term_frequencies[token] = term_frequencies.get(token, 0) + 1
        weights = {
            term: (1.0 + math.log(frequency)) * self._inverse_document_frequency[term]
            for term, frequency in sorted(term_frequencies.items())
            if term in self._postings
        }
        norm = math.sqrt(math.fsum(weight * weight for weight in weights.values()))
        if norm == 0.0:
            return {}, stats
        return {term: weight / norm for term, weight in weights.items()}, stats

    def score_query(
        self,
        query_text: str,
        *,
        exclude_doc_ids: frozenset[str] | set[str] = frozenset(),
    ) -> list[tuple[str, float]]:
        """Cosine similarity of the query with **every** corpus document.

        Matching documents accumulate ``q_t * (tf_td * idf_t) / ||d||`` over
        shared terms (``math.fsum`` in sorted term order); documents sharing no
        query term, including zero-token documents, score exactly 0.0 and stay
        in the ranking (``empty_vector_score = 0``). Excluded documents (Track A
        self policy) are omitted entirely.
        """
        normalized_query, _stats = self._normalized_query_vector(query_text)
        contributions: dict[str, list[float]] = {}
        for term in sorted(normalized_query):
            query_weight = normalized_query[term]
            idf_value = self._inverse_document_frequency[term]
            for doc_id, term_frequency in self._postings[term]:
                doc_weight = (
                    self._term_weight(term_frequency, idf_value) / self._doc_norms[doc_id]
                )
                contributions.setdefault(doc_id, []).append(query_weight * doc_weight)
        scored: list[tuple[str, float]] = []
        for doc_id in sorted(self._doc_lengths):
            if doc_id in exclude_doc_ids:
                continue
            values = contributions.get(doc_id)
            if values is not None and self._doc_norms[doc_id] != 0.0:
                score = math.fsum(values)
            else:
                # No shared term, or an empty (zero-token) document vector:
                # contract score 0, kept in the ranking.
                score = 0.0
            scored.append((doc_id, score))
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
            raise TFIDFDataError(f"top_k must be a positive integer; received {top_k!r}.")
        return self.score_query(query_text, exclude_doc_ids=exclude_doc_ids)[:top_k]


# ---------------------------------------------------------------------------
# Diagnostics (ties / filters) — measured, deterministic
# ---------------------------------------------------------------------------


def _tie_groups(scores: Sequence[float]) -> tuple[int, int, int, int]:
    """Return (tie_groups, tied_candidates, max_group_size, zero_tied_candidates).

    ``zero_tied_candidates`` counts candidates in the score-0.0 tie group when
    that group has more than one member, else 0.
    """
    counts: dict[float, int] = {}
    for score in scores:
        counts[score] = counts.get(score, 0) + 1
    group_sizes = [count for count in counts.values() if count > 1]
    zero_count = counts.get(0.0, 0)
    return (
        len(group_sizes),
        sum(group_sizes),
        max(group_sizes) if group_sizes else 0,
        zero_count if zero_count > 1 else 0,
    )


@dataclass(frozen=True)
class QueryDiagnostics:
    """Per-query ranking diagnostics for one TF-IDF run (measured only)."""

    query_id: str
    token_count: int
    unique_token_count: int
    oov_token_count: int
    empty_query_vector: bool
    matched_doc_count: int
    zero_score_in_top_k: int
    padded_slots: int
    tie_groups_in_top_k: int
    tied_candidates_in_top_k: int
    nonzero_tied_candidates_in_top_k: int
    max_tie_group_size_in_top_k: int
    zero_score_tied_in_top_k: int
    self_exclusion_applied: bool


def compute_query_diagnostics(
    *,
    index: TFIDFIndex,
    query_id: str,
    query_text: str,
    top_k: int,
    full_scores: Sequence[tuple[str, float]] | None = None,
    stats: QueryVectorStats | None = None,
) -> QueryDiagnostics:
    """Measure ties/filters for one query; the ranking itself is unchanged.

    ``full_scores``/``stats`` may be passed when the caller already computed
    :meth:`TFIDFIndex.score_query`/``query_vector_stats`` for this exact query
    with the same exclusion set, to avoid recomputation.
    """
    if full_scores is None:
        full_scores = index.score_query(query_text, exclude_doc_ids=frozenset({query_id}))
    if stats is None:
        stats = index.query_vector_stats(query_text)
    matched = sum(1 for _, score in full_scores if score > 0.0)
    top_scores = [score for _, score in full_scores[:top_k]]
    zero_in_top = sum(1 for score in top_scores if score == 0.0)
    groups, tied, max_group, zero_tied = _tie_groups(top_scores)
    return QueryDiagnostics(
        query_id=query_id,
        token_count=stats.token_count,
        unique_token_count=stats.unique_token_count,
        oov_token_count=stats.oov_token_count,
        empty_query_vector=stats.empty_query_vector,
        matched_doc_count=matched,
        zero_score_in_top_k=zero_in_top,
        padded_slots=max(0, top_k - matched),
        tie_groups_in_top_k=groups,
        tied_candidates_in_top_k=tied,
        nonzero_tied_candidates_in_top_k=max(0, tied - zero_tied),
        max_tie_group_size_in_top_k=max_group,
        zero_score_tied_in_top_k=zero_tied,
        self_exclusion_applied=index.has_document(query_id),
    )


def aggregate_diagnostics(
    per_query: Sequence[QueryDiagnostics],
    *,
    top_k: int,
    empty_vector_document_count: int,
) -> dict[str, Any]:
    """Aggregate per-query diagnostics into the report block (measured only)."""
    count = len(per_query)
    if count == 0:
        raise TFIDFDataError("No per-query diagnostics to aggregate; refusing to emit empty stats.")
    return {
        "query_count": count,
        "top_k": top_k,
        "zero_token_queries": sum(1 for row in per_query if row.token_count == 0),
        "empty_vector_documents": empty_vector_document_count,
        "queries_with_empty_query_vector_all_oov": sum(1 for row in per_query if row.empty_query_vector),
        "queries_with_oov_tokens": sum(1 for row in per_query if row.oov_token_count > 0),
        "total_oov_tokens": sum(row.oov_token_count for row in per_query),
        "mean_tokens_per_query": math.fsum(row.token_count for row in per_query) / count,
        "mean_matched_docs": math.fsum(row.matched_doc_count for row in per_query) / count,
        "queries_with_zero_score_in_top_k": sum(1 for row in per_query if row.zero_score_in_top_k > 0),
        "total_padded_slots": sum(row.padded_slots for row in per_query),
        "mean_padded_slots": math.fsum(row.padded_slots for row in per_query) / count,
        "queries_with_ties_in_top_k": sum(1 for row in per_query if row.tie_groups_in_top_k > 0),
        "queries_with_nonzero_ties_in_top_k": sum(
            1 for row in per_query if row.nonzero_tied_candidates_in_top_k > 0
        ),
        "total_tie_groups_in_top_k": sum(row.tie_groups_in_top_k for row in per_query),
        "total_tied_candidates_in_top_k": sum(row.tied_candidates_in_top_k for row in per_query),
        "max_tie_group_size_observed": max(row.max_tie_group_size_in_top_k for row in per_query),
        "queries_with_self_exclusion": sum(1 for row in per_query if row.self_exclusion_applied),
        "tie_break_policy": "score descending, then canonical doc ID ascending",
        "empty_vector_policy": "score 0.0, kept in ranking (empty_vector_score=0)",
        "zero_token_query_policy": "loud error (TFIDFEmptyQueryError), CLI exit 1",
    }


def _diagnostics_row(row: QueryDiagnostics, *, include_self_exclusion: bool = False) -> dict[str, Any]:
    payload = {
        "token_count": row.token_count,
        "unique_token_count": row.unique_token_count,
        "oov_token_count": row.oov_token_count,
        "empty_query_vector": row.empty_query_vector,
        "matched_doc_count": row.matched_doc_count,
        "padded_slots": row.padded_slots,
        "zero_score_in_top_k": row.zero_score_in_top_k,
        "tie_groups_in_top_k": row.tie_groups_in_top_k,
        "tied_candidates_in_top_k": row.tied_candidates_in_top_k,
        "nonzero_tied_candidates_in_top_k": row.nonzero_tied_candidates_in_top_k,
        "max_tie_group_size_in_top_k": row.max_tie_group_size_in_top_k,
    }
    if include_self_exclusion:
        payload["self_exclusion_applied"] = row.self_exclusion_applied
    return payload


# ---------------------------------------------------------------------------
# Pilot pipeline
# ---------------------------------------------------------------------------


def run_tfidf_pilot(
    *,
    dataset: str,
    split: str,
    data_root: Path | str,
    splits_dir: Path | str,
    protocol_path: Path | str,
    output_dir: Path | str,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Run the full TF-IDF pilot for one dataset split and return a run summary.

    Stages mirror ``run_bm25_pilot`` exactly: (1) pin the protocol contract,
    (2) verify the split manifest and SHA-256 of its input files, (3) load the
    full corpus and locked queries, (4) build the TF-IDF index and rank every
    locked query (qrels are not read at any point so far), (5) record rankings
    in a fresh immutable run, (6) load qrels and evaluate, (7) seal the run
    with aggregate metrics. Failures after stage (5) mark the run FAILED with a
    preserved error; any failure exits the CLI with code 1. ``synthetic=True``
    marks the run manifest as fixture data (tests only); it must never be set
    for benchmark measurements.
    """
    config = load_protocol_tfidf_config(Path(protocol_path))
    try:
        manifest = load_split_manifest(
            Path(splits_dir) / f"{dataset}_{split}.json",
            dataset=dataset,
            split=split,
        )
        corpus = load_corpus(Path(data_root) / dataset / "corpus.jsonl", dataset=dataset)
        queries = load_queries(manifest.queries_path, dataset=dataset)
        _verify_locked_queries_covered(manifest.query_ids, queries)
    except BM25DataError as exc:
        raise _wrap_data_error(exc) from exc
    query_texts = {qid: queries[qid] for qid in manifest.query_ids}
    corpus_path = Path(data_root) / dataset / "corpus.jsonl"
    corpus_sha256 = sha256_file(corpus_path)

    index = TFIDFIndex(corpus.texts)
    resolved_index_hash = index.state_hash(corpus_sha256=corpus_sha256, config=config)

    store = RunStore(Path(output_dir))
    command = [sys.executable, "-m", "scholargraph.retrieval.tfidf", *sys.argv[1:]]
    resolved_config: dict[str, Any] = {
        "method": "tfidf",
        "dataset": dataset,
        "split": split,
        "track": "A",
        "protocol_id": "scholargraph-research-v1",
        "protocol_source": str(Path(protocol_path)),
        "tf_formula": config.tf_formula,
        "idf_formula": config.idf_formula,
        "normalization": config.normalization,
        "similarity": config.similarity,
        "empty_vector_score": config.empty_vector_score,
        "query_terms": "tf_weighted_unique_terms",
        "empty_corpus": "fail",
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
        "corpus_file": str(corpus_path),
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
        "index_hash": resolved_index_hash,
        "index_vocabulary_size": index.vocabulary_size,
        "index_total_token_count": index.total_token_count,
        "index_zero_token_document_count": len(index.zero_token_document_ids),
        "ranking_reads_qrels": False,
        "shares_bm25_inputs": True,
        "module_version": MODULE_VERSION,
    }
    handle = store.create(
        method="tfidf",
        dataset=dataset,
        split=split,
        resolved_config=resolved_config,
        data_source=corpus_path,
        split_definition=Path(splits_dir) / f"{dataset}_{split}.json",
        code_source=Path(__file__),
        model={"id": "tfidf-protocol-v1", "revision": MODULE_VERSION},
        seed=PROTOCOL_SEED,
        command=command,
        protocol_source=Path(protocol_path),
        synthetic=synthetic,
        extra_hash_sources={
            "queries_file": manifest.queries_path,
            "qrels_file": manifest.qrels_path,
            "evaluator_source": EVALUATOR_SOURCE_PATH,
            "bm25_source": Path(__file__).resolve().parent / "bm25.py",
        },
    )
    try:
        # ---- Ranking path: corpus + query text only. Qrels are NOT read here. ----
        rankings: list[RankingResult] = []
        diagnostics: list[QueryDiagnostics] = []
        for query_id in manifest.query_ids:
            full_scores = index.score_query(query_texts[query_id], exclude_doc_ids=frozenset({query_id}))
            stats = index.query_vector_stats(query_texts[query_id])
            hits = full_scores[: config.top_k]
            rankings.append(
                RankingResult.create_sorted(query_id, [(doc_id, score, None) for doc_id, score in hits])
            )
            diagnostics.append(
                compute_query_diagnostics(
                    index=index,
                    query_id=query_id,
                    query_text=query_texts[query_id],
                    top_k=config.top_k,
                    full_scores=full_scores,
                    stats=stats,
                )
            )
        handle.record_rankings(rankings)
        handle.append_log(
            "diagnostics: "
            + json.dumps(
                {
                    "index_hash": resolved_index_hash,
                    "empty_vector_documents": len(index.zero_token_document_ids),
                    "queries_with_ties_in_top_k": sum(
                        1 for row in diagnostics if row.tie_groups_in_top_k > 0
                    ),
                    "queries_with_zero_score_in_top_k": sum(
                        1 for row in diagnostics if row.zero_score_in_top_k > 0
                    ),
                    "total_padded_slots": sum(row.padded_slots for row in diagnostics),
                    "queries_with_empty_query_vector_all_oov": sum(
                        1 for row in diagnostics if row.empty_query_vector
                    ),
                },
                sort_keys=True,
            )
        )

        # ---- Evaluation path: qrels consumed only here, after rankings are recorded. ----
        try:
            qrels, qrel_row_count = load_qrels(
                manifest.qrels_path,
                dataset=dataset,
                corpus_ids=corpus.texts,
                query_ids=set(manifest.query_ids),
            )
        except BM25DataError as exc:
            raise _wrap_data_error(exc) from exc
        if qrel_row_count != manifest.qrel_count:
            raise TFIDFDataError(
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

        diagnostics_block = aggregate_diagnostics(
            diagnostics,
            top_k=config.top_k,
            empty_vector_document_count=len(index.zero_token_document_ids),
        )
        diagnostics_block["empty_vector_document_ids_first5"] = list(index.zero_token_document_ids[:5])
        diagnostics_block["per_query_first10"] = {
            row.query_id: _diagnostics_row(row) for row in diagnostics[:10]
        }
        diagnostics_block["per_query_full"] = {
            row.query_id: _diagnostics_row(row, include_self_exclusion=True) for row in diagnostics
        }
    except BaseException as exc:  # noqa: BLE001 - preserve failure evidence then re-raise
        handle.fail(exc)
        raise

    # Input files must be unchanged after the run (before/after hash check).
    post_queries_sha256 = sha256_file(manifest.queries_path)
    post_qrels_sha256 = sha256_file(manifest.qrels_path)
    post_corpus_sha256 = sha256_file(corpus_path)
    if (post_queries_sha256, post_qrels_sha256, post_corpus_sha256) != (
        manifest.queries_sha256,
        manifest.qrels_sha256,
        corpus_sha256,
    ):
        raise TFIDFDataError("Input files changed during the run; refusing to seal a completed run.")
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
        "index_hash": resolved_index_hash,
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
            "tf_formula": config.tf_formula,
            "idf_formula": config.idf_formula,
            "normalization": config.normalization,
            "similarity": config.similarity,
            "empty_vector_score": config.empty_vector_score,
            "tokenizer": {
                "case": config.tokenizer_case,
                "pattern": config.token_pattern,
                "stopwords": False,
                "stemming": False,
            },
            "top_k": config.top_k,
        },
        "index": {
            "vocabulary_size": index.vocabulary_size,
            "total_token_count": index.total_token_count,
            "zero_token_document_count": len(index.zero_token_document_ids),
            "hash": resolved_index_hash,
        },
        "aggregate_metrics": aggregate_metrics,
        "evaluation_audit": {
            "no_positive_qrels_count": evaluation["audit"]["no_positive_qrels_count"],
            "missing_ranking_count": evaluation["audit"]["missing_ranking_count"],
            "empty_ranking_count": evaluation["audit"]["empty_ranking_count"],
        },
        "diagnostics": diagnostics_block,
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
        prog="scholargraph.retrieval.tfidf",
        description=(
            "Deterministic TF-IDF baseline per Research Protocol v1 (SG-018). "
            "Shares the BM25 corpus fields/tokenizer and inputs; ranks the locked "
            "split queries over the full corpus with l2-normalized log TF-IDF "
            "cosine similarity; qrels are read only by the evaluator after "
            "rankings are recorded."
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
        summary = run_tfidf_pilot(
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
