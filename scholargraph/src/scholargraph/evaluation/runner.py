"""Immutable experiment-run storage and provenance helpers.

The runner deliberately keeps evaluation labels out of its API.  It records the
inputs and outputs of an already configured experiment, and provides a small
state machine for safe interruption/resume and notebook export.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.data.schemas import RankingResult, RunManifest


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_-]+")
TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED"})
REDACTED = "<redacted>"
SECRET_KEY_PATTERN = r"(?:api[-_]?key|access[-_]?token|token|password|secret|authorization)"
SECRET_KEY_RE = re.compile(SECRET_KEY_PATTERN, re.IGNORECASE)
SECRET_START_RE = re.compile(
    rf"(?<![\w-])(?P<option>--?)?(?P<quote>[\"']?)"
    rf"(?P<key>{SECRET_KEY_PATTERN})(?P=quote)(?![\w-])",
    re.IGNORECASE,
)
SECRET_OPTION_RE = re.compile(
    rf"(?P<option>--?{SECRET_KEY_PATTERN})(?P<suffix>\s*(?:=.*)?)$",
    re.IGNORECASE | re.DOTALL,
)
AUTH_SCHEME_RE = re.compile(r"(?:basic|bearer|digest)(?=\s|$)", re.IGNORECASE)
BEARER_RE = re.compile(r"(?<![\w-])bearer[ \t]+", re.IGNORECASE)


class RunIntegrityError(RuntimeError):
    """Raised when a run transition would lose or mutate recorded evidence."""


class FinalTestGateError(RunIntegrityError):
    """Raised when a final-test run has not supplied all frozen prerequisites."""


def _canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON, rejecting NaN/Infinity."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    """Hash a JSON-compatible value, bytes object, file, or directory tree."""

    if isinstance(value, Path):
        return sha256_path(value)
    if isinstance(value, bytes):
        payload = value
    else:
        payload = _canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path | str) -> str:
    """Hash file contents or a directory including sorted relative paths."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    digest = hashlib.sha256()
    if source.is_file():
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    if not source.is_dir():
        raise ValueError(f"Unsupported hash source: {source}")

    files = sorted(item for item in source.rglob("*") if item.is_file())
    for item in files:
        relative = item.relative_to(source).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with item.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def _safe_component(value: str) -> str:
    component = SAFE_COMPONENT_RE.sub("-", value.strip()).strip("-")
    if not component:
        raise ValueError("Run ID components must contain a letter or number.")
    return component


def _redact_command(command: Sequence[str]) -> list[str]:
    """Respect argv boundaries, including separate ``=`` and auth-scheme tokens."""

    result: list[str] = []
    arguments = [str(item) for item in command]
    index = 0
    while index < len(arguments):
        item = arguments[index]
        match = SECRET_OPTION_RE.fullmatch(item.strip())
        if not match:
            # Header/scheme may itself be split across argv entries.
            header = re.fullmatch(
                r"(?i)(?:authorization\s*[:=]?\s*(?P<scheme>basic|bearer|digest)?|bearer)",
                item.strip(),
            )
            if header:
                result.append(_redact_text(item))
                index += 1
                if index < len(arguments) and arguments[index].strip() in {"=", ":"}:
                    result.append(arguments[index])
                    index += 1
                scheme = header.group("scheme")
                if item.strip().casefold() == "bearer":
                    scheme = "bearer"
                index = _redact_command_value(
                    arguments, index, result, authorization=True,
                    scheme=scheme.casefold() if scheme else None,
                )
            else:
                result.append(_redact_text(item))
                index += 1
            continue
        option, suffix = match.group("option", "suffix")
        authorization = option.lstrip("-").casefold() == "authorization"
        inline = suffix.partition("=")[2].strip() if "=" in suffix else ""
        result.append(f"{option}={REDACTED}" if "=" in suffix else option)
        index += 1
        if inline:
            if authorization and AUTH_SCHEME_RE.fullmatch(inline):
                index = _redact_command_value(
                    arguments, index, result, authorization=True, scheme=inline.casefold()
                )
            elif authorization and inline.split()[0].casefold() not in {"basic", "bearer"}:
                while index < len(arguments) and not arguments[index].lstrip().startswith("-"):
                    result.append(REDACTED)
                    index += 1
            continue
        if index < len(arguments) and arguments[index].strip() == "=":
            result.append("=")
            index += 1
        index = _redact_command_value(arguments, index, result, authorization=authorization)
    return result


