"""Resumable OpenAlex topic pilot downloader.

The raw, projected API responses are the evidence.  Cached pages are immutable
once a completed manifest exists; a resume rebuilds state from those pages
rather than trusting a possibly stale checkpoint.  Authentication is sent only
as a bearer header and is never persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import httpx


OPENALEX_API_URL = "https://api.openalex.org/works"
OPENALEX_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
OPENALEX_API_DOCS_URL = "https://help.openalex.org/api/"
OPENALEX_TOPICS_DOCS_URL = "https://help.openalex.org/data/topics/"
DEFAULT_FIELDS: tuple[str, ...] = (
    "id",
    "doi",
    "title",
    "publication_year",
    "abstract_inverted_index",
    "authorships",
    "primary_location",
    "cited_by_count",
    "referenced_works",
    "primary_topic",
    "topics",
    "updated_date",
    "type",
    "language",
    "is_retracted",
    "is_paratext",
)
_TOPIC_ID_RE = re.compile(r"^T\d+$")
_WORK_ID_RE = re.compile(r"^W\d+$")
_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class OpenAlexError(RuntimeError):
    """Base exception for OpenAlex ingestion failures."""


class OpenAlexAPIError(OpenAlexError):
    """A non-recoverable or exhausted API request failure."""


class SnapshotIntegrityError(OpenAlexError):
    """Cached or completed snapshot evidence does not match its manifest."""


@dataclass(frozen=True)
class OpenAlexPilotConfig:
    """Frozen selection and transport contract for a 1,000--3,000 work pilot."""

    topic_id: str
    topic_name: str
    target_count: int = 2_000
    sample_seed: str = "20260915"
    per_page: int = 100
    corpus: str = "core"
    endpoint: str = OPENALEX_API_URL
    fields: tuple[str, ...] = DEFAULT_FIELDS
    request_interval_seconds: float = 0.1
    timeout_seconds: float = 30.0
    max_retries: int = 5
    backoff_initial_seconds: float = 1.0
    max_backoff_seconds: float = 60.0

    def __post_init__(self) -> None:
        topic_id = self.topic_id.rsplit("/", 1)[-1].strip().upper()
        if not _TOPIC_ID_RE.fullmatch(topic_id):
            raise ValueError("topic_id must be an OpenAlex topic ID such as T10286")
        if not self.topic_name.strip():
            raise ValueError("topic_name must not be blank")
        if not 1_000 <= self.target_count <= 3_000:
            raise ValueError("target_count must be between 1,000 and 3,000 for SG-013")
        if not 1 <= self.per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        if self.corpus not in {"core", "expansion", "all"}:
            raise ValueError("corpus must be one of: core, expansion, all")
        if not self.sample_seed.strip():
            raise ValueError("sample_seed must not be blank")
        if self.request_interval_seconds < 0 or self.timeout_seconds <= 0:
            raise ValueError("request interval must be non-negative and timeout positive")
        if self.max_retries < 0 or self.backoff_initial_seconds < 0:
            raise ValueError("retry values must be non-negative")
        if not self.fields or "id" not in self.fields or "referenced_works" not in self.fields:
            raise ValueError("fields must include id and referenced_works")
        try:
            endpoint = httpx.URL(self.endpoint)
        except (httpx.InvalidURL, ValueError):
            raise ValueError("endpoint must be an absolute HTTP(S) URL without credentials") from None
        if endpoint.scheme not in {"http", "https"} or not endpoint.host:
            raise ValueError("endpoint must be an absolute HTTP(S) URL")
        if endpoint.query or endpoint.username or endpoint.password:
            raise ValueError("endpoint must not contain query parameters or user credentials")
        object.__setattr__(self, "topic_id", topic_id)
        object.__setattr__(self, "topic_name", self.topic_name.strip())
        object.__setattr__(self, "sample_seed", self.sample_seed.strip())
        object.__setattr__(self, "fields", tuple(self.fields))

    @property
    def api_sample_size(self) -> int:
        """Allow one extra page so duplicate/merged IDs do not shrink the snapshot."""

        return min(10_000, self.target_count + self.per_page)

    def selection_contract(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "filter": f"topics.id:{self.topic_id}",
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "target_count": self.target_count,
            "sample_size": self.api_sample_size,
            "sample_seed": self.sample_seed,
            "per_page": self.per_page,
            "corpus": self.corpus,
            "fields": list(self.fields),
            "paging": "basic_page_over_seeded_sample",
        }

    @property
    def fingerprint(self) -> str:
        return _sha256_json(self.selection_contract())


def canonical_openalex_work_id(value: str) -> str:
    """Map any standard OpenAlex work URI/ID to ScholarGraph's namespace."""

    raw = str(value).strip().rstrip("/").rsplit("/", 1)[-1].upper()
    if not _WORK_ID_RE.fullmatch(raw):
        raise ValueError(f"Invalid OpenAlex work ID: {value!r}")
    return f"openalex:{raw}"


