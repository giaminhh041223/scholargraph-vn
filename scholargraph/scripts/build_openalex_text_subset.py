"""Build the text-only OpenAlex dense universe (ADR-017, SG-026 follow-up).

Reads the frozen core snapshot, verifies its sha256 pin, and writes the
subset of works having a title and/or abstract (dense-encodable), preserving
canonical-ID-ascending order, plus a manifest pinning the subset sha256 and
recording the EXCLUDED textless works explicitly (never silent).

Writes:
  data/processed/openalex/works_text.jsonl
  data/manifests/openalex_core_text.json
Exit 1 on any missing/malformed resource, count/order/hash mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTLESS_IDS = [
    "openalex:W126924136",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the text-only OpenAlex dense universe (ADR-017).")
    parser.add_argument(
        "--parent-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "openalex_core.json",
        help="Path to parent OpenAlex core manifest JSON.",
    )
    parser.add_argument(
        "--input-data",
        type=Path,
        default=ROOT / "data" / "processed" / "openalex" / "works.jsonl",
        help="Path to parent OpenAlex works.jsonl.",
    )
    parser.add_argument(
        "--output-data",
        type=Path,
        default=ROOT / "data" / "processed" / "openalex" / "works_text.jsonl",
        help="Path to output works_text.jsonl.",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "openalex_core_text.json",
        help="Path to output openalex_core_text.json manifest.",
    )
    args = parser.parse_args(argv)
    try:
        parent = json.loads(args.parent_manifest.read_text(encoding="utf-8"))
        src = args.input_data
        pinned = parent["artifacts"]["works_jsonl"]["sha256"]
        if sha256(src) != pinned:
            return fail("parent snapshot sha256 mismatch; refusing to derive a subset")
        kept: list[str] = []
        dropped: list[dict] = []
        prev_id = ""
        with open(src, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    return fail(f"Blank line {lineno} in snapshot")
                o = json.loads(line)
                raw = str(o.get("id", ""))
                wid = "openalex:" + raw.split("/")[-1]
                if wid <= prev_id:
                    return fail(f"Snapshot order violated at line {lineno} (ADR-017 needs canonical order)")
                prev_id = wid
                title = (o.get("title") or "").strip()
                abs_ = o.get("abstract_inverted_index")
                if isinstance(abs_, dict):
                    has_abstract = len(abs_) > 0
                else:
                    abs_ = o.get("abstract") or ""
                    has_abstract = bool(str(abs_).strip())
                has_text = bool(title or has_abstract)
                if has_text:
                    kept.append(line if line.endswith("\n") else line + "\n")
                else:
                    dropped.append({"line": lineno, "id": wid})
        dropped_ids = sorted(d["id"] for d in dropped)
        if dropped_ids != sorted(TEXTLESS_IDS):
            return fail(f"Textless set changed: got {dropped_ids}; pinned expectation differs — needs human review, refusing")
        out_data = args.output_data
        out_data.parent.mkdir(parents=True, exist_ok=True)
        out_data.write_text("".join(kept), encoding="utf-8")
        manifest = {
            "schema_version": 1, "artifact_kind": "openalex_text_subset_manifest",
            "task_id": "SG-026", "adr": "ADR-017 (proposed)",
            "status": "COMPLETED",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parent_snapshot": {"manifest": "data/manifests/openalex_core.json",
                                "works_jsonl": "data/processed/openalex/works.jsonl",
                                "sha256": pinned},
            "postprocess": {"processed_works": len(kept), "output_order": "canonical ID ascending"},
            "artifacts": {"works_jsonl": {"path": "data/processed/openalex/works_text.jsonl",
                                          "sha256": sha256(out_data), "bytes": out_data.stat().st_size}},
            "excluded_textless_works": dropped,
            "counts": {"parent_works": len(kept) + len(dropped), "text_works": len(kept),
                       "excluded": len(dropped)},
        }
        out_manifest = args.output_manifest
        out_manifest.parent.mkdir(parents=True, exist_ok=True)
        out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"subset": len(kept), "excluded": len(dropped),
                          "sha256": manifest["artifacts"]["works_jsonl"]["sha256"]}, indent=2))
    except FileNotFoundError as exc:
        return fail(f"Missing required file: {exc}")
    except (json.JSONDecodeError, KeyError) as exc:
        return fail(f"Malformed input: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
