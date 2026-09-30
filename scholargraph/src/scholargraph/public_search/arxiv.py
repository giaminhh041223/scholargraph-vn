"""arXiv source adapter for public paper search (EXT-03, Wave W1 R5).

Implements search(request: SearchRequest, transport: Transport) -> SourceResult.
Strict Anti-Silent-Bypass protocol and robust error handling:
- Uses ArxivAdapterError(Exception) wrapping a strictly validated SearchError model.
- Unified parse_feed_payload function shared by both search() and CLI boundary runner.
- XML security with Appendix F signature sniffing (UTF-8, UTF-16LE/BE with or without BOM).
  Deterministically sniffs and rejects UTF-32 (LE/BE, with/without BOM) as unsupported encoding.
  Rejects DOCTYPE and ENTITY declarations to prevent XXE.
- Strict arXiv ID validation: supports modern (YYMM.NNNN[N](v[1-9]\\d*)?) and old-style
  (archive(.subj)?/YYMMNNN(v[1-9]\\d*)?) IDs. URL IDs must have arxiv.org host, path /abs/,
  no query/fragment, and version >= 1 (v0 strictly rejected).
- Upstream HTTP 200 error feeds detected exclusively via entry ID (arxiv.org/api/errors#...);
  does NOT misclassify valid papers with title 'Error' or abstract discussing 'Error correction'.
- XML root element must be Atom feed (<feed xmlns="http://www.w3.org/2005/Atom">).
  Strict singleton cardinality enforced for feed (id, title, updated, OpenSearch counters)
  and entry (id, title, summary, published, updated, journal_ref, doi).
- Accurate link selector provenance: FieldEvidence.raw_field reflects actual attributes
  (atom:link[title=pdf], atom:link[type=application/pdf], atom:link[rel=alternate],
  atom:link[type=text/html], atom:link[href], atom:link[rel=license], arxiv:license).
  No license from rel=related.
- CLI boundary validator: StrictArgumentParser exits with code 1 and 'FAIL:' message on missing/invalid args.
  CLI --request validates SearchRequest schema with duplicate key rejection without leaking secrets.
"""
from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import re
import sys
import xml.parsers.expat
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from pydantic import ValidationError

from .contracts import (
    CONTRACT_VERSION,
    SCHEMA_VERSION,
    YEAR_MAX,
    YEAR_MIN,
    FieldEvidence,
    PaperRecord,
    RawReference,
    SearchError,
    SearchRequest,
    SourceResult,
    aware,
    safe_url,
)

if TYPE_CHECKING:
    from .transport import Transport, TransportResponse
else:
    from .transport import Transport, TransportError, TransportResponse

PARSER_VERSION = "arxiv-v1"
SOURCE_NAME = "arxiv"

NAMESPACES: dict[str, str] = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

MAX_PAGING_PAGES = 10
DEFAULT_PAGE_SIZE = 50

ARXIV_MODERN_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v[1-9]\d*)?$")
ARXIV_OLD_ID_RE = re.compile(r"^[a-zA-Z\-]+(\.[a-zA-Z\-]+)?/\d{7}(v[1-9]\d*)?$")


class ArxivAdapterError(Exception):
    """Exception wrapping a validated SearchError model."""

    def __init__(self, error: SearchError):
        self.error = error
        super().__init__(error.message)


class StrictArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with status code 1 and a clean FAIL message upon error."""

    def error(self, message: str) -> None:
        print(f"FAIL: invalid CLI arguments: {message}", file=sys.stderr)
        sys.exit(1)


class DuplicateKeyError(ValueError):
    """Raised when JSON object contains duplicate keys."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Parse JSON object rejecting duplicate keys."""
    res: dict[str, Any] = {}
    for k, v in pairs:
        if k in res:
            raise DuplicateKeyError(f"duplicate key in JSON: {k}")
        res[k] = v
    return res


def make_search_error(
    kind: Literal["request", "config", "policy", "auth", "quota", "timeout", "upstream", "schema", "storage"],
    message: str,
    *,
    record_index: int | None = None,
    retry_after_seconds: float | None = None,
) -> SearchError:
    """Construct a strict SearchError model with all required nullable fields populated."""
    return SearchError(
        kind=kind,
        message=message,
        source=SOURCE_NAME,
        retry_after_seconds=retry_after_seconds,
        record_index=record_index,
    )


def fail_adapter(
    kind: Literal["request", "config", "policy", "auth", "quota", "timeout", "upstream", "schema", "storage"],
    message: str,
    *,
    record_index: int | None = None,
    retry_after_seconds: float | None = None,
) -> None:
    """Raise ArxivAdapterError wrapping a strictly validated SearchError."""
    err = make_search_error(kind, message, record_index=record_index, retry_after_seconds=retry_after_seconds)
    raise ArxivAdapterError(err)


