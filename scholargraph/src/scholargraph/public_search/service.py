"""Online public-paper search orchestration for EXT-05B.

The service owns request validation, source fan-out, snapshot/cache lifecycle,
and the frozen envelope truth table. Adapters, transport, fusion, and storage
remain separate testable boundaries; no offline corpus is consulted.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from . import arxiv, openalex
from .contracts import (
    CONTRACT_VERSION, FusionResult, PublicSearchConfig, SearchEnvelope, SearchError,
    SearchRequest, SearchSnapshot, SourceResult, cache_key, digest, error_http_status,
    load_config, overall_status,
)
from .fusion import FusionError, fuse
from .store import StoreError, SQLiteStore, initialize_store, open_existing
from .transport import RateState, Transport, TransportError, TransportResponse


class ServiceError(RuntimeError):
    """Structured boundary failure; the message is fixed and secret-free."""

    def __init__(self, error: SearchError):
        self.error = error
        super().__init__(error.message)


def _error(kind: str, message: str, source=None) -> SearchError:
    allowed = {"request", "config", "policy", "auth", "quota", "timeout",
               "upstream", "schema", "storage"}
    if kind not in allowed:
        kind = "config"
    return SearchError(kind=kind, message=message, source=source,
                       retry_after_seconds=None, record_index=None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _RecordingTransport:
    """Transport proxy retaining exact response bytes for store.save_snapshot."""

    def __init__(self, inner: Transport):
        self._inner = inner
        self._raw: dict[str, bytes] = {}
        self._lock = threading.Lock()

    @property
    def clock(self):
        return self._inner.clock

    @property
    def wall_clock(self):
        return self._inner.wall_clock

    def deadline(self) -> float:
        return self._inner.deadline()

    def get(self, source, params, *, deadline: float) -> TransportResponse:
        response = self._inner.get(source, params, deadline=deadline)
        raw_id = f"{source}-{response.sha256}"
        with self._lock:
            previous = self._raw.get(raw_id)
            if previous is not None and previous != response.body:
                raise TransportError(_error("schema", "duplicate raw response hash", source))
            self._raw[raw_id] = response.body
        return response

    def close(self):
        return self._inner.close()

    @property
    def raw_payloads(self) -> dict[str, bytes]:
        with self._lock:
            return dict(self._raw)


def _adapter_hash(module_file: Path) -> str:
    try:
        return hashlib.sha256(module_file.read_bytes()).hexdigest()
    except OSError:
        raise ServiceError(_error("config", "adapter source unavailable")) from None


class PublicSearchService:
    """Service using only the selected online adapters and initialized store."""

    def __init__(
        self,
        project_root: Path | str,
        config_path: Path | str | None = None,
        *,
        store=None,
        adapters: Mapping[str, Callable] | None = None,
        transport_factory: Callable | None = None,
        store_factory: Callable | None = None,
        clock: Callable[[], datetime] = _now,
        rate_state: RateState | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        path = Path(config_path) if config_path is not None else self.project_root / "configs" / "public_search.json"
        try:
            self.config = load_config(path)
        except (OSError, ValueError, TypeError):
            raise ServiceError(_error("config", "invalid or missing public search config")) from None
        self.config_path = path
        self._clock = clock
        self._rate_state = RateState() if rate_state is None else rate_state
        self._adapters = dict(adapters) if adapters is not None else {
            "openalex": openalex.search,
            "arxiv": arxiv.search,
        }
        for source in ("openalex", "arxiv"):
            if source not in self._adapters or not callable(self._adapters[source]):
                raise ServiceError(_error("config", "required source adapter unavailable", source))
            if not self.config.sources[source].source_policy_verified:
                raise ServiceError(_error("policy", "source policy not verified", source))
        self._transport_factory = transport_factory if transport_factory is not None else self._make_transport
        if store is not None:
            self.store = store
        else:
            factory = store_factory if store_factory is not None else open_existing
            try:
                self.store = factory(self.project_root, self.config)
            except StoreError as exc:
                raise ServiceError(exc.error) from None
            except (OSError, ValueError, TypeError):
                raise ServiceError(_error("storage", "public search store unavailable")) from None
        self._adapter_hashes = {
            "openalex": _adapter_hash(Path(openalex.__file__).resolve()),
            "arxiv": _adapter_hash(Path(arxiv.__file__).resolve()),
        }

    def _make_transport(self, config: PublicSearchConfig):
        return Transport(config, rate_state=self._rate_state)

    def close(self) -> None:
        try:
            self.store.close()
        except StoreError as exc:
            raise ServiceError(exc.error) from None

    def initialize_storage(self):
        try:
            return initialize_store(self.project_root, self.config)
        except StoreError as exc:
            raise ServiceError(exc.error) from None

    def _request(self, value: SearchRequest | Mapping) -> SearchRequest:
        try:
            if isinstance(value, SearchRequest):
                raw = value.model_dump(mode="json")
            elif isinstance(value, Mapping):
                raw = dict(value)
            else:
                raise TypeError()
            return SearchRequest.model_validate(json.loads(json.dumps(raw, allow_nan=False)))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ServiceError(_error("request", "invalid public search request")) from None

    def _make_envelope(self, overall: str, snapshot, errors, *, stale=False, cached=False) -> SearchEnvelope:
        try:
            return SearchEnvelope(schema_version=1, contract_version=CONTRACT_VERSION,
                                  overall=overall, snapshot=snapshot, errors=list(errors),
                                  stale=stale, cached=cached)
        except ValueError:
            raise ServiceError(_error("schema", "invalid public search envelope")) from None

    def _source_result(self, source: str, request: SearchRequest, transport) -> SourceResult:
        started = transport.clock()
        try:
            result = self._adapters[source](request, transport)
            raw = result.model_dump_json().encode("utf-8") if isinstance(result, SourceResult) else result
            result = SourceResult.model_validate_json(raw)
            if result.source != source:
                raise ValueError("source mismatch")
            return result
        except TransportError as exc:
            return SourceResult(source=source, status="failed", records=[], error=exc.error,
                                source_total=None, elapsed_seconds=max(0.0, transport.clock() - started), filter_coverage="none",
                                truncated=None, raw_references=[])
        except (ValueError, TypeError, AttributeError):
            return SourceResult(source=source, status="failed", records=[],
                                error=_error("schema", "invalid source result", source),
                                source_total=None, elapsed_seconds=max(0.0, transport.clock() - started), filter_coverage="none",
                                truncated=None, raw_references=[])

    def _snapshot(self, request: SearchRequest, results: list[SourceResult], fusion: FusionResult,
                  fetched_at: datetime) -> SearchSnapshot:
        overall = overall_status(results, request, len(fusion.hits))
        return SearchSnapshot(schema_version=1, contract_version=CONTRACT_VERSION,
                              snapshot_id="ps-" + uuid.uuid4().hex,
                              request=request, config_sha256=digest(self.config),
                              adapter_sha256={s: self._adapter_hashes[s] for s in request.sources},
                              source_results=results, fusion=fusion, overall=overall,
                              fetched_at=fetched_at,
                              expires_at=fetched_at + timedelta(seconds=self.config.cache_ttl_seconds))

    def _save(self, snapshot: SearchSnapshot, raw_payloads: dict[str, bytes], key: str) -> None:
        try:
            self.store.save_snapshot(snapshot, raw_payloads, cache_key=key)
        except StoreError as exc:
            raise ServiceError(exc.error) from None

    def search(self, value: SearchRequest | Mapping) -> SearchEnvelope:
        request = self._request(value)
        selected = tuple(request.sources)
        try:
            key = cache_key(request, self.config,
                            {s: self._adapter_hashes[s] for s in selected})
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ServiceError(_error("config", "service clock must include timezone"))
            if not request.refresh:
                cached_snapshot = self.store.load_cache(key, now=now)
                if cached_snapshot is not None:
                    return self._make_envelope(cached_snapshot.overall, cached_snapshot, [], cached=True)
        except StoreError as exc:
            raise ServiceError(exc.error) from None
        except ServiceError:
            raise
        except (ValueError, TypeError):
            raise ServiceError(_error("storage", "cache lookup failed")) from None

        transport = None
        try:
            transport = _RecordingTransport(self._transport_factory(self.config))
            # One transport/deadline is shared by all source futures. Two is the
            # bounded maximum in the frozen MVP source set.
            results_by_source = {}
            with ThreadPoolExecutor(max_workers=len(selected), thread_name_prefix="public-search") as pool:
                futures = {pool.submit(self._source_result, source, request, transport): source for source in selected}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        results_by_source[source] = future.result()
                    except Exception:
                        results_by_source[source] = SourceResult(
                            source=source, status="failed", records=[],
                            error=_error("schema", "source execution failed", source),
                            source_total=None, elapsed_seconds=None, filter_coverage="none",
                            truncated=None, raw_references=[])
            results = [results_by_source[s] for s in selected]
            fusion = fuse(results, request)
            fetched = self._clock()
            snapshot = self._snapshot(request, results, fusion, fetched)
            errors = [result.error for result in results if result.error is not None]
            self._save(snapshot, transport.raw_payloads, key)
            return self._make_envelope(snapshot.overall, snapshot, errors,
                                       cached=False, stale=False)
        except FusionError as exc:
            raise ServiceError(exc.error) from None
        except StoreError as exc:
            raise ServiceError(exc.error) from None
        except ServiceError:
            raise
        except (ValueError, TypeError, OSError):
            raise ServiceError(_error("schema", "public search failed")) from None
        finally:
            if transport is not None:
                try:
                    transport.close()
                except StoreError as exc:
                    raise ServiceError(exc.error) from None
                except Exception:
                    raise ServiceError(_error("storage", "public search transport close failed")) from None

    def results(self, snapshot_id: str) -> SearchEnvelope:
        try:
            snapshot = self.store.read_snapshot(snapshot_id)
            now = self._clock()
            stale = now >= snapshot.expires_at
            errors = [result.error for result in snapshot.source_results if result.error is not None]
            return self._make_envelope(snapshot.overall, snapshot, errors,
                                       stale=stale, cached=snapshot.overall in {"success", "empty"})
        except StoreError as exc:
            raise ServiceError(exc.error) from None
        except (ValueError, TypeError):
            raise ServiceError(_error("request", "invalid or missing snapshot")) from None

    def save_paper(self, snapshot_id: str, canonical_id: str) -> object:
        try:
            return self.store.save_paper(snapshot_id, canonical_id, now=self._clock())
        except StoreError as exc:
            raise ServiceError(exc.error) from None

    def library(self, offset: int, limit: int) -> list:
        try:
            return self.store.list_library(offset=offset, limit=limit)
        except StoreError as exc:
            raise ServiceError(exc.error) from None

    def export_library(self, format: str) -> bytes:
        try:
            return self.store.export_library(format)
        except StoreError as exc:
            raise ServiceError(exc.error) from None
        except (ValueError, TypeError):
            raise ServiceError(_error("request", "invalid export format")) from None


# Short alias used by route/CLI integrations and kept explicit for callers.
SearchService = PublicSearchService


def status_for(error: SearchError) -> int:
    return error_http_status([error])