def _redact_command_value(
    arguments: list[str], index: int, result: list[str], *, authorization: bool,
    scheme: str | None = None,
) -> int:
    if index == len(arguments):
        return index
    value = arguments[index].strip()
    result.append(REDACTED)
    index += 1
    if authorization and AUTH_SCHEME_RE.fullmatch(value) and index < len(arguments):
        # ``--authorization Bearer TOKEN`` contains two argv values, unlike
        # ``--authorization 'Bearer TOKEN'``. Never retain just the second one.
        result.append(REDACTED)
        index += 1
        scheme = value.casefold()
    # A complete known scheme/value in one argv element is already consumed.
    # Digest/unknown authorization may span multiple parameter elements.
    if authorization and scheme is None:
        scheme = value.split()[0].casefold() if value.split() else None
    if authorization and scheme not in {"basic", "bearer"}:
        while index < len(arguments) and not arguments[index].lstrip().startswith("-"):
            result.append(REDACTED)
            index += 1
    return index


def _scalar_end(text: str, start: int) -> int:
    """Consume a quoted value (including escapes) or one unquoted scalar."""

    if text.startswith(REDACTED, start):
        return start + len(REDACTED)
    if start >= len(text):
        return start
    quote = text[start] if text[start] in "\"'" else None
    index = start + 1 if quote else start
    while index < len(text):
        char = text[index]
        if char in "\r\n" and not quote:
            return index
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                return index + 1
        elif char.isspace() or char in "\"'":
            return index
        index += 1
    return len(text)


def _authorization_end(text: str, start: int) -> int:
    if start >= len(text) or text[start] in "\"'" or text.startswith(REDACTED, start):
        return _scalar_end(text, start)
    scheme = AUTH_SCHEME_RE.match(text, start)
    if scheme and scheme.group().casefold() in {"basic", "bearer"}:
        credential = scheme.end()
        while credential < len(text) and text[credential].isspace():
            credential += 1
        return _scalar_end(text, credential)
    # Digest has comma-separated key/value attributes. Unknown schemes may do
    # likewise: fail closed for the whole header, not just the scheme name.
    index = start
    while index < len(text) and text[index] not in "\r\n;}]":
        if text[index] in "\"'":
            index = _scalar_end(text, index)
        elif text[index].isspace() and re.match(r"\s+--?[A-Za-z]", text[index:]):
            break
        else:
            index += 1
    return index


def _redact_text(value: str) -> str:
    """Sanitize credential syntax without treating key substrings as secrets.

    Explicit keys/options consume any value, regardless of its shape. Bare
    Bearer in prose is ambiguous; recognize it at a field boundary or with an
    opaque token, retaining ordinary phrases such as ``for bearer plants``.
    """

    spans: list[tuple[int, int]] = []
    consumed = 0
    for match in SECRET_START_RE.finditer(value):
        if match.start() < consumed:
            continue
        start = match.end()
        while start < len(value) and value[start].isspace():
            start += 1
        separated = start > match.end()
        delimiter = start < len(value) and value[start] in ":="
        authorization = match.group("key").casefold() == "authorization"
        if delimiter:
            start += 1
            # JSON permits line breaks on either side of the delimiter.
            # An explicit credential key still applies to that next value.
            while start < len(value) and value[start].isspace():
                start += 1
        elif not (separated and (match.group("option") or (
            authorization and AUTH_SCHEME_RE.match(
                value, start + (1 if start < len(value) and value[start] in "\"'" else 0)
            )
        ))):
            continue
        end = _authorization_end(value, start) if authorization else _scalar_end(value, start)
        if end > start:
            spans.append((start, end))
            consumed = end
    for match in BEARER_RE.finditer(value):
        if any(start <= match.start() < end for start, end in spans):
            continue
        start, end = match.end(), _scalar_end(value, match.end())
        token = value[start:end]
        prefix = value[:match.start()].rstrip(" \t")
        field_start = not prefix or prefix[-1] in ":=,;([{\n\r"
        opaque_token = bool(re.search(r"[^a-z]", token)) or len(token) >= 20
        if token and (field_start or opaque_token):
            spans.append((start, end))
    for start, end in sorted(spans, reverse=True):
        value = value[:start] + REDACTED + value[end:]
    return value


