"""Build artifacts/reports/evidence_index.json from sealed JSON reports (SG-042 / SG-043).

Maps every table, run, statistical comparison, ablation arm, performance
measurement, and core report claim to its exact source JSON file, SHA-256,
run_id, and configuration.

Anti-Silent-Bypass: exits 1 if any required sealed artifact is missing,
malformed, or disagrees with configs/frozen_main.json SHA-256. Never fabricates
Track C (VN) metrics when SG-033 human labels are pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "SG-042"
MODULE_VERSION = "sg042-1.0.0"
EXPECTED_FREEZE_SHA256 = "34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557"
REQUIRED_METRICS = ("nDCG@10", "Recall@100", "MRR@10", "MAP@100", "P@5")


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _ci(row: dict[str, Any]) -> str:
    """Format a bootstrap CI exactly as the report cites it; never hand-typed."""
    return f"[{float(row['ci_low']):+.4f}, {float(row['ci_high']):+.4f}]"


def _expect_ci_excludes_zero(row: dict[str, Any], expected: bool, label: str) -> None:
    if bool(row["ci_excludes_zero"]) is not expected:
        raise ValueError(
            f"{label}: claim wording assumes ci_excludes_zero={expected}, statistics.json says {row['ci_excludes_zero']!r}"
        )


def _vn_pool_pair_counts(project_root: Path) -> dict[str, int]:
    """Pair counts of the current VN evaluation pool (query set v2, ADR-023)."""
    pool = _load_json(project_root / "data" / "annotations" / "v2" / "vn_pool.json")
    counts = {"dev": 0, "test": 0}
    for q in pool["pools"]:
        if q["split"] not in counts:
            raise ValueError(f"Unexpected VN pool split {q['split']!r} for {q['query_id']}")
        counts[q["split"]] += len(q["candidates"])
    total = counts["dev"] + counts["test"]
    if total != int(pool["counts"]["unique_pairs"]):
        raise ValueError(f"VN pool pair count {total} != counts.unique_pairs {pool['counts']['unique_pairs']}")
    counts["total"] = total
    return counts


def build_index(project_root: Path) -> dict[str, Any]:
    freeze_path = project_root / "configs" / "frozen_main.json"
    freeze_sha = _sha256(freeze_path)
    if freeze_sha != EXPECTED_FREEZE_SHA256:
        raise ValueError(
            f"frozen_main.json SHA-256 mismatch: expected {EXPECTED_FREEZE_SHA256}, got {freeze_sha}"
        )
    freeze_doc = _load_json(freeze_path)

    reports_dir = project_root / "artifacts" / "reports"
    registry_path = reports_dir / "main_run_registry.json"
    ablation_age_path = reports_dir / "ablation_age.json"
    ablation_rrfk_path = reports_dir / "ablation_rrfk.json"
    robustness_path = reports_dir / "robustness.json"
    stats_path = reports_dir / "statistics.json"
    perf_path = reports_dir / "performance.json"

    registry = _load_json(registry_path)
    ablation_age = _load_json(ablation_age_path)
    ablation_rrfk = _load_json(ablation_rrfk_path)
    robustness = _load_json(robustness_path)
    stats = _load_json(stats_path)
    perf = _load_json(perf_path)

    for name, doc in (
        ("main_run_registry.json", registry),
        ("ablation_age.json", ablation_age),
        ("ablation_rrfk.json", ablation_rrfk),
        ("robustness.json", robustness),
        ("statistics.json", stats),
        ("performance.json", perf),
    ):
        if doc.get("freeze_sha256") != freeze_sha:
            raise ValueError(f"{name} freeze_sha256 mismatch: {doc.get('freeze_sha256')!r}")

    track_a_runs = registry.get("track_A_runs")
    if not isinstance(track_a_runs, list) or len(track_a_runs) != 7:
        raise ValueError(f"Expected 7 Track A runs in main_run_registry.json, got {len(track_a_runs or [])}")

    track_a_table: dict[str, dict[str, Any]] = {}
    for run in track_a_runs:
        if run.get("status") != "COMPLETED":
            raise ValueError(f"Track A run {run.get('run_id')} not COMPLETED")
        metrics = run.get("metrics", {})
        for m in REQUIRED_METRICS:
            if m not in metrics or not isinstance(metrics[m], (int, float)):
                raise ValueError(f"Run {run.get('run_id')} missing metric {m}")
        key = f"{run['dataset']}__{run['method']}"
        track_a_table[key] = {
            "dataset": run["dataset"],
            "method": run["method"],
            "split": run["split"],
            "run_id": run["run_id"],
            "run_dir": str(run["run_dir"]).replace("\\", "/"),
            "manifest_sha256": run["manifest_sha256"],
            "metrics": {m: float(metrics[m]) for m in REQUIRED_METRICS},
        }

    track_b = registry.get("track_B", {})
    arms_b = track_b.get("arms", {})
    for arm_name in ("ppr_age_best_g0.3_l0.0", "global_pagerank_control"):
        if arm_name not in arms_b:
            raise ValueError(f"Missing Track B arm {arm_name!r}")
        for m in REQUIRED_METRICS:
            if m not in arms_b[arm_name]:
                raise ValueError(f"Track B arm {arm_name!r} missing metric {m}")

    comparisons_by_key: dict[str, dict[str, Any]] = {}
    for row in stats.get("comparisons", []):
        ckey = f"{row['dataset']}__{row['comparison']}__{row['metric']}"
        comparisons_by_key[ckey] = row
    if len(comparisons_by_key) != 24:
        raise ValueError(f"Expected 24 paired bootstrap comparisons, got {len(comparisons_by_key)}")

    vn_pairs = _vn_pool_pair_counts(project_root)
    vn_results_path = reports_dir / "vn_results.json"
    if vn_results_path.is_file():
        vn_doc = _load_json(vn_results_path)
        track_c_entry = {
            "status": "COMPLETED",
            "source_file": "artifacts/reports/vn_results.json",
            "source_sha256": _sha256(vn_results_path),
            "selected_default_method": vn_doc.get("selected_default_method"),
            "methods": {
                m: v.get("aggregate") for m, v in (vn_doc.get("methods") or {}).items()
            },
        }
    else:
        track_c_entry = {
            "status": "chua_do",
            "pending_human_gate": (
                f"SG-033 (2 human annotators label {vn_pairs['dev']} dev + {vn_pairs['test']} test pairs "
                "of VN query set v2, ADR-023) -> SG-034"
            ),
            "pool": "data/annotations/v2/vn_pool.json",
            "pool_pairs": vn_pairs,
            "metrics": None,
        }

    scifact_dense_bm25 = comparisons_by_key["scifact__dense-vs-bm25__nDCG@10"]
    scidocs_dense_bm25 = comparisons_by_key["scidocs__dense-vs-bm25__nDCG@10"]
    scifact_hybrid_dense = comparisons_by_key["scifact__hybrid-vs-dense__nDCG@10"]
    scidocs_hybrid_dense = comparisons_by_key["scidocs__hybrid-vs-dense__nDCG@10"]
    openalex_ppr_global = comparisons_by_key["openalex__ppr_best-vs-global_control__nDCG@10"]
    _expect_ci_excludes_zero(scifact_dense_bm25, True, "CLM-001")
    _expect_ci_excludes_zero(scidocs_dense_bm25, True, "CLM-002")
    _expect_ci_excludes_zero(scifact_hybrid_dense, False, "CLM-003 scifact")
    _expect_ci_excludes_zero(scidocs_hybrid_dense, True, "CLM-003 scidocs")
    _expect_ci_excludes_zero(openalex_ppr_global, False, "CLM-004")

    claims = [
        {
            "claim_id": "CLM-001",
            "category": "positive_finding",
            "statement_vi": f"Trên SciFact test (n=300), Dense (BGE-base-en-v1.5) đạt nDCG@10 = 0.7404, vượt BM25 (0.6647) với chênh lệch tuyệt đối +0.0757 (95% paired bootstrap CI {_ci(scifact_dense_bm25)}, không chứa 0).",
            "source_file": "artifacts/reports/statistics.json",
            "run_ids": [
                track_a_table["scifact__dense"]["run_id"],
                track_a_table["scifact__bm25"]["run_id"],
            ],
            "metrics": {
                "dense_nDCG@10": track_a_table["scifact__dense"]["metrics"]["nDCG@10"],
                "bm25_nDCG@10": track_a_table["scifact__bm25"]["metrics"]["nDCG@10"],
                "delta_absolute": scifact_dense_bm25["delta_absolute"],
                "ci_low": scifact_dense_bm25["ci_low"],
                "ci_high": scifact_dense_bm25["ci_high"],
                "ci_excludes_zero": scifact_dense_bm25["ci_excludes_zero"],
            },
        },
        {
            "claim_id": "CLM-002",
            "category": "positive_finding",
            "statement_vi": f"Trên SCIDOCS test (n=1000), Dense đạt nDCG@10 = 0.2172, vượt BM25 (0.1521) với chênh lệch tuyệt đối +0.0652 (95% paired bootstrap CI {_ci(scidocs_dense_bm25)}, không chứa 0).",
            "source_file": "artifacts/reports/statistics.json",
            "run_ids": [
                track_a_table["scidocs__dense"]["run_id"],
                track_a_table["scidocs__bm25"]["run_id"],
            ],
            "metrics": {
                "dense_nDCG@10": track_a_table["scidocs__dense"]["metrics"]["nDCG@10"],
                "bm25_nDCG@10": track_a_table["scidocs__bm25"]["metrics"]["nDCG@10"],
                "delta_absolute": scidocs_dense_bm25["delta_absolute"],
                "ci_low": scidocs_dense_bm25["ci_low"],
                "ci_high": scidocs_dense_bm25["ci_high"],
                "ci_excludes_zero": scidocs_dense_bm25["ci_excludes_zero"],
            },
        },
        {
            "claim_id": "CLM-003",
            "category": "negative_finding",
            "statement_vi": f"Kết quả âm 1 (Hybrid RRF k=60 vs Dense): Trên SciFact test, Hybrid RRF đạt nDCG@10 = 0.7204, thấp hơn Dense (0.7404) với delta -0.0200 (95% CI {_ci(scifact_hybrid_dense)}, chứa 0). Trên SCIDOCS test, Hybrid RRF đạt nDCG@10 = 0.1976, thấp hơn Dense (0.2172) với delta -0.0197 (95% CI {_ci(scidocs_hybrid_dense)}, không chứa 0). Ghép BM25 trọng số bằng nhau kéo tụt top-10 khi BM25 yếu hơn hẳn Dense.",
            "source_file": "artifacts/reports/statistics.json",
            "run_ids": [
                track_a_table["scifact__hybrid"]["run_id"],
                track_a_table["scifact__dense"]["run_id"],
                track_a_table["scidocs__hybrid"]["run_id"],
                track_a_table["scidocs__dense"]["run_id"],
            ],
            "metrics": {
                "scifact_hybrid_nDCG@10": track_a_table["scifact__hybrid"]["metrics"]["nDCG@10"],
                "scifact_delta": scifact_hybrid_dense["delta_absolute"],
                "scifact_ci_low": scifact_hybrid_dense["ci_low"],
                "scifact_ci_high": scifact_hybrid_dense["ci_high"],
                "scidocs_hybrid_nDCG@10": track_a_table["scidocs__hybrid"]["metrics"]["nDCG@10"],
                "scidocs_delta": scidocs_hybrid_dense["delta_absolute"],
                "scidocs_ci_low": scidocs_hybrid_dense["ci_low"],
                "scidocs_ci_high": scidocs_hybrid_dense["ci_high"],
            },
        },
        {
            "claim_id": "CLM-004",
            "category": "negative_finding",
            "statement_vi": f"Kết quả âm 2 (Track B Seeded PPR vs Global PageRank trên OpenAlex test200): Nhánh cấu hình đóng băng ppr_age_best_g0.3_l0.0 đạt nDCG@10 = 0.1004, không vượt đối chứng global_pagerank_control (0.1082); chênh lệch tuyệt đối -0.0078 với 95% paired bootstrap CI {_ci(openalex_ppr_global)} chứa 0 (Recall@100 cùng bằng 0.2325 trên tập ứng viên C100).",
            "source_file": "artifacts/reports/main_run_registry.json",
            "run_ids": ["b_trials_test:ppr_age_best_g0.3_l0.0", "b_trials_test:global_pagerank_control"],
            "metrics": {
                "ppr_nDCG@10": arms_b["ppr_age_best_g0.3_l0.0"]["nDCG@10"],
                "global_nDCG@10": arms_b["global_pagerank_control"]["nDCG@10"],
                "Recall@100": arms_b["ppr_age_best_g0.3_l0.0"]["Recall@100"],
                "delta_absolute": openalex_ppr_global["delta_absolute"],
                "ci_low": openalex_ppr_global["ci_low"],
                "ci_high": openalex_ppr_global["ci_high"],
                "ci_excludes_zero": openalex_ppr_global["ci_excludes_zero"],
            },
        },
        {
            "claim_id": "CLM-005",
            "category": "negative_finding",
            "statement_vi": "Kết quả âm 3 (Ablation A1 — Age adjustment lambda > 0): Khi tăng hệ số phạt tuổi bài báo lambda qua {0.0, 0.01, 0.03, 0.1} tại gamma=0.3 trên OpenAlex test200, nDCG@10 của PPR giảm đơn điệu từ 0.1004 xuống 0.0977, 0.0883 và 0.0673 (Global PR giảm từ 0.1082 xuống 0.0740) vì các bài báo nền tảng giàu trích dẫn bị đẩy khỏi top-10.",
            "source_file": "artifacts/reports/ablation_age.json",
            "run_ids": ["ablation_age:ppr_g0.3_l0.0..l0.1"],
            "metrics": {
                "ppr_l0.0": ablation_age["arms"]["ppr_g0.3_l0.0"]["nDCG@10"],
                "ppr_l0.01": ablation_age["arms"]["ppr_g0.3_l0.01"]["nDCG@10"],
                "ppr_l0.03": ablation_age["arms"]["ppr_g0.3_l0.03"]["nDCG@10"],
                "ppr_l0.1": ablation_age["arms"]["ppr_g0.3_l0.1"]["nDCG@10"],
            },
        },
        {
            "claim_id": "CLM-006",
            "category": "ablation_finding",
            "statement_vi": "Ablation A3 (Độ nhạy hằng số RRF k={30, 60, 100}): Thay đổi k rất ít ảnh hưởng đến chất lượng xếp hạng (SciFact nDCG@10: 0.7224 / 0.7204 / 0.7202; SCIDOCS nDCG@10: 0.1992 / 0.1976 / 0.1980), khẳng định việc giữ mặc định k=60 không làm sai lệch kết luận.",
            "source_file": "artifacts/reports/ablation_rrfk.json",
            "run_ids": ["ablation_rrfk:k30_k60_k100"],
            "metrics": {
                "scifact_k30": ablation_rrfk["arms"]["hybrid_rrf_k30_scifact"]["nDCG@10"],
                "scifact_k60": ablation_rrfk["arms"]["hybrid_rrf_k60_scifact"]["nDCG@10"],
                "scifact_k100": ablation_rrfk["arms"]["hybrid_rrf_k100_scifact"]["nDCG@10"],
                "scidocs_k30": ablation_rrfk["arms"]["hybrid_rrf_k30_scidocs"]["nDCG@10"],
                "scidocs_k60": ablation_rrfk["arms"]["hybrid_rrf_k60_scidocs"]["nDCG@10"],
                "scidocs_k100": ablation_rrfk["arms"]["hybrid_rrf_k100_scidocs"]["nDCG@10"],
            },
        },
        {
            "claim_id": "CLM-007",
            "category": "performance_finding",
            "statement_vi": "Hiệu năng hệ thống (SG-040): Trên SciFact (5.183 bài), warm P95 latency của mọi phương pháp đều dưới mục tiêu 500ms/query (BM25 P95 = 40.2ms, Dense search P95 = 1.4ms, Hybrid full P95 = 41.5ms). Tuy nhiên trên SCIDOCS (25.657 bài), BM25 thuần Python có P50 = 173.1ms nhưng P95 = 1510.9ms, và Track B C100+PPR trên đồ thị OpenAlex mất trung bình 1683.5ms/query (P95 = 2380.4ms), vượt mục tiêu 500ms/query.",
            "source_file": "artifacts/reports/performance.json",
            "run_ids": ["SG-040:performance_profile"],
            "metrics": {
                "query_budget_s": perf["query_budget_s"],
                "scifact_hybrid_p95_s": perf["perf_warm"]["methods"]["scifact"]["hybrid_full_per_query_s"]["p95_s"],
                "scidocs_bm25_p50_s": perf["perf_warm"]["methods"]["scidocs"]["bm25_search_per_query"]["p50_s"],
                "scidocs_bm25_p95_s": perf["perf_warm"]["methods"]["scidocs"]["bm25_search_per_query"]["p95_s"],
                "trackb_c100_ppr_mean_s": perf["perf_trackb"]["stages"]["c100_ppr"]["mean_s"],
                "trackb_c100_ppr_p95_s": perf["perf_trackb"]["stages"]["c100_ppr"]["p95_s"],
                "cold_worker_peak_rss_bytes": perf["peak_rss_bytes_cold_worker"],
                "concurrency_speedup_4t": perf["perf_concur"]["speedup_4t"],
            },
        },
        {
            "claim_id": "CLM-008",
            "category": "pending_human_gate",
            "statement_vi": f"Track C (Truy vấn tiếng Việt xuyên ngữ): Đã hoàn tất 30 truy vấn v2 (10 dev / 20 test, ADR-023), bộ nhớ đệm dịch máy (Opus-MT vi-en) và pool mù {vn_pairs['total']} cặp ({vn_pairs['dev']} dev / {vn_pairs['test']} test; SG-031..SG-033 tooling), nhưng CHƯA báo cáo điểm đánh giá cuối cùng vì đang chờ 2 thành viên con người gán nhãn độc lập (SG-033) và duyệt freeze VN (SG-034).",
            "source_file": "data/annotations/v2/vn_pool.json",
            "run_ids": [],
            "metrics": track_c_entry["metrics"],
        },
    ]

    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "module_version": MODULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freeze_manifest": {
            "path": "configs/frozen_main.json",
            "sha256": freeze_sha,
            "freeze_id": freeze_doc.get("freeze_id"),
            "git_head_at_freeze": freeze_doc.get("git_head"),
        },
        "source_files": {
            "main_run_registry.json": _sha256(registry_path),
            "ablation.json": _sha256(reports_dir / "ablation.json"),
            "ablation_age.json": _sha256(ablation_age_path),
            "ablation_rrfk.json": _sha256(ablation_rrfk_path),
            "robustness.json": _sha256(robustness_path),
            "statistics.json": _sha256(stats_path),
            "performance.json": _sha256(perf_path),
        },
        "tables": {
            "table_1_track_a_main": track_a_table,
            "table_2_track_b_main": {
                "report": track_b.get("report"),
                "report_sha256": track_b.get("report_sha256"),
                "frozen_weights": track_b.get("frozen_weights"),
                "queries": track_b.get("queries"),
                "arms": arms_b,
            },
            "table_3_track_c_vn": track_c_entry,
            "table_4_ablation_age": ablation_age.get("arms"),
            "table_5_ablation_rrfk": ablation_rrfk.get("arms"),
            "table_6_paired_bootstrap": comparisons_by_key,
            "table_7_robustness_buckets": robustness.get("buckets"),
            "table_8_performance": {
                "hardware": perf.get("hardware"),
                "query_budget_s": perf.get("query_budget_s"),
                "peak_rss_bytes_cold_worker": perf.get("peak_rss_bytes_cold_worker"),
                "index_bytes": perf.get("index_bytes"),
                "warm_methods": perf.get("perf_warm", {}).get("methods"),
                "warm_build": perf.get("perf_warm", {}).get("build"),
                "track_b_stages": perf.get("perf_trackb", {}).get("stages"),
                "concurrency": perf.get("perf_concur"),
            },
        },
        "claims": claims,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build evidence_index.json from sealed reports (SG-042/SG-043)")
    ap.add_argument("--project-root", default=str(ROOT))
    ap.add_argument("--output", default="artifacts/reports/evidence_index.json")
    args = ap.parse_args(argv)
    try:
        proot = Path(args.project_root).resolve()
        out_path = Path(args.output) if Path(args.output).is_absolute() else proot / args.output
        payload = build_index(proot)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # LF on every platform: the committed artifact is LF and the repo disables EOL conversion.
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(
            json.dumps(
                {
                    "status": "OK",
                    "output": str(out_path),
                    "track_a_runs": len(payload["tables"]["table_1_track_a_main"]),
                    "bootstrap_comparisons": len(payload["tables"]["table_6_paired_bootstrap"]),
                    "claims": len(payload["claims"]),
                },
                indent=2,
            )
        )
        return 0
    except (FileNotFoundError, ValueError, KeyError) as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
