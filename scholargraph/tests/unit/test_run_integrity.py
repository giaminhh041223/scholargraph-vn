"""Integrity tests for SG-007 experiment runner and run manifests."""

from __future__ import annotations

import json
from itertools import product
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.runner import (
    FinalTestGateError,
    RunIntegrityError,
    RunStore,
    _redact_command,
    _redact_text,
    sha256_path,
    sha256_value,
)


FIXED_TIME = datetime(2026, 9, 15, 12, 34, 56, tzinfo=timezone(timedelta(hours=7)))


def _create_run(store: RunStore, **overrides):
    arguments = {
        "method": "bm25",
        "dataset": "scifact",
        "split": "dev",
        "resolved_config": {"k1": 1.5, "b": 0.75},
        "data_source": {"snapshot": "scifact-v1", "sha256": "source-declared-value"},
        "split_definition": {"query_ids": ["q1", "q2"], "role": "internal_dev"},
        "code_source": {"commit": "abc123", "dirty": False},
        "model": {"id": "bm25", "revision": "rank-bm25-0.2.2"},
        "seed": 20260915,
        "command": ["python", "-m", "scholargraph.run", "--api-key", "do-not-store"],
        "synthetic": True,
        "at": FIXED_TIME,
    }
    arguments.update(overrides)
    return store.create(**arguments)


def _rankings():
    return [
        RankingResult.create_sorted("q2", [("doc:b", 0.4, {"raw": 0.4})]),
        RankingResult.create_sorted(
            "q1", [("doc:a", 1.25, {"raw": 1.25}), ("doc:b", 0.5, None)]
        ),
    ]


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _valid_final_inputs(tmp_path: Path, *, freeze_overrides=None, audit_overrides=None):
    resolved_config = {
        "resolved": True,
        "track": "A",
        "dataset": "scifact",
        "split": "test",
        "k1": 1.5,
        "b": 0.75,
    }
    data_source = {"snapshot": "scifact-v1"}
    split_definition = {"query_ids": ["q1", "q2"], "role": "test"}
    model = {"id": "bm25", "revision": "rank-bm25-0.2.2"}
    bindings = {
        "track": "A",
        "method": "bm25",
        "dataset": "scifact",
        "split": "test",
        "resolved_config_hash": sha256_value(resolved_config),
        "data_hash": sha256_value(data_source),
        "split_hash": sha256_value(split_definition),
        "model_hash": sha256_value(model),
        "model_id": model["id"],
        "model_revision": model["revision"],
    }
    freeze = {"status": "FROZEN", **bindings, "evaluator_revision": "metrics-v1"}
    freeze.update(freeze_overrides or {})
    audit = {
        "status": "PASS",
        "track": "A",
        "dataset": "scifact",
        "split": "test",
        "data_hash": bindings["data_hash"],
        "split_hash": bindings["split_hash"],
    }
    audit.update(audit_overrides or {})
    freeze_path = tmp_path / "freeze.json"
    audit_path = tmp_path / "leakage-audit.json"
    _write_json(freeze_path, freeze)
    _write_json(audit_path, audit)
    return {
        "resolved_config": resolved_config,
        "data_source": data_source,
        "split_definition": split_definition,
        "model": model,
        "freeze_evidence": {
            "freeze_artifact": {"path": str(freeze_path), "sha256": sha256_path(freeze_path)},
            "leakage_audit": {"path": str(audit_path), "sha256": sha256_path(audit_path)},
        },
    }


