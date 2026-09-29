"""VN label agreement: linearly-weighted kappa + raw agreement (SG-033 tool).

Reads a FILLED data/annotations/vn_labels.jsonl (label 0/1/2 or "unjudged",
annotator A|B, round independent|adjudicated; NO system-provenance fields
allowed) and writes annotation_agreement.json/.md BEFORE any adjudication
discussion. Raw labels are preserved; adjudicated rows are separate rows.

Kappa weights per ANNOTATION_GUIDE: w = 1 - |a-b|/2 over grades {0,1,2};
"unjudged" rows are excluded from kappa with an explicit count (never scored
as 0). Degenerate distributions yield kappa undefined (null), never a number.

Usage: score_vn_agreement.py [--labels PATH] [--output-dir DIR]
Exit 1 on incomplete/invalid labels (missing pairs, unknown grades, single
annotator, provenance leak).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TASK_ID = "SG-033"
MODULE_VERSION = "sg033-1.0.0"
GRADES = (0, 1, 2)
FORBIDDEN_KEYS = ("method", "system", "score", "rank", "provenance", "source")


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _weight(a: int, b: int) -> float:
    return 1.0 - abs(a - b) / 2.0


def weighted_kappa(pairs: list[tuple[int, int]]) -> float | None:
    """Linearly-weighted Cohen's kappa (guide weights); None when degenerate."""
    if not pairs:
        raise ValueError("No graded pairs for kappa")
    n = len(pairs)
    labels_a = [a for a, _ in pairs]
    labels_b = [b for _, b in pairs]
    if len(set(labels_a)) < 2 and len(set(labels_b)) < 2:
        return None  # degenerate distribution — undefined, never a number
    observed = sum(_weight(a, b) for a, b in pairs) / n
    expected = 0.0
    for g in GRADES:
        for h in GRADES:
            expected += (labels_a.count(g) / n) * (labels_b.count(h) / n) * _weight(g, h)
    if expected == 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def load_labels(path: Path) -> dict[tuple[str, str], dict[str, object]]:
    by_pair: dict[tuple[str, str], dict[str, object]] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"Blank line {lineno} in {path}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON line {lineno}: {exc}")
        for key in ("query_id", "doc_id", "label", "annotator", "round"):
            if key not in row:
                raise ValueError(f"Line {lineno} lacks {key!r}")
        for leaked in FORBIDDEN_KEYS:
            if leaked in row:
                raise ValueError(f"Line {lineno} leaks system provenance ({leaked!r}); blinding broken")
        label = row["label"]
        if label is None:
            raise ValueError(f"Line {lineno} unlabeled (label null) — labeling incomplete")
        if label != "unjudged" and label not in (0, 1, 2):
            raise ValueError(f"Line {lineno} has invalid label {label!r}")
        if row["annotator"] not in ("A", "B"):
            raise ValueError(f"Line {lineno} has invalid annotator {row['annotator']!r}")
        if row["round"] not in ("independent", "adjudicated"):
            raise ValueError(f"Line {lineno} has invalid round {row['round']!r}")
        key = (str(row["query_id"]), str(row["doc_id"]))
        by_pair.setdefault(key, {})[str(row["annotator"])] = row
    return by_pair


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="VN label agreement (SG-033)")
    ap.add_argument("--labels", default="data/annotations/vn_labels.jsonl")
    ap.add_argument("--output-dir", default="artifacts/reports")
    args = ap.parse_args(argv)
    try:
        lpath = ROOT / args.labels
        if not lpath.is_file():
            return fail(f"Missing labels file: {args.labels}")
        by_pair = load_labels(lpath)
        independent = {k: v for k, v in by_pair.items()
                       if v.get("A", {}).get("round") == "independent"
                       and v.get("B", {}).get("round") == "independent"}
        if not independent:
            return fail("No independent A+B pair found (labeling not started or round mislabeled)")
        single = [k for k, v in by_pair.items() if set(v) != {"A", "B"}]
        if single:
            return fail(f"{len(single)} pairs lack a second annotator (first: {single[0]})")
        graded = [(a["label"], b["label"]) for (a, b) in
                  ((v["A"], v["B"]) for v in independent.values())
                  if a["label"] != "unjudged" and b["label"] != "unjudged"]
        unjudged = sum(1 for v in independent.values()
                       if v["A"]["label"] == "unjudged" or v["B"]["label"] == "unjudged")
        exact = sum(1 for a, b in graded if a == b)
        confusion: dict[str, dict[str, int]] = {str(g): {str(h): 0 for h in GRADES} for g in GRADES}
        for a, b in graded:
            confusion[str(a)][str(b)] += 1
        kappa = weighted_kappa(graded) if graded else None
        payload = {"schema_version": 1, "task_id": TASK_ID, "module_version": MODULE_VERSION,
                   "generated_at": datetime.now(timezone.utc).isoformat(),
                   "labels_file": args.labels,
                   "pair_count": len(independent),
                   "graded_pairs": len(graded),
                   "unjudged_pairs": unjudged,
                   "raw_agreement": (exact / len(graded)) if graded else None,
                   "linearly_weighted_kappa": kappa,
                   "kappa_note": ("undefined (degenerate distribution)" if kappa is None else "as computed"),
                   "confusion_matrix": confusion,
                   "original_labels_preserved": True}
        outdir = ROOT / args.output_dir
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "annotation_agreement.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md = ["# Annotation agreement - before adjudication (SG-033)", "",
              f"Pairs (independent A+B): {payload['pair_count']}; graded: {payload['graded_pairs']}; "
              f"unjudged: {payload['unjudged_pairs']}.",
              f"Raw agreement: {payload['raw_agreement']}; linearly-weighted kappa: {payload['linearly_weighted_kappa']} "
              f"({payload['kappa_note']}).",
              "",
              "## Confusion (A rows x B cols)",
              "",
              "```json",
              json.dumps(confusion, indent=2),
              "```",
              "",
              "Raw labels preserved in vn_labels.jsonl; adjudication rows are separate.",
              ""]
        (outdir / "annotation_agreement.md").write_text("\n".join(md), encoding="utf-8")
        print(json.dumps({"pairs": payload["pair_count"], "kappa": kappa,
                          "raw_agreement": payload["raw_agreement"]}, indent=2))
    except ValueError as exc:
        return fail(f"LabelError: {exc}")
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        import traceback
        traceback.print_exc()
        return fail(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
