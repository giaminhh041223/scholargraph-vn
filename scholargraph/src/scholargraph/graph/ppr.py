"""Personalized PageRank over the masked citation graph — task SG-023.

Protocol §5.3 (configs/ppr.json): ``p(t+1) = 0.85 P^T p(t) + 0.15 v``,
``p(0) = v``, row-normalized ``P`` on ``G_mask``, dangling rows replaced by
``v``. Teleport ``v(d) = RRF(d)/Σ_seed RRF`` over the top-20 text seeds,
0 elsewhere. Converge at L1 < 1e-8 (max 200); non-convergence is a run
failure. Expansion is OFF in core: propagation may traverse the valid graph
but the final output stays exactly C100. Cache identity
``(graph_hash, seed_hash, damping, tol)``.

Leakage contract: seeds come from text ranks only. Empty seeds are an input
failure — never synthesize seeds from qrels/labels. Only the masked
adjacency is read.

Failure contract (ADR-013/014): missing/empty inputs, unknown seed nodes,
non-positive seed weights, or non-convergence fail loudly; CLI exits 1.
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

from scholargraph.graph.baselines import (
    GraphDataError,
    load_masked_adjacency,
    load_node_universe_from_degrees,
)

MODULE_VERSION = "sg023-1.1.0"
SCHEMA_VERSION = 1
DAMPING = 0.85
TOL_L1 = 1e-8
MAX_ITER = 200
MAX_SEEDS = 20


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GraphDataError(f"Missing required file: {path}")
    except OSError as exc:
        raise GraphDataError(f"Cannot read file {path}: {exc}")


def build_teleport(
    seeds: Sequence[Mapping[str, Any]],
    universe: set[str],
) -> dict[str, float]:
    """Normalized teleport vector from RRF seed rows [{doc_id, rrf}]."""
    if not seeds:
        raise GraphDataError("Empty seed set (input failure; qrels fallback forbidden)")
    if len(seeds) > MAX_SEEDS:
        raise GraphDataError(f"Too many seeds: {len(seeds)} > {MAX_SEEDS}")
    weights: dict[str, float] = {}
    for s in seeds:
        if not isinstance(s, Mapping):
            raise GraphDataError(f"Invalid seed row: {s!r}")
        d = s.get("doc_id")
        w = s.get("rrf")
        if not isinstance(d, str) or not d:
            raise GraphDataError(f"Invalid seed doc_id: {d!r}")
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or not (w > 0):
            raise GraphDataError(f"Seed weight must be positive finite, got {w!r} for {d}")
        if d in weights:
            raise GraphDataError(f"Duplicate seed: {d}")
        if d not in universe:
            raise GraphDataError(f"Seed outside masked graph: {d}")
        weights[d] = float(w)
    total = sum(weights.values())
    if total <= 0:
        raise GraphDataError("Seed weights sum to non-positive mass")
    return {d: w / total for d, w in weights.items()}


def personalized_pagerank(
    nodes: Sequence[str],
    out_links: Mapping[str, set[str]],
    teleport: Mapping[str, float],
    damping: float = DAMPING,
    tol: float = TOL_L1,
    max_iter: int = MAX_ITER,
) -> tuple[dict[str, float], int, float]:
    """PPR with explicit teleport; returns (scores, iterations, residual)."""
    if not nodes:
        raise GraphDataError("Empty node set")
    if not teleport:
        raise GraphDataError("Empty teleport vector")
    if not 0.0 < damping < 1.0:
        raise GraphDataError(f"Invalid damping: {damping}")
    n = len(nodes)
    index = {v: i for i, v in enumerate(nodes)}
    for d in teleport:
        if d not in index:
            raise GraphDataError(f"Teleport node outside graph: {d}")
    t_mass = sum(teleport.values())
    if t_mass <= 0:
        raise GraphDataError("Teleport mass must be positive")
    v = [teleport.get(x, 0.0) / t_mass for x in nodes]
    out_deg = {x: len(out_links.get(x, set())) for x in nodes}
    for x in nodes:
        for w in out_links.get(x, set()):
            if w not in index:
                raise GraphDataError(f"Unknown edge target: {x} -> {w}")
    rank = list(v)
    iters, residual = 0, float("inf")
    for it in range(1, max_iter + 1):
        new = [(1.0 - damping) * vi for vi in v]
        dangling_sum = sum(rank[index[x]] for x in nodes if out_deg[x] == 0)
        for x in nodes:
            if out_deg[x] == 0:
                continue
            share = damping * rank[index[x]] / out_deg[x]
            for w in out_links[x]:
                new[index[w]] += share
        if dangling_sum:
            for i in range(n):
                new[i] += damping * dangling_sum * v[i]
        residual = sum(abs(new[i] - rank[i]) for i in range(n))
        rank = new
        iters = it
        if residual < tol:
            break
    else:
        raise GraphDataError(f"PPR did not converge in {max_iter} iterations (residual {residual})")
    total = sum(rank)
    if total <= 0:
        raise GraphDataError("PPR produced non-positive mass")
    return ({x: rank[index[x]] / total for x in nodes}, iters, residual)


def finalize_c100(
    c100: Sequence[str],
    ppr_scores: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Rerank exactly C100 by PPR (expansion OFF: same set, new order)."""
    if not c100:
        raise GraphDataError("Empty C100")
    seen: set[str] = set()
    rows = []
    for c in c100:
        if c in seen:
            raise GraphDataError(f"Duplicate C100 member: {c}")
        seen.add(c)
        if c not in ppr_scores:
            raise GraphDataError(f"C100 member outside PPR scores: {c}")
        rows.append({"doc_id": c, "ppr": ppr_scores[c]})
    rows.sort(key=lambda r: (-r["ppr"], r["doc_id"]))
    return rows


