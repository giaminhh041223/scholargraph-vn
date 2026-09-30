"""REVIEWER PROBE EXT-05A W2 082 wire/CLI — MUSE independent.
Target contracts READ ONLY via target src import path.
Allowed write: management/public_search/reviews/MUSE/probes-ui-082/
Synthetic fixtures only, tmp dir under probes-ui-082/tmp-diag.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TARGET_SRC = Path(r"D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph\src")
sys.path.insert(0, str(TARGET_SRC))
import scholargraph.public_search.contracts as C  # noqa: E402
print("contracts file:", C.__file__)
print("contract", C.CONTRACT_VERSION, "schema", C.SCHEMA_VERSION)

TARGET_ROOT = Path(r"D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph")
UX = json.loads((TARGET_ROOT / "tests/fixtures/public_search/gemini/ux_examples.json").read_text(encoding="utf-8"))
PASS = 0
FAIL = 0

def check(cond, pid, detail):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {pid} :: {detail}")
    else:
        FAIL += 1
        print(f"[FAIL] {pid} :: {detail}")

# W-TRUTH: 6 envelope cases validate via contracts (wire JSON semantics: model_validate_json)
for key in ["example_02_tt01_all_empty", "example_03_tt02_success_plus_empty_with_hit",
            "example_04_tt03_success_sources_filtered_to_zero",
            "example_05_tt04_empty_plus_failed_no_hit",
            "example_06_tt05_success_plus_failed_partial_failure_with_hits",
            "example_07_tt06_all_failed_mixed_precedence",
            "example_11_storage_error_500_and_xss_url_sanitization"]:
    env = UX["examples"][key].get("envelope")
    if env is None:
        check(False, f"W-TRUTH-{key}", "no envelope")
        continue
    try:
        C.SearchEnvelope.model_validate_json(json.dumps(env))
        check(True, f"W-TRUTH-{key}", f"contracts ACCEPT overall={env['overall']} (expected, via validate_json)")
    except Exception as e:
        check(False, f"W-TRUTH-{key}", f"contracts REJECT valid fixture: {e}")

# W-FAIL-NULL: failed with snapshot null must ACCEPT
try:
    C.SearchEnvelope.model_validate_json(json.dumps(UX["examples"]["example_07_tt06_all_failed_mixed_precedence"]["envelope"]))
    check(True, "W-FAIL-NULL", "failed+snapshot null accepted per contract")
except Exception as e:
    check(False, "W-FAIL-NULL", str(e)[:200])

# W-PARTIAL-NOSNAP must REJECT
bad = {"schema_version": 1, "contract_version": "1.0.0", "overall": "partial_failure",
       "snapshot": None, "errors": [{"kind": "timeout", "message": "t", "source": "arxiv",
                                     "retry_after_seconds": None, "record_index": None}],
       "stale": False, "cached": False}
try:
    C.SearchEnvelope.model_validate_json(json.dumps(bad))
    check(False, "W-PARTIAL-NOSNAP", "contracts ACCEPT partial without snapshot (should REJECT)")
except Exception:
    check(True, "W-PARTIAL-NOSNAP", "contracts REJECT partial without snapshot (correct)")

# W-EXTRA: extra labels/splits must REJECT (contract extra=forbid)
base = json.loads(json.dumps(UX["examples"]["example_03_tt02_success_plus_empty_with_hit"]["envelope"]))
base["labels"] = [{"q": 1}]
try:
    C.SearchEnvelope.model_validate_json(json.dumps(base))
    check(False, "W-EXTRA-labels", "contracts ACCEPT extra labels (should REJECT)")
except Exception:
    check(True, "W-EXTRA-labels", "contracts REJECT extra labels (correct) — JS validateEnvelope ACCEPTS (see JS probe)")

base2 = json.loads(json.dumps(UX["examples"]["example_03_tt02_success_plus_empty_with_hit"]["envelope"]))
base2["splits"] = ["train"]
try:
    C.SearchEnvelope.model_validate_json(json.dumps(base2))
    check(False, "W-EXTRA-splits", "ACCEPT splits")
except Exception:
    check(True, "W-EXTRA-splits", "REJECT splits (correct)")

# W-SOURCE: selected status/count invariants
from scholargraph.public_search.contracts import SearchRequest, SourceResult
req = SearchRequest.model_validate({"query": "x", "sources": ["openalex", "arxiv"], "top_k": 10,
                                    "cap_per_source": 10, "year_from": None, "year_to": None, "refresh": False})
# success without records must fail
try:
    SourceResult.model_validate({"source": "openalex", "status": "success", "records": [], "error": None,
                                 "source_total": 0, "elapsed_seconds": 0.1, "filter_coverage": "server",
                                 "truncated": False, "raw_references": []})
    check(False, "W-SOURCE-success-empty", "ACCEPT success no records")
except Exception:
    check(True, "W-SOURCE-success-empty", "REJECT success without records (correct)")

# W-RANK: score 0 / rank 0 must fail (validate_json for datetime-containing hit)
hit0 = json.loads(json.dumps(UX["examples"]["example_03_tt02_success_plus_empty_with_hit"]["envelope"]["snapshot"]["fusion"]["hits"][0]))
for name, mut in [("score-zero", {"score": 0}), ("rank-zero", {"rank": 0})]:
    h = dict(json.loads(json.dumps(hit0)))
    h.update(mut)
    try:
        C.RankedHit.model_validate_json(json.dumps(h))
        check(False, f"W-RANK-{name}", f"ACCEPT {name}")
    except Exception:
        check(True, f"W-RANK-{name}", f"REJECT {name} (correct) — JS ACCEPTS (see JS probe)")
# NaN is not valid JSON; test via python object (allow_inf_nan=False must reject)
try:
    h = dict(json.loads(json.dumps(hit0)))
    h["score"] = float("nan")
    C.RankedHit.model_validate(h)
    check(False, "W-RANK-score-nan", "ACCEPT NaN")
except Exception:
    check(True, "W-RANK-score-nan", "REJECT NaN (correct) — JS ACCEPTS")

# W-DISPLAY: missing_fields/provenance
rec = hit0["display"]
check("missing_fields" in rec and "field_provenance" in rec, "W-DISPLAY-present", "display has missing_fields/field_provenance")
try:
    C.PaperRecord.model_validate_json(json.dumps(rec))
    check(True, "W-DISPLAY-valid", "display record validates via wire JSON")
except Exception as e:
    check(False, "W-DISPLAY-valid", f"display fails: {e}"[:300])

# W-LIB: LibraryEntry incompleteSources
lib = UX["examples"]["example_10_library_save_idempotent_and_export"]["library_entry"]
try:
    C.LibraryEntry.model_validate_json(json.dumps(lib))
    check(lib["incomplete_sources"] is True, "W-LIB-incomplete", f"incomplete_sources={lib['incomplete_sources']} (partial snapshot badge)")
except Exception as e:
    check(False, "W-LIB-incomplete", str(e)[:300])

# W-URL: contracts safe_url
for u in ["https://arxiv.org/abs/2401.00001"]:
    try:
        C.safe_url(u)
        check(True, "W-URL-safe", u)
    except Exception:
        check(False, "W-URL-safe", u)
for u in ["javascript:alert(1)", "http://user:pass@example.com/x", "http://example.com\\a", "http://example.com/a\x00b", "ftp://example.com/x", ""]:
    try:
        C.safe_url(u)
        check(False, "W-URL-unsafe", f"ACCEPT {repr(u)}")
    except Exception:
        check(True, "W-URL-unsafe", f"REJECT {repr(u)[:60]}")

# W-NOSKIP: Node missing must FAIL not skip
tpy = (TARGET_ROOT / "tests/unit/test_public_ui.py").read_text(encoding="utf-8")
check("pytest.skip" in tpy, "W-NOSKIP-gap", "test_public_ui.py contains pytest.skip for missing Node (5 occurrences) — required JS gate would be silently SKIPPED, must FAIL")

# W-CLI-UI: unknown/missing
PY = r"D:\Web_mining_20261\scholargraph\.venv\Scripts\python.exe"
import os
env = dict(os.environ)
env["PYTHONPATH"] = str(TARGET_SRC)
def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))

r = run([PY, "-m", "tests.unit.test_public_ui", "--check"])
check(r.returncode == 0 and "VALIDATED" in r.stdout, "W-CLI-check", f"exit={r.returncode} out={r.stdout[:80]!r}")
r = run([PY, "-m", "tests.unit.test_public_ui", "--unknown-flag"])
check(r.returncode == 1, "W-CLI-unknown", f"unknown args exit={r.returncode} (expected 1)")
# missing resource via tmp copy? simulate by calling node runner with missing file
NODE = r"C:\Program Files\nodejs\node.exe"
rr = subprocess.run([NODE, str(TARGET_ROOT / "tests/fixtures/public_search/gemini/ui/node_test_runner.js"),
                     "--fixtures", str(TARGET_ROOT / "tests/fixtures/public_search/gemini/ui/does_not_exist.json"),
                     "--ux-examples", str(TARGET_ROOT / "tests/fixtures/public_search/gemini/ux_examples.json")],
                    capture_output=True, text=True)
check(rr.returncode == 1, "W-CLI-missing", f"node missing fixtures exit={rr.returncode} (expected 1)")

# W-CLI-CONTRACTS: duplicate/nonfinite/extra/malformed must exit1
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    cfg_src = Path(r"D:\Web_mining_20261\scholargraph\configs\public_search.json")
    cfg = td / "cfg.json"
    cfg.write_bytes(cfg_src.read_bytes())
    good_req = {"query": "x", "sources": ["openalex"], "top_k": 5, "cap_per_source": 5,
                "year_from": None, "year_to": None, "refresh": False}
    rq = td / "req.json"
    rq.write_text(json.dumps(good_req), encoding="utf-8")
    r = subprocess.run([PY, "-m", "scholargraph.public_search.contracts", "--config", str(cfg), "--request", str(rq)],
                       capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
    check(r.returncode == 0, "W-CLI-good", f"valid req exit={r.returncode}")
    # malformed
    (td / "bad.json").write_text("{bad", encoding="utf-8")
    r = subprocess.run([PY, "-m", "scholargraph.public_search.contracts", "--config", str(cfg), "--request", str(td / "bad.json")],
                       capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
    check(r.returncode == 1, "W-CLI-malformed", f"malformed exit={r.returncode}")
    # duplicate keys
    (td / "dup.json").write_text('{"query":"x","query":"y","sources":["openalex"],"top_k":5,"cap_per_source":5,"year_from":null,"year_to":null,"refresh":false}', encoding="utf-8")
    r = subprocess.run([PY, "-m", "scholargraph.public_search.contracts", "--config", str(cfg), "--request", str(td / "dup.json")],
                       capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
    check(r.returncode == 1, "W-CLI-duplicate", f"duplicate exit={r.returncode}")
    # nonfinite
    (td / "inf.json").write_text('{"query":"x","sources":["openalex"],"top_k":Infinity,"cap_per_source":5,"year_from":null,"year_to":null,"refresh":false}', encoding="utf-8")
    r = subprocess.run([PY, "-m", "scholargraph.public_search.contracts", "--config", str(cfg), "--request", str(td / "inf.json")],
                       capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
    check(r.returncode == 1, "W-CLI-nonfinite", f"nonfinite exit={r.returncode}")
    # extra labels
    ex = dict(good_req)
    ex["labels"] = [1]
    (td / "extra.json").write_text(json.dumps(ex), encoding="utf-8")
    r = subprocess.run([PY, "-m", "scholargraph.public_search.contracts", "--config", str(cfg), "--request", str(td / "extra.json")],
                       capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
    check(r.returncode == 1, "W-CLI-extra", f"extra labels exit={r.returncode}")
    # missing resource
    r = subprocess.run([PY, "-m", "scholargraph.public_search.contracts", "--config", str(cfg), "--request", str(td / "nope.json")],
                       capture_output=True, text=True, env=env, cwd=str(TARGET_ROOT))
    check(r.returncode == 1, "W-CLI-missing2", f"missing exit={r.returncode}")

print(f"\n=== WIRE PROBE SUMMARY PASS={PASS} FAIL={FAIL} ===")