def build_arxiv_query(raw_query: str) -> str:
    """Build and validate an arXiv search_query string from user query text.

    Rules:
    - Validates balanced quotes and parentheses; rejects malformed unbalanced syntax with request error.
    - Preserves standard boolean operators (AND, OR, ANDNOT) and field prefixes (ti:, au:, abs:, all:).
    - Wraps plain text queries into all:(<clean_query>) for unambiguous term searching.
    - Parameter injection is prevented by transport encoding the search_query parameter value.
    """
    clean = " ".join(raw_query.strip().split())
    if not clean:
        fail_adapter("request", "empty query text after normalization")

    # Reject unbalanced quotes without silent fixing
    if clean.count('"') % 2 != 0:
        fail_adapter("request", "query has unbalanced double quotes")

    # Reject unbalanced parentheses without silent fixing
    if clean.count("(") != clean.count(")"):
        fail_adapter("request", "query has unbalanced parentheses")

    known_prefixes = ("ti:", "au:", "abs:", "co:", "jr:", "cat:", "rn:", "id:", "all:")
    lower = clean.lower()
    has_prefix = any(lower.startswith(prefix) for prefix in known_prefixes)

    if has_prefix:
        return clean
    return f"all:({clean})"


def sniff_xml_encoding(raw_bytes: bytes) -> str:
    """Sniff XML character encoding following XML Appendix F autodetection signatures.

    Supported encodings: UTF-8 and UTF-16 (LE/BE, with or without BOM).
    UTF-32 (LE/BE, with or without BOM) is deterministically sniffed and rejected
    as unsupported XML encoding.
    """
    if len(raw_bytes) < 4:
        fail_adapter("schema", "XML payload too short")

    prefix4 = raw_bytes[:4]

    # 1. UTF-32 signatures: 4-byte BOM or 4-byte ASCII '<'
    if prefix4 == b"\x00\x00\xfe\xff" or prefix4 == b"\x00\x00\x00<":
        fail_adapter("schema", "unsupported XML declared encoding: UTF-32 is not supported")
    if prefix4 == b"\xff\xfe\x00\x00" or prefix4 == b"<\x00\x00\x00":
        fail_adapter("schema", "unsupported XML declared encoding: UTF-32 is not supported")

    # 2. UTF-16 signatures (with BOM)
    if prefix4.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if prefix4.startswith(b"\xff\xfe"):
        return "utf-16-le"

    # 3. UTF-16 without BOM (starts with '<' followed by null or null followed by '<')
    if prefix4[0] == 0x3C and prefix4[1] == 0x00 and prefix4[2] != 0x00:
        return "utf-16-le"
    if prefix4[0] == 0x00 and prefix4[1] == 0x3C and prefix4[2] == 0x00:
        return "utf-16-be"

    # 4. UTF-8 with BOM
    if prefix4.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    # 5. Check XML declaration for declared encoding in ASCII family
    match = re.match(br'<\?xml[^>]+encoding=["\']([a-zA-Z0-9_\-]+)["\']', raw_bytes[:120], re.IGNORECASE)
    if match:
        declared = match.group(1).decode("ascii", errors="ignore").lower()
        if declared in ("utf-32", "utf-32-le", "utf-32-be", "ucs-4"):
            fail_adapter("schema", "unsupported XML declared encoding: UTF-32 is not supported")
        try:
            codec_info = codecs.lookup(declared)
            canon_name = codec_info.name.lower()
            if "utf-32" in canon_name or "ucs-4" in canon_name:
                fail_adapter("schema", "unsupported XML declared encoding: UTF-32 is not supported")
            return declared
        except LookupError:
            fail_adapter("schema", "unsupported XML declared encoding")

    return "utf-8"


def verify_xml_with_expat(raw_bytes: bytes, encoding: str) -> None:
    """Reject DOCTYPE and ENTITY at parser boundary using stdlib Expat handlers."""
    try:
        parser = xml.parsers.expat.ParserCreate()
    except Exception:
        fail_adapter("schema", "failed to initialize XML parser")

    def on_doctype(doctypeName, systemId, publicId, has_internal_subset):
        fail_adapter("schema", "XML DOCTYPE declaration forbidden")

    def on_entity(entityName, is_parameter_entity, value, base, systemId, publicId, notationName):
        fail_adapter("schema", "XML ENTITY declaration forbidden")

    parser.StartDoctypeDeclHandler = on_doctype
    parser.EntityDeclHandler = on_entity

    try:
        parser.Parse(raw_bytes, True)
    except ArxivAdapterError:
        raise
    except (xml.parsers.expat.ExpatError, ValueError):
        fail_adapter("schema", "malformed XML payload")


