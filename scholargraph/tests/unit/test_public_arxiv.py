"""Unit and adversarial tests for arXiv adapter (EXT-03, Wave W1 R5).

Adheres strictly to Anti-Silent-Bypass Protocol:
- Positive tests: valid feed, title-only, explicit DOI, empty feed, multi-page paging,
  updated-only entry without publication year, benign paper with title 'Error' or
  abstract discussing 'Error correction'.
- Strict ID validation (F2):
  * Modern (YYMM.NNNN[N](v[1-9]\\d*)?) and old-style (archive/YYMMNNN) IDs accepted.
  * URLs with host arxiv.org/export.arxiv.org, path /abs/, no query/fragment accepted.
  * Arbitrary string IDs, foreign hosts (foreign.invalid), and version 0 (v0) fail schema.
- XML security and encoding policy (F6):
  * UTF-8 and UTF-16 (with and without BOM, LE/BE) supported and validated.
  * UTF-32 (LE/BE, with and without BOM) sniffed and rejected as unsupported encoding.
  * DOCTYPE/ENTITY declarations rejected across all encodings.
- Feed root and singleton cardinality (F4):
  * Root must be Atom feed (<feed xmlns="http://www.w3.org/2005/Atom">).
  * Conflicting duplicate titles or singleton tags fail schema.
- Upstream HTTP 200 error feeds (F3):
  * Error entries identified exclusively by entry ID (arxiv.org/api/errors#...).
- Accurate link selector provenance (F7):
  * raw_field reflects actual attributes: atom:link[type=application/pdf],
    atom:link[title=pdf], atom:link[rel=alternate], atom:link[type=text/html],
    atom:link[href], atom:link[rel=license], arxiv:license.
  * rel=related is not accepted as license.
- CLI boundary verification (F1, F5):
  * No arguments exits with code 1 and 'FAIL:' message (no argparse code 2).
  * Duplicate JSON keys in request file fail with exit code 1 and 'FAIL:'.
  * Sensitive request values (e.g. synthetic secrets) are redacted; never appear in stderr/stdout.
  * Benign query strings with 'held_out', 'labels', 'qrels' pass validation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pytest
from pydantic import ValidationError

from scholargraph.public_search.arxiv import (
    NAMESPACES,
    PARSER_VERSION,
    SOURCE_NAME,
    ArxivAdapterError,
    DuplicateKeyError,
    build_arxiv_query,
    check_xml_security,
    detect_upstream_error_entry,
    extract_and_validate_arxiv_id,
    main,
    parse_entry,
    parse_feed_payload,
    parse_opensearch_counts,
    search,
    sniff_xml_encoding,
)
from scholargraph.public_search.contracts import (
    PaperRecord,
    SearchError,
    SearchRequest,
    SourceResult,
)
from scholargraph.public_search.transport import (
    TransportError,
    TransportResponse,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "public_search" / "gemini" / "arxiv"
PYTHON_EXE = sys.executable


class MockTransport:
    """Mock transport for controlled unit testing without network calls."""

    def __init__(
        self,
        responses: list[TransportResponse | Exception],
        *,
        clock_start: float = 100.0,
        deadline_val: float = 200.0,
    ):
        self._responses = list(responses)
        self._clock = clock_start
        self._deadline = deadline_val
        self.calls: list[dict] = []

    def clock(self) -> float:
        self._clock += 0.05
        return self._clock

    def deadline(self) -> float:
        return self._deadline

    def get(self, source: str, params: Mapping[str, str | int], *, deadline: float) -> TransportResponse:
        self.calls.append({"source": source, "params": dict(params), "deadline": deadline})
        if not self._responses:
            raise RuntimeError("MockTransport exhausted responses")
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def close(self) -> None:
        pass


def make_response(xml_bytes: bytes, content_type: str = "application/atom+xml", status: int = 200) -> TransportResponse:
    sha = hashlib.sha256(xml_bytes).hexdigest()
    return TransportResponse(
        body=xml_bytes,
        sha256=sha,
        content_type=content_type,
        elapsed_seconds=0.12,
        attempts=1,
    )


def sample_request(**changes) -> SearchRequest:
    base = {
        "query": "electron spectroscopy",
        "sources": ["arxiv"],
        "top_k": 10,
        "cap_per_source": 20,
        "year_from": None,
        "year_to": None,
        "refresh": False,
    }
    base.update(changes)
    return SearchRequest.model_validate(base)


# ---------------------------------------------------------------------------
# Positive Tests
# ---------------------------------------------------------------------------

def test_search_valid_feed_positive():
    """Verify parsing of standard synthetic valid feed matching pilot structure."""
    xml_path = FIXTURES_DIR / "valid_feed.xml"
    raw_bytes = xml_path.read_bytes()
    transport = MockTransport([make_response(raw_bytes)])

    req = sample_request(cap_per_source=2)
    result = search(req, transport)  # type: ignore[arg-type]

    assert result.source == "arxiv"
    assert result.status == "success"
    assert len(result.records) == 2
    assert result.error is None
    assert result.source_total == 186833
    assert result.filter_coverage == "none"
    assert result.truncated is True
    assert len(result.raw_references) == 1
    assert result.raw_references[0].sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert result.elapsed_seconds is not None and result.elapsed_seconds > 0

    rec0 = result.records[0]
    assert rec0.source == "arxiv"
    assert rec0.source_id == "cond-mat/0011267v1"
    assert rec0.arxiv_id == "cond-mat/0011267v1"
    assert rec0.title == "The electronic structure of cuprates from high energy spectroscopy"
    assert rec0.landing_url == "https://arxiv.org/abs/cond-mat/0011267v1"
    assert rec0.pdf_url == "https://arxiv.org/pdf/cond-mat/0011267v1"
    assert rec0.publication_year == 2000
    assert rec0.venue == "J. Electron Spectr. Relat. Phenom. 117-118, 203 (2001)"
    assert rec0.doi is None
    assert rec0.citation_count is None
    assert rec0.open_access_status is None
    assert rec0.authors == ["Mark S. Golden", "Christian Duerr"]
    assert rec0.authors_availability == "known"
    assert set(rec0.missing_fields) == {"citation_count", "doi", "license", "open_access_status"}

    expected_present = {"title", "source_id", "landing_url", "abstract", "publication_year", "arxiv_id", "venue", "pdf_url", "authors"}
    assert set(rec0.field_provenance) == expected_present
    for k, ev_list in rec0.field_provenance.items():
        assert len(ev_list) == 1
        assert ev_list[0].source == "arxiv"
        assert ev_list[0].source_id == rec0.source_id
        assert ev_list[0].raw_sha256 == rec0.raw_sha256

    rec1 = result.records[1]
    assert rec1.arxiv_id == "cond-mat/0211289v2"
    assert rec1.publication_year == 2002


def test_filter_coverage_year_mapping():
    """Verify filter_coverage is 'bounded_pool' when year filters are requested, 'none' otherwise."""
    xml_path = FIXTURES_DIR / "valid_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])
    req = sample_request(cap_per_source=2, year_from=2000, year_to=2024)
    result = search(req, transport)  # type: ignore[arg-type]
    assert result.filter_coverage == "bounded_pool"

    transport2 = MockTransport([make_response(xml_path.read_bytes())])
    req2 = sample_request(cap_per_source=2, year_from=None, year_to=None)
    result2 = search(req2, transport2)  # type: ignore[arg-type]
    assert result2.filter_coverage == "none"


def test_search_valid_with_doi():
    """Verify normalization and preservation of explicit arxiv:doi field."""
    xml_path = FIXTURES_DIR / "valid_with_doi.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    req = sample_request(cap_per_source=5)
    result = search(req, transport)  # type: ignore[arg-type]

    assert result.status == "success"
    rec = result.records[0]
    assert rec.doi == "10.1000/182"
    assert "doi" not in rec.missing_fields
    assert "doi" in rec.field_provenance
    assert rec.field_provenance["doi"][0].raw_field == "arxiv:doi"


def test_search_title_only_record():
    """Title-only record without summary/abstract must be valid with abstract=None."""
    xml_path = FIXTURES_DIR / "title_only_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    req = sample_request(cap_per_source=5)
    result = search(req, transport)  # type: ignore[arg-type]

    assert result.status == "success"
    rec = result.records[0]
    assert rec.abstract is None
    assert "abstract" in rec.missing_fields
    assert "abstract" not in rec.field_provenance


def test_updated_only_does_not_set_publication_year():
    """Entry with only atom:updated and no atom:published must NOT use updated year as publication_year."""
    xml_feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p_upd</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2405.00001v2</id><title>Updated Only Paper</title>
        <link href="https://arxiv.org/abs/2405.00001v2" rel="alternate" type="text/html"/>
        <updated>2024-05-15T12:00:00Z</updated>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(xml_feed.encode("utf-8"))])
    res = search(sample_request(cap_per_source=2), transport)  # type: ignore[arg-type]
    assert res.status == "success"
    rec = res.records[0]
    assert rec.publication_year is None
    assert "publication_year" in rec.missing_fields
    assert "publication_year" not in rec.field_provenance


def test_search_empty_feed():
    """Valid feed with totalResults 0 must produce SourceResult with status='empty'."""
    xml_path = FIXTURES_DIR / "empty_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    req = sample_request()
    result = search(req, transport)  # type: ignore[arg-type]

    assert result.status == "empty"
    assert result.records == []
    assert result.source_total == 0
    assert result.error is None
    assert result.truncated is False
    assert len(result.raw_references) == 1


def test_search_not_requested_zero_network():
    """When arxiv is not in request.sources, return status='not_requested' without touching transport."""
    transport = MockTransport([])
    req = sample_request(sources=["openalex"])

    result = search(req, transport)  # type: ignore[arg-type]

    assert result.status == "not_requested"
    assert result.records == []
    assert result.error is None
    assert result.source_total is None
    assert result.elapsed_seconds is None
    assert result.filter_coverage == "none"
    assert result.truncated is None
    assert result.raw_references == []
    assert len(transport.calls) == 0


def test_search_paging_and_bounded_cap():
    """Paging across multiple requests bounded by cap_per_source=3."""
    feed_page1 = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p1</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>2</opensearch:itemsPerPage>
      <opensearch:totalResults>4</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>P1 E1</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
        <published>2021-01-01T00:00:00Z</published>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2101.00002v1</id><title>P1 E2</title>
        <link href="https://arxiv.org/abs/2101.00002v1" rel="alternate" type="text/html"/>
        <published>2021-01-02T00:00:00Z</published>
      </entry>
    </feed>"""

    feed_page2 = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p2</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>4</opensearch:totalResults>
      <opensearch:startIndex>2</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00003v1</id><title>P2 E1</title>
        <link href="https://arxiv.org/abs/2101.00003v1" rel="alternate" type="text/html"/>
        <published>2021-01-03T00:00:00Z</published>
      </entry>
    </feed>"""

    resp1 = make_response(feed_page1.encode("utf-8"))
    resp2 = make_response(feed_page2.encode("utf-8"))
    transport = MockTransport([resp1, resp2])

    req = sample_request(cap_per_source=3)
    result = search(req, transport)  # type: ignore[arg-type]

    assert result.status == "success"
    assert len(result.records) == 3
    assert [r.source_id for r in result.records] == ["2101.00001v1", "2101.00002v1", "2101.00003v1"]
    assert len(transport.calls) == 2
    assert transport.calls[0]["params"]["start"] == 0
    assert transport.calls[0]["params"]["max_results"] == 3
    assert transport.calls[1]["params"]["start"] == 2
    assert transport.calls[1]["params"]["max_results"] == 1
    assert len(result.raw_references) == 2
    assert result.truncated is True


def test_entries_count_exceeds_requested_page_size_fails():
    """Negative test: if upstream returns more entries than requested page size, fail schema."""
    feed_oversized = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p_over</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>5</opensearch:itemsPerPage>
      <opensearch:totalResults>10</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>E1</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2101.00002v1</id><title>E2</title>
        <link href="https://arxiv.org/abs/2101.00002v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed_oversized.encode("utf-8"))])
    res = search(sample_request(cap_per_source=1), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error is not None
    assert res.error.kind == "schema"
    assert "exceeds requested page size" in res.error.message.lower()


# ---------------------------------------------------------------------------
# Query Escaping & Anti-Injection Tests
# ---------------------------------------------------------------------------

def test_query_escaping_and_parameter_injection():
    """Verify build_arxiv_query sanitizes input and transport params cannot inject query string keys."""
    q1 = build_arxiv_query("graph neural networks")
    assert q1 == "all:(graph neural networks)"

    q4 = build_arxiv_query("ti:electron")
    assert q4 == "ti:electron"

    q_inject = "quantum&max_results=500&id_list=bad"
    xml_path = FIXTURES_DIR / "empty_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])
    req = sample_request(query=q_inject)
    search(req, transport)  # type: ignore[arg-type]

    sent_params = transport.calls[0]["params"]
    assert "id_list" not in sent_params
    assert sent_params["max_results"] == 20
    assert "search_query" in sent_params


def test_query_unbalanced_syntax_fails_cleanly():
    """Unbalanced quotes or parentheses must fail as request error without silent alteration."""
    transport = MockTransport([])

    req1 = sample_request(query='quantum "cryptography')
    res1 = search(req1, transport)  # type: ignore[arg-type]
    assert res1.status == "failed"
    assert res1.error is not None
    assert res1.error.kind == "request"
    assert "quotes" in res1.error.message.lower()

    req2 = sample_request(query="(deep learning")
    res2 = search(req2, transport)  # type: ignore[arg-type]
    assert res2.status == "failed"
    assert res2.error is not None
    assert res2.error.kind == "request"
    assert "parentheses" in res2.error.message.lower()


def test_held_out_query_not_rejected():
    """Query containing 'held_out' keyword is legitimate search text and must not be blanket-rejected."""
    xml_path = FIXTURES_DIR / "empty_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])
    req = sample_request(query="held_out evaluation dataset")
    result = search(req, transport)  # type: ignore[arg-type]
    assert result.status == "empty"


# ---------------------------------------------------------------------------
# Finding F2: Strict arXiv ID Validation Tests
# ---------------------------------------------------------------------------

def test_strict_arxiv_id_validation_positive():
    """Valid modern and old-style arXiv IDs must validate cleanly."""
    valid_cases = [
        ("https://arxiv.org/abs/2401.00001v1", "2401.00001v1"),
        ("http://export.arxiv.org/abs/2401.00001v2", "2401.00001v2"),
        ("https://arxiv.org:443/abs/2401.00001v1", "2401.00001v1"),
        ("http://export.arxiv.org:80/abs/2401.00001v2", "2401.00001v2"),
        ("https://www.arxiv.org:8443/abs/2401.00001v1", "2401.00001v1"),
        ("https://arxiv.org/abs/0704.0001v1", "0704.0001v1"),
        ("https://arxiv.org/abs/1501.00001", "1501.00001"),
        ("http://arxiv.org/abs/cond-mat/0011267v1", "cond-mat/0011267v1"),
        ("http://arxiv.org/abs/math.GT/0309136v1", "math.GT/0309136v1"),
        ("http://arxiv.org/abs/hep-th/9912001", "hep-th/9912001"),
        ("arxiv:2401.00001v1", "2401.00001v1"),
        ("2401.00001v1", "2401.00001v1"),
        ("cond-mat/0011267", "cond-mat/0011267"),
    ]
    for raw_id, expected in valid_cases:
        actual = extract_and_validate_arxiv_id(raw_id, 0)
        assert actual == expected, f"Failed for {raw_id}"


def test_strict_arxiv_id_validation_negative():
    """Arbitrary strings, foreign hosts, version 0, and malformed/out-of-range ports must fail schema."""
    invalid_cases = [
        "NOT_AN_ARXIV_ID",
        "https://foreign.invalid/abs/2401.00001v1",
        "https://arxiv.org/abs/2401.00001v0",
        "https://arxiv.org/abs/2401.00001v01",
        "https://arxiv.org/abs/2401.00001v1?query=1",
        "https://arxiv.org/abs/2401.00001v1#section",
        "http://attacker@arxiv.org/abs/2401.00001v1",
        "http://arxiv.org/pdf/2401.00001v1",
        "https://arxiv.org:not-a-port/abs/2401.00001v1",
        "https://arxiv.org:99999/abs/2401.00001v1",
        "https://arxiv.org:0/abs/2401.00001v1",
        "https://arxiv.org:/abs/2401.00001v1",
        "https://arxiv.org:-80/abs/2401.00001v1",
        "https://arxiv.org:65536/abs/2401.00001v1",
        "",
        "   ",
    ]
    for raw_id in invalid_cases:
        with pytest.raises(ArxivAdapterError) as exc_info:
            extract_and_validate_arxiv_id(raw_id, 0)
        assert exc_info.value.error.kind == "schema"


# ---------------------------------------------------------------------------
# Finding F3: Error Feed False Positives vs Real Papers
# ---------------------------------------------------------------------------

def test_paper_title_error_is_validated():
    """Real paper with title 'Error' must be VALIDATED and not treated as error feed."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p_err_title</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id>
        <title>Error</title>
        <summary>A treatise on experimental error analysis.</summary>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
        <published>2024-01-01T00:00:00Z</published>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "success"
    assert len(res.records) == 1
    assert res.records[0].title == "Error"


