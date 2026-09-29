"""Unit and adversarial tests for SG-042 / SG-043 scripts (evidence_index, compare_reproduction, generate_figures)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE_SCRIPT = ROOT / "scripts" / "compare_reproduction.py"
EVIDENCE_SCRIPT = ROOT / "scripts" / "build_evidence_index.py"
FIGURES_SCRIPT = ROOT / "scripts" / "generate_figures.py"
EVIDENCE_PATH = ROOT / "artifacts" / "reports" / "evidence_index.json"


def test_evidence_index_exists_and_matches_freeze(tmp_path: Path) -> None:
    out = tmp_path / "evidence_index.json"
    res = subprocess.run(
        [sys.executable, str(EVIDENCE_SCRIPT), "--output", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["freeze_manifest"]["sha256"] == "34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557"
    assert len(doc["tables"]["table_1_track_a_main"]) == 7
    assert len(doc["tables"]["table_6_paired_bootstrap"]) == 24
    assert doc["tables"]["table_3_track_c_vn"]["status"] == "chua_do"


def test_evidence_index_missing_root_exits_1(tmp_path: Path) -> None:
    res = subprocess.run(
        [
            sys.executable,
            str(EVIDENCE_SCRIPT),
            "--project-root",
            str(tmp_path / "missing_root"),
            "--output",
            str(tmp_path / "out.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "FAIL:" in res.stderr


def test_compare_reproduction_within_tolerance_passes(tmp_path: Path) -> None:
    ev_doc = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    scifact_bm25 = dict(ev_doc["tables"]["table_1_track_a_main"]["scifact__bm25"]["metrics"])
    scifact_bm25["nDCG@10"] += 5e-5  # within 1e-4 tolerance
    ppr_arm = dict(ev_doc["tables"]["table_2_track_b_main"]["arms"]["ppr_age_best_g0.3_l0.0"])

    cand_path = tmp_path / "candidate.json"
    cand_path.write_text(
        json.dumps(
            {
                "track_A": {"scifact__bm25": {"metrics": scifact_bm25}},
                "track_B": {"ppr_age_best_g0.3_l0.0": ppr_arm},
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "audit_out"
    res = subprocess.run(
        [
            sys.executable,
            str(COMPARE_SCRIPT),
            "--reproducer",
            "member_B_human",
            "--candidate",
            str(cand_path),
            "--evidence-index",
            str(EVIDENCE_PATH),
            "--output-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    assert (out_dir / "reproduction_audit.json").is_file()
    assert (out_dir / "reproduction_audit.md").is_file()


def test_compare_reproduction_rejects_agent_reproducer_exit_1(tmp_path: Path) -> None:
    cand_path = tmp_path / "candidate.json"
    cand_path.write_text(json.dumps({"track_A": {}}), encoding="utf-8")
    for bad_name in ("agent", "codex_worker", "gemini", "claude", ""):
        res = subprocess.run(
            [
                sys.executable,
                str(COMPARE_SCRIPT),
                "--reproducer",
                bad_name,
                "--candidate",
                str(cand_path),
                "--evidence-index",
                str(EVIDENCE_PATH),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 1


def test_compare_reproduction_rejects_drift_and_out_of_bounds_exit_1(tmp_path: Path) -> None:
    ev_doc = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    drifted = dict(ev_doc["tables"]["table_1_track_a_main"]["scifact__bm25"]["metrics"])
    drifted["nDCG@10"] += 5e-4  # exceeds 1e-4 tolerance

    cand_path = tmp_path / "drifted.json"
    cand_path.write_text(
        json.dumps({"track_A": {"scifact__bm25": {"metrics": drifted}}}),
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            sys.executable,
            str(COMPARE_SCRIPT),
            "--reproducer",
            "member_B_human",
            "--candidate",
            str(cand_path),
            "--evidence-index",
            str(EVIDENCE_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "drifted beyond tolerance" in res.stderr

    # Out-of-bounds metric (> 1.0)
    oob = dict(ev_doc["tables"]["table_1_track_a_main"]["scifact__bm25"]["metrics"])
    oob["nDCG@10"] = 1.2
    oob_path = tmp_path / "oob.json"
    oob_path.write_text(
        json.dumps({"track_A": {"scifact__bm25": {"metrics": oob}}}),
        encoding="utf-8",
    )
    res_oob = subprocess.run(
        [
            sys.executable,
            str(COMPARE_SCRIPT),
            "--reproducer",
            "member_B_human",
            "--candidate",
            str(oob_path),
            "--evidence-index",
            str(EVIDENCE_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_oob.returncode == 1
    assert "outside [0, 1]" in res_oob.stderr


def test_generate_figures_happy_and_missing_exits_1(tmp_path: Path) -> None:
    fig_dir = tmp_path / "figs"
    res_ok = subprocess.run(
        [
            sys.executable,
            str(FIGURES_SCRIPT),
            "--evidence-index",
            str(EVIDENCE_PATH),
            "--output-dir",
            str(fig_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_ok.returncode == 0, res_ok.stderr
    for name in (
        "fig1_track_a_ndcg10.svg",
        "fig2_track_b_openalex.svg",
        "fig3_ablation_age_rrf.svg",
        "fig4_latency_budget.svg",
    ):
        assert (fig_dir / name).is_file()

    res_bad = subprocess.run(
        [
            sys.executable,
            str(FIGURES_SCRIPT),
            "--evidence-index",
            str(tmp_path / "missing.json"),
            "--output-dir",
            str(fig_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_bad.returncode == 1