def _redact_metadata(value: Any) -> Any:
    """Sanitize nested manifest metadata before serialization, keeping hashes."""

    if isinstance(value, Mapping):
        return {
            _redact_text(str(key)): (
                REDACTED if SECRET_KEY_RE.fullmatch(str(key).strip())
                else _redact_metadata(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_metadata(child) for child in value]
    return _redact_text(value) if isinstance(value, str) else value


def collect_hardware_info() -> dict[str, Any]:
    """Collect inexpensive, non-secret host facts useful for reproduction."""

    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }


def _aware_time(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Run timestamps must include a timezone.")
    return result


def _load_json_source(source: Mapping[str, Any] | Path | str | None) -> Mapping[str, Any]:
    if source is None:
        return {}
    if isinstance(source, Mapping):
        return source
    with Path(source).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError("Protocol source must contain a JSON object.")
    return value


def _verified_json_artifact(record: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(record, Mapping):
        raise FinalTestGateError(f"{label} must provide path and sha256.")
    raw_path = record.get("path")
    expected_hash = record.get("sha256")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise FinalTestGateError(f"{label} path is missing.")
    if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash.lower()):
        raise FinalTestGateError(f"{label} sha256 is missing or invalid.")
    path = Path(raw_path)
    if not path.is_file():
        raise FinalTestGateError(f"{label} file does not exist: {path}")
    actual_hash = sha256_path(path)
    if actual_hash != expected_hash.lower():
        raise FinalTestGateError(
            f"{label} hash mismatch ({actual_hash} != {expected_hash.lower()})."
        )
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalTestGateError(f"{label} is not a readable JSON artifact: {path}") from exc
    if not isinstance(value, Mapping):
        raise FinalTestGateError(f"{label} JSON root must be an object.")
    return value


def _has_unresolved_marker(value: Any) -> bool:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if key == "unresolved_gates" and child:
                return True
            if key == "runnable" and child is False:
                return True
            if _has_unresolved_marker(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_has_unresolved_marker(child) for child in value)
    return False


def _require_bindings(
    artifact: Mapping[str, Any],
    expected: Mapping[str, Any],
    label: str,
) -> None:
    mismatched = [
        key for key, expected_value in expected.items() if artifact.get(key) != expected_value
    ]
    if mismatched:
        raise FinalTestGateError(
            f"{label} is not bound to this run: " + ", ".join(sorted(mismatched))
        )


def _code_provenance(source: Any, source_digest: str) -> dict[str, Any]:
    """Keep the human-meaningful code identity alongside its integrity digest."""

    if isinstance(source, Mapping):
        provenance = dict(source)
    elif isinstance(source, Path):
        provenance = {"source_reference": str(source)}
    else:
        provenance = {"source_reference": source}
    provenance["source_digest"] = source_digest
    return provenance


def _validate_final_test_gate(
    resolved_config: Mapping[str, Any],
    freeze_evidence: Mapping[str, Any] | None,
    protocol: Mapping[str, Any],
    *,
    method: str,
    dataset: str,
    split: str,
    model: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> None:
    supported_requirements = {
        "resolved_run_config",
        "track_freeze_evidence",
        "data_and_split_hashes",
        "model_and_evaluator_revisions",
        "leakage_audit_pass",
    }
    declared_requirements = protocol.get("final_test_requires", supported_requirements)
    if not isinstance(declared_requirements, (list, tuple, set, frozenset)):
        raise FinalTestGateError("Protocol final_test_requires must be a collection.")
    unsupported = {str(item) for item in declared_requirements} - supported_requirements
    if unsupported:
        raise FinalTestGateError(
            "Runner cannot verify protocol final-test requirements: "
            + ", ".join(sorted(unsupported))
        )
    if resolved_config.get("resolved") is not True or _has_unresolved_marker(resolved_config):
        raise FinalTestGateError(
            "Final test requires resolved=True and no unresolved/runnable-false markers."
        )
    track = resolved_config.get("track")
    if not isinstance(track, str) or not track.strip():
        raise FinalTestGateError("Final test resolved config must name its track.")
    if resolved_config.get("dataset") != dataset or resolved_config.get("split") != split:
        raise FinalTestGateError("Resolved config dataset/split is not bound to this run.")

    evidence = dict(freeze_evidence or {})
    freeze_artifact = _verified_json_artifact(evidence.get("freeze_artifact"), "freeze artifact")
    leakage_artifact = _verified_json_artifact(evidence.get("leakage_audit"), "leakage audit")
    expected_common = {
        "track": track,
        "method": method,
        "dataset": dataset,
        "split": split,
        "resolved_config_hash": hashes["config"],
        "data_hash": hashes["data"],
        "split_hash": hashes["split"],
        "model_hash": hashes["model"],
        "model_id": model["id"],
        "model_revision": model["revision"],
    }
    _require_bindings(
        freeze_artifact,
        {"status": "FROZEN", **expected_common},
        "freeze artifact",
    )
    evaluator_revision = freeze_artifact.get("evaluator_revision")
    if not isinstance(evaluator_revision, str) or not evaluator_revision.strip():
        raise FinalTestGateError("Freeze artifact must pin a non-empty evaluator_revision.")
    _require_bindings(
        leakage_artifact,
        {
            "status": "PASS",
            "track": track,
            "dataset": dataset,
            "split": split,
            "data_hash": hashes["data"],
            "split_hash": hashes["split"],
        },
        "leakage audit",
    )


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_bytes_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise RunIntegrityError(f"Artifact already exists and will not be overwritten: {path.name}") from exc


@dataclass(frozen=True)
class RunHandle:
    """A handle to one run directory managed by :class:`RunStore`."""

    store: "RunStore"
    run_id: str

    @property
    def path(self) -> Path:
        return self.store.root / self.run_id

    @property
    def manifest_path(self) -> Path:
        return self.path / "manifest.json"

    def manifest(self) -> dict[str, Any]:
        return self.store._read_manifest(self.run_id)

    def _require_mutable(self) -> dict[str, Any]:
        manifest = self.manifest()
        if manifest["status"] in TERMINAL_STATUSES:
            raise RunIntegrityError(
                f"Run {self.run_id} is {manifest['status']} and its evidence is immutable."
            )
        return manifest

    def _record_artifact(self, relative_path: str) -> None:
        manifest = self._require_mutable()
        artifact = self.path / relative_path
        artifacts = dict(manifest.get("artifacts", {}))
        artifacts[relative_path] = {
            "sha256": sha256_path(artifact),
            "bytes": artifact.stat().st_size,
        }
        manifest["artifacts"] = artifacts
        self.store._write_manifest(self.run_id, manifest)

    def record_rankings(self, rankings: Sequence[RankingResult]) -> Path:
        """Persist canonical rankings with raw scores; one JSON object per query."""

        self._require_mutable()
        ordered = sorted(rankings, key=lambda result: result.query_id)
        query_ids = [result.query_id for result in ordered]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("Each query_id may appear only once in ranking output.")
        payload = b"".join(
            _canonical_json_bytes(result.model_dump(mode="json")) + b"\n" for result in ordered
        )
        path = self.path / "rankings.jsonl"
        _write_bytes_new(path, payload)
        self._record_artifact(path.name)
        return path

    def record_per_query(self, metrics: Mapping[str, Mapping[str, float]]) -> Path:
        """Persist per-query metrics without permitting an overwrite."""

        self._require_mutable()
        value = {str(query_id): dict(query_metrics) for query_id, query_metrics in metrics.items()}
        payload = _canonical_json_bytes(value) + b"\n"
        path = self.path / "per_query.json"
        _write_bytes_new(path, payload)
        self._record_artifact(path.name)
        return path

    def append_log(self, message: str, *, at: datetime | None = None) -> None:
        """Append a sanitized event while the run is active."""

        self._require_mutable()
        timestamp = _aware_time(at).isoformat()
        with (self.path / "run.log").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{timestamp} {_redact_text(message)}\n")

    def complete(
        self,
        aggregate_metrics: Mapping[str, float],
        *,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        """Seal a successful run after ranking and per-query artifacts exist."""

        manifest = self._require_mutable()
        required_artifacts = {"rankings.jsonl", "per_query.json"}
        recorded = set(manifest.get("artifacts", {}))
        missing = sorted(required_artifacts - recorded)
        if missing:
            raise RunIntegrityError("Cannot complete run; missing artifacts: " + ", ".join(missing))
        # A terminal status is evidence only if every previously registered byte
        # still matches the digest captured at write time.
        self.verify_integrity()
        # Serializing first rejects non-finite aggregate values.
        _canonical_json_bytes(dict(aggregate_metrics))
        log_path = self.path / "run.log"
        if log_path.exists():
            artifacts = dict(manifest["artifacts"])
            artifacts[log_path.name] = {
                "sha256": sha256_path(log_path),
                "bytes": log_path.stat().st_size,
            }
            manifest["artifacts"] = artifacts
        finished = _aware_time(at).isoformat()
        manifest.update(
            status="COMPLETED",
            completed_at=finished,
            metrics=dict(aggregate_metrics),
            aggregate_metrics=dict(aggregate_metrics),
            error=None,
        )
        self.store._write_manifest(self.run_id, manifest)
        self.store._seal_terminal_manifest(self.run_id)
        return manifest

    def fail(self, error: BaseException | str, *, at: datetime | None = None) -> dict[str, Any]:
        """Preserve a terminal failed run together with a sanitized error."""

        manifest = self._require_mutable()
        if isinstance(error, BaseException):
            error_type = type(error).__name__
            message = str(error)
        else:
            error_type = "RunError"
            message = str(error)
        error_record = {"type": error_type, "message": _redact_text(message)}
        _write_bytes_new(self.path / "error.json", _canonical_json_bytes(error_record) + b"\n")
        artifacts = {
            **manifest.get("artifacts", {}),
            "error.json": {
                "sha256": sha256_path(self.path / "error.json"),
                "bytes": (self.path / "error.json").stat().st_size,
            },
        }
        log_path = self.path / "run.log"
        if log_path.exists():
            artifacts[log_path.name] = {
                "sha256": sha256_path(log_path),
                "bytes": log_path.stat().st_size,
            }
        manifest["artifacts"] = artifacts
        manifest.update(
            status="FAILED",
            completed_at=_aware_time(at).isoformat(),
            error_message=error_record["message"],
            error=error_record,
        )
        self.store._write_manifest(self.run_id, manifest)
        self.store._seal_terminal_manifest(self.run_id)
        return manifest

    def verify_integrity(self) -> None:
        """Check all registered artifacts against their recorded SHA-256 hashes."""

        manifest = self.manifest()
        for relative_path, record in manifest.get("artifacts", {}).items():
            path = self.path / relative_path
            if not path.is_file() or sha256_path(path) != record["sha256"]:
                raise RunIntegrityError(f"Artifact integrity check failed: {relative_path}")

    def export(self, destination: Path | str) -> Path:
        """Copy the whole run to a new path, refusing to overwrite notebook output."""

        self.verify_integrity()
        target = Path(destination)
        if target.exists():
            raise RunIntegrityError(f"Export destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.path, target)
        return target


class RunStore:
    """Create, resume, and inspect immutable ScholarGraph experiment runs."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not re.fullmatch(r"RUN-\d{8}-\d{6}-[A-Za-z0-9_-]+", run_id):
            raise ValueError(f"Invalid run_id: {run_id!r}")

    def _read_manifest(self, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        path = self.root / run_id / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"Run manifest not found: {run_id}")
        with path.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        if manifest.get("run_id") != run_id:
            raise RunIntegrityError("Run directory and manifest run_id disagree.")
        if manifest.get("status") in TERMINAL_STATUSES:
            seal_path = path.with_name("seal.json")
            if not seal_path.is_file():
                raise RunIntegrityError(f"Terminal run {run_id} is missing its manifest seal.")
            with seal_path.open("r", encoding="utf-8") as stream:
                seal = json.load(stream)
            if seal.get("manifest_sha256") != sha256_path(path):
                raise RunIntegrityError(f"Terminal manifest integrity check failed: {run_id}")
        return manifest

    def _write_manifest(self, run_id: str, manifest: Mapping[str, Any]) -> None:
        _write_json_atomic(self.root / run_id / "manifest.json", _redact_metadata(manifest))

    def _seal_terminal_manifest(self, run_id: str) -> None:
        manifest_path = self.root / run_id / "manifest.json"
        seal = {"manifest_sha256": sha256_path(manifest_path)}
        _write_bytes_new(
            manifest_path.with_name("seal.json"),
            _canonical_json_bytes(seal) + b"\n",
        )

    def _allocate_run_id(
        self,
        method: str,
        dataset: str,
        split: str,
        at: datetime,
    ) -> tuple[str, Path]:
        timestamp = at.strftime("%Y%m%d-%H%M%S")
        base = "-".join(
            ("RUN", timestamp, _safe_component(method), _safe_component(dataset), _safe_component(split))
        )
        suffix = 1
        while True:
            run_id = base if suffix == 1 else f"{base}-{suffix}"
            path = self.root / run_id
            try:
                path.mkdir(parents=False, exist_ok=False)
                return run_id, path
            except FileExistsError:
                suffix += 1

    def create(
        self,
        *,
        method: str,
        dataset: str,
        split: str,
        resolved_config: Mapping[str, Any],
        data_source: Any,
        split_definition: Any,
        code_source: Any,
        model: Mapping[str, Any],
        seed: int,
        command: Sequence[str],
        protocol_source: Mapping[str, Any] | Path | str | None = None,
        hardware_info: Mapping[str, Any] | None = None,
        environment_lock: Mapping[str, Any] | None = None,
        extra_hash_sources: Mapping[str, Any] | None = None,
        synthetic: bool = False,
        final_test: bool = False,
        freeze_evidence: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> RunHandle:
        """Allocate a unique running run and write its initial manifest atomically."""

        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError("seed must be an integer")
        if not command:
            raise ValueError("command must not be empty")
        if not model.get("id") or not model.get("revision"):
            raise ValueError("model must include non-empty id and revision")
        protocol = _load_json_source(protocol_source)
        requires_final_gate = final_test or (split.strip().lower() == "test" and not synthetic)

        created = _aware_time(at)
        hashes = {
            "protocol": sha256_value(protocol),
            "config": sha256_value(dict(resolved_config)),
            "data": sha256_value(data_source),
            "split": sha256_value(split_definition),
            "code": sha256_value(code_source),
            "model": sha256_value(dict(model)),
        }
        for name, source in (extra_hash_sources or {}).items():
            safe_name = str(name).strip()
            if not safe_name or safe_name in hashes:
                raise ValueError(f"Invalid or duplicate extra hash name: {name!r}")
            hashes[safe_name] = sha256_value(source)
        if any(not SHA256_RE.fullmatch(value) for value in hashes.values()):
            raise RunIntegrityError("Internal error: a provenance digest is not SHA-256.")
        if requires_final_gate:
            _validate_final_test_gate(
                resolved_config,
                freeze_evidence,
                protocol,
                method=method,
                dataset=dataset,
                split=split,
                model=model,
                hashes=hashes,
            )

        run_id, run_path = self._allocate_run_id(method, dataset, split, created)
        try:
            base_manifest = RunManifest(
                run_id=run_id,
                protocol_version=str(protocol.get("protocol_version", "1.0.0")),
                method=method,
                dataset=dataset,
                split=split,
                status="RUNNING",
                config_hash=hashes["config"],
                data_hash=hashes["data"],
                split_hash=hashes["split"],
                created_at=created,
                parameters=dict(resolved_config),
                hardware_info=dict(hardware_info or collect_hardware_info()),
                synthetic=synthetic,
            ).model_dump(mode="json")
            manifest = {
                **base_manifest,
                "schema_version": 1,
                "hashes": hashes,
                "code_hash": hashes["code"],
                "model_hash": hashes["model"],
                "protocol_hash": hashes["protocol"],
                "resolved_config": dict(resolved_config),
                "code_provenance": _code_provenance(code_source, hashes["code"]),
                "model": dict(model),
                "seed": seed,
                "command": _redact_command(command),
                "environment_lock": dict(environment_lock or {"python": sys.version.split()[0]}),
                "final_test": requires_final_gate,
                "freeze_evidence": dict(freeze_evidence or {}),
                "artifacts": {},
                "aggregate_metrics": None,
                "error": None,
            }
            started = f"{created.isoformat()} status=RUNNING run_id={run_id}\n".encode("utf-8")
            _write_bytes_new(run_path / "run.log", started)
            self._write_manifest(run_id, manifest)
        except BaseException:
            shutil.rmtree(run_path)
            raise
        return RunHandle(self, run_id)

    def resume(
        self,
        run_id: str,
        *,
        expected_hashes: Mapping[str, str] | None = None,
    ) -> RunHandle:
        """Resume only an unfinished run, optionally checking caller provenance."""

        handle = RunHandle(self, run_id)
        manifest = handle.manifest()
        if manifest["status"] in TERMINAL_STATUSES:
            raise RunIntegrityError(
                f"Run {run_id} is {manifest['status']}; retry with a new run ID."
            )
        for name, expected in (expected_hashes or {}).items():
            actual = manifest.get("hashes", {}).get(name)
            if actual != expected:
                raise RunIntegrityError(
                    f"Cannot resume {run_id}: {name} hash mismatch ({actual!r} != {expected!r})."
                )
        handle.verify_integrity()
        return handle
