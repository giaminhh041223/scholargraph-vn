"""SG-020 Hybrid RRF tests: hand-computed fixtures + adversarial/negative + CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.data.interfaces import DataLeakageError
from scholargraph.retrieval.hybrid import (
    HybridDataError,
    HybridRRFRanker,
    load_hybrid_config,
    rrf_fuse,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT_ROOT / "configs" / "hybrid.json"
PYTHON = Path(sys.executable)


def test_config_loads_protocol_values() -> None:
    cfg = load_hybrid_config(CONFIG)
    assert cfg["rrf"]["k"] == 60
    assert cfg["depths"]["per_retriever_depth"] == 100
    assert cfg["depths"]["union_maximum"] == 200
    assert cfg["depths"]["final_depth"] == 100


def test_hand_computed_rrf_two_lists() -> None:
    # lex: A(1) B(2); dense: B(1) C(2); k=60
    rows = rrf_fuse(["A", "B"], ["B", "C"], k=60)
    by_id = {r["doc_id"]: r for r in rows}
    assert by_id["B"]["rrf"] == pytest.approx(1 / 62 + 1 / 61)
    assert by_id["A"]["rrf"] == pytest.approx(1 / 61)
    assert by_id["C"]["rrf"] == pytest.approx(1 / 62)
    assert [r["doc_id"] for r in rows] == ["B", "A", "C"]
    assert by_id["A"]["rank_dense"] is None
    assert by_id["C"]["rank_lexical"] is None


def test_tie_break_doc_id_ascending() -> None:
    # Symmetric swap: X and Y get identical fused scores -> X first.
    rows = rrf_fuse(["X", "Y"], ["Y", "X"], k=60)
    assert rows[0]["rrf"] == rows[1]["rrf"]
    assert [r["doc_id"] for r in rows] == ["X", "Y"]


def test_missing_component_contributes_zero() -> None:
    rows = rrf_fuse(["ONLY"], ["ONLY", "OTHER"], k=60)
    by_id = {r["doc_id"]: r for r in rows}
    assert by_id["ONLY"]["rrf"] == pytest.approx(1 / 61 + 1 / 61)
    assert by_id["OTHER"]["rrf"] == pytest.approx(1 / 62)


def test_deterministic_rerun() -> None:
    a = rrf_fuse(["d1", "d2", "d3"], ["d3", "d1", "d4"], k=60)
    b = rrf_fuse(["d1", "d2", "d3"], ["d3", "d1", "d4"], k=60)
    assert a == b


def test_ranker_enforces_leakage_boundary() -> None:
    r = HybridRRFRanker()
    with pytest.raises(DataLeakageError):
        r.rank("q", lexical_rank=["a"], dense_rank=["b"], qrels={})
    with pytest.raises(DataLeakageError):
        HybridRRFRanker(qrels={})


def test_duplicate_doc_id_fails() -> None:
    with pytest.raises(HybridDataError):
        rrf_fuse(["a", "a"], ["b", "c"], k=60)


def test_empty_list_fails_loudly() -> None:
    with pytest.raises(HybridDataError):
        rrf_fuse([], ["b"], k=60)


def test_wrong_k_fails() -> None:
    with pytest.raises(HybridDataError):
        rrf_fuse(["a"], ["b"], k=50)


def test_over_depth_fails() -> None:
    with pytest.raises(HybridDataError):
        rrf_fuse([f"d{i}" for i in range(101)], ["x"], k=60)


def test_config_missing_field_fails(tmp_path: Path) -> None:
    bad = json.loads(CONFIG.read_text(encoding="utf-8"))
    del bad["rrf"]["k"]
    p = tmp_path / "hybrid.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(HybridDataError):
        load_hybrid_config(p)


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src", "PATH": __import__("os").environ.get("PATH", "")}
    return subprocess.run([str(PYTHON), "-m", "scholargraph.retrieval.hybrid", *args], capture_output=True, text=True, cwd=PROJECT_ROOT, env={**__import__("os").environ, **env})


def test_cli_success_and_byte_identical_rerun(tmp_path: Path) -> None:
    lex = tmp_path / "lex.json"
    den = tmp_path / "den.json"
    lex.write_text(json.dumps({"q1": ["A", "B"], "q2": ["C", "D"]}), encoding="utf-8")
    den.write_text(json.dumps({"q1": ["B", "C"], "q2": ["D", "E"]}), encoding="utf-8")
    out1 = tmp_path / "f1.json"
    out2 = tmp_path / "f2.json"
    r1 = _run_cli(["--lexical", str(lex), "--dense", str(den), "--config", str(CONFIG), "--output", str(out1)])
    assert r1.returncode == 0, r1.stderr
    # rerun -> same queries/scores (payload timestamp may differ; compare queries block)
    r2 = _run_cli(["--lexical", str(lex), "--dense", str(den), "--config", str(CONFIG), "--output", str(out2)])
    assert r2.returncode == 0, r2.stderr
    q1 = json.loads(out1.read_text(encoding="utf-8"))["queries"]
    q2 = json.loads(out2.read_text(encoding="utf-8"))["queries"]
    assert q1 == q2


def test_cli_missing_file_exit_1(tmp_path: Path) -> None:
    r = _run_cli(["--lexical", str(tmp_path / "nope.json"), "--dense", str(tmp_path / "nope2.json"), "--config", str(CONFIG), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
    assert "FAIL" in r.stderr


def test_cli_mismatched_queries_exit_1(tmp_path: Path) -> None:
    lex = tmp_path / "lex.json"
    den = tmp_path / "den.json"
    lex.write_text(json.dumps({"q1": ["A"]}), encoding="utf-8")
    den.write_text(json.dumps({"q2": ["A"]}), encoding="utf-8")
    r = _run_cli(["--lexical", str(lex), "--dense", str(den), "--config", str(CONFIG), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1


def test_cli_malformed_json_exit_1(tmp_path: Path) -> None:
    lex = tmp_path / "lex.json"
    den = tmp_path / "den.json"
    lex.write_text("{not json", encoding="utf-8")
    den.write_text(json.dumps({"q1": ["A"]}), encoding="utf-8")
    r = _run_cli(["--lexical", str(lex), "--dense", str(den), "--config", str(CONFIG), "--output", str(tmp_path / "o.json")])
    assert r.returncode == 1
