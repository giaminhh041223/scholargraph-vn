"""Unit tests for the dense encoder model config selected at SG-017.

Covers:
1. ``configs/models/dense_encoder.json`` loads with a strict JSON parser
   (duplicate keys and NaN/Infinity constants are rejected, never silenced).
2. Required fields exist at top level, in ``selection``, in every candidate,
   and every source has a URL plus an access date (no fabricated provenance).
3. Consistency with ``configs/protocol_v1.json`` block ``retrieval.dense``:
   similarity=cosine, l2_normalize=true, missing_embedding=fail_not_drop_document,
   selection_gate=SG-017, and the shortlist budget (max 3 dense configs).
4. Revision integrity: every model revision is either a 40-hex commit sha
   verified against a source URL, or the literal "unknown" with a status that
   documents it. No silent fallback to branch names such as "main".
5. Cross-artifact consistency: the MiniLM revision must match the revision
   actually resolved by the SG-002 compute pilot (artifacts/reports/compute_pilot.json).
6. Overlap disclosure (AGENTS.md §6): every surveyed candidate has an
   overlap_risk entry and appears in the per-candidate risk map.
7. Adversarial / negative tests (ADR-013): corrupted config fixtures in a temp
   directory must be rejected by the validator with explicit error messages, and
   a subprocess consuming a broken fixture must exit with code 1 (never 0).
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "models" / "dense_encoder.json"
PROTOCOL_PATH = PROJECT_ROOT / "configs" / "protocol_v1.json"
COMPUTE_PILOT_PATH = PROJECT_ROOT / "artifacts" / "reports" / "compute_pilot.json"
TESTS_UNIT_DIR = Path(__file__).resolve().parent

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
REQUIRED_MINILM_ID = "sentence-transformers/all-MiniLM-L6-v2"

REQUIRED_TOP_LEVEL = (
    "schema_version",
    "config_id",
    "task_id",
    "created_at",
    "status",
    "track",
    "protocol_reference",
    "selection",
    "dense_shortlist",
    "candidates",
    "overlap_disclosure",
    "track_vn_note",
    "unknowns",
    "sources",
)

REQUIRED_SELECTION = (
    "config_id",
    "model_id",
    "revision",
    "revision_status",
    "revision_source_url",
    "revision_accessed_at",
    "pooling",
    "normalize",
    "max_length",
    "adapter",
    "prefix",
    "prefix_scope",
    "embedding_dimension",
    "license",
    "training_data_summary",
    "sources",
)

REQUIRED_CANDIDATE = (
    "candidate_id",
    "model_id",
    "revision",
    "revision_status",
    "pooling",
    "normalize",
    "max_length",
    "architecture",
    "parameters",
    "embedding_dimension",
    "adapter",
    "license",
    "training_data_summary",
    "usage_in_project",
    "overlap_risk",
    "overlap_evidence",
    "sources",
)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# Strict loading helpers (no silent bypass: duplicate keys / NaN must raise)
# ---------------------------------------------------------------------------


def _reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def _reject_constant(name):
    raise ValueError(f"non-finite JSON constant: {name}")


def load_json_strict(path):
    """Load JSON rejecting duplicate keys and NaN/Infinity constants."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)


# ---------------------------------------------------------------------------
# Validator (used by the positive tests on the real config and by the
# adversarial tests on corrupted fixtures). Direct membership checks only:
# a missing required field must become an explicit error, never a default.
# ---------------------------------------------------------------------------


def _check_revision(revision, revision_status, errors, where):
    if not isinstance(revision, str) or not revision.strip():
        errors.append(f"{where}.revision must be a non-empty string")
        return
    if SHA_RE.match(revision):
        if not isinstance(revision_status, str) or not revision_status.strip():
            errors.append(f"{where}.revision_status must document verification for sha revision")
        return
    if revision.strip().lower() == "unknown":
        if not isinstance(revision_status, str) or "unknown" not in revision_status.lower():
            errors.append(
                f"{where}: revision is 'unknown' but revision_status does not state it explicitly"
            )
        return
    errors.append(
        f"{where}.revision {revision!r} is neither a 40-hex commit sha nor the literal "
        "'unknown' with an explicit revision_status; refusing to guess (no silent bypass)"
    )


