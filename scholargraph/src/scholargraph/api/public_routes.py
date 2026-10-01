"""FastAPI routes for online public paper search (EXT-05B)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from starlette.requests import Request

from scholargraph.public_search.contracts import (
    SearchEnvelope, SearchError, SearchRequest, error_http_status, unique_object,
)
from scholargraph.public_search.service import PublicSearchService, ServiceError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
router = APIRouter(prefix="/public", tags=["public-search"])
_service: PublicSearchService | None = None


def set_public_service(service: PublicSearchService | None) -> None:
    """Test/application hook; production still constructs through open_existing."""
    global _service
    _service = service


def get_public_service() -> PublicSearchService:
    global _service
    if _service is None:
        _service = PublicSearchService(PROJECT_ROOT)
    return _service


def _failure(exc: ServiceError) -> JSONResponse:
    envelope = SearchEnvelope(schema_version=1, contract_version="1.0.0", overall="failed",
                              snapshot=None, errors=[exc.error], stale=False, cached=False)
    return JSONResponse(status_code=error_http_status(envelope.errors),
                        content=jsonable_encoder(envelope))


def _success(envelope: SearchEnvelope) -> JSONResponse:
    return JSONResponse(status_code=error_http_status(envelope.errors),
                        content=jsonable_encoder(envelope))


def _integer(value: str | None, name: str) -> int:
    if value is None or not value or (value.startswith("-") and not value[1:].isdigit()) or not value.lstrip("-").isdigit():
        raise ValueError(f"invalid {name}")
    return int(value)


def _query_request(request: Request) -> SearchRequest:
    params = request.query_params
    query = params.get("query")
    if query is None:
        query = params.get("q")
    source_text = params.get("sources")
    sources = [part.strip() for part in source_text.split(",")] if source_text is not None else ["openalex", "arxiv"]
    top_k = _integer(params.get("top_k", "20"), "top_k")
    cap = _integer(params.get("cap_per_source", "50"), "cap_per_source")
    year_from = _integer(params.get("year_from"), "year_from") if params.get("year_from") is not None else None
    year_to = _integer(params.get("year_to"), "year_to") if params.get("year_to") is not None else None
    refresh_raw = params.get("refresh", "false").casefold()
    if refresh_raw not in {"true", "false"}:
        raise ValueError("invalid refresh")
    return SearchRequest(query=query, sources=sources, top_k=top_k, cap_per_source=cap,
                         year_from=year_from, year_to=year_to, refresh=refresh_raw == "true")


async def _body_request(request: Request) -> SearchRequest:
    raw = await request.body()
    if not raw:
        raise ValueError("missing request body")
    payload = json.loads(raw, object_pairs_hook=unique_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    if not isinstance(payload, dict):
        raise ValueError("request body must be object")
    return SearchRequest.model_validate(payload)


@router.get("", response_model=None)
def public_root() -> dict[str, Any] | JSONResponse:
    try:
        service = get_public_service()
        return {"status": "ready", "contract_version": service.config.contract_version,
                "sources": ["openalex", "arxiv"]}
    except ServiceError as exc:
        return _failure(exc)


@router.get("/search")
def public_search(request: Request) -> JSONResponse:
    try:
        return _success(get_public_service().search(_query_request(request)))
    except ServiceError as exc:
        return _failure(exc)
    except (ValueError, TypeError, json.JSONDecodeError):
        return _failure(ServiceError(SearchError(
            kind="request", message="invalid public search request", source=None,
            retry_after_seconds=None, record_index=None)))


@router.post("/search")
async def public_search_post(request: Request) -> JSONResponse:
    try:
        return _success(get_public_service().search(await _body_request(request)))
    except ServiceError as exc:
        return _failure(exc)
    except (ValueError, TypeError, json.JSONDecodeError):
        return _failure(ServiceError(SearchError(
            kind="request", message="invalid public search request", source=None,
            retry_after_seconds=None, record_index=None)))


@router.get("/results/{snapshot_id}")
def public_results(snapshot_id: str) -> JSONResponse:
    try:
        return _success(get_public_service().results(snapshot_id))
    except ServiceError as exc:
        return _failure(exc)


@router.get("/library")
def public_library(offset: str = "0", limit: str = "50") -> JSONResponse:
    try:
        entries = get_public_service().library(_integer(offset, "offset"), _integer(limit, "limit"))
        return JSONResponse(content={"contract_version": "1.0.0", "entries": jsonable_encoder(entries), "errors": []})
    except ServiceError as exc:
        return _failure(exc)


@router.post("/library")
async def public_library_save(request: Request) -> JSONResponse:
    try:
        payload = json.loads(await request.body(), object_pairs_hook=unique_object)
        if not isinstance(payload, dict) or set(payload) != {"snapshot_id", "canonical_id"}:
            raise ValueError("invalid library request")
        entry = get_public_service().save_paper(payload["snapshot_id"], payload["canonical_id"])
        return JSONResponse(status_code=200, content={"contract_version": "1.0.0", "entry": jsonable_encoder(entry), "errors": []})
    except ServiceError as exc:
        return _failure(exc)
    except (ValueError, TypeError, json.JSONDecodeError):
        return _failure(ServiceError(SearchError(
            kind="request", message="invalid library request", source=None,
            retry_after_seconds=None, record_index=None)))


@router.get("/library/export", response_model=None)
def public_library_export(format: str = "json") -> Response | JSONResponse:
    try:
        body = get_public_service().export_library(format)
        media = "application/json; charset=utf-8" if format == "json" else "text/x-bibtex; charset=utf-8"
        return Response(content=body, media_type=media)
    except ServiceError as exc:
        return _failure(exc)