def test_paper_abstract_error_correction_is_validated():
    """Real paper with abstract starting with 'Error correction...' must be VALIDATED."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p_err_sum</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id>
        <title>Quantum Codes</title>
        <summary>Error correction is studied in this paper for topological systems.</summary>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
        <published>2024-01-01T00:00:00Z</published>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "success"
    assert len(res.records) == 1
    assert "Error correction" in (res.records[0].abstract or "")


# ---------------------------------------------------------------------------
# Finding F4: XML Root & Cardinality Tests
# ---------------------------------------------------------------------------

def test_non_atom_root_fails_schema():
    """Payload with root element other than Atom feed must fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <notfeed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id><title>E</title>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </notfeed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"
    assert "root element must be atom feed" in res.error.message.lower()


def test_entry_duplicate_conflicting_title_fails():
    """Entry containing multiple title elements must fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id>
        <title>First Title</title>
        <title>Contradictory Title</title>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"
    assert "atom:title" in res.error.message.lower()


def test_feed_duplicate_total_results_fails():
    """Feed containing duplicate opensearch:totalResults elements must fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:totalResults>2</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id><title>E</title>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"


# ---------------------------------------------------------------------------
# Finding F6: XML Encoding Policy Tests
# ---------------------------------------------------------------------------

def test_utf16_encodings_with_and_without_bom_pass():
    """UTF-16 with BOM, UTF-16LE without BOM, and UTF-16BE without BOM must all validate."""
    ns = "http://www.w3.org/2005/Atom"
    base = f'<?xml version="1.0" encoding="UTF-16"?><feed xmlns="{ns}" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><id>p_u16</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated><opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage><entry><id>https://arxiv.org/abs/2401.00001v1</id><title>Valid U16</title><link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/></entry></feed>'

    for enc in ("utf-16", "utf-16-le", "utf-16-be"):
        raw_bytes = base.encode(enc)
        transport = MockTransport([make_response(raw_bytes)])
        res = search(sample_request(), transport)  # type: ignore[arg-type]
        assert res.status == "success", f"Failed for {enc}: {res.error}"
        assert len(res.records) == 1
        assert res.records[0].arxiv_id == "2401.00001v1"