class OpenAlexPilotDownloader:
    """Download, cache, resume, finalize, and audit a seeded topic sample."""

    def __init__(
        self,
        config: OpenAlexPilotConfig,
        raw_dir: Path | str,
        manifest_path: Path | str,
        report_path: Path | str,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.raw_dir = Path(raw_dir)
        self.pages_dir = self.raw_dir / "pages"
        self.checkpoint_path = self.raw_dir / "checkpoint.json"
        self.works_path = self.raw_dir / "works.jsonl"
        self.manifest_path = Path(manifest_path)
        self.report_path = Path(report_path)
        self._sleeper = sleeper
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._owns_client = client is None
        headers = {
            "Accept": "application/json",
            "User-Agent": "ScholarGraph-VN/0.1 (academic reproducibility pilot)",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = client or httpx.Client(headers=headers, follow_redirects=True)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "OpenAlexPilotDownloader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def download(self) -> dict[str, Any]:
        """Return the completed manifest, resuming only the matching extraction."""

        if self.manifest_path.exists():
            return self._verify_completed_manifest()

        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        cached = self._load_cached_pages()
        unique = _deduplicate_results(cached)
        page_number = len(cached) + 1

        while len(unique) < self.config.target_count:
            if page_number > math.ceil(self.config.api_sample_size / self.config.per_page):
                raise OpenAlexAPIError(
                    f"Seeded sample ended with {len(unique)} unique works; "
                    f"target is {self.config.target_count}. Cached evidence was preserved."
                )
            if page_number > 1 and self.config.request_interval_seconds:
                self._sleeper(self.config.request_interval_seconds)
            page = self._fetch_page(page_number)
            self._write_page(page_number, page)
            cached.append(page)
            unique = _deduplicate_results(cached)
            self._write_checkpoint(cached, unique)
            if not page["payload"].get("results"):
                raise OpenAlexAPIError(
                    f"OpenAlex returned an empty page with {len(unique)} unique works; "
                    f"target is {self.config.target_count}. Cached evidence was preserved."
                )
            page_number += 1

        selected = unique[: self.config.target_count]
        return self._finalize(cached, selected)

    def _request_params(self, page_number: int) -> dict[str, str | int]:
        return {
            "filter": f"topics.id:{self.config.topic_id}",
            "sample": self.config.api_sample_size,
            "seed": self.config.sample_seed,
            "per_page": self.config.per_page,
            "page": page_number,
            "corpus": self.config.corpus,
            "select": ",".join(self.config.fields),
        }

    def _fetch_page(self, page_number: int) -> dict[str, Any]:
        params = self._request_params(page_number)
        last_error = "unknown transient failure"
        started = time.perf_counter()

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.get(
                    self.config.endpoint,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )
                if response.status_code == 200:
                    payload = response.json()
                    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                        raise OpenAlexAPIError("OpenAlex response lacks a list-valued 'results' field")
                    return {
                        "schema_version": 1,
                        "query_fingerprint": self.config.fingerprint,
                        "page_number": page_number,
                        "requested_at": _iso(self._clock()),
                        "request": {"method": "GET", "params": params},
                        "rate_limit": _safe_rate_headers(response.headers),
                        "retry_count": attempt,
                        "request_elapsed_seconds": round(time.perf_counter() - started, 6),
                        "payload_sha256": _sha256_json(payload),
                        "payload": payload,
                    }
                if response.status_code not in _TRANSIENT_STATUS_CODES:
                    message = _safe_error_message(response)
                    raise OpenAlexAPIError(
                        f"OpenAlex page {page_number} failed with HTTP {response.status_code}: {message}"
                    )
                last_error = f"HTTP {response.status_code}"
                retry_after = _parse_retry_after(
                    response.headers.get("Retry-After"), now=self._clock()
                )
                quota_reset = _quota_reset_delay(response.headers)
            except OpenAlexAPIError:
                raise
            except (httpx.RequestError, json.JSONDecodeError, ValueError) as exc:
                last_error = type(exc).__name__
                retry_after = 0.0
                quota_reset = 0.0

            if attempt >= self.config.max_retries:
                break
            exponential_delay = min(
                self.config.max_backoff_seconds,
                self.config.backoff_initial_seconds * (2**attempt),
            )
            # A server-specified Retry-After (or exhausted daily quota reset)
            # is a lower bound.  max_backoff_seconds caps only our own policy;
            # silently shortening the server's delay causes premature retries.
            delay = max(exponential_delay, retry_after, quota_reset)
            self._sleeper(delay)

        raise OpenAlexAPIError(
            f"OpenAlex page {page_number} exhausted {self.config.max_retries} retries "
            f"after {last_error}; cached evidence was preserved."
        )

    def _write_page(self, page_number: int, page: Mapping[str, Any]) -> None:
        path = self.pages_dir / f"page-{page_number:05d}.json"
        if path.exists():
            raise SnapshotIntegrityError(f"Refusing to overwrite cached page: {path}")
        _atomic_write_json(path, page)

    def _load_cached_pages(self) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for expected, path in enumerate(sorted(self.pages_dir.glob("page-*.json")), start=1):
            page = _read_json(path)
            if page.get("page_number") != expected:
                raise SnapshotIntegrityError(f"Non-contiguous cached page sequence at {path}")
            if page.get("query_fingerprint") != self.config.fingerprint:
                raise SnapshotIntegrityError(f"Cached page belongs to another query: {path}")
            payload = page.get("payload")
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise SnapshotIntegrityError(f"Malformed cached payload: {path}")
            if page.get("payload_sha256") != _sha256_json(payload):
                raise SnapshotIntegrityError(f"Cached page checksum mismatch: {path}")
            pages.append(page)
        return pages

    def _write_checkpoint(
        self, pages: Sequence[Mapping[str, Any]], unique: Sequence[Mapping[str, Any]]
    ) -> None:
        returned = sum(len(page["payload"]["results"]) for page in pages)
        checkpoint = {
            "schema_version": 1,
            "status": "IN_PROGRESS",
            "query_fingerprint": self.config.fingerprint,
            "selection": self.config.selection_contract(),
            "pages_cached": len(pages),
            "api_records_returned": returned,
            "unique_records_seen": len(unique),
            "duplicates_dropped": returned - len(unique),
            "next_page": len(pages) + 1,
            "updated_at": _iso(self._clock()),
        }
        _atomic_write_json(self.checkpoint_path, checkpoint)

    def _finalize(
        self,
        pages: Sequence[Mapping[str, Any]],
        works: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        completed_at = self._clock()
        _atomic_write_jsonl(self.works_path, works)
        report = _build_report(self.config, pages, works, completed_at)
        _atomic_write_json(self.report_path, report)

        page_artifacts = [
            {
                "path": _display_path(self.pages_dir / f"page-{index:05d}.json"),
                "sha256": _sha256_file(self.pages_dir / f"page-{index:05d}.json"),
            }
            for index in range(1, len(pages) + 1)
        ]
        manifest = {
            "schema_version": 1,
            "task_id": "SG-013",
            "dataset": "OpenAlex",
            "status": "COMPLETED",
            "snapshot_id": (
                f"openalex-api-{self.config.topic_id.lower()}-"
                f"seed{self.config.sample_seed}-{self.config.fingerprint[:12]}"
            ),
            "snapshot_kind": "immutable_local_extraction_from_live_api",
            "source": {
                "provider": "OpenAlex",
                "endpoint": self.config.endpoint,
                "api_documentation": OPENALEX_API_DOCS_URL,
                "topic_documentation": OPENALEX_TOPICS_DOCS_URL,
                "license": "CC0",
                "license_url": OPENALEX_LICENSE_URL,
                "authentication": "anonymous_or_bearer_header; credential_not_persisted",
            },
            "selection": self.config.selection_contract(),
            "query_fingerprint": self.config.fingerprint,
            "id_namespace": {
                "raw": "OpenAlex URI, e.g. https://openalex.org/W123",
                "canonical_mapping": "strip URI prefix and prepend openalex:, e.g. openalex:W123",
            },
            "retrieved_started_at": min(page["requested_at"] for page in pages),
            "retrieved_completed_at": _iso(completed_at),
            "counts": {
                "selected_unique_works": len(works),
                "api_records_returned": sum(len(page["payload"]["results"]) for page in pages),
                "duplicates_dropped_before_selection": (
                    sum(len(page["payload"]["results"]) for page in pages)
                    - len(_deduplicate_results(pages))
                ),
                "pages": len(pages),
                "retries": sum(int(page.get("retry_count", 0)) for page in pages),
            },
            "artifacts": {
                "works_jsonl": {
                    "path": _display_path(self.works_path),
                    "sha256": _sha256_file(self.works_path),
                    "bytes": self.works_path.stat().st_size,
                },
                "coverage_report": {
                    "path": _display_path(self.report_path),
                    "sha256": _sha256_file(self.report_path),
                },
                "raw_pages": page_artifacts,
            },
            "immutability": {
                "completed_manifest_prevents_overwrite": True,
                "resume_source_of_truth": "verified raw page cache",
            },
        }
        _atomic_write_json(self.manifest_path, manifest)
        self._write_checkpoint(pages, _deduplicate_results(pages))
        checkpoint = _read_json(self.checkpoint_path)
        checkpoint["status"] = "COMPLETED"
        checkpoint["manifest_path"] = _display_path(self.manifest_path)
        checkpoint["updated_at"] = _iso(completed_at)
        _atomic_write_json(self.checkpoint_path, checkpoint)
        return manifest

    def _verify_completed_manifest(self) -> dict[str, Any]:
        manifest = _read_json(self.manifest_path)
        if manifest.get("status") != "COMPLETED":
            raise SnapshotIntegrityError("Existing manifest is not COMPLETED")
        if manifest.get("query_fingerprint") != self.config.fingerprint:
            raise SnapshotIntegrityError("Completed manifest belongs to another selection contract")
        artifacts = manifest.get("artifacts", {})
        expected = (
            (self.works_path, artifacts.get("works_jsonl", {}).get("sha256")),
            (self.report_path, artifacts.get("coverage_report", {}).get("sha256")),
        )
        for path, digest in expected:
            if not path.exists() or not digest or _sha256_file(path) != digest:
                raise SnapshotIntegrityError(f"Completed snapshot artifact mismatch: {path}")
        raw_pages = artifacts.get("raw_pages")
        cached_paths = sorted(self.pages_dir.glob("page-*.json"))
        if not isinstance(raw_pages, list) or len(raw_pages) != len(cached_paths):
            raise SnapshotIntegrityError("Completed snapshot raw-page inventory mismatch")
        for path, page_artifact in zip(cached_paths, raw_pages):
            if not isinstance(page_artifact, dict):
                raise SnapshotIntegrityError("Malformed raw-page entry in completed manifest")
            digest = page_artifact.get("sha256")
            if not digest or _sha256_file(path) != digest:
                raise SnapshotIntegrityError(f"Completed snapshot raw-page mismatch: {path}")
        self._load_cached_pages()
        return manifest


def _build_report(
    config: OpenAlexPilotConfig,
    pages: Sequence[Mapping[str, Any]],
    works: Sequence[Mapping[str, Any]],
    completed_at: datetime,
) -> dict[str, Any]:
    ids = {str(work.get("id", "")).strip() for work in works if work.get("id")}
    valid_years = {
        str(work.get("id")): int(work["publication_year"])
        for work in works
        if work.get("id") and _valid_year(work.get("publication_year"))
    }
    internal_edges: set[tuple[str, str]] = set()
    referenced_total = 0
    eligible_sources_by_year: dict[str, int] = {}
    nodes_with_edges: set[str] = set()

    for work in works:
        source = str(work.get("id", "")).strip()
        refs = work.get("referenced_works") or []
        if not isinstance(refs, list):
            refs = []
        referenced_total += len(refs)
        source_year = valid_years.get(source)
        eligible_internal_refs: set[str] = set()
        for target_value in refs:
            target = str(target_value).strip()
            if source and target in ids and target != source:
                internal_edges.add((source, target))
                nodes_with_edges.update((source, target))
                target_year = valid_years.get(target)
                if source_year is not None and target_year is not None and target_year <= source_year:
                    eligible_internal_refs.add(target)
        if (
            source_year is not None
            and _has_text(work.get("title"))
            and bool(work.get("abstract_inverted_index"))
            and len(eligible_internal_refs) >= 2
        ):
            key = str(source_year)
            eligible_sources_by_year[key] = eligible_sources_by_year.get(key, 0) + 1

    n = len(works)
    internal_reference_occurrences = sum(
        1
        for work in works
        for target in (work.get("referenced_works") or [])
        if str(target).strip() in ids and str(target).strip() != str(work.get("id", "")).strip()
    )
    api_cost = sum(float(page["payload"].get("meta", {}).get("cost_usd") or 0.0) for page in pages)
    active_request_seconds = sum(float(page.get("request_elapsed_seconds") or 0.0) for page in pages)
    page_count = len(pages)
    bytes_per_work = 0.0
    if n:
        bytes_per_work = sum(
            len((_stable_json(work) + "\n").encode("utf-8")) for work in works
        ) / n

    def coverage(predicate: Callable[[Mapping[str, Any]], bool]) -> dict[str, Any]:
        count = sum(1 for work in works if predicate(work))
        return {"count": count, "fraction": round(count / n, 6) if n else None}

    projections: dict[str, Any] = {}
    mean_cost_per_page = api_cost / page_count if page_count else None
    mean_seconds_per_page = active_request_seconds / page_count if page_count else None
    for target in (10_000, 20_000):
        pages_needed = math.ceil(target / config.per_page)
        projections[str(target)] = {
            "pages_at_same_per_page": pages_needed,
            "estimated_api_cost_usd": (
                round(pages_needed * mean_cost_per_page, 6) if mean_cost_per_page is not None else None
            ),
            "estimated_active_request_seconds": (
                round(pages_needed * mean_seconds_per_page, 3)
                if mean_seconds_per_page is not None
                else None
            ),
            "estimated_raw_jsonl_bytes": round(target * bytes_per_work),
        }

    return {
        "schema_version": 1,
        "task_id": "SG-013",
        "status": "MEASURED",
        "measured_at": _iso(completed_at),
        "query_fingerprint": config.fingerprint,
        "selection": config.selection_contract(),
        "counts": {
            "works": n,
            "unique_openalex_ids": len(ids),
            "pages": page_count,
            "api_records_returned": sum(len(page["payload"]["results"]) for page in pages),
            "retries": sum(int(page.get("retry_count", 0)) for page in pages),
            "references_to_openalex_works": referenced_total,
            "internal_reference_occurrences": internal_reference_occurrences,
            "unique_internal_directed_edges": len(internal_edges),
            "isolated_nodes_in_induced_snapshot": n - len(nodes_with_edges),
        },
        "coverage": {
            "title": coverage(lambda work: _has_text(work.get("title"))),
            "abstract_inverted_index": coverage(lambda work: bool(work.get("abstract_inverted_index"))),
            "valid_publication_year_1900_2100": coverage(
                lambda work: _valid_year(work.get("publication_year"))
            ),
            "doi": coverage(lambda work: _has_text(work.get("doi"))),
            "authorship": coverage(lambda work: bool(work.get("authorships"))),
            "primary_location": coverage(_has_primary_location),
            "venue": coverage(_has_venue_name),
            "has_any_reference": coverage(lambda work: bool(work.get("referenced_works"))),
            "internal_reference_occurrence_fraction": (
                round(internal_reference_occurrences / referenced_total, 6)
                if referenced_total
                else None
            ),
        },
        "protocol_b_feasibility_inputs": {
            "eligible_source_count_by_publication_year": dict(
                sorted(eligible_sources_by_year.items(), key=lambda item: int(item[0]))
            ),
            "eligible_definition": (
                "valid year; non-empty title and abstract; at least two distinct internal references "
                "with target year <= source year"
            ),
            "cohort_selection_deferred_to": "SG-014",
        },
        "acquisition": {
            "api_cost_usd_reported_by_meta": round(api_cost, 6),
            "active_request_seconds": round(active_request_seconds, 3),
            "mean_api_page_cost_usd": round(api_cost / page_count, 8) if page_count else None,
            "mean_active_request_seconds_per_page": (
                round(active_request_seconds / page_count, 6) if page_count else None
            ),
            "last_rate_limit_headers": pages[-1].get("rate_limit", {}) if pages else {},
            "projections_are_linear_estimates_not_commitments": projections,
        },
        "known_limitations": [
            "This is a frozen local extraction from the continuously updated live API, not an official bulk snapshot release.",
            "The seeded random sample is reproducible only against an unchanged upstream database; local page hashes define this snapshot.",
            "topics.id selection uses any assigned OpenAlex topic; topic assignments are model-inferred and can introduce selection bias.",
            "OpenAlex referenced_works contains only references OpenAlex successfully matched to another work.",
            "Internal-edge coverage is conditional on this topic sample and does not estimate all out-of-snapshot references as missing metadata.",
            "Linear 10K/20K cost, time, and size projections exclude rate-limit waits and changes in record size or API pricing.",
        ],
    }


def _deduplicate_results(pages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for page in pages:
        for work in page["payload"]["results"]:
            if not isinstance(work, dict):
                raise SnapshotIntegrityError("OpenAlex results must be JSON objects")
            raw_id = str(work.get("id", "")).strip()
            try:
                canonical = canonical_openalex_work_id(raw_id)
            except ValueError as exc:
                raise SnapshotIntegrityError(str(exc)) from exc
            if canonical not in seen:
                seen.add(canonical)
                unique.append(work)
    return unique


def _valid_year(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1900 <= value <= 2100


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_primary_location(work: Mapping[str, Any]) -> bool:
    return isinstance(work.get("primary_location"), dict) and bool(work["primary_location"])


def _has_venue_name(work: Mapping[str, Any]) -> bool:
    """Whether primary location has an actual source name, not merely a URL."""

    location = work.get("primary_location")
    if not isinstance(location, dict):
        return False
    source = location.get("source")
    if isinstance(source, dict) and _has_text(source.get("display_name")):
        return True
    return _has_text(location.get("raw_source_name"))


def _safe_rate_headers(headers: Mapping[str, str]) -> dict[str, str]:
    safe_names = (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-credits-used",
        "x-ratelimit-reset",
    )
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    return {name: lowered[name] for name in safe_names if name in lowered}


def _safe_error_message(response: httpx.Response) -> str:
    """Return a diagnostic that never includes untrusted upstream error text.

    Error bodies can reflect Authorization headers, query tokens, or nested
    values.  Keeping only the response shape makes traceback/log output safe by
    construction while the HTTP status remains available to the caller.
    """

    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return "non-JSON response"
    if isinstance(payload, (dict, list)):
        return "upstream JSON error details omitted"
    return "upstream error details omitted"


def _parse_retry_after(value: str | None, *, now: datetime | None = None) -> float:
    """Parse RFC 9110 Retry-After delay-seconds or HTTP-date."""

    if value is None:
        return 0.0
    stripped = value.strip()
    if stripped.isdigit():
        return float(stripped)
    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - reference).total_seconds())


def _quota_reset_delay(headers: Mapping[str, str]) -> float:
    """Use OpenAlex's seconds-to-reset only when the daily budget is exhausted."""

    lowered = {str(key).lower(): str(value).strip() for key, value in headers.items()}
    try:
        remaining = float(lowered.get("x-ratelimit-remaining", "nan"))
    except ValueError:
        return 0.0
    if remaining > 0:
        return 0.0
    reset = lowered.get("x-ratelimit-reset")
    if reset is None:
        return 0.0
    try:
        return max(0.0, float(reset))
    except ValueError:
        return 0.0


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise SnapshotIntegrityError(f"Expected JSON object in {path}")
    return value


def _atomic_write_json(path: Path, value: Any) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_bytes(path, content.encode("utf-8"))


def _atomic_write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    content = "".join(_stable_json(value) + "\n" for value in values)
    _atomic_write_bytes(path, content.encode("utf-8"))


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download the resumable SG-013 OpenAlex pilot")
    parser.add_argument("--topic-id", default="T10286")
    parser.add_argument("--topic-name", default="Information Retrieval and Search Behavior")
    parser.add_argument("--target-count", type=int, default=2_000)
    parser.add_argument("--sample-seed", default="20260915")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/openalex"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/openalex_pilot.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("artifacts/reports/openalex_pilot.json")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = OpenAlexPilotConfig(
        topic_id=args.topic_id,
        topic_name=args.topic_name,
        target_count=args.target_count,
        sample_seed=args.sample_seed,
    )
    with OpenAlexPilotDownloader(
        config,
        args.raw_dir,
        args.manifest,
        args.report,
        api_key=os.environ.get("OPENALEX_API_KEY"),
    ) as downloader:
        manifest = downloader.download()
    print(
        f"Completed {manifest['snapshot_id']}: "
        f"{manifest['counts']['selected_unique_works']} unique works"
    )
    return 0


# ---------------------------------------------------------------------------
# SG-015 core snapshot: citation-connected acquisition and normalization.
#
# Strategy (pinned in data/manifests/openalex_core.json BEFORE any fetch, per
# ADR-016 §7): the sparse seeded topic pilot (2,000 works, 190 internal edges,
# 88.95% isolated -> NO_GO) is replaced by a citation-connected snapshot built
# from three pinned components:
#
#   1. PILOT SEEDS — the 2,000 works of the immutable pilot snapshot are
#      embedded verbatim (no re-fetch, hash pinned).
#   2. HUBS — the most referenced external targets of the pilot works (ranked
#      deterministically by distinct pilot sources, tie-break canonical ID)
#      are fetched by ID.  Dead IDs are tolerated and counted.  Active hubs
#      (valid year <= active_hub_max_year, not retracted, not paratext) form
#      the recruitment filter.
#   3. YEAR COHORTS — for each pinned year, a seeded reproducible OpenAlex
#      sample of works that cite at least one active hub.  Every cohort work
#      citing >= 2 snapshot works with year <= its own becomes an eligible
#      Protocol v1 track-B source; the gate CLI decides, floors stay 50/30/2/100.
#
# Failure contract mirrors the pilot (ADR-013/014): fatal problems raise, CLI
# exits 1, nothing measured is replaced by 0 or silently dropped.
# ---------------------------------------------------------------------------

CORE_SCHEMA_VERSION = 1
CORE_TASK_ID = "SG-015"
CORE_DEFAULT_MAILTO = "scholargraph-vn@example.org"
CORE_USER_AGENT = "ScholarGraph-VN/0.1 (academic reproducibility; SG-015 core snapshot)"
_CORE_OR_FILTER_LIMIT = 100  # verified against the live API for cites/openalex_id


def _bare_work_id(value: Any) -> str:
    """Return the bare ``W<digits>`` form of any OpenAlex work ID."""

    raw = str(value).strip().rstrip("/").rsplit("/", 1)[-1].upper()
    if not _WORK_ID_RE.fullmatch(raw):
        raise ValueError(f"Invalid OpenAlex work ID: {value!r}")
    return raw


_CORE_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "dx.doi.org/",
)


def normalize_core_doi(value: Any) -> str | None:
    """Lower-case bare DOI with URL prefix stripped; ``None`` when absent.

    Mirrors the SG-014 gate semantics so the processed snapshot and the gate
    agree on DOI identity.  Non-string non-null values are fatal.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise SnapshotIntegrityError(
            f"DOI must be a string or null, got {type(value).__name__}"
        )
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    for prefix in _CORE_DOI_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix) :].rstrip("/")
    return lowered.rstrip("/")


@dataclass(frozen=True)
class HubCandidate:
    """One pinned hub candidate derived from the immutable pilot snapshot."""

    openalex_id: str
    distinct_pilot_sources: int


def rank_hub_candidates(
    pilot_records: Sequence[Mapping[str, Any]], candidate_count: int
) -> list[HubCandidate]:
    """Rank external (non-pilot) reference targets of the pilot works.

    Rank key: distinct pilot source count descending, then bare OpenAlex ID
    ascending (deterministic tie-break).  Derived only from the pinned pilot
    snapshot so the plan can be written before any API call.
    """

    if candidate_count < 1:
        raise ValueError("candidate_count must be at least 1")
    pilot_ids: set[str] = set()
    for record in pilot_records:
        try:
            pilot_ids.add(_bare_work_id(record["id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotIntegrityError(
                f"Pilot record lacks a valid 'id' field: {exc}"
            ) from exc
    distinct_sources: dict[str, set[str]] = {}
    for record in pilot_records:
        source = _bare_work_id(record["id"])
        refs = record.get("referenced_works") if "referenced_works" in record else None
        if refs is None:
            continue
        if not isinstance(refs, list):
            raise SnapshotIntegrityError("Pilot 'referenced_works' must be a list")
        for target in refs:
            try:
                bare = _bare_work_id(target)
            except ValueError as exc:
                raise SnapshotIntegrityError(str(exc)) from exc
            if bare in pilot_ids:
                continue
            distinct_sources.setdefault(bare, set()).add(source)
    ranked = sorted(
        distinct_sources.items(), key=lambda item: (-len(item[1]), item[0])
    )[:candidate_count]
    return [
        HubCandidate(openalex_id=wild, distinct_pilot_sources=len(sources))
        for wild, sources in ranked
    ]


@dataclass(frozen=True)
class OpenAlexCoreConfig:
    """Frozen sampling and transport contract for the SG-015 core snapshot."""

    pilot_works_path: Path
    endpoint: str = OPENALEX_API_URL
    mailto: str = CORE_DEFAULT_MAILTO
    fields: tuple[str, ...] = DEFAULT_FIELDS
    per_page: int = 200
    sample_seed: str = "20260915"
    candidate_hub_count: int = 120
    hub_id_batch_size: int = 100
    active_hub_max_year: int = 2019
    active_hub_cap: int = 100
    cohort_years: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024, 2025)
    cohort_year_order: tuple[int, ...] = (2024, 2023, 2025, 2022, 2021, 2020)
    per_year_sample_cap: int = 2500
    global_work_cap: int = 20000
    minimum_snapshot_works: int = 10000
    request_interval_seconds: float = 0.15
    timeout_seconds: float = 30.0
    max_retries: int = 5
    backoff_initial_seconds: float = 1.0
    max_backoff_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not isinstance(self.pilot_works_path, Path):
            object.__setattr__(self, "pilot_works_path", Path(self.pilot_works_path))
        if self.per_page < 1 or self.per_page > 200:
            raise ValueError("per_page must be between 1 and 200")
        if not self.sample_seed.strip():
            raise ValueError("sample_seed must not be blank")
        if not self.mailto or "@" not in self.mailto:
            raise ValueError("mailto must be a non-empty email address for the polite pool")
        if self.candidate_hub_count < 1:
            raise ValueError("candidate_hub_count must be at least 1")
        if not 1 <= self.hub_id_batch_size <= _CORE_OR_FILTER_LIMIT:
            raise ValueError(
                f"hub_id_batch_size must be between 1 and {_CORE_OR_FILTER_LIMIT}"
            )
        if not 1900 <= self.active_hub_max_year <= 2100:
            raise ValueError("active_hub_max_year must be within 1900-2100")
        if self.active_hub_cap < 1:
            raise ValueError("active_hub_cap must be at least 1")
        if not self.cohort_years or len(set(self.cohort_years)) != len(self.cohort_years):
            raise ValueError("cohort_years must be a non-empty list of distinct years")
        for year in self.cohort_years:
            if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
                raise ValueError("cohort_years entries must be integers within 1900-2100")
        if sorted(self.cohort_year_order) != sorted(self.cohort_years):
            raise ValueError(
                "cohort_year_order must be a permutation of cohort_years "
                "(it pins the fetch and duplicate priority order)"
            )
        if self.per_year_sample_cap < 1 or self.per_year_sample_cap > 10_000:
            raise ValueError("per_year_sample_cap must be between 1 and 10000")
        if self.global_work_cap < 1:
            raise ValueError("global_work_cap must be at least 1")
        if self.minimum_snapshot_works < 1:
            raise ValueError("minimum_snapshot_works must be at least 1")
        if self.minimum_snapshot_works > self.global_work_cap:
            raise ValueError("minimum_snapshot_works must not exceed global_work_cap")
        if self.request_interval_seconds < 0 or self.timeout_seconds <= 0:
            raise ValueError("request interval must be non-negative and timeout positive")
        if self.max_retries < 0 or self.backoff_initial_seconds < 0:
            raise ValueError("retry values must be non-negative")
        if not self.fields or "id" not in self.fields or "referenced_works" not in self.fields:
            raise ValueError("fields must include id and referenced_works")
        try:
            endpoint = httpx.URL(self.endpoint)
        except (httpx.InvalidURL, ValueError):
            raise ValueError("endpoint must be an absolute HTTP(S) URL without credentials") from None
        if endpoint.scheme not in {"http", "https"} or not endpoint.host:
            raise ValueError("endpoint must be an absolute HTTP(S) URL")
        if endpoint.query or endpoint.username or endpoint.password:
            raise ValueError("endpoint must not contain query parameters or user credentials")
        object.__setattr__(self, "sample_seed", self.sample_seed.strip())
        object.__setattr__(self, "fields", tuple(self.fields))

    # -- pinned plan -------------------------------------------------------

    def plan(self, pilot_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """The pinned sampling plan (written to the manifest before fetching)."""

        candidates = rank_hub_candidates(pilot_records, self.candidate_hub_count)
        hub_batches = [
            [candidate.openalex_id for candidate in candidates[start : start + self.hub_id_batch_size]]
            for start in range(0, len(candidates), self.hub_id_batch_size)
        ]
        return {
            "strategy": "citation_connected_snowball_from_pinned_pilot_hubs_and_year_cohorts",
            "rationale": (
                "ADR-016 §7: the seeded topic pilot was citation-sparse (190 internal "
                "edges, 88.95% isolated).  Hubs are the pilot's most referenced "
                "external targets; per-year seeded samples of works citing the hubs "
                "recruit citing sources whose internal references (hubs, pilot works, "
                "other cohort works) supply >= 2 distinct internal references with "
                "target year <= source year.  Every Protocol v1 floor stays unchanged."
            ),
            "pilot_embedding": {
                "pilot_works_path": _display_path(self.pilot_works_path),
                "mode": "verbatim_no_refetch",
            },
            "hub_selection": {
                "source": "external referenced_works targets of the pinned pilot snapshot",
                "rank_rule": "distinct_pilot_sources desc, then openalex_id asc",
                "candidate_count": self.candidate_hub_count,
                "hub_candidates": [
                    {
                        "openalex_id": candidate.openalex_id,
                        "distinct_pilot_sources": candidate.distinct_pilot_sources,
                    }
                    for candidate in candidates
                ],
                "hub_id_batch_size": self.hub_id_batch_size,
                "hub_batches": hub_batches,
                "dead_id_policy": "unresolvable IDs are counted and reported, never fatal",
                "active_rule": (
                    "fetched successfully; valid publication_year 1900-2100 and "
                    f"<= {self.active_hub_max_year}; is_retracted is not true; "
                    "is_paratext is not true; ranked order; capped at "
                    f"{self.active_hub_cap}"
                ),
                "active_hub_cap": self.active_hub_cap,
                "empty_active_hub_policy": "fatal (recruitment filter cannot be empty)",
            },
            "cohort_selection": {
                "filter_template": (
                    "cites:<active_hubs>,publication_year:<Y>,is_paratext:false"
                ),
                "years": list(self.cohort_years),
                "year_order": list(self.cohort_year_order),
                "year_order_rationale": (
                    "most recent years first: highest probability of >= 50 eligible "
                    "sources per single year (test floor), then earlier years for the "
                    "dev floor; duplicate priority follows this order"
                ),
                "per_year_sample_cap": self.per_year_sample_cap,
                "sample_seed": self.sample_seed,
                "paging": "basic_page_over_seeded_sample (verified deterministic)",
                "per_page": self.per_page,
                "global_work_cap": self.global_work_cap,
                "minimum_snapshot_works": self.minimum_snapshot_works,
                "stop_rule": (
                    "a year ends when its sample pages are exhausted or an "
                    "out-of-sample empty page appears (counted); the whole fetch "
                    "stops before exceeding global_work_cap; below "
                    "minimum_snapshot_works the fetch fails loudly"
                ),
                "empty_first_page_policy": "fatal for a cohort year (unexpectedly empty)",
            },
            "dedup_priority": ["pilot", "hubs", "cohorts (year_order, page asc)"],
            "output_order": "snapshot records sorted by canonical ID ascending",
            "fields": list(self.fields),
            "transport": {
                "endpoint": self.endpoint,
                "mailto": self.mailto,
                "polite_pool": True,
                "request_interval_seconds": self.request_interval_seconds,
                "timeout_seconds": self.timeout_seconds,
                "max_retries": self.max_retries,
                "backoff_initial_seconds": self.backoff_initial_seconds,
                "max_backoff_seconds": self.max_backoff_seconds,
                "or_filter_limit_verified": _CORE_OR_FILTER_LIMIT,
            },
            "invariants": {
                "floors": {
                    "minimum_test_queries": 50,
                    "minimum_dev_queries": 30,
                    "minimum_eligible_references": 2,
                    "minimum_novel_candidates_per_query": 100,
                },
                "floors_source": "configs/protocol_v1.json tracks.B.graph_gate (ADR-016: unchanged)",
                "qrels_used": False,
                "beir_data_used_for_sampling": False,
                "pilot_snapshot_immutable": True,
            },
        }


class OpenAlexCoreDownloader:
    """Resumable, checkpointed fetcher for the pinned SG-015 core plan."""

    def __init__(
        self,
        config: OpenAlexCoreConfig,
        raw_dir: Path | str,
        manifest_path: Path | str,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.raw_dir = Path(raw_dir)
        self.pages_dir = self.raw_dir / "pages"
        self.checkpoint_path = self.raw_dir / "checkpoint.json"
        self.works_path = self.raw_dir / "works.jsonl"
        self.manifest_path = Path(manifest_path)
        self._sleeper = sleeper
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._owns_client = client is None
        headers = {"Accept": "application/json", "User-Agent": CORE_USER_AGENT}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = client or httpx.Client(headers=headers, follow_redirects=True)
        self._plan_fingerprint: str | None = None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "OpenAlexCoreDownloader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- pilot and plan ----------------------------------------------------

    def _load_pilot_records(self) -> list[dict[str, Any]]:
        path = self.config.pilot_works_path
        if not path.is_file():
            raise SnapshotIntegrityError(f"Pilot works file is missing: {path}")
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise SnapshotIntegrityError(
                        f"{path}:{line_number}: invalid JSON line ({exc.msg})"
                    ) from None
        if not records:
            raise SnapshotIntegrityError(f"Pilot works file is empty: {path}")
        return records

    def _fingerprint(self, plan: Mapping[str, Any]) -> str:
        return _sha256_json(plan)

    # -- page cache --------------------------------------------------------

    def _write_page(self, page_number: int, envelope: Mapping[str, Any]) -> None:
        path = self.pages_dir / f"page-{page_number:05d}.json"
        if path.exists():
            raise SnapshotIntegrityError(f"Refusing to overwrite cached page: {path}")
        _atomic_write_json(path, envelope)

    def _load_cached_pages(self, fingerprint: str) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for expected, path in enumerate(sorted(self.pages_dir.glob("page-*.json")), start=1):
            page = _read_json(path)
            if page.get("page_number") != expected:
                raise SnapshotIntegrityError(f"Non-contiguous cached page sequence at {path}")
            if page.get("query_fingerprint") != fingerprint:
                raise SnapshotIntegrityError(f"Cached page belongs to another plan: {path}")
            payload = page.get("payload")
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise SnapshotIntegrityError(f"Malformed cached payload: {path}")
            if page.get("payload_sha256") != _sha256_json(payload):
                raise SnapshotIntegrityError(f"Cached page checksum mismatch: {path}")
            pages.append(page)
        return pages

    def _write_checkpoint(self, state: Mapping[str, Any]) -> None:
        checkpoint = dict(state)
        checkpoint.update(
            {
                "schema_version": CORE_SCHEMA_VERSION,
                "task_id": CORE_TASK_ID,
                "query_fingerprint": self._plan_fingerprint,
                "updated_at": _iso(self._clock()),
            }
        )
        _atomic_write_json(self.checkpoint_path, checkpoint)

    # -- transport ---------------------------------------------------------

    def _request_works(self, params: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """GET one page of works with retry/backoff; returns (payload, meta)."""

        request_params = {key: str(value) for key, value in params.items()}
        last_error = "unknown transient failure"
        started = time.perf_counter()
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.get(
                    self.config.endpoint,
                    params=request_params,
                    timeout=self.config.timeout_seconds,
                )
                if response.status_code == 200:
                    payload = response.json()
                    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                        raise OpenAlexAPIError(
                            "OpenAlex response lacks a list-valued 'results' field"
                        )
                    meta = {
                        "retry_count": attempt,
                        "request_elapsed_seconds": round(time.perf_counter() - started, 6),
                        "rate_limit": _safe_rate_headers(response.headers),
                    }
                    return payload, meta
                if response.status_code not in _TRANSIENT_STATUS_CODES:
                    message = _safe_error_message(response)
                    raise OpenAlexAPIError(
                        f"OpenAlex request failed with HTTP {response.status_code}: {message}"
                    )
                last_error = f"HTTP {response.status_code}"
                retry_after = _parse_retry_after(
                    response.headers.get("Retry-After"), now=self._clock()
                )
                quota_reset = _quota_reset_delay(response.headers)
            except OpenAlexAPIError:
                raise
            except (httpx.RequestError, json.JSONDecodeError, ValueError) as exc:
                last_error = type(exc).__name__
                retry_after = 0.0
                quota_reset = 0.0
            if attempt >= self.config.max_retries:
                break
            exponential_delay = min(
                self.config.max_backoff_seconds,
                self.config.backoff_initial_seconds * (2**attempt),
            )
            # A server-specified Retry-After (or exhausted daily quota reset)
            # is a lower bound; our own backoff policy must not shorten it.
            delay = max(exponential_delay, retry_after, quota_reset)
            self._sleeper(delay)
        raise OpenAlexAPIError(
            f"OpenAlex request exhausted {self.config.max_retries} retries "
            f"after {last_error}; cached evidence was preserved."
        )

    # -- fetch -------------------------------------------------------------

    def fetch(self) -> dict[str, Any]:
        """Execute (or resume) the pinned plan and return the FETCHED manifest."""

        if not self.manifest_path.exists():
            raise SnapshotIntegrityError(
                "No pinned plan found; run 'core plan' before fetching "
                "(pin-before-fetch is mandatory per ADR-016 §7)"
            )
        manifest = _read_json(self.manifest_path)
        if manifest.get("status") == "COMPLETED":
            return self._verify_fetch_artifacts(manifest)
        if manifest.get("status") == "EXTEND_PLANNED":
            return self.fetch_extension()
        if manifest.get("status") not in {"PLANNED", "FETCHED"}:
            raise SnapshotIntegrityError(
                f"Manifest status {manifest.get('status')!r} is not PLANNED or FETCHED"
            )
        plan = manifest.get("sampling_plan")
        if not isinstance(plan, dict):
            raise SnapshotIntegrityError("Manifest lacks the pinned sampling_plan object")
        fingerprint = self._fingerprint(plan)
        self._plan_fingerprint = fingerprint
        if manifest.get("query_fingerprint") != fingerprint:
            raise SnapshotIntegrityError(
                "Pinned plan fingerprint mismatch: the manifest plan was edited after pinning"
            )

        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        pilot_records = self._load_pilot_records()
        pinned_sha = manifest.get("pilot_input", {}).get("works_sha256")
        actual_sha = _sha256_file(self.config.pilot_works_path)
        if not isinstance(pinned_sha, str) or pinned_sha != actual_sha:
            raise SnapshotIntegrityError(
                "Pilot works file changed after the plan was pinned "
                f"(manifest {pinned_sha!r} != measured {actual_sha})"
            )

        if manifest.get("status") == "FETCHED":
            return self._verify_fetch_artifacts(manifest)

        cached = self._load_cached_pages(fingerprint)
        page_number = len(cached) + 1
        state: dict[str, Any] = {
            "status": "IN_PROGRESS",
            "pages_cached": len(cached),
            "progress": self._progress_from_pages(cached),
            "counts": {"api_records_returned": 0, "retries": 0},
        }
        for page in cached:
            state["counts"]["api_records_returned"] += len(page["payload"]["results"])
            state["counts"]["retries"] += int(page.get("retry_count", 0))

        candidate_ids = [
            candidate["openalex_id"] for candidate in plan["hub_selection"]["hub_candidates"]
        ]
        batches = plan["hub_selection"]["hub_batches"]
        progress = state["progress"]
        hub_records: dict[str, dict[str, Any]] = {}
        for page in cached:
            if page["phase"] == "hubs":
                for result in page["payload"]["results"]:
                    hub_records[_bare_work_id(result["id"])] = result

        # ---- hub phase ---------------------------------------------------
        for batch_index, batch in enumerate(batches):
            hub_progress = progress["hubs"]
            if f"hub-batch-{batch_index}" in hub_progress["phase_keys_done"]:
                continue
            if state["counts"].get("stopped_early_global_cap"):
                break
            if self.config.request_interval_seconds:
                self._sleeper(self.config.request_interval_seconds)
            params = {
                "filter": f"openalex_id:{'|'.join(batch)}",
                "per_page": max(self.config.per_page, len(batch)),
                "page": 1,
                "select": ",".join(self.config.fields),
                "mailto": self.config.mailto,
            }
            payload, meta = self._request_works(params)
            envelope = self._envelope(
                phase="hubs",
                phase_key=f"hub-batch-{batch_index}",
                page_in_phase=1,
                page_number=page_number,
                params=params,
                payload=payload,
                meta=meta,
            )
            self._write_page(page_number, envelope)
            page_number += 1
            cached.append(envelope)
            for result in payload["results"]:
                hub_records[_bare_work_id(result["id"])] = result
            hub_progress["phase_keys_done"].append(f"hub-batch-{batch_index}")
            hub_progress["batches_done"] = len(hub_progress["phase_keys_done"])
            state["pages_cached"] = len(cached)
            state["counts"]["api_records_returned"] += len(payload["results"])
            state["counts"]["retries"] += meta["retry_count"]
            self._write_checkpoint(state)

        active_hubs, hub_exclusions = self._select_active_hubs(
            candidate_ids, hub_records
        )
        if not active_hubs:
            raise SnapshotIntegrityError(
                "No active hubs after applying the pinned active rule; "
                "the recruitment filter cannot be executed"
            )

        # ---- cohort phase ------------------------------------------------
        cohort_stats: dict[str, dict[str, Any]] = progress["cohorts"]
        cohort_records: dict[str, dict[str, Any]] = {}
        cohort_ids_by_year: dict[str, set[str]] = {key: set() for key in cohort_stats}
        for page in cached:
            if page["phase"] == "cohorts":
                for result in page["payload"]["results"]:
                    bare = _bare_work_id(result["id"])
                    cohort_records.setdefault(bare, result)
                    cohort_ids_by_year.setdefault(page["phase_key"], set()).add(bare)
        for key, ids in cohort_ids_by_year.items():
            if key in cohort_stats:
                cohort_stats[key]["unique_records_seen"] = len(ids)

        stopped_early = False
        for year in self.config.cohort_year_order:
            key = f"year-{year}"
            year_state = cohort_stats.setdefault(
                key,
                {
                    "pages_done": 0,
                    "sample_meta_count": None,
                    "planned_pages": None,
                    "api_records_returned": 0,
                    "unique_records_seen": 0,
                    "ended_on_empty_page": None,
                    "ended_reason": None,
                },
            )
            cohort_ids_by_year.setdefault(key, set())
            for page_in_phase in range(1, self._pages_per_year(self.config.per_year_sample_cap) + 1):
                if (
                    year_state["planned_pages"] is not None
                    and page_in_phase > year_state["planned_pages"]
                ):
                    year_state["ended_reason"] = "sample_pages_exhausted"
                    break
                if year_state["pages_done"] >= page_in_phase:
                    continue
                if stopped_early or state["counts"].get("stopped_early_global_cap"):
                    stopped_early = True
                    break
                unique_snapshot_estimate = (
                    len(pilot_records) + len(hub_records) + len(cohort_records)
                )
                if unique_snapshot_estimate >= self.config.global_work_cap:
                    stopped_early = True
                    state["counts"]["stopped_early_global_cap"] = True
                    break
                if page_in_phase > 1 and self.config.request_interval_seconds:
                    self._sleeper(self.config.request_interval_seconds)
                params = {
                    "filter": (
                        f"cites:{'|'.join(active_hubs)},publication_year:{year},"
                        "is_paratext:false"
                    ),
                    "sample": self.config.per_year_sample_cap,
                    "seed": self.config.sample_seed,
                    "per_page": self.config.per_page,
                    "page": page_in_phase,
                    "select": ",".join(self.config.fields),
                    "mailto": self.config.mailto,
                }
                payload, meta = self._request_works(params)
                results = payload["results"]
                if not results:
                    if page_in_phase == 1:
                        raise OpenAlexAPIError(
                            f"Cohort year {year} returned an empty first page; "
                            "the pinned sampling plan cannot be executed as pinned. "
                            "Cached evidence was preserved."
                        )
                    year_state["ended_on_empty_page"] = page_in_phase
                    year_state["ended_reason"] = "empty_page"
                    break
                envelope = self._envelope(
                    phase="cohorts",
                    phase_key=key,
                    page_in_phase=page_in_phase,
                    page_number=page_number,
                    params=params,
                    payload=payload,
                    meta=meta,
                )
                self._write_page(page_number, envelope)
                page_number += 1
                cached.append(envelope)
                for result in results:
                    bare = _bare_work_id(result["id"])
                    cohort_records.setdefault(bare, result)
                    cohort_ids_by_year[key].add(bare)
                year_state["pages_done"] = page_in_phase
                year_state["api_records_returned"] += len(results)
                year_state["unique_records_seen"] = len(cohort_ids_by_year[key])
                if year_state["sample_meta_count"] is None:
                    sample_count = payload.get("meta", {}).get("count")
                    if isinstance(sample_count, int):
                        year_state["sample_meta_count"] = sample_count
                        year_state["planned_pages"] = self._pages_per_year(sample_count)
                state["pages_cached"] = len(cached)
                state["counts"]["api_records_returned"] += len(results)
                state["counts"]["retries"] += meta["retry_count"]
                self._write_checkpoint(state)
                if (
                    year_state["planned_pages"] is not None
                    and page_in_phase >= year_state["planned_pages"]
                ):
                    year_state["ended_reason"] = "sample_pages_exhausted"
                    break
            else:
                if (
                    year_state["planned_pages"] is not None
                    and year_state["pages_done"] >= year_state["planned_pages"]
                ):
                    year_state["ended_reason"] = "sample_pages_exhausted"
                else:
                    year_state.setdefault("ended_reason", "cap_pages_reached")
            if stopped_early:
                state["counts"]["stopped_early_global_cap"] = True
                break

        return self._finalize_fetch(
            manifest,
            plan,
            fingerprint,
            cached,
            pilot_records,
            hub_records,
            cohort_records,
            active_hubs,
            hub_exclusions,
            cohort_stats,
            stopped_early,
        )

    def _pages_per_year(self, sample_count: int) -> int:
        return max(1, math.ceil(sample_count / self.config.per_page))

    def _progress_from_pages(self, pages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        hub_keys = sorted({page["phase_key"] for page in pages if page["phase"] == "hubs"})
        cohorts: dict[str, dict[str, Any]] = {}
        for page in pages:
            if page["phase"] != "cohorts":
                continue
            year_state = cohorts.setdefault(
                page["phase_key"],
                {
                    "pages_done": 0,
                    "sample_meta_count": None,
                    "planned_pages": None,
                    "api_records_returned": 0,
                    "unique_records_seen": 0,
                    "ended_on_empty_page": None,
                    "ended_reason": None,
                },
            )
            year_state["pages_done"] = max(year_state["pages_done"], int(page["page_in_phase"]))
            year_state["api_records_returned"] += len(page["payload"]["results"])
            if year_state["sample_meta_count"] is None:
                sample_count = page["payload"].get("meta", {}).get("count")
                if isinstance(sample_count, int):
                    year_state["sample_meta_count"] = sample_count
                    year_state["planned_pages"] = self._pages_per_year(sample_count)
        return {
            "hubs": {"phase_keys_done": list(hub_keys), "batches_done": len(hub_keys)},
            "cohorts": cohorts,
        }

    def _envelope(
        self,
        *,
        phase: str,
        phase_key: str,
        page_in_phase: int,
        page_number: int,
        params: Mapping[str, Any],
        payload: Mapping[str, Any],
        meta: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": CORE_SCHEMA_VERSION,
            "query_fingerprint": self._plan_fingerprint,
            "phase": phase,
            "phase_key": phase_key,
            "page_in_phase": page_in_phase,
            "page_number": page_number,
            "requested_at": _iso(self._clock()),
            "request": {"method": "GET", "params": dict(params)},
            "rate_limit": meta["rate_limit"],
            "retry_count": meta["retry_count"],
            "request_elapsed_seconds": meta["request_elapsed_seconds"],
            "payload_sha256": _sha256_json(payload),
            "payload": payload,
        }

    def _select_active_hubs(
        self,
        candidate_ids: Sequence[str],
        hub_records: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[str], dict[str, Any]]:
        """Apply the pinned active-hub rule in pinned rank order."""

        exclusions: dict[str, int] = {
            "unresolvable": 0,
            "year_missing_or_out_of_range": 0,
            "year_above_max": 0,
            "retracted": 0,
            "paratext": 0,
            "beyond_cap": 0,
        }
        unresolvable: list[str] = []
        active: list[str] = []
        for candidate_id in candidate_ids:
            record = hub_records.get(candidate_id)
            if record is None:
                exclusions["unresolvable"] += 1
                unresolvable.append(candidate_id)
                continue
            year = record.get("publication_year")
            if (
                isinstance(year, bool)
                or not isinstance(year, int)
                or not 1900 <= year <= 2100
            ):
                exclusions["year_missing_or_out_of_range"] += 1
                continue
            if year > self.config.active_hub_max_year:
                exclusions["year_above_max"] += 1
                continue
            if record.get("is_retracted") is True:
                exclusions["retracted"] += 1
                continue
            if record.get("is_paratext") is True:
                exclusions["paratext"] += 1
                continue
            if len(active) >= self.config.active_hub_cap:
                exclusions["beyond_cap"] += 1
                continue
            active.append(candidate_id)
        details: dict[str, Any] = dict(exclusions)
        details["unresolvable_ids"] = unresolvable
        return active, details

    def _finalize_fetch(
        self,
        manifest: dict[str, Any],
        plan: Mapping[str, Any],
        fingerprint: str,
        cached: Sequence[Mapping[str, Any]],
        pilot_records: Sequence[Mapping[str, Any]],
        hub_records: Mapping[str, Mapping[str, Any]],
        cohort_records: Mapping[str, Mapping[str, Any]],
        active_hubs: Sequence[str],
        hub_exclusions: Mapping[str, Any],
        cohort_stats: Mapping[str, Mapping[str, Any]],
        stopped_early: bool,
    ) -> dict[str, Any]:
        completed_at = self._clock()

        pilot_by_id: dict[str, dict[str, Any]] = {}
        for record in pilot_records:
            pilot_by_id[_bare_work_id(record["id"])] = record

        merged: dict[str, tuple[str, Mapping[str, Any]]] = {}
        overlaps = {
            "cohort_records_already_in_pilot": 0,
            "cohort_records_already_in_hubs": 0,
            "within_cohort_duplicate_records": 0,
            "hub_records_already_in_pilot": 0,
        }
        seen_cohort_ids: set[str] = set()
        for work_id, record in cohort_records.items():
            if work_id in seen_cohort_ids:
                continue
            seen_cohort_ids.add(work_id)
            if work_id in pilot_by_id:
                overlaps["cohort_records_already_in_pilot"] += 1
                continue
            if work_id in hub_records:
                overlaps["cohort_records_already_in_hubs"] += 1
                continue
            merged[work_id] = ("cohort", record)
        hub_merged = 0
        for work_id, record in hub_records.items():
            if work_id in pilot_by_id:
                overlaps["hub_records_already_in_pilot"] += 1
                continue
            merged[work_id] = ("hub", record)
            hub_merged += 1
        for work_id, record in pilot_by_id.items():
            merged[work_id] = ("pilot", record)

        if len(merged) < self.config.minimum_snapshot_works:
            raise SnapshotIntegrityError(
                f"Pinned plan requires at least {self.config.minimum_snapshot_works} "
                f"unique works; the fetch produced {len(merged)}. "
                "Cached evidence was preserved."
            )

        ordered_ids = sorted(merged, key=lambda work_id: f"openalex:{work_id}")
        _atomic_write_jsonl(self.works_path, (merged[work_id][1] for work_id in ordered_ids))

        composition = {
            "pilot_works": len(pilot_by_id),
            "hub_works_merged": hub_merged,
            "cohort_only_works": len(merged) - len(pilot_by_id) - hub_merged,
            "total_unique_works": len(merged),
        }
        per_year: dict[str, int] = {}
        for page in cached:
            if page["phase"] != "cohorts":
                continue
            year = page["phase_key"].removeprefix("year-")
            per_year[year] = per_year.get(year, 0) + len(page["payload"]["results"])

        retries = sum(int(page.get("retry_count", 0)) for page in cached)
        api_cost = sum(
            float(page["payload"].get("meta", {}).get("cost_usd") or 0.0) for page in cached
        )
        execution = {
            "fetch_started_at": min(page["requested_at"] for page in cached),
            "fetch_completed_at": _iso(completed_at),
            "pages": len(cached),
            "hub_batches": len(plan["hub_selection"]["hub_batches"]),
            "hub_records_returned": sum(
                len(page["payload"]["results"])
                for page in cached
                if page["phase"] == "hubs"
            ),
            "hubs": {
                "candidate_count": len(plan["hub_selection"]["hub_candidates"]),
                "unique_fetched": len(hub_records),
                "active_hubs_used": len(active_hubs),
                "active_hubs": list(active_hubs),
                "exclusions": dict(hub_exclusions),
            },
            "cohorts": {
                "years_fetched": {
                    key: dict(value) for key, value in sorted(cohort_stats.items())
                },
                "api_records_returned_by_year": per_year,
            },
            "duplicates_and_overlaps": overlaps,
            "snapshot_composition": composition,
            "stopped_early_global_cap": stopped_early,
            "retries": retries,
            "api_cost_usd_reported_by_meta": round(api_cost, 6),
            "last_rate_limit_headers": cached[-1].get("rate_limit", {}) if cached else {},
        }

        page_artifacts = [
            {
                "path": _display_path(self.pages_dir / f"page-{index:05d}.json"),
                "sha256": _sha256_file(self.pages_dir / f"page-{index:05d}.json"),
            }
            for index in range(1, len(cached) + 1)
        ]
        updated = dict(manifest)
        updated["status"] = "FETCHED"
        updated["retrieved_started_at"] = execution["fetch_started_at"]
        updated["retrieved_completed_at"] = execution["fetch_completed_at"]
        updated["execution"] = execution
        updated["artifacts"] = {
            "pilot_works_jsonl": {
                "path": _display_path(self.config.pilot_works_path),
                "sha256": _sha256_file(self.config.pilot_works_path),
                "bytes": self.config.pilot_works_path.stat().st_size,
            },
            "raw_works_jsonl": {
                "path": _display_path(self.works_path),
                "sha256": _sha256_file(self.works_path),
                "bytes": self.works_path.stat().st_size,
            },
            "raw_pages": page_artifacts,
        }
        _atomic_write_json(self.manifest_path, updated)

        state = {
            "status": "COMPLETED",
            "pages_cached": len(cached),
            "counts": {
                "api_records_returned": sum(
                    len(page["payload"]["results"]) for page in cached
                ),
                "retries": retries,
                "total_unique_works": len(merged),
            },
            "manifest_status": "FETCHED",
        }
        self._write_checkpoint(state)
        return updated

    def _verify_fetch_artifacts(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        artifacts = manifest.get("artifacts", {})
        raw = artifacts.get("raw_works_jsonl", {})
        if not isinstance(raw, dict) or not raw.get("sha256"):
            raise SnapshotIntegrityError("Manifest lacks raw_works_jsonl sha256")
        if not self.works_path.exists() or _sha256_file(self.works_path) != raw["sha256"]:
            raise SnapshotIntegrityError(
                f"Raw works file mismatch or missing: {self.works_path}"
            )
        raw_pages = artifacts.get("raw_pages")
        cached_paths = sorted(self.pages_dir.glob("page-*.json"))
        if not isinstance(raw_pages, list) or len(raw_pages) != len(cached_paths):
            raise SnapshotIntegrityError("Raw-page inventory mismatch")
        for path, page_artifact in zip(cached_paths, raw_pages):
            if not isinstance(page_artifact, dict):
                raise SnapshotIntegrityError("Malformed raw-page entry in manifest")
            if not page_artifact.get("sha256") or _sha256_file(path) != page_artifact["sha256"]:
                raise SnapshotIntegrityError(f"Raw page mismatch: {path}")
        return dict(manifest)

    # -- extension (v2) fetch ----------------------------------------------

    def _load_pages_with_fingerprints(
        self, v1_fingerprint: str, v2_fingerprint: str | None
    ) -> list[dict[str, Any]]:
        """Validate every cached page; v1 phases and the extension phase use
        their own pinned fingerprints."""

        pages: list[dict[str, Any]] = []
        for expected, path in enumerate(sorted(self.pages_dir.glob("page-*.json")), start=1):
            page = _read_json(path)
            if page.get("page_number") != expected:
                raise SnapshotIntegrityError(f"Non-contiguous cached page sequence at {path}")
            payload = page.get("payload")
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise SnapshotIntegrityError(f"Malformed cached payload: {path}")
            if page.get("payload_sha256") != _sha256_json(payload):
                raise SnapshotIntegrityError(f"Cached page checksum mismatch: {path}")
            if page.get("phase") == "extension":
                if v2_fingerprint is None or page.get("query_fingerprint") != v2_fingerprint:
                    raise SnapshotIntegrityError(
                        f"Extension page belongs to another extension plan: {path}"
                    )
            elif page.get("query_fingerprint") != v1_fingerprint:
                raise SnapshotIntegrityError(f"Cached page belongs to another plan: {path}")
            pages.append(page)
        return pages

    def fetch_extension(self) -> dict[str, Any]:
        """Execute (or resume) the pinned v2 extension and return the manifest."""

        manifest = _read_json(self.manifest_path)
        if manifest.get("status") != "EXTEND_PLANNED":
            raise SnapshotIntegrityError(
                "fetch_extension requires manifest status EXTEND_PLANNED "
                f"(found {manifest.get('status')!r})"
            )
        plan_v2 = manifest.get("sampling_plan_v2")
        if not isinstance(plan_v2, dict):
            raise SnapshotIntegrityError("Manifest lacks the pinned sampling_plan_v2")
        fingerprint_v2 = _sha256_json(plan_v2)
        if manifest.get("v2_fingerprint") != fingerprint_v2:
            raise SnapshotIntegrityError(
                "Extension plan fingerprint mismatch: the manifest v2 plan was "
                "edited after pinning"
            )
        fingerprint_v1 = manifest.get("query_fingerprint")
        self._plan_fingerprint = fingerprint_v2

        self.pages_dir.mkdir(parents=True, exist_ok=True)
        cached = self._load_pages_with_fingerprints(fingerprint_v1, fingerprint_v2)
        page_number = len(cached) + 1

        raw_entry = manifest.get("artifacts", {}).get("raw_works_jsonl", {})
        if not self.works_path.exists() or _sha256_file(self.works_path) != raw_entry.get("sha256"):
            raise SnapshotIntegrityError(
                f"v1 raw works file mismatch or missing: {self.works_path}"
            )
        existing: dict[str, dict[str, Any]] = {}
        with self.works_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    existing[_bare_work_id(record["id"])] = record

        recruitment = plan_v2["recruitment"]
        buckets: dict[int, int] = {
            int(year): int(count)
            for year, count in recruitment["year_buckets"].items()
        }
        first_year = int(recruitment["first_year"])
        topic_id = recruitment["topic_id"]
        ext_pages = [
            page for page in cached if page.get("phase") == "extension"
        ]
        done_keys = {page["phase_key"] for page in ext_pages}
        ext_records: dict[str, dict[str, Any]] = {}
        empty_buckets: set[str] = set()
        within_extension_duplicates = 0
        for page in ext_pages:
            for result in page["payload"]["results"]:
                bare = _bare_work_id(result["id"])
                if bare in ext_records:
                    within_extension_duplicates += 1
                else:
                    ext_records[bare] = result
            if not page["payload"]["results"]:
                empty_buckets.add(page["phase_key"])

        per_bucket: dict[str, dict[str, Any]] = {}
        added_total = 0
        stopped_early_cap = False
        state = {
            "status": "IN_PROGRESS",
            "stage": "extension",
            "pages_cached": len(cached),
        }
        cached_by_key = {page["phase_key"]: page for page in ext_pages}
        for year in sorted(buckets):
            key = f"ext-{year}"
            bucket_state = {
                "sample_size": buckets[year],
                "api_records_returned": len(cached_by_key[key]["payload"]["results"])
                if key in cached_by_key
                else 0,
                "unique_new_records": 0,
                "empty": key in empty_buckets,
            }
            if key not in done_keys:
                if len(existing) + len(ext_records) >= self.config.global_work_cap:
                    stopped_early_cap = True
                    bucket_state["skipped_cap"] = True
                    per_bucket[str(year)] = bucket_state
                    continue
                if self.config.request_interval_seconds:
                    self._sleeper(self.config.request_interval_seconds)
                params = {
                    "filter": f"topics.id:{topic_id},publication_year:{year}",
                    "sample": buckets[year],
                    "seed": self.config.sample_seed,
                    "per_page": max(self.config.per_page, buckets[year]),
                    "page": 1,
                    "select": ",".join(self.config.fields),
                    "mailto": self.config.mailto,
                }
                payload, meta = self._request_works(params)
                envelope = self._envelope(
                    phase="extension",
                    phase_key=key,
                    page_in_phase=1,
                    page_number=page_number,
                    params=params,
                    payload=payload,
                    meta=meta,
                )
                self._write_page(page_number, envelope)
                page_number += 1
                cached.append(envelope)
                if not payload["results"]:
                    empty_buckets.add(key)
                    bucket_state["empty"] = True
                for result in payload["results"]:
                    bare = _bare_work_id(result["id"])
                    if bare in ext_records:
                        within_extension_duplicates += 1
                    else:
                        ext_records[bare] = result
                bucket_state["api_records_returned"] = len(payload["results"])
                state["pages_cached"] = len(cached)
                self._write_checkpoint(state)
            per_bucket[str(year)] = bucket_state

        duplicates = {
            "extension_records_already_in_snapshot": 0,
            "within_extension_duplicates": within_extension_duplicates,
        }
        seen_ext: set[str] = set()
        new_records: dict[str, dict[str, Any]] = {}
        for work_id, record in ext_records.items():
            if work_id in seen_ext:
                duplicates["within_extension_duplicates"] += 1
                continue
            seen_ext.add(work_id)
            if work_id in existing:
                duplicates["extension_records_already_in_snapshot"] += 1
                continue
            new_records[work_id] = record
            added_total += 1

        merged = dict(existing)
        merged.update(new_records)
        if len(merged) > self.config.global_work_cap:
            raise SnapshotIntegrityError(
                f"Extension would reach {len(merged)} works, exceeding the pinned "
                f"global cap {self.config.global_work_cap}"
            )
        ordered_ids = sorted(merged, key=lambda work_id: f"openalex:{work_id}")
        superseded_sha = _sha256_file(self.works_path)
        _atomic_write_jsonl(
            self.works_path, (merged[work_id] for work_id in ordered_ids)
        )
        completed_at = self._clock()

        # Recompute per-bucket new-record counts from the request payloads.
        for year in per_bucket:
            per_bucket[year]["unique_new_records"] = 0
        for page in cached:
            if page.get("phase") != "extension":
                continue
            year_key = str(page["phase_key"]).removeprefix("ext-")
            if year_key in per_bucket and page["payload"]["results"]:
                per_bucket[year_key]["unique_new_records"] += len(
                    {
                        _bare_work_id(result["id"])
                        for result in page["payload"]["results"]
                        if _bare_work_id(result["id"]) in new_records
                    }
                )

        # Count from `cached`, not from the pre-fetch `ext_pages` snapshot:
        # on a fresh extension run `ext_pages` is empty and would record 0
        # pages even though this run just wrote its bucket pages.
        execution_extension = {
            "completed_at": _iso(completed_at),
            "pages": sum(1 for page in cached if page.get("phase") == "extension"),
            "per_bucket": per_bucket,
            "duplicates": duplicates,
            "new_works_added": added_total,
            "total_unique_works": len(merged),
            "stopped_early_cap": stopped_early_cap,
            "superseded_raw_works_sha256": superseded_sha,
        }

        page_artifacts = [
            {
                "path": _display_path(self.pages_dir / f"page-{index:05d}.json"),
                "sha256": _sha256_file(self.pages_dir / f"page-{index:05d}.json"),
            }
            for index in range(1, len(cached) + 1)
        ]
        updated = dict(manifest)
        updated["status"] = "FETCHED"
        updated["retrieved_completed_at"] = _iso(completed_at)
        updated["execution_extension"] = execution_extension
        artifacts = dict(updated.get("artifacts", {}))
        artifacts["raw_works_jsonl"] = {
            "path": _display_path(self.works_path),
            "sha256": _sha256_file(self.works_path),
            "bytes": self.works_path.stat().st_size,
        }
        artifacts["raw_pages"] = page_artifacts
        updated["artifacts"] = artifacts
        _atomic_write_json(self.manifest_path, updated)

        state = {
            "status": "COMPLETED",
            "stage": "extension",
            "pages_cached": len(cached),
            "counts": {"total_unique_works": len(merged), "new_works_added": added_total},
            "manifest_status": "FETCHED",
        }
        self._write_checkpoint(state)
        return updated


# ---------------------------------------------------------------------------
# SG-015 post-processing: normalization with counted transformations and the
# independent quality report.
# ---------------------------------------------------------------------------

_METADATA_FIELDS_ABSENT_NULLED = ("title", "abstract_inverted_index", "publication_year")


def normalize_core_record(record: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Normalize one raw work record; every transformation is counted.

    Fatal: missing/blank/invalid ``id``, wrong-typed ``referenced_works``
    entries, wrong-typed DOI/abstract/title/year values.  An absent
    ``referenced_works`` key is normalized to ``[]`` and counted (the SG-014
    gate treats a missing key as fatal, so the processed snapshot guarantees
    its presence explicitly rather than silently).
    """

    transformations = {
        "doi_normalized": 0,
        "doi_prefix_stripped": 0,
        "doi_case_normalized": 0,
        "reference_ids_canonicalized": 0,
        "referenced_works_key_filled": 0,
        "metadata_fields_absent_nulled": 0,
    }
    if not isinstance(record, Mapping):
        raise SnapshotIntegrityError("Work record must be a JSON object")
    if "id" not in record:
        raise SnapshotIntegrityError("Work record lacks required field 'id'")
    try:
        _bare_work_id(record["id"])
    except ValueError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc

    processed = dict(record)

    raw_doi = record.get("doi") if "doi" in record else None
    try:
        normalized_doi = normalize_core_doi(raw_doi)
    except SnapshotIntegrityError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc
    if isinstance(raw_doi, str) and normalized_doi != raw_doi:
        transformations["doi_normalized"] += 1
        stripped = raw_doi.strip().lower()
        if stripped != raw_doi.strip():
            transformations["doi_case_normalized"] += 1
        for prefix in _CORE_DOI_PREFIXES:
            if stripped.startswith(prefix):
                transformations["doi_prefix_stripped"] += 1
                break
    processed["doi"] = normalized_doi

    raw_refs = record.get("referenced_works") if "referenced_works" in record else None
    if raw_refs is None:
        transformations["referenced_works_key_filled"] += 1
        raw_refs = []
    if not isinstance(raw_refs, list):
        raise SnapshotIntegrityError(
            f"'referenced_works' must be a list, got {type(raw_refs).__name__}"
        )
    canonical_refs: list[str] = []
    for position, target in enumerate(raw_refs):
        if not isinstance(target, str):
            raise SnapshotIntegrityError(
                f"referenced_works[{position}] must be a string, got {type(target).__name__}"
            )
        try:
            bare = _bare_work_id(target)
        except ValueError as exc:
            raise SnapshotIntegrityError(str(exc)) from exc
        if bare != target:
            transformations["reference_ids_canonicalized"] += 1
        canonical_refs.append(bare)
    processed["referenced_works"] = canonical_refs

    for field in _METADATA_FIELDS_ABSENT_NULLED:
        if field not in record:
            processed[field] = None
            transformations["metadata_fields_absent_nulled"] += 1
        elif field == "publication_year":
            year = record[field]
            if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
                raise SnapshotIntegrityError(
                    f"'publication_year' must be an integer or null, got {type(year).__name__}"
                )
        elif field == "abstract_inverted_index":
            abstract = record[field]
            if abstract is not None and not isinstance(abstract, dict):
                raise SnapshotIntegrityError(
                    "'abstract_inverted_index' must be an object or null"
                )
        elif field == "title":
            title = record[field]
            if title is not None and not isinstance(title, str):
                raise SnapshotIntegrityError("'title' must be a string or null")

    return processed, transformations


def _valid_core_year(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1900 <= value <= 2100
    )


def _core_union_components(
    nodes: set[str], edges: set[tuple[str, str]]
) -> tuple[int, int]:
    """Weakly connected component count and largest size (independent impl)."""

    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for source, target in edges:
        root_source, root_target = find(source), find(target)
        if root_source != root_target:
            parent[root_source] = root_target
    sizes: dict[str, int] = {}
    for node in nodes:
        root = find(node)
        sizes[root] = sizes.get(root, 0) + 1
    return len(sizes), max(sizes.values()) if sizes else 0


def compute_core_quality_report(
    *,
    raw_records: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    raw_works_sha256: str,
    processed_works_path: Path,
    processed_works_sha256: str,
    measured_at: datetime,
    command: Sequence[str],
) -> dict[str, Any]:
    """Independent SG-015 quality measurement over the processed snapshot.

    Implemented separately from ``scholargraph.graph.feasibility`` so the two
    counts can be cross-checked; the official GO/NO-GO decision comes from the
    gate CLI report (``graph_feasibility_core.json``).
    """

    if not raw_records:
        raise SnapshotIntegrityError("Core snapshot is empty: no work records to measure")

    works: list[dict[str, Any]] = []
    transformations_total = {
        "doi_normalized": 0,
        "doi_prefix_stripped": 0,
        "doi_case_normalized": 0,
        "reference_ids_canonicalized": 0,
        "referenced_works_key_filled": 0,
        "metadata_fields_absent_nulled": 0,
    }
    anomalies = {
        "missing_title_count": 0,
        "blank_title_count": 0,
        "missing_abstract_count": 0,
        "missing_publication_year_count": 0,
        "out_of_range_publication_year_count": 0,
        "missing_doi_count": 0,
        "duplicate_reference_entry_count": 0,
        "self_loop_count": 0,
    }
    for index, record in enumerate(raw_records):
        processed, transforms = normalize_core_record(record)
        for key, value in transforms.items():
            transformations_total[key] += value
        canonical = f"openalex:{_bare_work_id(processed['id'])}"
        refs = processed["referenced_works"]
        if len(set(refs)) != len(refs):
            anomalies["duplicate_reference_entry_count"] += len(refs) - len(set(refs))
        if canonical in {f"openalex:{_bare_work_id(ref)}" for ref in refs}:
            anomalies["self_loop_count"] += 1
        title = processed.get("title")
        if title is None:
            anomalies["missing_title_count"] += 1
        elif not str(title).strip():
            anomalies["blank_title_count"] += 1
        if not processed.get("abstract_inverted_index"):
            anomalies["missing_abstract_count"] += 1
        year = processed.get("publication_year")
        if year is None:
            anomalies["missing_publication_year_count"] += 1
        elif not _valid_core_year(year):
            anomalies["out_of_range_publication_year_count"] += 1
        if processed.get("doi") is None:
            anomalies["missing_doi_count"] += 1
        works.append({**processed, "_canonical_id": canonical})

    works.sort(key=lambda work: work["_canonical_id"])
    n = len(works)
    canonical_ids = [work["_canonical_id"] for work in works]
    if len(set(canonical_ids)) != n:
        raise SnapshotIntegrityError("Duplicate canonical work IDs in the core snapshot")
    id_set = set(canonical_ids)
    years = {
        work["_canonical_id"]: work["publication_year"]
        for work in works
        if _valid_core_year(work.get("publication_year"))
    }

    reference_entries_total = 0
    internal_occurrences = 0
    out_of_snapshot_occurrences = 0
    unique_edges: set[tuple[str, str]] = set()
    out_degree: dict[str, int] = {canonical: 0 for canonical in id_set}
    in_degree: dict[str, int] = {canonical: 0 for canonical in id_set}
    for work in works:
        source = work["_canonical_id"]
        reference_entries_total += len(work["referenced_works"])
        for target in work["referenced_works"]:
            target_canonical = f"openalex:{target}"
            if target_canonical == source:
                continue
            if target_canonical not in id_set:
                out_of_snapshot_occurrences += 1
                continue
            internal_occurrences += 1
            unique_edges.add((source, target_canonical))
            out_degree[source] += 1
            in_degree[target_canonical] += 1

    reciprocal_pairs = (
        sum(1 for source, target in unique_edges if (target, source) in unique_edges) // 2
    )
    nodes_with_edges = {node for edge in unique_edges for node in edge}
    isolated = id_set - nodes_with_edges
    components, largest_component = _core_union_components(id_set, unique_edges)
    density = len(unique_edges) / (n * (n - 1)) if n > 1 else None

    doi_to_works: dict[str, list[str]] = {}
    for work in works:
        doi = work.get("doi")
        if doi is not None:
            doi_to_works.setdefault(doi, []).append(work["_canonical_id"])
    duplicated_doi_groups = {doi: ids for doi, ids in doi_to_works.items() if len(ids) > 1}

    year_distribution: dict[str, int] = {}
    for year in years.values():
        year_distribution[str(year)] = year_distribution.get(str(year), 0) + 1

    def coverage(count: int) -> dict[str, Any]:
        return {
            "count": count,
            "total": n,
            "fraction": round(count / n, 6) if n else None,
        }

    # ---- Protocol v1 track-B eligibility (independent recount) ----------
    floors = {
        "minimum_test_queries": 50,
        "minimum_dev_queries": 30,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 100,
    }
    manifest_gate = manifest.get("sampling_plan", {}).get("invariants", {}).get("floors")
    if isinstance(manifest_gate, dict):
        floors.update(
            {key: value for key, value in manifest_gate.items() if key in floors}
        )
    min_refs = floors["minimum_eligible_references"]
    works_per_year: dict[int, int] = {}
    for year in years.values():
        works_per_year[year] = works_per_year.get(year, 0) + 1
    cumulative: dict[int, int] = {}
    running = 0
    for year in sorted(works_per_year):
        running += works_per_year[year]
        cumulative[year] = running

    eligible_by_year: dict[int, int] = {}
    universe_sizes: list[int] = []
    for work in works:
        source_year = work.get("publication_year")
        title = work.get("title")
        if (
            not _valid_core_year(source_year)
            or title is None
            or not str(title).strip()
            or not work.get("abstract_inverted_index")
        ):
            continue
        eligible_refs = 0
        seen_targets: set[str] = set()
        for target in work["referenced_works"]:
            target_canonical = f"openalex:{target}"
            if target_canonical == work["_canonical_id"] or target_canonical in seen_targets:
                continue
            if target_canonical not in id_set:
                continue
            target_year = years.get(target_canonical)
            if target_year is not None and target_year <= source_year:
                eligible_refs += 1
                seen_targets.add(target_canonical)
        if eligible_refs >= min_refs:
            eligible_by_year[source_year] = eligible_by_year.get(source_year, 0) + 1
            universe_sizes.append(cumulative[source_year] - 1 - eligible_refs)

    snapshot_year = int(str(manifest.get("retrieved_completed_at", "0000"))[:4] or 0)
    test_year = None
    for year in sorted(eligible_by_year, reverse=True):
        if year < snapshot_year and eligible_by_year[year] >= floors["minimum_test_queries"]:
            test_year = year
            break
    dev_year = None
    if test_year is not None:
        for year in sorted(eligible_by_year, reverse=True):
            if year < test_year and eligible_by_year[year] >= floors["minimum_dev_queries"]:
                dev_year = year
                break

    composition = manifest.get("execution", {}).get("snapshot_composition", {})
    execution = manifest.get("execution", {})

    return {
        "schema_version": CORE_SCHEMA_VERSION,
        "artifact_type": "openalex_core_quality_report",
        "task_id": CORE_TASK_ID,
        "status": "MEASURED",
        "measured_at": _iso(measured_at),
        "command": list(command),
        "qrels_used": False,
        "provenance": {
            "snapshot_id": manifest.get("snapshot_id"),
            "query_fingerprint": manifest.get("query_fingerprint"),
            "manifest_path": _display_path(manifest_path),
            "pilot_works_jsonl": manifest.get("artifacts", {}).get("pilot_works_jsonl", {}),
            "raw_works_jsonl": {
                **manifest.get("artifacts", {}).get("raw_works_jsonl", {}),
                "sha256_measured": raw_works_sha256,
            },
            "processed_works_jsonl": {
                "path": _display_path(processed_works_path),
                "sha256": processed_works_sha256,
                "bytes": processed_works_path.stat().st_size,
            },
            "inputs_note": (
                "counts are recomputed from the processed snapshot; the official "
                "GO/NO-GO decision is the gate CLI report graph_feasibility_core.json"
            ),
        },
        "sampling_execution": {
            "pages": execution.get("pages"),
            "retries": execution.get("retries"),
            "api_cost_usd_reported_by_meta": execution.get("api_cost_usd_reported_by_meta"),
            "hubs": execution.get("hubs"),
            "cohorts": execution.get("cohorts"),
            "duplicates_and_overlaps": execution.get("duplicates_and_overlaps"),
            "snapshot_composition": composition,
            "extension": manifest.get("execution_extension"),
            "extension_plan_version": (
                manifest.get("sampling_plan_v2", {}).get("version")
                if manifest.get("sampling_plan_v2")
                else None
            ),
        },
        "counts": {
            "works": n,
            "unique_canonical_ids": len(id_set),
            "reference_entries_total": reference_entries_total,
            "internal_reference_occurrences": internal_occurrences,
            "unique_internal_directed_edges": len(unique_edges),
            "self_loop_count": anomalies["self_loop_count"],
            "duplicate_reference_entry_count": anomalies["duplicate_reference_entry_count"],
            "reciprocal_edge_pair_count": reciprocal_pairs,
            "out_of_snapshot_reference_occurrences": out_of_snapshot_occurrences,
            "isolated_nodes": len(isolated),
            "nodes_with_at_least_one_internal_edge": len(nodes_with_edges),
            "weakly_connected_components": components,
            "largest_weak_component_size": largest_component,
            "max_internal_out_degree": max(out_degree.values()) if out_degree else None,
            "max_internal_in_degree": max(in_degree.values()) if in_degree else None,
        },
        "derived": {
            "isolated_node_fraction": round(len(isolated) / n, 6) if n else None,
            "directed_density": round(density, 12) if density is not None else None,
            "mean_internal_out_degree": round(len(unique_edges) / n, 6) if n else None,
            "largest_weak_component_fraction": (
                round(largest_component / n, 6) if n else None
            ),
        },
        "coverage": {
            "title": coverage(n - anomalies["missing_title_count"] - anomalies["blank_title_count"]),
            "abstract_inverted_index": coverage(n - anomalies["missing_abstract_count"]),
            "doi": coverage(n - anomalies["missing_doi_count"]),
            "valid_publication_year_1900_2100": coverage(len(years)),
            "has_any_reference": coverage(
                sum(1 for work in works if work["referenced_works"])
            ),
        },
        "doi_normalization": {
            "works_with_doi": sum(len(ids) for ids in doi_to_works.values()),
            "unique_normalized_dois": len(doi_to_works),
            "duplicated_doi_groups": len(duplicated_doi_groups),
            "works_sharing_a_doi": sum(len(ids) for ids in duplicated_doi_groups.values()),
            "transformations": {
                key: transformations_total[key]
                for key in ("doi_normalized", "doi_prefix_stripped", "doi_case_normalized")
            },
            "absent_or_null_count": anomalies["missing_doi_count"],
        },
        "metadata_transformations": {
            "reference_ids_canonicalized": transformations_total["reference_ids_canonicalized"],
            "referenced_works_key_filled": transformations_total["referenced_works_key_filled"],
            "metadata_fields_absent_nulled": transformations_total["metadata_fields_absent_nulled"],
            "policy": (
                "every normalization is counted; missing referenced_works keys are "
                "filled with [] so the snapshot satisfies the gate's strict schema; "
                "nothing is dropped silently"
            ),
        },
        "anomalies": {
            key: value
            for key, value in anomalies.items()
            if key not in {"missing_title_count", "blank_title_count"}
        },
        "years": {
            "valid_publication_year_count": len(years),
            "missing_publication_year_count": anomalies["missing_publication_year_count"],
            "out_of_range_publication_year_count": anomalies[
                "out_of_range_publication_year_count"
            ],
            "min_valid_year": min(years.values()) if years else None,
            "max_valid_year": max(years.values()) if years else None,
            "distribution": dict(
                sorted(year_distribution.items(), key=lambda item: int(item[0]))
            ),
        },
        "protocol_b_cohorts_independent_recount": {
            "eligible_definition": (
                "valid publication year; non-empty title and abstract; at least "
                f"{min_refs} distinct internal references with known target year "
                "<= source year"
            ),
            "eligible_source_count_by_publication_year": {
                str(year): count for year, count in sorted(eligible_by_year.items())
            },
            "total_eligible_sources": sum(eligible_by_year.values()),
            "max_eligible_sources_in_any_year": (
                max(eligible_by_year.values()) if eligible_by_year else 0
            ),
            "novel_candidate_universe_lower_bound": {
                "sources_measured": len(universe_sizes),
                "min": min(universe_sizes) if universe_sizes else None,
                "median": statistics.median(universe_sizes) if universe_sizes else None,
                "max": max(universe_sizes) if universe_sizes else None,
                "sources_below_minimum_novel_candidates": (
                    sum(
                        1
                        for size in universe_sizes
                        if size < floors["minimum_novel_candidates_per_query"]
                    )
                    if universe_sizes
                    else None
                ),
            },
            "floors_applied": floors,
            "snapshot_year": snapshot_year or None,
            "test_year_candidate": test_year,
            "dev_year_candidate": dev_year,
            "note": (
                "independent recount for cross-checking; the binding gate decision "
                "is produced by the SG-014 CLI on this snapshot"
            ),
        },
        "known_limitations": [
            "OpenAlex referenced_works contains only references OpenAlex successfully matched to another work.",
            "Hub IDs that no longer resolve on the live API are counted as unresolvable and cannot contribute edges.",
            "The seeded per-year samples are reproducible only against an unchanged upstream database; local page hashes define this snapshot.",
            "The cohort recruitment filter biases the snapshot toward works citing the pinned hub set; coverage counts make this measurable.",
        ],
    }


def run_core_postprocess(
    *,
    manifest_path: Path,
    raw_dir: Path,
    processed_dir: Path,
    quality_report_path: Path,
    command: Sequence[str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Normalize the fetched raw snapshot and write processed + quality report.

    Returns ``(exit_code, manifest_or_error)``; exit code 1 on any fatal
    problem (missing raw file, manifest not FETCHED/COMPLETED, corrupt
    records).  When the manifest is already COMPLETED the artifacts are only
    verified, never rewritten.
    """

    try:
        manifest = _read_json(manifest_path)
        status = manifest.get("status")
        if status == "COMPLETED":
            artifacts = manifest.get("artifacts", {})
            processed_entry = artifacts.get("works_jsonl", {})
            quality_entry = artifacts.get("quality_report", {})
            processed_path = (
                Path(processed_entry["path"])
                if processed_entry.get("path")
                else processed_dir / "works.jsonl"
            )
            if processed_entry.get("sha256"):
                if not processed_path.exists() or _sha256_file(processed_path) != processed_entry["sha256"]:
                    raise SnapshotIntegrityError(
                        f"Processed works hash mismatch or missing: {processed_path}"
                    )
            if quality_entry.get("sha256"):
                quality_path = Path(quality_entry["path"])
                if not quality_path.exists() or _sha256_file(quality_path) != quality_entry["sha256"]:
                    raise SnapshotIntegrityError(
                        f"Quality report hash mismatch or missing: {quality_path}"
                    )
            return 0, manifest
        if status != "FETCHED":
            raise SnapshotIntegrityError(
                "Core manifest status must be FETCHED before postprocess "
                f"(found {status!r})"
            )

        raw_works_path = raw_dir / "works.jsonl"
        raw_entry = manifest.get("artifacts", {}).get("raw_works_jsonl", {})
        if not raw_works_path.is_file():
            raise SnapshotIntegrityError(f"Raw works file is missing: {raw_works_path}")
        raw_sha = _sha256_file(raw_works_path)
        if raw_entry.get("sha256") and raw_sha != raw_entry["sha256"]:
            raise SnapshotIntegrityError(
                "Raw works file hash changed since fetch "
                f"({raw_entry['sha256']} != {raw_sha})"
            )

        raw_records: list[dict[str, Any]] = []
        with raw_works_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw_records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise SnapshotIntegrityError(
                        f"{raw_works_path}:{line_number}: invalid JSON line ({exc.msg})"
                    ) from None

        processed_records: list[dict[str, Any]] = []
        for record in raw_records:
            processed, _ = normalize_core_record(record)
            processed_records.append(processed)
        processed_records.sort(
            key=lambda record: f"openalex:{_bare_work_id(record['id'])}"
        )
        processed_dir.mkdir(parents=True, exist_ok=True)
        processed_path = processed_dir / "works.jsonl"
        _atomic_write_jsonl(processed_path, processed_records)
        processed_sha = _sha256_file(processed_path)

        quality_report_path.parent.mkdir(parents=True, exist_ok=True)
        report = compute_core_quality_report(
            raw_records=raw_records,
            manifest=manifest,
            manifest_path=manifest_path,
            raw_works_sha256=raw_sha,
            processed_works_path=processed_path,
            processed_works_sha256=processed_sha,
            measured_at=(clock or (lambda: datetime.now(timezone.utc)))(),
            command=command if command is not None else list(sys.argv[1:]),
        )
        _atomic_write_json(quality_report_path, report)

        updated = dict(manifest)
        updated["status"] = "COMPLETED"
        updated["postprocess"] = {
            "processed_at": report["measured_at"],
            "processed_works": len(processed_records),
            "output_order": "canonical ID ascending",
        }
        artifacts = dict(updated.get("artifacts", {}))
        artifacts["works_jsonl"] = {
            "path": _display_path(processed_path),
            "sha256": processed_sha,
            "bytes": processed_path.stat().st_size,
        }
        artifacts["quality_report"] = {
            "path": _display_path(quality_report_path),
            "sha256": _sha256_file(quality_report_path),
        }
        updated["artifacts"] = artifacts
        _atomic_write_json(manifest_path, updated)
        return 0, updated
    except (SnapshotIntegrityError, OpenAlexError) as exc:
        return 1, {"status": "FAIL", "errors": [str(exc)]}


def write_core_plan(
    *,
    config: OpenAlexCoreConfig,
    manifest_path: Path,
    pilot_manifest_path: Path,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Pin the sampling plan into the manifest BEFORE any download (ADR-016 §7).

    Refuses to overwrite an existing manifest: the plan is written once.
    """

    if manifest_path.exists():
        raise SnapshotIntegrityError(
            f"Refusing to overwrite an existing manifest: {manifest_path}"
        )
    if not config.pilot_works_path.is_file():
        raise SnapshotIntegrityError(
            f"Pilot works file is missing: {config.pilot_works_path}"
        )
    if not pilot_manifest_path.is_file():
        raise SnapshotIntegrityError(
            f"Pilot manifest file is missing: {pilot_manifest_path}"
        )
    pilot_records: list[dict[str, Any]] = []
    with config.pilot_works_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                pilot_records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SnapshotIntegrityError(
                    f"{config.pilot_works_path}:{line_number}: "
                    f"invalid JSON line ({exc.msg})"
                ) from None
    if not pilot_records:
        raise SnapshotIntegrityError("Pilot works file is empty")

    plan = config.plan(pilot_records)
    fingerprint = _sha256_json(plan)
    pilot_manifest = _read_json(pilot_manifest_path)
    pilot_sha = pilot_manifest.get("artifacts", {}).get("works_jsonl", {}).get("sha256")
    measured_pilot_sha = _sha256_file(config.pilot_works_path)
    if pilot_sha and pilot_sha != measured_pilot_sha:
        raise SnapshotIntegrityError(
            "Pilot works file does not match the pinned pilot manifest "
            f"({pilot_sha} != {measured_pilot_sha})"
        )

    manifest = {
        "schema_version": CORE_SCHEMA_VERSION,
        "task_id": CORE_TASK_ID,
        "dataset": "OpenAlex",
        "snapshot_id": f"openalex-core-{fingerprint[:12]}",
        "snapshot_kind": "immutable_local_extraction_from_live_api",
        "status": "PLANNED",
        "planned_at": _iso((clock or (lambda: datetime.now(timezone.utc)))()),
        "query_fingerprint": fingerprint,
        "sampling_plan": plan,
        "pilot_input": {
            "manifest_path": _display_path(pilot_manifest_path),
            "manifest_sha256": _sha256_file(pilot_manifest_path),
            "works_path": _display_path(config.pilot_works_path),
            "works_sha256": measured_pilot_sha,
        },
        "source": {
            "provider": "OpenAlex",
            "endpoint": config.endpoint,
            "api_documentation": OPENALEX_API_DOCS_URL,
            "license": "CC0",
            "license_url": OPENALEX_LICENSE_URL,
            "authentication": "anonymous_or_bearer_header; credential_not_persisted",
        },
        "id_namespace": {
            "raw": "OpenAlex URI, e.g. https://openalex.org/W123",
            "canonical_mapping": "strip URI prefix and prepend openalex:, e.g. openalex:W123",
        },
        "artifacts": {},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(manifest_path, manifest)
    return manifest


# ---------------------------------------------------------------------------
# SG-015 extension plan (v2): historical depth for the novel-candidate floor.
#
# The v1 gate measurement may show that a few OLD eligible sources have a
# novel-candidate universe below the pinned floor of 100 (universe =
# cumulative works with year <= source year, minus self, minus the source's
# distinct internal references).  The extension recruits additional works from
# the SAME pinned pilot topic (filter topics.id:<pilot topic>) in older
# publication-year buckets, which raises the cumulative candidate pool for
# every eligible source without touching any floor and without changing the
# v1 plan.  The extension plan is pinned (fingerprint) BEFORE its fetch and
# records the v1 gate evidence as its reason — nothing is silent.
# ---------------------------------------------------------------------------

_CORE_EXT_CANDIDATE_FIRST_YEARS = tuple(range(1972, 1964, -1))  # 1972 down to 1965
_CORE_EXT_LAST_YEAR = 1979
_CORE_EXT_MIN_FIRST_YEAR_CUM = 180  # new-cum bound at the first bucket year
_CORE_EXT_MAX_SAMPLE_PER_BUCKET = 200
_CORE_EXT_WORKS_PER_WORK_REFS_BOUND = 79  # see safety note in the plan


def _extension_candidate_universe_stats(
    raw_records: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, int], dict[int, int]]:
    """Return (cumulative works per year, {year: min below-floor universe}).

    Mirrors the Protocol v1 track-B eligibility and novel-candidate-universe
    definitions (the same formulas the frozen SG-014 gate applies) so the
    extension plan can prove sufficiency before any fetch.
    """

    canonical_years: dict[str, int] = {}
    for record in raw_records:
        try:
            bare = _bare_work_id(record["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotIntegrityError(str(exc)) from exc
        year = record.get("publication_year")
        if _valid_core_year(year):
            canonical_years[bare] = year
    id_set = set(canonical_years)
    per_year: dict[int, int] = {}
    for year in canonical_years.values():
        per_year[year] = per_year.get(year, 0) + 1
    cumulative: dict[int, int] = {}
    running = 0
    for year in sorted(per_year):
        running += per_year[year]
        cumulative[year] = running

    min_universe_by_year: dict[int, int] = {}
    for record in raw_records:
        try:
            bare = _bare_work_id(record["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotIntegrityError(str(exc)) from exc
        source_year = record.get("publication_year")
        title = record.get("title")
        if (
            not _valid_core_year(source_year)
            or title is None
            or not str(title).strip()
            or not record.get("abstract_inverted_index")
        ):
            continue
        refs = record.get("referenced_works") if "referenced_works" in record else None
        if refs is None:
            refs = []
        if not isinstance(refs, list):
            raise SnapshotIntegrityError("'referenced_works' must be a list")
        eligible_refs = 0
        seen: set[str] = set()
        for target in refs:
            try:
                target_bare = _bare_work_id(target)
            except ValueError as exc:
                raise SnapshotIntegrityError(str(exc)) from exc
            if target_bare == bare or target_bare in seen or target_bare not in id_set:
                continue
            target_year = canonical_years.get(target_bare)
            if target_year is not None and target_year <= source_year:
                eligible_refs += 1
                seen.add(target_bare)
        if eligible_refs >= 2:
            universe = cumulative[source_year] - 1 - eligible_refs
            if universe < 100:
                current = min_universe_by_year.get(source_year)
                min_universe_by_year[source_year] = (
                    universe if current is None else min(current, universe)
                )
    return cumulative, min_universe_by_year


def resolve_extension_buckets(
    v1_cumulative: Mapping[int, int],
    pool_counts: Mapping[int, int],
    below_minimum_universes: Mapping[int, int],
    *,
    global_work_cap: int,
    current_works: int,
) -> dict[str, Any]:
    """Resolve the extension bucket list and prove its sufficiency arithmetically.

    Fatal (raises) when no first bucket year can reach the safety bound or the
    projected total would exceed the pinned global work cap — the extension is
    then impossible and must not be executed.
    """

    missing_pools = [
        year
        for year in range(min(_CORE_EXT_CANDIDATE_FIRST_YEARS), _CORE_EXT_LAST_YEAR + 1)
        if year not in pool_counts
    ]
    if missing_pools:
        raise SnapshotIntegrityError(
            f"Extension pool counts missing for years: {missing_pools}"
        )
    chosen_first_year = None
    for candidate in _CORE_EXT_CANDIDATE_FIRST_YEARS:  # 1972 down to 1965
        sample = min(pool_counts[candidate], _CORE_EXT_MAX_SAMPLE_PER_BUCKET)
        if v1_cumulative.get(candidate, 0) + sample >= _CORE_EXT_MIN_FIRST_YEAR_CUM:
            chosen_first_year = candidate
            break
    if chosen_first_year is None:
        raise SnapshotIntegrityError(
            "No first extension year in "
            f"{_CORE_EXT_CANDIDATE_FIRST_YEARS[0]}..{_CORE_EXT_CANDIDATE_FIRST_YEARS[-1]} "
            f"reaches cumulative >= {_CORE_EXT_MIN_FIRST_YEAR_CUM} with the probed "
            "topic pools; the novel-candidate floor cannot be proven fixable"
        )
    buckets = {
        year: min(pool_counts[year], _CORE_EXT_MAX_SAMPLE_PER_BUCKET)
        for year in range(chosen_first_year, _CORE_EXT_LAST_YEAR + 1)
    }
    total_added = sum(buckets.values())
    projected_total = current_works + total_added
    if projected_total > global_work_cap:
        raise SnapshotIntegrityError(
            f"Extension would reach {projected_total} works, exceeding the pinned "
            f"global cap {global_work_cap}"
        )

    def new_cumulative(year: int) -> int:
        return v1_cumulative.get(year, 0) + sum(
            count for bucket_year, count in buckets.items() if bucket_year <= year
        )

    fixes: dict[str, Any] = {}
    for year, old_universe in sorted(below_minimum_universes.items()):
        if year < chosen_first_year:
            raise SnapshotIntegrityError(
                f"Below-floor eligible source at year {year} predates the earliest "
                f"extension bucket {chosen_first_year}; the floor cannot be fixed"
            )
        old_cumulative = v1_cumulative.get(year, 0)
        new_universe = new_cumulative(year) - old_cumulative + old_universe
        fixes[str(year)] = {
            "old_universe": old_universe,
            "old_cumulative": old_cumulative,
            "new_cumulative_lower_bound": new_cumulative(year),
            "new_universe_lower_bound": new_universe,
            "satisfied": new_universe >= 100,
        }
        if new_universe < 100:
            raise SnapshotIntegrityError(
                f"Extension cannot lift the year-{year} source universe to the "
                f"floor 100 (lower bound {new_universe})"
            )
    first_year_cum = new_cumulative(chosen_first_year)
    if first_year_cum - 1 - _CORE_EXT_WORKS_PER_WORK_REFS_BOUND < 100:
        raise SnapshotIntegrityError(
            "First extension year cumulative is too small to absorb a heavily "
            "citing eligible source"
        )
    return {
        "first_year": chosen_first_year,
        "year_buckets": {str(year): count for year, count in sorted(buckets.items())},
        "max_new_works": total_added,
        "projected_total_works": projected_total,
        "safety_verification": {
            "rule": (
                "universe_new = cumulative_new - 1 - distinct internal references; "
                "recruited bucket years raise the cumulative pool for every eligible "
                "source with a later-or-equal publication year"
            ),
            "first_year_cumulative_lower_bound": first_year_cum,
            "max_internal_refs_absorbed_at_first_year": first_year_cum - 101,
            "below_floor_year_fixes": fixes,
            "assumption": (
                "recruited works may themselves become eligible only at years >= "
                f"{chosen_first_year}, where the cumulative lower bound {first_year_cum} "
                f"absorbs up to {first_year_cum - 101} distinct internal references per "
                "source; no new eligible source can appear below the first bucket year "
                "because recruitment cannot add references to older works"
            ),
        },
    }


def _probe_pool_counts(
    downloader: "OpenAlexCoreDownloader", topic_id: str, years: Sequence[int]
) -> dict[int, int]:
    """Measure topic pool sizes per year (planning metadata, no record data)."""

    pools: dict[int, int] = {}
    for year in years:
        if downloader.config.request_interval_seconds:
            downloader._sleeper(downloader.config.request_interval_seconds)
        payload, _ = downloader._request_works(
            {
                "filter": f"topics.id:{topic_id},publication_year:{year}",
                "per_page": 1,
                "page": 1,
                "select": "id",
                "mailto": downloader.config.mailto,
            }
        )
        count = payload.get("meta", {}).get("count")
        if not isinstance(count, int) or count < 0:
            raise OpenAlexAPIError(
                f"Pool probe for year {year} returned no usable meta.count"
            )
        pools[year] = count
    return pools


def write_core_plan_v2(
    *,
    config: OpenAlexCoreConfig,
    manifest_path: Path,
    gate_report_path: Path,
    client: httpx.Client | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Pin the extension (v2) plan into the manifest BEFORE its fetch.

    Requires: the core manifest is COMPLETED (v1 pipeline done), no v2 plan
    yet, and the v1 gate report measured overall=NO_GO (an extension after a
    GO would be unjustified and is refused).  Pool sizes are probed live and
    pinned into the plan together with the sufficiency arithmetic.
    """

    manifest = _read_json(manifest_path) if manifest_path.exists() else None
    if manifest is None or manifest.get("status") != "COMPLETED":
        found = "missing file" if manifest is None else repr(manifest.get("status"))
        raise SnapshotIntegrityError(
            "Extension planning requires a COMPLETED core manifest "
            f"(found {found})"
        )
    if "sampling_plan_v2" in manifest:
        raise SnapshotIntegrityError(
            "Extension plan already pinned in this manifest; refusing to overwrite"
        )
    if not gate_report_path.is_file():
        raise SnapshotIntegrityError(
            f"v1 gate report is missing: {gate_report_path}"
        )
    gate_report = json.loads(gate_report_path.read_text(encoding="utf-8"))
    gate_overall = gate_report.get("decision", {}).get("overall")
    if gate_overall != "NO_GO":
        raise SnapshotIntegrityError(
            "Refusing to plan an extension: the v1 gate overall is "
            f"{gate_overall!r}, not NO_GO"
        )

    raw_entry = manifest.get("artifacts", {}).get("raw_works_jsonl", {})
    raw_path = Path(raw_entry.get("path", ""))
    if not raw_path.is_file() or _sha256_file(raw_path) != raw_entry.get("sha256"):
        raise SnapshotIntegrityError(
            f"Raw works file missing or hash mismatch: {raw_path}"
        )
    raw_records: list[dict[str, Any]] = []
    with raw_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                raw_records.append(json.loads(line))

    pilot_manifest_path = Path(manifest["pilot_input"]["manifest_path"])
    pilot_manifest = _read_json(pilot_manifest_path)
    pilot_filter = pilot_manifest.get("selection", {}).get("filter", "")
    if not pilot_filter.startswith("topics.id:"):
        raise SnapshotIntegrityError(
            f"Pilot manifest selection.filter is not a topic filter: {pilot_filter!r}"
        )
    topic_id = pilot_filter.split(":", 1)[1].strip()

    v1_cumulative, below_minimum = _extension_candidate_universe_stats(raw_records)
    if not below_minimum:
        raise SnapshotIntegrityError(
            "No below-floor eligible sources found; an extension is unjustified"
        )

    current_works = int(
        manifest.get("execution", {}).get("snapshot_composition", {}).get(
            "total_unique_works", len(raw_records)
        )
    )
    with OpenAlexCoreDownloader(
        config,
        manifest_path.parent / ".extension_probe",
        manifest_path,
        client=client,
        sleeper=sleeper,
        clock=clock,
    ) as downloader:
        pool_counts = _probe_pool_counts(
            downloader, topic_id, range(1965, _CORE_EXT_LAST_YEAR + 1)
        )
    resolution = resolve_extension_buckets(
        v1_cumulative,
        pool_counts,
        below_minimum,
        global_work_cap=config.global_work_cap,
        current_works=current_works,
    )

    plan_v2 = {
        "version": 2,
        "strategy": "historical_depth_extension_for_novel_candidate_floor",
        "reason": (
            "The v1 gate measured minimum_novel_candidates_per_source = NO_GO: "
            f"{sum(1 for _ in below_minimum)} eligible source(s) below the pinned "
            "floor of 100 novel candidates.  The extension recruits additional "
            "works from the SAME pinned pilot topic in older publication-year "
            "buckets, raising the cumulative candidate pool for every eligible "
            "source.  Floors are unchanged; the v1 plan and its records are "
            "untouched."
        ),
        "v1_gate_evidence": {
            "report_path": _display_path(gate_report_path),
            "report_sha256": _sha256_file(gate_report_path),
            "overall": gate_overall,
            "measured_at": gate_report.get("measured_at"),
        },
        "recruitment": {
            "filter_template": f"topics.id:{topic_id},publication_year:<Y>",
            "topic_id": topic_id,
            "topic_source": (
                "reused verbatim from the pinned pilot manifest selection.filter"
            ),
            "first_year": resolution["first_year"],
            "last_year": _CORE_EXT_LAST_YEAR,
            "year_buckets": resolution["year_buckets"],
            "sample_seed": config.sample_seed,
            "per_page": config.per_page,
            "paging": "single_page_per_year_bucket",
            "bucket_order": "ascending publication year (oldest first for cap-stop)",
            "empty_bucket_policy": "recorded and skipped (buckets are depth padding)",
            "probe": {
                "probed_years": sorted(pool_counts),
                "pool_counts": {
                    str(year): pool_counts[year] for year in sorted(pool_counts)
                },
                "note": (
                    "pool counts are per-year planning metadata (per_page=1, "
                    "select=id); no record data entered the snapshot during probing"
                ),
            },
        },
        "budget": {
            "max_new_works": resolution["max_new_works"],
            "projected_total_works": resolution["projected_total_works"],
            "global_work_cap": config.global_work_cap,
        },
        "dedup_priority": (
            "v1 snapshot records win; extension duplicates are dropped and counted"
        ),
        "invariants": {
            "floors": {
                "minimum_test_queries": 50,
                "minimum_dev_queries": 30,
                "minimum_eligible_references": 2,
                "minimum_novel_candidates_per_query": 100,
            },
            "qrels_used": False,
            "beir_data_used_for_sampling": False,
            "v1_plan_untouched": True,
        },
        "safety_verification": resolution["safety_verification"],
    }
    fingerprint_v2 = _sha256_json(plan_v2)

    updated = dict(manifest)
    updated["sampling_plan_v2"] = plan_v2
    updated["v2_fingerprint"] = fingerprint_v2
    updated["planned_v2_at"] = _iso((clock or (lambda: datetime.now(timezone.utc)))())
    updated["status"] = "EXTEND_PLANNED"
    _atomic_write_json(manifest_path, updated)
    return updated


# ---------------------------------------------------------------------------
# SG-015 CLI
# ---------------------------------------------------------------------------

def _core_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SG-015 OpenAlex core snapshot: plan, fetch, postprocess"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(target: argparse.ArgumentParser) -> None:
        target.add_argument("--pilot-works", type=Path,
                            default=Path("data/raw/openalex/works.jsonl"))
        target.add_argument("--pilot-manifest", type=Path,
                            default=Path("data/manifests/openalex_pilot.json"))
        target.add_argument("--manifest", type=Path,
                            default=Path("data/manifests/openalex_core.json"))
        target.add_argument("--endpoint", default=OPENALEX_API_URL)
        target.add_argument("--mailto", default=CORE_DEFAULT_MAILTO)
        target.add_argument("--sample-seed", default="20260915")
        target.add_argument("--candidate-hub-count", type=int, default=120)
        target.add_argument("--hub-id-batch-size", type=int, default=100)
        target.add_argument("--active-hub-max-year", type=int, default=2019)
        target.add_argument("--active-hub-cap", type=int, default=100)
        target.add_argument("--cohort-years", default="2020,2021,2022,2023,2024,2025")
        target.add_argument(
            "--cohort-year-order", default="2024,2023,2025,2022,2021,2020"
        )
        target.add_argument("--per-year-sample-cap", type=int, default=2500)
        target.add_argument("--global-work-cap", type=int, default=20000)
        target.add_argument("--minimum-snapshot-works", type=int, default=10000)
        target.add_argument("--per-page", type=int, default=200)
        target.add_argument("--request-interval", type=float, default=0.15)

    plan_parser = sub.add_parser("plan", help="pin the sampling plan (no network)")
    add_common(plan_parser)

    extend_parser = sub.add_parser(
        "extend-plan",
        help="pin the v2 historical-depth extension plan (probes pool counts)",
    )
    add_common(extend_parser)
    extend_parser.add_argument(
        "--gate-report", type=Path,
        default=Path("artifacts/reports/graph_feasibility_core.json"),
    )

    fetch_parser = sub.add_parser("fetch", help="fetch (or resume) the pinned plan")
    add_common(fetch_parser)
    fetch_parser.add_argument("--raw-dir", type=Path,
                              default=Path("data/raw/openalex_core"))
    fetch_parser.add_argument("--api-key", default=None,
                              help="optional; defaults to OPENALEX_API_KEY env (never persisted)")

    post_parser = sub.add_parser("postprocess", help="normalize + quality report")
    post_parser.add_argument("--manifest", type=Path,
                             default=Path("data/manifests/openalex_core.json"))
    post_parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/openalex_core"))
    post_parser.add_argument("--processed-dir", type=Path,
                             default=Path("data/processed/openalex"))
    post_parser.add_argument("--quality-report", type=Path,
                             default=Path("artifacts/reports/openalex_quality.json"))
    return parser


def _core_config_from_args(args: argparse.Namespace) -> OpenAlexCoreConfig:
    years = tuple(int(value) for value in str(args.cohort_years).split(",") if value.strip())
    order = tuple(
        int(value) for value in str(args.cohort_year_order).split(",") if value.strip()
    )
    return OpenAlexCoreConfig(
        pilot_works_path=args.pilot_works,
        endpoint=args.endpoint,
        mailto=args.mailto,
        sample_seed=args.sample_seed,
        candidate_hub_count=args.candidate_hub_count,
        hub_id_batch_size=args.hub_id_batch_size,
        active_hub_max_year=args.active_hub_max_year,
        active_hub_cap=args.active_hub_cap,
        cohort_years=years,
        cohort_year_order=order,
        per_year_sample_cap=args.per_year_sample_cap,
        global_work_cap=args.global_work_cap,
        minimum_snapshot_works=args.minimum_snapshot_works,
        per_page=args.per_page,
        request_interval_seconds=args.request_interval,
    )


def core_main(argv: Sequence[str] | None = None) -> int:
    """CLI entry for the SG-015 core pipeline; returns a process exit code."""

    args = _core_parser().parse_args(list(argv) if argv is not None else None)
    command_argv = list(argv) if argv is not None else sys.argv[1:]
    try:
        if args.command == "plan":
            config = _core_config_from_args(args)
            manifest = write_core_plan(
                config=config,
                manifest_path=args.manifest,
                pilot_manifest_path=args.pilot_manifest,
            )
            print(
                f"Pinned plan {manifest['snapshot_id']} "
                f"(fingerprint {manifest['query_fingerprint'][:12]}); "
                f"{len(manifest['sampling_plan']['hub_selection']['hub_candidates'])} "
                "hub candidates; cohort years "
                f"{manifest['sampling_plan']['cohort_selection']['year_order']}"
            )
            return 0
        if args.command == "extend-plan":
            config = _core_config_from_args(args)
            manifest = write_core_plan_v2(
                config=config,
                manifest_path=args.manifest,
                gate_report_path=args.gate_report,
            )
            plan_v2 = manifest["sampling_plan_v2"]
            print(
                f"Pinned extension plan v{plan_v2['version']} "
                f"(fingerprint {manifest['v2_fingerprint'][:12]}); buckets "
                f"{plan_v2['recruitment']['first_year']}-"
                f"{plan_v2['recruitment']['last_year']} "
                f"(max +{plan_v2['budget']['max_new_works']} works)"
            )
            return 0
        if args.command == "fetch":
            config = _core_config_from_args(args)
            api_key = args.api_key if args.api_key else os.environ.get("OPENALEX_API_KEY")
            with OpenAlexCoreDownloader(
                config, args.raw_dir, args.manifest, api_key=api_key
            ) as downloader:
                manifest = downloader.fetch()
            counts = manifest.get("execution", {}).get("snapshot_composition", {})
            if manifest.get("execution_extension"):
                counts = {"total_unique_works": manifest["execution_extension"]["total_unique_works"]}
            print(
                f"Fetched {manifest.get('snapshot_id')}: "
                f"{counts.get('total_unique_works')} unique works "
                f"({manifest.get('status')})"
            )
            return 0
        if args.command == "postprocess":
            exit_code, manifest = run_core_postprocess(
                manifest_path=args.manifest,
                raw_dir=args.raw_dir,
                processed_dir=args.processed_dir,
                quality_report_path=args.quality_report,
                command=command_argv,
            )
            if exit_code != 0:
                for error in manifest.get("errors", []):
                    print(f"CORE POSTPROCESS FAILED: {error}", file=sys.stderr)
                return 1
            print(
                f"Postprocessed {manifest.get('snapshot_id')}: "
                f"{manifest.get('postprocess', {}).get('processed_works')} works; "
                f"report={args.quality_report}"
            )
            return 0
        raise SnapshotIntegrityError(f"Unknown core command: {args.command}")  # pragma: no cover
    except (OpenAlexError, SnapshotIntegrityError, ValueError) as exc:
        print(f"CORE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    _argv = sys.argv[1:]
    if _argv and _argv[0] == "core":
        raise SystemExit(core_main(_argv[1:]))
    raise SystemExit(main())
