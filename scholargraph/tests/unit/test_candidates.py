"""SG-021 candidate recall tests: synthetic fixtures + adversarial + CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.retrieval.candidates import (
    CandidateDataError,
    audit_pools,
    load_qrels_grades,
    load_rank_pools,
    oracle_ndcg_at_10,
    pick_examples,
    recall_at_k,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
BM25 = PROJECT_ROOT / "artifacts" / "runs" / "RUN-20260916-163653-bm25-scifact-dev" / "rankings.jsonl"
TFIDF = PROJECT_ROOT / "artifacts" / "runs" / "RUN-20260916-191127-tfidf-scifact-dev" / "rankings.jsonl"
QRELS = PROJECT_ROOT / "data" / "raw" / "beir" / "scifact" / "qrels" / "train.tsv"


def test_recall_hand_computed() -> None:
    assert recall_at_k(["a", "b", "c"], {"a": 1, "z": 1}) == pytest.approx(0.5)
    assert recall_at_k(["x"], {"a": 1}) == 0.0
    assert recall_at_k(["a"], {}) is None


def test_oracle_hand_computed() -> None:
    import math
    # single relevant in pool -> ideal rerank puts it first -> oracle 1.0
    assert oracle_ndcg_at_10(["x", "a"], {"a": 1}) == pytest.approx(1.0)
    # one of two relevant missing from pool -> partial oracle
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert oracle_ndcg_at_10(["x", "a"], {"a": 1, "b": 1}) == pytest.approx(1.0 / idcg)
    assert oracle_ndcg_at_10(["x"], {"a": 1}) == 0.0
    assert oracle_ndcg_at_10(["a"], {}) is None


def test_audit_union_covers_members(tmp_path: Path) -> None:
    q = {"q1": {"a": 1, "b": 1}}
    pools = {"m1": {"q1": ["a", "x"]}, "m2": {"q1": ["b", "y"]}}
    s = audit_pools(pools, q)
    assert s["per_method"]["m1"]["mean_recall_at_100"] == pytest.approx(0.5)
    assert s["union_oracle"]["mean_recall_full_union"] == pytest.approx(1.0)
    assert s["union_oracle"]["answerable_rate"] == pytest.approx(1.0)


def test_union_recall_ge_members_on_real_runs() -> None:
    pools = {
        "bm25": load_rank_pools(BM25),
        "tfidf": load_rank_pools(TFIDF),
    }
    qrels = load_qrels_grades(QRELS)
    s = audit_pools(pools, qrels)
    u = s["union_oracle"]["mean_recall_full_union"]
    for m in ("bm25", "tfidf"):
        assert u >= s["per_method"][m]["mean_recall_at_100"]
    assert s["union_oracle"]["answerable_rate"] >= s["per_method"]["bm25"]["answerable_rate"]


def test_qrels_grade_zero_not_relevant(tmp_path: Path) -> None:
    p = tmp_path / "q.tsv"
    p.write_text("query-id\tcorpus-id\tscore\n0\t1\t0\n0\t2\t1\n", encoding="utf-8")
    q = load_qrels_grades(p)
    assert q == {"beir:scifact:0": {"beir:scifact:2": 1}}


def test_rankings_blank_line_rejected(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps({"query_id": "q", "candidates": [{"doc_id": "a"}]}) + "\n\n", encoding="utf-8")
    with pytest.raises(CandidateDataError):
        load_rank_pools(p)


def test_audit_query_mismatch_fails() -> None:
    with pytest.raises(CandidateDataError):
        audit_pools({"m1": {"q1": ["a"]}}, {"q1": {"a": 1}, "q2": {"b": 1}})


def test_qrels_duplicate_fails(tmp_path: Path) -> None:
    p = tmp_path / "q.tsv"
    p.write_text("query-id\tcorpus-id\tscore\n0\t1\t1\n0\t1\t1\n", encoding="utf-8")
    with pytest.raises(CandidateDataError):
        load_qrels_grades(p)


def test_qrels_bad_score_fails(tmp_path: Path) -> None:
    p = tmp_path / "q.tsv"
    p.write_text("query-id\tcorpus-id\tscore\n0\t1\tbad\n", encoding="utf-8")
    with pytest.raises(CandidateDataError):
        load_qrels_grades(p)


def test_rankings_duplicate_doc_fails(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps({"query_id": "q", "candidates": [{"doc_id": "a"}, {"doc_id": "a"}]}), encoding="utf-8")
    with pytest.raises(CandidateDataError):
        load_rank_pools(p)


def test_pick_examples_split() -> None:
    pools = {"m": ["a"], "m2": ["z"]}
    q = {"q1": {"a": 1}, "q2": {"b": 1}}
    ex = pick_examples({"q1": ["a"], "q2": ["z"]}, q)
    cases = [e["case"] for e in ex]
    assert "candidate_miss" in cases and "rank_error_candidate_present" in cases


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH="src")
    return subprocess.run([str(PYTHON), "-m", "scholargraph.retrieval.candidates", *args],
                          capture_output=True, text=True, cwd=PROJECT_ROOT, env=env)


def test_cli_real_audit(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    js = tmp_path / "a.json"
    r = _run_cli(["--bm25-rankings", str(BM25), "--tfidf-rankings", str(TFIDF),
                  "--qrels", str(QRELS), "--output-md", str(md), "--output-json", str(js)])
    assert r.returncode == 0, r.stderr
    d = json.loads(js.read_text(encoding="utf-8"))
    assert d["per_method"]["bm25"]["queries"] == 809
    assert d["dense"] is None
    assert len(d["examples"]) == 10
    assert 0.0 <= d["per_method"]["bm25"]["mean_recall_at_100"] <= 1.0


def test_cli_missing_file_exit_1(tmp_path: Path) -> None:
    r = _run_cli(["--bm25-rankings", str(tmp_path / "nope"), "--tfidf-rankings", str(TFIDF),
                  "--qrels", str(QRELS), "--output-md", str(tmp_path / "a.md"),
                  "--output-json", str(tmp_path / "a.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_malformed_rankings_exit_1(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{oops", encoding="utf-8")
    r = _run_cli(["--bm25-rankings", str(bad), "--tfidf-rankings", str(TFIDF),
                  "--qrels", str(QRELS), "--output-md", str(tmp_path / "a.md"),
                  "--output-json", str(tmp_path / "a.json")])
    assert r.returncode == 1