def test_smoke_run_records_provenance_rankings_and_metrics(tmp_path: Path):
    handle = _create_run(RunStore(tmp_path / "runs"))
    initial = handle.manifest()

    assert handle.run_id == "RUN-20260915-123456-bm25-scifact-dev"
    assert initial["status"] == "RUNNING"
    assert initial["seed"] == 20260915
    assert initial["command"][-1] == "<redacted>"
    assert set(initial["hashes"]) == {"protocol", "config", "data", "split", "code", "model"}
    assert all(len(value) == 64 for value in initial["hashes"].values())
    assert initial["config_hash"] == sha256_value({"b": 0.75, "k1": 1.5})
    assert initial["code_provenance"] == {
        "commit": "abc123",
        "dirty": False,
        "source_digest": initial["code_hash"],
    }
    assert initial["synthetic"] is True

    rankings_path = handle.record_rankings(_rankings())
    per_query_path = handle.record_per_query(
        {"q1": {"ndcg_at_10": 1.0}, "q2": {"ndcg_at_10": 0.5}}
    )
    completed = handle.complete({"ndcg_at_10": 0.75}, at=FIXED_TIME + timedelta(seconds=5))

    ranking_rows = [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines()]
    assert [row["query_id"] for row in ranking_rows] == ["q1", "q2"]
    assert ranking_rows[0]["candidates"][0]["score"] == 1.25  # raw score is retained
    assert json.loads(per_query_path.read_text(encoding="utf-8"))["q2"]["ndcg_at_10"] == 0.5
    assert completed["status"] == "COMPLETED"
    assert completed["completed_at"] == "2026-09-15T12:35:01+07:00"
    handle.verify_integrity()


def test_completed_run_is_immutable_and_export_never_overwrites(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    handle = _create_run(store)
    handle.record_rankings(_rankings())
    handle.record_per_query({"q1": {"mrr_at_10": 1.0}})
    handle.complete({"mrr_at_10": 1.0})
    manifest_before = handle.manifest_path.read_bytes()

    with pytest.raises(RunIntegrityError, match="immutable"):
        handle.record_per_query({"q1": {"mrr_at_10": 0.0}})
    with pytest.raises(RunIntegrityError, match="new run ID"):
        store.resume(handle.run_id)
    assert handle.manifest_path.read_bytes() == manifest_before

    exported = handle.export(tmp_path / "notebook-export")
    assert (exported / "manifest.json").read_bytes() == manifest_before
    with pytest.raises(RunIntegrityError, match="already exists"):
        handle.export(exported)


def test_terminal_manifest_tampering_is_detected(tmp_path: Path):
    handle = _create_run(RunStore(tmp_path / "runs"))
    handle.record_rankings(_rankings())
    handle.record_per_query({"q1": {"mrr_at_10": 1.0}})
    handle.complete({"mrr_at_10": 1.0})
    manifest = json.loads(handle.manifest_path.read_text(encoding="utf-8"))
    manifest["aggregate_metrics"]["mrr_at_10"] = 0.0
    handle.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RunIntegrityError, match="manifest integrity"):
        handle.manifest()


