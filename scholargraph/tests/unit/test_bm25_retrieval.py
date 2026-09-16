"""Adversarial and positive tests for the SG-012 BM25 pilot (Protocol v1).

Covers:
1. Exact Protocol v1 lexical semantics (tokenizer, positive IDF, unique query
   tokens, canonical ordering, hand-computed scores).
2. No-silent-bypass failures: missing resources, empty corpus, zero-token
   queries, tampered SHA-256, malformed qrels, protocol deviations.
3. Leakage: rankings must be byte-identical when qrels content changes
   (qrels are consumed only by the evaluator after rankings are recorded).
4. Reproducibility: two runs on the same fixture produce identical ranking
   and metric artifacts under distinct run IDs.
5. A real-data integration check that the frozen SciFact dev manifest counts
   (809 queries / 919 qrels / 5183 corpus docs) match the pipeline.

All fixtures are synthetic and written to ``tmp_path``; nothing is written
under ``data/raw``. CLI tests run through ``subprocess`` and assert exit
codes (0 on success, 1 on failure) per ADR-013.
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
from scholargraph.retrieval.bm25 import (
    BM25ConfigError,
    BM25DataError,
    BM25EmptyQueryError,
    BM25Index,
    load_corpus,
    load_protocol_lexical_config,
    load_qrels,
    load_queries,
    load_split_manifest,
    run_bm25_pilot,
    tokenize,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

K1 = 1.5
B = 0.75

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
                "bm25": {
                    "k1": K1,
                    "b": B,
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
        "created_at": "2026-09-16T00:00:00+07:00",
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
    qrels_rows: list[tuple[str, str, str]] | None = None,
) -> dict[str, Path]:
    """Create a synthetic SciFact-namespaced BEIR layout under ``root``."""
    dataset_dir = root / "beir" / "scifact"
    corpus_path = _write_jsonl(dataset_dir / "corpus.jsonl", CORPUS_ROWS)
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
        [sys.executable, "-m", "scholargraph.retrieval.bm25", *args],
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


def test_tokenizer_uses_casefold_and_word_regex() -> None:
    assert tokenize("Graph Neural NETWORKS") == ["graph", "neural", "networks"]
    # Unicode casefold, no stemming, punctuation dropped, digits/underscore kept.
    assert tokenize("Café GRUPOS! v2 _x 3D") == ["café", "grupos", "v2", "_x", "3d"]
    assert tokenize("networks network running") == ["networks", "network", "running"]


def test_idf_positive_across_document_frequencies() -> None:
    docs = {
        f"beir:scifact:d{i}": f"shared term doc{i}" for i in range(4)
    }
    docs["beir:scifact:d0"] = "shared unique0"
    index = BM25Index(docs, k1=K1, b=B)
    for term, idf in index.idf.items():
        assert math.isfinite(idf) and idf > 0.0
    # df == N ("shared" in all docs) must still be strictly positive.
    n = index.document_count
    expected = math.log(1.0 + (n - n + 0.5) / (n + 0.5))
    assert index.idf["shared"] == pytest.approx(expected, abs=1e-12)


def test_bm25_hand_computed_score_matches_protocol_formula() -> None:
    docs = {"d1": "apple banana apple", "d2": "banana cherry"}
    index = BM25Index(docs, k1=K1, b=B)
    n = 2
    avgdl = 2.5
    df_apple = 1
    idf_apple = math.log(1.0 + (n - df_apple + 0.5) / (df_apple + 0.5))
    f = 2
    doc_len = 3
    tf_factor = f * (K1 + 1) / (f + K1 * (1 - B + B * doc_len / avgdl))
    expected = idf_apple * tf_factor
    scored = index.score_query("apple")
    assert [doc_id for doc_id, _ in scored] == ["d1"]
    assert scored[0][1] == pytest.approx(expected, abs=1e-12)


def test_unique_query_tokens_counted_once() -> None:
    docs = {"d1": "apple banana apple", "d2": "banana cherry"}
    index = BM25Index(docs, k1=K1, b=B)
    assert index.score_query("apple apple apple") == index.score_query("apple")


def test_canonical_order_score_desc_then_doc_id_asc() -> None:
    docs = {"d2": "alpha beta", "d1": "alpha beta", "d3": "gamma"}
    index = BM25Index(docs, k1=K1, b=B)
    scored = index.score_query("alpha")
    assert [doc_id for doc_id, _ in scored] == ["d1", "d2"]
    assert scored[0][1] == pytest.approx(scored[1][1], abs=0.0)


def test_top_k_truncation_and_self_exclusion() -> None:
    docs = {"d1": "apple banana apple", "d2": "apple", "d3": "banana"}
    index = BM25Index(docs, k1=K1, b=B)
    assert [doc_id for doc_id, _ in index.rank("apple banana", top_k=2)] == ["d1", "d2"]
    excluded = index.rank("apple banana", top_k=2, exclude_doc_ids={"d1"})
    assert [doc_id for doc_id, _ in excluded] == ["d2", "d3"]


def test_ranking_result_factory_respects_canonical_order() -> None:
    docs = {"d1": "alpha beta", "d2": "alpha beta", "d3": "alpha gamma"}
    index = BM25Index(docs, k1=K1, b=B)
    hits = index.rank("alpha", top_k=3)
    result = RankingResult.create_sorted("q1", [(doc_id, score, None) for doc_id, score in hits])
    assert [item.doc_id for item in result.candidates] == [doc_id for doc_id, _ in hits]


# ---------------------------------------------------------------------------
# No-silent-bypass failures (unit level)
# ---------------------------------------------------------------------------


def test_empty_corpus_index_raises() -> None:
    with pytest.raises(BM25DataError, match="non-empty corpus"):
        BM25Index({}, k1=K1, b=B)


def test_empty_vocabulary_raises() -> None:
    with pytest.raises(BM25DataError, match="empty vocabulary"):
        BM25Index({"d1": "!!! ???", "d2": "..."}, k1=K1, b=B)


def test_zero_token_query_raises() -> None:
    index = BM25Index({"d1": "alpha beta"}, k1=K1, b=B)
    with pytest.raises(BM25EmptyQueryError):
        index.score_query("!!!")
    with pytest.raises(BM25EmptyQueryError):
        index.rank("???", top_k=3)


def test_corpus_missing_both_fields_raises(tmp_path: Path) -> None:
    corpus_path = _write_jsonl(tmp_path / "corpus.jsonl", [{"_id": "1"}])
    with pytest.raises(BM25DataError, match="neither title nor text"):
        load_corpus(corpus_path, dataset="scifact")


def test_corpus_coverage_counts_missing_fields(tmp_path: Path) -> None:
    rows = [
        {"_id": "1", "title": "Title only"},
        {"_id": "2", "text": "abstract only"},
        {"_id": "3", "title": "Both", "text": "present"},
    ]
    corpus_path = _write_jsonl(tmp_path / "corpus.jsonl", rows)
    corpus = load_corpus(corpus_path, dataset="scifact")
    assert corpus.document_count == 3
    assert corpus.missing_title_count == 1
    assert corpus.missing_abstract_count == 1
    # Protocol join: title + " " + abstract, empty string for a missing field.
    assert corpus.texts["beir:scifact:2"] == " abstract only"


def test_duplicate_corpus_and_query_ids_raise(tmp_path: Path) -> None:
    corpus_path = _write_jsonl(
        tmp_path / "corpus.jsonl",
        [{"_id": "1", "title": "a"}, {"_id": "1", "title": "b"}],
    )
    with pytest.raises(BM25DataError, match="Duplicate corpus ID"):
        load_corpus(corpus_path, dataset="scifact")
    queries_path = _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"_id": "1", "text": "a"}, {"_id": "1", "text": "b"}],
    )
    with pytest.raises(BM25DataError, match="Duplicate query ID"):
        load_queries(queries_path, dataset="scifact")


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ([("10", "100", "3")], "outside \\[0, 2\\]"),
        ([("10", "100", "x")], "Non-integer qrel score"),
        ([("99", "100", "1")], "outside\\n.*the locked split query set|locked split query set"),
        ([("10", "999", "1")], "outside\\n.*the corpus universe|corpus universe"),
    ],
)
def test_qrels_strict_validation(tmp_path: Path, rows: list[tuple[str, str, str]], match: str) -> None:
    qrels_path = _write_qrels(tmp_path / "qrels.tsv", rows)
    with pytest.raises(BM25DataError, match=match):
        load_qrels(
            qrels_path,
            dataset="scifact",
            corpus_ids={"beir:scifact:100"},
            query_ids={"beir:scifact:10"},
        )


def test_qrels_duplicate_pair_and_bad_header_raise(tmp_path: Path) -> None:
    qrels_path = _write_qrels(tmp_path / "qrels.tsv", [("10", "100", "1"), ("10", "100", "2")])
    with pytest.raises(BM25DataError, match="Duplicate qrel"):
        load_qrels(qrels_path, dataset="scifact", corpus_ids={"beir:scifact:100"}, query_ids={"beir:scifact:10"})
    bad_header = tmp_path / "bad.tsv"
    bad_header.write_text("query-id\tdoc-id\tscore\n10\t100\t1\n", encoding="utf-8")
    with pytest.raises(BM25DataError, match="header"):
        load_qrels(bad_header, dataset="scifact", corpus_ids={"beir:scifact:100"}, query_ids={"beir:scifact:10"})


def test_split_manifest_sha256_mismatch_raises(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    forged = "0" * 64
    _write_manifest(
        tmp_path / "splits" / "forged.json",
        queries_file=fixture["queries"],
        qrels_file=fixture["qrels"],
        query_ids=sorted(f"beir:scifact:{row['_id']}" for row in QUERY_ROWS),
        qrel_count=3,
        qrels_sha256=forged,
    )
    with pytest.raises(BM25DataError, match="qrels SHA-256 mismatch"):
        load_split_manifest(tmp_path / "splits" / "forged.json", dataset="scifact", split="dev")


def test_split_manifest_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(BM25DataError, match="Missing split manifest"):
        load_split_manifest(tmp_path / "splits" / "absent.json", dataset="scifact", split="dev")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"idf": "ln((N-df+0.5)/(df+0.5))"}, "Unsupported idf formula"),
        ({"k1": 0.0}, "k1 must be positive"),
        ({"b": 1.5}, "within \\[0, 1\\]"),
    ],
)
def test_protocol_bm25_deviations_raise(tmp_path: Path, mutation: dict[str, Any], match: str) -> None:
    protocol_path = _write_protocol(tmp_path / "protocol.json")
    data = json.loads(protocol_path.read_text(encoding="utf-8"))
    data["retrieval"]["lexical"]["bm25"].update(mutation)
    protocol_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BM25ConfigError, match=match):
        load_protocol_lexical_config(protocol_path)


def test_protocol_tokenizer_and_policy_deviations_raise(tmp_path: Path) -> None:
    protocol_path = _write_protocol(tmp_path / "protocol.json")
    data = json.loads(protocol_path.read_text(encoding="utf-8"))
    lexical = data["retrieval"]["lexical"]
    lexical["tokenizer"]["stemming"] = True
    protocol_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BM25ConfigError, match="stemming"):
        load_protocol_lexical_config(protocol_path)

    data = json.loads(_write_protocol(tmp_path / "p2.json").read_text(encoding="utf-8"))
    data["retrieval"]["lexical"]["bm25"]["query_terms"] = "all_tokens"
    (tmp_path / "p2.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BM25ConfigError, match="query_terms"):
        load_protocol_lexical_config(tmp_path / "p2.json")

    data = json.loads(_write_protocol(tmp_path / "p3.json").read_text(encoding="utf-8"))
    data["retrieval"]["lexical"]["bm25"]["empty_corpus"] = "warn"
    (tmp_path / "p3.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BM25ConfigError, match="empty_corpus"):
        load_protocol_lexical_config(tmp_path / "p3.json")

    data = json.loads(_write_protocol(tmp_path / "p4.json").read_text(encoding="utf-8"))
    del data["retrieval"]["lexical"]["bm25"]["k1"]
    (tmp_path / "p4.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BM25ConfigError, match="Protocol section"):
        load_protocol_lexical_config(tmp_path / "p4.json")


def test_strict_json_rejects_duplicate_keys(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        '{"_id": "1", "title": "a", "title": "b"}\n', encoding="utf-8"
    )
    with pytest.raises(BM25DataError, match="Duplicate JSON key"):
        load_corpus(corpus_path, dataset="scifact")


# ---------------------------------------------------------------------------
# End-to-end synthetic pipeline (direct call, synthetic=True)
# ---------------------------------------------------------------------------


def test_run_bm25_pilot_synthetic_end_to_end(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    summary = run_bm25_pilot(
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
    assert summary["evaluation_audit"]["empty_ranking_count"] == 1  # query 30 has no matching docs

    manifests = read_run_manifests(fixture["runs"])
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest["status"] == "COMPLETED"
    assert manifest["synthetic"] is True
    assert manifest["run_id"] == summary["run_id"]
    assert manifest["resolved_config"]["corpus_count"] == 5
    assert manifest["resolved_config"]["ranking_reads_qrels"] is False

    rankings_path = fixture["runs"] / manifest["run_id"] / "rankings.jsonl"
    rankings = [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines()]
    by_query = {row["query_id"]: row for row in rankings}
    top_ids = [item["doc_id"] for item in by_query["beir:scifact:10"]["candidates"]]
    assert "beir:scifact:100" in top_ids[:3]
    assert by_query["beir:scifact:30"]["candidates"] == []


# ---------------------------------------------------------------------------
# CLI subprocess tests (ADR-013: exit codes)
# ---------------------------------------------------------------------------


def test_cli_success_exit_0(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    completed = run_cli(
        [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ],
        cwd=tmp_path,
    )
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
    completed = run_cli(
        [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ],
        cwd=tmp_path,
    )
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


def test_cli_missing_split_manifest_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    fixture["manifest"].unlink()
    completed = run_cli(
        [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ],
        cwd=tmp_path,
    )
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


@pytest.mark.parametrize("field", ["queries_sha256", "qrels_sha256"])
def test_cli_tampered_input_sha256_exit_1(tmp_path: Path, field: str) -> None:
    fixture = build_fixture(tmp_path)
    manifest_data = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
    manifest_data[field] = "0" * 64
    fixture["manifest"].write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    completed = run_cli(
        [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ],
        cwd=tmp_path,
    )
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


def test_cli_empty_corpus_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    fixture["corpus"].write_text("", encoding="utf-8")
    completed = run_cli(
        [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ],
        cwd=tmp_path,
    )
    assert completed.returncode == 1
    assert "FAIL" in completed.stderr


def test_cli_zero_token_query_exit_1(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path, zero_token_query=True)
    completed = run_cli(
        [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ],
        cwd=tmp_path,
    )
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

    def cli_args(fixture: dict[str, Path]) -> list[str]:
        return [
            "--dataset", "scifact",
            "--split", "dev",
            "--data-root", str(fixture["root"] / "beir"),
            "--splits-dir", str(fixture["root"] / "splits"),
            "--protocol", str(fixture["protocol"]),
            "--output-dir", str(fixture["runs"]),
            "--synthetic",
        ]

    run_a = run_cli(cli_args(fixture_a), cwd=tmp_path)
    run_b = run_cli(cli_args(fixture_b), cwd=tmp_path)
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
    cli_args = [
        "--dataset", "scifact",
        "--split", "dev",
        "--data-root", str(fixture["root"] / "beir"),
        "--splits-dir", str(fixture["root"] / "splits"),
        "--protocol", str(fixture["protocol"]),
        "--output-dir", str(fixture["runs"]),
        "--synthetic",
    ]
    first = run_cli(cli_args, cwd=tmp_path)
    second = run_cli(cli_args, cwd=tmp_path)
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
    assert summary_first["artifact_hashes"]["rankings.jsonl"] == (
        summary_second["artifact_hashes"]["rankings.jsonl"]
    )

    manifests = read_run_manifests(fixture["runs"])
    assert len(manifests) == 2
    assert {m["run_id"] for m in manifests} == {
        summary_first["run_id"],
        summary_second["run_id"],
    }


# ---------------------------------------------------------------------------
# Real frozen SciFact dev integration (read-only; no run directories created)
# ---------------------------------------------------------------------------


def test_real_scifact_dev_pipeline_matches_frozen_manifest() -> None:
    config = load_protocol_lexical_config(PROJECT_ROOT / "configs" / "protocol_v1.json")
    manifest = load_split_manifest(
        PROJECT_ROOT / "data" / "splits" / "scifact_dev.json", dataset="scifact", split="dev"
    )
    assert manifest.query_count == 809
    assert manifest.qrel_count == 919
    corpus = load_corpus(PROJECT_ROOT / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl", dataset="scifact")
    assert corpus.document_count == 5183
    queries = load_queries(manifest.queries_path, dataset="scifact")
    assert all(qid in queries for qid in manifest.query_ids)

    index = BM25Index(corpus.texts, k1=config.k1, b=config.b)
    qrels, row_count = load_qrels(
        manifest.qrels_path, dataset="scifact", corpus_ids=corpus.texts, query_ids=set(manifest.query_ids)
    )
    assert row_count == 919

    rankings = [
        RankingResult.create_sorted(
            qid,
            [
                (doc_id, score, None)
                for doc_id, score in index.rank(
                    queries[qid], top_k=config.top_k, exclude_doc_ids=frozenset({qid})
                )
            ],
        )
        for qid in manifest.query_ids
    ]
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

    # Determinism: re-scoring one query reproduces the identical ordering.
    probe_qid = manifest.query_ids[0]
    again = index.rank(queries[probe_qid], top_k=config.top_k, exclude_doc_ids=frozenset({probe_qid}))
    first = [(item.doc_id, item.score) for item in next(
        r for r in rankings if r.query_id == probe_qid
    ).candidates]
    assert again == first
