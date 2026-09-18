"""Track-B warm-start citation pipeline — SG-026 dev trials / SG-028 final runs.

Per query source u (dev/test cohorts from the SG-016 masked split):

1. Universe U(u): valid-year works with year <= year(u), minus self and
   OBSERVED references O(u). Held-out H(u) stays (they are the labels).
2. Text query = title + abstract of u. BM25 top-100 + dense top-100 over U(u).
3. RRF k=60 -> C100. Seeds = top-20 RRF rows -> PPR on the cutoff subgraph
   (masked graph induced by year <= year(u)); global PageRank diagnostic.
4. Fusion F = (1-gamma)*norm(RRF) + gamma*norm(graph) for the frozen gamma
   grid, then age variants over the lambda grid (SG-024 formula).
5. Track-B evaluation against H(u) (ProtocolEvaluator, evaluator-side only).

Leakage contract: H(u) is NEVER in any candidate pool filter, seed, feature,
or text input — it enters only the evaluator. O(u)/self are excluded from
every baseline candidate list. Graph features come from G_mask + cutoff only.

Failure contract (ADR-013/014): any missing/malformed input, empty U(u)/C100/
seeds, unknown nodes, or non-convergence fails loudly; CLI exits 1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.data.schemas import RankedDocument, RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator
from scholargraph.graph.age_adjustment import apply_age
from scholargraph.graph.baselines import global_pagerank
from scholargraph.graph.ppr import build_teleport, finalize_c100, personalized_pagerank
from scholargraph.ingest.openalex import canonical_openalex_work_id
from scholargraph.retrieval.hybrid import rrf_fuse

MODULE_VERSION = "sg026b-1.0.0"
GAMMA_GRID = (0.0, 0.1, 0.2, 0.3)
LAMBDA_GRID = (0.0, 0.01, 0.03, 0.05, 0.1)


class BTrackDataError(Exception):
    """Fatal track-B pipeline problem."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BTrackDataError(f"Missing required file: {path}")


def load_works(path: Path) -> dict[str, dict[str, Any]]:
    """id -> {year, refs(raw list), title, abstract_text}."""
    works: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                raise BTrackDataError(f"Blank line {lineno} in {path}")
            try:
                o = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BTrackDataError(f"Malformed JSON line {lineno}: {exc}")
            raw = o.get("id")
            if not isinstance(raw, str) or not raw.strip():
                raise BTrackDataError(f"Missing id line {lineno}")
            cid = canonical_openalex_work_id(raw)
            if cid in works:
                raise BTrackDataError(f"Duplicate work {cid}")
            inv = o.get("abstract_inverted_index")
            if isinstance(inv, dict):
                words = sorted(((p, w) for w, ps in inv.items() for p in ps), key=lambda t: t[0])
                abstract = " ".join(w for _, w in words)
            else:
                abstract = ""
            refs = o.get("referenced_works")
            if refs is None:
                refs = []
            if not isinstance(refs, list):
                raise BTrackDataError(f"Bad referenced_works line {lineno}")
            works[cid] = {"year": o.get("publication_year"),
                          "refs": [str(r) for r in refs],
                          "title": str(o.get("title") or ""),
                          "abstract": abstract}
    if not works:
        raise BTrackDataError(f"Empty works file: {path}")
    return works


def load_holdout(path: Path) -> dict[str, list[str]]:
    """source -> [held-out targets] (canonical IDs, order preserved)."""
    h: dict[str, list[str]] = {}
    for lineno, line in enumerate(_read_text(path).splitlines(), start=1):
        if not line.strip():
            raise BTrackDataError(f"Blank line {lineno} in {path}")
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise BTrackDataError(f"Malformed holdout line {lineno}")
        h.setdefault(parts[0], []).append(parts[1])
    return h


