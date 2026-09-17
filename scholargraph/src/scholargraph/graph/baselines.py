"""Graph baselines on the masked citation graph — task SG-022.

Computes, exclusively from ``G_mask`` (``data/processed/graph/
adjacency_masked.tsv`` produced by SG-016):

- Global PageRank with uniform teleport (popularity diagnostic, Protocol §5.3):
  ``p(t+1) = 0.85 P^T p(t) + 0.15 v`` with row-normalized ``P`` over the valid
  graph, dangling rows replaced by ``v``, ``p(0) = v``. Converges when
  ``||p(t+1)-p(t)||_1 < 1e-8`` (max 200 iterations); non-convergence is a run
  failure, never silently accepted.
- Bibliographic coupling baseline: ``coupling(u,v) = |out(u) ∩ out(v)|``
  (shared references) plus Jaccard variant; undirected similarity for
  related-paper control, computed on masked out-neighborhoods only.
- Popularity/coverage audit: isolated/dangling counts, score concentration
  (top-1% share), overlap of PageRank top-K with high in-degree nodes.

Leakage contract: only the masked adjacency is read. Holdout/mask edge lists
and qrels are never opened here.

Failure contract (ADR-013/014): missing/empty graph, malformed lines,
duplicate edges, unknown nodes in queries, or non-convergence fail loudly;
CLI exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_VERSION = "sg022-1.1.0"
SCHEMA_VERSION = 1
DAMPING = 0.85
TOL_L1 = 1e-8
MAX_ITER = 200


class GraphDataError(Exception):
    """Fatal graph-baseline input or computation problem."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GraphDataError(f"Missing required file: {path}")
    except OSError as exc:
        raise GraphDataError(f"Cannot read file {path}: {exc}")


def load_masked_adjacency(
    path: Path,
    universe: Sequence[str] | None = None,
) -> tuple[list[str], dict[str, set[str]]]:
    """Load directed masked adjacency; returns (sorted nodes, out-neighbors).

    The TSV only materializes edge-incident nodes. When the full masked-graph
    node universe (e.g. 18.251 works incl. isolated) is passed, isolated nodes
    are added with empty out-sets instead of being silently dropped.
    """
    out: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    for lineno, line in enumerate(_read_text(path).splitlines(), start=1):
        if not line.strip():
            raise GraphDataError(f"Blank line {lineno} in {path} (rejected)")
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise GraphDataError(f"Malformed adjacency line {lineno} in {path}")
        u, v = parts
        if (u, v) in seen:
            raise GraphDataError(f"Duplicate edge line {lineno}: {u} -> {v}")
        seen.add((u, v))
        out.setdefault(u, set()).add(v)
        out.setdefault(v, set())
    if not out and universe is None:
        raise GraphDataError(f"Empty graph: {path}")
    if universe is not None:
        if len(set(universe)) != len(list(universe)):
            raise GraphDataError("Node universe contains duplicates")
        for v in universe:
            out.setdefault(v, set())
    if not out:
        raise GraphDataError(f"Empty graph: {path}")
    return sorted(out), out


def load_node_universe_from_degrees(path: Path, expected_edges: int | None = None) -> list[str]:
    """Node universe from SG-016 degree features (covers isolated nodes)."""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GraphDataError(f"Missing required file: {path}")
    except json.JSONDecodeError as exc:
        raise GraphDataError(f"Malformed JSON in {path}: {exc}")
    if not isinstance(obj, dict) or "in_degree" not in obj or "out_degree" not in obj:
        raise GraphDataError(f"Degree file lacks in_degree/out_degree: {path}")
    if set(obj["in_degree"]) != set(obj["out_degree"]):
        raise GraphDataError(f"In/out degree key mismatch in {path}")
    if expected_edges is not None and obj.get("edge_count") != expected_edges:
        raise GraphDataError(f"Degree file edge_count {obj.get('edge_count')} != expected {expected_edges}")
    return sorted(obj["in_degree"])


def global_pagerank(
    nodes: Sequence[str],
    out_links: Mapping[str, set[str]],
    damping: float = DAMPING,
    tol: float = TOL_L1,
    max_iter: int = MAX_ITER,
) -> tuple[dict[str, float], int, float]:
    """Uniform-teleport PageRank; returns (scores, iterations, residual)."""
    if not nodes:
        raise GraphDataError("Empty node set")
    if not 0.0 < damping < 1.0:
        raise GraphDataError(f"Invalid damping: {damping}")
    n = len(nodes)
    index = {v: i for i, v in enumerate(nodes)}
    for v in nodes:
        if v not in out_links:
            raise GraphDataError(f"Node missing from adjacency map: {v}")
        for w in out_links[v]:
            if w not in index:
                raise GraphDataError(f"Unknown edge target: {v} -> {w}")
    out_deg = {v: len(out_links[v]) for v in nodes}
    rank = [1.0 / n] * n
    teleport = [(1.0 - damping) / n] * n
    iters = 0
    residual = float("inf")
    for it in range(1, max_iter + 1):
        new = list(teleport)
        dangling_sum = sum(rank[index[v]] for v in nodes if out_deg[v] == 0)
        for v in nodes:
            if out_deg[v] == 0:
                continue
            share = damping * rank[index[v]] / out_deg[v]
            for w in out_links[v]:
                new[index[w]] += share
        if dangling_sum:
            add = damping * dangling_sum / n
            for i in range(n):
                new[i] += add
        residual = sum(abs(new[i] - rank[i]) for i in range(n))
        rank = new
        iters = it
        if residual < tol:
            break
    else:
        raise GraphDataError(f"PageRank did not converge in {max_iter} iterations (residual {residual})")
    total = sum(rank)
    if total <= 0:
        raise GraphDataError("PageRank produced non-positive mass")
    return ({v: rank[index[v]] / total for v in nodes}, iters, residual)


