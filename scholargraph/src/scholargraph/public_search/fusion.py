"""Pure bounded-pool fusion. No retrieval, storage, or research-label inputs."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, TypeAdapter, ValidationError

from .contracts import (
    FieldEvidence, FusionCounts, FusionResult, PaperRecord, RankedHit, SearchError,
    SearchRequest, SourceResult, digest, overall_status, safe_url,
)

FUSION_VERSION = "fusion-1.0.0"
RRF_K = 60
_SOURCE_PRIORITY = {"openalex": 0, "arxiv": 1}
_ARXIV = re.compile(r"(?:\d{4}\.\d{4,5}|[A-Za-z-]+(?:\.[A-Za-z-]+)?/\d{7})(?:v[1-9]\d*)?")
_FIELDS = ("source_id", "title", "landing_url", "abstract", "publication_year",
           "doi", "arxiv_id", "venue", "pdf_url", "license", "open_access_status",
           "citation_count", "authors")


class FusionError(ValueError):
    """Redacted structured schema failure; invalid records are never dropped."""

    def __init__(self, message: str):
        super().__init__(message)
        self.error = SearchError(kind="schema", message=message, source=None,
                                 retry_after_seconds=None, record_index=None)


def normalize_doi(value: str) -> str:
    """Normalize an explicit identifier; typed records still require contract DOI syntax."""
    if not isinstance(value, str):
        raise FusionError("invalid DOI")
    value = value.strip()
    if value.casefold().startswith("doi:"):
        value = value[4:].strip()
    if value.casefold().startswith(("http://", "https://")):
        try:
            parsed = urlsplit(safe_url(value))
        except ValueError:
            raise FusionError("invalid DOI resolver") from None
        if parsed.hostname not in {"doi.org", "dx.doi.org"} or parsed.query or parsed.fragment:
            raise FusionError("invalid DOI resolver")
        value = parsed.path.lstrip("/")
    value = value.casefold()
    if not re.fullmatch(r"10\.\d{4,9}/[^\s]+", value):
        raise FusionError("invalid DOI")
    return value


def arxiv_base_id(value: str) -> str:
    """Validate explicit modern/legacy ID, removing version only from group identity."""
    if not isinstance(value, str) or _ARXIV.fullmatch(value) is None:
        raise FusionError("invalid arXiv identifier")
    return re.sub(r"v[1-9]\d*$", "", value).casefold()


def _plain(value):
    # model_validate(model) trusts nested instances by default. Walk actual state,
    # including unknown construct fields, to validate fresh strict dictionaries.
    if isinstance(value, BaseModel):
        row = {key: _plain(item) for key, item in vars(value).items()}
        if value.__pydantic_extra__:
            row.update({key: _plain(item) for key, item in value.__pydantic_extra__.items()})
        return row
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _validated(source_results, request):
    if not isinstance(request, SearchRequest) or type(source_results) is not list:
        raise FusionError("fusion requires typed request and source results")
    if any(not isinstance(result, SourceResult) for result in source_results):
        raise FusionError("fusion requires typed source results")
    try:
        request_state = _plain(request)
        result_states = [_plain(result) for result in source_results]
        request = SearchRequest.model_validate(request_state)
        results = [SourceResult.model_validate(state) for state in result_states]
        if _plain(request) != request_state or [_plain(r) for r in results] != result_states:
            raise ValueError("mutated noncanonical model state")
        overall_status(results, request, 0)
    except (ValidationError, ValueError, TypeError, AttributeError, RecursionError):
        raise FusionError("invalid fusion input schema or source selection") from None
    for result in results:
        if len(result.records) > request.cap_per_source:
            raise FusionError("source pool exceeds request cap")
        if result.source_total is not None and result.source_total < len(result.records):
            raise FusionError("source total smaller than validated pool")
        for record in result.records:
            if record.arxiv_id is not None:
                arxiv_base_id(record.arxiv_id)
    return results, request


def _record_key(record: PaperRecord):
    return (_SOURCE_PRIORITY[record.source], record.source_id, digest(record))


def _evidence(records: list[PaperRecord], field: str) -> list[FieldEvidence]:
    unique = {}
    for record in records:
        if getattr(record, field) is not None:
            for item in record.field_provenance[field]:
                unique[digest(item)] = item
    return [unique[key] for key in sorted(unique)]


def fuse(source_results: list[SourceResult], request: SearchRequest) -> FusionResult:
    """Filter, group explicit identities, then score best original rank per source.

    Alias components connect same-source IDs and explicit arXiv base IDs. DOI
    groups remain separate even when aliases disagree. A DOI-less record joins
    only an alias component with exactly one DOI; an ambiguous component keeps
    DOI-less records separate and exposes all conflicting DOI field evidence.
    """
    results, request = _validated(source_results, request)
    raw = sum(len(result.records) for result in results)
    entries = []
    for result in results:
        for rank, record in enumerate(result.records, 1):
            year = record.publication_year
            if request.year_from is not None or request.year_to is not None:
                if (year is None or (request.year_from is not None and year < request.year_from)
                        or (request.year_to is not None and year > request.year_to)):
                    continue
            entries.append((record, rank))

    # <=100 records. A small alias graph is enough; DOI is deliberately NOT an
    # edge, so a shared arXiv/source ID cannot bridge distinct DOI groups.
    aliases = []
    for record, _ in entries:
        keys = {f"{record.source}:{record.source_id}"}
        if record.arxiv_id is not None:
            keys.add("arxiv:" + arxiv_base_id(record.arxiv_id))
        aliases.append(keys)
    components = []
    pending = set(range(len(entries)))
    while pending:
        indices = {pending.pop()}
        keys = set().union(*(aliases[i] for i in indices))
        while True:
            connected = {i for i in pending if keys & aliases[i]}
            if not connected:
                break
            indices.update(connected)
            pending.difference_update(connected)
            keys.update(*(aliases[i] for i in connected))
        components.append((indices, keys))

    groups = {}
    conflict_context = {}
    for indices, keys in components:
        component_records = [entries[i][0] for i in indices]
        dois = {normalize_doi(r.doi) for r in component_records if r.doi is not None}
        base_ids = {arxiv_base_id(r.arxiv_id) for r in component_records if r.arxiv_id is not None}
        alias_id = "arxiv:" + min(base_ids) if base_ids else min(keys)
        for i in indices:
            record, rank = entries[i]
            if record.doi is not None:
                canonical = "doi:" + normalize_doi(record.doi)
            elif len(dois) == 1:
                canonical = "doi:" + next(iter(dois))
            else:
                canonical = alias_id
            if canonical not in groups:
                groups[canonical] = []
                conflict_context[canonical] = []
            groups[canonical].append((record, rank))
            if len(dois) > 1:
                conflict_context[canonical].extend(component_records)

    hits = []
    for canonical, members in groups.items():
        records = sorted((record for record, _ in members), key=_record_key)
        ranks = {}
        for record, rank in members:
            if record.source not in ranks or rank < ranks[record.source]:
                ranks[record.source] = rank
        conflicts = {}
        for field in _FIELDS:
            present = [r for r in records if getattr(r, field) is not None]
            values = {json.dumps(normalize_doi(r.doi) if field == "doi" else getattr(r, field),
                                 sort_keys=True, ensure_ascii=False) for r in present}
            if len(values) > 1:
                conflicts[field] = _evidence(present, field)
        if conflict_context[canonical]:
            conflicts["doi"] = _evidence(records + conflict_context[canonical], "doi")
        hits.append(RankedHit(canonical_id=canonical, rank=1,
                              score=sum(1 / (RRF_K + ranks[source]) for source in sorted(ranks)),
                              display=records[0], source_records=records,
                              source_ranks=dict(sorted(ranks.items())), conflicts=conflicts))
    hits.sort(key=lambda hit: (-hit.score, hit.canonical_id))
    returned = [hit.model_copy(update={"rank": rank})
                for rank, hit in enumerate(hits[:request.top_k], 1)]
    eligible = len(entries)
    return FusionResult(hits=returned, counts=FusionCounts(
        raw=raw, valid=raw, invalid=0, excluded_by_year=raw-eligible, eligible=eligible,
        groups=len(groups), duplicate_excess=eligible-len(groups), returned=len(returned)))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise FusionError("invalid boundary arguments")


def _unique_object(pairs):
    row = {}
    for key, value in pairs:
        if key in row:
            raise FusionError("duplicate JSON key")
        row[key] = value
    return row


def _nonfinite(value):
    raise FusionError("nonfinite JSON number")


def _read(path: str) -> bytes:
    value = json.loads(Path(path).read_bytes(), object_pairs_hook=_unique_object,
                       parse_constant=_nonfinite)
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def main(argv=None) -> int:
    """Executable fixture/schema boundary, not the production search CLI."""
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--request", required=True)
        parser.add_argument("--source-results", required=True)
        args = parser.parse_args(argv)
        request = SearchRequest.model_validate_json(_read(args.request))
        results = TypeAdapter(list[SourceResult]).validate_json(_read(args.source_results), strict=True)
        fusion = fuse(results, request)
        print(fusion.model_dump_json())
        if overall_status(results, request, len(fusion.hits)) in {"failed", "partial_failure"}:
            print("FAIL: selected source failed", file=sys.stderr)
            return 1
        return 0
    except (OSError, ValueError, TypeError, RecursionError):
        print("FAIL: invalid fusion boundary input", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