def internal_refs(u: str, works: Mapping[str, dict[str, Any]], year_u: int) -> list[str]:
    """R(u): internal, non-self refs with year(v) <= year(u), deduped, order-kept."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in works[u]["refs"]:
        try:
            v = canonical_openalex_work_id(raw)
        except ValueError:
            continue  # unresolvable reference: unmapped, counted by caller
        if v == u or v in seen or v not in works:
            continue
        yv = works[v]["year"]
        if not isinstance(yv, int) or yv > year_u:
            continue
        seen.add(v)
        out.append(v)
    return out


def query_universe(u: str, works: Mapping[str, dict[str, Any]], year_u: int,
                   observed: set[str]) -> set[str]:
    """U(u): valid-year works year<=yu minus self and observed refs."""
    uni = {w for w, info in works.items()
           if isinstance(info["year"], int) and info["year"] <= year_u}
    uni.discard(u)
    uni -= observed
    if not uni:
        raise BTrackDataError(f"Empty universe for {u}")
    return uni


def fuse_c100(bm25_ids: Sequence[str], dense_ids: Sequence[str]) -> list[dict[str, Any]]:
    rows = rrf_fuse(list(bm25_ids), list(dense_ids), k=60, final_depth=100)
    if not rows:
        raise BTrackDataError("Empty C100 fusion")
    return rows


def cutoff_subgraph(nodes: Sequence[str], out_links: Mapping[str, set[str]],
                    years: Mapping[str, int | None], cutoff: int
                    ) -> tuple[list[str], dict[str, set[str]]]:
    """Induced subgraph of nodes with known year <= cutoff (both endpoints)."""
    keep = {v for v in nodes if isinstance(years.get(v), int) and years[v] <= cutoff}
    if not keep:
        raise BTrackDataError(f"Empty cutoff subgraph at {cutoff}")
    sub = {v: {w for w in out_links.get(v, set()) if w in keep} for v in keep}
    return sorted(keep), sub


def run_query(u: str, works: Mapping[str, dict[str, Any]],
              holdout: Mapping[str, list[str]],
              bm25_rank_fn: Any, dense_rank_fn: Any,
              masked_nodes: Sequence[str], masked_out: Mapping[str, set[str]],
              global_scores: Mapping[str, dict[int, dict[str, float]]],
              ) -> dict[str, Any]:
    """Full per-query pipeline returning C100 + PPR/global scores + sets."""
    info = works.get(u)
    if info is None:
        raise BTrackDataError(f"Unknown query source: {u}")
    yu = info["year"]
    if not isinstance(yu, int):
        raise BTrackDataError(f"Query {u} lacks a valid year")
    refs = internal_refs(u, works, yu)
    h = [v for v in holdout.get(u, []) if v in refs]
    if not h:
        raise BTrackDataError(f"Query {u} has no held-out refs inside R(u) — labels missing, refusing")
    observed = set(refs) - set(h)
    uni = query_universe(u, works, yu, observed)
    for v in h:
        if v not in uni:
            raise BTrackDataError(f"Held-out {v} outside universe of {u}")
    query_text = (info["title"] + " " + info["abstract"]).strip()
    if not query_text:
        raise BTrackDataError(f"Query {u} has empty text")
    bm25_ids = bm25_rank_fn(query_text, uni)
    dense_ids = dense_rank_fn(query_text, uni)
    c100_rows = fuse_c100(bm25_ids, dense_ids)
    c100 = [r["doc_id"] for r in c100_rows]
    if any(d not in uni for d in c100):
        raise BTrackDataError(f"C100 escapes universe for {u}")
    seeds = [{"doc_id": r["doc_id"], "rrf": r["rrf"]} for r in c100_rows[:20]]
    years = {w: works[w]["year"] for w in works}
    sub_nodes, sub_out = cutoff_subgraph(masked_nodes, masked_out, years, yu)
    uni_nodes = set(sub_nodes)
    if any(d not in uni_nodes for d in c100):
        missing = [d for d in c100 if d not in uni_nodes]
        raise BTrackDataError(f"C100 members outside cutoff graph for {u}: {missing[:3]}")
    tel = build_teleport(seeds, uni_nodes)
    ppr, p_iters, p_res = personalized_pagerank(sub_nodes, sub_out, tel)
    gscores = global_scores[yu]
    return {"query": u, "year": yu, "heldout": h, "observed": sorted(observed),
            "universe_size": len(uni), "c100": c100,
            "c100_rows": [{"doc_id": r["doc_id"], "rrf": r["rrf"]} for r in c100_rows],
            "ppr": {d: ppr[d] for d in c100}, "ppr_iters": p_iters, "ppr_residual": p_res,
            "global": {d: gscores[d] for d in c100}}


def fuse_variants(c100_rows: Sequence[Mapping[str, Any]], graph_scores: Mapping[str, float],
                  years: Mapping[str, int | None], year_u: int,
                  ) -> dict[str, list[dict[str, Any]]]:
    """All 20 (gamma, lambda) variants on fixed C100 (rerank.py semantics)."""
    from scholargraph.retrieval.rerank import rerank_query, apply_age_to_rows
    c100 = [r["doc_id"] for r in c100_rows]
    rrf = {r["doc_id"]: float(r["rrf"]) for r in c100_rows}
    out: dict[str, list[dict[str, Any]]] = {}
    for g in GAMMA_GRID:
        rows, _ = rerank_query(c100, rrf, graph_scores, g)
        for lam in LAMBDA_GRID:
            aged = apply_age_to_rows(
                [{"doc_id": r["doc_id"], "fused": r["fused"]} for r in rows],
                years, year_u, lam)
            out[f"g{g}_l{lam}"] = [{"doc_id": r["doc_id"], "score": r["fused_age"]} for r in aged]
    return out


def evaluate_variants(per_query_variants: Mapping[str, Mapping[str, list[dict[str, Any]]]],
                      holdout: Mapping[str, list[str]],
                      universes: Mapping[str, set[str]],
                      sources: Mapping[str, str],
                      corpus_ids: Sequence[str],
                      ) -> dict[str, Any]:
    """Track-B evaluation per variant (evaluator-side; qrels allowed here)."""
    qrels = {q: {d: 1 for d in holdout[q]} for q in per_query_variants}
    results: dict[str, Any] = {}
    for variant in next(iter(per_query_variants.values())):
        runs = {q: RankingResult(query_id=q, candidates=[
            RankedDocument(doc_id=r["doc_id"], score=float(r["score"]), rank=i + 1)
            for i, r in enumerate(per_query_variants[q][variant])])
            for q in per_query_variants}
        ev = ProtocolEvaluator().evaluate(
            runs, qrels, query_ids=sorted(per_query_variants),
            corpus_ids=corpus_ids,
            eligible_ids={q: universes[q] for q in per_query_variants},
            query_document_ids=sources, track="B")
        results[variant] = ev["aggregate"]
    return results