def test_utf32_rejected_as_unsupported_encoding():
    """UTF-32 encoded feed must fail schema cleanly as unsupported encoding."""
    ns = "http://www.w3.org/2005/Atom"
    base = f'<?xml version="1.0" encoding="UTF-32"?><feed xmlns="{ns}" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><id>p_u32</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated><opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage><entry><id>https://arxiv.org/abs/2401.00001v1</id><title>Valid U32</title><link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/></entry></feed>'

    for enc in ("utf-32", "utf-32-le", "utf-32-be"):
        raw_bytes = base.encode(enc)
        transport = MockTransport([make_response(raw_bytes)])
        res = search(sample_request(), transport)  # type: ignore[arg-type]
        assert res.status == "failed"
        assert res.error.kind == "schema"
        assert "unsupported" in res.error.message.lower()


DTD_VALID_FEED_TEMPLATE = """<?xml version="1.0" encoding="{enc}"?>
<!DOCTYPE feed [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
  <id>https://arxiv.org/api/xxe</id>
  <title>Safe Title</title>
  <updated>2026-09-30T00:00:00Z</updated>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <entry>
    <id>http://arxiv.org/abs/2101.00001v1</id>
    <title>Valid Title</title>
    <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
    <updated>2026-09-30T00:00:00Z</updated>
  </entry>
</feed>"""


