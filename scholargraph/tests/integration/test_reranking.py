"""SG-025 reranking integration tests: end-to-end synthetic + adversarial + CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.data.interfaces import DataLeakageError
from scholargraph.retrieval.rerank import (
    HybridReranker,
    RerankDataError,
    apply_age_to_rows,
    minmax_normalize,
    rerank_query,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)


def test_end_to_end_gamma_zero_equals_rrf_order() -> None:
    rows, diag = rerank_query(["a", "b", "c"], {"a": 3.0, "b": 2.0, "c": 1.0},
                              {"a": 0.9, "b": 0.1, "c": 0.5}, gamma=0.0)
    assert [r["doc_id"] for r in rows] == ["a", "b", "c"]
    assert diag["missing_graph_scores"] == 0


def test_gamma_full_equals_graph_order() -> None:
    rows, _ = rerank_query(["a", "b"], {"a": 5.0, "b": 1.0},
                           {"a": 0.1, "b": 0.9}, gamma=0.3)
    # norm_rrf a=1,b=0; norm_graph a=0,b=1 -> F a=0.7, b=0.3
    assert [r["doc_id"] for r in rows] == ["a", "b"]
    assert rows[0]["fused"] == pytest.approx(0.7)


def test_missing_graph_score_zero_with_count() -> None:
    rows, diag = rerank_query(["a", "b"], {"a": 1.0, "b": 2.0}, {"a": 0.5}, gamma=0.2)
    assert diag["missing_graph_scores"] == 1
    assert diag["missing_reason"] is not None
    by = {r["doc_id"]: r for r in rows}
    assert by["b"]["graph"] is None and by["b"]["norm_graph"] == 0.0


def test_constant_signal_all_zero() -> None:
    norm, const = minmax_normalize({"a": 2.0, "b": 2.0})
    assert const is True and set(norm.values()) == {0.0}


def test_universe_unchanged_and_no_self() -> None:
    rows, _ = rerank_query(["a", "b"], {"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 0.0}, 0.1)
    assert {r["doc_id"] for r in rows} == {"a", "b"}
    with pytest.raises(RerankDataError):
        rerank_query(["a", "s"], {"a": 1.0, "s": 2.0}, {"a": 1.0, "s": 0.0}, 0.1, query_source="s")


def test_rrf_coverage_mismatch_fails() -> None:
    with pytest.raises(RerankDataError):
        rerank_query(["a", "b"], {"a": 1.0}, {"a": 1.0, "b": 0.0}, 0.1)


def test_bad_gamma_fails() -> None:
    with pytest.raises(RerankDataError):
        rerank_query(["a"], {"a": 1.0}, {"a": 1.0}, 0.5)


def test_ranker_leakage_guard() -> None:
    r = HybridReranker(gamma=0.1)
    with pytest.raises(DataLeakageError):
        r.rank("q", candidate_ids=["a"], rrf={"a": 1.0}, graph_scores={"a": 1.0}, qrels={})
    for key in ("labels", "heldout_edges", "ground_truth", "test_labels", "human_labels"):
        with pytest.raises(DataLeakageError):
            r.rank("q", candidate_ids=["a"], rrf={"a": 1.0}, graph_scores={"a": 1.0}, **{key: {}})


def test_duplicate_age_input_fails() -> None:
    rows, _ = rerank_query(["a", "b"], {"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 0.0}, 0.1)
    dup = [{"doc_id": "a", "fused": 1.0}, {"doc_id": "a", "fused": 0.5}]
    with pytest.raises(RerankDataError):
        apply_age_to_rows(dup, {"a": 2020}, 2025, 0.05)


def test_full_gamma_grid_orders() -> None:
    rrf = {"a": 5.0, "b": 1.0}
    gs = {"a": 0.1, "b": 0.9}
    expect = {0.0: ["a", "b"], 0.1: ["a", "b"], 0.2: ["a", "b"], 0.3: ["a", "b"]}
    for g, order in expect.items():
        rows, _ = rerank_query(["a", "b"], rrf, gs, g)
        assert [r["doc_id"] for r in rows] == order
    rows, _ = rerank_query(["a", "b"], {"a": 1.0, "b": 5.0}, gs, 0.0)
    assert [r["doc_id"] for r in rows] == ["b", "a"]


def test_present_only_normalization_pinned() -> None:
    # one present graph score -> constant -> 0; fused uses RRF only at any gamma
    rows, diag = rerank_query(["a", "b"], {"a": 1.0, "b": 2.0}, {"a": 0.7}, gamma=0.3)
    by = {r["doc_id"]: r for r in rows}
    assert by["a"]["norm_graph"] == 0.0 and by["b"]["norm_graph"] == 0.0
    assert diag["constant_graph"] is True


def test_age_variant_end_to_end() -> None:
    # 3 docs so normalized RRF has interior values: old=1.0, new=0.6, z=0.0.
    rows, _ = rerank_query(["old", "new", "z"], {"old": 1.0, "new": 0.6, "z": 0.0},
                           {"old": 0.5, "new": 0.5, "z": 0.5}, gamma=0.0)
    assert [r["doc_id"] for r in rows] == ["old", "new", "z"]
    aged = apply_age_to_rows(rows, {"old": 2000, "new": 2025, "z": 2025}, 2025, 0.1)
    assert aged[0]["doc_id"] == "new"  # 0.6*1.0 beats 1.0*exp(-2.5)=0.082
    with pytest.raises(RerankDataError):
        apply_age_to_rows(rows, {"old": 2000}, 2025, 0.1)


def test_component_evidence_travels() -> None:
    rows, _ = rerank_query(["a"], {"a": 2.0}, {"a": 3.0}, 0.2, graph_evidence={"graph_hash": "abc"})
    assert rows[0]["graph_evidence"] == {"graph_hash": "abc"}
    assert set(rows[0]) >= {"rrf", "graph", "norm_rrf", "norm_graph", "fused"}


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH="src")
    return subprocess.run([str(PYTHON), "-m", "scholargraph.retrieval.rerank", *args],
                          capture_output=True, text=True, cwd=PROJECT_ROOT, env=env)


def test_cli_success(tmp_path: Path) -> None:
    (tmp_path / "c.json").write_text(json.dumps({"q1": ["a", "b"]}), encoding="utf-8")
    (tmp_path / "r.json").write_text(json.dumps({"q1": {"a": 1.0, "b": 2.0}}), encoding="utf-8")
    (tmp_path / "g.json").write_text(json.dumps({"q1": {"a": 0.5, "b": 0.5}}), encoding="utf-8")
    out = tmp_path / "o.json"
    r = _run_cli(["--c100", str(tmp_path / "c.json"), "--rrf", str(tmp_path / "r.json"),
                  "--graph-scores", str(tmp_path / "g.json"), "--gamma", "0.2",
                  "--graph-kind", "ppr", "--output", str(out)])
    assert r.returncode == 0, r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert {x["doc_id"] for x in d["queries"]["q1"]["rows"]} == {"a", "b"}


def test_cli_bad_gamma_exit_1(tmp_path: Path) -> None:
    (tmp_path / "c.json").write_text(json.dumps({"q1": ["a"]}), encoding="utf-8")
    (tmp_path / "r.json").write_text(json.dumps({"q1": {"a": 1.0}}), encoding="utf-8")
    (tmp_path / "g.json").write_text(json.dumps({"q1": {"a": 1.0}}), encoding="utf-8")
    r = _run_cli(["--c100", str(tmp_path / "c.json"), "--rrf", str(tmp_path / "r.json"),
                  "--graph-scores", str(tmp_path / "g.json"), "--gamma", "0.5",
                  "--graph-kind", "ppr", "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def _write_inputs(tmp: Path) -> None:
    (tmp / "c.json").write_text(json.dumps({"q1": ["a", "b"]}), encoding="utf-8")
    (tmp / "r.json").write_text(json.dumps({"q1": {"a": 1.0, "b": 2.0}}), encoding="utf-8")
    (tmp / "g.json").write_text(json.dumps({"q1": {"a": 0.5, "b": 0.5}}), encoding="utf-8")


def test_cli_missing_file_exit_1(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    r = _run_cli(["--c100", str(tmp_path / "nope.json"), "--rrf", str(tmp_path / "r.json"),
                  "--graph-scores", str(tmp_path / "g.json"), "--gamma", "0.2",
                  "--graph-kind", "ppr", "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_self_recommendation_exit_1(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    (tmp_path / "s.json").write_text(json.dumps({"q1": "a"}), encoding="utf-8")
    r = _run_cli(["--c100", str(tmp_path / "c.json"), "--rrf", str(tmp_path / "r.json"),
                  "--graph-scores", str(tmp_path / "g.json"), "--gamma", "0.2",
                  "--graph-kind", "ppr", "--source-map", str(tmp_path / "s.json"),
                  "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_age_variant(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    (tmp_path / "y.json").write_text(json.dumps({"a": 2000, "b": 2025}), encoding="utf-8")
    (tmp_path / "qy.json").write_text(json.dumps({"q1": 2025}), encoding="utf-8")
    r = _run_cli(["--c100", str(tmp_path / "c.json"), "--rrf", str(tmp_path / "r.json"),
                  "--graph-scores", str(tmp_path / "g.json"), "--gamma", "0.0",
                  "--graph-kind", "global", "--years", str(tmp_path / "y.json"),
                  "--query-years", str(tmp_path / "qy.json"), "--lambda", "0.05",
                  "--output", str(tmp_path / "o.json")])
    assert r.returncode == 0, r.stderr
    d = json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))
    assert "rows_age" in d["queries"]["q1"]
    assert "inputs" in d and "c100" in d["inputs"]
