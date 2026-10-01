"""Unit, integration and adversarial tests for Public Paper Search UI (EXT-05A, Wave W2).

Strict Anti-Silent-Bypass Protocol:
- Positive tests:
  * Template inspection: ui/templates/search.html contains explicit navigation link to /public/ui.
  * Template inspection: ui/templates/public_search.html contains required forms, inputs, language notice,
    sources checkboxes, year range bounds, action buttons, tabs, detail panel, library section.
  * CSS stylesheet verification: ui/static/public_search.css contains required banners, badges, and accessible states.
  * Real JavaScript execution via Node.js DOM test harness (node_test_runner.js) verifying:
    - Safe URL sanitization (isSafeUrl) rejecting javascript:, data:, credentials, control chars, backslashes.
    - Strict envelope validation (validateEnvelope) rejecting missing required fields or counter mismatches.
    - All 7 Truth Table cases (TT-01..TT-07) and 9 Mandatory UI states.
    - XSS prevention and safe textContent rendering.
    - Race condition and sequence counter protection.
    - Refresh failure and previous snapshot review button.
    - Idempotent library saving.
- Negative & Adversarial tests (Destructive testing):
  * Node test runner called with non-existent fixtures file -> exits with nonzero code 1.
  * Node test runner called with non-existent UX examples file -> exits with nonzero code 1.
  * Node test runner called with malformed JSON fixture in temp directory -> exits with nonzero code 1.
  * Contract validation on malformed envelopes in ui_fixtures.json -> raises ValidationError.
  * Leakage detection probe: rejects forbidden research labels/qrels/splits in fixture metadata.
  * CLI boundary of test_public_ui: exits code 0 on valid check, code 1 on missing resources.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholargraph.public_search.contracts import (
    CONTRACT_VERSION,
    SCHEMA_VERSION,
    LibraryEntry,
    SearchEnvelope,
    SearchSnapshot,
    SourceResult,
    safe_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXE = (
    Path("D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe")
    if Path("D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe").is_file()
    else Path(sys.executable)
)
NODE_EXE_PATH = Path("C:/Program Files/nodejs/node.exe")
NODE_CMD = str(NODE_EXE_PATH) if NODE_EXE_PATH.is_file() else (shutil.which("node") or "node")

UI_DIR = PROJECT_ROOT / "ui"
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "public_search" / "gemini" / "ui"
UX_EXAMPLES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "public_search" / "gemini" / "ux_examples.json"
NODE_RUNNER_PATH = FIXTURES_DIR / "node_test_runner.js"


def test_search_html_contains_public_link():
    """Verify that search.html has the explicit navigation link to /public/ui."""
    search_html = TEMPLATES_DIR / "search.html"
    assert search_html.is_file(), "ui/templates/search.html must exist"
    content = search_html.read_text(encoding="utf-8")
    assert "/public/ui" in content, "search.html must link to /public/ui"
    assert 'href="/public/ui"' in content or "href='/public/ui'" in content, "search.html must have href='/public/ui'"
    assert "Tìm kiếm công khai" in content or "public" in content.lower(), "search.html must have descriptive text"


def test_public_search_html_structure():
    """Verify semantic structure, form controls, notices and accessibility attributes of public_search.html."""
    pub_html = TEMPLATES_DIR / "public_search.html"
    assert pub_html.is_file(), "ui/templates/public_search.html must exist"
    content = pub_html.read_text(encoding="utf-8")

    # Navigation back to offline search
    assert 'href="/"' in content or "href='/'" in content, "public_search.html must contain link back to /"

    # Form and inputs
    assert 'id="public-search-form"' in content, "Missing form id public-search-form"
    assert 'id="q"' in content, "Missing query input id q"
    assert 'id="language-notice"' in content, "Missing language notice"
    assert "chưa tự động dịch Việt–Anh" in content, "Language notice wording must be present"

    # Sources
    assert 'id="src-openalex"' in content, "Missing openalex source checkbox"
    assert 'id="src-arxiv"' in content, "Missing arxiv source checkbox"
    assert 'id="sources-error"' in content, "Missing sources error container"

    # Year filters
    assert 'id="year_from"' in content, "Missing year_from input"
    assert 'id="year_to"' in content, "Missing year_to input"
    assert "excluded_by_year" in content, "Missing excluded_by_year notice"
    assert 'id="years-error"' in content, "Missing years error container"

    # Top-K and Cap
    assert 'id="top_k"' in content, "Missing top_k input"
    assert 'id="cap_per_source"' in content, "Missing cap_per_source input"

    # Buttons
    assert 'id="btn-search"' in content, "Missing btn-search"
    assert 'id="btn-refresh"' in content, "Missing btn-refresh"

    # Tabs & Sections
    assert 'id="tab-search"' in content, "Missing tab-search button"
    assert 'id="tab-library"' in content, "Missing tab-library button"
    assert 'id="search-section"' in content, "Missing search-section"
    assert 'id="library-section"' in content, "Missing library-section"
    assert 'id="results"' in content, "Missing results container"
    assert 'id="library-list"' in content, "Missing library-list container"
    assert 'id="detail-panel"' in content, "Missing detail-panel container"

    # Script tag
    assert 'src="/static/public_search.js"' in content, "Missing script inclusion of public_search.js"
    assert 'href="/static/public_search.css"' in content, "Missing css inclusion of public_search.css"


def test_public_search_css_rules():
    """Verify that public_search.css includes necessary state and badge classes."""
    pub_css = STATIC_DIR / "public_search.css"
    assert pub_css.is_file(), "ui/static/public_search.css must exist"
    content = pub_css.read_text(encoding="utf-8")

    required_classes = [
        ".banner-error",
        ".banner-warning",
        ".banner-success",
        ".banner-info",
        ".badge-source",
        ".badge-fresh",
        ".badge-stale",
        ".badge-oa-unknown",
        ".badge-idempotent",
        ".detail-panel",
        ".provenance-table",
    ]
    for cls in required_classes:
        assert cls in content, f"CSS missing required rule/class: {cls}"


def test_ui_fixtures_sidecar_and_integrity():
    """Verify that ui_fixtures.json and sidecar are strictly synthetic and non-live."""
    fixtures_file = FIXTURES_DIR / "ui_fixtures.json"
    sidecar_file = FIXTURES_DIR / "ui_fixtures.sidecar.json"
    assert fixtures_file.is_file(), "ui_fixtures.json must exist"
    assert sidecar_file.is_file(), "ui_fixtures.sidecar.json must exist"

    data = json.loads(fixtures_file.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_file.read_text(encoding="utf-8"))

    assert data.get("synthetic") is True, "ui_fixtures.json must declare synthetic: true"
    assert data.get("not_live_evidence") is True, "ui_fixtures.json must declare not_live_evidence: true"
    assert data.get("not_for_production_fallback") is True, "ui_fixtures.json must declare not_for_production_fallback: true"
    assert sidecar.get("synthetic") is True, "sidecar must declare synthetic: true"


def test_safe_url_contract_conformance():
    """Verify that Python contracts safe_url rejects the same unsafe URLs defined in ui_fixtures.json."""
    fixtures_file = FIXTURES_DIR / "ui_fixtures.json"
    data = json.loads(fixtures_file.read_text(encoding="utf-8"))

    safe_list = data["fixtures"]["safe_urls"]
    unsafe_list = data["fixtures"]["unsafe_urls"]

    for u in safe_list:
        assert safe_url(u) == u, f"Expected {u} to be safe"

    for u in unsafe_list:
        with pytest.raises(ValueError):
            safe_url(u)


def test_malformed_envelopes_fail_pydantic_schema():
    """Verify that all malformed envelopes in ui_fixtures.json fail Pydantic model validation."""
    fixtures_file = FIXTURES_DIR / "ui_fixtures.json"
    data = json.loads(fixtures_file.read_text(encoding="utf-8"))
    malformed_cases = data["fixtures"]["malformed_envelopes"]

    for name, env_dict in malformed_cases.items():
        with pytest.raises(ValidationError):
            SearchEnvelope.model_validate(env_dict)


def test_node_dom_test_runner_all_tests():
    """Run real JavaScript execution of public_search.js via Node.js DOM test harness."""
    node_exe = shutil.which(NODE_CMD) or (str(NODE_EXE_PATH) if NODE_EXE_PATH.is_file() else None)
    if not node_exe:
        pytest.fail(f"Node.js executable not available at {NODE_CMD}; JS execution gate is mandatory.")

    ui_fixtures_path = FIXTURES_DIR / "ui_fixtures.json"
    assert NODE_RUNNER_PATH.is_file(), "node_test_runner.js must exist"

    cmd = [
        node_exe,
        str(NODE_RUNNER_PATH),
        "--fixtures",
        str(ui_fixtures_path),
        "--ux-examples",
        str(UX_EXAMPLES_PATH),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print("STDOUT:\n", result.stdout)
    if result.returncode != 0:
        print("STDERR:\n", result.stderr)

    assert result.returncode == 0, f"Node.js test harness failed with exit code {result.returncode}"
    assert "ALL TESTS PASSED WITH EXIT CODE 0!" in result.stdout


def test_negative_node_runner_missing_fixtures():
    """Negative test: node_test_runner fails with exit code 1 when fixtures file does not exist."""
    node_exe = shutil.which(NODE_CMD) or (str(NODE_EXE_PATH) if NODE_EXE_PATH.is_file() else None)
    if not node_exe:
        pytest.fail(f"Node.js executable not available at {NODE_CMD}; JS execution gate is mandatory.")

    cmd = [
        node_exe,
        str(NODE_RUNNER_PATH),
        "--fixtures",
        str(FIXTURES_DIR / "does_not_exist.json"),
        "--ux-examples",
        str(UX_EXAMPLES_PATH),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, "Expected exit code 1 for missing fixtures"
    assert "FAIL:" in result.stderr or "FAIL:" in result.stdout


def test_negative_node_runner_missing_ux_examples():
    """Negative test: node_test_runner fails with exit code 1 when ux_examples does not exist."""
    node_exe = shutil.which(NODE_CMD) or (str(NODE_EXE_PATH) if NODE_EXE_PATH.is_file() else None)
    if not node_exe:
        pytest.fail(f"Node.js executable not available at {NODE_CMD}; JS execution gate is mandatory.")

    cmd = [
        node_exe,
        str(NODE_RUNNER_PATH),
        "--fixtures",
        str(FIXTURES_DIR / "ui_fixtures.json"),
        "--ux-examples",
        str(FIXTURES_DIR / "does_not_exist_ux.json"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, "Expected exit code 1 for missing UX examples"
    assert "FAIL:" in result.stderr or "FAIL:" in result.stdout


def test_negative_node_runner_malformed_json(tmp_path: Path):
    """Negative test: node_test_runner fails with exit code 1 when given a malformed JSON file."""
    node_exe = shutil.which(NODE_CMD) or (str(NODE_EXE_PATH) if NODE_EXE_PATH.is_file() else None)
    if not node_exe:
        pytest.fail(f"Node.js executable not available at {NODE_CMD}; JS execution gate is mandatory.")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{ unclosed json content: 123", encoding="utf-8")

    cmd = [
        node_exe,
        str(NODE_RUNNER_PATH),
        "--fixtures",
        str(bad_json),
        "--ux-examples",
        str(UX_EXAMPLES_PATH),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, "Expected exit code 1 for malformed JSON"


def test_negative_leakage_probes():
    """Negative test: Probe for leakage of forbidden research tokens (labels, qrels, splits) in metadata."""
    fixtures_file = FIXTURES_DIR / "ui_fixtures.json"
    text = fixtures_file.read_text(encoding="utf-8")
    data = json.loads(text)

    # In top-level and metadata keys, forbidden keys should not be present
    forbidden_keys = {"labels", "qrels", "splits", "ground_truth", "test_set_citations"}
    for k in data.keys():
        assert k not in forbidden_keys, f"Forbidden leakage key '{k}' found in fixture root"

    for k in data.get("fixtures", {}).keys():
        assert k not in forbidden_keys, f"Forbidden leakage key '{k}' found in fixture entries"


def test_adversarial_source_result_required_fields_and_types():
    """Adversarial test (Finding 1): SourceResult strictly enforces presence and types of source_total, elapsed_seconds, truncated."""
    valid_row = {
        "source": "openalex",
        "status": "empty",
        "records": [],
        "error": None,
        "source_total": 0,
        "elapsed_seconds": 0.5,
        "filter_coverage": "server",
        "truncated": False,
        "raw_references": [],
    }
    # Happy path passes
    assert SourceResult.model_validate(valid_row).status == "empty"

    # 1. Missing source_total
    bad1 = copy.deepcopy(valid_row)
    del bad1["source_total"]
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad1)

    # 2. Missing truncated
    bad2 = copy.deepcopy(valid_row)
    del bad2["truncated"]
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad2)

    # 3. Missing elapsed_seconds
    bad3 = copy.deepcopy(valid_row)
    del bad3["elapsed_seconds"]
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad3)

    # 4. String source_total
    bad4 = copy.deepcopy(valid_row)
    bad4["source_total"] = "wrong"
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad4)

    # 5. Non-boolean truncated
    bad5 = copy.deepcopy(valid_row)
    bad5["truncated"] = "wrong"
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad5)

    # 6. Negative elapsed_seconds
    bad6 = copy.deepcopy(valid_row)
    bad6["elapsed_seconds"] = -1.0
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad6)

    # 7. not_requested with observations
    bad7 = copy.deepcopy(valid_row)
    bad7["status"] = "not_requested"
    bad7["filter_coverage"] = "none"
    bad7["source_total"] = 1
    with pytest.raises(ValidationError):
        SourceResult.model_validate(bad7)


def test_adversarial_datetime_year_and_offset_rejection():
    """Adversarial test (Finding 2): Reject year 0000 and timezone offsets outside valid range."""
    ux_data = json.loads(UX_EXAMPLES_PATH.read_text(encoding="utf-8"))
    base_envelope = ux_data["examples"]["example_03_tt02_success_plus_empty_with_hit"]["envelope"]

    # Year 0000
    bad_year = copy.deepcopy(base_envelope)
    bad_year["snapshot"]["fetched_at"] = "0000-01-01T00:00:00Z"
    with pytest.raises(ValidationError):
        SearchEnvelope.model_validate(bad_year)

    # Offset outside valid range (+23:59)
    bad_tz = copy.deepcopy(base_envelope)
    bad_tz["snapshot"]["fetched_at"] = "2026-01-01T00:00:00+23:59"
    with pytest.raises(ValidationError):
        SearchEnvelope.model_validate(bad_tz)


def test_adversarial_idempotent_library_entry_preserves_original_snapshot():
    """Adversarial test (Finding 3): Idempotent library entry retains original snapshot_id while matching canonical_id."""
    fixtures_file = FIXTURES_DIR / "ui_fixtures.json"
    data = json.loads(fixtures_file.read_text(encoding="utf-8"))
    entry_dict = data["fixtures"]["idempotent_library_save"]

    # Entry is valid per contract
    entry = LibraryEntry.model_validate_json(json.dumps(entry_dict))
    assert entry.canonical_id == entry.hit.canonical_id

    # Simulated duplicate save where paper came from snap_newer_999, but store returned existing snap_syn_w2_001
    assert entry.snapshot_id == "snap_syn_w2_001"

    # Negative test: canonical_id mismatch with hit MUST raise ValidationError
    bad_entry = copy.deepcopy(entry_dict)
    bad_entry["canonical_id"] = "mismatched_canonical_id"
    with pytest.raises(ValidationError, match="library identity mismatch"):
        LibraryEntry.model_validate_json(json.dumps(bad_entry))


def test_cli_boundary_subprocess():
    """Verify that test_public_ui can be executed directly as a Python CLI module."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    # 1. Valid execution
    cmd = [str(PYTHON_EXE), "-m", "tests.unit.test_public_ui", "--check"]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0
    assert "VALIDATED: public UI templates, static files, and node harness" in res.stdout

    # 2. Invalid option -> exit 1 (Anti-silent-bypass)
    cmd_bad = [str(PYTHON_EXE), "-m", "tests.unit.test_public_ui", "--unknown-flag"]
    res_bad = subprocess.run(cmd_bad, capture_output=True, text=True, env=env)
    assert res_bad.returncode == 1


