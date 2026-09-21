"""SG-028 sealed final runs — positive + adversarial tests (all synthetic)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.data.schemas import RankedDocument, RankingResult
from scholargraph.evaluation.runner import FinalTestGateError, RunStore

import run_final
from scholargraph.evaluation import sealed as sealed_mod


def _runs(qids, doc_ids=("d1", "d2", "d3"), score=1.0) -> dict[str, RankingResult]:
    return {q: RankingResult(query_id=q, candidates=[
        RankedDocument(doc_id=d, score=score / (i + 1), rank=i + 1)
        for i, d in enumerate(doc_ids)]) for q in qids}


# ---- policy checks (synthetic) ----

def test_policy_check_passes_clean():
    out = run_final.policy_check(_runs(["q1", "q2"]), ["q1", "q2"], ["d1", "d2", "d3", "d9"], "m")
    assert out["queries"] == 2 and out["duplicate_docs"] == 0


def test_policy_rejects_nan_score():
    runs = _runs(["q1"])
    # Bypass schema validation to prove the policy layer itself catches NaN.
    object.__setattr__(runs["q1"].candidates[0], "score", float("nan"))
    with pytest.raises(RuntimeError, match="non-finite"):
        run_final.policy_check(runs, ["q1"], ["d1", "d2", "d3"], "m")


def test_policy_rejects_missing_query():
    with pytest.raises(RuntimeError, match="!= split queries"):
        run_final.policy_check(_runs(["q1"]), ["q1", "q2"], ["d1", "d2", "d3"], "m")


def test_policy_rejects_outside_universe_candidate():
    with pytest.raises(RuntimeError, match="outside corpus universe"):
        run_final.policy_check(_runs(["q1"]), ["q1"], ["d1", "d2"], "m")


def test_policy_rejects_duplicate_doc():
    runs = _runs(["q1"])
    runs["q1"].candidates.append(RankedDocument(doc_id="d1", score=0.01, rank=4))
    with pytest.raises(RuntimeError, match="duplicate"):
        run_final.policy_check(runs, ["q1"], ["d1", "d2", "d3"], "m")


def test_policy_rejects_empty_ranking():
    runs = {"q1": RankingResult(query_id="q1", candidates=[])}
    with pytest.raises(RuntimeError, match="empty ranking"):
        run_final.policy_check(runs, ["q1"], ["d1"], "m")


# ---- sealed gate (synthetic, tmp RunStore) ----

def test_unsealed_test_run_refused(tmp_path):
    for name in ("corpus.jsonl", "split.json", "code.py"):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    store = RunStore(tmp_path / "runs")
    with pytest.raises(FinalTestGateError):
        store.create(method="bm25", dataset="scifact", split="test",
                     resolved_config={"resolved": False, "track": "A",
                                      "dataset": "scifact", "split": "test"},
                     data_source=tmp_path / "corpus.jsonl",
                     split_definition=tmp_path / "split.json",
                     code_source=tmp_path / "code.py",
                     model={"id": "m", "revision": "r"}, seed=1,
                     command=["cmd"], protocol_source=None, synthetic=False)


def test_sealed_evidence_rejects_non_test_split(tmp_path):
    with pytest.raises(RuntimeError, match="only built for locked test splits"):
        sealed_mod.build_final_test_evidence(
            project_root=tmp_path, freeze={}, freeze_sha256="x",
            track="A", method="bm25", dataset="scifact", split="dev",
            resolved_config={}, data_source=tmp_path / "c",
            split_definition=tmp_path / "s", model={"id": "m", "revision": "r"},
            evaluator_revision="sg008-1.0.0", leakage_notes=[])


def test_sealed_evidence_rejects_empty_evaluator_revision(tmp_path):
    with pytest.raises(RuntimeError, match="evaluator_revision"):
        sealed_mod.build_final_test_evidence(
            project_root=tmp_path, freeze={}, freeze_sha256="x",
            track="A", method="bm25", dataset="scifact", split="test",
            resolved_config={}, data_source=tmp_path / "c",
            split_definition=tmp_path / "s", model={"id": "m", "revision": "r"},
            evaluator_revision=" ", leakage_notes=[])


def test_cli_rejects_unknown_step():
    with pytest.raises(SystemExit) as exc:
        run_final.main(["--only", "bogus-step"])
    assert exc.value.code != 0


def test_step_rejects_unknown_dataset():
    with pytest.raises(RuntimeError):
        run_final.load_split("nope-dataset", "test")


# ---- live consistency (reads real sealed artifacts, asserts no test tuning) ----

def test_live_registry_consistent_with_freeze():
    reg_path = ROOT / "artifacts" / "reports" / "main_run_registry.json"
    freeze = json.loads((ROOT / "configs" / "frozen_main.json").read_text(encoding="utf-8"))
    if not reg_path.is_file():
        pytest.skip("Sealed registry not built yet in this checkout")
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    assert reg["freeze_sha256"] == sealed_mod._sha_file(ROOT / "configs" / "frozen_main.json")
    have = {(r["method"], r["dataset"]) for r in reg["track_A_runs"]}
    assert have == {("bm25", "scifact"), ("tfidf", "scifact"), ("dense", "scifact"),
                    ("hybrid", "scifact"), ("bm25", "scidocs"),
                    ("dense", "scidocs"), ("hybrid", "scidocs")}
    assert all(r["status"] == "COMPLETED" for r in reg["track_A_runs"])
    # Track B: exactly the frozen arms, weights identical to the dev selection.
    sel = freeze["tuning_selection"]["track_B_best"]
    assert set(reg["track_B"]["arms"]) == {"ppr_age_best_g0.3_l0.0", "global_pagerank_control"}
    assert reg["track_B"]["frozen_weights"]["gamma"] == sel["gamma"] == 0.3
    assert reg["track_B"]["frozen_weights"]["lambda"] == sel["lambda"] == 0.0
    # Track C must stay unmeasured (never 0 or empty string).
    assert reg["track_C_vn"]["status"] not in (0, "", None)
    assert "SG-033" in reg["track_C_vn"]["reason"]
