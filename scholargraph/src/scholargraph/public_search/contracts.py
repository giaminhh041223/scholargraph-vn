"""Strict public-search v1 boundary and executable config/request validator."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

CONTRACT_VERSION = "1.0.0"
SCHEMA_VERSION = 1
YEAR_MIN, YEAR_MAX = 1800, 2100
Source = Literal["openalex", "arxiv"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(ge=0)]
Budget = Annotated[int, Field(ge=1, le=50)]
Year = Annotated[int, Field(ge=YEAR_MIN, le=YEAR_MAX)]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]

class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version must be integer")
        return value

class SearchRequest(StrictModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    sources: list[Source]
    top_k: Budget
    cap_per_source: Budget
    year_from: Year | None
    year_to: Year | None
    refresh: bool = False

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, value):
        if not value or len(set(value)) != len(value):
            raise ValueError("sources must be nonempty and unique")
        return sorted(value)

    @model_validator(mode="after")
    def year_order(self):
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("year bounds reversed")
        return self

def safe_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or any(ord(c) <= 32 for c in value) or "\\" in value):
        raise ValueError("URL must be HTTP(S) without credentials/control characters")
    try:
        parsed.port
    except ValueError:
        raise ValueError("invalid URL port") from None
    return value

def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return value

class FieldEvidence(StrictModel):
    source: Source
    source_id: Text
    raw_sha256: Hash
    raw_field: Text

class PaperRecord(StrictModel):
    source: Source
    source_id: Text
    title: Text
    landing_url: Text
    retrieved_at: datetime
    raw_sha256: Hash
    parser_version: Text
    abstract: Text | None
    publication_year: Year | None
    doi: Text | None
    arxiv_id: Text | None
    venue: Text | None
    pdf_url: Text | None
    license: Text | None
    open_access_status: Literal["open", "closed", "unknown"] | None
    citation_count: Count | None
    authors: list[Text] | None
    authors_availability: Literal["known", "missing"]
    missing_fields: list[Text]
    field_provenance: dict[str, list[FieldEvidence]]

    @field_validator("landing_url", "pdf_url")
    @classmethod
    def url(cls, value):
        return None if value is None else safe_url(value)

    @field_validator("doi")
    @classmethod
    def doi_format(cls, value):
        if value is not None and not re.fullmatch(r"10\.\d{4,9}/[^\s]+", value, flags=re.IGNORECASE):
            raise ValueError("doi must be normalized DOI; raw value stays in source evidence")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def timestamp(cls, value):
        return aware(value)

    @model_validator(mode="after")
    def metadata_consistency(self):
        nullable = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
                    "license", "open_access_status", "citation_count", "authors")
        expected = {key for key in nullable if getattr(self, key) is None}
        if set(self.missing_fields) != expected or len(self.missing_fields) != len(expected):
            raise ValueError("missing_fields must exactly describe null metadata")
        if (self.authors is None) != (self.authors_availability == "missing"):
            raise ValueError("authors availability mismatch")
        present = {"title", "source_id", "landing_url"} | (set(nullable) - expected)
        if set(self.field_provenance) != present:
            raise ValueError("provenance required for every present metadata field")
        for entries in self.field_provenance.values():
            if not entries or any(e.source != self.source or e.source_id != self.source_id
                                  or e.raw_sha256 != self.raw_sha256 for e in entries):
                raise ValueError("field provenance does not trace source/raw")
        return self

class SearchError(StrictModel):
    kind: Literal["request", "config", "policy", "auth", "quota", "timeout", "upstream", "schema", "storage"]
    message: Text
    source: Source | None
    retry_after_seconds: Seconds | None
    record_index: Count | None

class RawReference(StrictModel):
    raw_id: Text
    sha256: Hash
    byte_count: Count

class SourceResult(StrictModel):
    source: Source
    status: Literal["success", "empty", "failed", "not_requested"]
    records: list[PaperRecord]
    error: SearchError | None
    source_total: Count | None
    elapsed_seconds: Seconds | None
    filter_coverage: Literal["server", "bounded_pool", "none"]
    truncated: bool | None
    raw_references: list[RawReference]

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("failed requires error; other statuses forbid error")
        if self.error is not None and self.error.source != self.source:
            raise ValueError("error source mismatch")
        if self.status == "success" and not self.records:
            raise ValueError("success requires records")
        if self.status != "success" and self.records:
            raise ValueError("only successful source exposes validated records")
        if self.status == "not_requested":
            if self.filter_coverage != "none":
                raise ValueError("not_requested requires filter_coverage=none")
            if self.raw_references or self.elapsed_seconds is not None or self.source_total is not None or self.truncated is not None:
                raise ValueError("not_requested must not claim observations")
        elif self.elapsed_seconds is None:
            raise ValueError("attempted source requires elapsed time")
        hashes = {ref.sha256 for ref in self.raw_references}
        if any(record.source != self.source or record.raw_sha256 not in hashes for record in self.records):
            raise ValueError("record source/raw reference mismatch")
        return self

class RankedHit(StrictModel):
    canonical_id: Text
    rank: Annotated[int, Field(ge=1)]
    score: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    display: PaperRecord
    source_records: list[PaperRecord]
    source_ranks: dict[Source, Annotated[int, Field(ge=1)]]
    conflicts: dict[str, list[FieldEvidence]]

    @model_validator(mode="after")
    def evidence(self):
        if not self.source_records or self.display not in self.source_records:
            raise ValueError("display must be an evidenced source record")
        if set(self.source_ranks) != {r.source for r in self.source_records}:
            raise ValueError("source ranks mismatch")
        return self

class FusionCounts(StrictModel):
    raw: Count
    valid: Count
    invalid: Count
    excluded_by_year: Count
    eligible: Count
    groups: Count
    duplicate_excess: Count
    returned: Count

    @model_validator(mode="after")
    def identities(self):
        if self.raw != self.valid + self.invalid or self.valid != self.eligible + self.excluded_by_year:
            raise ValueError("raw/valid/filter count identity mismatch")
        if self.eligible != self.groups + self.duplicate_excess or self.returned > self.groups:
            raise ValueError("group/duplicate count identity mismatch")
        return self

class FusionResult(StrictModel):
    hits: list[RankedHit]
    counts: FusionCounts

    @model_validator(mode="after")
    def counts_match(self):
        if len(self.hits) != self.counts.returned or [h.rank for h in self.hits] != list(range(1, len(self.hits)+1)):
            raise ValueError("returned count/ranks mismatch")
        if len({h.canonical_id for h in self.hits}) != len(self.hits):
            raise ValueError("duplicate canonical hits")
        return self

def overall_status(results: list[SourceResult], request: SearchRequest, hit_count: int) -> str:
    if type(hit_count) is not int or hit_count < 0:
        raise ValueError("invalid hit_count")
    if len({r.source for r in results}) != len(results):
        raise ValueError("duplicate source result")
    mapping = {r.source: r for r in results}
    if any(s not in mapping or mapping[s].status == "not_requested" for s in request.sources):
        raise ValueError("missing selected source result")
    if any(r.source not in request.sources and r.status != "not_requested" for r in results):
        raise ValueError("unselected source was attempted")
    failed = sum(mapping[s].status == "failed" for s in request.sources)
    if hit_count and not any(mapping[s].status == "success" for s in request.sources):
        raise ValueError("hits without successful source")
    if failed == len(request.sources):
        return "failed"
    if failed:
        return "partial_failure"
    return "success" if hit_count else "empty"

def error_http_status(errors: list[SearchError]) -> int:
    if not errors:
        return 200
    codes = {"request": 422, "storage": 500, "quota": 503, "timeout": 504,
             "upstream": 502, "schema": 502, "auth": 502, "config": 500, "policy": 502}
    priority = ["request", "storage", "config", "quota", "timeout", "upstream", "schema", "auth", "policy"]
    return next(codes[k] for k in priority if any(e.kind == k for e in errors))

class SearchSnapshot(StrictModel):
    schema_version: Literal[1]
    contract_version: Literal["1.0.0"]
    snapshot_id: Text
    request: SearchRequest
    config_sha256: Hash
    adapter_sha256: dict[Source, Hash]
    source_results: list[SourceResult]
    fusion: FusionResult
    overall: Literal["success", "empty", "partial_failure", "failed"]
    fetched_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def consistent(self):
        aware(self.fetched_at); aware(self.expires_at)
        if self.expires_at <= self.fetched_at:
            raise ValueError("expiry must follow fetch")
        if set(self.adapter_sha256) != set(self.request.sources):
            raise ValueError("adapter hashes missing/extra")
        if self.overall != overall_status(self.source_results, self.request, len(self.fusion.hits)):
            raise ValueError("overall mismatch")
        records = [r for s in self.source_results for r in s.records]
        if self.fusion.counts.valid != len(records) or self.fusion.counts.invalid != 0:
            raise ValueError("snapshot cannot contain invalid or uncounted source records")
        if any(r not in records for h in self.fusion.hits for r in h.source_records):
            raise ValueError("hit not traced to selected source result")
        return self

class SearchEnvelope(StrictModel):
    schema_version: Literal[1]
    contract_version: Literal["1.0.0"]
    overall: Literal["success", "empty", "partial_failure", "failed"]
    snapshot: SearchSnapshot | None
    errors: list[SearchError]
    stale: bool
    cached: bool

    @model_validator(mode="after")
    def consistent(self):
        good = self.overall in {"success", "empty"}
        if good and (self.snapshot is None or self.errors):
            raise ValueError("completed envelope needs snapshot and no errors")
        if not good and not self.errors:
            raise ValueError("failure envelope requires errors")
        if self.snapshot is not None and self.snapshot.overall != self.overall:
            raise ValueError("envelope/snapshot overall mismatch")
        if self.snapshot is not None:
            expected=[s.error for s in self.snapshot.source_results if s.error is not None]
            if [e for e in self.errors if e.source is not None] != expected:
                raise ValueError("envelope errors must match source failures")
        if self.overall == "partial_failure" and self.snapshot is None:
            raise ValueError("partial failure requires evidence snapshot")
        if self.cached and not good:
            raise ValueError("failure is not a cache success")
        return self

class SourcePolicy(StrictModel):
    endpoint: Text
    source_policy_verified: bool
    policy_evidence_sha256: Hash | None
    auth_mode: Literal["anonymous", "bearer"]
    key_env: Text | None
    interval_seconds: Seconds
    timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    max_retries: Annotated[int, Field(ge=0, le=2)]
    backoff_seconds: Seconds
    max_body_bytes: Annotated[int, Field(gt=0)]
    content_types: list[Text]

    @model_validator(mode="after")
    def consistent(self):
        safe_url(self.endpoint)
        if urlsplit(self.endpoint).query or urlsplit(self.endpoint).fragment:
            raise ValueError("endpoint forbids query/fragment")
        if self.source_policy_verified != (self.policy_evidence_sha256 is not None):
            raise ValueError("verified policy needs audit evidence hash")
        if (self.auth_mode == "bearer") != (self.key_env is not None):
            raise ValueError("auth mode/key env mismatch")
        if not self.content_types or len(set(self.content_types)) != len(self.content_types):
            raise ValueError("content types required/unique")
        return self

class PublicSearchConfig(StrictModel):
    schema_version: Literal[1]
    contract_version: Literal["1.0.0"]
    config_version: Text
    data_root: Text
    cache_ttl_seconds: Annotated[int, Field(gt=0)]
    deadline_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    sources: dict[Source, SourcePolicy]

    @model_validator(mode="after")
    def sources_required(self):
        if set(self.sources) != {"openalex", "arxiv"}:
            raise ValueError("config requires both source policies")
        endpoints={"openalex": "https://api.openalex.org/works", "arxiv": "https://export.arxiv.org/api/query"}
        if any(policy.endpoint != endpoints[source] for source,policy in self.sources.items()):
            raise ValueError("source endpoint outside approved MVP allowlist")
        p=Path(self.data_root)
        if p.is_absolute() or ".." in p.parts or p.parts[:2] != ("data", "public_search"):
            raise ValueError("data_root must stay under data/public_search")
        return self

class LibraryEntry(StrictModel):
    canonical_id: Text
    snapshot_id: Text
    saved_at: datetime
    hit: RankedHit
    incomplete_sources: bool

    @model_validator(mode="after")
    def consistent(self):
        aware(self.saved_at)
        if self.canonical_id != self.hit.canonical_id:
            raise ValueError("library identity mismatch")
        return self

class PublicStore(Protocol):
    """Signatures only; EXT-04A implements storage, no runtime imports here."""
    def load_cache(self, cache_key: str, *, now: datetime) -> SearchSnapshot | None: ...
    def save_snapshot(self, snapshot: SearchSnapshot, raw_payloads: dict[str, bytes], *, cache_key: str) -> None: ...
    def read_snapshot(self, snapshot_id: str) -> SearchSnapshot: ...
    def save_paper(self, snapshot_id: str, canonical_id: str, *, now: datetime) -> LibraryEntry: ...
    def list_library(self, *, offset: int, limit: int) -> list[LibraryEntry]: ...
    def export_library(self, format: Literal["json", "bibtex"]) -> bytes: ...
    def close(self) -> None: ...

class PublicAdapter(Protocol):
    def search(self, request: SearchRequest, transport: "Transport") -> SourceResult: ...

# TYPE_CHECKING avoids importing implementations not yet dispatched.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .transport import Transport

def digest(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))

def load_config(path: Path | str) -> PublicSearchConfig:
    return PublicSearchConfig.model_validate(read_json(Path(path)))

def cache_key(request: SearchRequest, config: PublicSearchConfig, adapter_sha256: dict[Source, str]) -> str:
    if set(adapter_sha256) != set(request.sources):
        raise ValueError("cache key requires selected adapter hashes")
    for value in adapter_sha256.values():
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid adapter hash")
    return digest({"schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
                   "request": request.model_dump(mode="json", exclude={"refresh"}),
                   "config_sha256": digest(config), "adapter_sha256": adapter_sha256})

def main() -> int:
    parser=argparse.ArgumentParser(description="Contract boundary validator; not production search CLI")
    parser.add_argument("--config", required=True)
    parser.add_argument("--request", required=True)
    args=parser.parse_args()
    try:
        config=load_config(args.config)
        request=SearchRequest.model_validate(read_json(Path(args.request)))
        print(json.dumps({"status": "VALIDATED", "config_sha256": digest(config), "request": request.model_dump(mode="json")}))
        return 0
    except (OSError, ValueError):
        print("FAIL: invalid or missing config/request", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
