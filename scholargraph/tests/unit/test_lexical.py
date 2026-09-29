"""Adversarial and positive tests for the SG-018 TF-IDF baseline (Protocol v1).

Covers:
1. Exact Protocol v1 TF-IDF semantics (shared tokenizer with BM25, log tf,
   ``ln((N+1)/(df+1))+1`` idf, l2 normalization, cosine, hand-computed score,
   canonical ordering, self exclusion).
2. The ``empty_vector_score = 0`` contract: zero-token documents score 0.0 and
   are kept in the ranking; all-OOV queries produce the deterministic all-zero
   vector ranking; zero-token queries are a loud error (unit + CLI exit 1).
3. No-silent-bypass failures: missing resources, empty corpus, tampered
   SHA-256, malformed inputs, protocol deviations (tf/idf/normalization/
   similarity/empty_vector_score and the shared lexical contract).
4. Leakage: rankings must be byte-identical when qrels content changes (qrels
   are consumed only by the evaluator after rankings are recorded).
5. Reproducibility: two runs on the same fixture produce identical ranking and
   metric artifacts under distinct run IDs; the index hash is stable for the
   same inputs and changes with the corpus.
6. A real-data integration check that the frozen SciFact dev manifest counts
   (809 queries / 919 qrels / 5183 corpus docs) match the pipeline.

All fixtures are synthetic and written to ``tmp_path``; nothing is written
under ``data/raw``. CLI tests run through ``subprocess`` and assert exit codes
(0 on success, 1 on failure) per ADR-013.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.metrics import METRIC_NAMES, ProtocolEvaluator
from scholargraph.ingest.beir_loader import sha256_file
from scholargraph.retrieval import tfidf
from scholargraph.retrieval.bm25 import BM25DataError, tokenize as bm25_tokenize
from scholargraph.retrieval.tfidf import (
    TFIDFConfigError,
    TFIDFDataError,
    TFIDFEmptyQueryError,
    TFIDFIndex,
    compute_query_diagnostics,
    load_protocol_tfidf_config,
    run_tfidf_pilot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

QRELS_ROWS_DEFAULT = [
    ("10", "100", "2"),
    ("20", "300", "1"),
    ("30", "200", "0"),
]
# Completely different labels for the leakage test; same file shape.
QRELS_ROWS_TAMPERED_LABELS = [
    ("10", "200", "1"),
    ("20", "100", "2"),
    ("30", "100", "1"),
]

CORPUS_ROWS = [
    {"_id": "100", "title": "Graph neural networks for citation recommendation",
     "text": "Citation networks and graph convolutional models recommend related papers."},
    {"_id": "200", "title": "BM25 lexical ranking function",
     "text": "Term frequency and inverse document frequency drive lexical ranking."},
    {"_id": "300", "title": "Deep learning for protein structure prediction",
     "text": "Protein folding with deep neural networks predicts amino acid structure."},
    {"_id": "400", "title": "Attention mechanisms in transformers"},
    {"_id": "500", "text": "Self attention improves transformer language models."},
]

QUERY_ROWS = [
    {"_id": "10", "text": "Graph neural networks for citation recommendation"},
    {"_id": "20", "text": "protein structure prediction deep learning"},
    {"_id": "30", "text": "zooplankton ecology"},
]


# ---------------------------------------------------------------------------
# Synthetic fixture builders (tmp_path only; never data/raw)
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def _write_qrels(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{q}\t{d}\t{s}\n" for q, d, s in rows)
    path.write_text("query-id\tcorpus-id\tscore\n" + body, encoding="utf-8")
    return path


def _write_protocol(path: Path, *, top_k: int = 3) -> Path:
    protocol = {
        "retrieval": {
            "per_retriever_depth": top_k,
            "lexical": {
                "text_fields": ["title", "abstract"],
                "field_joiner": " ",
                "missing_field": "empty_string_report_coverage",
                "tokenizer": {
                    "case": "unicode_casefold",
                    "pattern": "(?u)\\b\\w+\\b",
                    "stopwords": False,
                    "stemming": False,
                },
                "tfidf": {
                    "tf": "1+ln(f) for f>0",
                    "idf": "ln((N+1)/(df+1))+1",
                    "normalization": "l2",
                    "similarity": "cosine",
                    "empty_vector_score": 0,
                },
                "bm25": {
                    "k1": 1.5,
                    "b": 0.75,
                    "idf": "ln(1+(N-df+0.5)/(df+0.5))",
                    "query_terms": "unique_tokens",
                    "empty_corpus": "fail",
                },
            },
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    return path


def _write_manifest(
    path: Path,
    *,
    queries_file: Path,
    qrels_file: Path,
    query_ids: list[str],
    qrel_count: int,
    queries_sha256: str | None = None,
    qrels_sha256: str | None = None,
) -> Path:
    manifest = {
        "schema_version": 1,
        "dataset": "scifact",
        "split": "dev",
        "raw_split_source": "train",
        "role": "development_and_tuning",
        "created_at": "2026-09-17T00:00:00+07:00",
        "query_count": len(query_ids),
        "qrel_count": qrel_count,
        "queries_file": queries_file.as_posix(),
        "queries_sha256": queries_sha256 or sha256_file(queries_file),
        "qrels_file": qrels_file.as_posix(),
        "qrels_sha256": qrels_sha256 or sha256_file(qrels_file),
        "query_ids": query_ids,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def build_fixture(
    root: Path,
    *,
    zero_token_query: bool = False,
    extra_zero_token_document: bool = False,
    qrels_rows: list[tuple[str, str, str]] | None = None,
    corpus_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """Create a synthetic SciFact-namespaced BEIR layout under ``root``."""
    rows = corpus_rows if corpus_rows is not None else list(CORPUS_ROWS)
    if extra_zero_token_document:
        rows = rows + [{"_id": "600", "title": "!!! ???"}]
    dataset_dir = root / "beir" / "scifact"
    corpus_path = _write_jsonl(dataset_dir / "corpus.jsonl", rows)
    query_rows = list(QUERY_ROWS)
    if zero_token_query:
        query_rows.append({"_id": "40", "text": "??!"})
    queries_path = _write_jsonl(dataset_dir / "queries.jsonl", query_rows)
    qrels_path = _write_qrels(dataset_dir / "qrels" / "dev.tsv", qrels_rows or QRELS_ROWS_DEFAULT)
    query_ids = sorted(f"beir:scifact:{row['_id']}" for row in query_rows)
    manifest_path = _write_manifest(
        root / "splits" / "scifact_dev.json",
        queries_file=queries_path,
        qrels_file=qrels_path,
        query_ids=query_ids,
        qrel_count=len(qrels_rows or QRELS_ROWS_DEFAULT),
    )
    protocol_path = _write_protocol(root / "protocol.json")
    return {
        "root": root,
        "corpus": corpus_path,
        "queries": queries_path,
        "qrels": qrels_path,
        "manifest": manifest_path,
        "protocol": protocol_path,
        "runs": root / "runs",
    }


def run_cli(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the module CLI through subprocess with the project src on PYTHONPATH."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.tfidf", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=600,
        check=False,
    )


def read_run_manifests(runs_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((runs_dir).glob("RUN-*/manifest.json"))
    ]


# ---------------------------------------------------------------------------
# Tokenizer and scoring semantics (positive tests)
# ---------------------------------------------------------------------------


def test_tokenizer_is_imported_verbatim_from_bm25() -> None:
    """Same-inputs requirement: TF-IDF must use the identical BM25 tokenizer."""
    assert tfidf.tokenize is bm25_tokenize
    assert tfidf.tokenize("Graph Neural NETWORKS") == ["graph", "neural", "networks"]
    assert tfidf.tokenize("Café GRUPOS! v2 _x 3D") == ["café", "grupos", "v2", "_x", "3d"]


def test_protocol_config_pins_exact_tfidf_contract() -> None:
    config = load_protocol_tfidf_config(PROJECT_ROOT / "configs" / "protocol_v1.json")
    assert config.tf_formula == "1+ln(f) for f>0"
    assert config.idf_formula == "ln((N+1)/(df+1))+1"
    assert config.normalization == "l2"
    assert config.similarity == "cosine"
    assert config.empty_vector_score == 0
    assert config.top_k == 100
    assert config.tokenizer_case == "unicode_casefold"
    assert config.token_pattern == r"(?u)\b\w+\b"
    assert config.text_fields == ("title", "abstract")
    assert config.field_joiner == " "


def test_log_idf_formula_values_and_positivity() -> None:
    docs = {"d1": "apple banana", "d2": "banana cherry", "d3": "banana apple"}
    index = TFIDFIndex(docs)
    n = 3
    # df=1 -> ln((N+1)/2)+1 ; df=N -> exactly 1.0; never below 1.
    assert index.idf["cherry"] == pytest.approx(math.log((n + 1) / 2) + 1.0, abs=1e-15)
    assert index.idf["apple"] == pytest.approx(math.log((n + 1) / 3) + 1.0, abs=1e-15)
    assert index.idf["banana"] == pytest.approx(1.0, abs=1e-15)  # df == N
    for term, idf_value in index.idf.items():
        assert math.isfinite(idf_value) and idf_value >= 1.0


def test_hand_computed_tfidf_cosine_matches_module() -> None:
    """Hand-derived example: 2 docs, query 'apple', every step by formula."""
    docs = {"d1": "apple banana apple", "d2": "banana cherry"}
    index = TFIDFIndex(docs)
    n = 2
    idf_apple = math.log((n + 1) / (1 + 1)) + 1.0
    idf_banana = math.log((n + 1) / (2 + 1)) + 1.0
    idf_cherry = math.log((n + 1) / (1 + 1)) + 1.0  # df(cherry) = 1

    # Document vectors: tf = 1 + ln(f); then l2 normalize.
    w_d1_apple = (1.0 + math.log(2.0)) * idf_apple
    w_d1_banana = (1.0 + math.log(1.0)) * idf_banana
    norm_d1 = math.sqrt(w_d1_apple**2 + w_d1_banana**2)
    w_d2_banana = idf_banana
    w_d2_cherry = (1.0 + math.log(1.0)) * idf_cherry
    norm_d2 = math.sqrt(w_d2_banana**2 + w_d2_cherry**2)

    # Query 'apple': tf = 1, idf = idf_apple; l2 normalize -> unit weight 1.
    expected_d1 = 1.0 * (w_d1_apple / norm_d1)
    expected_d2 = 0.0

    scored = index.score_query("apple")
    assert [doc_id for doc_id, _ in scored] == ["d1", "d2"]  # d2 kept with cosine 0
    assert scored[0][1] == pytest.approx(expected_d1, abs=1e-12)
    assert scored[1][1] == pytest.approx(expected_d2, abs=1e-15)
    # Cosine of l2-normalized vectors is within [0, 1].
    assert 0.0 <= scored[0][1] <= 1.0


def test_scores_are_cosines_within_unit_range() -> None:
    docs = {
        "d1": "alpha beta gamma",
        "d2": "alpha alpha alpha alpha alpha",
        "d3": "alpha beta delta epsilon zeta eta",
    }
    index = TFIDFIndex(docs)
    for query in ("alpha", "alpha beta", "alpha beta gamma delta epsilon zeta eta"):
        for _, score in index.score_query(query):
            assert math.isfinite(score)
            assert -1e-12 <= score <= 1.0 + 1e-12


def test_repeated_single_query_term_is_scale_invariant_under_l2() -> None:
    """1+ln(f) grows the query weight, but l2 normalization removes the scale."""
    docs = {"d1": "apple banana apple", "d2": "banana cherry"}
    index = TFIDFIndex(docs)
    single = index.score_query("apple")
    repeated = index.score_query("apple apple apple")
    assert single == repeated


def test_canonical_order_score_desc_then_doc_id_asc() -> None:
    docs = {"d2": "alpha beta", "d1": "alpha beta", "d3": "gamma"}
    index = TFIDFIndex(docs)
    scored = index.score_query("alpha")
    # d1 and d2 have identical vectors -> exact tie -> doc ID ascending.
    assert [doc_id for doc_id, _ in scored] == ["d1", "d2", "d3"]
    assert scored[0][1] == pytest.approx(scored[1][1], abs=0.0)
    assert scored[2][1] == 0.0  # d3 shares no term: cosine 0, still ranked


def test_full_corpus_scoring_returns_every_non_excluded_document() -> None:
    docs = {"d1": "alpha", "d2": "beta", "d3": "gamma", "d4": "delta"}
    index = TFIDFIndex(docs)
    scored = index.score_query("alpha")
    assert len(scored) == 4  # empty_vector_score=0: no document is dropped
    excluded = index.score_query("alpha", exclude_doc_ids={"d1"})
    assert len(excluded) == 3 and all(doc_id != "d1" for doc_id, _ in excluded)
    with pytest.raises(TFIDFDataError, match="top_k"):
        index.rank("alpha", top_k=0)


def test_top_k_truncation_and_self_exclusion() -> None:
    docs = {"d1": "apple banana apple", "d2": "apple", "d3": "banana", "d4": "epsilon"}
    index = TFIDFIndex(docs)
    ranked = index.rank("apple banana", top_k=4)
    # d1 matches both terms; d2/d3 share one term each with equal idf -> exact
    # tie broken by doc ID; d4 shares nothing -> cosine 0, kept at the tail.
    assert [doc_id for doc_id, _ in ranked][:3] == ["d1", "d2", "d3"]
    assert ranked[2][1] == pytest.approx(ranked[1][1], abs=0.0)
    assert ranked[3] == ("d4", 0.0)
    excluded = index.rank("apple banana", top_k=2, exclude_doc_ids={"d1"})
    assert [doc_id for doc_id, _ in excluded] == ["d2", "d3"]


# ---------------------------------------------------------------------------
# empty_vector_score = 0 and query edge cases
# ---------------------------------------------------------------------------


def test_zero_token_document_scored_zero_and_kept() -> None:
    docs = {"d1": "alpha beta", "d2": "!!! ???", "d3": "alpha"}
    index = TFIDFIndex(docs)
    assert index.zero_token_document_ids == ("d2",)
    assert index._doc_norms["d2"] == 0.0  # empty vector
    scored = index.score_query("alpha")
    rows = dict(scored)
    assert rows["d2"] == 0.0  # explicit contract score, not an error
    # d3 (alpha only) normalizes to 1.0 and beats d1 (diluted by beta).
    assert [doc_id for doc_id, _ in scored] == ["d3", "d1", "d2"]
    assert scored[-1] == ("d2", 0.0)


def test_all_oov_query_yields_deterministic_all_zero_ranking() -> None:
    """Tokens exist but none is in the vocabulary: cosine 0 everywhere, doc-ID order."""
    docs = {"d3": "alpha beta", "d1": "gamma", "d2": "alpha"}
    index = TFIDFIndex(docs)
    stats = index.query_vector_stats("zzz qqq")
    assert stats.empty_query_vector is True
    assert stats.token_count == 2 and stats.oov_token_count == 2
    scored = index.score_query("zzz qqq")
    assert [doc_id for doc_id, _ in scored] == ["d1", "d2", "d3"]
    assert all(score == 0.0 for _, score in scored)


def test_zero_token_query_raises_loudly() -> None:
    index = TFIDFIndex({"d1": "alpha beta"})
    with pytest.raises(TFIDFEmptyQueryError):
        index.score_query("!!!")
    with pytest.raises(TFIDFEmptyQueryError):
        index.rank("???", top_k=3)


def test_index_hash_stable_and_input_sensitive(tmp_path: Path) -> None:
    config = load_protocol_tfidf_config(_write_protocol(tmp_path / "protocol.json"))
    docs_a = {"d1": "alpha beta", "d2": "gamma"}
    docs_b = {"d1": "alpha beta", "d2": "gamma delta"}
    index_a1 = TFIDFIndex(docs_a)
    index_a2 = TFIDFIndex(dict(docs_a))
    index_b = TFIDFIndex(docs_b)
    hash_a1 = index_a1.state_hash(corpus_sha256="0" * 64, config=config)
    assert hash_a1 == index_a2.state_hash(corpus_sha256="0" * 64, config=config)
    assert hash_a1 != index_b.state_hash(corpus_sha256="0" * 64, config=config)
    assert hash_a1 != index_a1.state_hash(corpus_sha256="1" * 64, config=config)


# ---------------------------------------------------------------------------
# No-silent-bypass failures (unit level)
# ---------------------------------------------------------------------------


def test_empty_corpus_index_raises() -> None:
    with pytest.raises(TFIDFDataError, match="non-empty corpus"):
        TFIDFIndex({})


def test_empty_vocabulary_raises() -> None:
    with pytest.raises(TFIDFDataError, match="empty vocabulary"):
        TFIDFIndex({"d1": "!!! ???", "d2": "..."})


def test_missing_corpus_file_raises(tmp_path: Path) -> None:
    # Shared loader contract: load_corpus is the BM25 loader re-exported by the
    # tfidf module; the pilot pipeline wraps its errors as TFIDFDataError
    # (wrapped-error + exit 1 behavior is covered by the CLI tests below).
    with pytest.raises(BM25DataError, match="Missing corpus file"):
        tfidf.load_corpus(tmp_path / "absent" / "corpus.jsonl", dataset="scifact")


def test_missing_split_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(BM25DataError, match="Missing split manifest"):
        tfidf.load_split_manifest(tmp_path / "absent.json", dataset="scifact", split="dev")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"tf": "f"}, "Unsupported tfidf.tf"),
        ({"idf": "ln(N/(df+1))"}, "Unsupported tfidf.idf"),
        ({"normalization": "l1"}, "Unsupported tfidf.normalization"),
        ({"similarity": "dot"}, "Unsupported tfidf.similarity"),
        ({"empty_vector_score": 1}, "Unsupported empty_vector_score"),
        ({"empty_vector_score": "zero"}, "must be the number 0"),
    ],
)
def test_protocol_tfidf_deviations_raise(tmp_path: Path, mutation: dict[str, Any], match: str) -> None:
    protocol_path = _write_protocol(tmp_path / "protocol.json")
    data = json.loads(protocol_path.read_text(encoding="utf-8"))
    data["retrieval"]["lexical"]["tfidf"].update(mutation)
    protocol_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TFIDFConfigError, match=match):
        load_protocol_tfidf_config(protocol_path)


def test_protocol_missing_tfidf_block_raises(tmp_path: Path) -> None:
    protocol_path = _write_protocol(tmp_path / "protocol.json")
    data = json.loads(protocol_path.read_text(encoding="utf-8"))
    del data["retrieval"]["lexical"]["tfidf"]
    protocol_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TFIDFConfigError, match="tfidf"):
        load_protocol_tfidf_config(protocol_path)


def test_protocol_shared_lexical_deviations_raise(tmp_path: Path) -> None:
    """The shared BM25-validated contract (tokenizer/fields) guards TF-IDF too."""
    protocol_path = _write_protocol(tmp_path / "protocol.json")
    data = json.loads(protocol_path.read_text(encoding="utf-8"))
    data["retrieval"]["lexical"]["tokenizer"]["stemming"] = True
    protocol_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TFIDFConfigError, match="stemming"):
        load_protocol_tfidf_config(protocol_path)


def test_diagnostics_aggregation_rejects_empty_input() -> None:
    with pytest.raises(TFIDFDataError, match="No per-query diagnostics"):
        tfidf.aggregate_diagnostics([], top_k=3, empty_vector_document_count=0)


# ---------------------------------------------------------------------------
# End-to-end synthetic pipeline (direct call, synthetic=True)
# ---------------------------------------------------------------------------


def test_run_tfidf_pilot_synthetic_end_to_end(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    summary = run_tfidf_pilot(
        dataset="scifact",
        split="dev",
        data_root=fixture["root"] / "beir",
        splits_dir=fixture["root"] / "splits",
        protocol_path=fixture["protocol"],
        output_dir=fixture["runs"],
        synthetic=True,
    )
    assert summary["status"] == "COMPLETED"
    assert summary["counts"] == {
        "corpus": 5,
        "queries": 3,
        "qrels": 3,
        "qrels_rows_loaded": 3,
        "locked_ranked_queries": 3,
    }
    assert summary["coverage"] == {"corpus_missing_title": 1, "corpus_missing_abstract": 1}
    assert set(summary["aggregate_metrics"]) == set(METRIC_NAMES)
    assert all(0.0 <= value <= 1.0 for value in summary["aggregate_metrics"].values())
    assert summary["evaluation_audit"]["no_positive_qrels_count"] == 1  # query 30
    # empty_vector_score=0: query 30 is all-OOV, so its top-3 is the doc-ID tie
    # at 0.0 -- never an empty ranking, unlike BM25.
    assert summary["evaluation_audit"]["empty_ranking_count"] == 0

    manifests = read_run_manifests(fixture["runs"])
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest["status"] == "COMPLETED"
    assert manifest["synthetic"] is True
    assert manifest["method"] == "tfidf"
    assert manifest["run_id"] == summary["run_id"]
    assert manifest["resolved_config"]["corpus_count"] == 5
    assert manifest["resolved_config"]["ranking_reads_qrels"] is False
    assert manifest["resolved_config"]["index_hash"] == summary["index_hash"]
    assert len(manifest["resolved_config"]["index_hash"]) == 64
    assert manifest["seed"] == 20260915

    rankings_path = fixture["runs"] / manifest["run_id"] / "rankings.jsonl"
    rankings = [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines()]
    by_query = {row["query_id"]: row for row in rankings}
    top_ids = [item["doc_id"] for item in by_query["beir:scifact:10"]["candidates"]]
    assert "beir:scifact:100" in top_ids[:3]
    # All-OOV query 30: deterministic doc-ID-ascending zero-score ranking.
    q30 = [item["doc_id"] for item in by_query["beir:scifact:30"]["candidates"]]
    assert q30 == sorted(q30) and len(q30) == 3
    assert all(item["score"] == 0.0 for item in by_query["beir:scifact:30"]["candidates"])

    diagnostics = summary["diagnostics"]
    assert diagnostics["query_count"] == 3
    assert diagnostics["queries_with_empty_query_vector_all_oov"] == 1  # query 30
    assert diagnostics["queries_with_ties_in_top_k"] >= 1
    assert diagnostics["tie_break_policy"].startswith("score descending")


def test_run_tfidf_pilot_records_empty_vector_document(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path, extra_zero_token_document=True)
    summary = run_tfidf_pilot(
        dataset="scifact",
        split="dev",
        data_root=fixture["root"] / "beir",
        splits_dir=fixture["root"] / "splits",
        protocol_path=fixture["protocol"],
        output_dir=fixture["runs"],
        synthetic=True,
    )
    assert summary["status"] == "COMPLETED"
    assert summary["counts"]["corpus"] == 6
    assert summary["diagnostics"]["empty_vector_documents"] == 1
    assert summary["diagnostics"]["empty_vector_document_ids_first5"] == ["beir:scifact:600"]
    assert summary["diagnostics"]["queries_with_zero_score_in_top_k"] >= 1
    # The zero-token document is ranked (score 0), never dropped: with top_k=3
    # and few matching docs it can only appear via the score-0 tail, so also
    # verify directly that score_query keeps it for every fixture query.
    corpus = tfidf.load_corpus(fixture["corpus"], dataset="scifact")
    index = TFIDFIndex(corpus.texts)
    for query_id, text in (
        ("beir:scifact:10", "Graph neural networks for citation recommendation"),
        ("beir:scifact:30", "zooplankton ecology"),
    ):
        scored = index.score_query(text, exclude_doc_ids=frozenset({query_id}))
        assert ("beir:scifact:600", 0.0) in scored


def test_diagnostics_measure_ties_and_padding_on_fixture(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    corpus = tfidf.load_corpus(fixture["corpus"], dataset="scifact")
    index = TFIDFIndex(corpus.texts)
    row = compute_query_diagnostics(
        index=index,
        query_id="beir:scifact:30",
        query_text="zooplankton ecology",
        top_k=3,
    )
    # All-OOV query: every document ties at 0.0 in a single group.
    assert row.empty_query_vector is True
    assert row.matched_doc_count == 0
    assert row.tie_groups_in_top_k == 1
    assert row.tied_candidates_in_top_k == 3
    assert row.zero_score_tied_in_top_k == 3
    assert row.nonzero_tied_candidates_in_top_k == 0
    assert row.max_tie_group_size_in_top_k == 3
    assert row.padded_slots == 3


# ---------------------------------------------------------------------------
# CLI subprocess tests (ADR-013: exit codes)
# ---------------------------------------------------------------------------


def _cli_args(fixture: dict[str, Path]) -> list[str]:
    return [
        "--dataset", "scifact",
        "--split", "dev",
        "--data-root", str(fixture["root"] / "beir"),
        "--splits-dir", str(fixture["root"] / "splits"),
        "--protocol", str(fixture["protocol"]),
        "--output-dir", str(fixture["runs"]),
        "--synthetic",
    ]


def test_cli_success_exit_0(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    completed = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    manifests = read_run_manifests(fixture["runs"])
    assert len(manifests) == 1 and manifests[0]["status"] == "COMPLETED"
    run_dir = fixture["runs"] / summary["run_id"]
    assert (run_dir / "rankings.jsonl").is_file()
    assert (run_dir / "per_query.json").is_file()
    assert (run_dir / "seal.json").is_file()


def test_cli_missing_corpus_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    fixture["corpus"].unlink()
    completed = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


def test_cli_missing_split_manifest_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    fixture["manifest"].unlink()
    completed = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


@pytest.mark.parametrize("field", ["queries_sha256", "qrels_sha256"])
def test_cli_tampered_input_sha256_exit_1(tmp_path: Path, field: str) -> None:
    fixture = build_fixture(tmp_path)
    manifest_data = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
    manifest_data[field] = "0" * 64
    fixture["manifest"].write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    completed = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr
    assert "SHA-256 mismatch" in completed.stderr


def test_cli_empty_corpus_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    fixture["corpus"].write_text("", encoding="utf-8")
    completed = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


def test_cli_zero_token_query_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path, zero_token_query=True)
    completed = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr
    # The interrupted run is preserved as FAILED with its error recorded,
    # never silently discarded and never sealed COMPLETED.
    manifests = read_run_manifests(fixture["runs"])
    assert len(manifests) == 1
    assert manifests[0]["status"] == "FAILED"
    assert (fixture["runs"] / manifests[0]["run_id"] / "error.json").is_file()
    assert not (fixture["runs"] / manifests[0]["run_id"] / "per_query.json").is_file()


def test_cli_ranking_is_independent_of_qrels_content(tmp_path: Path) -> None:
    """Leakage: changing qrels content must not change recorded rankings."""
    fixture_a = build_fixture(tmp_path / "a", qrels_rows=QRELS_ROWS_DEFAULT)
    fixture_b = build_fixture(tmp_path / "b", qrels_rows=QRELS_ROWS_TAMPERED_LABELS)

    run_a = run_cli(_cli_args(fixture_a), cwd=tmp_path)
    run_b = run_cli(_cli_args(fixture_b), cwd=tmp_path)
    assert run_a.returncode == 0, run_a.stderr
    assert run_b.returncode == 0, run_b.stderr

    rankings_a = (fixture_a["runs"] / json.loads(run_a.stdout)["run_id"] / "rankings.jsonl").read_bytes()
    rankings_b = (fixture_b["runs"] / json.loads(run_b.stdout)["run_id"] / "rankings.jsonl").read_bytes()
    assert hashlib.sha256(rankings_a).hexdigest() == hashlib.sha256(rankings_b).hexdigest()

    manifest_a = read_run_manifests(fixture_a["runs"])[0]
    manifest_b = read_run_manifests(fixture_b["runs"])[0]
    # The two fixtures genuinely differ in qrels provenance, so identical
    # rankings cannot be explained by identical labels.
    assert manifest_a["hashes"]["qrels_file"] != manifest_b["hashes"]["qrels_file"]
    assert manifest_a["hashes"]["data"] == manifest_b["hashes"]["data"]
    assert manifest_a["hashes"]["queries_file"] == manifest_b["hashes"]["queries_file"]


def test_cli_rerun_is_reproducible_under_new_run_id(tmp_path: Path) -> None:
    """Reproducibility: a second run yields identical artifacts, new run ID."""
    fixture = build_fixture(tmp_path)
    first = run_cli(_cli_args(fixture), cwd=tmp_path)
    second = run_cli(_cli_args(fixture), cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    summary_first = json.loads(first.stdout)
    summary_second = json.loads(second.stdout)
    assert summary_first["run_id"] != summary_second["run_id"]

    run_dir_first = fixture["runs"] / summary_first["run_id"]
    run_dir_second = fixture["runs"] / summary_second["run_id"]
    assert (
        run_dir_first / "rankings.jsonl"
    ).read_bytes() == (run_dir_second / "rankings.jsonl").read_bytes()
    assert (
        run_dir_first / "per_query.json"
    ).read_bytes() == (run_dir_second / "per_query.json").read_bytes()
    assert summary_first["aggregate_metrics"] == summary_second["aggregate_metrics"]
    assert summary_first["index_hash"] == summary_second["index_hash"]
    assert summary_first["artifact_hashes"]["rankings.jsonl"] == (
        summary_second["artifact_hashes"]["rankings.jsonl"]
    )

    manifests = read_run_manifests(fixture["runs"])
    assert len(manifests) == 2
    assert {m["run_id"] for m in manifests} == {
        summary_first["run_id"],
        summary_second["run_id"],
    }


def test_ranking_result_factory_respects_canonical_order() -> None:
    docs = {"d1": "alpha beta", "d2": "alpha beta", "d3": "alpha gamma"}
    index = TFIDFIndex(docs)
    hits = index.rank("alpha", top_k=3)
    result = RankingResult.create_sorted("q1", [(doc_id, score, None) for doc_id, score in hits])
    assert [item.doc_id for item in result.candidates] == [doc_id for doc_id, _ in hits]


# ---------------------------------------------------------------------------
# Real frozen SciFact dev integration (read-only; no run directories created)
# ---------------------------------------------------------------------------


def test_real_scifact_dev_pipeline_matches_frozen_manifest() -> None:
    config = load_protocol_tfidf_config(PROJECT_ROOT / "configs" / "protocol_v1.json")
    manifest = tfidf.load_split_manifest(
        PROJECT_ROOT / "data" / "splits" / "scifact_dev.json", dataset="scifact", split="dev"
    )
    assert manifest.query_count == 809
    assert manifest.qrel_count == 919
    corpus = tfidf.load_corpus(
        PROJECT_ROOT / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl", dataset="scifact"
    )
    assert corpus.document_count == 5183
    queries = tfidf.load_queries(manifest.queries_path, dataset="scifact")
    assert all(qid in queries for qid in manifest.query_ids)

    index = TFIDFIndex(corpus.texts)
    assert index.vocabulary_size > 0
    qrels, row_count = tfidf.load_qrels(
        manifest.qrels_path, dataset="scifact", corpus_ids=corpus.texts, query_ids=set(manifest.query_ids)
    )
    assert row_count == 919

    rankings = []
    diagnostics = []
    for qid in manifest.query_ids:
        full_scores = index.score_query(queries[qid], exclude_doc_ids=frozenset({qid}))
        rankings.append(
            RankingResult.create_sorted(
                qid, [(doc_id, score, None) for doc_id, score in full_scores[: config.top_k]]
            )
        )
        diagnostics.append(
            compute_query_diagnostics(
                index=index,
                query_id=qid,
                query_text=queries[qid],
                top_k=config.top_k,
                full_scores=full_scores,
            )
        )
    evaluator = ProtocolEvaluator()
    evaluation = evaluator.evaluate(
        {result.query_id: result for result in rankings},
        qrels,
        query_ids=list(manifest.query_ids),
        corpus_ids=list(corpus.texts.keys()),
        track="A",
    )
    aggregate = evaluation["aggregate"]
    assert all(0.0 <= value <= 1.0 for value in aggregate.values())
    assert aggregate["nDCG@10"] > 0.0
    assert evaluation["audit"]["missing_ranking_count"] == 0

    # Measured diagnostics on the frozen dev split (mirrors the CLI run).
    assert sum(1 for row in diagnostics if row.token_count == 0) == 0
    assert len(index.zero_token_document_ids) == 0
    assert all(row.token_count >= 1 for row in diagnostics)
    assert all(row.matched_doc_count >= 0 for row in diagnostics)

    # Determinism: re-scoring one query reproduces the identical ordering.
    probe_qid = manifest.query_ids[0]
    again = index.rank(queries[probe_qid], top_k=config.top_k, exclude_doc_ids=frozenset({probe_qid}))
    first = [(item.doc_id, item.score) for item in next(
        r for r in rankings if r.query_id == probe_qid
    ).candidates]
    assert again == first
