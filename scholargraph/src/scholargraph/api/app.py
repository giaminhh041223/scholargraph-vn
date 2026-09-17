"""FastAPI application — ScholarGraph VN demo (SG-035)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from scholargraph.api.service import SearchService, ServiceError

PROJECT_ROOT = Path(__file__).resolve().parents[3]

app = FastAPI(title="ScholarGraph VN", version="0.1.0")
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "ui" / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "ui" / "templates")
_service: SearchService | None = None


def get_service() -> SearchService:
    global _service
    if _service is None:
        try:
            _service = SearchService(PROJECT_ROOT)
        except Exception as exc:  # noqa: BLE001 - startup boundary
            raise HTTPException(status_code=500, detail=f"Service unavailable: {exc}")
    return _service


@app.get("/health")
def health() -> dict[str, Any]:
    svc = get_service()
    return {"status": "ok", "snapshot": "beir-scifact-frozen",
            "docs": svc.doc_count, "model_revision": svc.model_revision}


@app.get("/", include_in_schema=False)
def index(request: Request) -> Any:
    svc = get_service()
    return templates.TemplateResponse(request, "search.html", {
        "snapshot": "beir-scifact-frozen", "docs": svc.doc_count})


@app.get("/search")
def search(q: str = Query(..., min_length=1),
           method: Literal["bm25", "dense", "hybrid"] = "bm25",
           top_k: int = 10,
           title_must_contain: str | None = None) -> dict[str, Any]:
    try:
        return get_service().search_filter(q, method, top_k, title_must_contain)
    except ServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/paper/{doc_id}")
def paper(doc_id: str) -> dict[str, Any]:
    try:
        return get_service().paper(doc_id)
    except ServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/recommend/{doc_id}")
def recommend(doc_id: str, top_k: int = 10) -> dict[str, Any]:
    try:
        return get_service().recommend(doc_id, top_k)
    except ServiceError as exc:
        code = 404 if str(exc).startswith("Unknown document") else 400
        raise HTTPException(status_code=code, detail=str(exc))
