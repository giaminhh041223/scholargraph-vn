"""Adversarial service tests; all responses and records are synthetic."""
from __future__ import annotations

import copy
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholargraph.public_search.contracts import (
    FusionCounts, FusionResult, FieldEvidence, PaperRecord, RawReference,
    SearchError, SearchRequest, SearchSnapshot, SourceResult, digest, load_config,
)
from scholargraph.public_search.service import PublicSearchService, ServiceError
from scholargraph.public_search.transport import Transport, TransportError

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
SHA = "a" * 64


def cfg(tmp_path, *, policy=True):
    row = json.loads((ROOT / "configs/public_search.json").read_text(encoding="utf-8"))
    row["data_root"] = "data/public_search/service-test"
    for source in row["sources"].values():
        source["source_policy_verified"] = policy
        source["policy_evidence_sha256"] = "a" * 64 if policy else None
    path = tmp_path / "config.json"
    path.write_text(json.dumps(row), encoding="utf-8")
    return path


def request(**changes):
    row = dict(query="synthetic query", sources=["openalex", "arxiv"], top_k=5,
               cap_per_source=5, year_from=None, year_to=None, refresh=False)
    row.update(changes)
    return SearchRequest.model_validate(row)


def paper(source="openalex", sid="W1", doi="10.1234/a"):
    nullable = ["abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
                "license", "open_access_status", "citation_count", "authors"]
    row = dict(source=source, source_id=sid, title="Synthetic title",
               landing_url="https://example.org/paper", retrieved_at=NOW,
               raw_sha256=SHA, parser_version="synthetic-1", abstract=None,
               publication_year=None, doi=doi, arxiv_id=None, venue=None, pdf_url=None,
               license=None, open_access_status=None, citation_count=None, authors=None,
               authors_availability="missing", missing_fields=[x for x in nullable if x != "doi"],
               field_provenance={})
    row["field_provenance"] = {"source_id": [dict(source=source, source_id=sid, raw_sha256=SHA, raw_field="id")],
                               "title": [dict(source=source, source_id=sid, raw_sha256=SHA, raw_field="title")],
                               "landing_url": [dict(source=source, source_id=sid, raw_sha256=SHA, raw_field="url")],
                               "doi": [dict(source=source, source_id=sid, raw_sha256=SHA, raw_field="doi")]}
    return PaperRecord.model_validate(row)


def source(source, status="empty", records=None, error=None):
    records = [] if records is None else records
    refs = [RawReference(raw_id=source + "-" + SHA, sha256=SHA, byte_count=0)] if records else []
    return SourceResult(source=source, status=status, records=records, error=error,
                        source_total=len(records) if status in {"success", "empty"} else None,
                        elapsed_seconds=0.01, filter_coverage="none", truncated=False,
                        raw_references=refs)


class MemoryStore:
    def __init__(self):
        self.snapshots = {}
        self.cache = {}
        self.saved = []
        self.closed = False
        self.calls = []

    def load_cache(self, key, *, now):
        self.calls.append(("load_cache", key))
        snap = self.cache.get(key)
        return snap if snap is not None and now < snap.expires_at else None

    def save_snapshot(self, snapshot, raw_payloads, *, cache_key):
        self.calls.append(("save_snapshot", snapshot.overall))
        self.snapshots[snapshot.snapshot_id] = snapshot
        if snapshot.overall in {"success", "empty"}:
            self.cache[cache_key] = snapshot

    def read_snapshot(self, snapshot_id):
        if snapshot_id not in self.snapshots:
            from scholargraph.public_search.store import StoreError
            raise StoreError(SearchError(kind="storage", message="snapshot missing", source=None,
                                         retry_after_seconds=None, record_index=None))
        return self.snapshots[snapshot_id]

    def save_paper(self, snapshot_id, canonical_id, *, now):
        snap = self.read_snapshot(snapshot_id)
        for hit in snap.fusion.hits:
            if hit.canonical_id == canonical_id:
                from scholargraph.public_search.contracts import LibraryEntry
                entry = LibraryEntry(canonical_id=canonical_id, snapshot_id=snapshot_id,
                                     saved_at=now, hit=hit, incomplete_sources=snap.overall == "partial_failure")
                self.saved.append(entry)
                return entry
        from scholargraph.public_search.store import StoreError
        raise StoreError(SearchError(kind="request", message="unknown hit", source=None,
                                     retry_after_seconds=None, record_index=None))

    def list_library(self, *, offset, limit):
        return self.saved[offset:offset + limit]

    def export_library(self, format):
        from scholargraph.public_search.export import export_library_bytes
        return export_library_bytes(self.saved, format)

    def close(self):
        self.closed = True


def adapters_for(calls, *, failed=False, empty=False):
    def make(source):
        def adapter(req, transport):
            calls.append((source, id(transport), transport.deadline()))
            if failed:
                return source_result_failed(source)
            if empty:
                return source_result_empty(source)
            return source_result_success(source)
        return adapter
    return {"openalex": make("openalex"), "arxiv": make("arxiv")}