def check_xml_security(raw_bytes: bytes) -> str:
    """Verify XML payload is safe, well-encoded, and free of DOCTYPE/ENTITY declarations.

    Rejects DOCTYPE and ENTITY declarations across supported encodings (UTF-8, UTF-16).
    Unsupported encodings like UTF-32 fail schema cleanly.
    """
    if len(raw_bytes) == 0:
        fail_adapter("schema", "empty XML payload")

    encoding = sniff_xml_encoding(raw_bytes)

    try:
        text = raw_bytes.decode(encoding)
    except Exception:
        fail_adapter("schema", "XML decoding failed for declared encoding")

    text_lower = text.lower()
    if "<!doctype" in text_lower:
        fail_adapter("schema", "XML DOCTYPE declaration forbidden")
    if "<!entity" in text_lower:
        fail_adapter("schema", "XML ENTITY declaration forbidden")

    verify_xml_with_expat(raw_bytes, encoding)

    return text


def detect_upstream_error_entry(entry: ET.Element, idx: int) -> None:
    """Detect if an Atom entry represents an arXiv error response (HTTP 200 error feed).

    arXiv API error responses return standard Atom entries with an id containing:
    http://arxiv.org/api/errors#...
    Does NOT rely on title or abstract text so valid research papers (e.g. with title 'Error'
    or abstract discussing 'Error correction') are never falsely rejected.
    """
    id_elem = entry.find("atom:id", NAMESPACES)
    if id_elem is None or not (id_elem.text or "").strip():
        return

    raw_id = id_elem.text.strip().lower()
    if "arxiv.org/api/errors" in raw_id or raw_id.startswith(("http://arxiv.org/api/errors", "https://arxiv.org/api/errors")):
        fail_adapter("upstream", "arXiv upstream query error entry detected", record_index=idx)


def extract_and_validate_arxiv_id(raw_id: str, idx: int) -> str:
    """Extract and strictly validate an arXiv ID from atom:id.

    Supports:
    - Modern format: YYMM.NNNN or YYMM.NNNNN, optional version v[1-9]\\d*
    - Old-style archive format: archive/YYMMNNN or archive.subj/YYMMNNN, optional version v[1-9]\\d*
    - URL format: https?://(arxiv.org|export.arxiv.org|www.arxiv.org)/abs/<id>
      (must have valid host, path starting with /abs/, no query, no fragment).
    - URI prefix: arxiv:<id>

    Rejects:
    - Version 0 (e.g. v0, v01)
    - Foreign hosts (e.g. foreign.invalid)
    - Arbitrary strings (e.g. NOT_AN_ARXIV_ID)
    """
    clean = raw_id.strip()
    if not clean:
        fail_adapter("schema", "entry has empty id", record_index=idx)

    candidate: str
    if clean.startswith(("http://", "https://")):
        try:
            safe_url(clean)
            parsed = urlsplit(clean)
            if "@" in (parsed.netloc or ""):
                raise ValueError("userinfo forbidden")
            if parsed.netloc.endswith(":"):
                raise ValueError("empty port forbidden")
            if parsed.port is not None and not (1 <= parsed.port <= 65535):
                raise ValueError("port out of range")
        except ValueError:
            fail_adapter("schema", "entry id URL has invalid syntax or port", record_index=idx)

        host = (parsed.hostname or "").lower()
        if host not in ("arxiv.org", "export.arxiv.org", "www.arxiv.org"):
            fail_adapter("schema", "entry id URL host is not arXiv", record_index=idx)
        if parsed.query or parsed.fragment:
            fail_adapter("schema", "entry id URL must not contain query or fragment", record_index=idx)
        path = parsed.path
        if not path.startswith("/abs/"):
            fail_adapter("schema", "entry id URL path must start with /abs/", record_index=idx)
        candidate = path[5:].strip()
    elif clean.lower().startswith("arxiv:"):
        candidate = clean[6:].strip()
    else:
        candidate = clean

    if not candidate:
        fail_adapter("schema", "entry has invalid empty arxiv_id", record_index=idx)

    if not (ARXIV_MODERN_ID_RE.match(candidate) or ARXIV_OLD_ID_RE.match(candidate)):
        fail_adapter("schema", "entry has invalid arXiv ID format", record_index=idx)

    return candidate


