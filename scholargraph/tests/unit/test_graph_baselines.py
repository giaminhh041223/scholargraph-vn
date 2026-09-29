"""SG-022 graph baseline tests: toy graphs + adversarial + CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.graph.baselines import (
    GraphDataError,
    bibliographic_coupling,
    global_pagerank,
    load_masked_adjacency,
    rank_candidates_by_global,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
MASKED = PROJECT_ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv"


def _graph(edges: list[tuple[str, str]]) -> tuple[list[str], dict[str, set[str]]]:
    out: dict[str, set[str]] = {}
    for u, v in edges:
        out.setdefault(u, set()).add(v)
        out.setdefault(v, set())
    return sorted(out), out


def test_direction_matters() -> None:
    # A -> B -> C: mass flows forward, A lowest, C highest.
    nodes, out = _graph([("A", "B"), ("B", "C")])
    scores, iters, res = global_pagerank(nodes, out)
    assert scores["C"] > scores["B"] > scores["A"]
    assert abs(sum(scores.values()) - 1.0) < 1e-9
    assert res < 1e-8


def test_symmetric_equal_scores() -> None:
    nodes, out = _graph([("A", "B"), ("B", "A")])
    scores, _, _ = global_pagerank(nodes, out)
    assert scores["A"] == pytest.approx(scores["B"])


def test_dangling_redistributes() -> None:
    nodes, out = _graph([("A", "B")])  # B dangling
    scores, _, _ = global_pagerank(nodes, out)
    assert abs(sum(scores.values()) - 1.0) < 1e-9
    assert scores["B"] > scores["A"]


def test_star_center_wins() -> None:
    nodes, out = _graph([("L1", "C"), ("L2", "C"), ("L3", "C")])
    scores, _, _ = global_pagerank(nodes, out)
    assert scores["C"] == max(scores.values())


def test_coupling_counts() -> None:
    _, out = _graph([("U", "R1"), ("U", "R2"), ("V", "R2"), ("V", "R3")])
    c = bibliographic_coupling("U", "V", out)
    assert c["shared_references"] == 1
    assert c["jaccard"] == pytest.approx(1 / 3)


def test_coupling_unknown_node_fails() -> None:
    _, out = _graph([("U", "R1")])
    with pytest.raises(GraphDataError):
        bibliographic_coupling("U", "GHOST", out)


def test_candidate_ranking_same_order_rule() -> None:
    nodes, out = _graph([("A", "B"), ("B", "C")])
    scores, _, _ = global_pagerank(nodes, out)
    rows = rank_candidates_by_global(scores, ["A", "C"])
    assert [r["doc_id"] for r in rows] == ["C", "A"]


def test_candidate_outside_graph_fails_loudly() -> None:
    nodes, out = _graph([("A", "B")])
    scores, _, _ = global_pagerank(nodes, out)
    with pytest.raises(GraphDataError):
        rank_candidates_by_global(scores, ["A", "GHOST"])


def test_empty_graph_fails(tmp_path: Path) -> None:
    p = tmp_path / "adj.tsv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(GraphDataError):
        load_masked_adjacency(p)


def test_duplicate_edge_fails(tmp_path: Path) -> None:
    p = tmp_path / "adj.tsv"
    p.write_text("A\tB\nA\tB\n", encoding="utf-8")
    with pytest.raises(GraphDataError):
        load_masked_adjacency(p)


def test_blank_line_rejected(tmp_path: Path) -> None:
    p = tmp_path / "adj.tsv"
    p.write_text("A\tB\n\n", encoding="utf-8")
    with pytest.raises(GraphDataError):
        load_masked_adjacency(p)


def test_nonconvergence_fails() -> None:
    nodes, out = _graph([("A", "B"), ("B", "A")])
    with pytest.raises(GraphDataError):
        global_pagerank(nodes, out, tol=0.0, max_iter=2)


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH="src")
    return subprocess.run([str(PYTHON), "-m", "scholargraph.graph.baselines", *args],
                          capture_output=True, text=True, cwd=PROJECT_ROOT, env=env)


def test_cli_on_masked_graph(tmp_path: Path) -> None:
    out = tmp_path / "base.json"
    degrees = PROJECT_ROOT / "data" / "processed" / "graph" / "features_degree_masked.json"
    r = _run_cli(["--adjacency", str(MASKED), "--node-degrees", str(degrees),
                  "--output", str(out), "--top-k", "100"])
    assert r.returncode == 0, r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["graph"]["nodes"] == 18251
    assert d["graph"]["edges"] == 26186
    assert d["graph"]["isolated_nodes"] == 2325
    assert d["graph"]["dangling_nodes"] == 2492
    assert abs(d["pagerank"]["mass"] - 1.0) < 1e-9
    assert d["pagerank"]["residual"] < 1e-8
    assert d["pagerank"]["iterations"] <= 200
    assert d["inputs"]["node_degrees"]["edge_count"] == 26186
    assert 0.0 < d["popularity_audit"]["top_100_mass_share"] < 1.0


def test_cli_missing_file_exit_1(tmp_path: Path) -> None:
    r = _run_cli(["--adjacency", str(tmp_path / "nope.tsv"), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_bad_topk_exit_1(tmp_path: Path) -> None:
    r = _run_cli(["--adjacency", str(MASKED), "--output", str(tmp_path / "o.json"), "--top-k", "0"])
    assert r.returncode == 1
