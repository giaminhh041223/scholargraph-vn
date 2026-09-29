"""Reranking integration: text RRF + graph + age on a FIXED C100 — SG-025.

Pipeline per query (Protocol §5.4, configs in SG-020/023/024):

1. Inputs: RRF rows ``[{doc_id, rrf}]`` (SG-020), graph scores ``{doc_id:
   ppr|global}`` (SG-022/023), publication years + source year (SG-024).
2. Per-query min-max normalization of each signal (constant vector → all 0,
   reported, never divided by zero).
3. ``F = (1-gamma) × norm(RRF) + gamma × norm(graph)``,
   ``gamma ∈ {0, 0.1, 0.2, 0.3}``. Missing graph scores become 0 with an
   explicit count + reason (never silent).
4. Optional age variant ``F_age`` (SG-024, explicit lambda + years).
5. Output is EXACTLY the input C100 set, reranked. No universe change, no
   expansion, no self-recommendation (query source in C100 is a loud error,
   never silently dropped). Component scores + graph evidence (graph hash,
   seed hash, gamma, lambda) travel with every row for ablation (SG-029).

Leakage contract: ranker-side. Qrels/labels/held-out edges forbidden via
``BaseRanker``. Evaluator-side metric computation lives elsewhere.

Failure contract (ADR-013/014): C100/set mismatches, duplicates, self-hits,
empty inputs, unknown gamma, non-finite scores, or missing years (when age
is requested) fail loudly; CLI exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.data.interfaces import BaseRanker
from scholargraph.graph.age_adjustment import AgeDataError, age_weight

MODULE_VERSION = "sg025-1.1.0"
SCHEMA_VERSION = 1
GAMMA_GRID = (0.0, 0.1, 0.2, 0.3)


class RerankDataError(Exception):
    """Fatal reranking input or config problem."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RerankDataError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _require_gamma(value: Any) -> float:
    g = _finite(value, "gamma")
    if g not in GAMMA_GRID:
        raise RerankDataError(f"gamma must be one of {list(GAMMA_GRID)}, got {value!r}")
    return g


def minmax_normalize(values: Mapping[str, float]) -> tuple[dict[str, float], bool]:
    """Per-query min-max to [0,1]; constant vectors become all-0 (reported)."""
    if not values:
        raise RerankDataError("Empty signal for normalization")
    for d, v in values.items():
        _finite(v, f"signal({d})")
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return ({d: 0.0 for d in values}, True)
    span = hi - lo
    return ({d: (v - lo) / span for d, v in values.items()}, False)


