"""SG-036 UI/API integration tests — real service, real frozen data, no mocks.

Covers the SG-036 acceptance surface: template render, static offline assets,
search/detail/related over the real API, missing metadata as null (never
fabricated), error/no-results paths, and self-exclusion in recommend.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import scholargraph.api.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as tc:  # lifespan-free; lazy service
        yield tc


def test_index_renders_template(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "app.js" in body and "search-form" in body
    assert "beir-scifact-frozen" in body and "5183" in body


def test_static_served_offline(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200
    js = r.text
    assert "fetch(" in js
    static_dir = PROJECT_ROOT / "ui" / "static"
    for f in static_dir.iterdir():
        if f.suffix in {".js", ".css", ".html"}:
            assert "http://" not in f.read_text(encoding="utf-8"), f.name
            assert "https://" not in f.read_text(encoding="utf-8"), f.name


def test_health_real_counts(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["docs"] == 5183
    assert body["model_revision"] == "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"


def test_search_bm25_real_results(client):
    r = client.get("/search", params={"q": "insulin resistance obesity", "method": "bm25", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "bm25-positive-idf-k1_1.5-b_0.75"
    assert 1 <= len(body["results"]) <= 5
    top = body["results"][0]
    for key in ("doc_id", "score", "title", "snippet", "method"):
        assert key in top
    assert top["doc_id"].startswith("beir:scifact:")


def test_search_zero_token_query_rejected(client):
    r = client.get("/search", params={"q": "!!!", "method": "bm25"})
    assert r.status_code == 400
    assert "zero tokens" in r.json()["detail"]


def test_search_bad_top_k_rejected(client):
    r = client.get("/search", params={"q": "diabetes", "top_k": 1000})
    assert r.status_code == 400


def test_paper_known_and_unknown(client):
    r = client.get("/paper/beir:scifact:195352")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] and body["abstract"]
    # SciFact frozen corpus carries no year/DOI metadata: null, never fabricated.
    assert body["year"] is None and body["doi"] is None
    r404 = client.get("/paper/beir:scifact:does-not-exist")
    assert r404.status_code == 404


def test_recommend_excludes_self(client):
    doc = "beir:scifact:195352"
    r = client.get(f"/recommend/{doc}", params={"top_k": 5})
    assert r.status_code == 200
    body = r.json()
    ids = [row["doc_id"] for row in body["results"]]
    assert doc not in ids and len(ids) == 5
    for row in body["results"]:
        assert row["title"] is not None


def test_no_results_path_is_200_empty(client):
    # 'zxqvkjwx' tokenizes to a single token present in zero documents, so the
    # positive-score BM25 ranking returns an empty list (same probe as ui_smoke.py).
    r = client.get("/search", params={"q": "zxqvkjwx", "method": "bm25", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["results"] == []
