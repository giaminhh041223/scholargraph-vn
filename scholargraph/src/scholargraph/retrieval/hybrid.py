"""Hybrid Reciprocal Rank Fusion (RRF) — task SG-020.

Contract (docs/TASKS.md SG-020, configs/protocol_v1.json -> retrieval.rrf,
configs/hybrid.json):

- ``RRF(d) = sum_m 1/(k + rank_m(d))`` with ``k=60``, ranks starting at 1.
  Document absent from a component top-k contributes 0. Equal weights.
- Inputs are two rank orders (lexical BM25 top-100, dense top-100); union max
  200, output top-100 fused. Canonical order: fused score descending, ties
  broken by canonical doc ID ascending (Unicode code points). Deterministic.
- Leakage boundary: fusion reads only component rank orders. Qrels/labels or
  held-out edges are forbidden (``BaseRanker`` raises ``DataLeakageError``).
- No silent bypass: missing config fields, non-finite scores (if score inputs
  are given), duplicate doc IDs, non-positive ranks, or empty union all fail
  loudly; CLI exits 1. Nothing unmeasured is replaced by 0 except the
  protocol-defined missing-component contribution (document absent from one
  list contributes exactly 0 to that component, per protocol).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.data.interfaces import BaseRanker, DataLeakageError

MODULE_VERSION = "sg020-1.0.0"
SCHEMA_VERSION = 1


class HybridDataError(Exception):
    """Raised for any fatal hybrid/RRF input or config problem."""


def _load_strict_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HybridDataError(f"Missing required file: {path}")
    except OSError as exc:
        raise HybridDataError(f"Cannot read file {path}: {exc}")
    def _no_nan(value: str) -> Any:
        raise HybridDataError(f"Invalid JSON constant in {path}: {value}")
    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise HybridDataError(f"Duplicate JSON key in {path}: {k!r}")
            out[k] = v
        return out
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_nan)
    except json.JSONDecodeError as exc:
        raise HybridDataError(f"Malformed JSON in {path}: {exc}")


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise HybridDataError(f"Missing required field {key!r} in {where}")
    return mapping[key]


def load_hybrid_config(config_path: Path | str = "configs/hybrid.json") -> dict[str, Any]:
    path = Path(config_path)
    cfg = _load_strict_json(path)
    if not isinstance(cfg, dict):
        raise HybridDataError(f"Hybrid config must be a JSON object: {path}")
    rrf = _require(cfg, "rrf", str(path))
    if not isinstance(rrf, dict):
        raise HybridDataError("Hybrid config 'rrf' must be an object")
    k = _require(rrf, "k", "rrf")
    if not isinstance(k, int) or k != 60:
        raise HybridDataError(f"Protocol RRF k must be exactly 60, got {k!r}")
    if _require(rrf, "rank_origin", "rrf") != 1:
        raise HybridDataError("Protocol rank_origin must be 1")
    if _require(rrf, "missing_contribution", "rrf") != 0:
        raise HybridDataError("Protocol missing_contribution must be 0")
    if _require(rrf, "equal_weights", "rrf") is not True:
        raise HybridDataError("Protocol equal_weights must be true")
    depths = _require(cfg, "depths", str(path))
    per = _require(depths, "per_retriever_depth", "depths")
    union_max = _require(depths, "union_maximum", "depths")
    final = _require(depths, "final_depth", "depths")
    if not (isinstance(per, int) and per == 100):
        raise HybridDataError(f"per_retriever_depth must be 100, got {per!r}")
    if not (isinstance(union_max, int) and union_max == 200):
        raise HybridDataError(f"union_maximum must be 200, got {union_max!r}")
    if not (isinstance(final, int) and final == 100):
        raise HybridDataError(f"final_depth must be 100, got {final!r}")
    return cfg


def _validate_rank_list(doc_ids: Sequence[Any], name: str) -> list[str]:
    if not isinstance(doc_ids, (list, tuple)):
        raise HybridDataError(f"{name} must be a list of doc IDs")
    if len(doc_ids) == 0:
        raise HybridDataError(f"{name} must not be empty (at least 1 candidate)")
    if len(doc_ids) > 100:
        raise HybridDataError(f"{name} exceeds per-retriever depth 100 (got {len(doc_ids)})")
    seen: set[str] = set()
    out: list[str] = []
    for d in doc_ids:
        if not isinstance(d, str) or not d:
            raise HybridDataError(f"{name} contains invalid doc ID: {d!r}")
        if d in seen:
            raise HybridDataError(f"{name} contains duplicate doc ID: {d!r}")
        seen.add(d)
        out.append(d)
    return out


def rrf_fuse(
    lexical_rank: Sequence[str],
    dense_rank: Sequence[str],
    k: int = 60,
    final_depth: int = 100,
) -> list[dict[str, Any]]:
    """Fuse two rank orders with RRF; returns ranked rows with component info."""
    if not isinstance(k, int) or k != 60:
        raise HybridDataError(f"RRF k must be 60, got {k!r}")
    lex = _validate_rank_list(lexical_rank, "lexical_rank")
    den = _validate_rank_list(dense_rank, "dense_rank")
    lex_pos = {d: i + 1 for i, d in enumerate(lex)}
    den_pos = {d: i + 1 for i, d in enumerate(den)}
    union = list(dict.fromkeys([*lex, *den]))
    if len(union) > 200:
        raise HybridDataError(f"Union exceeds maximum 200 (got {len(union)})")
    rows: list[dict[str, Any]] = []
    for d in union:
        rl = lex_pos.get(d)
        rd = den_pos.get(d)
        score = (1.0 / (k + rl) if rl is not None else 0.0) + (1.0 / (k + rd) if rd is not None else 0.0)
        if not math.isfinite(score):
            raise HybridDataError(f"Non-finite RRF score for {d!r}")
        rows.append({"doc_id": d, "rrf": score, "rank_lexical": rl, "rank_dense": rd})
    rows.sort(key=lambda r: (-r["rrf"], r["doc_id"]))
    return rows[:final_depth]


class HybridRRFRanker(BaseRanker):
    """Ranker wrapper enforcing the leakage boundary for RRF fusion."""

    def __init__(self, k: int = 60, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if k != 60:
            raise HybridDataError(f"RRF k must be 60, got {k!r}")
        self.k = k

    def _rank(
        self,
        query: Any,
        candidate_ids: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        lexical_rank = kwargs.get("lexical_rank")
        dense_rank = kwargs.get("dense_rank")
        if lexical_rank is None or dense_rank is None:
            raise HybridDataError("HybridRRFRanker requires lexical_rank and dense_rank rank orders")
        return rrf_fuse(lexical_rank, dense_rank, k=self.k)


def fuse_query_file(
    lexical_path: Path,
    dense_path: Path,
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    cfg = load_hybrid_config(config_path)
    k = int(cfg["rrf"]["k"])
    final_depth = int(cfg["depths"]["final_depth"])
    lex_data = _load_strict_json(lexical_path)
    den_data = _load_strict_json(dense_path)
    if not isinstance(lex_data, dict) or not isinstance(den_data, dict):
        raise HybridDataError("Input rank files must be JSON objects query_id -> [doc_ids]")
    if set(lex_data.keys()) != set(den_data.keys()):
        raise HybridDataError("Lexical and dense inputs must cover the same query IDs")
    fused: dict[str, Any] = {}
    for qid in sorted(lex_data.keys()):
        rows = rrf_fuse(lex_data[qid], den_data[qid], k=k, final_depth=final_depth)
        fused[qid] = rows
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "task_id": "SG-020",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
        "rrf_k": k,
        "queries": fused,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": str(output_path), "queries": len(fused)}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Hybrid RRF fusion (SG-020)")
    p.add_argument("--lexical", required=True, help="JSON query_id -> [doc_ids] lexical top-k")
    p.add_argument("--dense", required=True, help="JSON query_id -> [doc_ids] dense top-k")
    p.add_argument("--config", default="configs/hybrid.json")
    p.add_argument("--output", required=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = fuse_query_file(Path(args.lexical), Path(args.dense), Path(args.config), Path(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
