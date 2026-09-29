"""SG-036 UI integration tests (real app, no browser, no mocks)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from scholargraph.api.app import app

client = TestClient(app, raise_server_exceptions=False)


def test_index_serves_template() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "ScholarGraph VN" in r.text
    assert "/static/app.js" in r.text
    assert "https://" not in r.text  # offline: no CDN


def test_static_js_no_cdn() -> None:
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "fetch" in r.text
    assert "https://" not in r.text


def test_search_to_detail_flow() -> None:
    s = client.get("/search", params={"q": "cancer therapy", "method": "hybrid", "top_k": 3})
    assert s.status_code == 200 and len(s.json()["results"]) == 3
    assert s.json()["results"][0]["snippet"]
    doc = s.json()["results"][0]["doc_id"]
    assert client.get(f"/paper/{doc}").status_code == 200
    rel = client.get(f"/recommend/{doc}", params={"top_k": 3})
    assert rel.status_code == 200 and len(rel.json()["results"]) == 3


def test_error_states() -> None:
    assert client.get("/search", params={"q": "   ", "method": "bm25"}).status_code in (400, 422)
    assert client.get("/search", params={"q": "diabetes", "top_k": 500}).status_code == 400
    assert client.get("/search", params={"q": "diabetes", "top_k": 0}).status_code in (400, 422)


def test_no_results_and_unknown_doc() -> None:
    r = client.get("/search", params={"q": "zxqvkjwx", "method": "bm25", "top_k": 5})
    assert r.status_code == 200 and r.json()["results"] == []
    assert client.get("/paper/beir:scifact:0").status_code == 404
    assert client.get("/recommend/beir:scifact:0").status_code == 404


def test_static_assets_and_health() -> None:
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/health").status_code == 200