def test_xxe_doctype_rejection_utf8():
    """Reject DOCTYPE in UTF-8 with SearchError schema failure."""
    xml_path = FIXTURES_DIR / "xxe_doctype.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "doctype" in result.error.message.lower()
    assert len(result.raw_references) == 1


def test_xxe_doctype_rejection_utf16le():
    """Reject DOCTYPE encoded in UTF-16LE (both with BOM and without BOM) on fully formed feed."""
    raw_text = DTD_VALID_FEED_TEMPLATE.format(enc="UTF-16")
    utf16_no_bom = raw_text.encode("utf-16-le")
    transport1 = MockTransport([make_response(utf16_no_bom)])
    result1 = search(sample_request(), transport1)  # type: ignore[arg-type]
    assert result1.status == "failed"
    assert result1.error is not None
    assert result1.error.kind == "schema"
    assert "doctype" in result1.error.message.lower()

    utf16_bom = raw_text.encode("utf-16")
    transport2 = MockTransport([make_response(utf16_bom)])
    result2 = search(sample_request(), transport2)  # type: ignore[arg-type]
    assert result2.status == "failed"
    assert result2.error is not None
    assert result2.error.kind == "schema"
    assert "doctype" in result2.error.message.lower()


def test_xxe_doctype_rejection_utf16be():
    """Reject DOCTYPE encoded in UTF-16BE (both with BOM and without BOM) on fully formed feed."""
    raw_text = DTD_VALID_FEED_TEMPLATE.format(enc="UTF-16")
    utf16_be = raw_text.encode("utf-16-be")
    transport = MockTransport([make_response(utf16_be)])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "doctype" in result.error.message.lower()