def source_result_success(name):
    return source(name, "success", [paper(name, "W-" + name, "10.1234/" + name)])


def source_result_failed(name):
    return source(name, "failed", error=SearchError(kind="timeout", message="synthetic timeout", source=name,
                                                     retry_after_seconds=None, record_index=None))


def source_result_empty(name):
    return source(name, "empty")


def make_service(tmp_path, *, calls=None, store=None, adapters=None, policy=True, store_factory=None):
    return PublicSearchService(tmp_path, cfg(tmp_path, policy=policy), store=store or MemoryStore(),
                               adapters=adapters or adapters_for(calls if calls is not None else []),
                               store_factory=store_factory)


def test_parallel_sources_share_transport_and_deadline_and_snapshot(tmp_path):
    calls = []
    store = MemoryStore()
    service = make_service(tmp_path, calls=calls, store=store)
    envelope = service.search(request())
    assert envelope.overall == "success" and envelope.cached is False
    assert len(calls) == 2 and len({item[1] for item in calls}) == 1
    assert len({item[2] for item in calls}) == 1
    assert len(store.snapshots) == 1 and store.calls[-1][0] == "save_snapshot"


def test_cache_hit_skips_adapters_and_refresh_bypasses_cache(tmp_path):
    calls = []
    store = MemoryStore()
    service = make_service(tmp_path, calls=calls, store=store)
    first = service.search(request())
    calls.clear()
    cached = service.search(request())
    assert cached.cached and len(calls) == 0 and cached.snapshot.snapshot_id == first.snapshot.snapshot_id
    refreshed = service.search(request(refresh=True))
    assert not refreshed.cached and len(calls) == 2 and refreshed.snapshot.snapshot_id != first.snapshot.snapshot_id


def test_refresh_failure_does_not_return_stale_success(tmp_path):
    calls = []
    store = MemoryStore()
    good = make_service(tmp_path, calls=calls, store=store)
    good.search(request())
    bad = make_service(tmp_path, calls=calls, store=store,
                       adapters=adapters_for(calls, failed=True))
    result = bad.search(request(refresh=True))
    assert result.overall == "failed" and result.snapshot is not None and not result.cached


@pytest.mark.parametrize("states,overall", [
    (("empty", "empty"), "empty"), (("success", "empty"), "success"),
    (("success", "failed"), "partial_failure"), (("empty", "failed"), "partial_failure"),
    (("failed", "failed"), "failed")])
def test_truth_table(states, overall, tmp_path):
    calls = []
    def factory(source_name):
        def adapter(req, transport):
            state = states[0 if source_name == "openalex" else 1]
            if state == "success": return source_result_success(source_name)
            if state == "empty": return source(source_name, "empty")
            return source_result_failed(source_name)
        return adapter
    service = make_service(tmp_path, calls=calls, store=MemoryStore(),
                           adapters={"openalex": factory("openalex"), "arxiv": factory("arxiv")})
    envelope = service.search(request())
    assert envelope.overall == overall
    if "failed" in states:
        assert envelope.errors and not (envelope.overall in {"success", "empty"})


def test_mixed_error_http_priority_is_structured(tmp_path):
    from scholargraph.public_search.service import status_for
    assert status_for(SearchError(kind="timeout", message="x", source="openalex", retry_after_seconds=None, record_index=None)) == 504
    assert status_for(SearchError(kind="quota", message="x", source="openalex", retry_after_seconds=None, record_index=None)) == 503
    assert status_for(SearchError(kind="storage", message="x", source=None, retry_after_seconds=None, record_index=None)) == 500


def test_missing_policy_and_missing_existing_store_fail_without_fallback(tmp_path):
    with pytest.raises(ServiceError) as policy:
        make_service(tmp_path, policy=False)
    assert policy.value.error.kind == "policy"
    with pytest.raises(ServiceError) as missing:
        PublicSearchService(tmp_path, cfg(tmp_path), store_factory=lambda root, config: (_ for _ in ()).throw(
            __import__("scholargraph.public_search.store", fromlist=["StoreError"]).StoreError(
                SearchError(kind="storage", message="store not initialized", source=None,
                            retry_after_seconds=None, record_index=None))))
    assert missing.value.error.kind == "storage"


def test_malformed_adapter_result_fails_source_not_empty(tmp_path):
    def bad(req, transport):
        return {"source": "openalex", "status": "success", "records": [], "error": None,
                "source_total": 0, "elapsed_seconds": 0.1, "filter_coverage": "none",
                "truncated": False, "raw_references": []}
    service = make_service(tmp_path, store=MemoryStore(), adapters={"openalex": bad, "arxiv": lambda r, t: source("arxiv", "empty")})
    result = service.search(request())
    assert result.overall == "partial_failure" and result.errors[0].kind == "schema"


