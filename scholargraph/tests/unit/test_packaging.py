"""SG-041 packaging and release — positive + adversarial tests (synthetic first)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_release


def test_version_compare_handles_suffixes():
    assert verify_release._version_at_least("2.14.0+cpu", "2.0.0") is True
    assert verify_release._version_at_least("1.18.1", "1.12.0") is True
    assert verify_release._version_at_least("0.28.1", "0.28.0") is True
    assert verify_release._version_at_least("1.0.0", "2.0.0") is False
    assert verify_release._version_at_least("3.12.14", "3.12") is True


def test_fail_returns_nonzero():
    assert verify_release.fail("synthetic probe") == 1


def test_requirements_lock_clean_and_pinned():
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
    assert len(lock) >= 20
    has_cpu_index = False
    for line in lock:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "--extra-index-url https://download.pytorch.org/whl/cpu":
            has_cpu_index = True
            continue
        assert re.fullmatch(r"[A-Za-z0-9_.\-]+==\S+", line), f"unpinned line: {line}"
        assert "file://" not in line and "@" not in line.split("==")[0]
    assert has_cpu_index, "requirements.lock must include PyTorch CPU extra-index-url for torch==2.14.0+cpu"


def test_demo_launcher_wires_required_stages():
    text = (ROOT / "scripts" / "run_demo.ps1").read_text(encoding="utf-8")
    for needle in ("verify_release.py", "offline_smoke.py", "HF_HUB_OFFLINE", "exit 1", "DEMO_SCRIPT.md"):
        assert needle in text, f"launcher lacks {needle}"
    bat = (ROOT.parent / "run_demo.bat").read_text(encoding="utf-8")
    assert ">1" not in bat, "run_demo.bat must not contain unescaped >1 redirection"
    assert not (ROOT / "1").exists(), "stray scholargraph/1 file from batch redirection must not exist"
    for doc_rel in ("docs/REPRODUCE.md", "docs/DEMO_SCRIPT.md"):
        doc_text = (ROOT / doc_rel).read_text(encoding="utf-8")
        assert "bn\\scholargraph" not in doc_text and "bn/scholargraph" not in doc_text, (
            f"{doc_rel} still contains hardcoded bn path"
        )


def test_release_manifest_matches_live_freeze():
    manifest = ROOT / "docs" / "RELEASE_MANIFEST.md"
    assert manifest.is_file()
    text = manifest.read_text(encoding="utf-8")
    freeze_sha = verify_release.check_freeze()["freeze_sha256"]
    assert freeze_sha in text
    assert "requirements.lock" in text and "REPRODUCE.md" in text


def test_write_manifest_to_tmp(tmp_path):
    report = verify_release.run_all()
    outp = tmp_path / "RELEASE_MANIFEST.md"
    verify_release.write_manifest(report, outp)
    text = outp.read_text(encoding="utf-8")
    assert report["freeze"]["freeze_sha256"] in text
    if report["git_head"]:
        assert report["git_head"][:12] in text
    assert "torch==" in text


def test_live_release_passes():
    report = verify_release.run_all()
    assert report["status"] == "PASS"
    assert report["freeze"]["files_checked"] >= 30
    assert all(v is True for v in report["statics"]["cli_modules"].values())
