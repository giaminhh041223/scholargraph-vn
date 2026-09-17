"""SG-038 demo/export tests — real frozen data, explicit missing policy.

Covers the export module contract: known docs export with real metadata,
missing metadata stays null + '[không có]' (never fabricated), unknown IDs and
foreign namespaces fail loudly (exit 1), and the pinned demo config is valid.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "export_references.py"
DEMO = PROJECT_ROOT / "configs" / "demo.json"

spec = importlib.util.spec_from_file_location("export_references", SCRIPT)
export_references = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_references)


@pytest.fixture(scope="module")
def corpora():
    return (export_references._load_scifact(), export_references._load_openalex())


def test_scifact_record_missing_metadata_is_null(corpora):
    scifact, _ = corpora
    rec = export_references.export_record("beir:scifact:195352", scifact, {})
    assert rec["title"] and rec["abstract_present"] is True
    assert rec["year"] is None and rec["doi"] is None and rec["url"] is None
    assert "[không có]" in rec["citation_text"]  # year is missing -> explicit marker
    assert "https://doi.org/" not in rec["citation_text"]


def test_openalex_record_has_real_metadata(corpora):
    _, openalex = corpora
    rec = export_references.export_record("openalex:W1678356000", {}, openalex)
    assert rec["year"] == 2001
    assert rec["doi"] and rec["url"] == f"https://doi.org/{rec['doi']}"
    assert rec["citation_text"].startswith(rec["title"])


def test_openalex_no_doi_gets_canonical_url(corpora):
    _, openalex = corpora
    # The frozen snapshot contains 1,538 works without DOI (SG-015 quality
    # report); pick one dynamically instead of pinning an ID that may gain one.
    no_doi = next(doc_id for doc_id, row in sorted(openalex.items())
                  if export_references._normalize_doi(row.get("doi")) is None)
    rec = export_references.export_record(no_doi, {}, openalex)
    assert rec["doi"] is None
    assert rec["url"] == f"https://openalex.org/{no_doi.split(':', 1)[1]}"
    # No DOI -> citation links the canonical OpenAlex URL instead of doi.org.
    assert "https://doi.org/" not in rec["citation_text"]
    assert rec["url"] in rec["citation_text"]


def test_unknown_doc_raises(corpora):
    scifact, openalex = corpora
    with pytest.raises(export_references.ExportError):
        export_references.export_record("beir:scifact:does-not-exist", scifact, openalex)


def test_foreign_namespace_raises(corpora):
    with pytest.raises(export_references.ExportError):
        export_references.export_record("unexpected:abc", {}, {})


def test_cli_exit_1_on_unknown_id(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--doc-ids", "beir:scifact:nope", "--output", str(tmp_path / "o.json")],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        env={"SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
             "PATH": __import__("os").environ.get("PATH", ""),
             "PYTHONPATH": str(PROJECT_ROOT / "src")})
    assert proc.returncode == 1 and "Unknown document" in (proc.stderr + proc.stdout)


def test_demo_config_pins_real_state():
    demo = json.loads(DEMO.read_text(encoding="utf-8"))
    assert demo["snapshot_pins"]["search_corpus"]["document_count"] == 5183
    assert demo["snapshot_pins"]["dense_encoder"]["revision"] == "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
    assert len(demo["demo_queries"]) == 5 and len(demo["export_doc_ids"]) == 4
    assert demo["offline_policy"]["missing_metadata"].startswith("null/")