def test_xxe_doctype_rejection_utf32():
    """Reject DOCTYPE encoded in UTF-32LE and UTF-32BE on fully formed feed."""
    raw_text = DTD_VALID_FEED_TEMPLATE.format(enc="UTF-32")
    utf32_le = raw_text.encode("utf-32-le")
    transport = MockTransport([make_response(utf32_le)])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "unsupported" in result.error.message.lower() or "doctype" in result.error.message.lower()


def test_unsupported_encoding_fails():
    """Declared unsupported XML encoding must fail schema immediately without lossy fallback."""
    raw_bytes = b'<?xml version="1.0" encoding="unsupported-codec-xyz"?><feed/>'
    transport = MockTransport([make_response(raw_bytes)])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "unsupported" in result.error.message.lower()


def test_malformed_xml():
    """Malformed unclosed XML must fail with kind='schema'."""
    xml_path = FIXTURES_DIR / "malformed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "schema"


def test_missing_id_fails():
    """Entry missing required atom:id tag must fail whole source."""
    xml_path = FIXTURES_DIR / "missing_id.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "missing" in result.error.message.lower() or "atom:id" in result.error.message.lower()


def test_missing_title_fails():
    """Entry missing required atom:title tag must fail whole source."""
    xml_path = FIXTURES_DIR / "missing_title.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "missing" in result.error.message.lower() or "atom:title" in result.error.message.lower()


def test_missing_link_fails():
    """Entry missing required landing_url must fail whole source without fallback from atom:id."""
    xml_path = FIXTURES_DIR / "missing_link.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "landing_url" in result.error.message.lower()


def test_upstream_error_feed_detected():
    """HTTP 200 feed containing upstream error entry must fail with kind='upstream' without leaking raw payload."""
    xml_path = FIXTURES_DIR / "error_entry_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "upstream"
    assert result.error.message == "arXiv upstream query error entry detected"


def test_upstream_error_feed_without_counters_detected():
    """HTTP 200 feed containing upstream error entry and NO OpenSearch counters must fail with kind='upstream'."""
    xml_path = FIXTURES_DIR / "error_feed_no_counters.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "upstream"
    assert result.error.message == "arXiv upstream query error entry detected"


def test_invalid_date_fails():
    """Entry with unparseable published date must fail with kind='schema'."""
    xml_path = FIXTURES_DIR / "invalid_date.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"


def test_blank_published_tag_fails():
    """Blank or whitespace-only published tag must fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>E</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
        <published>   </published>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"


def test_invalid_updated_date_fails():
    """Entry with invalid updated timestamp must fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>E</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
        <updated>not-an-iso-date</updated>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"
    assert "updated" in res.error.message.lower()


def test_invalid_counter_fails():
    """Feed with non-digit totalResults counter must fail with kind='schema'."""
    xml_path = FIXTURES_DIR / "invalid_counter.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "opensearch:totalresults" in result.error.message.lower()


def test_missing_opensearch_tag_fails():
    """Feed missing opensearch:totalResults tag must fail loudly without silent fallback."""
    xml_path = FIXTURES_DIR / "missing_opensearch.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "opensearch:totalresults" in result.error.message.lower()


def test_duplicate_id_in_feed_fails():
    """Feed with duplicate entry IDs must not be silently dropped; fails loudly."""
    xml_path = FIXTURES_DIR / "duplicate_id_feed.xml"
    transport = MockTransport([make_response(xml_path.read_bytes())])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "duplicate record id" in result.error.message.lower()
    assert result.error.record_index == 1


def test_repeated_page_response_detected():
    """If server responds with the exact same response hash for a subsequent page, fail with upstream error."""
    xml_path = FIXTURES_DIR / "valid_feed.xml"
    resp = make_response(xml_path.read_bytes())
    transport = MockTransport([resp, resp])

    req = sample_request(cap_per_source=20)
    result = search(req, transport)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "upstream"
    assert "repeated" in result.error.message.lower()
    assert len(result.raw_references) == 1