def test_failed_run_keeps_sanitized_error_and_is_terminal(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    handle = _create_run(store)
    failed = handle.fail(RuntimeError("request failed token=super-secret"))

    assert failed["status"] == "FAILED"
    assert failed["error"] == {"type": "RuntimeError", "message": "request failed token=<redacted>"}
    error_text = (handle.path / "error.json").read_text(encoding="utf-8")
    assert "super-secret" not in error_text
    with pytest.raises(RunIntegrityError, match="new run ID"):
        store.resume(handle.run_id)
    with pytest.raises(RunIntegrityError, match="immutable"):
        handle.fail("second failure")


def test_credentials_are_redacted_from_command_log_error_and_export(tmp_path: Path):
    secrets = ["COMMAND_SECRET", "HEADER_SECRET", "LOG_SECRET", "CLI_SECRET", "FAIL_SECRET"]
    handle = _create_run(
        RunStore(tmp_path / "runs"),
        command=[
            "python",
            "run.py",
            "--api-key",
            secrets[0],
            "-H",
            f"Authorization: Bearer {secrets[1]}",
        ],
    )
    handle.append_log(f"Authorization: Bearer {secrets[2]} --api-key {secrets[3]}")
    handle.fail(RuntimeError(f"request failed --token {secrets[4]}"))
    exported = handle.export(tmp_path / "export")

    stored_text = "\n".join(
        path.read_text(encoding="utf-8") for path in exported.rglob("*") if path.is_file()
    )
    assert "<redacted>" in stored_text
    for secret in secrets:
        assert secret not in stored_text


def test_reviewer_credential_forms_are_redacted_in_all_persisted_outputs(tmp_path: Path):
    cases = [
        ("Authorization=Bearer REVIEW_SECRET_EQUALS", "REVIEW_SECRET_EQUALS"),
        ("Authorization: Basic REVIEW_SECRET_BASIC", "REVIEW_SECRET_BASIC"),
        ('--password="prefix REVIEW_SECRET_QUOTED"', "REVIEW_SECRET_QUOTED"),
        ("{'api_key': 'REVIEW_SECRET_DICT'}", "REVIEW_SECRET_DICT"),
    ]
    store = RunStore(tmp_path / "runs")

    for index, (message, secret) in enumerate(cases):
        assert secret not in _redact_text(message)
        handle = _create_run(store, command=["python", "run.py", message])
        handle.append_log(message)
        handle.fail(message)
        exported = handle.export(tmp_path / f"export-{index}")
        persisted = "\n".join(
            path.read_text(encoding="utf-8")
            for path in exported.rglob("*")
            if path.is_file()
        )
        assert secret not in persisted
        assert "<redacted>" in persisted


def test_sanitizer_does_not_redact_ordinary_scientific_metadata():
    metadata = (
        "token_count=512 tokenizer=wordpiece passwordless_method=True; "
        "authorization model for bearer plants and API key effects"
    )
    assert _redact_text(metadata) == metadata


@pytest.mark.parametrize("whitespace", ["\n", "\r\n", "\n\t "])
def test_multiline_credentials_are_redacted_before_persistence(tmp_path: Path, whitespace: str):
    secret = "SYNTH_MULTILINE_SECRET_42"
    messages = [
        f'{{"api_key"{whitespace}:{whitespace}"{secret}"}}',
        f"password:{whitespace}{secret}",
        f"--token{whitespace}={whitespace}{secret}",
        f"Authorization:{whitespace}Bearer{whitespace}{secret}",
    ]
    store = RunStore(tmp_path / "runs")
    for index, message in enumerate(messages):
        sanitized = _redact_text(message)
        assert secret not in sanitized
        assert _redact_text(sanitized) == sanitized
        handle = _create_run(store, command=["run", message],
                             resolved_config={"diagnostic": message})
        handle.append_log(message)
        handle.fail(RuntimeError(message))
        exported = handle.export(tmp_path / f"export-{index}")
        for directory in (handle.path, exported):
            for path in directory.rglob("*"):
                if path.is_file():
                    assert secret not in path.read_text(encoding="utf-8"), path


def _credential_text_cases():
    """Generate syntax families independently of sanitizer implementation."""

    secret = "synthetic_Credential9-7e42"
    scalar_values = [secret, f"prefix,{secret}/=+", f'"prefix {secret} suffix"', f"'prefix {secret} suffix'",
                     f'"prefix \\"quoted\\" {secret}"']
    for key, separator, scalar in product(
        ["password", "API_KEY", "access-token", "ToKeN", "secret"],
        ["=", " = ", ":", ": "], scalar_values,
    ):
        yield f"{key}{separator}{scalar}", secret
        yield f"{{'{key}'{separator}{scalar}}}", secret
    for option, separator, scalar in product(
        ["--password", "--API-KEY", "--access_token", "-ToKeN", "--secret"],
        [" ", "\t", "=", " =", "= ", " = "], scalar_values,
    ):
        yield f"command {option}{separator}{scalar} --seed 42", secret
    for key, separator, scheme, scalar in product(
        ["Authorization", "aUtHoRiZaTiOn", "--AUTHORIZATION"],
        [": ", "=", " = ", " "], ["Basic", "bEaReR"], scalar_values,
    ):
        yield f"{key}{separator}{scheme} {scalar}", secret
        yield f"{key}{separator}'{scheme} {secret}'", secret
    for key, separator in product(
        ["Authorization", "--authorization"], [": ", " = ", " "],
    ):
        yield f'{key}{separator}Digest username="{secret}", nonce="{secret}-nonce", response="{secret}-response"', secret
    for scheme in ["Bearer", "bEaReR", "BEARER"]:
        yield f"{scheme} {secret}", secret
        yield f"HTTP failure ({scheme} {secret})", secret
        yield f"{scheme} plainlowercase", "plainlowercase"
    for quote in ["'", '"']:
        yield f"{{{quote}Authorization{quote}: {quote}Bearer {secret}{quote}}}", secret
        yield f"{{{quote}API_KEY{quote}: {quote}{secret}{quote}}}", secret
    yield f"Authorization: CustomScheme opaque={secret}, signature={secret}", secret
    yield f'--password="first line\n{secret}\nlast line"', secret
    yield f'--password="unfinished {secret}', secret


def _credential_command_cases():
    secret = "synthetic_ArgvCredential9-128"
    for option, value in product(
        ["--password", "--API-KEY", "--token", "--secret"],
        [secret, f"prefix {secret} suffix", f"'{secret}'"],
    ):
        yield ["run", option, value, "--seed", "42"], secret
        yield ["run", option, "=", value, "--seed", "42"], secret
        yield ["run", option + " = ", value, "--seed", "42"], secret
        yield ["run", option + "=" + value, "--seed", "42"], secret
    for option, scheme in product(
        ["--authorization", "--AUTHORIZATION", "Authorization:"],
        ["Basic", "bEaReR", "Digest"],
    ):
        payload = f'username="{secret}", nonce="{secret}"' if scheme == "Digest" else secret
        yield ["run", option, scheme, payload, "--seed", "42"], secret
        yield ["run", option, "=", scheme, payload, "--seed", "42"], secret
        yield ["run", option, f"{scheme} {payload}", "--seed", "42"], secret
        if option.startswith("--"):
            yield ["run", option + " = " + scheme, payload, "--seed", "42"], secret
    yield ["run", "--authorization", "Digest", f'username="{secret}",', f'nonce="{secret}"', "--seed", "42"], secret
    yield ["run", "--authorization=Digest", f'username="{secret}",', f'nonce="{secret}"', "--seed", "42"], secret
    yield ["run", f'--authorization=Digest username="{secret}",', f'nonce="{secret}"', "--seed", "42"], secret
    yield ["run", "--authorization", "CustomScheme", secret, "--seed", "42"], secret
    yield ["run", "--authorization=CustomScheme", secret, "--seed", "42"], secret
    yield ["run", "Authorization: Bearer", secret, "--seed", "42"], secret
    yield ["run", "Bearer", secret, "--seed", "42"], secret


def test_generated_credential_syntax_and_command_boundaries():
    for message, secret in _credential_text_cases():
        sanitized = _redact_text(message)
        assert secret.casefold() not in sanitized.casefold(), message
        assert _redact_text(sanitized) == sanitized, message
    for command, secret in _credential_command_cases():
        sanitized = _redact_command(command)
        assert secret.casefold() not in " ".join(sanitized).casefold(), command
        assert sanitized[-2:] == ["--seed", "42"], command
        assert _redact_command(sanitized) == sanitized, command


def test_generated_credentials_absent_from_source_and_exported_files(tmp_path: Path):
    cases = list(_credential_text_cases())
    message = "\n".join(text for text, _ in cases)
    secrets = {secret.casefold() for _, secret in cases}
    store = RunStore(tmp_path / "runs")
    # Each text is an independent argv item; raw multiline diagnostics also go
    # through both persistence paths. Scan source AND export, including seals.
    handle = _create_run(store, command=["run", *[text for text, _ in cases]])
    handle.append_log(message)
    handle.fail(RuntimeError(message))
    exported = handle.export(tmp_path / "export-text")
    for folder in [handle.path, exported]:
        for path in folder.rglob("*"):
            if path.is_file():
                content = path.read_text(encoding="utf-8").casefold()
                assert all(secret not in content for secret in secrets), path
    # Preserve true argv boundaries during persistence as well as direct checks.
    for index, (command, secret) in enumerate(_credential_command_cases()):
        argv_handle = _create_run(store, command=command)
        argv_handle.fail("synthetic failure")
        exported = argv_handle.export(tmp_path / f"export-argv-{index}")
        for folder in [argv_handle.path, exported]:
            for path in folder.rglob("*"):
                if path.is_file():
                    assert secret.casefold() not in path.read_text(encoding="utf-8").casefold()


def test_nested_manifest_credentials_redacted_without_losing_provenance(tmp_path: Path):
    secret = "synthetic_MetadataCredential91"
    config = {"token_count": 512, "tokenizer": "wordpiece", "passwordless": True,
              "client": {"API_KEY": secret, "authorization": f"Bearer {secret}"},
              "notes": [f"--password = '{secret}'", "authorization model for bearer plants"]}
    handle = _create_run(
        RunStore(tmp_path / "runs"), resolved_config=config,
        environment_lock={"python": "3.11", "diagnostic": f"Authorization: Basic {secret}"},
        code_source={"commit": "synthetic-fixture", "dirty": True, "token": secret},
        model={"id": "bm25", "revision": "synthetic-v1", "token": secret},
    )
    initial = handle.manifest()
    assert initial["config_hash"] == sha256_value(config)  # original input identity
    assert initial["resolved_config"]["token_count"] == 512
    assert initial["resolved_config"]["tokenizer"] == "wordpiece"
    assert initial["resolved_config"]["passwordless"] is True
    assert initial["resolved_config"]["notes"][1] == config["notes"][1]
    handle.record_rankings(_rankings())
    handle.record_per_query({"q1": {"ndcg_at_10": 1.0}})
    handle.complete({"ndcg_at_10": 1.0})
    handle.verify_integrity()
    exported = handle.export(tmp_path / "export")
    for folder in [handle.path, exported]:
        for path in folder.rglob("*"):
            if path.is_file():
                assert secret.casefold() not in path.read_text(encoding="utf-8").casefold()
    assert handle.manifest()["code_provenance"]["commit"] == "synthetic-fixture"


def test_collision_allocates_suffix_and_resume_checks_provenance(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    first = _create_run(store)
    second = _create_run(store)

    assert second.run_id == first.run_id + "-2"
    resumed = store.resume(
        first.run_id,
        expected_hashes={"config": first.manifest()["hashes"]["config"]},
    )
    assert resumed.run_id == first.run_id
    with pytest.raises(RunIntegrityError, match="hash mismatch"):
        store.resume(first.run_id, expected_hashes={"data": "0" * 64})
    with pytest.raises(ValueError, match="Invalid run_id"):
        store.resume("../../outside")


def test_integrity_check_detects_out_of_band_artifact_change(tmp_path: Path):
    handle = _create_run(RunStore(tmp_path / "runs"))
    ranking_path = handle.record_rankings(_rankings())
    ranking_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(RunIntegrityError, match="rankings.jsonl"):
        handle.verify_integrity()


def test_complete_refuses_tampered_or_missing_artifacts_without_sealing(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    tampered = _create_run(store)
    ranking_path = tampered.record_rankings(_rankings())
    tampered.record_per_query({"q1": {"ndcg_at_10": 1.0}})
    with ranking_path.open("a", encoding="utf-8") as stream:
        stream.write("CORRUPTED\n")

    with pytest.raises(RunIntegrityError, match="rankings.jsonl"):
        tampered.complete({"ndcg_at_10": 1.0})
    assert tampered.manifest()["status"] == "RUNNING"
    assert not (tampered.path / "seal.json").exists()

    missing = _create_run(store)
    missing.record_rankings(_rankings())
    per_query = missing.record_per_query({"q1": {"ndcg_at_10": 1.0}})
    per_query.unlink()
    with pytest.raises(RunIntegrityError, match="per_query.json"):
        missing.complete({"ndcg_at_10": 1.0})
    assert missing.manifest()["status"] == "RUNNING"


def test_final_test_requires_resolved_freeze_evidence(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    valid = _valid_final_inputs(tmp_path)

    with pytest.raises(FinalTestGateError, match="must provide path"):
        _create_run(
            store,
            split="test",
            synthetic=False,
            final_test=True,
            **{**valid, "freeze_evidence": {"freeze_artifact": True, "leakage_audit": True}},
        )
    assert not list((tmp_path / "runs").iterdir())

    handle = _create_run(
        store,
        split="test",
        synthetic=False,
        final_test=True,
        **valid,
    )
    assert handle.manifest()["final_test"] is True
    assert handle.manifest()["freeze_evidence"]["freeze_artifact"]["path"].endswith(".json")


def test_final_gate_rejects_missing_hash_mismatch_wrong_binding_and_failed_audit(tmp_path: Path):
    cases = []
    # Each case gets separate artifacts so mutations cannot mask another failure.
    for name, freeze_overrides, audit_overrides in (
        ("wrong-track", {"track": "B"}, None),
        ("wrong-dataset", {"dataset": "scidocs"}, None),
        ("wrong-split", {"split": "dev"}, None),
        ("failed-audit", None, {"status": "FAIL"}),
    ):
        case_dir = tmp_path / name
        case_dir.mkdir()
        cases.append(
            _valid_final_inputs(
                case_dir,
                freeze_overrides=freeze_overrides,
                audit_overrides=audit_overrides,
            )
        )

    for index, inputs in enumerate(cases):
        with pytest.raises(FinalTestGateError, match="not bound"):
            _create_run(
                RunStore(tmp_path / f"runs-{index}"),
                split="test",
                synthetic=False,
                **inputs,
            )

    absent_dir = tmp_path / "absent"
    absent_dir.mkdir()
    absent = _valid_final_inputs(absent_dir)
    Path(absent["freeze_evidence"]["freeze_artifact"]["path"]).unlink()
    with pytest.raises(FinalTestGateError, match="does not exist"):
        _create_run(RunStore(tmp_path / "runs-absent"), split="test", synthetic=False, **absent)

    mismatch_dir = tmp_path / "mismatch"
    mismatch_dir.mkdir()
    mismatch = _valid_final_inputs(mismatch_dir)
    mismatch["freeze_evidence"]["freeze_artifact"]["sha256"] = "0" * 64
    with pytest.raises(FinalTestGateError, match="hash mismatch"):
        _create_run(RunStore(tmp_path / "runs-mismatch"), split="test", synthetic=False, **mismatch)


def test_final_gate_rejects_unresolved_config(tmp_path: Path):
    valid = _valid_final_inputs(tmp_path)
    valid["resolved_config"] = {
        **valid["resolved_config"],
        "resolved": False,
        "unresolved_gates": ["model"],
    }
    with pytest.raises(FinalTestGateError, match="resolved=True"):
        _create_run(RunStore(tmp_path / "runs"), split="test", synthetic=False, **valid)


def test_real_test_split_cannot_bypass_gate_by_omitting_flag(tmp_path: Path):
    with pytest.raises(FinalTestGateError, match="resolved=True"):
        _create_run(
            RunStore(tmp_path / "runs"),
            split="test",
            synthetic=False,
            final_test=False,
        )


def test_code_commit_and_dirty_provenance_survive_export(tmp_path: Path):
    code = {
        "commit": "review-fixture",
        "dirty": True,
        "source_snapshot": "artifacts/source/review-fixture.tar",
    }
    handle = _create_run(RunStore(tmp_path / "runs"), code_source=code)
    handle.record_rankings(_rankings())
    handle.record_per_query({"q1": {"ndcg_at_10": 1.0}})
    handle.complete({"ndcg_at_10": 1.0})
    exported = handle.export(tmp_path / "export")
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["code_provenance"]["commit"] == "review-fixture"
    assert manifest["code_provenance"]["dirty"] is True
    assert manifest["code_provenance"]["source_snapshot"].endswith(".tar")
    assert manifest["code_provenance"]["source_digest"] == manifest["code_hash"]


def test_hashes_are_deterministic_and_include_directory_paths(tmp_path: Path):
    left = {"b": [2, 1], "a": 3}
    right = {"a": 3, "b": [2, 1]}
    assert sha256_value(left) == sha256_value(right)

    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_text("same", encoding="utf-8")
    before = sha256_path(tree)
    (tree / "a.txt").rename(tree / "b.txt")
    assert sha256_path(tree) != before


def test_duplicate_output_is_rejected_without_changing_first_artifact(tmp_path: Path):
    handle = _create_run(RunStore(tmp_path / "runs"))
    path = handle.record_rankings(_rankings())
    original = path.read_bytes()

    with pytest.raises(RunIntegrityError, match="will not be overwritten"):
        handle.record_rankings(_rankings())
    assert path.read_bytes() == original
