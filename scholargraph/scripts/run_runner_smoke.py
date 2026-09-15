"""Exercise SG-007 storage with synthetic data and retain inspectable evidence."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.runner import RunIntegrityError, RunStore, sha256_path


def main() -> None:
    now = datetime.now(timezone.utc)
    output = ROOT / "artifacts" / "runs" / f"SG007-SMOKE-{now:%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    store = RunStore(output / "runs")
    sources = ["src/scholargraph/evaluation/runner.py", "src/scholargraph/data/schemas.py",
               "scripts/run_runner_smoke.py"]
    code = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--", "."], cwd=ROOT, text=True).strip()),
        "snapshot_sha256": {path: sha256_path(ROOT / path) for path in sources},
    }
    environment = {"python": platform.python_version(),
                   **{name: version(name) for name in ("pydantic", "pytest", "httpx")}}
    inputs = dict(
        method="storage-smoke", dataset="synthetic-sg007", split="dev",
        resolved_config={"synthetic": True, "purpose": "storage acceptance only"},
        data_source={"synthetic": True, "documents": ["fixture:a", "fixture:b"]},
        split_definition={"synthetic": True, "query_ids": ["fixture:q1"]},
        code_source=code, model={"id": "fixture", "revision": "1"}, seed=20260915,
        command=[sys.executable, "-B", "scripts/run_runner_smoke.py"],
        protocol_source=ROOT / "configs/protocol_v1.json",
        environment_lock=environment, synthetic=True,
    )
    complete = store.create(**inputs)
    hashes = complete.manifest()["hashes"]
    resumed = store.resume(complete.run_id, expected_hashes=hashes)
    resumed.record_rankings([RankingResult.create_sorted(
        "fixture:q1", [("fixture:a", 0.9, None), ("fixture:b", 0.4, None)])])
    resumed.record_per_query({"fixture:q1": {"synthetic_smoke_value": 1.0}})
    resumed.append_log("Synthetic storage acceptance; no retrieval quality measured.")
    resumed.complete({"synthetic_smoke_value": 1.0})
    original = complete.manifest_path.read_bytes()

    def rejected(action) -> bool:
        try:
            action()
        except RunIntegrityError:
            return True
        raise AssertionError("Expected immutable/no-overwrite operation to be rejected")

    checks = {"resume_running": resumed.run_id == complete.run_id}
    checks["completed_write_rejected"] = rejected(lambda: complete.append_log("late write"))
    checks["completed_resume_rejected"] = rejected(lambda: store.resume(complete.run_id))
    exported = complete.export(output / "exports" / "completed")
    checks["export_overwrite_rejected"] = rejected(lambda: complete.export(exported))
    checks["completed_manifest_unchanged"] = (
        original == complete.manifest_path.read_bytes() == (exported / "manifest.json").read_bytes())
    failed = store.create(**inputs)
    message = '{"api_key":\n "SG007_SYNTHETIC_SECRET_42"}'
    failed.append_log(message)
    failed.fail(RuntimeError(message))
    failed_export = failed.export(output / "exports" / "failed")
    checks["failed_error_recorded"] = failed.manifest()["status"] == "FAILED" and (failed.path / "error.json").is_file()
    checks["failed_resume_rejected"] = rejected(lambda: store.resume(failed.run_id))
    checks["failed_secret_redacted"] = all(
        "SG007_SYNTHETIC_SECRET_42" not in path.read_text(encoding="utf-8")
        for directory in (failed.path, failed_export)
        for path in directory.rglob("*") if path.is_file()
    )
    complete.verify_integrity()
    failed.verify_integrity()
    checks["artifact_and_seal_integrity"] = True
    assert all(checks.values()), checks
    report = {
        "task_id": "SG-007", "created_at": now.isoformat(), "synthetic": True,
        "status": "PASS", "scope": "Storage acceptance only; no retrieval quality measured",
        "checks": checks, "environment": environment, "code_provenance": code,
        "runs": [{"run_id": handle.run_id, "status": handle.manifest()["status"],
                  "path": handle.path.relative_to(ROOT).as_posix(),
                  "manifest_sha256": sha256_path(handle.manifest_path),
                  "hashes": handle.manifest()["hashes"]} for handle in (complete, failed)],
        "exports": [path.relative_to(ROOT).as_posix() for path in (exported, failed_export)],
    }
    report_path = ROOT / "artifacts/reports/sg007_smoke_20260915.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "checks": len(checks), "report": str(report_path)}))


if __name__ == "__main__":
    main()
