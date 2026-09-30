"""BibTeX and JSON library export for EXT-04A, no network calls."""

from __future__ import annotations

import json
import re
from typing import Literal

from .contracts import LibraryEntry


def bibtex_escape(value: str) -> str:
    """Escape BibTeX specials, newlines, braces and backslash."""
    if type(value) is not str:
        raise ValueError("bibtex value must be str")
    cleaned = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    out: list[str] = []
    for ch in cleaned:
        if ch == "\\":
            out.append("{\\textbackslash}")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ch == "#":
            out.append("\\#")
        elif ch == "$":
            out.append("\\$")
        elif ch == "%":
            out.append("\\%")
        elif ch == "&":
            out.append("\\&")
        elif ch == "_":
            out.append("\\_")
        elif ch == "^":
            out.append("{\\textasciicircum}")
        elif ch == "~":
            out.append("{\\textasciitilde}")
        else:
            out.append(ch)
    return "".join(out)


def stable_bibtex_key(canonical_id: str, used: set[str]) -> str:
    """Stable ASCII key from canonical id without fabrication."""
    if type(canonical_id) is not str or not canonical_id.strip():
        raise ValueError("canonical id must be nonempty str")
    base_chars: list[str] = []
    for ch in canonical_id.strip():
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in "_:-":
            base_chars.append(ch)
        else:
            base_chars.append("_")
    base = "".join(base_chars)
    if not base:
        base = "paper"
    if base[0].isdigit():
        base = "paper_" + base
    if len(base) > 64:
        base = base[:64]
    candidate = base
    suffix = 2
    while candidate in used:
        tail = "_" + str(suffix)
        head_len = 64 - len(tail)
        head = base[:head_len] if len(base) > head_len else base
        candidate = head + tail
        suffix += 1
    used.add(candidate)
    return candidate


def _revalidate_entry(entry: LibraryEntry) -> LibraryEntry:
    raw = entry.model_dump_json().encode("utf-8")
    return LibraryEntry.model_validate_json(raw)


def export_json(entries: list[LibraryEntry]) -> bytes:
    """Export library as UTF-8 JSON array with full provenance."""
    if type(entries) is not list:
        raise ValueError("entries must be list")
    validated: list[LibraryEntry] = []
    for entry in entries:
        if not isinstance(entry, LibraryEntry):
            raise ValueError("entries must be LibraryEntry")
        validated.append(_revalidate_entry(entry))
    validated.sort(key=lambda e: (e.saved_at, e.canonical_id))
    payload = [e.model_dump(mode="json") for e in validated]
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return text.encode("utf-8")


def export_bibtex(entries: list[LibraryEntry]) -> bytes:
    """Export library as UTF-8 BibTeX, missing fields omitted."""
    if type(entries) is not list:
        raise ValueError("entries must be list")
    validated: list[LibraryEntry] = []
    for entry in entries:
        if not isinstance(entry, LibraryEntry):
            raise ValueError("entries must be LibraryEntry")
        validated.append(_revalidate_entry(entry))
    validated.sort(key=lambda e: e.canonical_id)
    used: set[str] = set()
    blocks: list[str] = []
    for entry in validated:
        key = stable_bibtex_key(entry.canonical_id, used)
        display = entry.hit.display
        lines = ["@misc{" + key + ","]
        lines.append("  title = {" + bibtex_escape(display.title) + "},")
        if display.authors is not None and len(display.authors) > 0:
            joined = " and ".join(display.authors)
            lines.append("  author = {" + bibtex_escape(joined) + "},")
        if display.publication_year is not None:
            lines.append("  year = {" + str(display.publication_year) + "},")
        if display.doi is not None:
            lines.append("  doi = {" + bibtex_escape(display.doi) + "},")
        lines.append("  url = {" + bibtex_escape(display.landing_url) + "},")
        if display.venue is not None:
            lines.append("  journal = {" + bibtex_escape(display.venue) + "},")
        if display.pdf_url is not None:
            lines.append("  howpublished = {\\url{" + bibtex_escape(display.pdf_url) + "}},")
        provenance = "source:" + display.source + ";snapshot:" + entry.snapshot_id + ";incomplete:" + ("true" if entry.incomplete_sources else "false")
        lines.append("  note = {" + bibtex_escape(provenance) + "}")
        lines.append("}")
        blocks.append("\n".join(lines))
    text = "\n\n".join(blocks)
    if blocks:
        text += "\n"
    return text.encode("utf-8")


def export_library_bytes(entries: list[LibraryEntry], format: Literal["json", "bibtex"]) -> bytes:
    """Dispatch by exact format, unknown format fails."""
    if format == "json":
        return export_json(entries)
    if format == "bibtex":
        return export_bibtex(entries)
    raise ValueError("unknown export format")