def _check_sources(sources, errors, where):
    if not isinstance(sources, list) or not sources:
        errors.append(f"{where}.sources must be a non-empty list")
        return
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"{where}.sources[{index}] must be an object")
            continue
        for key in ("url", "accessed_at", "content"):
            if key not in source:
                errors.append(f"{where}.sources[{index}] is missing required key {key!r}")
            elif not isinstance(source[key], str) or not source[key].strip():
                errors.append(f"{where}.sources[{index}].{key} must be a non-empty string")


def _check_dimension(dimension, errors, where):
    if isinstance(dimension, bool):
        errors.append(f"{where}.embedding_dimension must not be a boolean")
        return
    if isinstance(dimension, int) and dimension > 0:
        return
    if isinstance(dimension, str) and dimension.strip() and ("not_stated" in dimension or "unknown" in dimension):
        return
    errors.append(
        f"{where}.embedding_dimension must be a positive int or an explicit "
        f"'not_stated'/'unknown' marker, got {dimension!r}"
    )


def validate_dense_encoder_config(cfg):
    """Return the list of validation error strings; empty list means valid."""
    errors = []
    if not isinstance(cfg, dict):
        return ["config must be a JSON object"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in cfg:
            errors.append(f"missing required top-level field: {key}")
    if errors:
        return errors

    if cfg["schema_version"] != 1:
        errors.append("schema_version must be 1")

    # Protocol-facing invariants carried by the config itself.
    protocol_ref = cfg["protocol_reference"]
    if not isinstance(protocol_ref, dict):
        errors.append("protocol_reference must be an object")
    else:
        if "similarity" not in protocol_ref or protocol_ref["similarity"] != "cosine":
            errors.append("protocol_reference.similarity must be 'cosine' per protocol dense block")
        if "l2_normalize" not in protocol_ref or protocol_ref["l2_normalize"] is not True:
            errors.append("protocol_reference.l2_normalize must be exactly true per protocol dense block")
        if "missing_embedding" not in protocol_ref or protocol_ref["missing_embedding"] != "fail_not_drop_document":
            errors.append("protocol_reference.missing_embedding must be 'fail_not_drop_document'")
        if "selection_gate" not in protocol_ref or protocol_ref["selection_gate"] != "SG-017":
            errors.append("protocol_reference.selection_gate must be 'SG-017'")

    # Selection block.
    selection = cfg["selection"]
    if not isinstance(selection, dict):
        errors.append("selection must be an object")
        selection = {}
    for key in REQUIRED_SELECTION:
        if key not in selection:
            errors.append(f"selection is missing required field: {key}")
    if "model_id" in selection and (not isinstance(selection["model_id"], str) or not selection["model_id"].strip()):
        errors.append("selection.model_id must be a non-empty string")
    if "revision" in selection and "revision_status" in selection:
        _check_revision(selection["revision"], selection["revision_status"], errors, "selection")
    if "pooling" in selection and selection["pooling"] not in ("mean", "cls"):
        errors.append("selection.pooling must be 'mean' or 'cls' (verified pooling of the selected model)")
    if "normalize" not in selection or selection["normalize"] is not True:
        errors.append("selection.normalize must be exactly true (protocol l2_normalize)")
    if "max_length" in selection:
        max_length = selection["max_length"]
        if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length <= 0:
            errors.append("selection.max_length must be a positive int")
    if "embedding_dimension" in selection:
        _check_dimension(selection["embedding_dimension"], errors, "selection")
    if "license" in selection and (not isinstance(selection["license"], str) or not selection["license"].strip()):
        errors.append("selection.license must be a non-empty string")
    if isinstance(selection.get("model_id"), str) and selection["model_id"].startswith("BAAI/bge"):
        if "prefix" not in selection or selection["prefix"] != BGE_QUERY_PREFIX:
            errors.append(
                "selection.prefix must be the documented BGE v1.5 query instruction "
                f"{BGE_QUERY_PREFIX!r} for BAAI/bge models"
            )
        if "prefix_scope" not in selection or selection["prefix_scope"] != "query_only":
            errors.append("selection.prefix_scope must be 'query_only' for BAAI/bge models (card FAQ)")
    _check_sources(selection.get("sources"), errors, "selection")

    # Candidates.
    candidates = cfg["candidates"]
    if not isinstance(candidates, list) or len(candidates) < 2:
        errors.append("candidates must be a list with at least 2 surveyed encoders")
        candidates = []
    model_ids = []
    candidate_ids = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidates[{index}] must be an object")
            continue
        where = f"candidates[{index}]"
        for key in REQUIRED_CANDIDATE:
            if key not in candidate:
                errors.append(f"{where} is missing required field: {key}")
        if "candidate_id" in candidate:
            candidate_ids.append(candidate["candidate_id"])
        if "model_id" in candidate:
            model_ids.append(candidate["model_id"])
        if "revision" in candidate and "revision_status" in candidate:
            _check_revision(candidate["revision"], candidate["revision_status"], errors, where)
        if "normalize" in candidate and candidate["normalize"] is not True:
            errors.append(f"{where}.normalize must be exactly true (protocol l2_normalize)")
        if "pooling" in candidate:
            pooling = candidate["pooling"]
            if pooling not in ("mean", "cls") and not (
                isinstance(pooling, str) and "unknown" in pooling.lower()
            ):
                errors.append(f"{where}.pooling must be 'mean', 'cls', or an explicit unknown marker")
        if "max_length" in candidate:
            candidate_max_length = candidate["max_length"]
            if isinstance(candidate_max_length, bool) or not isinstance(candidate_max_length, int) or candidate_max_length <= 0:
                errors.append(f"{where}.max_length must be a positive int")
        if "embedding_dimension" in candidate:
            _check_dimension(candidate["embedding_dimension"], errors, where)
        if "overlap_risk" in candidate and (
            not isinstance(candidate["overlap_risk"], str) or not candidate["overlap_risk"].strip()
        ):
            errors.append(f"{where}.overlap_risk must be a non-empty disclosure string")
        if "overlap_evidence" in candidate and (
            not isinstance(candidate["overlap_evidence"], str) or not candidate["overlap_evidence"].strip()
        ):
            errors.append(f"{where}.overlap_evidence must cite the inspected model card evidence")
        _check_sources(candidate.get("sources"), errors, where)
    if len(set(candidate_ids)) != len(candidate_ids):
        errors.append("candidate_id values must be unique")
    if len(set(model_ids)) != len(model_ids):
        errors.append("candidate model_id values must be unique")

    # The selected model must be one of the surveyed candidates.
    if model_ids and isinstance(selection.get("model_id"), str) and selection["model_id"] not in model_ids:
        errors.append("selection.model_id must appear among surveyed candidates.model_id values")

    # Shortlist budget from protocol tuning.dense_shortlist_max_configs.
    shortlist = cfg["dense_shortlist"]
    if not isinstance(shortlist, list):
        errors.append("dense_shortlist must be a list")
    elif len(shortlist) > 3:
        errors.append("dense_shortlist exceeds the protocol budget of 3 model/task-adapter configs")
    else:
        shortlist_ids = []
        for index, entry in enumerate(shortlist):
            if not isinstance(entry, dict):
                errors.append(f"dense_shortlist[{index}] must be an object")
                continue
            for key in ("config_id", "model_id", "role"):
                if key not in entry or not isinstance(entry[key], str) or not entry[key].strip():
                    errors.append(f"dense_shortlist[{index}] is missing required key {key!r}")
            if isinstance(entry, dict) and "config_id" in entry:
                shortlist_ids.append(entry["config_id"])
        if len(set(shortlist_ids)) != len(shortlist_ids):
            errors.append("dense_shortlist config_id values must be unique")

    # Overlap disclosure must cover every surveyed candidate.
    disclosure = cfg["overlap_disclosure"]
    if not isinstance(disclosure, dict):
        errors.append("overlap_disclosure must be an object")
    else:
        if "statement" not in disclosure or not isinstance(disclosure["statement"], str) or not disclosure["statement"].strip():
            errors.append("overlap_disclosure.statement must be a non-empty disclosure text")
        per_candidate = disclosure.get("per_candidate_risk")
        if not isinstance(per_candidate, dict) or not per_candidate:
            errors.append("overlap_disclosure.per_candidate_risk must be a non-empty object")
        else:
            for model_id in model_ids:
                if model_id not in per_candidate:
                    errors.append(
                        f"overlap_disclosure.per_candidate_risk is missing coverage for surveyed model {model_id!r}"
                    )
        mitigation = disclosure.get("mitigation_and_reporting")
        if not isinstance(mitigation, list) or not mitigation:
            errors.append("overlap_disclosure.mitigation_and_reporting must be a non-empty list")

    # Global source registry.
    _check_sources(cfg["sources"], errors, "config")
    if not isinstance(cfg["unknowns"], list):
        errors.append("unknowns must be a list (explicitly documented gaps, possibly empty)")

    return errors


# ---------------------------------------------------------------------------
# Positive tests on the real config
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_config():
    assert CONFIG_PATH.exists(), f"required config file is missing: {CONFIG_PATH}"
    return load_json_strict(CONFIG_PATH)


def test_config_file_exists_and_loads_strict():
    assert CONFIG_PATH.exists(), f"required config file is missing: {CONFIG_PATH}"
    cfg = load_json_strict(CONFIG_PATH)
    assert isinstance(cfg, dict)


def test_config_passes_validation(real_config):
    errors = validate_dense_encoder_config(real_config)
    assert errors == [], "dense_encoder.json must satisfy every validation rule: " + "; ".join(errors)


def test_required_top_level_fields_present(real_config):
    for key in REQUIRED_TOP_LEVEL:
        assert key in real_config, f"missing required top-level field: {key}"


def test_selection_fields_present(real_config):
    selection = real_config["selection"]
    for key in REQUIRED_SELECTION:
        assert key in selection, f"selection is missing required field: {key}"


def test_config_matches_protocol_dense_block(real_config):
    protocol = load_json_strict(PROTOCOL_PATH)
    dense = protocol["retrieval"]["dense"]
    assert dense["similarity"] == "cosine"
    assert dense["l2_normalize"] is True
    assert dense["missing_embedding"] == "fail_not_drop_document"
    assert dense["selection_gate"] == "SG-017"
    assert protocol["tuning"]["dense_shortlist_max_configs"] == 3

    reference = real_config["protocol_reference"]
    assert reference["similarity"] == dense["similarity"]
    assert reference["l2_normalize"] is dense["l2_normalize"]
    assert reference["missing_embedding"] == dense["missing_embedding"]
    assert reference["selection_gate"] == dense["selection_gate"]


def test_selection_revision_is_sha_or_explicit_unknown(real_config):
    revision = real_config["selection"]["revision"]
    assert isinstance(revision, str) and revision.strip(), "selection.revision must be non-empty"
    assert SHA_RE.match(revision) or revision.strip().lower() == "unknown", (
        f"selection.revision {revision!r} is neither a 40-hex sha nor an explicit 'unknown'"
    )


def test_minilm_candidate_required_and_revision_matches_compute_pilot(real_config):
    candidates = {c["model_id"]: c for c in real_config["candidates"]}
    assert REQUIRED_MINILM_ID in candidates, (
        "the survey must include sentence-transformers/all-MiniLM-L6-v2 (SG-002 pilot model)"
    )
    pilot = load_json_strict(COMPUTE_PILOT_PATH)
    assert pilot["model"]["id"] == REQUIRED_MINILM_ID
    resolved = pilot["model"]["resolved_revision"]
    assert isinstance(resolved, str) and SHA_RE.match(resolved), (
        "compute pilot must carry a resolved 40-hex revision, not a branch name"
    )
    assert candidates[REQUIRED_MINILM_ID]["revision"] == resolved, (
        "MiniLM revision in dense_encoder.json must match the revision actually resolved by SG-002"
    )


def test_selected_model_is_surveyed_and_revision_verified(real_config):
    selection = real_config["selection"]
    surveyed = {c["model_id"] for c in real_config["candidates"]}
    assert selection["model_id"] in surveyed
    assert SHA_RE.match(selection["revision"])
    assert selection["revision_status"]
    assert selection["revision_source_url"].startswith("https://")
    assert selection["revision_accessed_at"]


def test_bge_selection_uses_documented_query_prefix_on_queries_only(real_config):
    selection = real_config["selection"]
    assert selection["model_id"].startswith("BAAI/bge")
    assert selection["prefix"] == BGE_QUERY_PREFIX
    assert selection["prefix_scope"] == "query_only"


def test_every_candidate_has_overlap_disclosure_and_sources(real_config):
    for candidate in real_config["candidates"]:
        assert candidate["overlap_risk"].strip(), f"{candidate['model_id']} must disclose overlap risk"
        assert candidate["overlap_evidence"].strip(), f"{candidate['model_id']} must cite overlap evidence"
        assert candidate["sources"], f"{candidate['model_id']} must list its inspected sources"
        for source in candidate["sources"]:
            assert source["url"].strip()
            assert source["accessed_at"].strip()


def test_overlap_disclosure_covers_all_surveyed_candidates(real_config):
    per_candidate = real_config["overlap_disclosure"]["per_candidate_risk"]
    for candidate in real_config["candidates"]:
        assert candidate["model_id"] in per_candidate, (
            f"overlap disclosure must cover surveyed model {candidate['model_id']}"
        )


def test_shortlist_within_protocol_budget(real_config):
    shortlist = real_config["dense_shortlist"]
    assert 1 <= len(shortlist) <= 3
    selected_ids = {entry["config_id"] for entry in shortlist}
    assert real_config["selection"]["config_id"] in selected_ids


def test_global_sources_have_url_and_access_date(real_config):
    assert real_config["sources"], "config must carry a global source registry"
    for source in real_config["sources"]:
        assert source["url"].strip()
        assert source["accessed_at"].strip()
        assert source["content"].strip()


def test_unknowns_explicitly_documented(real_config):
    assert isinstance(real_config["unknowns"], list)
    assert real_config["unknowns"], (
        "the survey must record what could not be verified (BGE training data list, etc.)"
    )


# ---------------------------------------------------------------------------
# Adversarial / negative tests on corrupted fixtures in a temp dir (ADR-013)
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_config_copy(real_config):
    return copy.deepcopy(real_config)


def _write_fixture(tmp_path: Path, cfg) -> Path:
    path = tmp_path / "dense_encoder_fixture.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_required_field_fails(real_config_copy):
    del real_config_copy["selection"]["license"]
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("license" in e for e in errors), errors


def test_missing_whole_selection_block_fails(tmp_path, real_config_copy):
    del real_config_copy["selection"]
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("selection" in e for e in errors), errors


def test_empty_revision_fails(real_config_copy):
    real_config_copy["selection"]["revision"] = ""
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("revision" in e for e in errors), errors


def test_branch_name_revision_fails(real_config_copy):
    """A branch name like 'main' must not pass as a revision."""
    real_config_copy["selection"]["revision"] = "main"
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("revision" in e and "40-hex" in e for e in errors), errors


def test_revision_unknown_without_status_fails(real_config_copy):
    real_config_copy["selection"]["revision"] = "unknown"
    real_config_copy["selection"]["revision_status"] = "verified_sha_of_main_at_access_time"
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("unknown" in e for e in errors), errors


def test_revision_unknown_with_status_passes(real_config_copy):
    real_config_copy["selection"]["revision"] = "unknown"
    real_config_copy["selection"]["revision_status"] = "unknown_sha_not_verifiable_at_access_time"
    errors = validate_dense_encoder_config(real_config_copy)
    assert errors == [], errors


def test_normalize_false_fails(real_config_copy):
    real_config_copy["selection"]["normalize"] = False
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("normalize" in e for e in errors), errors


def test_similarity_not_cosine_fails(real_config_copy):
    real_config_copy["protocol_reference"]["similarity"] = "dot"
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("cosine" in e for e in errors), errors


def test_missing_embedding_policy_change_fails(real_config_copy):
    real_config_copy["protocol_reference"]["missing_embedding"] = "drop_document"
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("fail_not_drop_document" in e for e in errors), errors


def test_selected_model_not_in_candidates_fails(real_config_copy):
    real_config_copy["selection"]["model_id"] = "not/surveyed-model"
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("among surveyed candidates" in e for e in errors), errors


def test_overlap_coverage_gap_fails(real_config_copy):
    surveyed = real_config_copy["candidates"][0]["model_id"]
    del real_config_copy["overlap_disclosure"]["per_candidate_risk"][surveyed]
    errors = validate_dense_encoder_config(real_config_copy)
    assert any(surveyed in e for e in errors), errors


def test_shortlist_over_budget_fails(real_config_copy):
    extra = dict(real_config_copy["dense_shortlist"][0])
    extra["config_id"] = "dense-a-extra-config"
    real_config_copy["dense_shortlist"] = real_config_copy["dense_shortlist"] + [extra]
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("budget of 3" in e for e in errors), errors


def test_candidate_missing_overlap_evidence_fails(real_config_copy):
    real_config_copy["candidates"][0]["overlap_evidence"] = ""
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("overlap_evidence" in e for e in errors), errors


def test_source_without_access_date_fails(real_config_copy):
    real_config_copy["sources"][0]["accessed_at"] = ""
    errors = validate_dense_encoder_config(real_config_copy)
    assert any("accessed_at" in e for e in errors), errors


def test_malformed_json_rejected(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"schema_version": 1, "selection": ', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_json_strict(path)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_json_strict(path)


def test_nan_constant_rejected(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text('{"schema_version": 1, "selection": {"max_length": NaN}}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        load_json_strict(path)


def test_missing_config_file_is_reported(tmp_path):
    """A missing required resource must fail loudly, never fall back silently."""
    missing = tmp_path / "dense_encoder.json"
    assert not missing.exists()
    with pytest.raises(OSError):
        load_json_strict(missing)


def test_subprocess_exits_1_on_broken_fixture(tmp_path, real_config_copy):
    """ADR-013: a consumer of the config must exit nonzero on invalid data."""
    real_config_copy["selection"]["normalize"] = False
    broken = _write_fixture(tmp_path, real_config_copy)

    script = (
        "import sys\n"
        f"sys.path.insert(0, r'{TESTS_UNIT_DIR}')\n"
        "from test_model_config import validate_dense_encoder_config, load_json_strict\n"
        f"cfg = load_json_strict(r'{broken}')\n"
        "errors = validate_dense_encoder_config(cfg)\n"
        "if errors:\n"
        "    print('CONFIG_INVALID: ' + '; '.join(errors), file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "print('CONFIG_OK')\n"
        "sys.exit(0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, (
        f"expected exit code 1 for invalid config, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert "CONFIG_INVALID" in result.stderr
    assert "normalize" in result.stderr


def test_subprocess_exits_0_on_valid_config(tmp_path, real_config_copy):
    valid = _write_fixture(tmp_path, real_config_copy)
    script = (
        "import sys\n"
        f"sys.path.insert(0, r'{TESTS_UNIT_DIR}')\n"
        "from test_model_config import validate_dense_encoder_config, load_json_strict\n"
        f"cfg = load_json_strict(r'{valid}')\n"
        "errors = validate_dense_encoder_config(cfg)\n"
        "if errors:\n"
        "    print('CONFIG_INVALID: ' + '; '.join(errors), file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "print('CONFIG_OK')\n"
        "sys.exit(0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"expected exit code 0 for the valid config fixture, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert "CONFIG_OK" in result.stdout
