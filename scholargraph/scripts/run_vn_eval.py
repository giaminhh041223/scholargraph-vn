"""Track C Vietnamese cross-lingual dev freeze & final test evaluation (SG-034).

Two-phase workflow per Research Protocol v1 §7 & MERGE_AND_FINISH_PLAN §6.7 (CX-3):
  1. --phase freeze-dev:
     Reads ONLY dev pool pairs from vn_labels.jsonl (refusing any test-split
     evaluation or unlabeled dev pair), scores the 3 frozen pool methods
     (translated_bm25, multilingual_dense, vn_hybrid_rrf) on dev nDCG@10,
     selects the winning method via scholargraph.evaluation.tuning.select_best
     (lexicographic trial_id tie-break), and writes configs/frozen_vn.json with
     human_approved=false. Stops and waits for GM-5 review + human approval.
  2. --phase eval-test:
     Requires configs/frozen_vn.json with human_approved=true and complete test
     labels in vn_labels.jsonl. Runs final VN test evaluation once and writes
     artifacts/reports/vn_results.json and artifacts/reports/vn_results.md
     (including nDCG@10, P@5, MRR@10, pooled Recall@100, unjudged_ratio@10, and
     intent-family breakdown).

Anti-Silent-Bypass: exits 1 on missing files, unlabeled rows, unresolved A/B
disagreements without adjudication, provenance leaks, or unapproved freeze.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scholargraph.evaluation.metrics import _score_query
from scholargraph.evaluation.tuning import select_best

TASK_ID = "SG-034"
MODULE_VERSION = "sg034-1.0.0"
POOL_METHODS = ("translated_bm25", "multilingual_dense", "vn_hybrid_rrf")
DIAGNOSTIC_METHODS = ("original_vi_bm25",)
FORBIDDEN_LABEL_KEYS = ("method", "system", "score", "rank", "provenance", "source")


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_split_judgments(
    labels_path: Path,
    pool_doc: dict[str, Any],
    target_split: str,
) -> tuple[dict[str, dict[str, int]], dict[str, set[str]], dict[str, Any]]:
    """Resolve adjudicated/agreed labels for a single split (dev or test).

    Never reads or returns judgments for any query outside target_split.
    Raises ValueError on any missing pair, null label, provenance leak, or
    unresolved A/B disagreement lacking an adjudicated row.
    """
    if target_split not in ("dev", "test"):
        raise ValueError(f"Invalid target_split: {target_split!r}")
    if not labels_path.is_file():
        raise FileNotFoundError(f"Missing labels file: {labels_path}")

    pools = pool_doc.get("pools")
    if not isinstance(pools, list) or not pools:
        raise ValueError("Malformed vn_pool.json: missing non-empty 'pools' list")

    split_pools = [p for p in pools if p.get("split") == target_split]
    if not split_pools:
        raise ValueError(f"No pools found for split={target_split!r}")

    expected_pairs: dict[str, set[str]] = {}
    for p in split_pools:
        qid = str(p.get("query_id", "")).strip()
        cands = p.get("candidates")
        if not qid or not isinstance(cands, list) or not cands:
            raise ValueError(f"Invalid pool entry for query {qid!r}")
        expected_pairs[qid] = {str(c["doc_id"]) for c in cands if "doc_id" in c}
        if len(expected_pairs[qid]) != len(cands):
            raise ValueError(f"Duplicate or missing doc_id in pool for {qid}")

    independent_rows: dict[tuple[str, str], dict[str, int | str]] = {}
    adjudicated_rows: dict[tuple[str, str], int | str] = {}

    for lineno, line in enumerate(labels_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"Blank line {lineno} in {labels_path}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON at line {lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Line {lineno} must be a JSON object")
        for leaked in FORBIDDEN_LABEL_KEYS:
            if leaked in row:
                raise ValueError(f"Line {lineno} leaks system provenance ({leaked!r})")
        for req in ("query_id", "doc_id", "label", "annotator", "round"):
            if req not in row:
                raise ValueError(f"Line {lineno} missing required field {req!r}")
        qid = str(row["query_id"])
        if qid not in expected_pairs:
            # Ignore other split rows so freeze-dev never touches test labels.
            continue
        doc_id = str(row["doc_id"])
        if doc_id not in expected_pairs[qid]:
            raise ValueError(f"Line {lineno}: pair ({qid}, {doc_id}) not in locked {target_split} pool")
        label = row["label"]
        if label is None:
            raise ValueError(f"Line {lineno}: ({qid}, {doc_id}) has null label — human labeling incomplete")
        if label != "unjudged" and (type(label) is not int or label not in (0, 1, 2)):
            raise ValueError(f"Line {lineno}: invalid label {label!r}")
        rnd = row["round"]
        ann = row["annotator"]
        if rnd == "independent":
            if ann not in ("A", "B"):
                raise ValueError(f"Line {lineno}: independent row must have annotator A or B, got {ann!r}")
            pair_map = independent_rows.setdefault((qid, doc_id), {})
            if ann in pair_map:
                raise ValueError(f"Line {lineno}: duplicate independent row for ({qid}, {doc_id}, {ann})")
            pair_map[ann] = label
        elif rnd == "adjudicated":
            if (qid, doc_id) in adjudicated_rows:
                raise ValueError(f"Line {lineno}: duplicate adjudicated row for ({qid}, {doc_id})")
            adjudicated_rows[(qid, doc_id)] = label
        else:
            raise ValueError(f"Line {lineno}: invalid round {rnd!r}")

    qrels: dict[str, dict[str, int]] = {qid: {} for qid in expected_pairs}
    unjudged_Explicit: dict[str, set[str]] = {qid: set() for qid in expected_pairs}
    disagreements_adjudicated = 0

    for qid, doc_ids in sorted(expected_pairs.items()):
        for doc_id in sorted(doc_ids):
            key = (qid, doc_id)
            ind = independent_rows.get(key, {})
            if set(ind.keys()) != {"A", "B"}:
                raise ValueError(
                    f"Pair ({qid}, {doc_id}) lacks independent A+B judgments (found {sorted(ind.keys())})"
                )
            la, lb = ind["A"], ind["B"]
            if la == lb:
                final_label = adjudicated_rows.get(key, la)
            else:
                if key not in adjudicated_rows:
                    raise ValueError(
                        f"Pair ({qid}, {doc_id}) has A={la!r} != B={lb!r} without an adjudicated row"
                    )
                final_label = adjudicated_rows[key]
                disagreements_adjudicated += 1

            if final_label == "unjudged":
                unjudged_Explicit[qid].add(doc_id)
            else:
                qrels[qid][doc_id] = int(final_label)

    stats = {
        "split": target_split,
        "queries": len(expected_pairs),
        "total_pooled_pairs": sum(len(v) for v in expected_pairs.values()),
        "graded_pairs": sum(len(v) for v in qrels.values()),
        "explicit_unjudged_pairs": sum(len(v) for v in unjudged_Explicit.values()),
        "disagreements_adjudicated": disagreements_adjudicated,
    }
    return qrels, unjudged_Explicit, stats


def score_method_on_split(
    rankings: dict[str, list[str]],
    qrels: dict[str, dict[str, int]],
    explicit_unjudged: dict[str, set[str]],
    query_meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute pooled metrics + unjudged_ratio@10 + intent breakdown."""
    qids = sorted(qrels.keys())
    if not qids:
        raise ValueError("Empty query split")
    per_query: dict[str, dict[str, float]] = {}
    for qid in qids:
        if qid not in rankings:
            raise ValueError(f"Missing ranking for query {qid}")
        docs = rankings[qid]
        if not isinstance(docs, list):
            raise ValueError(f"Ranking for {qid} must be a list of doc_ids")
        base = _score_query(docs, qrels[qid])
        top10 = docs[:10]
        judged_set = set(qrels[qid].keys())
        unjudged_in_top10 = sum(
            1 for d in top10 if (d not in judged_set or d in explicit_unjudged.get(qid, set()))
        )
        unjudged_ratio = (unjudged_in_top10 / len(top10)) if top10 else 1.0
        per_query[qid] = {
            "nDCG@10": base["nDCG@10"],
            "P@5": base["P@5"],
            "MRR@10": base["MRR@10"],
            "pooled Recall@100": base["Recall@100"],
            "pooled MAP@100": base["MAP@100"],
            "unjudged_ratio@10": unjudged_ratio,
        }

    metric_keys = ("nDCG@10", "P@5", "MRR@10", "pooled Recall@100", "pooled MAP@100", "unjudged_ratio@10")
    aggregate = {
        k: math.fsum(per_query[qid][k] for qid in qids) / len(qids)
        for k in metric_keys
    }

    by_intent: dict[str, list[str]] = {}
    for qid in qids:
        intent = str(query_meta.get(qid, {}).get("intent_family", "unknown"))
        by_intent.setdefault(intent, []).append(qid)
    intent_breakdown = {
        intent: {
            "n": len(iqids),
            "nDCG@10": math.fsum(per_query[q]["nDCG@10"] for q in iqids) / len(iqids),
            "P@5": math.fsum(per_query[q]["P@5"] for q in iqids) / len(iqids),
            "MRR@10": math.fsum(per_query[q]["MRR@10"] for q in iqids) / len(iqids),
            "unjudged_ratio@10": math.fsum(per_query[q]["unjudged_ratio@10"] for q in iqids) / len(iqids),
        }
        for intent, iqids in sorted(by_intent.items())
    }
    return {
        "aggregate": aggregate,
        "per_query": per_query,
        "by_intent_family": intent_breakdown,
    }


