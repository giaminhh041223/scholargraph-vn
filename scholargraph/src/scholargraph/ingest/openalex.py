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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
