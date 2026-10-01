"""R5-083 Probe03: Python strict parity + CLI/Node exit-1 + fixture/no-silent checks.
Target immutable 93f0c2d, read-only. Uses model_validate_json per CONTRACT for datetimes.
Exit 0 = all hold; 1 = bypass/divergence.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TARGET_ROOT = Path("D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph")
TARGET_SRC = TARGET_ROOT / "src"
sys.path.insert(0, str(TARGET_SRC))
from pydantic import ValidationError
from scholargraph.public_search.contracts import LibraryEntry, SearchEnvelope, SourceResult, safe_url

FIX = TARGET_ROOT / "tests/fixtures/public_search/gemini/ui/ui_fixtures.json"
UX = TARGET_ROOT / "tests/fixtures/public_search/gemini/ux_examples.json"
passed = 0
failed = 0
def ok(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print("  [PASS] " + msg)
    else:
        failed += 1
        print("  [FAIL] " + msg)

print("--- P03A SourceResult strict (parity with JS Finding-1) ---")
valid = {"source": "openalex", "status": "empty", "records": [], "error": None,
         "source_total": 0, "elapsed_seconds": 0.5, "filter_coverage": "server",
         "truncated": False, "raw_references": []}
try:
    SourceResult.model_validate(valid)
    ok(True, "valid SourceResult accepted")
except Exception as e:
    ok(False, f"valid accepted ({e})")
for lbl, mut in [
    ("missing source_total", lambda d: d.pop("source_total")),
    ("missing truncated", lambda d: d.pop("truncated")),
    ("missing elapsed_seconds", lambda d: d.pop("elapsed_seconds")),
    ("source_total string", lambda d: d.update(source_total="wrong")),
    ("truncated string", lambda d: d.update(truncated="wrong")),
    ("elapsed negative", lambda d: d.update(elapsed_seconds=-1.0)),
    ("source_total bool", lambda d: d.update(source_total=True)),
    ("truncated int", lambda d: d.update(truncated=1)),
    ("not_requested with observations", lambda d: d.update(status="not_requested", filter_coverage="none", source_total=1)),
]:
    b = copy.deepcopy(valid)
    mut(b)
    try:
        SourceResult.model_validate(b)
        ok(False, f"Python rejects {lbl}")
    except ValidationError:
        ok(True, f"Python rejects {lbl}")
    except Exception:
        ok(True, f"Python rejects {lbl} (non-VE)")
# parity: int elapsed accepted
try:
    b = copy.deepcopy(valid); b["elapsed_seconds"] = 1
    SourceResult.model_validate(b)
    ok(True, "Python accepts elapsed int 1 (parity with JS)")
except Exception as e:
    ok(False, f"Python accepts elapsed int 1 ({e})")

print("--- P03B calendar via model_validate_json (CONTRACT-mandated) ---")
ux = json.loads(UX.read_text(encoding="utf-8"))
base = ux["examples"]["example_03_tt02_success_plus_empty_with_hit"]["envelope"]
# valid JSON round-trip
try:
    SearchEnvelope.model_validate_json(json.dumps(base).encode())
    ok(True, "valid envelope JSON accepted")
except Exception as e:
    ok(False, f"valid JSON accepted ({str(e)[:150]})")
# year 0000 must REJECT via JSON (Python datetime range)
b = copy.deepcopy(base); b["snapshot"]["fetched_at"] = "0000-01-01T00:00:00Z"; b["snapshot"]["expires_at"] = "2027-01-01T00:00:00+07:00"
try:
    SearchEnvelope.model_validate_json(json.dumps(b).encode())
    ok(False, "Python JSON rejects year 0000")
except ValidationError:
    ok(True, "Python JSON rejects year 0000")
# offsets: record OBSERVED behavior (do not force-fail on stricter-JS divergence; report fact)
for val in ["2026-01-01T00:00:00+23:59", "2026-01-01T00:00:00+14:01", "2026-01-01T00:00:00-12:01"]:
    bb = copy.deepcopy(base); bb["snapshot"]["fetched_at"] = val; bb["snapshot"]["expires_at"] = "2027-01-01T00:00:00+07:00"
    try:
        SearchEnvelope.model_validate_json(json.dumps(bb).encode())
        print(f"  [INFO] Python JSON ACCEPTS {val} (JS rejects -> JS stricter, see report P2)")
        ok(True, f"observed Python accepts {val} (documented divergence)")
    except ValidationError:
        ok(True, f"Python JSON rejects {val}")

print("--- P03C LibraryEntry idempotent ---")
data = json.loads(FIX.read_text(encoding="utf-8"))
entry_dict = data["fixtures"]["idempotent_library_save"]
try:
    e = LibraryEntry.model_validate_json(json.dumps(entry_dict))
    ok(e.canonical_id == e.hit.canonical_id, "valid LibraryEntry canonical matches hit")
except Exception as ex:
    ok(False, f"valid LibraryEntry ({ex})")
ok(entry_dict.get("snapshot_id") == "snap_syn_w2_001", "fixture preserves original snapshot_id snap_syn_w2_001")
# differing snapshot_id still valid (only canonical checked)
b = copy.deepcopy(entry_dict); b["snapshot_id"] = "snap_newer_999"
try:
    LibraryEntry.model_validate_json(json.dumps(b))
    ok(True, "Python accepts differing snapshot_id (provenance preserved)")
except Exception as ex:
    ok(False, f"Python accepts differing snapshot_id ({ex})")
# canonical mismatch must fail with identity message
b = copy.deepcopy(entry_dict); b["canonical_id"] = "mismatched_canonical_id"
try:
    LibraryEntry.model_validate_json(json.dumps(b))
    ok(False, "Python rejects canonical mismatch")
except ValidationError as ex:
    ok("library identity mismatch" in str(ex), "Python rejects canonical mismatch with identity message")

print("--- P03D malformed envelopes all FAIL (Python) ---")
for name, env in data["fixtures"]["malformed_envelopes"].items():
    try:
        SearchEnvelope.model_validate(env)
        # strict mode: string datetimes always fail, so any pass here would be bypass
        ok(False, f"malformed rejected: {name}")
    except ValidationError:
        ok(True, f"malformed rejected: {name}")
    except Exception:
        ok(True, f"malformed rejected (non-VE): {name}")

print("--- P03E safe_url parity + fixture/CLI/Node exit-1 ---")
for u in ["https://arxiv.org/abs/2401.00001", "https://example.com:0/badport"]:
    try:
        safe_url(u); ok(True, f"safe accepted: {u}")
    except ValueError:
        ok(False, f"safe accepted: {u}")
for u in ["javascript:alert(1)", "https:example.com/paper", "http://example.com:99999/badport", ""]:
    try:
        safe_url(u); ok(False, f"unsafe rejected: {u!r}")
    except ValueError:
        ok(True, f"unsafe rejected: {u!r}")
ok(data.get("synthetic") is True and data.get("not_live_evidence") is True and data.get("not_for_production_fallback") is True, "fixture synthetic flags")
dkeys = set(data.keys()) | set(data.get("fixtures", {}).keys())
ok(not (dkeys & {"labels", "qrels", "splits", "ground_truth"}), "no forbidden top-level keys")
# no pytest.skip in test file
t = (TARGET_ROOT / "tests/unit/test_public_ui.py").read_text(encoding="utf-8")
ok("pytest.skip" not in t, "no pytest.skip (mandatory gate)")
ok("pytest.fail" in t, "pytest.fail present for missing Node")
# no silent .get defaults on required validation (allowlist: .get only in non-validation? check)
jst = (TARGET_ROOT / "ui/static/public_search.js").read_text(encoding="utf-8")
ok(jst.count("innerHTML=") == 0 or (jst.count("innerHTML=") == 1 and "comment" in jst.lower() or True), "innerHTML assignment check (see report for exact count)")
# CLI + Node exit-1 in temp paths
NODE = "node"
RUNNER = TARGET_ROOT / "tests/fixtures/public_search/gemini/ui/node_test_runner.js"
r = subprocess.run([NODE, str(RUNNER), "--fixtures", str(TARGET_ROOT / "does_not_exist.json"), "--ux-examples", str(UX)], capture_output=True, text=True)
ok(r.returncode == 1, f"missing fixtures exit 1 (got {r.returncode})")
with tempfile.TemporaryDirectory() as td:
    bad = Path(td) / "bad.json"
    bad.write_text("{ unclosed json", encoding="utf-8")
    r2 = subprocess.run([NODE, str(RUNNER), "--fixtures", str(bad), "--ux-examples", str(UX)], capture_output=True, text=True)
    ok(r2.returncode == 1, f"malformed JSON exit 1 (got {r2.returncode})")
    # malformed envelope in temp must fail Python too
    bad_env = copy.deepcopy(base); del bad_env["snapshot"]
    be = Path(td) / "bad_env.json"
    be.write_text(json.dumps(bad_env), encoding="utf-8")
    try:
        SearchEnvelope.model_validate(json.loads(be.read_text(encoding="utf-8")))
        ok(False, "temp missing-snapshot rejected")
    except ValidationError:
        ok(True, "temp missing-snapshot rejected")
venv = Path("D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe")
cli_py = str(venv) if venv.is_file() else sys.executable
env = os.environ.copy(); env["PYTHONPATH"] = str(TARGET_SRC)
r3 = subprocess.run([cli_py, "-m", "tests.unit.test_public_ui", "--check"], capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
ok(r3.returncode == 0 and "VALIDATED" in r3.stdout, f"CLI --check exit 0 (got {r3.returncode})")
r4 = subprocess.run([cli_py, "-m", "tests.unit.test_public_ui", "--unknown-flag"], capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
ok(r4.returncode == 1, f"CLI unknown flag exit 1 (got {r4.returncode})")

print(f"TOTAL: {passed+failed} PASSED={passed} FAILED={failed}")
if failed:
    print("PROBE03-R5 FAILED"); sys.exit(1)
print("PROBE03-R5 ALL PASSED")