def compute_live_rankings(queries: list[dict[str, Any]], entries: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Compute rankings for the 3 pool methods + original_vi_bm25 diagnostic."""
    from scripts.build_vn_pool import retrieve_multilingual_dense, retrieve_translated_bm25
    from scholargraph.graph.b_track import load_works
    from scholargraph.retrieval.bm25 import BM25Index
    from scholargraph.retrieval.hybrid import rrf_fuse

    bm25_orders, _ = retrieve_translated_bm25(queries, entries)
    dense_orders, _ = retrieve_multilingual_dense(queries)
    hybrid_orders: dict[str, list[str]] = {}
    for q in queries:
        qid = q["query_id"]
        rows = rrf_fuse(bm25_orders[qid][:100], dense_orders[qid][:100], k=60, final_depth=100)
        hybrid_orders[qid] = [r["doc_id"] for r in rows]

    works = load_works(ROOT / "data" / "processed" / "openalex" / "works.jsonl")
    texts = {w: f"{info['title']} {info['abstract']}".strip() for w, info in works.items() if f"{info['title']} {info['abstract']}".strip()}
    bm25_vi = BM25Index(texts, k1=1.5, b=0.75)
    raw_vi_orders: dict[str, list[str]] = {}
    for q in queries:
        qid = q["query_id"]
        hits = bm25_vi.rank(str(q["text_vi"]), top_k=100)
        raw_vi_orders[qid] = [d for d, _ in hits]

    return {
        "translated_bm25": bm25_orders,
        "multilingual_dense": dense_orders,
        "vn_hybrid_rrf": hybrid_orders,
        "original_vi_bm25": raw_vi_orders,
    }


def load_rankings(
    rankings_json: Path | None,
    pool_doc: dict[str, Any],
    target_split: str,
) -> dict[str, dict[str, list[str]]]:
    if rankings_json is not None:
        if not rankings_json.is_file():
            raise FileNotFoundError(f"Missing rankings file: {rankings_json}")
        data = json.loads(rankings_json.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("rankings_json must be a JSON object mapping method -> query_id -> [doc_id]")
        for m in POOL_METHODS:
            if m not in data or not isinstance(data[m], dict):
                raise ValueError(f"rankings_json missing required pool method {m!r}")
        return data

    split_queries = [
        {
            "query_id": p["query_id"],
            "split": p["split"],
            "intent_family": p.get("intent_family", "unknown"),
            "text_vi": p["text_vi"],
        }
        for p in pool_doc.get("pools", [])
        if p.get("split") == target_split
    ]
    entries = {
        p["query_id"]: {"text_en": p["text_en"]}
        for p in pool_doc.get("pools", [])
        if p.get("split") == target_split
    }
    return compute_live_rankings(split_queries, entries)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SG-034 VN freeze-dev & eval-test CLI")
    ap.add_argument("--phase", required=True, choices=("freeze-dev", "eval-test"))
    ap.add_argument("--labels", default="data/annotations/vn_labels.jsonl")
    ap.add_argument("--pool", default="data/annotations/vn_pool.json")
    ap.add_argument("--methods-config", default="configs/vn_methods.json")
    ap.add_argument("--frozen-out", default="configs/frozen_vn.json")
    ap.add_argument("--report-dir", default="artifacts/reports")
    ap.add_argument("--rankings-json", default=None, help="Optional precomputed rankings JSON (for tests/offline)")
    args = ap.parse_args(argv)

    try:
        labels_path = Path(args.labels) if Path(args.labels).is_absolute() else ROOT / args.labels
        pool_path = Path(args.pool) if Path(args.pool).is_absolute() else ROOT / args.pool
        methods_path = Path(args.methods_config) if Path(args.methods_config).is_absolute() else ROOT / args.methods_config
        frozen_path = Path(args.frozen_out) if Path(args.frozen_out).is_absolute() else ROOT / args.frozen_out
        report_dir = Path(args.report_dir) if Path(args.report_dir).is_absolute() else ROOT / args.report_dir
        rankings_path = (
            (Path(args.rankings_json) if Path(args.rankings_json).is_absolute() else ROOT / args.rankings_json)
            if args.rankings_json
            else None
        )

        for p in (labels_path, pool_path, methods_path):
            if not p.is_file():
                return fail(f"Missing required input file: {p}")

        pool_doc = json.loads(pool_path.read_text(encoding="utf-8"))
        methods_cfg = json.loads(methods_path.read_text(encoding="utf-8"))
        query_meta = {str(p["query_id"]): p for p in pool_doc.get("pools", []) if isinstance(p, dict) and "query_id" in p}

        if args.phase == "freeze-dev":
            qrels_dev, unjudged_dev, dev_stats = resolve_split_judgments(labels_path, pool_doc, "dev")
            rankings_by_method = load_rankings(rankings_path, pool_doc, "dev")
            trials: list[dict[str, Any]] = []
            dev_results: dict[str, Any] = {}
            for method_id in POOL_METHODS:
                res = score_method_on_split(rankings_by_method[method_id], qrels_dev, unjudged_dev, query_meta)
                dev_results[method_id] = res
                trials.append(
                    {
                        "trial_id": method_id,
                        "track": "C",
                        "config": {"method": method_id},
                        "status": "COMPLETED",
                        "metrics": res["aggregate"],
                    }
                )
            selection = select_best(trials)
            frozen_payload = {
                "schema_version": 1,
                "task_id": TASK_ID,
                "module_version": MODULE_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "phase": "freeze-dev",
                "human_approved": False,
                "approval_note": "Set human_approved=true after GM-5 review and human owner approval before running --phase eval-test.",
                "selection_policy": "dev_pooled_nDCG@10_tie_break_lexicographic_method_id",
                "selected_default_method": selection["best_trial_id"],
                "selected_dev_nDCG@10": selection["nDCG@10"],
                "selection_summary": selection,
                "dev_label_stats": dev_stats,
                "dev_methods": {m: dev_results[m]["aggregate"] for m in POOL_METHODS},
                "pins": {
                    "vn_labels_sha256": _sha256(labels_path),
                    "vn_pool_sha256": _sha256(pool_path),
                    "vn_methods_sha256": _sha256(methods_path),
                    "multilingual_model": methods_cfg.get("multilingual_dense", {}).get("decision", {}),
                    "translation": methods_cfg.get("translation", {}),
                },
            }
            frozen_path.parent.mkdir(parents=True, exist_ok=True)
            frozen_path.write_text(json.dumps(frozen_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "status": "FROZEN_DEV_PENDING_APPROVAL",
                        "selected_default_method": selection["best_trial_id"],
                        "dev_nDCG@10": selection["nDCG@10"],
                        "frozen_out": str(frozen_path),
                    },
                    indent=2,
                )
            )
            return 0

        # --phase eval-test
        if not frozen_path.is_file():
            return fail(f"Cannot run eval-test before freeze-dev: missing {frozen_path}")
        frozen_doc = json.loads(frozen_path.read_text(encoding="utf-8"))
        if frozen_doc.get("human_approved") is not True:
            return fail(
                "Refusing eval-test: configs/frozen_vn.json does not have human_approved=true "
                "(requires GM-5 review + human owner approval first)."
            )
        if frozen_doc["pins"]["vn_pool_sha256"] != _sha256(pool_path):
            return fail(f"Refusing eval-test: {pool_path} is not the pool pinned at freeze-dev (vn_pool_sha256).")
        selected_method = frozen_doc.get("selected_default_method")
        if selected_method not in POOL_METHODS:
            return fail(f"Invalid selected_default_method in frozen_vn.json: {selected_method!r}")

        qrels_test, unjudged_test, test_stats = resolve_split_judgments(labels_path, pool_doc, "test")
        rankings_by_method = load_rankings(rankings_path, pool_doc, "test")

        eval_methods = list(POOL_METHODS) + [
            m for m in DIAGNOSTIC_METHODS if m in rankings_by_method
        ]
        test_results: dict[str, Any] = {}
        for method_id in eval_methods:
            test_results[method_id] = score_method_on_split(
                rankings_by_method[method_id], qrels_test, unjudged_test, query_meta
            )

        report_dir.mkdir(parents=True, exist_ok=True)
        out_json = {
            "schema_version": 1,
            "task_id": TASK_ID,
            "module_version": MODULE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "frozen_vn_sha256": _sha256(frozen_path),
            "vn_labels_sha256": _sha256(labels_path),
            "selected_default_method": selected_method,
            "test_label_stats": test_stats,
            "methods": test_results,
            "scope_note": "Small internal cross-lingual pilot (20 test queries on OpenAlex text-subset); not comparable to English BEIR benchmarks.",
        }
        (report_dir / "vn_results.json").write_text(
            json.dumps(out_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        lines = [
            "# Kết quả đánh giá truy vấn tiếng Việt — Track C (SG-034)",
            "",
            f"- **Phương pháp mặc định đã khóa trên dev:** `{selected_method}`",
            f"- **SHA-256 `configs/frozen_vn.json`:** `{out_json['frozen_vn_sha256']}`",
            f"- **SHA-256 `data/annotations/vn_labels.jsonl`:** `{out_json['vn_labels_sha256']}`",
            f"- **Số truy vấn test:** `{test_stats['queries']}` (tổng `{test_stats['total_pooled_pairs']}` cặp trong pool, `{test_stats['graded_pairs']}` cặp có điểm 0/1/2, `{test_stats['explicit_unjudged_pairs']}` cặp `unjudged`).",
            "- **Lưu ý phạm vi:** Đây là tập pilot nội bộ cỡ nhỏ trên OpenAlex text-subset (18.250 bài); tuyệt đối không gộp điểm với BEIR tiếng Anh và không tuyên bố chuẩn quốc tế.",
            "",
            "## Bảng 1 — Kết quả tổng hợp trên tập Test (20 truy vấn)",
            "",
            "| Phương pháp | Vai trò | nDCG@10 | P@5 | MRR@10 | pooled Recall@100 | pooled MAP@100 | Unjudged@10 |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for method_id in eval_methods:
            agg = test_results[method_id]["aggregate"]
            role = "Default (frozen on dev)" if method_id == selected_method else (
                "Pool candidate" if method_id in POOL_METHODS else "Diagnostic (non-pool)"
            )
            lines.append(
                f"| `{method_id}` | {role} | {agg['nDCG@10']:.4f} | {agg['P@5']:.4f} | "
                f"{agg['MRR@10']:.4f} | {agg['pooled Recall@100']:.4f} | "
                f"{agg['pooled MAP@100']:.4f} | {agg['unjudged_ratio@10']:.4f} |"
            )
        lines.extend(
            [
                "",
                f"## Bảng 2 — Phân rã theo nhóm chủ đề/ý định (`{selected_method}`)",
                "",
                "| Intent family | n | nDCG@10 | P@5 | MRR@10 | Unjudged@10 |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for intent, row in test_results[selected_method]["by_intent_family"].items():
            lines.append(
                f"| `{intent}` | {row['n']} | {row['nDCG@10']:.4f} | {row['P@5']:.4f} | "
                f"{row['MRR@10']:.4f} | {row['unjudged_ratio@10']:.4f} |"
            )
        lines.append("")
        (report_dir / "vn_results.md").write_text("\n".join(lines), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "COMPLETED",
                    "selected_default_method": selected_method,
                    "test_nDCG@10": test_results[selected_method]["aggregate"]["nDCG@10"],
                    "report_md": str(report_dir / "vn_results.md"),
                },
                indent=2,
            )
        )
        return 0
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
