"""Reproduce the SG-024 descriptive age-exposure measurement (committed provenance).

Reads the frozen OpenAlex snapshot + SG-016 masked split, pairs every selected
query source with all valid-year works (year <= year(source)), and reports how
the age weights of each lambda grid value redistribute top-10 exposure under
UNIFORM fused scores (weight-only behavior, NOT a relevance measurement).

Writes artifacts/reports/age_exposure.json with input hashes + command.
Exit 1 on any missing/malformed resource (no silent bypass).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAMBDAS = (0.0, 0.01, 0.03, 0.05, 0.1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError:
        print("FAIL: numpy is required", file=sys.stderr)
        return 1
    try:
        root = Path(__file__).resolve().parents[1]
        works_p = root / "data" / "processed" / "openalex" / "works.jsonl"
        split_p = root / "data" / "processed" / "graph" / "split_queries.json"
        out_p = root / "artifacts" / "reports" / "age_exposure.json"
        years: dict[str, int | None] = {}
        # NOTE: iterate the file object (universal newlines), NOT splitlines():
        # abstracts may embed unicode line boundaries that splitlines() would
        # treat as record separators and corrupt JSON records.
        with open(works_p, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    print(f"FAIL: blank line {lineno} in works.jsonl", file=sys.stderr)
                    return 1
                o = json.loads(line)
                raw = str(o.get("id", ""))
                wid = "openalex:" + raw.split("/")[-1]
                years[wid] = o.get("publication_year")
        sq = json.loads(split_p.read_text(encoding="utf-8"))
        queries = sq["cohorts"]["dev"]["selected"] + sq["cohorts"]["test"]["selected"]
        valid = np.array([y for y in years.values() if isinstance(y, int) and 1900 <= y <= 2100])
        n_missing = sum(1 for y in years.values() if y is None)
        n_oor = sum(1 for y in years.values() if isinstance(y, int) and not 1900 <= y <= 2100)
        table = {}
        total_pairs = 0
        disc10 = np.array([1.0 / np.log2(i + 2) for i in range(10)])
        disc_total = float(disc10.sum())
        for lam in LAMBDAS:
            top_gaps: list = []
            exp_b = {"0-2y": 0.0, "3-5y": 0.0, "6-10y": 0.0, ">=11y": 0.0}
            nq = 0
            for q in queries:
                yu = years.get(q)
                if not isinstance(yu, int):
                    continue
                cand = valid[valid <= yu]
                total_pairs += len(cand) if lam == LAMBDAS[0] else 0
                gaps = yu - cand
                w = np.exp(-lam * gaps)
                top_idx = np.argsort(-w, kind="stable")[:10]
                tg = gaps[top_idx]
                top_gaps.extend(tg.tolist())
                for rank, g in enumerate(tg):
                    key = "0-2y" if g <= 2 else ("3-5y" if g <= 5 else ("6-10y" if g <= 10 else ">=11y"))
                    exp_b[key] += float(disc10[rank]) / disc_total
                nq += 1
            top_gaps = np.array(top_gaps)
            table[str(lam)] = {
                "top10_0-2y": float(np.mean(top_gaps <= 2)),
                "top10_3-5y": float(np.mean((top_gaps >= 3) & (top_gaps <= 5))),
                "top10_6-10y": float(np.mean((top_gaps >= 6) & (top_gaps <= 10))),
                "top10_gt10y": float(np.mean(top_gaps > 10)),
                "exposure_b_at_10_mean": {b: v / nq for b, v in exp_b.items()},
            }
        payload = {
            "schema_version": 1, "task_id": "SG-024",
            "module_version": "sg024-1.0.0",
            "command": ["scripts/age_exposure_audit.py"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {"works": {"path": "data/processed/openalex/works.jsonl", "sha256": sha256(works_p)},
                       "split": {"path": "data/processed/graph/split_queries.json", "sha256": sha256(split_p)}},
            "universe": {"works": len(years), "valid_year": int(len(valid)), "missing_year": n_missing,
                         "out_of_range_year": n_oor, "queries": len(queries), "pairs": total_pairs},
            "method": "uniform fused=1.0 isolates the age-weight effect; NOT a relevance measurement",
            "lambda_grid": list(LAMBDAS),
            "exposure": table,
        }
        out_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(out_p), "pairs": total_pairs}, indent=2))
    except FileNotFoundError as exc:
        print(f"FAIL: Missing required file: {exc}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL: Malformed input: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
