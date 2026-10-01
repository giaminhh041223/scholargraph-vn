"""FastAPI application — ScholarGraph VN demo (SG-035)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from scholargraph.api.graph_service import (
    GraphService,
    GraphServiceError,
    read_manifest_snapshot,
)
from scholargraph.api.service import SearchService, ServiceError
from scholargraph.api.public_routes import router as public_router

PROJECT_ROOT = Path(__file__).resolve().parents[3]

app = FastAPI(title="ScholarGraph VN", version="0.1.0")
app.include_router(public_router)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "ui" / "static"), name="static")
app.mount("/graph-static", StaticFiles(directory=PROJECT_ROOT / "ui" / "graph"),
          name="graph-static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "ui" / "templates")
_service: SearchService | None = None
_graph_service: GraphService | None = None


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


@app.get("/public/ui", response_class=HTMLResponse, include_in_schema=False)
def public_page(request: Request) -> Any:
    return templates.TemplateResponse(request, "public_search.html", {})


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


# --- Citation graph UI (task SG-037) — additive; existing routes untouched ---

def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        try:
            _graph_service = GraphService(PROJECT_ROOT)
        except Exception as exc:  # noqa: BLE001 - startup boundary
            raise HTTPException(status_code=500, detail=f"Graph service unavailable: {exc}")
    return _graph_service


@app.get("/graph", include_in_schema=False)
def graph_page(request: Request) -> Any:
    try:
        ctx = read_manifest_snapshot(PROJECT_ROOT)
    except GraphServiceError as exc:
        raise HTTPException(status_code=500, detail=f"Graph service unavailable: {exc}")
    ctx["snapshot_date"] = ctx["retrieved_completed_at"]
    return templates.TemplateResponse(request, "graph.html", ctx)


@app.get("/graph/{doc_id}")
def graph_neighborhood(doc_id: str, mode: str = "evaluated", hop: int = 1,
                       cap: int = 30) -> dict[str, Any]:
    try:
        return get_graph_service().neighborhood(doc_id, mode=mode, hop=hop, cap=cap)
    except GraphServiceError as exc:
        message = str(exc)
        if message.startswith("Unknown document"):
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
