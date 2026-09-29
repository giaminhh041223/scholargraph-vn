"""Generate SVG figures for the academic report from evidence_index.json (SG-043).

Reads ONLY artifacts/reports/evidence_index.json and writes deterministic SVG
charts into reports/figures/:
  - fig1_track_a_ndcg10.svg
  - fig2_track_b_openalex.svg
  - fig3_ablation_age_rrf.svg
  - fig4_latency_budget.svg

Anti-Silent-Bypass: exits 1 if evidence_index.json is missing or lacks any
required table/metric.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "SG-043"
MODULE_VERSION = "sg043-1.0.0"


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _require_float(mapping: dict[str, Any], key: str, ctx: str) -> float:
    if not isinstance(mapping, dict) or key not in mapping:
        raise ValueError(f"Missing required metric {key!r} in {ctx}")
    val = mapping[key]
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise ValueError(f"Non-numeric metric {key!r} in {ctx}: {val!r}")
    return float(val)


def render_fig1_track_a(tables: dict[str, Any]) -> str:
    t1 = tables.get("table_1_track_a_main")
    if not isinstance(t1, dict):
        raise ValueError("Missing table_1_track_a_main")

    items = [
        ("SciFact — TF-IDF", _require_float(t1.get("scifact__tfidf", {}).get("metrics", {}), "nDCG@10", "scifact__tfidf"), "#64748b"),
        ("SciFact — BM25", _require_float(t1.get("scifact__bm25", {}).get("metrics", {}), "nDCG@10", "scifact__bm25"), "#3b82f6"),
        ("SciFact — Dense (BGE)", _require_float(t1.get("scifact__dense", {}).get("metrics", {}), "nDCG@10", "scifact__dense"), "#10b981"),
        ("SciFact — Hybrid RRF", _require_float(t1.get("scifact__hybrid", {}).get("metrics", {}), "nDCG@10", "scifact__hybrid"), "#f59e0b"),
        ("SCIDOCS — BM25", _require_float(t1.get("scidocs__bm25", {}).get("metrics", {}), "nDCG@10", "scidocs__bm25"), "#3b82f6"),
        ("SCIDOCS — Dense (BGE)", _require_float(t1.get("scidocs__dense", {}).get("metrics", {}), "nDCG@10", "scidocs__dense"), "#10b981"),
        ("SCIDOCS — Hybrid RRF", _require_float(t1.get("scidocs__hybrid", {}).get("metrics", {}), "nDCG@10", "scidocs__hybrid"), "#f59e0b"),
    ]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="360" viewBox="0 0 760 360">',
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        '  <text x="24" y="32" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="bold" fill="#0f172a">Hình 1 — Track A (BEIR SciFact &amp; SCIDOCS Test): nDCG@10 theo phương pháp</text>',
        '  <text x="24" y="52" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#475569">Nguồn: artifacts/reports/main_run_registry.json (Dense &gt; Hybrid RRF k=60 &gt; BM25 &gt; TF-IDF)</text>',
    ]
    y0 = 80
    bar_max_w = 460.0
    for idx, (label, val, color) in enumerate(items):
        y = y0 + idx * 36
        w = max(2.0, val * bar_max_w)
        lines.append(
            f'  <text x="24" y="{y + 16}" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#1e293b">{label}</text>'
        )
        lines.append(
            f'  <rect x="210" y="{y}" width="{w:.1f}" height="22" rx="3" fill="{color}"/>'
        )
        lines.append(
            f'  <text x="{218 + w:.1f}" y="{y + 16}" font-family="Consolas, monospace" font-size="12" fill="#0f172a">{val:.4f}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_fig2_track_b(tables: dict[str, Any]) -> str:
    t2 = (tables.get("table_2_track_b_main") or {}).get("arms")
    if not isinstance(t2, dict):
        raise ValueError("Missing table_2_track_b_main.arms")
    ppr = t2.get("ppr_age_best_g0.3_l0.0", {})
    glob = t2.get("global_pagerank_control", {})
    metrics = ("nDCG@10", "Recall@100", "MRR@10", "MAP@100", "P@5")

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="340" viewBox="0 0 760 340">',
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        '  <text x="24" y="32" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="bold" fill="#0f172a">Hình 2 — Track B (OpenAlex Test 200 queries): Seeded PPR vs Global PageRank</text>',
        '  <text x="24" y="52" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#475569">Cấu hình đóng băng gamma=0.3, lambda=0.0; 95% CI của nDCG@10 [-0.0198, +0.0021] chứa 0</text>',
    ]
    y0 = 82
    scale = 1400.0
    for idx, m in enumerate(metrics):
        vp = _require_float(ppr, m, "ppr_age_best_g0.3_l0.0")
        vg = _require_float(glob, m, "global_pagerank_control")
        y = y0 + idx * 46
        wp = max(2.0, vp * scale)
        wg = max(2.0, vg * scale)
        lines.append(
            f'  <text x="24" y="{y + 18}" font-family="Segoe UI, Arial, sans-serif" font-size="13" font-weight="bold" fill="#1e293b">{m}</text>'
        )
        lines.append(f'  <rect x="160" y="{y}" width="{wp:.1f}" height="14" rx="2" fill="#2563eb"/>')
        lines.append(
            f'  <text x="{168 + wp:.1f}" y="{y + 11}" font-family="Consolas, monospace" font-size="11" fill="#1e3a8a">PPR: {vp:.4f}</text>'
        )
        lines.append(f'  <rect x="160" y="{y + 18}" width="{wg:.1f}" height="14" rx="2" fill="#64748b"/>')
        lines.append(
            f'  <text x="{168 + wg:.1f}" y="{y + 29}" font-family="Consolas, monospace" font-size="11" fill="#334155">Global PR: {vg:.4f}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_fig3_ablation(tables: dict[str, Any]) -> str:
    t4 = tables.get("table_4_ablation_age")
    t5 = tables.get("table_5_ablation_rrfk")
    if not isinstance(t4, dict) or not isinstance(t5, dict):
        raise ValueError("Missing ablation tables")

    age_rows = [
        ("PPR lambda=0.00", _require_float(t4.get("ppr_g0.3_l0.0", {}), "nDCG@10", "ppr_g0.3_l0.0"), "#2563eb"),
        ("PPR lambda=0.01", _require_float(t4.get("ppr_g0.3_l0.01", {}), "nDCG@10", "ppr_g0.3_l0.01"), "#3b82f6"),
        ("PPR lambda=0.03", _require_float(t4.get("ppr_g0.3_l0.03", {}), "nDCG@10", "ppr_g0.3_l0.03"), "#60a5fa"),
        ("PPR lambda=0.10", _require_float(t4.get("ppr_g0.3_l0.1", {}), "nDCG@10", "ppr_g0.3_l0.1"), "#93c5fd"),
        ("RRF k=30 (SciFact)", _require_float(t5.get("hybrid_rrf_k30_scifact", {}), "nDCG@10", "k30_scifact"), "#d97706"),
        ("RRF k=60 (SciFact)", _require_float(t5.get("hybrid_rrf_k60_scifact", {}), "nDCG@10", "k60_scifact"), "#f59e0b"),
        ("RRF k=100 (SciFact)", _require_float(t5.get("hybrid_rrf_k100_scifact", {}), "nDCG@10", "k100_scifact"), "#fbbf24"),
    ]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="360" viewBox="0 0 760 360">',
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        '  <text x="24" y="32" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="bold" fill="#0f172a">Hình 3 — Ablation A1 (Age decay lambda) &amp; A3 (Hằng số RRF k): nDCG@10</text>',
        '  <text x="24" y="52" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#475569">Tăng lambda làm giảm đơn điệu nDCG@10 trên OpenAlex; thay đổi k={30,60,100} hầu như bất biến</text>',
    ]
    y0 = 80
    for idx, (label, val, color) in enumerate(age_rows):
        y = y0 + idx * 36
        w = max(4.0, val * 450.0)
        lines.append(
            f'  <text x="24" y="{y + 16}" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#1e293b">{label}</text>'
        )
        lines.append(f'  <rect x="210" y="{y}" width="{w:.1f}" height="22" rx="3" fill="{color}"/>')
        lines.append(
            f'  <text x="{218 + w:.1f}" y="{y + 16}" font-family="Consolas, monospace" font-size="12" fill="#0f172a">{val:.4f}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_fig4_latency(tables: dict[str, Any]) -> str:
    t8 = tables.get("table_8_performance")
    if not isinstance(t8, dict):
        raise ValueError("Missing table_8_performance")
    warm = t8.get("warm_methods") or {}
    tb = t8.get("track_b_stages") or {}

    rows = [
        ("SciFact — BM25 P95", _require_float((warm.get("scifact") or {}).get("bm25_search_per_query", {}), "p95_s", "scifact_bm25") * 1000.0, "#10b981"),
        ("SciFact — Hybrid Full P95", _require_float((warm.get("scifact") or {}).get("hybrid_full_per_query_s", {}), "p95_s", "scifact_hybrid") * 1000.0, "#10b981"),
        ("SCIDOCS — BM25 P50", _require_float((warm.get("scidocs") or {}).get("bm25_search_per_query", {}), "p50_s", "scidocs_bm25_p50") * 1000.0, "#10b981"),
        ("SCIDOCS — BM25 P95 (>500ms)", _require_float((warm.get("scidocs") or {}).get("bm25_search_per_query", {}), "p95_s", "scidocs_bm25_p95") * 1000.0, "#ef4444"),
        ("Track B — C100+PPR Mean (>500ms)", _require_float((tb.get("c100_ppr") or {}), "mean_s", "trackb_ppr_mean") * 1000.0, "#ef4444"),
        ("Track B — C100+PPR P95 (>500ms)", _require_float((tb.get("c100_ppr") or {}), "p95_s", "trackb_ppr_p95") * 1000.0, "#dc2626"),
    ]
    scale = 0.18  # ms -> px (2500ms = 450px)
    budget_x = 240.0 + 500.0 * scale

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="340" viewBox="0 0 760 340">',
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        '  <text x="24" y="32" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="bold" fill="#0f172a">Hình 4 — Độ trễ truy vấn (ms) so với mục tiêu 500ms/query (SG-040)</text>',
        '  <text x="24" y="52" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#475569">Đường nét đứt: ngưỡng mục tiêu 500ms; màu đỏ: các phép đo vượt ngân sách được báo cáo trung thực</text>',
        f'  <line x1="{budget_x:.1f}" y1="70" x2="{budget_x:.1f}" y2="310" stroke="#0f172a" stroke-width="1.5" stroke-dasharray="4,4"/>',
        f'  <text x="{budget_x + 4:.1f}" y="78" font-family="Consolas, monospace" font-size="11" fill="#0f172a">500ms target</text>',
    ]
    y0 = 90
    for idx, (label, ms, color) in enumerate(rows):
        y = y0 + idx * 36
        w = max(2.0, ms * scale)
        lines.append(
            f'  <text x="24" y="{y + 16}" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#1e293b">{label}</text>'
        )
        lines.append(f'  <rect x="240" y="{y}" width="{w:.1f}" height="20" rx="3" fill="{color}"/>')
        lines.append(
            f'  <text x="{248 + w:.1f}" y="{y + 15}" font-family="Consolas, monospace" font-size="12" fill="#0f172a">{ms:.1f} ms</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate SVG report figures from evidence_index.json (SG-043)")
    ap.add_argument("--evidence-index", default="artifacts/reports/evidence_index.json")
    ap.add_argument("--output-dir", default="reports/figures")
    args = ap.parse_args(argv)
    try:
        ev_path = Path(args.evidence_index) if Path(args.evidence_index).is_absolute() else ROOT / args.evidence_index
        out_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else ROOT / args.output_dir
        if not ev_path.is_file():
            return fail(f"Missing evidence_index.json: {ev_path}")
        doc = json.loads(ev_path.read_text(encoding="utf-8"))
        tables = doc.get("tables")
        if not isinstance(tables, dict):
            return fail("Malformed evidence_index.json: missing 'tables'")

        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            "fig1_track_a_ndcg10.svg": render_fig1_track_a(tables),
            "fig2_track_b_openalex.svg": render_fig2_track_b(tables),
            "fig3_ablation_age_rrf.svg": render_fig3_ablation(tables),
            "fig4_latency_budget.svg": render_fig4_latency(tables),
        }
        for fname, content in outputs.items():
            (out_dir / fname).write_text(content, encoding="utf-8")

        print(
            json.dumps(
                {
                    "status": "OK",
                    "output_dir": str(out_dir),
                    "figures": sorted(outputs.keys()),
                },
                indent=2,
            )
        )
        return 0
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
