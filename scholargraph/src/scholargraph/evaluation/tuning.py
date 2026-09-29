"""Dev tuning registry and selection — task SG-026 (Protocol §8.1).

- Search spaces are FROZEN in ``configs/tuning_space.json``: track B grid is
  exactly gamma {0, 0.1, 0.2, 0.3} × lambda {0, 0.01, 0.03, 0.05, 0.1}
  (20 trials); track A uses fixed defaults (no grid search); track C uses
  three fixed methods (no relevance grid).
- Selection uses DEV metrics only, primary nDCG@10. Ties go to the smaller
  gamma, then smaller lambda (B) or lexicographic config ID (A/C).
- FAILED trials stay in the registry with errors + costs and are excluded
  from selection with an explicit count — never silently dropped, never
  selected. Any test-set metric in a trial registry is rejected (no test
  peeking): tuning reads dev only.

Failure contract (ADR-013/014): empty registries, all-failed grids, duplicate
trial IDs, missing fields, or test metrics fail loudly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_VERSION = "sg026-1.1.0"
PRIMARY_METRIC = "nDCG@10"
GAMMA_GRID = (0.0, 0.1, 0.2, 0.3)
LAMBDA_GRID = (0.0, 0.01, 0.03, 0.05, 0.1)


class TuningDataError(Exception):
    """Fatal tuning registry or selection problem."""


REQUIRED_TRIAL_FIELDS = ("trial_id", "track", "config", "status")


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise TuningDataError(f"Missing required field {key!r} in {where}")
    return mapping[key]


def load_registry(path: Path | str) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TuningDataError(f"Missing trial registry: {path}")
    except json.JSONDecodeError as exc:
        raise TuningDataError(f"Malformed registry {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("trials"), list):
        raise TuningDataError(f"Registry must be an object with a trials list: {path}")
    trials = data["trials"]
    if not trials:
        raise TuningDataError(f"Empty trial registry: {path}")
    seen: set[str] = set()
    for t in trials:
        if not isinstance(t, dict):
            raise TuningDataError(f"Invalid trial entry: {t!r}")
        for f in REQUIRED_TRIAL_FIELDS:
            _require(t, f, f"trial {t.get('trial_id')}")
        tid = t["trial_id"]
        if tid in seen:
            raise TuningDataError(f"Duplicate trial_id: {tid}")
        seen.add(tid)
        metrics = t.get("metrics") or {}
        for k in metrics:
            if str(k).startswith("test"):
                raise TuningDataError(f"Test metric {k!r} in trial {tid}: tuning reads dev only")
        if t["status"] not in ("COMPLETED", "FAILED"):
            raise TuningDataError(f"Trial {tid} has invalid status {t['status']!r}")
        if t["status"] == "COMPLETED" and PRIMARY_METRIC not in metrics:
            raise TuningDataError(f"Completed trial {tid} lacks primary metric {PRIMARY_METRIC}")
        if t.get("track") == "B" and t["status"] == "COMPLETED":
            cfg = t.get("config")
            if not isinstance(cfg, dict) or cfg.get("gamma") not in GAMMA_GRID or cfg.get("lambda") not in LAMBDA_GRID:
                raise TuningDataError(f"Trial {tid} off the frozen B grid: {cfg!r}")
    return trials


def _sort_key(trial: Mapping[str, Any]) -> tuple:
    m = trial["metrics"]
    cfg = trial.get("config", {})
    gamma = cfg.get("gamma", 0.0)
    lamb = cfg.get("lambda", 0.0)
    return (-float(m[PRIMARY_METRIC]), float(gamma), float(lamb), str(trial["trial_id"]))


def select_best(trials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Select the winning COMPLETED trial; report excluded FAILED count.

    Final tie-break is lexicographic ``trial_id``; for track C, trial IDs MUST
    equal the method/config IDs so this implements the protocol's
    config-ID-lexicographic rule. Optional ``cost_seconds``/``latency_ms``
    fields are carried through for SG-040 tracking but never select on.
    """
    done = [t for t in trials if t["status"] == "COMPLETED"]
    failed = [t for t in trials if t["status"] == "FAILED"]
    if not done:
        raise TuningDataError(f"No COMPLETED trials ({len(failed)} failed); refusing to select")
    best = sorted(done, key=_sort_key)[0]
    return {"best_trial_id": best["trial_id"], "best_config": best.get("config"),
            PRIMARY_METRIC: best["metrics"][PRIMARY_METRIC],
            "completed": len(done), "failed_excluded": len(failed),
            "failed_ids": [t["trial_id"] for t in failed]}


def validate_space(space: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the frozen tuning space (12-20 light configs for B)."""
    b = _require(space, "track_B_grid", "tuning space")
    if not isinstance(b, list) or not 12 <= len(b) <= 20:
        raise TuningDataError(f"Track B grid must hold 12-20 configs, got {len(b) if isinstance(b, list) else type(b)}")
    seen = set()
    for c in b:
        key = (c.get("gamma"), c.get("lambda"))
        if key in seen:
            raise TuningDataError(f"Duplicate B grid point: {key}")
        seen.add(key)
        if c.get("gamma") not in GAMMA_GRID or c.get("lambda") not in LAMBDA_GRID:
            raise TuningDataError(f"B grid point outside protocol grid: {c}")
    a = _require(space, "track_A", "tuning space")
    if not isinstance(a, dict) or a.get("policy") != "fixed_defaults_no_grid_search":
        raise TuningDataError("Track A must be pinned fixed_defaults_no_grid_search")
    if not isinstance(a.get("configs"), list) or not a["configs"]:
        raise TuningDataError("Track A needs a non-empty frozen config list")
    c = _require(space, "track_C", "tuning space")
    if not isinstance(c, dict) or c.get("policy") != "three_fixed_methods_no_relevance_grid":
        raise TuningDataError("Track C must be pinned three_fixed_methods_no_relevance_grid")
    if sorted(c.get("configs", [])) != ["multilingual_dense", "translated_bm25", "vn_hybrid_rrf"]:
        raise TuningDataError(f"Track C must be exactly the protocol section-7 pool trio, got {c.get('configs')}")
    sel = _require(space, "selection", "tuning space")
    if sel.get("primary") != "dev nDCG@10" or sel.get("test_use") != "forbidden_for_selection":
        raise TuningDataError("Selection must be dev-nDCG@10 primary with test forbidden")
    return {"b_trials": len(b), "status": "frozen"}
