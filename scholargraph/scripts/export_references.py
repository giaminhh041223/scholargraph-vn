"""Reference export with explicit missing-data policy — task SG-038.

Reads the frozen SciFact corpus and the processed OpenAlex core snapshot and
emits structured reference records (title/year/doi/url/venue) plus a plain
citation line. MISSING metadata stays ``null`` in structured output and
``[không có]`` in the citation line — never fabricated, never guessed.

Usage:
    PYTHONPATH=src python scripts/export_references.py \
        --doc-ids beir:scifact:195352 openalex:W2115584760 \
        --output artifacts/reports/demo_references.json

Exit codes: 0 on success, 1 on any missing input, unknown ID, or IO failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SCIFACT_CORPUS = PROJECT_ROOT / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl"
OPENALEX_WORKS = PROJECT_ROOT / "data" / "processed" / "openalex" / "works.jsonl"
MISSING = "[không có]"


class ExportError(RuntimeError):
    """Fatal export failure; the CLI must exit 1."""


def _load_scifact() -> dict[str, dict[str, Any]]:
    if not SCIFACT_CORPUS.is_file():
        raise ExportError(f"Missing frozen corpus: {SCIFACT_CORPUS}")
    out: dict[str, dict[str, Any]] = {}
    content = SCIFACT_CORPUS.read_text(encoding="utf-8").rstrip("\n")
    for lineno, line in enumerate(content.split("\n"), 1):
        # split("\n") only: str.splitlines() would also split on raw U+2028/U+2029
        # characters inside JSON string values (abstracts) and corrupt the line.
        # rstrip("\n") drops only the trailing final newline; interior blank lines stay errors.
        if not line.strip():
            raise ExportError(f"Blank line in {SCIFACT_CORPUS} at {lineno}")
        row = json.loads(line)
        out[f"beir:scifact:{row['_id']}"] = row
    return out


def _load_openalex() -> dict[str, dict[str, Any]]:
    if not OPENALEX_WORKS.is_file():
        raise ExportError(f"Missing processed snapshot: {OPENALEX_WORKS}")
    out: dict[str, dict[str, Any]] = {}
    content = OPENALEX_WORKS.read_text(encoding="utf-8").rstrip("\n")
    for lineno, line in enumerate(content.split("\n"), 1):
        # split("\n") only: str.splitlines() would also split on raw U+2028/U+2029
        # characters inside JSON string values (abstracts) and corrupt the line.
        # rstrip("\n") drops only the trailing final newline; interior blank lines stay errors.
        if not line.strip():
            raise ExportError(f"Blank line in {OPENALEX_WORKS} at {lineno}")
        row = json.loads(line)
        out[f"openalex:{row['id'].rsplit('/', 1)[-1]}"] = row
    return out


def _normalize_doi(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    doi = raw.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi or None


def export_record(doc_id: str, scifact: dict[str, dict[str, Any]],
                  openalex: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if doc_id.startswith("beir:scifact:"):
        row = scifact.get(doc_id)
        if row is None:
            raise ExportError(f"Unknown document: {doc_id}")
        record = {
            "doc_id": doc_id,
            "title": str(row.get("title") or "").strip() or None,
            "year": None,           # frozen SciFact corpus carries no year metadata
            "doi": None,            # ... and no DOI metadata
            "venue": None,
            "url": None,
            "source_corpus": "beir-scifact-frozen",
            "abstract_present": bool(str(row.get("text") or "").strip()),
        }
    elif doc_id.startswith("openalex:"):
        row = openalex.get(doc_id)
        if row is None:
            raise ExportError(f"Unknown document: {doc_id}")
        doi = _normalize_doi(row.get("doi"))
        oa_id = doc_id.split(":", 1)[1]
        record = {
            "doc_id": doc_id,
            "title": str(row.get("title") or "").strip() or None,
            "year": row.get("publication_year") if isinstance(row.get("publication_year"), int) else None,
            "doi": doi,
            "venue": None,
            "url": (f"https://doi.org/{doi}" if doi else f"https://openalex.org/{oa_id}"),
            "source_corpus": "openalex-core-text-subset",
            "abstract_present": bool(row.get("abstract_inverted_index")),
        }
    else:
        raise ExportError(f"Unsupported doc_id namespace: {doc_id}")

    parts = []
    if record["title"]:
        parts.append(record["title"])
    year = record["year"] if record["year"] is not None else MISSING
    parts.append(str(year))
    if record["venue"]:
        parts.append(record["venue"])
    if record["doi"]:
        parts.append(f"https://doi.org/{record['doi']}")
    citation = ". ".join(parts) + "."
    if record["url"] and not record["doi"] and record["url"] not in citation:
        citation += f" {record['url']}"
    record["citation_text"] = citation
    return record


def export_docs(doc_ids: list[str]) -> dict[str, Any]:
    scifact = _load_scifact()
    openalex = _load_openalex()
    records = [export_record(doc_id, scifact, openalex) for doc_id in doc_ids]
    return {
        "schema_version": 1,
        "artifact_kind": "reference_export",
        "generated_by": "scripts/export_references.py (SG-038)",
        "missing_policy": "missing metadata is null in structured fields and '[không có]' in citation_text; never fabricated",
        "counts": {"requested": len(doc_ids), "exported": len(records),
                   "with_doi": sum(1 for r in records if r["doi"]),
                   "missing_doi": sum(1 for r in records if not r["doi"]),
                   "missing_year": sum(1 for r in records if r["year"] is None)},
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export references with explicit missing policy (SG-038).")
    parser.add_argument("--doc-ids", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = export_docs(args.doc_ids)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except ExportError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"Exported {payload['counts']['exported']} records -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
