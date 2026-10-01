#!/usr/bin/env python
"""Verify EXT-06 evidence without mutating frozen project inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _failure(kind: str, message: str, **extra: Any) -> dict:
    result = {"status": "INSUFFICIENT_EVIDENCE", "kind": kind, "message": message}
    result.update(extra)
    return result


def _safe_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("manifest path must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"manifest path is outside root: {value!r}")
    resolved = (root / path).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"manifest path is outside root: {value!r}")
    return resolved


def _hash_file(root: Path, relative: str, expected: Any, hashes: dict[str, str]) -> None:
    target = _safe_path(root, relative)
    if not target.is_file():
        raise ValueError(f"required evidence is missing: {relative}")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"invalid sha256 for {relative}")
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"evidence hash mismatch: {relative}")
    hashes[relative] = actual


def _validate_freeze(core_root: Path, value: Any, hashes: dict[str, str]) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("manifest"), str):
        raise ValueError("core_freeze.manifest is required")
    manifest_rel = value["manifest"]
    _hash_file(core_root, manifest_rel, value.get("sha256"), hashes)
    try:
        freeze = json.loads(_safe_path(core_root, manifest_rel).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"core freeze manifest is invalid: {exc}") from None
    if not isinstance(freeze, dict):
        raise ValueError("core freeze manifest must be an object")
    for section in ("data", "splits", "graph", "models", "configs"):
        if section not in freeze:
            raise ValueError(f"required core freeze section missing: {section}")
        entries = freeze[section]
        if not isinstance(entries, dict) or not entries:
            raise ValueError(f"core freeze section {section} is invalid")
        for relative, digest in entries.items():
            if section == "data" and isinstance(digest, dict):
                if not digest:
                    raise ValueError("core freeze data group is empty")
                for data_path, data_sha in digest.items():
                    _hash_file(core_root, data_path, data_sha, hashes)
            else:
                _hash_file(core_root, relative, digest, hashes)


def _validate_splits(core_root: Path, value: Any, hashes: dict[str, str]) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("required_splits must be a non-empty list")
    seen_ids: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("required_splits entry is invalid")
        relative = entry.get("path")
        _hash_file(core_root, relative, entry.get("sha256"), hashes)
        try:
            payload = json.loads(_safe_path(core_root, relative).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"split manifest is invalid: {relative}: {exc}") from None
        if not isinstance(payload, dict) or "query_ids" not in payload:
            raise ValueError(f"split manifest has no query IDs: {relative}")
        ids = payload["query_ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i.strip() for i in ids):
            raise ValueError(f"split query IDs invalid: {relative}")
        if len(set(ids)) != len(ids) or seen_ids.intersection(ids):
            raise ValueError(f"duplicate or overlapping split query IDs: {relative}")
        if type(payload.get("query_count")) is not int or payload["query_count"] != len(ids):
            raise ValueError(f"split query_count mismatch: {relative}")
        seen_ids.update(ids)


def _validate_acceptance(root: Path, value: Any, hashes: dict[str, str]) -> None:
    if not isinstance(value, dict):
        raise ValueError("acceptance evidence is required")
    for name in ("adversarial", "regression", "pilot"):
        if name not in value:
            raise ValueError(f"acceptance evidence missing: {name}")
        row = value[name]
        if not isinstance(row, dict):
            raise ValueError(f"acceptance {name} needs hashed evidence")
        status = row.get("status")
        if status not in {"PASS", "FAIL", "NOT_RUN"}:
            raise ValueError(f"acceptance {name} has invalid status")
        if status == "NOT_RUN" or (status == "FAIL" and name != "pilot"):
            raise ValueError(f"acceptance {name} is {status}; required evidence is not complete")
        if name == "pilot" and (row.get("evidence_status") != "PASS" or not row.get("reason")):
            raise ValueError("pilot requires explicit evidence_status PASS and operational reason")
        paths = row.get("evidence_paths")
        if not isinstance(paths, list) or not paths or any(p not in hashes for p in paths):
            raise ValueError(f"acceptance {name} needs hashed evidence_paths")
        report_path = row.get("report_path")
        if report_path not in paths:
            raise ValueError(f"acceptance {name} needs a hashed report_path")
        report = json.loads(_safe_path(root, report_path).read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError(f"acceptance {name} report must be an object")
        if name != "pilot":
            if (report.get("status") != "PASS" or type(report.get("passed")) is not int
                or report["passed"] <= 0 or type(report.get("failed")) is not int
                or report["failed"] != 0 or type(report.get("exit_code")) is not int
                or report["exit_code"] != 0 or not isinstance(report.get("command"), str)
                or not report["command"].strip()):
                raise ValueError(f"acceptance {name} report has no valid test run")
        else:
            _validate_pilot(root, report, status, hashes)


def _validate_pilot(root: Path, report: dict, status: str, hashes: dict[str, str]) -> None:
    from scholargraph.public_search.contracts import SearchEnvelope, unique_object
    if report.get("evidence_status") != "PASS" or report.get("two_source_operational") != status:
        raise ValueError("pilot report status mismatch")
    if not isinstance(report.get("code_commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", report["code_commit"]):
        raise ValueError("pilot code_commit missing or invalid")
    if report.get("config_path") not in hashes:
        raise ValueError("pilot config must be a required hashed input")
    _hash_file(root, report["config_path"], report.get("config_sha256"), hashes)
    queries = report.get("approved_queries")
    if (not isinstance(queries, list) or len(queries) < 5
        or any(not isinstance(q, str) or not q.strip() for q in queries) or len(set(queries)) != len(queries)):
        raise ValueError("pilot approved queries invalid")
    runs = report.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("pilot runs missing")
    counts = dict.fromkeys(("canonical_runs", "cli_exit0", "cli_exit1", "partial_failure", "success",
                           "two_source_success", "arxiv_timeout", "arxiv_quota"), 0)
    modes = {"refresh": set(), "cache": set()}
    timings: dict[str, list[float]] = {"refresh": [], "cache": []}
    two_source = []
    for run in runs:
        if not isinstance(run, dict) or run.get("query") not in queries:
            raise ValueError("pilot run query mismatch")
        if run.get("stdout_path") not in hashes:
            raise ValueError("pilot stdout must be a required hashed input")
        _hash_file(root, run["stdout_path"], run.get("stdout_sha256"), hashes)
        if run.get("encoding") not in {"utf-8", "cp1252"}:
            raise ValueError("pilot encoding missing or unsupported")
        raw_json = _safe_path(root, run["stdout_path"]).read_bytes().decode(run["encoding"])
        try:
            json.loads(raw_json, object_pairs_hook=unique_object)
            envelope = SearchEnvelope.model_validate_json(raw_json)
        except ValueError:
            raise ValueError("pilot envelope schema invalid") from None
        snapshot = envelope.snapshot
        expected_exit = 1 if envelope.errors else 0
        if (snapshot is None or snapshot.request.query != run["query"] or envelope.overall != run.get("overall")
            or type(run.get("exit_code")) is not int or run["exit_code"] != expected_exit):
            raise ValueError("pilot run status/CLI/request mismatch")
        counts["canonical_runs"] += 1
        counts[f"cli_exit{expected_exit}"] += 1
        if envelope.overall in {"success", "partial_failure"}: counts[envelope.overall] += 1
        for error in envelope.errors:
            if error.source == "arxiv" and error.kind in {"timeout", "quota"}:
                counts[f"arxiv_{error.kind}"] += 1
        if set(snapshot.request.sources) == {"openalex", "arxiv"}:
            two_source.append(envelope.overall in {"success", "empty"})
            counts["two_source_success"] += envelope.overall == "success"
        elif snapshot.request.sources == ["openalex"] or tuple(snapshot.request.sources) == ("openalex",):
            mode = run.get("mode")
            seconds = run.get("elapsed_seconds")
            if (mode not in modes or run["query"] in modes[mode] or envelope.errors
                or envelope.cached != (mode == "cache") or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0):
                raise ValueError("OpenAlex pilot mode/cache/timing mismatch")
            modes[mode].add(run["query"])
            timings[mode].append(seconds)
        else:
            raise ValueError("pilot source set unsupported")
    if not two_source or ("PASS" if all(two_source) else "FAIL") != status:
        raise ValueError("pilot operational status contradicts two-source runs")
    reported_counts = report.get("counts")
    if (not isinstance(reported_counts, dict) or any(type(v) is not int for v in reported_counts.values())
        or counts != reported_counts or any(v != set(queries) for v in modes.values())):
        raise ValueError("pilot counts or query coverage mismatch")
    latency = report.get("latency")
    if not isinstance(latency, dict):
        raise ValueError("pilot latency evidence missing")
    for mode, values in timings.items():
        measurement = latency.get(f"openalex_{mode}")
        if (not isinstance(measurement, dict) or type(measurement.get("n")) is not int
            or measurement["n"] != len(values)
            or isinstance(measurement.get("median_seconds"), bool) or isinstance(measurement.get("p95_seconds"), bool)
            or not isinstance(measurement.get("method"), str) or not measurement["method"]
            or measurement.get("median_seconds") != statistics.median(values)
            or measurement.get("p95_seconds") != sorted(values)[math.ceil(.95 * len(values)) - 1]):
            raise ValueError("pilot P95/n/method mismatch")


def validate_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    required = manifest.get("required_files")
    expected = manifest.get("sha256")
    if not isinstance(required, list) or not required or not isinstance(expected, dict):
        raise ValueError("manifest required_files/sha256 is invalid")
    hashes: dict[str, str] = {}
    for relative in required:
        if relative not in expected:
            raise ValueError(f"missing sha256 for required evidence: {relative}")
        _hash_file(root, relative, expected[relative], hashes)
    core_root = _safe_path(root, manifest.get("core_root", "."))
    _validate_freeze(core_root, manifest.get("core_freeze"), hashes)
    _validate_splits(core_root, manifest.get("required_splits"), hashes)
    _validate_acceptance(root, manifest.get("acceptance"), hashes)
    return hashes


def _guard_outputs(root: Path, manifest_path: Path, manifest: dict, outputs: list[Path]) -> None:
    protected = {manifest_path}
    for relative in manifest.get("required_files", []):
        protected.add(_safe_path(root, relative))
    acceptance = manifest.get("acceptance")
    if isinstance(acceptance, dict):
        for name, row in acceptance.items():
            if not isinstance(row, dict):
                continue
            for relative in row.get("evidence_paths", []):
                protected.add(_safe_path(root, relative))
            if isinstance(row.get("report_path"), str):
                report_path = _safe_path(root, row["report_path"])
                protected.add(report_path)
                if name == "pilot" and report_path.is_file():
                    expected_hashes = manifest.get("sha256")
                    if isinstance(expected_hashes, dict) and row["report_path"] in expected_hashes:
                        _hash_file(root, row["report_path"], expected_hashes[row["report_path"]], {})
                    pilot = json.loads(report_path.read_text(encoding="utf-8"))
                    if isinstance(pilot, dict):
                        if isinstance(pilot.get("config_path"), str):
                            protected.add(_safe_path(root, pilot["config_path"]))
                        runs = pilot.get("runs")
                        if isinstance(runs, list):
                            for run in runs:
                                if isinstance(run, dict) and isinstance(run.get("stdout_path"), str):
                                    protected.add(_safe_path(root, run["stdout_path"]))
    core = _safe_path(root, manifest.get("core_root", "."))
    freeze_info = manifest.get("core_freeze")
    if isinstance(freeze_info, dict) and isinstance(freeze_info.get("manifest"), str):
        freeze_path = _safe_path(core, freeze_info["manifest"])
        protected.add(freeze_path)
        if freeze_path.is_file():
            freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
            if isinstance(freeze, dict):
                for section in ("data", "splits", "graph", "models", "configs"):
                    entries = freeze.get(section)
                    if isinstance(entries, dict):
                        for relative, digest in entries.items():
                            if section == "data" and isinstance(digest, dict):
                                protected.update(_safe_path(core, p) for p in digest)
                            else:
                                protected.add(_safe_path(core, relative))
    for split in manifest.get("required_splits", []):
        if isinstance(split, dict) and isinstance(split.get("path"), str):
            protected.add(_safe_path(core, split["path"]))
    if len(set(outputs)) != len(outputs):
        raise ValueError("output paths must be distinct")
    for path in outputs:
        if root not in path.parents or path in protected:
            raise ValueError("output path is outside project or overlaps protected input")
        if path.is_dir():
            raise ValueError("output path is a directory")


def _write_report(json_path: Path, md_path: Path, report: dict) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Public search validation — {report['status']}", "", f"- Checked at: {report['checked_at']}"]
    for key, value in report.items():
        if key != "checked_at":
            lines.append(f"- {key}: `{json.dumps(value, ensure_ascii=False)}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify public-search adversarial evidence")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1
    checked_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {"status": "INSUFFICIENT_EVIDENCE", "evidence_status": "NOT_RUN", "checked_at": checked_at,
        "pilot_status": "NOT_RUN", "pilot_reason": "Live pilot is not inferred from synthetic tests."}
    root = Path(args.project_root).resolve()
    outputs = [Path(args.output_json).resolve(), Path(args.output_md).resolve()]
    outputs_safe = False
    try:
        if not root.is_dir():
            raise ValueError("project root is missing")
        manifest_path = Path(args.manifest).resolve()
        if manifest_path != root and root not in manifest_path.parents:
            raise ValueError("manifest must be inside project root")
        if not manifest_path.is_file():
            raise ValueError("manifest is missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        _guard_outputs(root, manifest_path, manifest, outputs)
        outputs_safe = True
        hashes = validate_manifest(root, manifest)
        pilot = manifest["acceptance"]["pilot"]
        report["pilot_status"] = pilot.get("status") if isinstance(pilot, dict) else pilot
        if isinstance(pilot, dict) and pilot.get("reason"):
            report["pilot_reason"] = pilot["reason"]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        command = [sys.executable, "-m", "pytest", "tests/integration/test_public_adversarial.py", "-q", "-p", "no:cacheprovider"]
        result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=args.timeout, env=env)
        match = re.search(r"(\d+) passed", result.stdout)
        if result.returncode != 0 or match is None:
            report = _failure("adversarial_tests", "required adversarial test run failed or had no count",
                              checked_at=checked_at, command_exit_code=result.returncode,
                              stdout_tail=result.stdout[-2000:], stderr_tail=result.stderr[-2000:])
        else:
            report.update({"status": "PASS" if report["pilot_status"] == "PASS" else "FAIL",
                           "evidence_status": "PASS", "adversarial_tests_passed": int(match.group(1)), "command_exit_code": result.returncode,
                           "manifest_hashes": hashes})
    except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = _failure("required_resource", str(exc), checked_at=checked_at)
    if outputs_safe:
        try:
            _write_report(outputs[0], outputs[1], report)
        except OSError as exc:
            report = _failure("output", str(exc), checked_at=checked_at)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