def parse_opensearch_counts(root: ET.Element) -> tuple[int, int, int]:
    """Strictly parse OpenSearch pagination counters with Anti-Silent-Bypass."""
    total_elem = root.find("opensearch:totalResults", NAMESPACES)
    if total_elem is None:
        fail_adapter("schema", "missing required opensearch:totalResults")
    total_raw = (total_elem.text or "").strip()
    if not total_raw.isdigit():
        fail_adapter("schema", "invalid opensearch:totalResults counter")
    total = int(total_raw)

    start_elem = root.find("opensearch:startIndex", NAMESPACES)
    if start_elem is None:
        fail_adapter("schema", "missing required opensearch:startIndex")
    start_raw = (start_elem.text or "").strip()
    if not start_raw.isdigit():
        fail_adapter("schema", "invalid opensearch:startIndex counter")
    start = int(start_raw)

    items_elem = root.find("opensearch:itemsPerPage", NAMESPACES)
    if items_elem is None:
        fail_adapter("schema", "missing required opensearch:itemsPerPage")
    items_raw = (items_elem.text or "").strip()
    if not items_raw.isdigit():
        fail_adapter("schema", "invalid opensearch:itemsPerPage counter")
    items_per_page = int(items_raw)

    return total, start, items_per_page


def parse_iso_datetime(dt_str: str, field_name: str, idx: int) -> datetime:
    """Parse timezone-aware ISO 8601 datetime string strictly."""
    clean = dt_str.strip()
    if not clean:
        fail_adapter("schema", f"entry has invalid {field_name} timestamp", record_index=idx)
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(clean)
        return aware(dt)
    except Exception:
        fail_adapter("schema", f"entry has invalid {field_name} timestamp", record_index=idx)
        raise  # unreachable