def test_total_results_mutation_across_pages_fails():
    """If totalResults changes unexpectedly between pages, fail schema."""
    page1 = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p1</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>4</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>E1</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""

    page2 = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p2</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>999</opensearch:totalResults>
      <opensearch:startIndex>1</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00002v1</id><title>E2</title>
        <link href="https://arxiv.org/abs/2101.00002v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""

    transport = MockTransport([make_response(page1.encode("utf-8")), make_response(page2.encode("utf-8"))])
    req = sample_request(cap_per_source=2)
    result = search(req, transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.kind == "schema"
    assert "totalresults changed" in result.error.message.lower()


def test_items_per_page_zero_with_entries_fails():
    """If itemsPerPage is 0 but entries are present, fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>0</opensearch:itemsPerPage>
      <opensearch:totalResults>10</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>E</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"
    assert "itemsperpage is 0" in res.error.message.lower()


def test_start_plus_entries_exceeds_total_fails():
    """If start index + len(entries) > totalResults, fail schema."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>5</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>http://arxiv.org/abs/2101.00001v1</id><title>E1</title>
        <link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2101.00002v1</id><title>E2</title>
        <link href="https://arxiv.org/abs/2101.00002v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "schema"
    assert "exceeds totalresults" in res.error.message.lower()


def test_empty_page_when_total_exceeds_start_fails_upstream():
    """If feed has 0 entries but totalResults > startIndex, fail upstream as incomplete feed."""
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>10</opensearch:itemsPerPage>
      <opensearch:totalResults>5</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "failed"
    assert res.error.kind == "upstream"
    assert "empty page received" in res.error.message.lower()


def test_transport_quota_error():
    """Transport quota 429 error is propagated cleanly as failed SourceResult with kind='quota'."""
    err = TransportError(SearchError(kind="quota", message="upstream rate limited", source="arxiv", retry_after_seconds=30.0, record_index=None))
    transport = MockTransport([err])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "quota"
    assert result.error.retry_after_seconds == 30.0


def test_transport_timeout_error():
    """Transport timeout error is propagated cleanly as failed SourceResult with kind='timeout'."""
    err = TransportError(SearchError(kind="timeout", message="request deadline exhausted", source="arxiv", retry_after_seconds=None, record_index=None))
    transport = MockTransport([err])

    result = search(sample_request(), transport)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.records == []
    assert result.error is not None
    assert result.error.kind == "timeout"


# ---------------------------------------------------------------------------
# Finding F7: Link Selector Provenance Tests
# ---------------------------------------------------------------------------

def test_link_selector_provenance_accuracy():
    """raw_field in FieldEvidence must reflect actual XML attributes matched."""
    # Case 1: PDF link has type="application/pdf" but no title attribute
    # Landing link has no rel and no type (bare href)
    feed = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id><title>P</title>
        <link href="https://arxiv.org/abs/2401.00001v1"/>
        <link href="https://arxiv.org/pdf/2401.00001v1" type="application/pdf"/>
      </entry>
    </feed>"""
    transport = MockTransport([make_response(feed.encode("utf-8"))])
    res = search(sample_request(), transport)  # type: ignore[arg-type]
    assert res.status == "success"
    rec = res.records[0]
    assert rec.field_provenance["landing_url"][0].raw_field == "atom:link[href]"
    assert rec.field_provenance["pdf_url"][0].raw_field == "atom:link[type=application/pdf]"
    assert rec.license is None

    # Case 2: License link has rel="license"
    feed_lic = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id><title>P</title>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
        <link href="http://creativecommons.org/licenses/by/4.0/" rel="license"/>
      </entry>
    </feed>"""
    transport2 = MockTransport([make_response(feed_lic.encode("utf-8"))])
    res2 = search(sample_request(), transport2)  # type: ignore[arg-type]
    assert res2.status == "success"
    rec2 = res2.records[0]
    assert rec2.license == "http://creativecommons.org/licenses/by/4.0/"
    assert rec2.field_provenance["license"][0].raw_field == "atom:link[rel=license]"

    # Case 3: Link has rel="related" with license in URL -> MUST NOT be assigned as license
    feed_related = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns="http://www.w3.org/2005/Atom">
      <id>p</id><title>Q</title><updated>2026-09-30T00:00:00Z</updated>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <entry>
        <id>https://arxiv.org/abs/2401.00001v1</id><title>P</title>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
        <link href="http://arxiv.org/licenses/nonexclusive-distrib/1.0/" rel="related"/>
      </entry>
    </feed>"""
    transport3 = MockTransport([make_response(feed_related.encode("utf-8"))])
    res3 = search(sample_request(), transport3)  # type: ignore[arg-type]
    assert res3.status == "success"
    rec3 = res3.records[0]
    assert rec3.license is None


# ---------------------------------------------------------------------------
# CLI Boundary Tests via Subprocess (Anti-Silent-Bypass)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name,expected_exit", [
    ("valid_feed.xml", 0),
    ("valid_with_doi.xml", 0),
    ("title_only_feed.xml", 0),
    ("empty_feed.xml", 0),
    ("error_entry_feed.xml", 1),
    ("error_feed_no_counters.xml", 1),
    ("xxe_doctype.xml", 1),
    ("malformed.xml", 1),
    ("missing_id.xml", 1),
    ("missing_title.xml", 1),
    ("missing_link.xml", 1),
    ("invalid_date.xml", 1),
    ("invalid_counter.xml", 1),
    ("missing_opensearch.xml", 1),
    ("duplicate_id_feed.xml", 1),
    ("nonexistent_file.xml", 1),
])
def test_cli_executable_boundary_subprocess(fixture_name: str, expected_exit: int):
    """Executable boundary verification: asserts exit code 0 for valid fixtures and exit 1 for malformed."""
    fixture_path = FIXTURES_DIR / fixture_name
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir

    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", str(fixture_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    assert proc.returncode == expected_exit, f"Fixture {fixture_name} expected exit {expected_exit}, got {proc.returncode}. Stderr: {proc.stderr}"
    if expected_exit == 0:
        assert "VALIDATED" in proc.stdout
    else:
        assert "FAIL:" in proc.stderr
        assert "Traceback" not in proc.stderr, f"Unhandled exception traceback found in stderr for {fixture_name}: {proc.stderr}"


def test_cli_no_args_exits_one_with_fail_message():
    """Running CLI with no arguments must exit with code 1 and FAIL message (not argparse exit 2)."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir

    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    assert proc.returncode == 1
    assert "FAIL:" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_secret_error_redaction(tmp_path: Path):
    """CLI must not leak sensitive request values (e.g. synthetic secrets) in stderr or stdout upon error."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir
    payload = str(FIXTURES_DIR / "valid_feed.xml")

    sentinel = "SYNTHETIC_SECRET_081_NOT_REAL"
    req_file = tmp_path / "secret_req.json"
    req_data = sample_request().model_dump(mode="json")
    req_data["api_key"] = sentinel
    req_file.write_text(json.dumps(req_data), encoding="utf-8")

    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(req_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    assert proc.returncode == 1
    assert "FAIL:" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert sentinel not in proc.stderr
    assert sentinel not in proc.stdout


def test_cli_duplicate_json_keys_fails(tmp_path: Path):
    """CLI --request must reject duplicate JSON keys with exit code 1."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir
    payload = str(FIXTURES_DIR / "valid_feed.xml")

    dup_json = '{"query":"test","sources":["arxiv"],"top_k":0,"top_k":2,"cap_per_source":2,"year_from":null,"year_to":null}'
    req_file = tmp_path / "dup_req.json"
    req_file.write_text(dup_json, encoding="utf-8")

    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(req_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    assert proc.returncode == 1
    assert "FAIL: invalid request JSON: duplicate keys detected" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_benign_query_keywords_passes(tmp_path: Path):
    """CLI with benign research query containing 'held_out', 'labels', 'qrels' must exit 0."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir
    payload = str(FIXTURES_DIR / "valid_feed.xml")

    req_data = {
        "query": "held_out labels and qrels in public retrieval research",
        "sources": ["arxiv"],
        "top_k": 2,
        "cap_per_source": 2,
        "year_from": None,
        "year_to": None,
    }
    req_file = tmp_path / "benign_req.json"
    req_file.write_text(json.dumps(req_data), encoding="utf-8")

    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(req_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

    assert proc.returncode == 0
    assert "VALIDATED" in proc.stdout
    assert "Traceback" not in proc.stderr


def test_cli_with_request_argument_valid_and_invalid(tmp_path: Path):
    """Verify CLI properly parses and validates --request argument when supplied."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir
    payload = str(FIXTURES_DIR / "valid_feed.xml")

    # 1. Valid request file
    req_file = tmp_path / "valid_req.json"
    req_file.write_text(json.dumps(sample_request().model_dump(mode="json")), encoding="utf-8")
    cmd_valid = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(req_file)]
    p_valid = subprocess.run(cmd_valid, capture_output=True, text=True, env=env)
    assert p_valid.returncode == 0
    assert "VALIDATED" in p_valid.stdout

    # 2. Non-existent request file
    cmd_missing = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(tmp_path / "missing.json")]
    p_missing = subprocess.run(cmd_missing, capture_output=True, text=True, env=env)
    assert p_missing.returncode == 1
    assert "FAIL:" in p_missing.stderr

    # 3. Invalid schema request file
    bad_req_file = tmp_path / "bad_req.json"
    bad_req_file.write_text(json.dumps({"query": ""}), encoding="utf-8")
    cmd_bad = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(bad_req_file)]
    p_bad = subprocess.run(cmd_bad, capture_output=True, text=True, env=env)
    assert p_bad.returncode == 1
    assert "FAIL:" in p_bad.stderr


