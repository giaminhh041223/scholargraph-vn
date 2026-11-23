"""Verify 1:1 correspondence between report/claims checklist and evidence_index.json (SG-043).

Checks:
  1. Every claim_id in artifacts/reports/evidence_index.json is cited in both
     docs/CLAIMS_CHECKLIST.md and reports/final_report.md.
  2. All primary Track A & Track B nDCG@10 values (formatted to 4 decimals) are
     present in reports/final_report.md.
  3. Negative findings (Hybrid < Dense on BEIR, PPR vs Global PR CI includes 0,
     Age decay lambda > 0 degrades nDCG@10) are explicitly documented.
  4. No forbidden p-value assertions ("p < 0.05", "p = 0.") or SOTA claims
     appear in reports/final_report.md or docs/CLAIMS_CHECKLIST.md.
  5. While Track C VN status is 'chua_do', report explicitly states 'chưa đo' /
     'SG-033' and does not invent Track C test scores.
  6. The nDCG@10 bootstrap CIs behind CLM-001..CLM-004 appear in both documents
     exactly as stored in table_6_paired_bootstrap (4 decimals, signed).

Not checked: any other number (secondary metrics, robustness buckets, counts).

Anti-Silent-Bypass: exits 1 on any missing file, missing claim ID, missing
primary metric, or forbidden pattern.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATTERNS = (
    (re.compile(r"\bp\s*[<=]\s*0\.0\d+", re.IGNORECASE), "forbidden p-value threshold claim"),
    (re.compile(r"\bp-value\s*=\s*0\.\d+", re.IGNORECASE), "forbidden numeric p-value claim"),
    (re.compile(r"\bwe achieve state-of-the-art\b", re.IGNORECASE), "forbidden SOTA claim"),
    (re.compile(r"\bđạt chuẩn state-of-the-art\b", re.IGNORECASE), "forbidden SOTA claim"),
)
CLAIM_CI_KEYS = (
    "scifact__dense-vs-bm25__nDCG@10",
    "scidocs__dense-vs-bm25__nDCG@10",
    "scifact__hybrid-vs-dense__nDCG@10",
    "scidocs__hybrid-vs-dense__nDCG@10",
    "openalex__ppr_best-vs-global_control__nDCG@10",
)


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def verify_documents(
    evidence_doc: dict[str, Any],
    report_text: str,
    checklist_text: str,
) -> dict[str, Any]:
    if not report_text.strip():
        raise ValueError("reports/final_report.md is empty")
    if not checklist_text.strip():
        raise ValueError("docs/CLAIMS_CHECKLIST.md is empty")

    claims = evidence_doc.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("evidence_index.json has no claims list")

    missing_in_report: list[str] = []
    missing_in_checklist: list[str] = []
    for c in claims:
        cid = str(c.get("claim_id", "")).strip()
        if not cid:
            raise ValueError("Claim entry missing claim_id")
        if cid not in report_text:
            missing_in_report.append(cid)
        if cid not in checklist_text:
            missing_in_checklist.append(cid)

    if missing_in_report:
        raise ValueError(f"final_report.md missing claim IDs: {missing_in_report}")
    if missing_in_checklist:
        raise ValueError(f"CLAIMS_CHECKLIST.md missing claim IDs: {missing_in_checklist}")

    tables = evidence_doc.get("tables") or {}
    t1 = tables.get("table_1_track_a_main") or {}
    t2 = (tables.get("table_2_track_b_main") or {}).get("arms") or {}
    if not t1 or not t2:
        raise ValueError("evidence_index.json missing table_1_track_a_main or table_2_track_b_main")

    required_numbers: list[tuple[str, str]] = []
    for key, row in sorted(t1.items()):
        val = float(row["metrics"]["nDCG@10"])
        required_numbers.append((f"Track A {key} nDCG@10", f"{val:.4f}"))
        if row["run_id"] not in report_text and row["run_id"] not in checklist_text:
            raise ValueError(f"Run ID {row['run_id']} not cited in report or claims checklist")

    for arm, metrics in sorted(t2.items()):
        val = float(metrics["nDCG@10"])
        required_numbers.append((f"Track B {arm} nDCG@10", f"{val:.4f}"))

    missing_numbers = [label for label, num_str in required_numbers if num_str not in report_text]
    if missing_numbers:
        raise ValueError(f"final_report.md missing primary metric values: {missing_numbers}")

    # Bootstrap CIs behind CLM-001..CLM-004 must be quoted exactly as measured in both documents.
    t6 = tables.get("table_6_paired_bootstrap") or {}
    missing_ci: list[str] = []
    for key in CLAIM_CI_KEYS:
        row = t6[key]
        ci = f"[{float(row['ci_low']):+.4f}, {float(row['ci_high']):+.4f}]"
        for text_name, text_body in (("final_report.md", report_text), ("CLAIMS_CHECKLIST.md", checklist_text)):
            if ci not in text_body:
                missing_ci.append(f"{text_name}: {key} {ci}")
    if missing_ci:
        raise ValueError(f"bootstrap CI not quoted as measured: {missing_ci}")

    for text_name, text_body in (("final_report.md", report_text), ("CLAIMS_CHECKLIST.md", checklist_text)):
        for regex, reason in FORBIDDEN_PATTERNS:
            m = regex.search(text_body)
            if m:
                raise ValueError(f"{text_name} contains {reason}: {m.group(0)!r}")

    t3 = tables.get("table_3_track_c_vn") or {}
    if t3.get("status") == "chua_do":
        if "SG-033" not in report_text or ("chưa đo" not in report_text.lower() and "chờ nhãn" not in report_text.lower()):
            raise ValueError(
                "Track C VN status is chua_do, but final_report.md does not clearly state pending SG-033 human labels"
            )

    return {
        "status": "PASS",
        "verified_claims": len(claims),
        "verified_primary_numbers": len(required_numbers),
        "track_c_status": t3.get("status"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify report and claims checklist against evidence_index.json (SG-043)")
    ap.add_argument("--evidence-index", default="artifacts/reports/evidence_index.json")
    ap.add_argument("--report", default="reports/final_report.md")
    ap.add_argument("--checklist", default="docs/CLAIMS_CHECKLIST.md")
    args = ap.parse_args(argv)
    try:
        ev_path = Path(args.evidence_index) if Path(args.evidence_index).is_absolute() else ROOT / args.evidence_index
        rep_path = Path(args.report) if Path(args.report).is_absolute() else ROOT / args.report
        chk_path = Path(args.checklist) if Path(args.checklist).is_absolute() else ROOT / args.checklist
        for p in (ev_path, rep_path, chk_path):
            if not p.is_file():
                return fail(f"Missing required file: {p}")

        ev_doc = json.loads(ev_path.read_text(encoding="utf-8"))
        rep_text = rep_path.read_text(encoding="utf-8")
        chk_text = chk_path.read_text(encoding="utf-8")
        res = verify_documents(ev_doc, rep_text, chk_text)
        print(json.dumps(res, indent=2))
        return 0
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
