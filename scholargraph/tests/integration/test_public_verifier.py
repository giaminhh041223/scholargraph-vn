"""Verifier contract tests; every synthetic input/output lives in tmp_path."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_public_search.py"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def synthetic_manifest(root: Path) -> tuple[Path, dict]:
    """Small complete contract fixture, never an academic acceptance dataset."""
    freeze = {"schema_version": 1, "synthetic": True,
              "data": {"synthetic": {}}, "splits": {}, "graph": {}, "models": {}, "configs": {}}
    paths = {"data": "core/corpus.jsonl", "graph": "core/graph.tsv",
             "models": "core/model.json", "configs": "core/config.json"}
    for section, relative in paths.items():
        _write(root / relative, {"synthetic": True, "section": section})
        target = freeze[section]["synthetic"] if section == "data" else freeze[section]
        target[relative] = _digest(root / relative)
    splits = []
    for name in ("dev", "test"):
        relative = f"core/{name}.json"
        _write(root / relative, {"synthetic": True, "query_ids": [f"synthetic:{name}:q1"], "query_count": 1})
        sha = _digest(root / relative)
        splits.append({"path": relative, "sha256": sha})
        freeze["splits"][relative] = sha
    _write(root / "core/freeze.json", freeze)
    required = []
    acceptance = {}
    for name in ("adversarial", "regression", "pilot"):
        relative = f"evidence/{name}.json"
        _write(root / relative, {"synthetic": True, "status": "PASS", "passed": 1,
                                 "failed": 0, "exit_code": 0, "command": "synthetic validator fixture"})
        required.append(relative)
        acceptance[name] = {"status": "PASS", "evidence_paths": [relative], "report_path": relative,
                            "reason": "synthetic validator fixture"}
        if name == "pilot":
            acceptance[name]["evidence_status"] = "PASS"
    manifest = {"synthetic": True, "required_files": required,
                "sha256": {relative: _digest(root / relative) for relative in required},
                "core_freeze": {"manifest": "core/freeze.json", "sha256": _digest(root / "core/freeze.json")},
                "required_splits": splits, "acceptance": acceptance}
    _update_pilot(root, manifest, "PASS")
    path = root / "manifest.json"
    _write(path, manifest)
    return path, manifest


def _update_pilot(root: Path, manifest: dict, status: str) -> None:
    """Create strict envelopes with real service logic and synthetic adapters."""
    from tests.unit.test_public_service import (MemoryStore, make_service, source_result_success,
                                                 source_result_failed)
    service = make_service(root, store=MemoryStore(), calls=[])
    queries = [f"synthetic validator query {i}" for i in range(5)]
    runs = []
    counts = dict.fromkeys(("canonical_runs", "cli_exit0", "cli_exit1", "partial_failure", "success",
                           "two_source_success", "arxiv_timeout", "arxiv_quota"), 0)
    def save(envelope, mode=None, seconds=None):
        relative = f"evidence/stdout-{len(runs)}.json"
        (root / relative).write_text(envelope.model_dump_json(), encoding="utf-8")
        sha = _digest(root / relative)
        if relative not in manifest["required_files"]:
            manifest["required_files"].append(relative)
        manifest["sha256"][relative] = sha
        runs.append({"query": envelope.snapshot.request.query, "overall": envelope.overall,
                     "exit_code": 1 if envelope.errors else 0, "stdout_path": relative,
                     "stdout_sha256": sha, "encoding": "utf-8", "mode": mode, "elapsed_seconds": seconds})
        counts["canonical_runs"] += 1
        counts["cli_exit1" if envelope.errors else "cli_exit0"] += 1
        if envelope.overall in {"success", "partial_failure"}:
            counts[envelope.overall] += 1
        for error in envelope.errors:
            if error.source == "arxiv" and error.kind in {"timeout", "quota"}:
                counts[f"arxiv_{error.kind}"] += 1
        if set(envelope.snapshot.request.sources) == {"openalex", "arxiv"}:
            counts["two_source_success"] += envelope.overall == "success"
    request = {"query": queries[0], "sources": ["openalex", "arxiv"], "top_k": 2,
               "cap_per_source": 2, "year_from": None, "year_to": None, "refresh": True}
    if status == "FAIL":
        service._adapters["arxiv"] = lambda req, transport: source_result_failed("arxiv")
    save(service.search(request))
    service._adapters["arxiv"] = lambda req, transport: source_result_success("arxiv")
    for query in queries:
        request.update(query=query, sources=["openalex"], refresh=True)
        envelope = service.search(request)
        save(envelope, "refresh", 0.2)
        request["refresh"] = False
        save(service.search(request), "cache", 0.1)
    config = root / "config.json"
    if "config.json" not in manifest["required_files"]:
        manifest["required_files"].append("config.json")
    manifest["sha256"]["config.json"] = _digest(config)
    report = {"synthetic": True, "evidence_status": "PASS", "two_source_operational": status,
              "code_commit": "a" * 40, "config_path": "config.json", "config_sha256": _digest(config),
              "approved_queries": queries, "runs": runs, "counts": counts,
              "latency": {f"openalex_{mode}": {"n": 5, "method": "nearest-rank P95 ceil(0.95*n)",
                          "p95_seconds": seconds, "median_seconds": statistics.median([seconds] * 5)}
                          for mode, seconds in (("refresh", 0.2), ("cache", 0.1))}}
    _write(root / "evidence/pilot.json", report)
    manifest["sha256"]["evidence/pilot.json"] = _digest(root / "evidence/pilot.json")
    manifest["acceptance"]["pilot"]["status"] = status


def _update_freeze(root: Path, manifest: dict, freeze) -> None:
    _write(root / "core/freeze.json", freeze)
    manifest["core_freeze"]["sha256"] = _digest(root / "core/freeze.json")


def _update_split(root: Path, manifest: dict, index: int, payload) -> None:
    relative = manifest["required_splits"][index]["path"]
    _write(root / relative, payload)
    sha = _digest(root / relative)
    manifest["required_splits"][index]["sha256"] = sha
    freeze = json.loads((root / "core/freeze.json").read_text(encoding="utf-8"))
    freeze["splits"][relative] = sha
    _update_freeze(root, manifest, freeze)


def _run(root: Path, manifest: Path, *, output_json: Path | None = None,
         output_md: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(PYTHON), str(SCRIPT), "--project-root", str(root), "--manifest", str(manifest),
        "--output-json", str(output_json if output_json is not None else root / "out.json"),
        "--output-md", str(output_md if output_md is not None else root / "out.md")],
        text=True, capture_output=True, timeout=30, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})


def _assert_rejected(root: Path, path: Path, manifest: dict, expected_reason: str | None = None) -> dict:
    _write(path, manifest)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = _run(root, path)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "Traceback" not in result.stderr
    # Unsafe preflight inputs must fail before output writes; stdout is the CLI report.
    report = json.loads(result.stdout)
    if (root / "out.json").exists():
        assert json.loads((root / "out.json").read_text(encoding="utf-8")) == report
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    if expected_reason:
        assert expected_reason in report["message"], report
    assert all(p.read_bytes() == value for p, value in before.items())
    return report


def _verifier():
    spec = importlib.util.spec_from_file_location("public_verifier_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_synthetic_manifest_is_valid_without_running_pilot(tmp_path: Path) -> None:
    _, manifest = synthetic_manifest(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    hashes = _verifier().validate_manifest(tmp_path, manifest)
    assert set(manifest["required_files"]).issubset(hashes)
    assert {"core/freeze.json", "core/dev.json", "core/test.json", "core/model.json"}.issubset(hashes)
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize("key", ["required_files", "sha256", "core_freeze", "required_splits", "acceptance"])
def test_missing_manifest_keys_fail_closed(tmp_path: Path, key: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    del manifest[key]
    _assert_rejected(tmp_path, path, manifest)


@pytest.mark.parametrize("freeze", [{}, None])
def test_empty_or_null_freeze_rejected(tmp_path: Path, freeze) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    _update_freeze(tmp_path, manifest, freeze)
    _assert_rejected(tmp_path, path, manifest, "freeze")


@pytest.mark.parametrize("section", ["data", "splits", "graph", "models", "configs"])
@pytest.mark.parametrize("bad", [None, {}])
def test_required_freeze_sections_cannot_be_null_or_empty(tmp_path: Path, section: str, bad) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    freeze = json.loads((tmp_path / "core/freeze.json").read_text(encoding="utf-8"))
    freeze[section] = bad
    _update_freeze(tmp_path, manifest, freeze)
    _assert_rejected(tmp_path, path, manifest, section)


def test_missing_models_section_rejected(tmp_path: Path) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    freeze = json.loads((tmp_path / "core/freeze.json").read_text(encoding="utf-8"))
    del freeze["models"]
    _update_freeze(tmp_path, manifest, freeze)
    _assert_rejected(tmp_path, path, manifest, "models")


def test_empty_nested_data_group_rejected(tmp_path: Path) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    freeze = json.loads((tmp_path / "core/freeze.json").read_text(encoding="utf-8"))
    freeze["data"] = {"synthetic": {}}
    _update_freeze(tmp_path, manifest, freeze)
    _assert_rejected(tmp_path, path, manifest, "data")


@pytest.mark.parametrize("ids", [None, [], ["duplicate", "duplicate"], [""], [3], "query"])
def test_invalid_split_query_ids_rejected(tmp_path: Path, ids) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    _update_split(tmp_path, manifest, 0, {"query_ids": ids, "query_count": len(ids) if isinstance(ids, list) else 1})
    _assert_rejected(tmp_path, path, manifest, "query IDs")


@pytest.mark.parametrize("count", [None, True, 0, 2, "1"])
def test_invalid_split_count_rejected(tmp_path: Path, count) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    _update_split(tmp_path, manifest, 0, {"query_ids": ["synthetic:dev:q1"], "query_count": count})
    _assert_rejected(tmp_path, path, manifest, "query_count")


def test_dev_test_split_overlap_rejected(tmp_path: Path) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    _update_split(tmp_path, manifest, 1, {"query_ids": ["synthetic:dev:q1"], "query_count": 1})
    _assert_rejected(tmp_path, path, manifest, "overlapping")


@pytest.mark.parametrize("resource", ["core/corpus.jsonl", "core/model.json", "core/dev.json", "evidence/pilot.json"])
def test_missing_required_resource_rejected(tmp_path: Path, resource: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    (tmp_path / resource).unlink()
    _assert_rejected(tmp_path, path, manifest, resource)


@pytest.mark.parametrize("row", ["PASS", {},
    {"status": "PASS", "evidence_status": "PASS", "reason": "synthetic"},
    {"status": "PASS", "evidence_status": "PASS", "reason": "synthetic", "evidence_paths": []},
    {"status": "PASS", "evidence_status": "PASS", "reason": "synthetic", "evidence_paths": ["unhashed.json"]}])
def test_acceptance_requires_hashed_evidence_object(tmp_path: Path, row) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    manifest["acceptance"]["pilot"] = row
    _assert_rejected(tmp_path, path, manifest, "pilot")


def test_pilot_not_run_cannot_be_overall_pass(tmp_path: Path) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    manifest["acceptance"]["pilot"].update(status="NOT_RUN", reason="not executed")
    _assert_rejected(tmp_path, path, manifest, "pilot")


def test_complete_failed_pilot_evidence_remains_operational_failure(tmp_path: Path) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    _update_pilot(tmp_path, manifest, "FAIL")
    manifest["acceptance"]["pilot"].update(status="FAIL", evidence_status="PASS", reason="upstream source failed")
    _write(path, manifest)
    # Complete failure evidence can be inspected.  CLI still cannot report PASS.
    _verifier().validate_manifest(tmp_path, manifest)
    result = _run(tmp_path, path)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    report = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert report["status"] != "PASS"


@pytest.mark.parametrize("protected", ["manifest.json", "core/freeze.json", "core/dev.json", "evidence/pilot.json"])
@pytest.mark.parametrize("output_kind", ["json", "md"])
def test_outputs_cannot_overwrite_protected_inputs(tmp_path: Path, protected: str, output_kind: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    kwargs = {"output_json" if output_kind == "json" else "output_md": tmp_path / protected}
    result = _run(tmp_path, path, **kwargs)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    assert all(p.read_bytes() == value for p, value in before.items())


def test_json_and_markdown_outputs_cannot_be_same_path(tmp_path: Path) -> None:
    path, _ = synthetic_manifest(tmp_path)
    output = tmp_path / "report.same"
    output.write_bytes(b"do not overwrite ambiguous output")
    result = _run(tmp_path, path, output_json=output, output_md=output)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    assert output.read_bytes() == b"do not overwrite ambiguous output"


@pytest.mark.parametrize("resource", ["core/corpus.jsonl", "core/model.json", "core/dev.json", "evidence/pilot.json"])
def test_changed_required_file_hash_rejected(tmp_path: Path, resource: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    (tmp_path / resource).write_bytes(b"corrupted synthetic evidence")
    _assert_rejected(tmp_path, path, manifest, "hash mismatch")


@pytest.mark.parametrize("value", ["../outside.json", "core/../corpus.jsonl"])
def test_manifest_path_traversal_rejected(tmp_path: Path, value: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    manifest["required_files"][0] = value
    manifest["sha256"][value] = "a" * 64
    _write(path, manifest)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = _run(tmp_path, path)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "INSUFFICIENT_EVIDENCE" and "outside root" in report["message"]
    assert not (tmp_path / "out.json").exists()  # path preflight prevents output writes
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize("key", ["reason", "evidence_status"])
def test_pilot_failure_needs_explicit_evidence_and_reason(tmp_path: Path, key: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    manifest["acceptance"]["pilot"]["status"] = "FAIL"
    del manifest["acceptance"]["pilot"][key]
    _assert_rejected(tmp_path, path, manifest, "pilot")


@pytest.mark.parametrize("report", [{}, {"status": "PASS", "passed": 0, "failed": 0, "exit_code": 0, "command": "fixture"},
    {"status": "PASS", "passed": True, "failed": 0, "exit_code": 0, "command": "fixture"},
    {"status": "PASS", "passed": 1, "failed": 1, "exit_code": 0, "command": "fixture"}])
def test_acceptance_report_cannot_fake_test_run(tmp_path: Path, report: dict) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    relative = "evidence/adversarial.json"
    _write(tmp_path / relative, report)
    manifest["sha256"][relative] = _digest(tmp_path / relative)
    _assert_rejected(tmp_path, path, manifest, "no valid test run")


@pytest.mark.parametrize("mutation,reason", [("counts", "counts"), ("p95", "P95"), ("median", "P95"),
    ("n", "P95"), ("exit_code", "status/CLI/request"), ("cache_flag", "mode/cache/timing")])
def test_pilot_summary_rederived_from_strict_envelopes(tmp_path: Path, mutation: str, reason: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    relative = "evidence/pilot.json"
    report = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
    if mutation == "counts":
        report["counts"]["success"] += 1
    elif mutation in {"p95", "median", "n"}:
        key = {"p95": "p95_seconds", "median": "median_seconds", "n": "n"}[mutation]
        report["latency"]["openalex_cache"][key] += 1
    elif mutation == "exit_code":
        report["runs"][0]["exit_code"] = 1
    elif mutation == "cache_flag":
        run = report["runs"][2]
        assert run["mode"] == "cache"
        stdout = tmp_path / run["stdout_path"]
        envelope = json.loads(stdout.read_text(encoding="utf-8"))
        envelope["cached"] = False
        _write(stdout, envelope)
        run["stdout_sha256"] = _digest(stdout)
        manifest["sha256"][run["stdout_path"]] = _digest(stdout)
    _write(tmp_path / relative, report)
    manifest["sha256"][relative] = _digest(tmp_path / relative)
    _assert_rejected(tmp_path, path, manifest, reason)


@pytest.mark.parametrize("resource", ["config.json", "evidence/stdout-0.json"])
def test_omitted_dynamic_pilot_input_stays_protected_from_output(tmp_path: Path, resource: str) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    manifest["required_files"].remove(resource)
    del manifest["sha256"][resource]
    _write(path, manifest)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = _run(tmp_path, path, output_json=tmp_path / resource)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert "overlaps protected input" in report["message"]
    assert not (tmp_path / "out.md").exists()  # unsafe output stops all report writes
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize("resource,reason", [("config.json", "pilot config must be a required hashed input"),
    ("evidence/stdout-0.json", "pilot stdout must be a required hashed input")])
def test_omitted_dynamic_pilot_input_rejected_without_output_collision(
    tmp_path: Path, resource: str, reason: str,
) -> None:
    path, manifest = synthetic_manifest(tmp_path)
    manifest["required_files"].remove(resource)
    del manifest["sha256"][resource]
    _assert_rejected(tmp_path, path, manifest, reason)
