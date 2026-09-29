"""Paired bootstrap uncertainty for sealed test comparisons (SG-030).

Implements ``configs/protocol_v1.json`` -> ``statistics`` exactly:

- Estimand: macro query-mean treatment-minus-control (paired by query).
- B=10.000 resamples over query groups (singleton per query unless a group map
  is supplied), seed from the protocol (20260915), percentile 95% CI with
  linear interpolation. Rerunning with the same seed reproduces bit-identical
  intervals (acceptance: CI/run IDs reproducible).
- No p-values, no formal significance claims (pointwise unadjusted CIs).
- Relative delta is undefined (null) when the control mean is 0.
- Deterministic repeated runs must NEVER be used as uncertainty
  (``deterministic_repeated_seeds_for_quality_ci=false``); only this bootstrap.

Failure contract: empty/mismatched inputs, non-finite values, unknown metric,
or an invalid (B, seed, level) triple fail loudly; CLI exits 1.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

MODULE_VERSION = "sg030-1.0.0"
PROTOCOL_SEED = 20260915
PROTOCOL_RESAMPLES = 10000
PROTOCOL_LEVEL = 0.95


class StatisticsError(Exception):
    """Fatal statistics input or configuration problem."""


def _require_metric_values(values: Mapping[str, float], name: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for qid, v in values.items():
        if not isinstance(qid, str) or not qid:
            raise StatisticsError(f"{name}: invalid query ID {qid!r}")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise StatisticsError(f"{name}: non-numeric value for {qid}")
        if not math.isfinite(f):
            raise StatisticsError(f"{name}: non-finite value for {qid}")
        out[qid] = f
    if not out:
        raise StatisticsError(f"{name}: empty value set")
    return out


def _check_paired(treatment: Mapping[str, float], control: Mapping[str, float]) -> list[str]:
    if set(treatment) != set(control):
        raise StatisticsError("Treatment and control must cover the same queries")
    return sorted(treatment)


def paired_bootstrap_ci(
    treatment: Mapping[str, float],
    control: Mapping[str, float],
    *,
    resamples: int = PROTOCOL_RESAMPLES,
    seed: int = PROTOCOL_SEED,
    level: float = PROTOCOL_LEVEL,
    groups: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Paired percentile CI for mean(treatment - control).

    ``groups`` maps query_id -> group_id (default: every query is its own
    group = singleton rule in the protocol). Resampling draws groups with
    replacement, including all member queries, then recomputes the query macro.
    """
    if not isinstance(resamples, int) or isinstance(resamples, bool) or resamples < 100:
        raise StatisticsError(f"resamples must be an integer >= 100, got {resamples!r}")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise StatisticsError(f"seed must be an integer, got {seed!r}")
    if not (0.0 < level < 1.0) or not math.isfinite(level):
        raise StatisticsError(f"level must be in (0, 1), got {level!r}")
    t = _require_metric_values(treatment, "treatment")
    c = _require_metric_values(control, "control")
    qids = _check_paired(t, control)
    if groups is not None:
        missing = [q for q in qids if q not in groups]
        if missing:
            raise StatisticsError(f"groups missing {len(missing)} queries")
        gmap: dict[str, list[str]] = {}
        for q in qids:
            gmap.setdefault(str(groups[q]), []).append(q)
        group_members = [gmap[g] for g in sorted(gmap)]
    else:
        group_members = [[q] for q in qids]
    diffs = np.array([t[q] - c[q] for q in qids], dtype=np.float64)
    qindex = {q: i for i, q in enumerate(qids)}
    members_idx = [[qindex[q] for q in members] for members in group_members]
    rng = np.random.default_rng(seed)
    n_groups = len(members_idx)
    boot = np.empty(resamples, dtype=np.float64)
    for b in range(resamples):
        picks = rng.integers(0, n_groups, size=n_groups)
        vals = [diffs[i] for p in picks for i in members_idx[p]]
        boot[b] = float(sum(vals) / len(vals))
    alpha = 1.0 - level
    lo = float(np.quantile(boot, alpha / 2, method="linear"))
    hi = float(np.quantile(boot, 1.0 - alpha / 2, method="linear"))
    mean_t = float(sum(t[q] for q in qids) / len(qids))
    mean_c = float(sum(c[q] for q in qids) / len(qids))
    delta = mean_t - mean_c
    relative = (delta / mean_c) if mean_c != 0.0 else None
    return {
        "n_queries": len(qids),
        "n_groups": n_groups,
        "resamples": resamples,
        "seed": seed,
        "level": level,
        "mean_treatment": mean_t,
        "mean_control": mean_c,
        "delta_absolute": delta,
        "delta_relative": relative,
        "ci_low": lo,
        "ci_high": hi,
        "ci_excludes_zero": bool(lo > 0.0 or hi < 0.0),
        "bootstrap_mean": float(boot.mean()),
    }


def ndcg_at_10(order: Sequence[str], rel: Mapping[str, int]) -> float:
    """Linear-gain nDCG@10 (same definition as the SG-008 evaluator)."""
    ideal = sorted((int(g) for g in rel.values()), reverse=True)
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal[:10]))
    if idcg == 0:
        raise StatisticsError("Query without positives has undefined nDCG")
    dcg = sum((2 ** rel[d] - 1) / math.log2(i + 2) for i, d in enumerate(order[:10]) if d in rel)
    return dcg / idcg