def rerank_query(
    c100: Sequence[str],
    rrf: Mapping[str, float],
    graph_scores: Mapping[str, float],
    gamma: float,
    query_source: str | None = None,
    graph_evidence: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fuse RRF + graph on exactly C100; returns (rows, diagnostics)."""
    g = _require_gamma(gamma)
    if not c100:
        raise RerankDataError("Empty C100")
    if len(set(c100)) != len(list(c100)):
        raise RerankDataError("Duplicate members in C100")
    if set(c100) != set(rrf.keys()):
        raise RerankDataError("RRF scores must cover exactly C100")
    if query_source is not None and query_source in set(c100):
        raise RerankDataError(f"Self-recommendation blocked: source {query_source} inside C100")
    missing = [d for d in c100 if d not in graph_scores]
    extra = [d for d in graph_scores if d not in set(c100)]
    nrrf, const_rrf = minmax_normalize({d: rrf[d] for d in c100})
    # Present-only normalization (documented): when only a subset of C100 has
    # graph scores, normalization is computed over the PRESENT subset; a single
    # present score is constant -> 0. Missing docs score 0 with count.
    present = {d: graph_scores[d] for d in c100 if d in graph_scores}
    if present:
        ngraph, const_graph = minmax_normalize(present)
    else:
        ngraph, const_graph = {}, True
    for d in missing:
        ngraph[d] = 0.0
    rows = []
    for d in c100:
        f = (1 - g) * nrrf[d] + g * ngraph[d]
        rows.append({"doc_id": d, "rrf": rrf[d], "graph": graph_scores.get(d),
                     "norm_rrf": nrrf[d], "norm_graph": ngraph[d], "fused": f,
                     "graph_evidence": dict(graph_evidence or {})})
    rows.sort(key=lambda r: (-r["fused"], r["doc_id"]))
    diag = {"gamma": g, "c100": len(c100), "missing_graph_scores": len(missing),
            "missing_reason": "docs absent from graph-score map score 0 with count" if missing else None,
            "extra_graph_keys_ignored": len(extra),
            "constant_rrf": const_rrf, "constant_graph": const_graph}
    return rows, diag


def apply_age_to_rows(
    rows: Sequence[Mapping[str, Any]],
    years: Mapping[str, int | None],
    year_source: int,
    lambda_: float,
) -> list[dict[str, Any]]:
    """Age variant on fused rows (SG-024 formula, explicit years)."""
    if not isinstance(year_source, int) or isinstance(year_source, bool):
        raise RerankDataError(f"Invalid year_source: {year_source!r}")
    base = []
    seen: set[str] = set()
    for r in rows:
        if not isinstance(r, Mapping) or "doc_id" not in r or "fused" not in r:
            raise RerankDataError(f"Invalid fused row (missing doc_id/fused): {r!r}")
        if r["doc_id"] in seen:
            raise RerankDataError(f"Duplicate doc in age input: {r['doc_id']}")
        seen.add(r["doc_id"])
        base.append({"doc_id": r["doc_id"], "fused": _finite(r["fused"], f"fused({r.get('doc_id')})")})
    if not base:
        raise RerankDataError("Empty rows for age variant")
    out = []
    for b in base:
        d = b["doc_id"]
        if d not in years or years[d] is None:
            raise RerankDataError(f"Missing publication year for {d} (never imputed)")
        yd = years[d]
        if isinstance(yd, bool) or not isinstance(yd, int):
            raise RerankDataError(f"Invalid publication year for {d}: {yd!r}")
        try:
            w = age_weight(year_source, yd, lambda_)
        except AgeDataError as exc:
            raise RerankDataError(f"Age computation failed for {d}: {exc}") from exc
        row = dict([ (k, v) for r in rows if r["doc_id"] == d for k, v in r.items() ])
        row.update({"age_weight": w, "fused_age": b["fused"] * w,
                    "age_gap": max(0, year_source - yd), "lambda": float(lambda_)})
        out.append(row)
    out.sort(key=lambda r: (-r["fused_age"], r["doc_id"]))
    return out


class HybridReranker(BaseRanker):
    """Leakage-guarded reranker (rank() rejects qrels/holdout kwargs)."""

    def __init__(self, gamma: float = 0.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        _require_gamma(gamma)
        self.gamma = gamma

    def _rank(self, query: Any, candidate_ids: Sequence[str] | None = None, **kwargs: Any) -> Any:
        rrf = kwargs.get("rrf")
        graph_scores = kwargs.get("graph_scores")
        if rrf is None or graph_scores is None:
            raise RerankDataError("HybridReranker requires rrf + graph_scores maps")
        c100 = list(candidate_ids) if candidate_ids is not None else sorted(rrf.keys())
        rows, _ = rerank_query(c100, rrf, graph_scores, self.gamma,
                               query_source=kwargs.get("query_source"),
                               graph_evidence=kwargs.get("graph_evidence"))
        return rows


def _load(path: str) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RerankDataError(f"Missing required file: {path}")
    except OSError as exc:
        raise RerankDataError(f"Cannot read file {path}: {exc}")
    def _no_const(value: str) -> Any:
        raise RerankDataError(f"Invalid JSON constant in {path}: {value}")
    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise RerankDataError(f"Duplicate JSON key in {path}: {k!r}")
            out[k] = v
        return out
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_const)
    except json.JSONDecodeError as exc:
        raise RerankDataError(f"Malformed JSON in {path}: {exc}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reranking integration (SG-025)")
    p.add_argument("--c100", required=True, help="JSON query_id -> [doc_ids]")
    p.add_argument("--rrf", required=True, help="JSON query_id -> {doc_id: rrf}")
    p.add_argument("--graph-scores", required=True, help="JSON query_id -> {doc_id: graph_score}")
    p.add_argument("--gamma", type=float, required=True)
    p.add_argument("--graph-kind", required=True, choices=["ppr", "global"])
    p.add_argument("--source-map", default=None, help="Optional JSON query_id -> source doc_id (self-recommendation guard)")
    p.add_argument("--years", default=None, help="Optional JSON doc_id -> year for the age variant")
    p.add_argument("--query-years", default=None, help="Optional JSON query_id -> source year (with --years)")
    p.add_argument("--lambda", dest="lambda_", type=float, default=None, help="Optional age lambda (with --years)")
    p.add_argument("--output", required=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        c100, rrf, gs = _load(args.c100), _load(args.rrf), _load(args.graph_scores)
        if not (isinstance(c100, dict) and isinstance(rrf, dict) and isinstance(gs, dict)):
            raise RerankDataError("Inputs must be JSON objects")
        if not (set(c100) == set(rrf) == set(gs)):
            raise RerankDataError("C100/RRF/graph-scores must cover the same queries")
        sources = _load(args.source_map) if args.source_map else {}
        if not isinstance(sources, dict):
            raise RerankDataError("--source-map must be a JSON object")
        use_age = args.years is not None or args.query_years is not None or args.lambda_ is not None
        if use_age and not (args.years and args.query_years and args.lambda_ is not None):
            raise RerankDataError("--years/--query-years/--lambda must be given together")
        years = _load(args.years) if args.years else {}
        qyears = _load(args.query_years) if args.query_years else {}
        queries = {}
        for qid in sorted(c100):
            rows, diag = rerank_query(c100[qid], rrf[qid], gs[qid], args.gamma,
                                      query_source=sources.get(qid),
                                      graph_evidence={"graph_kind": args.graph_kind})
            entry: dict[str, Any] = {"rows": rows, "diagnostics": diag}
            if use_age:
                if qid not in qyears:
                    raise RerankDataError(f"Query {qid} missing from --query-years")
                entry["rows_age"] = apply_age_to_rows(rows, years, qyears[qid], args.lambda_)
            queries[qid] = entry
        def _sha(p: str) -> str:
            return hashlib.sha256(Path(p).read_bytes()).hexdigest()
        payload = {"schema_version": SCHEMA_VERSION, "module_version": MODULE_VERSION,
                   "task_id": "SG-025", "generated_at": datetime.now(timezone.utc).isoformat(),
                   "gamma": _require_gamma(args.gamma), "graph_kind": args.graph_kind,
                   "lambda": args.lambda_,
                   "inputs": {"c100": {"path": args.c100, "sha256": _sha(args.c100)},
                              "rrf": {"path": args.rrf, "sha256": _sha(args.rrf)},
                              "graph_scores": {"path": args.graph_scores, "sha256": _sha(args.graph_scores)},
                              "qrels_used": False},
                   "config_hash": hashlib.sha256(json.dumps({"gamma": args.gamma, "graph_kind": args.graph_kind, "lambda": args.lambda_}, sort_keys=True).encode()).hexdigest(),
                   "queries": queries}
        outp = Path(args.output)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(outp), "queries": len(queries)}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
