"""Synthetic export tests for EXT-04A, no live data."""
import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
import pytest
from scholargraph.public_search.contracts import LibraryEntry
from scholargraph.public_search.contracts import PaperRecord
from scholargraph.public_search.contracts import RankedHit
from scholargraph.public_search.export import bibtex_escape
from scholargraph.public_search.export import export_bibtex
from scholargraph.public_search.export import export_json
from scholargraph.public_search.export import export_library_bytes
from scholargraph.public_search.export import stable_bibtex_key

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 64


def paper_row(title="Synthetic title"):
    nullable = ["abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url", "license", "open_access_status", "citation_count", "authors"]
    row = {"source": "openalex", "source_id": "W1", "title": title, "landing_url": "https://example.org/paper", "retrieved_at": datetime(2026, 9, 30, tzinfo=timezone.utc), "raw_sha256": SHA, "parser_version": "synthetic-1", "authors_availability": "missing", "missing_fields": nullable, "field_provenance": {}}
    row.update({name: None for name in nullable})
    row["field_provenance"] = {key: [{"source": "openalex", "source_id": "W1", "raw_sha256": SHA, "raw_field": key}] for key in ["title", "source_id", "landing_url"]}
    return row


def entry_for(canonical, title="Synthetic title"):
    rec = PaperRecord.model_validate(paper_row(title))
    hit = RankedHit(canonical_id=canonical, rank=1, score=1.0 / 61.0, display=rec, source_records=[rec], source_ranks={"openalex": 1}, conflicts={})
    return LibraryEntry(canonical_id=canonical, snapshot_id="snap-1", saved_at=datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc), hit=hit, incomplete_sources=False)


def test_json_contains_full_provenance():
    entries = [entry_for("synthetic:W1"), entry_for("synthetic:W2", "Second title")]
    raw = export_json(entries)
    payload = json.loads(raw.decode("utf-8"))
    assert len(payload) == 2
    assert payload[0]["canonical_id"] == "synthetic:W1"
    assert "field_provenance" in payload[0]["hit"]["display"]
    assert payload[0]["hit"]["display"]["title"] == "Synthetic title"
    second = LibraryEntry.model_validate_json(json.dumps(payload[1]).encode("utf-8"))
    assert second.canonical_id == "synthetic:W2"


def test_bibtex_escapes_and_omits_missing():
    fixture = json.loads((ROOT / "tests" / "fixtures" / "public_search" / "muse" / "store" / "special_chars.json").read_text(encoding="utf-8"))
    assert fixture["synthetic"] is True
    titles = [c["title"] for c in fixture["cases"]]
    entries = [entry_for("synthetic:ESC" + str(i), t) for i, t in enumerate(titles)]
    out = export_bibtex(entries).decode("utf-8")
    assert "\\#" in out and "\\$" in out and "\\%" in out and "\\&" in out
    assert "\\_" in out and "\\{" in out and "\\}" in out
    assert "{\\textbackslash}" in out
    assert "{\\textasciicircum}" in out and "{\\textasciitilde}" in out
    assert "author =" not in out
    assert "year =" not in out and "doi =" not in out
    assert "\n" not in [l for l in out.split("title = {")[1].split("}")[0] if l == "\n"]


def test_bibtex_newline_and_backslash():
    entry = entry_for("synthetic:NL", "Line one\nLine two \\ end")
    out = export_bibtex([entry]).decode("utf-8")
    assert "Line one Line two" in out
    assert "{\\textbackslash}" in out
    assert bibtex_escape("a\nb") == "a b"


def test_bibtex_stable_keys_and_deterministic():
    entries = [entry_for("synthetic:B"), entry_for("synthetic:A")]
    first = export_bibtex(entries)
    second = export_bibtex(list(reversed(entries)))
    assert first == second
    text = first.decode("utf-8")
    assert text.index("synthetic:A") < text.index("synthetic:B")
    used: set[str] = set()
    k1 = stable_bibtex_key("synthetic:W1", used)
    k2 = stable_bibtex_key("synthetic:W1!", used)
    assert k1 != k2 and k1 == "synthetic:W1"


def test_unknown_format_fails():
    with pytest.raises(ValueError):
        export_library_bytes([entry_for("synthetic:X")], "xml")
    assert export_library_bytes([], "json") == b"[]"
    assert export_library_bytes([], "bibtex") == b""


def test_no_fallback_get_in_export():
    src = (ROOT / "src" / "scholargraph" / "public_search" / "export.py").read_text(encoding="utf-8")
    assert ".get(" not in src


def test_sidecar_marks_synthetic():
    sidecar = json.loads((ROOT / "tests" / "fixtures" / "public_search" / "muse" / "store" / "special_chars.sidecar.json").read_text(encoding="utf-8"))
    assert sidecar["synthetic"] is True
    manifest = json.loads((ROOT / "tests" / "fixtures" / "public_search" / "muse" / "store" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True


def _entry_with_time(canonical, saved_at):
    rec = PaperRecord.model_validate(paper_row("Title " + canonical))
    hit = RankedHit(canonical_id=canonical, rank=1, score=1.0 / 61.0, display=rec, source_records=[rec], source_ranks={"openalex": 1}, conflicts={})
    return LibraryEntry(canonical_id=canonical, snapshot_id="snap-1", saved_at=saved_at, hit=hit, incomplete_sources=False)


def test_export_json_mixed_timezone_chronological():
    from datetime import timedelta
    t_a = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    tz7 = timezone(timedelta(hours=7))
    t_b = datetime(2026, 9, 30, 20, 0, 0, tzinfo=tz7)
    assert t_b < t_a
    assert t_a.isoformat() < t_b.isoformat()
    entry_a = _entry_with_time("paper:A", t_a)
    entry_b = _entry_with_time("paper:B", t_b)
    out = json.loads(export_json([entry_a, entry_b]).decode("utf-8"))
    assert [r["canonical_id"] for r in out] == ["paper:B", "paper:A"]
    out_rev = json.loads(export_json([entry_b, entry_a]).decode("utf-8"))
    assert [r["canonical_id"] for r in out_rev] == ["paper:B", "paper:A"]


def test_export_json_equivalent_instants_tie_break():
    from datetime import timedelta
    t1 = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 30, 21, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    assert t1 == t2
    assert t1.isoformat() != t2.isoformat()
    entry_a = _entry_with_time("paper:A", t1)
    entry_b = _entry_with_time("paper:B", t2)
    out = json.loads(export_json([entry_b, entry_a]).decode("utf-8"))
    assert [r["canonical_id"] for r in out] == ["paper:A", "paper:B"]
    assert out[0]["saved_at"] != out[1]["saved_at"]
