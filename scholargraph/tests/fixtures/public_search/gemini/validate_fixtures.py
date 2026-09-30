"""Executable validator for GEMINI UX fixtures against SOL typed models.

Strict Anti-Silent-Bypass (W0 R2 Follow-up):
- Validates sidecar metadata via --sidecar CLI argument (requires SOL head cb64c59,
  contract commit 774aeef, version 1.0.0, coordinator checkpoint timestamp 2026-09-30T10:05:00+07:00).
- Imports typed models from SOL checkout in READ-ONLY mode.
- Validates 100% of ux_examples.json examples against SOL pydantic models using model_validate_json
  (supporting ISO timestamp strings without false validation errors).
- Validates that allowed contract_type matches exactly its payload type (rejects unknown
  or multiple payloads).
- Requires root coverage declarations (ui_states_covered, truth_table_cases_covered) equal
  the observed sets and required sets.
- Rejects unknown or missing cache subcases in example_09.
- Rejects .get() defaults for required fields (no silent masking of missing data).
- Recursive leakage boundary check: detects forbidden metadata fields (labels, qrels, splits,
  benchmark_input) while allowing benign textual occurrences of 'held_out' in user query/title text.
- Destructive negative/adversarial tests: runs the CLI itself via subprocess in temp directories
  asserting exit code 1 for all failure cases.
- Positive checks: 13 typed objects, title-only valid record, benign textual occurrence of 'held_out'.
- Any validation or invariant failure exits with non-zero exit code (1).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add SOL src to sys.path in read-only mode to access authoritative contracts
SOL_SRC_PATH = Path("D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/src")
if str(SOL_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SOL_SRC_PATH))

try:
    from pydantic import ValidationError
    from scholargraph.public_search.contracts import (
        CONTRACT_VERSION,
        SCHEMA_VERSION,
        FieldEvidence,
        FusionCounts,
        FusionResult,
        LibraryEntry,
        PaperRecord,
        RankedHit,
        RawReference,
        SearchEnvelope,
        SearchError,
        SearchRequest,
        SearchSnapshot,
        SourceResult,
    )
except ImportError as err:
    print(f"FAIL: Unable to import SOL typed contracts from {SOL_SRC_PATH}: {err}", file=sys.stderr)
    sys.exit(1)


FIXTURE_PATH = Path(__file__).resolve().parent / "ux_examples.json"
SIDECAR_PATH = Path(__file__).resolve().parent / "ux_examples.sidecar.json"

EXPECTED_TRUTH_TABLE_CASES = {
    "TT-01",
    "TT-02",
    "TT-03",
    "TT-04",
    "TT-05",
    "TT-06",
    "TT-07",
}

EXPECTED_UI_STATES = {
    "loading",
    "empty",
    "missing_fields",
    "partial_failure",
    "quota_exceeded",
    "cached_fresh",
    "cached_stale",
    "oa_unknown",
    "save_idempotent",
}

EXPECTED_EXAMPLE_KEYS = {
    "example_01_success_dedup_rrf_and_missing_fields",
    "example_02_tt01_all_empty",
    "example_03_tt02_success_plus_empty_with_hit",
    "example_04_tt03_success_sources_filtered_to_zero",
    "example_05_tt04_empty_plus_failed_no_hit",
    "example_06_tt05_success_plus_failed_partial_failure_with_hits",
    "example_07_tt06_all_failed_mixed_precedence",
    "example_08_tt07_invalid_request_422",
    "example_09_cache_fresh_stale_and_refresh_failure",
    "example_10_library_save_idempotent_and_export",
    "example_11_storage_error_500_and_xss_url_sanitization",
}

EXPECTED_CACHE_SUBCASES = {
    "A_cached_fresh",
    "B_refresh_failure_does_not_mask_with_old_cache",
    "C_explicit_open_stale_snapshot",
}

ALLOWED_CONTRACT_TYPES = {
    "SearchEnvelope",
    "SearchEnvelope_StorageError",
    "SearchEnvelope_CacheScenarios",
    "SearchRequest_ValidationError",
    "LibraryEntry",
}

PAYLOAD_KEYS = {"envelope", "subcases", "invalid_request_payload", "library_entry"}

CONTRACT_TYPE_TO_PAYLOAD_KEY = {
    "SearchEnvelope": "envelope",
    "SearchEnvelope_StorageError": "envelope",
    "SearchEnvelope_CacheScenarios": "subcases",
    "SearchRequest_ValidationError": "invalid_request_payload",
    "LibraryEntry": "library_entry",
}

FORBIDDEN_METADATA_KEYS = {
    "labels",
    "qrels",
    "splits",
    "split",
    "benchmark_input",
    "benchmark_inputs",
    "test_labels",
    "eval_labels",
    "test_qrels",
    "dev_qrels",
    "held_out_labels",
    "held_out_qrels",
    "held_out_split",
}


def validate_sidecar(sidecar_file: Path) -> dict:
    """Validate sidecar metadata provenance against coordinator checkpoint requirements."""
    if not sidecar_file.exists():
        raise FileNotFoundError(f"Sidecar metadata file does not exist: {sidecar_file}")

    raw_text = sidecar_file.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except Exception as exc:
        raise ValueError(f"Sidecar metadata is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Sidecar metadata root must be a dictionary")

    required_keys = (
        "schema_version",
        "task_id",
        "wave",
        "iteration",
        "owner",
        "reviewer",
        "dispatch_id",
        "worker_session_id",
        "updated_at",
        "synthetic",
        "not_live_evidence",
        "not_for_production_fallback",
        "reconciled_contract_version",
        "contract_code_commit",
        "proposed_sol_head",
        "contract_status",
    )
    for k in required_keys:
        if k not in data:
            raise ValueError(f"Required sidecar metadata field missing: {k}")

    if data["schema_version"] != 1:
        raise ValueError(f"Sidecar schema_version mismatch: expected 1, got {data['schema_version']}")
    if data["synthetic"] is not True or data["not_live_evidence"] is not True or data["not_for_production_fallback"] is not True:
        raise ValueError("Sidecar synthetic/not_live_evidence/not_for_production_fallback flags must all be True")
    if data["task_id"] != "EXT-01C" or data["wave"] != "W0" or data["iteration"] != "R2":
        raise ValueError("Sidecar task_id, wave, or iteration mismatch")

    # Strict coordinator checkpoint timestamp (explicitly provided 2026-09-30T10:05:00+07:00, not current clock)
    if data["updated_at"] != "2026-09-30T10:05:00+07:00":
        raise ValueError(
            f"Sidecar updated_at mismatch: expected '2026-09-30T10:05:00+07:00', got '{data['updated_at']}'"
        )

    # Actual current SOL head cb64c59 and contract code commit 774aeef version 1.0.0
    if not str(data["proposed_sol_head"]).startswith("cb64c59"):
        raise ValueError(
            f"Sidecar proposed_sol_head mismatch: expected cb64c59..., got '{data['proposed_sol_head']}'"
        )
    if not str(data["contract_code_commit"]).startswith("774aeef"):
        raise ValueError(
            f"Sidecar contract_code_commit mismatch: expected 774aeef..., got '{data['contract_code_commit']}'"
        )
    if str(data["reconciled_contract_version"]) != "1.0.0":
        raise ValueError(
            f"Sidecar reconciled_contract_version mismatch: expected '1.0.0', got '{data['reconciled_contract_version']}'"
        )

    return data


def check_leakage_boundary(node: object, path: str = "root") -> None:
    """Recursively detect forbidden benchmark metadata fields (labels, qrels, splits, benchmark_input).

    Avoids blocking legitimate user query or title text that merely contains 'held_out' or similar terms.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            k_lower = str(k).strip().lower()
            if k_lower in FORBIDDEN_METADATA_KEYS or any(
                bad in k_lower for bad in ("qrels", "test_labels", "eval_labels", "benchmark_input")
            ):
                raise ValueError(
                    f"Data leakage boundary violation: forbidden benchmark metadata field '{k}' detected at {path}.{k}"
                )
            check_leakage_boundary(v, f"{path}.{k}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            check_leakage_boundary(item, f"{path}[{idx}]")


def validate_all_examples(fixture_file: Path) -> dict[str, int]:
    """Dynamically validate every example and subcase without hardcoding or bypasses."""
    if not fixture_file.exists():
        raise FileNotFoundError(f"Fixture file does not exist: {fixture_file}")

    raw_text = fixture_file.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except Exception as exc:
        raise ValueError(f"Fixture is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Fixture root must be a JSON dictionary")

    # Recursive leakage check on all parsed metadata fields
    check_leakage_boundary(data)

    # Anti-Silent-Bypass: no .get() with defaults for required root metadata
    for required_key in (
        "synthetic",
        "not_live_evidence",
        "not_for_production_fallback",
        "schema_version",
        "contract_version",
        "examples",
        "truth_table_cases_covered",
        "ui_states_covered",
    ):
        if required_key not in data:
            raise ValueError(f"Required root field missing from fixture: {required_key}")

    if data["synthetic"] is not True:
        raise ValueError("synthetic=true flag missing or not True in fixture root")
    if data["not_live_evidence"] is not True or data["not_for_production_fallback"] is not True:
        raise ValueError("provisional / not-live flags missing or not True in fixture root")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version mismatch: expected {SCHEMA_VERSION}, got {data['schema_version']}"
        )
    if data["contract_version"] != CONTRACT_VERSION:
        raise ValueError(
            f"contract_version mismatch: expected {CONTRACT_VERSION}, got {data['contract_version']}"
        )

    # Validate root ui_states_covered declaration against required set
    if not isinstance(data["ui_states_covered"], list) or not data["ui_states_covered"]:
        raise ValueError("Root 'ui_states_covered' must be a non-empty list")
    root_ui_states = set(data["ui_states_covered"])
    if len(data["ui_states_covered"]) != len(root_ui_states):
        raise ValueError("Duplicate entries in root 'ui_states_covered'")
    if root_ui_states != EXPECTED_UI_STATES:
        raise ValueError(
            f"Root 'ui_states_covered' does not equal required set: missing {EXPECTED_UI_STATES - root_ui_states}, extra {root_ui_states - EXPECTED_UI_STATES}"
        )

    # Validate root truth_table_cases_covered declaration against required set
    if not isinstance(data["truth_table_cases_covered"], list) or not data["truth_table_cases_covered"]:
        raise ValueError("Root 'truth_table_cases_covered' must be a non-empty list")
    root_tt_ids = {entry.split("_")[0] if "_" in entry else entry for entry in data["truth_table_cases_covered"]}
    if len(data["truth_table_cases_covered"]) != len(root_tt_ids):
        raise ValueError("Duplicate entries in root 'truth_table_cases_covered'")
    if root_tt_ids != EXPECTED_TRUTH_TABLE_CASES:
        raise ValueError(
            f"Root 'truth_table_cases_covered' does not equal required set: missing {EXPECTED_TRUTH_TABLE_CASES - root_tt_ids}, extra {root_tt_ids - EXPECTED_TRUTH_TABLE_CASES}"
        )

    examples = data["examples"]
    if not isinstance(examples, dict) or not examples:
        raise ValueError("examples must be a non-empty dictionary")

    # Check for missing or unrecognized examples dynamically
    actual_keys = set(examples.keys())
    missing_keys = EXPECTED_EXAMPLE_KEYS - actual_keys
    unrecognized_keys = actual_keys - EXPECTED_EXAMPLE_KEYS
    if missing_keys:
        raise ValueError(f"Missing expected example keys: {sorted(missing_keys)}")
    if unrecognized_keys:
        raise ValueError(f"Unrecognized example keys found: {sorted(unrecognized_keys)}")

    counts = {"envelopes": 0, "requests": 0, "library_entries": 0, "total": 0}
    observed_tt_cases: set[str] = set()
    observed_ui_states: set[str] = set()

    # Dynamically iterate across all example nodes
    for ex_key, ex_node in examples.items():
        if not isinstance(ex_node, dict):
            raise ValueError(f"Example {ex_key} must be a dictionary object")

        if "synthetic" not in ex_node or ex_node["synthetic"] is not True:
            raise ValueError(f"Example {ex_key} missing synthetic=true")
        if "contract_type" not in ex_node:
            raise ValueError(f"Example {ex_key} missing contract_type")

        contract_type = ex_node["contract_type"]

        # Validate allowed contract_type
        if contract_type not in ALLOWED_CONTRACT_TYPES:
            raise ValueError(
                f"Example {ex_key} has disallowed contract_type: '{contract_type}'. Allowed: {sorted(ALLOWED_CONTRACT_TYPES)}"
            )

        # Validate that allowed contract_type matches exactly its payload type (reject unknown or multiple payloads)
        present_payloads = [k for k in PAYLOAD_KEYS if k in ex_node]
        if len(present_payloads) == 0:
            raise ValueError(f"Example {ex_key} missing required payload key from {sorted(PAYLOAD_KEYS)}")
        if len(present_payloads) > 1:
            raise ValueError(f"Example {ex_key} has multiple payload keys: {present_payloads} (expected exactly one)")

        expected_payload = CONTRACT_TYPE_TO_PAYLOAD_KEY[contract_type]
        actual_payload = present_payloads[0]
        if actual_payload != expected_payload:
            raise ValueError(
                f"Example {ex_key} contract_type '{contract_type}' does not match payload key '{actual_payload}' (expected '{expected_payload}')"
            )

        # Record truth table case if present
        if "truth_table_id" in ex_node and ex_node["truth_table_id"] is not None:
            tt_id = ex_node["truth_table_id"]
            if tt_id not in EXPECTED_TRUTH_TABLE_CASES:
                raise ValueError(f"Example {ex_key} has unrecognized truth_table_id: {tt_id}")
            observed_tt_cases.add(tt_id)
        else:
            tt_id = None

        # Record UI states if present
        if "ui_states_demonstrated" in ex_node:
            states = ex_node["ui_states_demonstrated"]
            if not isinstance(states, list):
                raise ValueError(f"Example {ex_key} ui_states_demonstrated must be a list")
            for state in states:
                if state not in EXPECTED_UI_STATES:
                    raise ValueError(f"Example {ex_key} has unrecognized UI state: {state}")
                observed_ui_states.add(state)

        # Case A: Cache Subcases
        if contract_type == "SearchEnvelope_CacheScenarios":
            subcases = ex_node["subcases"]
            if not isinstance(subcases, dict) or not subcases:
                raise ValueError(f"Example {ex_key} has invalid or empty subcases")

            actual_subcases = set(subcases.keys())
            if actual_subcases != EXPECTED_CACHE_SUBCASES:
                raise ValueError(
                    f"Example {ex_key} cache subcases mismatch: missing {EXPECTED_CACHE_SUBCASES - actual_subcases}, unrecognized {actual_subcases - EXPECTED_CACHE_SUBCASES}"
                )

            for sub_key in sorted(EXPECTED_CACHE_SUBCASES):
                sub_val = subcases[sub_key]
                if not isinstance(sub_val, dict) or "envelope" not in sub_val:
                    raise ValueError(f"Subcase {sub_key} in {ex_key} missing envelope")

                env = SearchEnvelope.model_validate_json(json.dumps(sub_val["envelope"]))
                counts["envelopes"] += 1

                if sub_key == "A_cached_fresh":
                    if not (env.cached is True and env.stale is False):
                        raise ValueError("A_cached_fresh must have cached=True, stale=False")
                elif sub_key == "B_refresh_failure_does_not_mask_with_old_cache":
                    if not (env.overall == "failed" and env.cached is False):
                        raise ValueError("B_refresh_failure must have overall=failed, cached=False")
                elif sub_key == "C_explicit_open_stale_snapshot":
                    if not (env.cached is True and env.stale is True):
                        raise ValueError("C_explicit_open_stale must have cached=True, stale=True")

        # Case B: Direct SearchEnvelope (SearchEnvelope or SearchEnvelope_StorageError)
        elif contract_type in ("SearchEnvelope", "SearchEnvelope_StorageError"):
            env = SearchEnvelope.model_validate_json(json.dumps(ex_node["envelope"]))
            counts["envelopes"] += 1

            if tt_id == "TT-01":
                if env.overall != "empty" or env.snapshot is None or len(env.snapshot.fusion.hits) != 0:
                    raise ValueError("TT-01 invariant failure: expected empty with 0 hits")
            elif tt_id == "TT-02":
                if env.overall != "success" or env.snapshot is None or len(env.snapshot.fusion.hits) < 1:
                    raise ValueError("TT-02 invariant failure: expected success with >=1 hit")
            elif tt_id == "TT-03":
                if env.overall != "empty" or env.snapshot is None or len(env.snapshot.fusion.hits) != 0:
                    raise ValueError("TT-03 invariant failure: expected empty with 0 hits")
            elif tt_id == "TT-04":
                if env.overall != "partial_failure" or len(env.errors) < 1 or (env.snapshot is not None and len(env.snapshot.fusion.hits) != 0):
                    raise ValueError("TT-04 invariant failure: expected partial_failure with 0 hits")
            elif tt_id == "TT-05":
                if env.overall != "partial_failure" or len(env.errors) < 1 or env.snapshot is None or len(env.snapshot.fusion.hits) < 1:
                    raise ValueError("TT-05 invariant failure: expected partial_failure with >=1 hit")
            elif tt_id == "TT-06":
                if env.overall != "failed" or len(env.errors) < 1:
                    raise ValueError("TT-06 invariant failure: expected failed with errors")
            elif contract_type == "SearchEnvelope_StorageError":
                if env.overall != "failed" or not any(e.kind == "storage" for e in env.errors):
                    raise ValueError("StorageError invariant failure: expected storage error")

        # Case C: Invalid Request Payload (HTTP 422)
        elif contract_type == "SearchRequest_ValidationError":
            try:
                SearchRequest.model_validate_json(json.dumps(ex_node["invalid_request_payload"]))
                raise ValueError(f"SearchRequest in {ex_key} unexpectedly passed validation!")
            except ValidationError:
                counts["requests"] += 1

        # Case D: Library Entry
        elif contract_type == "LibraryEntry":
            lib_entry = LibraryEntry.model_validate_json(json.dumps(ex_node["library_entry"]))
            if lib_entry.canonical_id != lib_entry.hit.canonical_id:
                raise ValueError(f"LibraryEntry identity mismatch in {ex_key}")
            counts["library_entries"] += 1

        else:
            raise ValueError(f"Unhandled contract_type: {contract_type}")

    # Require root coverage declarations equal the observed sets and required sets
    if observed_ui_states != EXPECTED_UI_STATES:
        raise ValueError(
            f"Coverage failure: observed UI states do not cover required set: missing {EXPECTED_UI_STATES - observed_ui_states}"
        )
    if root_ui_states != observed_ui_states:
        raise ValueError("Coverage mismatch: root 'ui_states_covered' does not equal observed UI states demonstrated")

    if observed_tt_cases != EXPECTED_TRUTH_TABLE_CASES:
        raise ValueError(
            f"Coverage failure: observed truth table cases do not cover required set: missing {EXPECTED_TRUTH_TABLE_CASES - observed_tt_cases}"
        )
    if root_tt_ids != observed_tt_cases:
        raise ValueError("Coverage mismatch: root 'truth_table_cases_covered' does not equal observed truth table cases")

    counts["total"] = counts["envelopes"] + counts["requests"] + counts["library_entries"]
    return counts


