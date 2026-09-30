"""Bounded OpenAlex metadata adapter; --payload is a parser boundary, not search CLI."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from .contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchError, SearchRequest,
    SourceResult, YEAR_MIN, YEAR_MAX, aware, safe_url, unique_object,
)
from .transport import Transport, TransportError

PARSER_VERSION = "openalex-1.0.0"
SELECT_FIELDS = (
    "id", "title", "doi", "publication_year", "abstract_inverted_index",
    "authorships", "primary_location", "open_access", "cited_by_count",
)
PAGE_SIZE = 25
NULLABLE_FIELDS = (
    "abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
    "license", "open_access_status", "citation_count", "authors",
)


class OpenAlexSchemaError(ValueError):
    """Fixed description plus record index; never echo upstream values."""
    def __init__(self, field: str, record_index: int | None = None):
        self.record_index = record_index
        super().__init__(f"invalid OpenAlex {field}")


@dataclass(frozen=True)
class ParsedPage:
    records: list[PaperRecord]
    count: int
    per_page: int
    meta: dict
    raw_reference: RawReference


def _text(value, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise OpenAlexSchemaError(field)
    return value.strip()


def _optional(row: dict, key: str):
    # Only documented nullable/optional source metadata uses this accessor.
    return row[key] if key in row else None


def _integer(value, field: str, low: int, high: int | None = None) -> int:
    if type(value) is not int or value < low or (high is not None and value > high):
        raise OpenAlexSchemaError(field)
    return value


def _object(value, field: str) -> dict:
    if type(value) is not dict:
        raise OpenAlexSchemaError(field)
    return value


def _required(row: dict, key: str):
    if key not in row:
        raise OpenAlexSchemaError(key)
    return row[key]


def _reject_label_metadata(value):
    """Online payloads cannot carry evaluator/split label fields into retrieval."""
    if type(value) is dict:
        if any(key.casefold() in {"qrels", "labels", "held_out", "heldout", "test_labels", "dev_labels"}
               for key in value):
            raise OpenAlexSchemaError("label/held-out metadata forbidden")
        for child in value.values():
            _reject_label_metadata(child)
    elif type(value) is list:
        for child in value:
            _reject_label_metadata(child)


def reconstruct_abstract(index) -> str | None:
    if index is None:
        return None
    _object(index, "abstract_inverted_index")
    if not index:
        raise OpenAlexSchemaError("abstract_inverted_index empty object")
    total = 0
    for word, positions in index.items():
        _text(word, "abstract token")
        if type(positions) is not list or not positions:
            raise OpenAlexSchemaError("abstract positions")
        total += len(positions)
    words = [None] * total
    for word, positions in index.items():
        for position in positions:
            _integer(position, "abstract position", 0, total - 1)
            if words[position] is not None:
                raise OpenAlexSchemaError("duplicate abstract position")
            words[position] = word
    if any(word is None for word in words):
        raise OpenAlexSchemaError("noncontiguous abstract positions")
    return " ".join(words)


def normalize_doi(value) -> str | None:
    if value is None:
        return None
    value = _text(value, "doi")
    if value.lower().startswith(("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/")):
        safe_url(value)
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment:
            raise OpenAlexSchemaError("doi resolver query/fragment")
        value = parsed.path[1:]
    elif value.lower().startswith("doi:"):
        value = value[4:].strip()
    if not re.fullmatch(r"10\.\d{4,9}/[^\s]+", value, flags=re.IGNORECASE):
        raise OpenAlexSchemaError("doi")
    return value.casefold()


def _paper(row: dict, sha256: str, retrieved_at: datetime) -> PaperRecord:
    _object(row, "work")
    source_url = _text(_required(row, "id"), "id")
    if not re.fullmatch(r"https://openalex\.org/W[0-9]+", source_url):
        raise OpenAlexSchemaError("id")
    source_id = source_url.rsplit("/", 1)[1]
    title = _text(_required(row, "title"), "title")
    values = {name: None for name in NULLABLE_FIELDS}
    raw_fields = {"source_id": "id", "title": "title", "landing_url": "id"}
    landing_url = source_url  # Explicit source work page, also valid for title-only.
    values["abstract"] = reconstruct_abstract(_optional(row, "abstract_inverted_index"))
    raw_fields["abstract"] = "abstract_inverted_index"
    values["doi"] = normalize_doi(_optional(row, "doi"))
    raw_fields["doi"] = "doi"
    year = _optional(row, "publication_year")
    values["publication_year"] = None if year is None else _integer(year, "publication_year", YEAR_MIN, YEAR_MAX)
    raw_fields["publication_year"] = "publication_year"
    citations = _optional(row, "cited_by_count")
    values["citation_count"] = None if citations is None else _integer(citations, "cited_by_count", 0)
    raw_fields["citation_count"] = "cited_by_count"
    if "relevance_score" in row:
        score = row["relevance_score"]
        if score is not None and (type(score) not in {int, float} or not math.isfinite(score) or score < 0):
            raise OpenAlexSchemaError("relevance_score")
        # Optional source score is not consumed by RRF or called correctness.
    authorships = _optional(row, "authorships")
    if authorships is not None:
        if type(authorships) is not list:
            raise OpenAlexSchemaError("authorships")
        values["authors"] = []
        for authorship in authorships:
            entry = _object(authorship, "authorship")
            author = _object(_required(entry, "author"), "author")
            values["authors"].append(_text(_required(author, "display_name"), "author.display_name"))
        raw_fields["authors"] = "authorships[].author.display_name"
    location = _optional(row, "primary_location")
    if location is not None:
        _object(location, "primary_location")
        for key, field in (("landing_page_url", "landing_url"), ("pdf_url", "pdf_url"), ("license", "license")):
            value = _optional(location, key)
            if value is not None:
                value = _text(value, "primary_location." + key)
                if field != "license":
                    safe_url(value)
                if field == "landing_url":
                    landing_url = value
                else:
                    values[field] = value
                raw_fields[field] = "primary_location." + key
        venue = _optional(location, "source")
        if venue is not None:
            _object(venue, "primary_location.source")
            name = _optional(venue, "display_name")
            if name is not None:
                values["venue"] = _text(name, "primary_location.source.display_name")
                raw_fields["venue"] = "primary_location.source.display_name"
    oa = _optional(row, "open_access")
    if oa is not None:
        _object(oa, "open_access")
        flag = _optional(oa, "is_oa")
        status = _optional(oa, "oa_status")
        if flag is not None and type(flag) is not bool:
            raise OpenAlexSchemaError("open_access.is_oa")
        allowed = {"gold", "green", "hybrid", "bronze", "diamond", "closed", "unknown"}
        if status is not None and (type(status) is not str or status not in allowed):
            raise OpenAlexSchemaError("open_access.oa_status")
        if flag is not None:
            if status is not None and status != "unknown" and (status != "closed") != flag:
                raise OpenAlexSchemaError("conflicting open_access")
            values["open_access_status"] = "open" if flag else "closed"
            raw_fields["open_access_status"] = "open_access.is_oa"
        elif status is not None:
            values["open_access_status"] = "unknown" if status == "unknown" else ("closed" if status == "closed" else "open")
            raw_fields["open_access_status"] = "open_access.oa_status"
    provenance = {
        field: [FieldEvidence(source="openalex", source_id=source_id, raw_sha256=sha256, raw_field=raw_fields[field])]
        for field in ("source_id", "title", "landing_url", *NULLABLE_FIELDS)
        if field not in values or values[field] is not None
    }
    return PaperRecord(
        source="openalex", source_id=source_id, title=title, landing_url=landing_url,
        retrieved_at=aware(retrieved_at), raw_sha256=sha256, parser_version=PARSER_VERSION,
        **values, authors_availability="missing" if values["authors"] is None else "known",
        missing_fields=[name for name in NULLABLE_FIELDS if values[name] is None], field_provenance=provenance,
    )


def parse_page(body: bytes, *, retrieved_at: datetime) -> ParsedPage:
    """Require list metadata; validate every record before exposing a page."""
    sha256 = hashlib.sha256(body).hexdigest()
    reference = RawReference(raw_id="openalex-" + sha256, sha256=sha256, byte_count=len(body))
    try:
        row = json.loads(body, object_pairs_hook=unique_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        _object(row, "envelope")
        _reject_label_metadata(row)
        if "error" in row:
            raise OpenAlexSchemaError("upstream error envelope")
        meta = _object(_required(row, "meta"), "meta")
        count = _integer(_required(meta, "count"), "meta.count", 0)
        per_page = _integer(_required(meta, "per_page"), "meta.per_page", 1, 100)
        if "page" in meta and meta["page"] is not None:
            _integer(meta["page"], "meta.page", 1)
        if "next_cursor" in meta and meta["next_cursor"] is not None:
            _text(meta["next_cursor"], "meta.next_cursor")
        rows = _required(row, "results")
        if type(rows) is not list or len(rows) > per_page or len(rows) > count:
            raise OpenAlexSchemaError("results/count/per_page")
    except OpenAlexSchemaError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise OpenAlexSchemaError("JSON payload") from None
    records = []
    seen = set()
    for index, work in enumerate(rows):
        try:
            record = _paper(work, sha256, retrieved_at)
            if record.source_id in seen:
                raise OpenAlexSchemaError("duplicate work id")
        except (ValueError, TypeError, KeyError, OverflowError):
            raise OpenAlexSchemaError("record metadata", index) from None
        seen.add(record.source_id)
        records.append(record)
    return ParsedPage(records, count, per_page, meta, reference)


def search(request: SearchRequest, transport: Transport) -> SourceResult:
    """Cursor pool <= cap, one deadline; failure exposes no partial source records."""
    if "openalex" not in request.sources:
        return SourceResult(source="openalex", status="not_requested", records=[], error=None,
                            source_total=None, elapsed_seconds=None, filter_coverage="none",
                            truncated=None, raw_references=[])
    start = transport.clock()
    deadline = transport.deadline()
    records, references = [], []
    reference_hashes, seen_ids, seen_cursors = set(), set(), {"*"}
    total = None
    cursor = "*"
    filters = []
    if request.year_from is not None or request.year_to is not None:
        lower = YEAR_MIN if request.year_from is None else request.year_from
        upper = YEAR_MAX if request.year_to is None else request.year_to
        filters.append(f"publication_year:{lower}-{upper}")
    coverage = "server" if filters else "none"
    try:
        while len(records) < request.cap_per_source:
            per_page = min(PAGE_SIZE, request.cap_per_source - len(records))
            params = {"search": request.query, "cursor": cursor, "per_page": per_page,
                      "select": ",".join(SELECT_FIELDS)}
            if filters:
                params["filter"] = ",".join(filters)
            response = transport.get("openalex", params, deadline=deadline)
            actual_hash = hashlib.sha256(response.body).hexdigest()
            reference = RawReference(raw_id="openalex-" + actual_hash, sha256=actual_hash, byte_count=len(response.body))
            if actual_hash not in reference_hashes:
                references.append(reference)
                reference_hashes.add(actual_hash)
            else:
                raise OpenAlexSchemaError("repeated page body")
            if actual_hash != response.sha256:
                raise OpenAlexSchemaError("transport body hash")
            try:
                page = parse_page(response.body, retrieved_at=transport.wall_clock())
            except OpenAlexSchemaError as exc:
                if exc.record_index is not None:
                    raise OpenAlexSchemaError("record metadata", len(records) + exc.record_index) from None
                raise
            if page.per_page != per_page:
                raise OpenAlexSchemaError("meta.per_page does not match request")
            if total is None:
                total = page.count
            elif page.count != total:
                raise OpenAlexSchemaError("meta.count changed during pagination")
            for index, record in enumerate(page.records):
                if record.source_id in seen_ids:
                    raise OpenAlexSchemaError("work id repeated across pages", len(records) + index)
                if filters and (record.publication_year is None or
                                not lower <= record.publication_year <= upper):
                    raise OpenAlexSchemaError("server year filter violated", len(records) + index)
            if len(records) + len(page.records) > total:
                raise OpenAlexSchemaError("records exceed source total")
            if len(page.records) != min(per_page, total - len(records)):
                raise OpenAlexSchemaError("short or empty page before total exhausted")
            records.extend(page.records)
            seen_ids.update(r.source_id for r in page.records)
            if len(records) == total or len(records) == request.cap_per_source:
                break
            cursor = _text(_required(page.meta, "next_cursor"), "meta.next_cursor")
            if cursor in seen_cursors:
                raise OpenAlexSchemaError("repeated cursor")
            seen_cursors.add(cursor)
        return SourceResult(source="openalex", status="success" if records else "empty",
                            records=records, error=None, source_total=total,
                            elapsed_seconds=transport.clock()-start, filter_coverage=coverage,
                            truncated=total > len(records), raw_references=references)
    except TransportError as exc:
        error = exc.error
    except (OpenAlexSchemaError, ValueError, TypeError) as exc:
        error = SearchError(kind="schema", message="invalid OpenAlex response metadata",
                            source="openalex", retry_after_seconds=None,
                            record_index=exc.record_index if isinstance(exc, OpenAlexSchemaError) else None)
    return SourceResult(source="openalex", status="failed", records=[], error=error,
                        source_total=total, elapsed_seconds=transport.clock()-start,
                        filter_coverage=coverage, truncated=None, raw_references=references)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAlex payload boundary validator; no live search")
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()
    try:
        page = parse_page(Path(args.payload).read_bytes(), retrieved_at=datetime.now(timezone.utc))
        print(json.dumps({"status": "VALIDATED", "source_total": page.count, "records": len(page.records),
                          "raw_sha256": page.raw_reference.sha256}))
        return 0
    except (OSError, ValueError, TypeError):
        print("FAIL: missing or invalid OpenAlex payload", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
