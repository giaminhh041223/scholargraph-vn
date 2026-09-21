"""Paired bootstrap CIs + error packets on sealed test artifacts (SG-030).

Comparisons below are the PRIMARY method pairs from the freeze (no selection):
they mirror the SG-028 table rows. Uncertainty follows protocol statistics
(paired percentile CI 95%, B=10.000, seed 20260915, query-group resampling).
No p-values, no formal significance claims (ADR-012).

Error packets (24) are prepared for the TWO MEMBERS to read (human work, gate);
this script only assembles the packets, it does not judge them.

Usage: run_statistics.py
Exit 1 on any fatal problem.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.evaluation.sealed import load_verified_freeze
from scholargraph.evaluation.statistics import (
    PROTOCOL_LEVEL,
    PROTOCOL_RESAMPLES,
    PROTOCOL_SEED,
    ndcg_at_10,
    paired_bootstrap_ci,
)
from scholargraph.ingest.beir_loader import canonical_beir_id

TASK_ID = "SG-030"
MODULE_VERSION = "sg030-1.0.0"
METRICS = ("nDCG@10", "Recall@100", "MRR@10")
# Primary pairs (pre-specified; mirror the sealed table — not chosen on test).
COMPARISONS = [
    {"track": "A", "dataset": "scifact", "treatment": "dense", "control": "bm25"},
    {"track": "A", "dataset": "scifact", "treatment": "hybrid", "control": "dense"},
    {"track": "A", "dataset": "scifact", "treatment": "hybrid", "control": "bm25"},
    {"track": "A", "dataset": "scifact", "treatment": "tfidf", "control": "bm25"},
    {"track": "A", "dataset": "scidocs", "treatment": "dense", "control": "bm25"},
    {"track": "A", "dataset": "scidocs", "treatment": "hybrid", "control": "dense"},
    {"track": "A", "dataset": "scidocs", "treatment": "hybrid", "control": "bm25"},
    {"track": "B", "dataset": "openalex", "treatment": "ppr_best", "control": "global_control"},
]


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _per_query_trackA(run_dir: Path, metric: str) -> dict[str, float]:
    perq = json.loads((run_dir / "per_query.json").read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for qid, row in perq.items():
        if metric not in row or row[metric] is None:
            raise RuntimeError(f"Missing per-query {metric} for {qid} in {run_dir}")
        out[qid] = float(row[metric])
    return out


def _mrr_recall(order: list[str], rel: set[str]) -> tuple[float, float]:
    mrr = 0.0
    for i, d in enumerate(order[:10]):
        if d in rel:
            mrr = 1.0 / (i + 1)
            break
    recall = len([d for d in order[:100] if d in rel]) / len(rel) if rel else 0.0
    return mrr, recall


def _per_query_trackB(arm: str, metric: str) -> tuple[dict[str, float], dict[str, list[str]], dict[str, set[str]]]:
    btest = json.loads((ROOT / "artifacts" / "reports" / "b_trials_test.json").read_text(encoding="utf-8"))
    pq = btest["per_query_rankings"]
    vals: dict[str, float] = {}
    orders: dict[str, list[str]] = {}
    rels: dict[str, set[str]] = {}
    for q, v in pq.items():
        order = [r["doc_id"] for r in v[arm]]
        rel = set(v["heldout"])
        orders[q] = order
        rels[q] = rel
        if metric == "nDCG@10":
            vals[q] = ndcg_at_10(order, {d: 1 for d in rel})
        elif metric == "MRR@10":
            vals[q], _ = _mrr_recall(order, rel)
        elif metric == "Recall@100":
            _, vals[q] = _mrr_recall(order, rel)
        else:
            raise RuntimeError(f"Unknown metric {metric}")
    return vals, orders, rels


def _beir_titles(dataset: str) -> dict[str, str]:
    titles: dict[str, str] = {}
    for line in (ROOT / "data" / "raw" / "beir" / dataset / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            titles[canonical_beir_id(dataset, str(row["_id"]))] = str(row.get("title", ""))[:200]
    return titles


def _query_texts(dataset: str, split_file: str) -> dict[str, str]:
    split_def = json.loads((ROOT / split_file).read_text(encoding="utf-8"))
    want = set(split_def["query_ids"])
    out: dict[str, str] = {}
    for line in (ROOT / split_def["queries_file"]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            cid = canonical_beir_id(dataset, str(row["_id"]))
            if cid in want:
                out[cid] = str(row.get("text", ""))[:300]
    return out


def main() -> int:
    try:
        t_start = time.time()
        freeze, freeze_sha = load_verified_freeze(ROOT)
        reg = json.loads((ROOT / "artifacts" / "reports" / "main_run_registry.json").read_text(encoding="utf-8"))
        if reg.get("freeze_sha256") != freeze_sha:
            raise RuntimeError("Registry sealed on a different freeze; refusing statistics.")
        by_key = {(r["method"], r["dataset"]): r for r in reg["track_A_runs"]}
        results: list[dict] = []
        per_query_cache: dict[tuple[str, str, str], dict[str, float]] = {}
        # Track-B orders cached for packets.
        b_orders: dict[str, dict[str, list[str]]] = {}
        b_rels: dict[str, set[str]] = {}
        for comp in COMPARISONS:
            for metric in METRICS:
                if comp["track"] == "A":
                    key_t = (comp["treatment"], comp["dataset"], metric)
                    key_c = (comp["control"], comp["dataset"], metric)
                    if key_t not in per_query_cache:
                        per_query_cache[key_t] = _per_query_trackA(
                            ROOT / by_key[(comp["treatment"], comp["dataset"])]["run_dir"], metric)
                    if key_c not in per_query_cache:
                        per_query_cache[key_c] = _per_query_trackA(
                            ROOT / by_key[(comp["control"], comp["dataset"])]["run_dir"], metric)
                    t_vals, c_vals = per_query_cache[key_t], per_query_cache[key_c]
                else:
                    key_t = (comp["treatment"], "openalex", metric)
                    key_c = (comp["control"], "openalex", metric)
                    if key_t not in per_query_cache:
                        vals, orders, rels = _per_query_trackB(comp["treatment"], metric)
                        per_query_cache[key_t] = vals
                        b_orders[comp["treatment"]] = orders
                        b_rels = rels
                    if key_c not in per_query_cache:
                        vals, orders, _ = _per_query_trackB(comp["control"], metric)
                        per_query_cache[key_c] = vals
                        b_orders[comp["control"]] = orders
                    t_vals, c_vals = per_query_cache[key_t], per_query_cache[key_c]
                ci = paired_bootstrap_ci(t_vals, c_vals, resamples=PROTOCOL_RESAMPLES,
                                         seed=PROTOCOL_SEED, level=PROTOCOL_LEVEL)
                results.append({"comparison": f"{comp['treatment']}-vs-{comp['control']}",
                                "track": comp["track"], "dataset": comp["dataset"],
                                "metric": metric, **ci})
        # ---- error packets (24) for the two members ----
        packets: list[dict] = []
        scifact_texts = _query_texts("scifact", "data/splits/scifact_test.json")
        scidocs_texts = _query_texts("scidocs", "data/splits/scidocs_test.json")
        scifact_titles = _beir_titles("scifact")
        scidocs_titles = _beir_titles("scidocs")
        dense_sf = per_query_cache[("dense", "scifact", "nDCG@10")]
        bm25_sf = per_query_cache[("bm25", "scifact", "nDCG@10")]
        losses = sorted(((dense_sf[q] - bm25_sf[q], q) for q in dense_sf if bm25_sf[q] > 0))
        zeros = sorted((q for q in dense_sf if dense_sf[q] == 0.0))
        for q in [q for _, q in losses[:6]] + zeros[:6]:
            packets.append(_packet_trackA("scifact", q, scifact_texts, scifact_titles,
                                          by_key, per_query_cache))
        dense_sd = per_query_cache[("dense", "scidocs", "nDCG@10")]
        bm25_sd = per_query_cache[("bm25", "scidocs", "nDCG@10")]
        losses_sd = sorted(((dense_sd[q] - bm25_sd[q], q) for q in dense_sd if bm25_sd[q] > 0))
        zeros_sd = sorted((q for q in dense_sd if dense_sd[q] == 0.0))
        for q in [q for _, q in losses_sd[:3]] + zeros_sd[:3]:
            packets.append(_packet_trackA("scidocs", q, scidocs_texts, scidocs_titles,
                                          by_key, per_query_cache))
        ppr_vals = per_query_cache[("ppr_best", "openalex", "nDCG@10")]
        glo_vals = per_query_cache[("global_control", "openalex", "nDCG@10")]
        gaps = sorted(((glo_vals[q] - ppr_vals[q], q) for q in ppr_vals))
        zeros_b = sorted((q for q in ppr_vals if ppr_vals[q] == 0.0))
        import json as _js
        works_titles = {u: "" for u in list(ppr_vals)[:0]}
        _ = works_titles
        for q in [q for _, q in gaps[:3]] + zeros_b[:3]:
            packets.append({"packet": f"trackB:{q}", "query_source": q,
                            "ppr_nDCG@10": ppr_vals[q], "global_nDCG@10": glo_vals[q],
                            "heldout": sorted(b_rels[q]),
                            "ppr_top3": b_orders["ppr_best"][q][:3],
                            "global_top3": b_orders["global_control"][q][:3]})
        payload = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
                   "generated_at": datetime.now(timezone.utc).isoformat(),
                   "freeze_sha256": freeze_sha,
                   "protocol": {"resamples": PROTOCOL_RESAMPLES, "seed": PROTOCOL_SEED,
                                "level": PROTOCOL_LEVEL, "paired": True, "unit": "query_group",
                                "p_values": False},
                   "comparisons": results,
                   "n_packets": len(packets),
                   "elapsed_seconds": time.time() - t_start}
        out_dir = ROOT / "artifacts" / "reports"
        (out_dir / "statistics.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "error_packets.json").write_text(
            json.dumps({"schema_version": 1, "task_id": TASK_ID, "packets": packets},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        _write_md(payload, packets)
        print(json.dumps({"comparisons": len(results), "packets": len(packets),
                          "elapsed_s": round(time.time() - t_start, 1)}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        import traceback
        traceback.print_exc()
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


def _packet_trackA(dataset, q, texts, titles, by_key, cache) -> dict:
    per_method_top3 = {}
    for method in (["bm25", "tfidf", "dense", "hybrid"] if dataset == "scifact"
                   else ["bm25", "dense", "hybrid"]):
        run_dir = ROOT / by_key[(method, dataset)]["run_dir"]
        for line in (run_dir / "rankings.jsonl").read_text(encoding="utf-8").splitlines():
            o = json.loads(line)
            if o["query_id"] == q:
                per_method_top3[method] = [
                    {"doc_id": c["doc_id"], "score": round(float(c["score"]), 4),
                     "title": titles.get(c["doc_id"], "")[:160]}
                    for c in o["candidates"][:3]]
                break
    return {"packet": f"{dataset}:{q}", "query_text": texts.get(q, ""),
            "nDCG@10": {m: cache[(m, dataset, "nDCG@10")][q] for m in per_method_top3},
            "top3": per_method_top3}


def _write_md(payload: dict, packets: list[dict]) -> None:
    out_dir = ROOT / "artifacts" / "reports"
    lines = ["# Statistics - paired bootstrap CIs (SG-030)", "",
             f"Freeze sha256 `{payload['freeze_sha256']}`.",
             f"Protocol: paired bootstrap, B={PROTOCOL_RESAMPLES}, seed={PROTOCOL_SEED}, "
             f"level={PROTOCOL_LEVEL}, unit=query_group. No p-values, no formal claims.",
             "",
             "## Comparisons (absolute delta + 95% CI + relative delta)",
             "",
             "| comparison | dataset | metric | n | delta | 95% CI | rel | CI excl 0 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in payload["comparisons"]:
        rel = "n/a" if r["delta_relative"] is None else f"{r['delta_relative']:.3f}"
        lines.append(f"| {r['comparison']} | {r['dataset']} | {r['metric']} | {r['n_queries']} | "
                     f"{r['delta_absolute']:.4f} | [{r['ci_low']:.4f}, {r['ci_high']:.4f}] | "
                     f"{rel} | {r['ci_excludes_zero']} |")
    lines += ["",
              "## Subgroups (exploratory, with sample size)",
              "",
              "See `artifacts/reports/robustness.json` buckets (R1/R2/R3) — every bucket "
              "carries n; small-n buckets are exploratory only.",
              "",
              "## Error packets for the two members",
              "",
              f"{len(packets)} packets in `artifacts/reports/error_packets.json`; reading guide "
              "in `docs/ERROR_ANALYSIS.md`. Member reading is a human gate (pending).",
              ""]
    (out_dir / "statistics.md").write_text("\n".join(lines), encoding="utf-8")

    docs = ["# ERROR ANALYSIS - reading guide for the two members (SG-030)", "",
            "## How to read a CI row",
            "",
            "- `delta` = mean(treatment) - mean(control) over the same queries (paired).",
            "- A 95% CI that contains 0 means: no conclusion either way (not proof of tie).",
            "- Negative results stand: low/negative deltas are kept, never edited.",
            "- Subgroup buckets are exploratory; mind the n.",
            "",
            "## Checklist (each member reads all packets, then you compare)",
            "",
            "- [ ] Member 1 read all 24 packets + noted failure hypotheses",
            "- [ ] Member 2 read all 24 packets + noted failure hypotheses",
            "- [ ] Disagreements discussed; joint note appended below",
            "",
            "## Packets",
            ""]
    for p in packets:
        docs.append(f"### {p['packet']}")
        docs.append("")
        docs.append("```json")
        docs.append(json.dumps(p, ensure_ascii=False, indent=2)[:2000])
        docs.append("```")
        docs.append("")
    docs += ["## Joint note (to be filled by the two members)", "", "(pending)", ""]
    (ROOT / "docs" / "ERROR_ANALYSIS.md").write_text("\n".join(docs), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