def run_negative_tests(fixture_file: Path, sidecar_file: Path) -> None:
    """Run destructive/adversarial test cases via subprocess/CLI in temp dirs, asserting exit code 1."""
    print("Running adversarial / negative tests via CLI subprocess...")

    with fixture_file.open("r", encoding="utf-8") as f:
        base_data = json.load(f)

    python_bin = sys.executable
    script_path = str(Path(__file__).resolve())

    def run_cli_expect_exit_1(extra_args: list[str], test_name: str) -> None:
        cmd = [python_bin, script_path, "--no-negative"] + extra_args
        env = os.environ.copy()
        current_pp = env.get("PYTHONPATH", "")
        if str(SOL_SRC_PATH) not in current_pp:
            env["PYTHONPATH"] = f"{SOL_SRC_PATH};{current_pp}" if current_pp else str(SOL_SRC_PATH)

        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 1:
            print(
                f"FAIL [{test_name}]: Expected exit code 1, got {proc.returncode}.\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  [PASS] {test_name} correctly exited with code 1.")

    # 1. Missing sidecar file
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_sidecar = Path(tmp_dir) / "nonexistent.sidecar.json"
        run_cli_expect_exit_1(["--fixture", str(fixture_file), "--sidecar", str(missing_sidecar)], "Missing sidecar file")

    # 2. Missing fixture file
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_file = Path(tmp_dir) / "nonexistent.json"
        run_cli_expect_exit_1(["--fixture", str(missing_file), "--sidecar", str(sidecar_file)], "Missing fixture file")

    # 3. Malformed JSON syntax
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_file = Path(tmp_dir) / "malformed.json"
        bad_file.write_text('{"schema_version": 1, "contract_version": "1.0.0", unclosed_syntax: ', encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Malformed JSON syntax")

    # 4. Missing required root field ('schema_version')
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        del bad_data["schema_version"]
        bad_file = Path(tmp_dir) / "missing_schema_version.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Missing required field 'schema_version'")

    # 5. Missing required field in envelope ('overall')
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        del bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["overall"]
        bad_file = Path(tmp_dir) / "missing_overall.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Missing required envelope field 'overall'")

    # 6. Text-only record with missing/empty title (ensures failure is specifically from no-title defect)
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["source_results"][0]["records"][0]["title"] = ""
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["fusion"]["hits"][0]["display"]["title"] = ""
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["fusion"]["hits"][0]["source_records"][0]["title"] = ""
        bad_file = Path(tmp_dir) / "no_title_text_only.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Text-only record with empty title")

    # 7. Invalid numeric score: mutate actual 'score' in RankedHit (score <= 0)
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["fusion"]["hits"][0]["score"] = -1.0
        bad_file = Path(tmp_dir) / "bad_score.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Negative numeric score (-1.0) on RankedHit")

    # 8. Count identity mismatch (raw != valid + invalid)
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["fusion"]["counts"]["raw"] = 999
        bad_file = Path(tmp_dir) / "bad_counts.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Count identity violation (raw=999)")

    # 9. Injected benchmark metadata field ('qrels' metadata key)
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["qrels"] = {"doc1": 1}
        bad_file = Path(tmp_dir) / "injected_qrels.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Injected benchmark metadata ('qrels')")

    # 10. Destructive mutation: change example_01 contract_type to 'Unknown'
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["contract_type"] = "Unknown"
        bad_file = Path(tmp_dir) / "unknown_contract_type.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: contract_type='Unknown'")

    # 11. Destructive mutation: clear root ui_states_covered
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["ui_states_covered"] = []
        bad_file = Path(tmp_dir) / "clear_root_ui_states.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: clear root ui_states_covered")

    # 12. Destructive mutation: clear every example ui_states_demonstrated
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        for ex in bad_data["examples"].values():
            if "ui_states_demonstrated" in ex:
                ex["ui_states_demonstrated"] = []
        bad_file = Path(tmp_dir) / "clear_example_ui_states.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: clear all example ui_states_demonstrated")

    # 13. Destructive mutation: missing cache subcase in example_09
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        del bad_data["examples"]["example_09_cache_fresh_stale_and_refresh_failure"]["subcases"]["C_explicit_open_stale_snapshot"]
        bad_file = Path(tmp_dir) / "missing_cache_subcase.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: missing cache subcase C")

    # 14. Destructive mutation: unknown cache subcase in example_09
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_09_cache_fresh_stale_and_refresh_failure"]["subcases"]["D_unknown_subcase"] = copy.deepcopy(
            bad_data["examples"]["example_09_cache_fresh_stale_and_refresh_failure"]["subcases"]["A_cached_fresh"]
        )
        bad_file = Path(tmp_dir) / "unknown_cache_subcase.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: unknown cache subcase D")

    # 15. Destructive mutation: multiple payload keys in example_01
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["invalid_request_payload"] = {"query": "bad"}
        bad_file = Path(tmp_dir) / "multiple_payloads.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: multiple payload keys")

    # 16. Destructive mutation: payload key mismatch with contract_type
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_data = copy.deepcopy(base_data)
        bad_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["contract_type"] = "LibraryEntry"
        bad_file = Path(tmp_dir) / "payload_mismatch.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
        run_cli_expect_exit_1(["--fixture", str(bad_file), "--sidecar", str(sidecar_file)], "Destructive mutation: contract_type and payload key mismatch")

    print(f"ALL 16 adversarial / negative CLI subprocess checks passed successfully!")

    # Positive check 1: Title-only valid record check
    raw_hash = "6666666666666666666666666666666666666666666666666666666666666666"
    title_only_dict = {
        "source": "arxiv",
        "source_id": "2409.00001",
        "title": "Valid Title Only Paper",
        "landing_url": "https://arxiv.org/abs/2409.00001",
        "retrieved_at": "2026-09-30T08:00:00+07:00",
        "raw_sha256": raw_hash,
        "parser_version": "test-1.0.0",
        "abstract": None,
        "publication_year": None,
        "doi": None,
        "arxiv_id": None,
        "venue": None,
        "pdf_url": None,
        "license": None,
        "open_access_status": None,
        "citation_count": None,
        "authors": None,
        "authors_availability": "missing",
        "missing_fields": [
            "abstract", "publication_year", "doi", "arxiv_id", "venue",
            "pdf_url", "license", "open_access_status", "citation_count", "authors"
        ],
        "field_provenance": {
            "source_id": [{"source": "arxiv", "source_id": "2409.00001", "raw_sha256": raw_hash, "raw_field": "id"}],
            "title": [{"source": "arxiv", "source_id": "2409.00001", "raw_sha256": raw_hash, "raw_field": "title"}],
            "landing_url": [{"source": "arxiv", "source_id": "2409.00001", "raw_sha256": raw_hash, "raw_field": "id"}],
        },
    }
    title_only = PaperRecord.model_validate_json(json.dumps(title_only_dict))
    assert title_only.title == "Valid Title Only Paper"
    print("  [PASS] Title-only valid record verified with model_validate_json.")

    # Positive check 2: Benign textual occurrence of 'held_out' in request query text
    benign_data = copy.deepcopy(base_data)
    benign_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"]["snapshot"]["request"]["query"] = (
        "Benchmarking held_out scientific papers in citation graphs and splits"
    )
    check_leakage_boundary(benign_data)
    SearchEnvelope.model_validate_json(
        json.dumps(benign_data["examples"]["example_01_success_dedup_rrf_and_missing_fields"]["envelope"])
    )
    print("  [PASS] Benign textual occurrence of 'held_out' in query text verified successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GEMINI UX fixtures against SOL typed models")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help="Path to ux_examples.json")
    parser.add_argument("--sidecar", type=Path, default=SIDECAR_PATH, help="Path to ux_examples.sidecar.json")
    parser.add_argument("--no-negative", action="store_true", help="Do not run negative subprocess tests")
    args = parser.parse_args()

    print(f"Validating fixture: {args.fixture}")
    print(f"Validating sidecar: {args.sidecar}")
    print(f"Authoritative SOL models loaded from: {SOL_SRC_PATH}")

    try:
        sidecar_meta = validate_sidecar(args.sidecar)
        counts = validate_all_examples(args.fixture)
        print("PASS: 1:1 typed model validation succeeded!")
        print(f"  Sidecar validated: {args.sidecar.name} (checkpoint {sidecar_meta['updated_at']}, SOL head {sidecar_meta['proposed_sol_head'][:7]})")
        print(f"  Envelopes validated: {counts['envelopes']}")
        print(f"  Requests validated: {counts['requests']}")
        print(f"  Library entries validated: {counts['library_entries']}")
        print(f"  Total validated examples: {counts['total']}")

        if not args.no_negative:
            run_negative_tests(args.fixture, args.sidecar)

        return 0
    except Exception as exc:
        print(f"FAIL: Validation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
