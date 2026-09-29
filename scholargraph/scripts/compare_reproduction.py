"""Compare a second human member's reproduced runs against evidence_index.json (SG-042).

Enforces Research Protocol v1 tolerance (1e-4 default) and SG-042 acceptance
criteria:
  - Requires a human reproducer identifier (--reproducer); rejects AI/agent
    names so agent runs are never mislabeled as human reproduction.
  - Compares all 5 protocol metrics (nDCG@10, Recall@100, MRR@10, MAP@100, P@5)
    for each provided Track A run or Track B arm against evidence_index.json.
  - Fails loudly (exit 1) on missing files, empty candidate, unknown arm/run,
    missing metric, non-finite/out-of-bounds score, or abs diff > tolerance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "SG-042"
MODULE_VERSION = "sg042-1.0.0"
REQUIRED_METRICS = ("nDCG@10", "Recall@100", "MRR@10", "MAP@100", "P@5")
FORBIDDEN_REPRODUCERS = {"agent", "codex", "gemini", "claude", "ai", "bot", "system", "auto"}


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_reproducer(name: str) -> str:
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ValueError("Missing required --reproducer (human member identifier)")
    tokens = {t.lower() for t in cleaned.replace("-", " ").replace("_", " ").split()}
    if cleaned.lower() in FORBIDDEN_REPRODUCERS or (tokens & FORBIDDEN_REPRODUCERS):
        raise ValueError(
            f"Refusing non-human reproducer {cleaned!r}: SG-042 forbids calling agent runs human reproduction"
        )
    return cleaned


def compare_candidate(
    evidence_doc: dict[str, Any],
    candidate_doc: dict[str, Any],
    *,
    reproducer: str,
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    human_id = validate_reproducer(reproducer)
    if not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance <= 0 or tolerance > 0.01:
        raise ValueError(f"Invalid tolerance {tolerance!r}; must be in (0, 0.01]")

    tables = evidence_doc.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Malformed evidence_index.json: missing 'tables'")
    ref_a = tables.get("table_1_track_a_main")
    ref_b = (tables.get("table_2_track_b_main") or {}).get("arms")
    if not isinstance(ref_a, dict) or not isinstance(ref_b, dict):
        raise ValueError("Malformed evidence_index.json: missing Track A or Track B reference tables")

    if not isinstance(candidate_doc, dict):
        raise ValueError("Candidate reproduction payload must be a JSON object")

    cand_a = candidate_doc.get("track_A", {})
    cand_b = candidate_doc.get("track_B", {})
    if not isinstance(cand_a, dict) or not isinstance(cand_b, dict):
        raise ValueError("Candidate track_A and track_B fields must be JSON objects")
    if not cand_a and not cand_b:
        raise ValueError("Candidate reproduction payload has neither track_A nor track_B runs")

    rows: list[dict[str, Any]] = []
    drifted: list[str] = []

    def _check_block(track_label: str, cand_map: dict[str, Any], ref_map: dict[str, Any]) -> None:
        for key, cand_entry in sorted(cand_map.items()):
            if key not in ref_map:
                raise ValueError(f"Unknown {track_label} key {key!r} (not in evidence_index.json)")
            ref_metrics = ref_map[key].get("metrics") if "metrics" in ref_map[key] else ref_map[key]
            cand_metrics = cand_entry.get("metrics") if isinstance(cand_entry, dict) and "metrics" in cand_entry else cand_entry
            if not isinstance(cand_metrics, dict):
                raise ValueError(f"Candidate {track_label}:{key} must provide a metrics mapping")
            for m in REQUIRED_METRICS:
                if m not in cand_metrics:
                    raise ValueError(f"Candidate {track_label}:{key} missing required metric {m!r}")
                val = cand_metrics[m]
                if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(float(val)):
                    raise ValueError(f"Candidate {track_label}:{key} metric {m!r} is non-numeric or non-finite: {val!r}")
                fval = float(val)
                if fval < 0.0 or fval > 1.0:
                    raise ValueError(f"Candidate {track_label}:{key} metric {m!r}={fval} outside [0, 1]")
                rval = float(ref_metrics[m])
                diff = abs(fval - rval)
                passed = diff <= tolerance
                if not passed:
                    drifted.append(f"{track_label}:{key}:{m} (diff={diff:.6e} > tol={tolerance:.6e})")
                rows.append(
                    {
                        "track": track_label,
                        "key": key,
                        "metric": m,
                        "reference": rval,
                        "reproduced": fval,
                        "abs_diff": diff,
                        "within_tolerance": passed,
                    }
                )

    _check_block("A", cand_a, ref_a)
    _check_block("B", cand_b, ref_b)

    max_diff = max((r["abs_diff"] for r in rows), default=0.0)
    status = "PASS" if not drifted else "FAIL"
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "module_version": MODULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reproducer": human_id,
        "tolerance": tolerance,
        "status": status,
        "checked_metrics_count": len(rows),
        "max_abs_diff": max_diff,
        "drifted": drifted,
        "rows": rows,
    }


def write_audit_markdown(audit: dict[str, Any], out_path: Path) -> None:
    lines = [
        "# Báo cáo đối chiếu tái lập chéo (SG-042)",
        "",
        f"- **Người tái lập (Human Reproducer):** `{audit['reproducer']}`",
        f"- **Trạng thái:** **{audit['status']}**",
        f"- **Ngưỡng sai số (Tolerance):** `{audit['tolerance']:.1e}`",
        f"- **Số phép đo đối chiếu:** `{audit['checked_metrics_count']}`",
        f"- **Sai lệch tuyệt đối lớn nhất (`max_abs_diff`):** `{audit['max_abs_diff']:.3e}`",
        "",
        "| Track | Cấu hình / Run | Metric | Giá trị gốc (Sealed) | Giá trị tái lập | `|Diff|` | Kết quả |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for r in audit["rows"]:
        verdict = "PASS" if r["within_tolerance"] else "FAIL"
        lines.append(
            f"| {r['track']} | `{r['key']}` | `{r['metric']}` | {r['reference']:.6f} | "
            f"{r['reproduced']:.6f} | {r['abs_diff']:.2e} | {verdict} |"
        )
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare human reproduction against evidence_index.json (SG-042)")
    ap.add_argument("--reproducer", required=True, help="Human member name/ID who executed the reproduction")
    ap.add_argument("--candidate", required=True, help="Path to candidate reproduction JSON file")
    ap.add_argument("--evidence-index", default="artifacts/reports/evidence_index.json")
    ap.add_argument("--tolerance", type=float, default=1e-4)
    ap.add_argument("--output-dir", default=None, help="Optional directory to write reproduction_audit.json/.md")
    args = ap.parse_args(argv)

    try:
        ev_path = Path(args.evidence_index) if Path(args.evidence_index).is_absolute() else ROOT / args.evidence_index
        cand_path = Path(args.candidate) if Path(args.candidate).is_absolute() else ROOT / args.candidate
        if not ev_path.is_file():
            return fail(f"Missing evidence index: {ev_path}")
        if not cand_path.is_file():
            return fail(f"Missing candidate reproduction file: {cand_path}")

        ev_doc = json.loads(ev_path.read_text(encoding="utf-8"))
        cand_doc = json.loads(cand_path.read_text(encoding="utf-8"))
        audit = compare_candidate(
            ev_doc,
            cand_doc,
            reproducer=args.reproducer,
            tolerance=args.tolerance,
        )
        audit["evidence_index_sha256"] = _sha256(ev_path)
        audit["candidate_sha256"] = _sha256(cand_path)

        if args.output_dir:
            out_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else ROOT / args.output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "reproduction_audit.json").write_text(
                json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            write_audit_markdown(audit, out_dir / "reproduction_audit.md")

        print(
            json.dumps(
                {
                    "status": audit["status"],
                    "reproducer": audit["reproducer"],
                    "checked_metrics_count": audit["checked_metrics_count"],
                    "max_abs_diff": audit["max_abs_diff"],
                },
                indent=2,
            )
        )
        if audit["status"] != "PASS":
            return fail(f"Reproduction drifted beyond tolerance: {'; '.join(audit['drifted'])}")
        return 0
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