@pytest.mark.parametrize("failed_source", ["openalex", "arxiv"])
@pytest.mark.parametrize("year_from", [None, 2024])
@pytest.mark.parametrize("exception", [RuntimeError, OSError, TransportError])
def test_exception_preserves_healthy_source_and_measured_failure(tmp_path, failed_source, year_from, exception):
    secret = "secret-token-must-not-appear"
    healthy_source = "arxiv" if failed_source == "openalex" else "openalex"

    def bad(req, transport):
        time.sleep(0.01)
        if exception is TransportError:
            raise TransportError(SearchError(kind="timeout", message="synthetic timeout", source=failed_source,
                                             retry_after_seconds=None, record_index=None))
        raise exception(secret)

    def healthy(req, transport):
        result = source_result_success(healthy_source)
        row = result.records[0].model_dump()
        row["publication_year"] = 2024
        row["missing_fields"].remove("publication_year")
        row["field_provenance"]["publication_year"] = [dict(source=healthy_source,
            source_id=row["source_id"], raw_sha256=SHA, raw_field="year")]
        return result.model_copy(update={"records": [PaperRecord.model_validate(row)]})

    store = MemoryStore()
    service = make_service(tmp_path, store=store, adapters={failed_source: bad, healthy_source: healthy})
    started = time.perf_counter()
    envelope = service.search(request(year_from=year_from))
    duration = time.perf_counter() - started
    assert envelope.overall == "partial_failure"
    assert len(envelope.snapshot.fusion.hits) == 1
    assert envelope.snapshot.fusion.hits[0].display.source == healthy_source
    results = {r.source: r for r in envelope.snapshot.source_results}
    failed = results[failed_source]
    assert failed.status == "failed" and failed.records == []
    assert 0.01 <= failed.elapsed_seconds <= duration
    assert failed.filter_coverage == ("none" if year_from is None else
                                     "server" if failed_source == "openalex" else "bounded_pool")
    assert failed.error.kind == ("timeout" if exception is TransportError else "schema")
    assert results[healthy_source].status == "success"
    assert secret not in envelope.model_dump_json()
    assert store.snapshots[envelope.snapshot.snapshot_id] == envelope.snapshot
    assert store.cache == {}


def test_broken_transport_clock_is_measured_and_isolates_source(tmp_path):
    class BrokenClockTransport:
        def clock(self):
            time.sleep(0.01)
            raise RuntimeError("secret-clock-error")

        def close(self):
            self.closed = True

    transport = BrokenClockTransport()
    service = make_service(tmp_path, adapters={
        "openalex": lambda req, t: t.clock(),
        "arxiv": lambda req, t: source_result_success("arxiv"),
    })
    service._transport_factory = lambda config: transport
    result = service.search(request())
    assert result.overall == "partial_failure"
    assert len(result.snapshot.fusion.hits) == 1
    failed = next(row for row in result.snapshot.source_results if row.source == "openalex")
    assert failed.source == "openalex" and failed.status == "failed"
    assert failed.elapsed_seconds >= 0.01
    assert "secret-clock-error" not in result.model_dump_json()
    assert transport.closed


@pytest.mark.parametrize("readings", [
    [OSError("secret-start-error")], [1.0, OSError("secret-end-error")],
    [1.0, float("nan")], [2.0, 1.0],
])
def test_unmeasurable_failure_raises_explicit_service_error(tmp_path, monkeypatch, readings):
    import scholargraph.public_search.service as service_module

    values = iter(readings)
    def counter():
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    def bad(req, transport):
        raise RuntimeError("secret-adapter-error")

    store = MemoryStore()
    service = make_service(tmp_path, store=store, adapters={"openalex": bad, "arxiv": bad})
    monkeypatch.setattr(service_module.time, "perf_counter", counter)
    with pytest.raises(ServiceError) as failure:
        service.search(request(sources=["openalex"]))
    assert failure.value.error.kind == "config"
    assert failure.value.error.source == "openalex"
    assert failure.value.error.message == "source elapsed time measurement failed"
    assert store.snapshots == {} and store.cache == {}


def test_init_storage_uses_initialize_not_open_existing(tmp_path):
    service = make_service(tmp_path, store=MemoryStore())
    initialized = []
    fake = MemoryStore()
    service_module = __import__("scholargraph.public_search.service", fromlist=["initialize_store"])
    original = service_module.initialize_store
    service_module.initialize_store = lambda root, config: (initialized.append((root, config)) or fake)
    try:
        assert service.initialize_storage() is fake and initialized
    finally:
        service_module.initialize_store = original


def test_transport_close_failure_is_reported(tmp_path):
    class ClosingTransport:
        def clock(self):
            return 0.0

        def deadline(self):
            return 1.0

        def close(self):
            raise RuntimeError("close failed")

    service = make_service(tmp_path, store=MemoryStore(), adapters=adapters_for([]),
                           calls=[] , store_factory=None)
    service._transport_factory = lambda config: ClosingTransport()
    with pytest.raises(ServiceError) as failure:
        service.search(request())
    assert failure.value.error.kind == "storage"
