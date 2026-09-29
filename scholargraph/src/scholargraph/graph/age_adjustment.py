"""Age freshness adjustment — task SG-024 (post-fusion variant, Protocol §5.4).

Single authorized family: ``F_age(d) = F(d) × exp(-lambda × max(0, year(u) -
year(d)))`` with ``lambda ∈ {0, 0.01, 0.03, 0.05, 0.1}``. Reference year is
the SOURCE year ``year(u)``, never the machine clock. Future-dated candidates
(``year(d) > year(u)``) get weight 1.0 (no boost, no penalty). Missing
publication year is EXCLUDED from line B from the start — never median-imputed
(ADR-013/014, ARCHITECTURE §5.2); encountering one here is a loud error.

This is a post-fusion freshness adaptation, NOT a re-implementation of
CiteRank or time-balanced centrality, and higher new-paper exposure proves no
fairness/debiasing claim (protocol §5.4, RQ3).

Failure contract: unknown lambda, non-integer years, missing years, empty
candidate lists, or non-finite scores fail loudly; CLI exits 1.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_VERSION = "sg024-1.0.0"
SCHEMA_VERSION = 1
LAMBDA_GRID = (0.0, 0.01, 0.03, 0.05, 0.1)
YEAR_MIN, YEAR_MAX = 1900, 2100


class AgeDataError(Exception):
    """Fatal age-adjustment input or config problem."""


def _require_year(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgeDataError(f"{name} must be an integer year, got {value!r}")
    if not (YEAR_MIN <= value <= YEAR_MAX):
        raise AgeDataError(f"{name} out of range [{YEAR_MIN},{YEAR_MAX}]: {value}")
    return value


def _require_lambda(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AgeDataError(f"lambda must be a finite number, got {value!r}")
    if float(value) not in LAMBDA_GRID:
        raise AgeDataError(f"lambda must be one of {list(LAMBDA_GRID)}, got {value!r}")
    return float(value)


def age_weight(year_source: int, year_doc: int, lambda_: float) -> float:
    """Freshness multiplier for one candidate (1.0 for future-dated docs)."""
    yu = _require_year(year_source, "year_source")
    yd = _require_year(year_doc, "year_doc")
    lam = _require_lambda(lambda_)
    gap = max(0, yu - yd)
    w = math.exp(-lam * gap)
    if not math.isfinite(w):
        raise AgeDataError(f"Non-finite age weight for gap {gap}, lambda {lam}")
    return w


def apply_age(
    fused: Sequence[Mapping[str, Any]],
    years: Mapping[str, int | None],
    year_source: int,
    lambda_: float,
) -> list[dict[str, Any]]:
    """Apply the age variant to fused rows [{doc_id, fused}]; re-sorts."""
    lam = _require_lambda(lambda_)
    yu = _require_year(year_source, "year_source")
    if not fused:
        raise AgeDataError("Empty fused list")
    rows = []
    seen: set[str] = set()
    for r in fused:
        if not isinstance(r, Mapping) or "doc_id" not in r or "fused" not in r:
            raise AgeDataError(f"Invalid fused row: {r!r}")
        d = r["doc_id"]
        s = r["fused"]
        if d in seen:
            raise AgeDataError(f"Duplicate doc: {d}")
        seen.add(d)
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s):
            raise AgeDataError(f"Non-finite fused score for {d}: {s!r}")
        if d not in years or years[d] is None:
            raise AgeDataError(f"Missing publication year for {d} (excluded from line B, never imputed)")
        yd = _require_year(years[d], f"year({d})")
        w = age_weight(yu, yd, lam)
        rows.append({"doc_id": d, "fused": float(s), "age_weight": w,
                     "fused_age": float(s) * w, "age_gap": max(0, yu - yd)})
    rows.sort(key=lambda x: (-x["fused_age"], x["doc_id"]))
    return rows


def exposure_by_gap(
    rows: Sequence[Mapping[str, Any]],
    k: int,
) -> dict[str, Any]:
    """Descriptive exposure: share of top-k fused_age mass per age-gap bucket.

    Mass-share descriptive variant for SG-024 analysis. The protocol §6.3
    rank-discounted exposure (exposure_b@10) is implemented separately in
    :func:`exposure_at_10` and MUST be used for RQ3 reporting in SG-026+.

    Purely descriptive — says nothing about relevance, fairness or causality.
    When total mass is 0 (all fused_age 0) shares are reported as 0.0
    (documented convention, not a measurement).
    """
    if k <= 0:
        raise AgeDataError(f"Invalid k: {k}")
    if not rows:
        raise AgeDataError("Empty rows for exposure")
    top = sorted(rows, key=lambda x: (-x["fused_age"], x["doc_id"]))[:k]
    mass = sum(x["fused_age"] for x in top)
    buckets: dict[str, float] = {"0-2y": 0.0, "3-5y": 0.0, "6-10y": 0.0, ">10y": 0.0}
    for x in top:
        g = x["age_gap"]
        key = "0-2y" if g <= 2 else ("3-5y" if g <= 5 else ("6-10y" if g <= 10 else ">10y"))
        buckets[key] += x["fused_age"]
    if mass > 0:
        buckets = {b: v / mass for b, v in buckets.items()}
    return {"k": k, "mass_shares": buckets}


def exposure_at_10(
    ranked_doc_ids: Sequence[str],
    gaps: Mapping[str, int],
) -> dict[str, Any]:
    """Protocol §6.3 rank-discounted exposure over the returned top-10.

    exposure_b@10 = Σ_{i≤10} I(gap_i ∈ b)/log2(i+1), divided by the total
    discount of the ACTUAL returned results (empty list → 0). Buckets
    0–2 / 3–5 / 6–10 / ≥11. Unknown-gap docs raise (never silently dropped).
    """
    if not ranked_doc_ids:
        return {"k": 0, "results": 0, "exposure": {"0-2y": 0.0, "3-5y": 0.0, "6-10y": 0.0, ">=11y": 0.0}}
    top = list(ranked_doc_ids)[:10]
    discounts = [1.0 / math.log2(i + 2) for i in range(len(top))]
    total = sum(discounts)
    buckets = {"0-2y": 0.0, "3-5y": 0.0, "6-10y": 0.0, ">=11y": 0.0}
    for d, disc in zip(top, discounts):
        if d not in gaps or gaps[d] is None:
            raise AgeDataError(f"Unknown age gap for {d} (never silently dropped)")
        g = gaps[d]
        key = "0-2y" if g <= 2 else ("3-5y" if g <= 5 else ("6-10y" if g <= 10 else ">=11y"))
        buckets[key] += disc
    return {"k": 10, "results": len(top), "exposure": {b: v / total for b, v in buckets.items()}}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Age adjustment analysis (SG-024)")
    p.add_argument("--fused", required=True, help="JSON query_id -> [{doc_id, fused}]")
    p.add_argument("--years", required=True, help="JSON doc_id -> year (null forbidden)")
    p.add_argument("--query-years", required=True, help="JSON query_id -> source year")
    p.add_argument("--output", required=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        def _load(p: str) -> Any:
            try:
                return json.loads(Path(p).read_text(encoding="utf-8"))
            except FileNotFoundError:
                raise AgeDataError(f"Missing required file: {p}")
            except json.JSONDecodeError as exc:
                raise AgeDataError(f"Malformed JSON in {p}: {exc}")
        fused, years, qyears = _load(args.fused), _load(args.years), _load(args.query_years)
        if not isinstance(fused, dict) or not isinstance(years, dict) or not isinstance(qyears, dict):
            raise AgeDataError("Inputs must be JSON objects")
        if set(fused) != set(qyears):
            raise AgeDataError("Fused and query-years must cover the same queries")
        per_lambda: dict[str, Any] = {}
        for lam in LAMBDA_GRID:
            exp_acc: dict[str, float] = {"0-2y": 0.0, "3-5y": 0.0, "6-10y": 0.0, ">10y": 0.0}
            n = 0
            for qid in sorted(fused):
                rows = apply_age(fused[qid], years, qyears[qid], lam)
                e = exposure_by_gap(rows, min(10, len(rows)))
                for b, v in e["mass_shares"].items():
                    exp_acc[b] += v
                n += 1
            per_lambda[str(lam)] = {"queries": n, "mean_top10_mass_shares": {b: v / n for b, v in exp_acc.items()}}
        payload = {"schema_version": SCHEMA_VERSION, "module_version": MODULE_VERSION,
                   "task_id": "SG-024", "generated_at": datetime.now(timezone.utc).isoformat(),
                   "lambda_grid": list(LAMBDA_GRID),
                   "note": "Descriptive exposure only. Relevance-side selection belongs to SG-026; no fairness claim.",
                   "per_lambda": per_lambda}
        outp = Path(args.output)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(outp), "queries": len(fused)}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
