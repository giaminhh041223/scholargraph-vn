"""SG-039 integration tests: full script pass + fast pin/leakage guards."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)


def test_manifest_pins_fast() -> None:
    mom = json.loads((PROJECT_ROOT / "data" / "manifests" / "openalex_core.json").read_text(encoding="utf-8"))
    assert mom["artifacts"]["works_jsonl"]["sha256"] == "04e7008e6e536d10adbd9acaba3d0e5a2e335035e958b216f09ad3c628fd60a4"
    gm = json.loads((PROJECT_ROOT / "data" / "manifests" / "graph_core.json").read_text(encoding="utf-8"))
    assert gm["counts"]["internal_directed_edges_postmask"] == 26186
    vn = json.loads((PROJECT_ROOT / "data" / "annotations" / "vn_query_manifest.json").read_text(encoding="utf-8"))
    assert len(vn["queries"]) == 30


def test_serving_path_reads_no_qrels() -> None:
    hits = []
    for rel in ("src/scholargraph/api/service.py", "src/scholargraph/api/app.py",
                "src/scholargraph/api/graph_service.py", "ui/static/app.js",
                "scripts/integration_checks.py"):
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            if "qrel" in low and "no qrel" not in low:
                hits.append(f"{rel}:{i}")
    assert hits == []


def test_integration_script_all_pass() -> None:
    env = dict(os.environ)
    r = subprocess.run([str(PYTHON), "scripts/integration_checks.py"],
                       capture_output=True, text=True, cwd=PROJECT_ROOT, env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    report = (PROJECT_ROOT / "artifacts" / "reports" / "integration_checks.md").read_text(encoding="utf-8")
    assert "[!]" not in report


def test_write_report_exit_code_unit() -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "integration_checks", PROJECT_ROOT / "scripts" / "integration_checks.py")
    assert spec is not None and spec.loader is not None
    # prove the FAIL branch without running the heavy pipeline: feed synthetic
    # failing results straight into the pure report writer.
    import tempfile
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # noqa: imports only define helpers (no main run)
    except SystemExit:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rep.md"
        assert mod.write_report([("a", True, ""), ("b", False, "boom")], out) == 1
        text = out.read_text(encoding="utf-8")
        assert "[!]" in text and "boom" in text
        assert mod.write_report([("a", True, "")], out) == 0
