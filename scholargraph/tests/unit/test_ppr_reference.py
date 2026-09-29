"""SG-023 PPR tests: hand-computed reference + adversarial + CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.graph.baselines import GraphDataError
from scholargraph.graph.ppr import (
    build_teleport,
    finalize_c100,
    personalized_pagerank,
    seed_hash,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
MASKED = PROJECT_ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv"
DEGREES = PROJECT_ROOT / "data" / "processed" / "graph" / "features_degree_masked.json"


def _graph(edges: list[tuple[str, str]]) -> tuple[list[str], dict[str, set[str]]]:
    out: dict[str, set[str]] = {}
    for u, v in edges:
        out.setdefault(u, set()).add(v)
        out.setdefault(v, set())
    return sorted(out), out


def test_hand_computed_single_seed() -> None:
    # A -> B, seeds {A:1}: v=[1,0]; B dangling redistributes by v (all to A).
    # Steady state: pA = 0.15 + 0.85*pB, pB = 0.85*pA -> A=0.5405, B=0.4595.
    nodes, out = _graph([("A", "B")])
    tel = build_teleport([{"doc_id": "A", "rrf": 1.0}], set(nodes))
    assert tel == {"A": 1.0}
    scores, iters, res = personalized_pagerank(nodes, out, tel)
    assert scores["A"] == pytest.approx(0.54054054, abs=1e-6)
    assert scores["B"] == pytest.approx(0.45945946, abs=1e-6)
    assert abs(sum(scores.values()) - 1.0) < 1e-9
    assert res < 1e-8 and iters <= 200


def test_teleport_normalization() -> None:
    nodes, _ = _graph([("A", "B"), ("B", "A")])
    tel = build_teleport([{"doc_id": "A", "rrf": 2.0}, {"doc_id": "B", "rrf": 1.0}], set(nodes))
    assert tel["A"] == pytest.approx(2 / 3)
    assert tel["B"] == pytest.approx(1 / 3)


def test_empty_seeds_fails_no_qrels_fallback() -> None:
    with pytest.raises(GraphDataError):
        build_teleport([], {"A"})


def test_too_many_seeds_fails() -> None:
    nodes, _ = _graph([("A", "B")])
    with pytest.raises(GraphDataError):
        build_teleport([{"doc_id": "A", "rrf": 1.0}] * 21, set(nodes))


def test_seed_outside_graph_fails() -> None:
    with pytest.raises(GraphDataError):
        build_teleport([{"doc_id": "GHOST", "rrf": 1.0}], {"A"})


def test_nonpositive_weight_fails() -> None:
    with pytest.raises(GraphDataError):
        build_teleport([{"doc_id": "A", "rrf": 0.0}], {"A"})


def test_nonfinite_and_bool_weights_fail() -> None:
    import math
    nodes, _ = _graph([("A", "B")])
    for bad in (float("inf"), float("-inf"), float("nan"), True, "1.0", None):
        with pytest.raises(GraphDataError):
            build_teleport([{"doc_id": "A", "rrf": bad}], set(nodes))


def test_finalize_keeps_c100_set() -> None:
    nodes, out = _graph([("A", "B"), ("B", "C")])
    tel = build_teleport([{"doc_id": "A", "rrf": 1.0}], set(nodes))
    scores, _, _ = personalized_pagerank(nodes, out, tel)
    rows = finalize_c100(["C", "A"], scores)
    assert {r["doc_id"] for r in rows} == {"A", "C"}  # same set (expansion off)
    assert rows[0]["ppr"] >= rows[1]["ppr"]


def test_finalize_unknown_member_fails() -> None:
    assert finalize_c100(["A"], {"A": 0.5})[0]["doc_id"] == "A"
    with pytest.raises(GraphDataError):
        finalize_c100(["GHOST"], {"A": 0.5})


def test_nonconvergence_fails() -> None:
    nodes, out = _graph([("A", "B"), ("B", "A")])
    with pytest.raises(GraphDataError):
        personalized_pagerank(nodes, out, {"A": 0.5, "B": 0.5}, tol=0.0, max_iter=2)


def test_seed_hash_deterministic() -> None:
    s = [{"doc_id": "A", "rrf": 1.0}]
    assert seed_hash(s) == seed_hash(s)
    assert seed_hash([{"doc_id": "B", "rrf": 1.0}]) != seed_hash(s)


def test_seed_hash_bad_row_fails() -> None:
    from scholargraph.graph.ppr import seed_hash as _sh
    with pytest.raises(GraphDataError):
        _sh([{"doc_id": "A"}])


def test_smoke_masked_graph_converges() -> None:
    """Technical smoke (synthetic seeds, NOT a retrieval measurement): PPR must
    converge within budget on the real 18.251-node masked graph."""
    from scholargraph.graph.baselines import load_masked_adjacency
    from scholargraph.graph.ppr import load_node_universe_from_degrees, personalized_pagerank as _ppr
    universe = load_node_universe_from_degrees(DEGREES)
    nodes, out = load_masked_adjacency(MASKED, universe)
    assert len(nodes) == 18251
    sprouts = [v for v in nodes if out[v]][:5]
    tel = build_teleport([{"doc_id": d, "rrf": 5 - i} for i, d in enumerate(sprouts)], set(nodes))
    scores, iters, res = _ppr(nodes, out, tel)
    assert iters <= 200 and res < 1e-8
    assert abs(sum(scores.values()) - 1.0) < 1e-9


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH="src")
    return subprocess.run([str(PYTHON), "-m", "scholargraph.graph.ppr", *args],
                          capture_output=True, text=True, cwd=PROJECT_ROOT, env=env)


def test_cli_toy_graph(tmp_path: Path) -> None:
    adj = tmp_path / "adj.tsv"
    adj.write_text("A\tB\nB\tC\n", encoding="utf-8")
    seeds = tmp_path / "seeds.json"
    seeds.write_text(json.dumps({"q1": [{"doc_id": "A", "rrf": 0.5}, {"doc_id": "B", "rrf": 0.25}]}), encoding="utf-8")
    c100 = tmp_path / "c.json"
    c100.write_text(json.dumps({"q1": ["A", "B", "C"]}), encoding="utf-8")
    out = tmp_path / "o.json"
    r = _run_cli(["--adjacency", str(adj), "--seeds", str(seeds), "--c100", str(c100), "--output", str(out)])
    assert r.returncode == 0, r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    got = [x["doc_id"] for x in d["queries"]["q1"]["final"]]
    assert got == ["B", "C", "A"]  # verified: B=0.3860 > C=0.3281 > A=0.2859
    vals = [x["ppr"] for x in d["queries"]["q1"]["final"]]
    assert vals == sorted(vals, reverse=True)
    assert d["inputs"]["expansion"] == "off"


def test_cli_empty_seeds_exit_1(tmp_path: Path) -> None:
    adj = tmp_path / "adj.tsv"
    adj.write_text("A\tB\n", encoding="utf-8")
    seeds = tmp_path / "seeds.json"
    seeds.write_text(json.dumps({"q1": []}), encoding="utf-8")
    c100 = tmp_path / "c.json"
    c100.write_text(json.dumps({"q1": ["A"]}), encoding="utf-8")
    r = _run_cli(["--adjacency", str(adj), "--seeds", str(seeds), "--c100", str(c100),
                  "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_mismatched_queries_exit_1(tmp_path: Path) -> None:
    adj = tmp_path / "adj.tsv"
    adj.write_text("A\tB\n", encoding="utf-8")
    seeds = tmp_path / "seeds.json"
    seeds.write_text(json.dumps({"q1": [{"doc_id": "A", "rrf": 1.0}]}), encoding="utf-8")
    c100 = tmp_path / "c.json"
    c100.write_text(json.dumps({"q2": ["A"]}), encoding="utf-8")
    r = _run_cli(["--adjacency", str(adj), "--seeds", str(seeds), "--c100", str(c100),
                  "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