def parse_entry(
    entry: ET.Element,
    idx: int,
    retrieved_at: datetime,
    raw_sha256: str,
) -> PaperRecord:
    """Parse and validate a single arXiv Atom entry into a strict PaperRecord."""
    # 1. ID & arxiv_id (required singleton)
    id_elems = entry.findall("atom:id", NAMESPACES)
    if len(id_elems) != 1:
        fail_adapter("schema", "entry must contain exactly one atom:id", record_index=idx)
    raw_id = (id_elems[0].text or "").strip()
    arxiv_id = extract_and_validate_arxiv_id(raw_id, idx)
    source_id = arxiv_id

    # 2. Title (required singleton, non-empty)
    title_elems = entry.findall("atom:title", NAMESPACES)
    if len(title_elems) != 1:
        fail_adapter("schema", "entry must contain exactly one atom:title", record_index=idx)
    title = " ".join((title_elems[0].text or "").split())
    if not title:
        fail_adapter("schema", "entry has empty title after normalization", record_index=idx)

    # 3. Summary / Abstract (optional singleton; Title-only is valid when summary absent/empty)
    summary_elems = entry.findall("atom:summary", NAMESPACES)
    if len(summary_elems) > 1:
        fail_adapter("schema", "entry has duplicate atom:summary", record_index=idx)
    abstract: str | None = None
    if len(summary_elems) == 1 and (summary_elems[0].text or "").strip():
        norm_summary = " ".join(summary_elems[0].text.split())
        if norm_summary:
            abstract = norm_summary

    # 4. Dates & Publication Year (optional singletons)
    published_elems = entry.findall("atom:published", NAMESPACES)
    if len(published_elems) > 1:
        fail_adapter("schema", "entry has duplicate atom:published", record_index=idx)
    publication_year: int | None = None
    if len(published_elems) == 1:
        pub_raw = (published_elems[0].text or "").strip()
        if not pub_raw:
            fail_adapter("schema", "entry has invalid published timestamp", record_index=idx)
        dt = parse_iso_datetime(pub_raw, "published", idx)
        if dt.year < YEAR_MIN or dt.year > YEAR_MAX:
            fail_adapter("schema", "entry publication year out of range", record_index=idx)
        publication_year = dt.year

    updated_elems = entry.findall("atom:updated", NAMESPACES)
    if len(updated_elems) > 1:
        fail_adapter("schema", "entry has duplicate atom:updated", record_index=idx)
    if len(updated_elems) == 1:
        upd_raw = (updated_elems[0].text or "").strip()
        if not upd_raw:
            fail_adapter("schema", "entry has invalid updated timestamp", record_index=idx)
        parse_iso_datetime(upd_raw, "updated", idx)

    # 5. Venue (from arxiv:journal_ref, optional singleton)
    jr_elems = entry.findall("arxiv:journal_ref", NAMESPACES)
    if len(jr_elems) > 1:
        fail_adapter("schema", "entry has duplicate arxiv:journal_ref", record_index=idx)
    venue: str | None = None
    if len(jr_elems) == 1 and (jr_elems[0].text or "").strip():
        venue = " ".join(jr_elems[0].text.split())

    # 6. DOI (strictly from arxiv:doi, optional singleton)
    doi_elems = entry.findall("arxiv:doi", NAMESPACES)
    if len(doi_elems) > 1:
        fail_adapter("schema", "entry has duplicate arxiv:doi", record_index=idx)
    doi: str | None = None
    if len(doi_elems) == 1 and (doi_elems[0].text or "").strip():
        raw_doi = doi_elems[0].text.strip()
        for prefix in ("https://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "http://doi.org/", "doi:"):
            if raw_doi.lower().startswith(prefix):
                raw_doi = raw_doi[len(prefix):].strip()
                break
        if not re.fullmatch(r"10\.\d{4,9}/[^\s]+", raw_doi, flags=re.IGNORECASE):
            fail_adapter("schema", "entry has malformed DOI format", record_index=idx)
        doi = raw_doi

    # 7. Links: landing_url (required), pdf_url (optional), license (optional)
    # Extracts exact attribute selector provenance for FieldEvidence
    landing_url: str | None = None
    landing_raw_field: str | None = None
    pdf_url: str | None = None
    pdf_raw_field: str | None = None
    license_val: str | None = None
    license_raw_field: str | None = None

    for link in entry.findall("atom:link", NAMESPACES):
        href = (link.attrib.get("href") or "").strip()
        if not href:
            continue
        rel = (link.attrib.get("rel") or "").strip()
        link_type = (link.attrib.get("type") or "").strip().lower()
        title_attr = (link.attrib.get("title") or "").strip().lower()

        # PDF Link
        if link_type == "application/pdf" or title_attr == "pdf":
            if not pdf_url:
                pdf_url = href
                if title_attr == "pdf":
                    pdf_raw_field = "atom:link[title=pdf]"
                elif link_type == "application/pdf":
                    pdf_raw_field = "atom:link[type=application/pdf]"
                else:
                    pdf_raw_field = "atom:link[pdf]"
            continue

        # License Link (strictly rel="license", never rel="related")
        if rel == "license":
            if not license_val:
                license_val = href
                license_raw_field = "atom:link[rel=license]"
            continue

        # Landing URL (alternate HTML link or bare href)
        if rel in ("alternate", "") and link_type in ("text/html", ""):
            if not landing_url:
                landing_url = href
                if rel == "alternate":
                    landing_raw_field = "atom:link[rel=alternate]"
                elif link_type == "text/html":
                    landing_raw_field = "atom:link[type=text/html]"
                else:
                    landing_raw_field = "atom:link[href]"

    # Also check arxiv:license element if license not yet found from link
    if not license_val:
        lic_elems = entry.findall("arxiv:license", NAMESPACES)
        if len(lic_elems) > 1:
            fail_adapter("schema", "entry has duplicate arxiv:license", record_index=idx)
        if len(lic_elems) == 1 and (lic_elems[0].text or "").strip():
            license_val = lic_elems[0].text.strip()
            license_raw_field = "arxiv:license"

    if not landing_url:
        fail_adapter("schema", "entry missing required landing_url", record_index=idx)

    try:
        landing_url = safe_url(landing_url)
    except ValueError:
        fail_adapter("schema", "entry has invalid landing_url", record_index=idx)

    if pdf_url is not None:
        try:
            pdf_url = safe_url(pdf_url)
        except ValueError:
            fail_adapter("schema", "entry has invalid pdf_url", record_index=idx)

    # 8. Authors
    author_elements = entry.findall("atom:author", NAMESPACES)
    authors: list[str] | None = None
    authors_availability: Literal["known", "missing"] = "missing"

    if author_elements:
        names: list[str] = []
        for a_idx, author_elem in enumerate(author_elements):
            name_elems = author_elem.findall("atom:name", NAMESPACES)
            if len(name_elems) != 1:
                fail_adapter("schema", "entry has author tag but missing or duplicate name", record_index=idx)
            clean_name = " ".join((name_elems[0].text or "").split())
            if not clean_name:
                fail_adapter("schema", "entry has author tag with empty name", record_index=idx)
            names.append(clean_name)
        authors = names
        authors_availability = "known"
    else:
        authors = None
        authors_availability = "missing"

    # 9. Open Access Status & Citation Count
    # Rule: No OA claim solely due to presence of PDF link.
    open_access_status = None
    citation_count = None

    # 10. missing_fields: exact null nullable fields
    nullable_map = {
        "abstract": abstract,
        "publication_year": publication_year,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "venue": venue,
        "pdf_url": pdf_url,
        "license": license_val,
        "open_access_status": open_access_status,
        "citation_count": citation_count,
        "authors": authors,
    }
    missing_fields = sorted([k for k, v in nullable_map.items() if v is None])

    # 11. field_provenance: exact present fields
    field_provenance: dict[str, list[FieldEvidence]] = {}

    def add_evidence(field_name: str, raw_field: str):
        field_provenance[field_name] = [
            FieldEvidence(
                source=SOURCE_NAME,
                source_id=source_id,
                raw_sha256=raw_sha256,
                raw_field=raw_field,
            )
        ]

    add_evidence("title", "atom:title")
    add_evidence("source_id", "atom:id")
    add_evidence("landing_url", landing_raw_field or "atom:link[rel=alternate]")

    if abstract is not None:
        add_evidence("abstract", "atom:summary")
    if publication_year is not None:
        add_evidence("publication_year", "atom:published")
    if doi is not None:
        add_evidence("doi", "arxiv:doi")
    if arxiv_id is not None:
        add_evidence("arxiv_id", "atom:id")
    if venue is not None:
        add_evidence("venue", "arxiv:journal_ref")
    if pdf_url is not None:
        add_evidence("pdf_url", pdf_raw_field or "atom:link[title=pdf]")
    if license_val is not None:
        add_evidence("license", license_raw_field or "atom:link[rel=license]")
    if open_access_status is not None:
        add_evidence("open_access_status", "open_access_status")
    if citation_count is not None:
        add_evidence("citation_count", "citation_count")
    if authors is not None:
        add_evidence("authors", "atom:author")

    try:
        return PaperRecord(
            source=SOURCE_NAME,
            source_id=source_id,
            title=title,
            landing_url=landing_url,
            retrieved_at=retrieved_at,
            raw_sha256=raw_sha256,
            parser_version=PARSER_VERSION,
            abstract=abstract,
            publication_year=publication_year,
            doi=doi,
            arxiv_id=arxiv_id,
            venue=venue,
            pdf_url=pdf_url,
            license=license_val,
            open_access_status=open_access_status,
            citation_count=citation_count,
            authors=authors,
            authors_availability=authors_availability,
            missing_fields=missing_fields,
            field_provenance=field_provenance,
        )
    except ValidationError:
        fail_adapter("schema", "entry PaperRecord validation failed", record_index=idx)
        raise  # unreachable


def parse_feed_payload(
    raw_bytes: bytes,
    expected_start: int | None,
    retrieved_at: datetime,
    raw_sha256: str,
    max_requested_items: int | None = None,
) -> tuple[int, int, int, list[PaperRecord]]:
    """Parse, securely validate, and extract PaperRecords from an arXiv Atom feed payload.

    Unified validation logic used by both search() and CLI boundary runner:
    - Verifies XML security (DOCTYPE/ENTITY rejection, UTF-8/UTF-16 support, UTF-32 rejection).
    - Validates root element is Atom feed (<feed xmlns="http://www.w3.org/2005/Atom">).
    - Detects HTTP 200 error entries FIRST before parsing counters (error feeds may lack counters).
    - Strictly checks singleton cardinality on feed and entry elements.
    - Checks OpenSearch counters strictly:
      * itemsPerPage == 0 with entries fails schema.
      * start + entries > totalResults fails schema.
      * len(entries) == 0 when total > start fails upstream (incomplete feed).
      * expected_start matches opensearch:startIndex if expected_start is provided.
    - Validates ALL entries in the feed (detecting duplicate IDs, invalid IDs, and schema violations).
    """
    xml_text = check_xml_security(raw_bytes)
    try:
        # Strip XML declaration if present to avoid Expat ValueError on decoded Python str
        clean_xml = re.sub(r'<\?xml[^>]*\?>', '', xml_text, count=1)
        root = ET.fromstring(clean_xml)
    except (ET.ParseError, ValueError):
        fail_adapter("schema", "malformed XML payload")

    # Root element MUST be Atom feed
    if root.tag != f"{{{NAMESPACES['atom']}}}feed":
        fail_adapter("schema", f"root element must be Atom feed, got {root.tag}")

    # Check feed singleton elements (F4)
    feed_id_elems = root.findall("atom:id", NAMESPACES)
    if len(feed_id_elems) != 1:
        fail_adapter("schema", "feed must contain exactly one atom:id")

    feed_title_elems = root.findall("atom:title", NAMESPACES)
    if len(feed_title_elems) != 1:
        fail_adapter("schema", "feed must contain exactly one atom:title")

    feed_updated_elems = root.findall("atom:updated", NAMESPACES)
    if len(feed_updated_elems) != 1:
        fail_adapter("schema", "feed must contain exactly one atom:updated")

    # 1. FIRST: Detect upstream HTTP 200 error entries across all entries
    # Upstream error feeds may not have OpenSearch counters at all!
    entries = root.findall("atom:entry", NAMESPACES)
    for idx, entry in enumerate(entries):
        detect_upstream_error_entry(entry, (expected_start or 0) + idx)

    # 2. SECOND: Parse OpenSearch counters strictly (only for non-error feeds)
    total_elems = root.findall("opensearch:totalResults", NAMESPACES)
    if len(total_elems) != 1:
        fail_adapter("schema", "feed must contain exactly one opensearch:totalResults")

    start_elems = root.findall("opensearch:startIndex", NAMESPACES)
    if len(start_elems) != 1:
        fail_adapter("schema", "feed must contain exactly one opensearch:startIndex")

    items_elems = root.findall("opensearch:itemsPerPage", NAMESPACES)
    if len(items_elems) != 1:
        fail_adapter("schema", "feed must contain exactly one opensearch:itemsPerPage")

    total, start, items_per_page = parse_opensearch_counts(root)

    # 3. Counter semantic validations
    if items_per_page == 0 and len(entries) > 0:
        fail_adapter("schema", "itemsPerPage is 0 but entries present")
    if total >= 0 and start + len(entries) > total:
        fail_adapter("schema", "start index plus entries count exceeds totalResults")
    if len(entries) == 0 and total > start:
        fail_adapter("upstream", "empty page received when totalResults exceeds startIndex")

    if expected_start is not None and start != expected_start:
        fail_adapter("schema", f"page startIndex mismatch: expected {expected_start}, got {start}")

    if max_requested_items is not None and len(entries) > max_requested_items:
        fail_adapter("schema", "entries count exceeds requested page size")
    if items_per_page > 0 and len(entries) > items_per_page:
        fail_adapter("schema", "entries count exceeds itemsPerPage counter")

    # 4. Parse and validate all entries
    feed_records: list[PaperRecord] = []
    seen_in_feed: set[str] = set()

    for idx, entry in enumerate(entries):
        record_idx = start + idx
        record = parse_entry(entry, record_idx, retrieved_at, raw_sha256)
        if record.source_id in seen_in_feed:
            fail_adapter("schema", "duplicate record ID within feed", record_index=record_idx)
        seen_in_feed.add(record.source_id)
        feed_records.append(record)

    return total, start, items_per_page, feed_records


def search(request: SearchRequest, transport: Transport) -> SourceResult:
    """Execute public paper search on arXiv using the unified transport.

    Adheres strictly to the public search contract:
    - If 'arxiv' is not in request.sources, immediately returns not_requested without network.
    - Uses unified transport.deadline() across all pagination calls.
    - Handles arXiv pagination bounded by cap_per_source.
    - Detects infinite loops, repeated page hashes, duplicate IDs, and HTTP 200 error feeds.
    - Correctly sets filter_coverage to 'bounded_pool' when year filters are present,
      and 'none' when no year filter is requested.
    - Preserves RawReferences for all received payloads even upon schema failure.
    """
    if SOURCE_NAME not in request.sources:
        return SourceResult(
            source=SOURCE_NAME,
            status="not_requested",
            records=[],
            error=None,
            source_total=None,
            elapsed_seconds=None,
            filter_coverage="none",
            truncated=None,
            raw_references=[],
        )

    start_time = transport.clock()
    deadline = transport.deadline()
    target_count = request.cap_per_source

    raw_references: list[RawReference] = []

    # Map filter_coverage: bounded_pool if year filter is requested, else none
    filter_cov: Literal["server", "bounded_pool", "none"] = (
        "bounded_pool" if (request.year_from is not None or request.year_to is not None) else "none"
    )

    try:
        query_str = build_arxiv_query(request.query)

        all_records: list[PaperRecord] = []
        all_seen_ids: set[str] = set()
        seen_page_hashes: set[str] = set()

        start_offset = 0
        initial_total: int | None = None

        for page_num in range(MAX_PAGING_PAGES):
            if len(all_records) >= target_count:
                break

            remaining_needed = target_count - len(all_records)
            page_size = min(DEFAULT_PAGE_SIZE, remaining_needed)

            params: dict[str, str | int] = {
                "search_query": query_str,
                "start": start_offset,
                "max_results": page_size,
            }

            resp = transport.get(SOURCE_NAME, params, deadline=deadline)

            # Check for duplicate page response (infinite loop protection)
            if resp.sha256 in seen_page_hashes:
                fail_adapter("upstream", "repeated identical page response from arXiv")
            seen_page_hashes.add(resp.sha256)

            # Record raw reference for this response
            raw_references.append(
                RawReference(
                    raw_id=f"arxiv-{resp.sha256}",
                    sha256=resp.sha256,
                    byte_count=len(resp.body),
                )
            )

            retrieved_at = aware(datetime.now(timezone.utc))

            # Unified validation of whole feed
            page_total, page_start, page_items, page_records = parse_feed_payload(
                resp.body,
                expected_start=start_offset,
                retrieved_at=retrieved_at,
                raw_sha256=resp.sha256,
                max_requested_items=page_size,
            )

            # Track and verify totalResults consistency across pages
            if initial_total is None:
                initial_total = page_total
            elif page_total != initial_total:
                fail_adapter("schema", "feed totalResults changed unexpectedly between pages")

            # Check duplicate IDs across all pages
            for idx, record in enumerate(page_records):
                if record.source_id in all_seen_ids:
                    fail_adapter("schema", "duplicate record ID across pages", record_index=start_offset + idx)
                all_seen_ids.add(record.source_id)

            # Append needed records up to target_count
            needed = target_count - len(all_records)
            all_records.extend(page_records[:needed])

            start_offset += len(page_records)
            if start_offset >= initial_total or len(page_records) == 0:
                break

        elapsed = max(0.0, transport.clock() - start_time)

        if not all_records:
            return SourceResult(
                source=SOURCE_NAME,
                status="empty",
                records=[],
                error=None,
                source_total=initial_total,
                elapsed_seconds=elapsed,
                filter_coverage=filter_cov,
                truncated=False,
                raw_references=raw_references,
            )

        truncated = (initial_total is not None and initial_total > len(all_records))

        return SourceResult(
            source=SOURCE_NAME,
            status="success",
            records=all_records,
            error=None,
            source_total=initial_total,
            elapsed_seconds=elapsed,
            filter_coverage=filter_cov,
            truncated=truncated,
            raw_references=raw_references,
        )

    except ArxivAdapterError as err:
        elapsed = max(0.0, transport.clock() - start_time)
        return SourceResult(
            source=SOURCE_NAME,
            status="failed",
            records=[],
            error=err.error,
            source_total=None,
            elapsed_seconds=elapsed,
            filter_coverage="none",
            truncated=None,
            raw_references=raw_references,
        )
    except TransportError as err:
        elapsed = max(0.0, transport.clock() - start_time)
        return SourceResult(
            source=SOURCE_NAME,
            status="failed",
            records=[],
            error=err.error,
            source_total=None,
            elapsed_seconds=elapsed,
            filter_coverage="none",
            truncated=None,
            raw_references=raw_references,
        )
    except Exception as err:
        elapsed = max(0.0, transport.clock() - start_time)
        err_model = make_search_error("upstream", f"unexpected error: {type(err).__name__}")
        return SourceResult(
            source=SOURCE_NAME,
            status="failed",
            records=[],
            error=err_model,
            source_total=None,
            elapsed_seconds=elapsed,
            filter_coverage="none",
            truncated=None,
            raw_references=raw_references,
        )


def main() -> int:
    """Executable boundary validator for arXiv XML payload fixtures (CLI boundary-only).

    Boundary CLI note:
    The CLI --request option validates the SearchRequest schema and payload integrity
    (including duplicate key rejection). It is a fixture/boundary validation utility,
    not a live search runner, and does not execute query translation or network search.
    """
    parser = StrictArgumentParser(
        description="arXiv adapter boundary validator (not production search CLI)"
    )
    parser.add_argument("--payload", required=True, help="Path to XML payload fixture")
    parser.add_argument("--request", required=False, help="Optional path to SearchRequest JSON")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    if not payload_path.exists():
        print(f"FAIL: payload file does not exist: {payload_path}", file=sys.stderr)
        return 1

    # Validate request file if supplied (strict validation with duplicate key rejection)
    if args.request:
        req_path = Path(args.request)
        if not req_path.exists():
            print(f"FAIL: request file does not exist: {req_path}", file=sys.stderr)
            return 1
        try:
            raw_req_text = req_path.read_text(encoding="utf-8")
            req_data = json.loads(raw_req_text, object_pairs_hook=_unique_json_object)
            SearchRequest.model_validate(req_data)
        except DuplicateKeyError:
            print("FAIL: invalid request JSON: duplicate keys detected", file=sys.stderr)
            return 1
        except json.JSONDecodeError:
            print("FAIL: invalid request JSON: malformed JSON syntax", file=sys.stderr)
            return 1
        except ValidationError:
            # Redact error details to prevent leaking sensitive request values (e.g. synthetic secrets)
            print("FAIL: invalid request schema", file=sys.stderr)
            return 1
        except ValueError:
            print("FAIL: invalid request value", file=sys.stderr)
            return 1
        except Exception:
            print("FAIL: invalid request file", file=sys.stderr)
            return 1

    try:
        raw_bytes = payload_path.read_bytes()
        raw_sha = hashlib.sha256(raw_bytes).hexdigest()
        retrieved_at = aware(datetime.now(timezone.utc))

        # Uses the exact same unified parse and validation logic
        total, start, items, records = parse_feed_payload(
            raw_bytes,
            expected_start=None,
            retrieved_at=retrieved_at,
            raw_sha256=raw_sha,
            max_requested_items=None,
        )

        output = {
            "status": "VALIDATED",
            "source": SOURCE_NAME,
            "source_total": total,
            "start_index": start,
            "items_per_page": items,
            "record_count": len(records),
            "records": [r.model_dump(mode="json") for r in records],
        }
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except ArxivAdapterError as err:
        print(f"FAIL: {err.error.kind} error: {err.error.message}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"FAIL: unexpected error: {type(err).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