def bibliographic_coupling(
    u: str,
    v: str,
    out_links: Mapping[str, set[str]],
) -> dict[str, Any]:
    """Coupling between two nodes on masked out-neighborhoods.

    Convention (documented, not a measurement): when both nodes have no
    references (union == 0) Jaccard is undefined (0/0) and reported as 0.0.
    """
    if u not in out_links:
        raise GraphDataError(f"Unknown node: {u}")
    if v not in out_links:
        raise GraphDataError(f"Unknown node: {v}")
    ou, ov = out_links[u], out_links[v]
    inter = len(ou & ov)
    union = len(ou | ov)
    return {"u": u, "v": v, "shared_references": inter,
            "jaccard": (inter / union) if union else 0.0,
            "jaccard_note": "0.0 when union==0 is a documented convention (undefined 0/0), not a measured zero." if not union else None,
            "out_degree_u": len(ou), "out_degree_v": len(ov)}


def rank_candidates_by_global(
    scores: Mapping[str, float],
    candidate_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Order a fixed candidate set by global PageRank (same graph/candidates rule)."""
    if not candidate_ids:
        raise GraphDataError("Empty candidate set")
    seen: set[str] = set()
    rows = []
    for c in candidate_ids:
        if c in seen:
            raise GraphDataError(f"Duplicate candidate: {c}")
        seen.add(c)
        if c not in scores:
            raise GraphDataError(f"Candidate outside masked graph: {c} (fallback: report, never invent score)")
        rows.append({"doc_id": c, "global_pagerank": scores[c]})
    rows.sort(key=lambda r: (-r["global_pagerank"], r["doc_id"]))
    return rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Graph baselines on masked graph (SG-022)")
    p.add_argument("--adjacency", required=True, help="Masked adjacency TSV (u<TAB>v)")
    p.add_argument("--node-degrees", default=None,
                   help="SG-016 degree features JSON for the full node universe (incl. isolated)")
    p.add_argument("--output", required=True, help="Baseline report JSON")
    p.add_argument("--top-k", type=int, default=100)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.top_k <= 0:
            raise GraphDataError(f"Invalid --top-k: {args.top_k}")
        adj = Path(args.adjacency)
        tsv_edges = sum(1 for line in adj.read_text(encoding="utf-8").splitlines() if line.strip()) if adj.is_file() else 0
        universe = None
        node_degrees_info = None
        if args.node_degrees:
            deg_path = Path(args.node_degrees)
            universe = load_node_universe_from_degrees(deg_path, expected_edges=tsv_edges)
            deg_obj = json.loads(deg_path.read_text(encoding="utf-8"))
            node_degrees_info = {"path": str(deg_path),
                                 "sha256": hashlib.sha256(deg_path.read_bytes()).hexdigest(),
                                 "edge_count": deg_obj.get("edge_count")}
        nodes, out_links = load_masked_adjacency(adj, universe)
        scores, iters, residual = global_pagerank(nodes, out_links)
        if args.top_k > len(nodes):
            raise GraphDataError(f"--top-k {args.top_k} exceeds node count {len(nodes)}")
        dangling = sum(1 for v in nodes if not out_links[v])
        indeg: dict[str, int] = {v: 0 for v in nodes}
        for v in nodes:
            for w in out_links[v]:
                indeg[w] += 1
        ordered = sorted(scores, key=lambda v: (-scores[v], v))
        top = ordered[: args.top_k]
        top_mass = sum(scores[v] for v in top)
        top_indeg = sorted(nodes, key=lambda v: (-indeg[v], v))[: args.top_k]
        overlap = len(set(top) & set(top_indeg)) / args.top_k
        report = {
            "schema_version": SCHEMA_VERSION, "module_version": MODULE_VERSION,
            "task_id": "SG-022", "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {"adjacency": str(adj), "sha256": hashlib.sha256(adj.read_bytes()).hexdigest(),
                         "node_degrees": node_degrees_info,
                         "qrels_used": False,
                         "command": ["--adjacency", str(adj)] + (["--node-degrees", str(args.node_degrees)] if args.node_degrees else []) + ["--output", str(args.output), "--top-k", str(args.top_k)]},
            "graph": {"nodes": len(nodes), "edges": sum(len(s) for s in out_links.values()),
                      "dangling_nodes": dangling,
                      "isolated_nodes": sum(1 for v in nodes if not out_links[v] and indeg[v] == 0)},
            "pagerank": {"damping": DAMPING, "tol_l1": TOL_L1, "max_iter": MAX_ITER,
                         "iterations": iters, "residual": residual,
                         "mass": sum(scores.values())},
            "popularity_audit": {f"top_{args.top_k}_mass_share": top_mass,
                                 f"top_{args.top_k}_indeg_overlap": overlap},
            "fallback_policy": "Candidates outside the masked graph are reported as errors, never scored 0 silently.",
        }
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(out), "nodes": len(nodes), "iterations": iters}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