def test_negative_cli_missing_node_resource():
    """Negative test: CLI exits with code 1 when Node.js is missing (Anti-silent-bypass)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    cmd = [
        str(PYTHON_EXE),
        "-c",
        "import sys, tests.unit.test_public_ui as m; m.NODE_CMD = 'nonexistent_node_bin_xyz'; m.NODE_EXE_PATH = m.Path('C:/nonexistent/node.exe'); sys.exit(m.main())",
        "--check",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 1, "CLI must exit 1 when Node.js is missing"
    assert "FAIL: Node.js executable not available" in res.stderr


def main() -> int:
    """CLI boundary for test_public_ui."""
    parser = argparse.ArgumentParser(description="Public UI verification CLI boundary")
    parser.add_argument("--check", action="store_true", help="Run static and template verification checks")
    args, unknown = parser.parse_known_args()

    if unknown:
        print(f"FAIL: unrecognized arguments: {unknown}", file=sys.stderr)
        return 1

    # Verify templates and static files exist and contain required anchors
    search_html = TEMPLATES_DIR / "search.html"
    pub_html = TEMPLATES_DIR / "public_search.html"
    pub_js = STATIC_DIR / "public_search.js"
    pub_css = STATIC_DIR / "public_search.css"
    fixtures_json = FIXTURES_DIR / "ui_fixtures.json"

    for p in (search_html, pub_html, pub_js, pub_css, fixtures_json):
        if not p.is_file():
            print(f"FAIL: required file not found: {p}", file=sys.stderr)
            return 1

    node_exe = shutil.which(NODE_CMD) or (str(NODE_EXE_PATH) if NODE_EXE_PATH.is_file() else None)
    if not node_exe:
        print(f"FAIL: Node.js executable not available at {NODE_CMD}", file=sys.stderr)
        return 1

    if not NODE_RUNNER_PATH.is_file():
        print(f"FAIL: required file not found: {NODE_RUNNER_PATH}", file=sys.stderr)
        return 1

    if "/public" not in search_html.read_text(encoding="utf-8"):
        print("FAIL: search.html does not link to /public", file=sys.stderr)
        return 1

    if "public-search-form" not in pub_html.read_text(encoding="utf-8"):
        print("FAIL: public_search.html missing public-search-form", file=sys.stderr)
        return 1

    print("VALIDATED: public UI templates, static files, and node harness exist and are well-formed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
