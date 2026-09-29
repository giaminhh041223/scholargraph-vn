"""SG-029 ablation and robustness — positive + adversarial tests (synthetic first)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import run_ablation
from scholargraph.retrieval.hybrid import rrf_fuse


def test_rrf_k60_reproduces_pinned_fusion():
    lex = [f"lex{i}" for i in range(5)] + ["shared"]
    den = [f"den{i}" for i in range(5)] + ["shared"]
    got = run_ablation._rrf_with_k(lex, den, k=60)
    want = rrf_fuse(lex, den, k=60)
    assert [(r["doc_id"], r["rrf"]) for r in got] == [(r["doc_id"], r["rrf"]) for r in want]


def test_rrf_k_variation_changes_scores_but_keeps_valid_order():
    lex = [f"d{i}" for i in range(10)]
    den = [f"d{i}" for i in range(5, 15)]  # partial overlap: k reweights shared vs unique
    a = run_ablation._rrf_with_k(lex, den, k=30)
    b = run_ablation._rrf_with_k(lex, den, k=100)
    assert [r["rrf"] for r in a] != [r["rrf"] for r in b]
    for rows in (a, b):
        scores = [r["rrf"] for r in rows]
        assert scores == sorted(scores, reverse=True)
        assert len({r["doc_id"] for r in rows}) == len(rows)


def test_rrf_with_k_rejects_bad_inputs():
    with pytest.raises(RuntimeError):
        run_ablation._rrf_with_k(["a"], ["b"], k=0)
    with pytest.raises(RuntimeError):
        run_ablation._rrf_with_k([], ["b"], k=30)
    with pytest.raises(RuntimeError):
        run_ablation._rrf_with_k(["a", "a"], ["b"], k=30)
    with pytest.raises(RuntimeError):
        run_ablation._rrf_with_k(["a"] * 101, ["b"], k=30)


def test_bucket_mean_empty_is_null_not_zero():
    assert run_ablation._bucket_mean({"q1": {"nDCG@10": 0.5}}, [], "nDCG@10") is None
    assert run_ablation._bucket_mean({}, ["q9"], "nDCG@10") is None


def test_bucket_mean_rejects_nan():
    perq = {"q1": {"nDCG@10": float("nan")}}
    with pytest.raises(RuntimeError, match="Non-finite"):
        run_ablation._bucket_mean(perq, ["q1"], "nDCG@10")


def test_bucket_mean_value():
    perq = {"q1": {"nDCG@10": 0.5}, "q2": {"nDCG@10": 1.0}}
    assert run_ablation._bucket_mean(perq, ["q1", "q2"], "nDCG@10") == pytest.approx(0.75)


def test_terciles_rejects_tiny_input():
    with pytest.raises(RuntimeError, match="Too few"):
        run_ablation._terciles([1.0, 2.0])


def test_ndcg10_perfect_and_no_positive():
    assert run_ablation._ndcg10(["a", "b"], {"a": 1, "b": 1}) == pytest.approx(1.0)
    assert 0.0 < run_ablation._ndcg10(["x", "a"], {"a": 1}) < 1.0
    with pytest.raises(RuntimeError, match="without positives"):
        run_ablation._ndcg10(["x"], {})


def test_prespecified_variant_sets_unchanged():
    # Trip-wire: extending these sets needs a freeze bump + ADR, not a quiet edit.
    assert run_ablation.AGE_LAMBDAS == (0.0, 0.01, 0.03, 0.1)
    assert run_ablation.AGE_GAMMA == 0.3
    assert run_ablation.RRF_KS == (30, 60, 100)


def test_cli_rejects_unknown_step():
    with pytest.raises(SystemExit) as exc:
        run_ablation.main(["--only", "bogus"])
    assert exc.value.code != 0


def test_live_ablation_arms_within_prespecified_plan():
    age_path = ROOT / "artifacts" / "reports" / "ablation_age.json"
    rrf_path = ROOT / "artifacts" / "reports" / "ablation_rrfk.json"
    if not (age_path.is_file() and rrf_path.is_file()):
        pytest.skip("Ablation artifacts not built yet in this checkout")
    age = json.loads(age_path.read_text(encoding="utf-8"))
    allowed_age = {f"ppr_g0.3_l{lam}" for lam in run_ablation.AGE_LAMBDAS} | \
                  {f"global_g0.3_l{lam}" for lam in run_ablation.AGE_LAMBDAS}
    assert set(age["arms"]) == allowed_age, "unplanned age arm = test tuning"
    rrf = json.loads(rrf_path.read_text(encoding="utf-8"))
    allowed_rrf = {f"hybrid_rrf_k{k}_{d}" for k in run_ablation.RRF_KS for d in ("scifact", "scidocs")}
    assert set(rrf["arms"]) == allowed_rrf, "unplanned RRF arm = test tuning"
    live_freeze = json.loads((ROOT / "configs" / "frozen_main.json").read_bytes().decode("utf-8"))
    _ = live_freeze
    from scholargraph.evaluation.sealed import _sha_file
    assert age["freeze_sha256"] == _sha_file(ROOT / "configs" / "frozen_main.json")
    assert rrf["freeze_sha256"] == _sha_file(ROOT / "configs" / "frozen_main.json")


def test_ablation_markdown_table_columns_aligned():
    lines = run_ablation._build_ablation_lines(
        "deadbeef",
        {"arms": {"global_g0.3_l0.0": {"nDCG@10": 0.1, "Recall@100": 0.2, "MRR@10": 0.1}}},
        {"track_A_runs": [{"method": "bm25", "dataset": "scifact", "metrics": {"nDCG@10": 0.66}, "run_id": "RUN-1"}]},
        {"arms": {"hybrid_rrf_k60_scifact": {"nDCG@10": 0.72}}},
    )
    assert "| arm | dataset | nDCG@10 | run_id |" in lines
    in_table = False
    expected_cols = 0
    for line in lines:
        if line.startswith("|"):
            cols = len(line.strip("|").split("|"))
            if not in_table:
                in_table = True
                expected_cols = cols
            else:
                assert cols == expected_cols, f"Table column mismatch on line: {line}"
        else:
            in_table = False
