"""SG-026 B-pipeline unit tests on a tiny SYNTHETIC graph (never academic)."""

from __future__ import annotations

import pytest

from scholargraph.graph.b_track import (
    BTrackDataError,
    cutoff_subgraph,
    evaluate_variants,
    fuse_c100,
    fuse_variants,
    internal_refs,
    query_universe,
    run_query,
)

U, A, B, C, D = "openalex:W10", "openalex:W11", "openalex:W12", "openalex:W13", "openalex:W14"
W = {
    U: {"year": 2020, "refs": ["https://openalex.org/W11", "https://openalex.org/W12",
                               "https://openalex.org/W13"], "title": "t u", "abstract": "a u"},
    A: {"year": 2018, "refs": [], "title": "t a", "abstract": "a a"},
    B: {"year": 2019, "refs": ["https://openalex.org/W11"], "title": "t b", "abstract": "a b"},
    C: {"year": 2021, "refs": [], "title": "t c", "abstract": "a c"},
    D: {"year": 2017, "refs": [], "title": "t d", "abstract": "a d"},
}
H = {U: [B]}  # held-out; O = {A} (C is future-dated, out of R)
NODES = sorted(W)
OUT = {U: {A, B, C}, A: set(), B: {A}, C: set(), D: set()}


def _bm25(text: str, uni: set) -> list:
    return sorted(uni)[:100]


def _dense(text: str, uni: set) -> list:
    return sorted(uni, reverse=True)[:100]


def test_internal_refs_and_universe() -> None:
    assert internal_refs(U, W, 2020) == [A, B]  # C excluded: year 2021 > 2020
    uni = query_universe(U, W, 2020, {A})
    assert U not in uni and A not in uni
    assert {B, D} <= uni  # H stays, old D stays


def test_fuse_c100_union() -> None:
    rows = fuse_c100(["a", "b"], ["b", "c"])
    assert [r["doc_id"] for r in rows] == ["b", "a", "c"]


def test_cutoff_subgraph() -> None:
    years = {k: v["year"] for k, v in W.items()}
    nodes, out = cutoff_subgraph(NODES, OUT, years, 2019)
    assert C not in nodes and U not in nodes
    assert set(nodes) == {A, B, D}


def test_run_query_end_to_end() -> None:
    from scholargraph.graph.baselines import global_pagerank
    years = {k: v["year"] for k, v in W.items()}
    sub_nodes = [v for v in NODES if years[v] <= 2020]
    sub_out = {v: {w for w in OUT[v] if years[w] <= 2020} for v in sub_nodes}
    g, _, _ = global_pagerank(sub_nodes, sub_out)
    res = run_query(U, W, H, _bm25, _dense, NODES, OUT, {2020: g})
    assert res["heldout"] == [B]
    assert set(res["c100"]) <= ({B, D} | {A})
    assert U not in res["c100"] and A not in res["c100"]  # self + observed excluded
    assert B in res["c100"]  # held-out stays retrievable
    assert len(res["c100"]) <= 100


def test_variants_20_and_eval() -> None:
    rows = [{"doc_id": B, "rrf": 0.03}, {"doc_id": D, "rrf": 0.01}]
    years = {B: 2019, D: 2017}
    var = fuse_variants(rows, {B: 0.5, D: 0.5}, years, 2020)
    assert len(var) == 20
    per_q = {U: var}
    uni = {U: {B, D}}
    ev = evaluate_variants(per_q, H, uni, {U: U}, list(W))
    assert len(ev) == 20 and all("nDCG@10" in m for m in ev.values())


def test_query_without_holdout_fails() -> None:
    from scholargraph.graph.baselines import global_pagerank
    years = {k: v["year"] for k, v in W.items()}
    sub_nodes = [v for v in NODES if years[v] <= 2020]
    sub_out = {v: {w for w in OUT[v] if years[w] <= 2020} for v in sub_nodes}
    g, _, _ = global_pagerank(sub_nodes, sub_out)
    with pytest.raises(BTrackDataError):
        run_query(U, W, {}, _bm25, _dense, NODES, OUT, {2020: g})


def test_unknown_query_fails() -> None:
    with pytest.raises(BTrackDataError):
        run_query("openalex:W999999", W, H, _bm25, _dense, NODES, OUT, {})


def test_empty_universe_fails() -> None:
    with pytest.raises(BTrackDataError):
        query_universe(U, W, 2020, {A, B, C, D})


def test_run_b_dev_cli_bad_split_exit_nonzero() -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    r = subprocess.run([sys.executable, "scripts/run_b_dev.py", "--split", "bogus"],
                       capture_output=True, text=True, cwd=root, env=env)
    assert r.returncode != 0