def seed_hash(seeds: Sequence[Mapping[str, Any]]) -> str:
    """Cache identity of the ORDERED seed rank list (rank order matters)."""
    rows = []
    for s in seeds:
        if not isinstance(s, Mapping) or "doc_id" not in s or "rrf" not in s:
            raise GraphDataError(f"Invalid seed row for hashing: {s!r}")
        rows.append({"doc_id": s["doc_id"], "rrf": s["rrf"]})
    canon = json.dumps(rows, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Personalized PageRank (SG-023)")
    p.add_argument("--adjacency", required=True)
    p.add_argument("--node-degrees", default=None)
    p.add_argument("--seeds", required=True, help="JSON query_id -> [{doc_id, rrf}] top-20 text seeds")
    p.add_argument("--c100", required=True, help="JSON query_id -> [doc_ids] fixed candidate set")
    p.add_argument("--output", required=True)
    return p


def _load_strict_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GraphDataError(f"Missing required file: {path}")
    except json.JSONDecodeError as exc:
        raise GraphDataError(f"Malformed JSON in {path}: {exc}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        adj = Path(args.adjacency)
        universe = load_node_universe_from_degrees(Path(args.node_degrees)) if args.node_degrees else None
        nodes, out_links = load_masked_adjacency(adj, universe)
        uni = set(nodes)
        seeds_data = _load_strict_json(Path(args.seeds))
        c100_data = _load_strict_json(Path(args.c100))
        if not isinstance(seeds_data, dict) or not isinstance(c100_data, dict):
            raise GraphDataError("Seeds/C100 files must be JSON objects")
        if set(seeds_data) != set(c100_data):
            raise GraphDataError("Seeds and C100 must cover the same queries")
        graph_hash = hashlib.sha256(adj.read_bytes()).hexdigest()
        deg_hash = hashlib.sha256(Path(args.node_degrees).read_bytes()).hexdigest() if args.node_degrees else None
        out_queries: dict[str, Any] = {}
        for qid in sorted(seeds_data):
            tel = build_teleport(seeds_data[qid], uni)
            scores, iters, residual = personalized_pagerank(nodes, out_links, tel)
            final = finalize_c100(c100_data[qid], scores)
            out_queries[qid] = {"seeds": len(tel), "seed_hash": seed_hash(seeds_data[qid]),
                                "iterations": iters, "residual": residual, "final": final}
        payload = {"schema_version": SCHEMA_VERSION, "module_version": MODULE_VERSION,
                   "task_id": "SG-023", "generated_at": datetime.now(timezone.utc).isoformat(),
                   "inputs": {"adjacency": str(adj), "graph_hash": graph_hash,
                              "node_degrees": {"path": str(args.node_degrees), "sha256": deg_hash} if deg_hash else None,
                              "qrels_used": False, "expansion": "off", "final_set": "C100"},
                   "queries": out_queries}
        outp = Path(args.output)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(outp), "queries": len(out_queries)}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