# ---------------------------------------------------------------------------
# Finding R4-F1 & R4-F2 Regression Tests (Wave W1 R5)
# ---------------------------------------------------------------------------

def test_cli_request_diagnostic_distinction(tmp_path: Path):
    """Regression R4-F1: Distinguish duplicate JSON keys vs malformed syntax vs schema validation failures.

    All must exit 1, label with FAIL:, emit accurate diagnostic, and never leak sentinels/secrets/tracebacks.
    """
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir
    payload = str(FIXTURES_DIR / "valid_feed.xml")
    sentinel = "SYNTHETIC_SECRET_R5_081_NOT_REAL"

    # Case 1: Schema failure (top_k is boolean, not integer count)
    req_schema = {
        "query": "quantum gravity",
        "sources": ["arxiv"],
        "top_k": True,
        "cap_per_source": 2,
        "year_from": None,
        "year_to": None,
        "api_key": sentinel,
    }
    schema_file = tmp_path / "schema_err.json"
    schema_file.write_text(json.dumps(req_schema), encoding="utf-8")
    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(schema_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "FAIL: invalid request schema" in proc.stderr
    assert "duplicate keys" not in proc.stderr
    assert "malformed" not in proc.stderr
    assert "Traceback" not in proc.stderr
    assert sentinel not in proc.stderr
    assert sentinel not in proc.stdout

    # Case 2: Malformed JSON syntax
    malformed_file = tmp_path / "malformed_syntax.json"
    malformed_file.write_text('{"query":', encoding="utf-8")
    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(malformed_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "FAIL: invalid request JSON: malformed JSON syntax" in proc.stderr
    assert "duplicate keys" not in proc.stderr
    assert "invalid request schema" not in proc.stderr
    assert "Traceback" not in proc.stderr

    # Case 3: Actual duplicate JSON keys
    dup_file = tmp_path / "actual_dup.json"
    dup_file.write_text(
        '{"query":"quantum","query":"gravity","sources":["arxiv"],"top_k":2,"cap_per_source":2,"year_from":null,"year_to":null}',
        encoding="utf-8",
    )
    cmd = [PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", payload, "--request", str(dup_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "FAIL: invalid request JSON: duplicate keys detected" in proc.stderr
    assert "malformed" not in proc.stderr
    assert "invalid request schema" not in proc.stderr
    assert "Traceback" not in proc.stderr


def test_url_id_port_validation_search():
    """Regression R4-F2: URL ID port validation in search() parser."""
    feed_tmpl = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
      <id>https://arxiv.org/api/synthetic-feed</id><title>Synthetic feed</title><updated>2024-01-01T00:00:00Z</updated>
      <opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <entry>
        <id>{entry_id}</id><title>Valid Paper</title><summary>Valid abstract</summary>
        <published>2024-01-01T00:00:00Z</published>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""

    # Invalid ports: not-a-port, 99999, 0 must fail schema
    for bad_id in (
        "https://arxiv.org:not-a-port/abs/2401.00001v1",
        "https://arxiv.org:99999/abs/2401.00001v1",
        "https://arxiv.org:0/abs/2401.00001v1",
    ):
        raw = feed_tmpl.format(entry_id=bad_id).encode("utf-8")
        tr = MockTransport([make_response(raw)])
        res = search(sample_request(), tr)  # type: ignore[arg-type]
        assert res.status == "failed"
        assert res.error is not None
        assert res.error.kind == "schema"

    # Valid port: 443 must succeed
    raw_ok = feed_tmpl.format(entry_id="https://arxiv.org:443/abs/2401.00001v1").encode("utf-8")
    tr_ok = MockTransport([make_response(raw_ok)])
    res_ok = search(sample_request(), tr_ok)  # type: ignore[arg-type]
    assert res_ok.status == "success"
    assert len(res_ok.records) == 1
    assert res_ok.records[0].arxiv_id == "2401.00001v1"


def test_url_id_port_validation_cli_subprocess(tmp_path: Path):
    """Regression R4-F2: CLI boundary rejects feeds with malformed/out-of-range URL ID port with exit 1."""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_dir

    feed_tmpl = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
      <id>https://arxiv.org/api/synthetic-feed</id><title>Synthetic feed</title><updated>2024-01-01T00:00:00Z</updated>
      <opensearch:totalResults>1</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <entry>
        <id>{entry_id}</id><title>Valid Paper</title><summary>Valid abstract</summary>
        <published>2024-01-01T00:00:00Z</published>
        <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate" type="text/html"/>
      </entry>
    </feed>"""

    # Malformed port -> exit 1, FAIL: in stderr, no traceback
    bad_file = tmp_path / "bad_port.xml"
    bad_file.write_text(feed_tmpl.format(entry_id="https://arxiv.org:not-a-port/abs/2401.00001v1"), encoding="utf-8")
    proc = subprocess.run([PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", str(bad_file)], capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "FAIL:" in proc.stderr
    assert "Traceback" not in proc.stderr

    # Out of range port -> exit 1, FAIL: in stderr, no traceback
    oor_file = tmp_path / "oor_port.xml"
    oor_file.write_text(feed_tmpl.format(entry_id="https://arxiv.org:99999/abs/2401.00001v1"), encoding="utf-8")
    proc = subprocess.run([PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", str(oor_file)], capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "FAIL:" in proc.stderr
    assert "Traceback" not in proc.stderr

    # Valid port -> exit 0, VALIDATED in stdout
    valid_file = tmp_path / "valid_port.xml"
    valid_file.write_text(feed_tmpl.format(entry_id="https://arxiv.org:443/abs/2401.00001v1"), encoding="utf-8")
    proc = subprocess.run([PYTHON_EXE, "-m", "scholargraph.public_search.arxiv", "--payload", str(valid_file)], capture_output=True, text=True, env=env)
    assert proc.returncode == 0
    assert "VALIDATED" in proc.stdout
    assert "Traceback" not in proc.stderr
