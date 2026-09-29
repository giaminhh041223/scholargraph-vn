"""Unit and adversarial tests for scripts/verify_claims.py (SG-043)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_claims.py"
EVIDENCE_PATH = ROOT / "artifacts" / "reports" / "evidence_index.json"
REPORT_PATH = ROOT / "reports" / "final_report.md"
CHECKLIST_PATH = ROOT / "docs" / "CLAIMS_CHECKLIST.md"


def test_verify_claims_real_files_pass() -> None:
    res = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--evidence-index",
            str(EVIDENCE_PATH),
            "--report",
            str(REPORT_PATH),
            "--checklist",
            str(CHECKLIST_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    assert '"status": "PASS"' in res.stdout


def test_verify_claims_rejects_missing_claim_id_exit_1(tmp_path: Path) -> None:
    bad_report = tmp_path / "bad_report.md"
    bad_report.write_text(
        REPORT_PATH.read_text(encoding="utf-8").replace("CLM-004", "CLM-XXX"),
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--evidence-index",
            str(EVIDENCE_PATH),
            "--report",
            str(bad_report),
            "--checklist",
            str(CHECKLIST_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "missing claim IDs" in res.stderr


def test_verify_claims_rejects_p_value_and_sota_exit_1(tmp_path: Path) -> None:
    for injected in ("Kết quả có ý nghĩa thống kê với p < 0.05.", "We achieve state-of-the-art results."):
        bad_report = tmp_path / "bad_report.md"
        bad_report.write_text(
            REPORT_PATH.read_text(encoding="utf-8") + "\n" + injected,
            encoding="utf-8",
        )
        res = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--evidence-index",
                str(EVIDENCE_PATH),
                "--report",
                str(bad_report),
                "--checklist",
                str(CHECKLIST_PATH),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 1
        assert "forbidden" in res.stderr


def test_verify_claims_rejects_altered_metric_exit_1(tmp_path: Path) -> None:
    bad_report = tmp_path / "bad_report.md"
    bad_report.write_text(
        REPORT_PATH.read_text(encoding="utf-8").replace("0.7404", "0.9999"),
        encoding="utf-8",
    )
    res = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--evidence-index",
            str(EVIDENCE_PATH),
            "--report",
            str(bad_report),
            "--checklist",
            str(CHECKLIST_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "missing primary metric values" in res.stderr
