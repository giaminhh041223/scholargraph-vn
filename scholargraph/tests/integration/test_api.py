"""SG-035 API integration tests on real frozen data (no qrels, no mocks)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scholargraph.api.app import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_real_snapshot() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["docs"] == 5183
    assert body["model_revision"] == "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"


def test_search_bm25_real() -> None:
    r = client.get("/search", params={"q": "diabetes obesity", "method": "bm25", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 5
    assert body["snapshot"] == "beir-scifact-frozen"
    assert "bm25" in body["method"]


def test_search_dense_real() -> None:
    r = client.get("/search", params={"q": "diabetes obesity", "method": "dense", "top_k": 3})
    assert r.status_code == 200
    assert len(r.json()["results"]) == 3


def test_search_hybrid_real() -> None:
    r = client.get("/search", params={"q": "diabetes obesity", "method": "hybrid", "top_k": 5})
    assert r.status_code == 200
    assert len(r.json()["results"]) == 5


def test_search_filter_real() -> None:
    r = client.get("/search", params={"q": "diabetes", "method": "bm25", "top_k": 10,
                                      "title_must_contain": "diabetes"})
    assert r.status_code == 200
    for row in r.json()["results"]:
        assert "diabetes" in (row["title"] or "").casefold()


def test_search_empty_query_400() -> None:
    r = client.get("/search", params={"q": "   ", "method": "bm25"})
    assert r.status_code in (400, 422)


def test_search_bad_topk_400() -> None:
    r = client.get("/search", params={"q": "diabetes", "top_k": 500})
    assert r.status_code == 400


def test_paper_real_and_404() -> None:
    first = client.get("/search", params={"q": "diabetes", "top_k": 1}).json()["results"][0]["doc_id"]
    r = client.get(f"/paper/{first}")
    assert r.status_code == 200
    assert r.json()["doc_id"] == first
    assert r.json()["year"] is None and r.json()["doi"] is None
    assert client.get("/paper/beir:scifact:0").status_code == 404


def test_recommend_excludes_self() -> None:
    first = client.get("/search", params={"q": "diabetes", "top_k": 1}).json()["results"][0]["doc_id"]
    r = client.get(f"/recommend/{first}", params={"top_k": 5})
    assert r.status_code == 200
    ids = [x["doc_id"] for x in r.json()["results"]]
    assert first not in ids and len(ids) == 5
    assert client.get("/recommend/beir:scifact:0").status_code == 404


def test_hybrid_zero_overlap_falls_back_dense_only() -> None:
    # Zero BM25 token overlap (nonsense probe) must NOT 500: the service falls
    # back to the dense order with an honest method label (SG-036 UI bugfix).
    r = client.get("/search", params={"q": "zxqvkjwx", "method": "hybrid", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert "fallback-dense-only" in body["method"]
    assert len(body["results"]) == 3
    assert all("fallback" in row["method"] for row in body["results"])


def test_hybrid_falls_back_lexical_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from scholargraph.retrieval.dense import ExactDenseIndex

    monkeypatch.setattr(ExactDenseIndex, "search", lambda self, vec, top_k=100, **kw: [])
    r = client.get("/search", params={"q": "diabetes obesity", "method": "hybrid", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert "fallback-lexical-only" in body["method"]
    assert len(body["results"]) == 3
    assert all("hybrid-fallback-dense-empty" in row["method"] for row in body["results"])


def test_hybrid_both_sides_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from scholargraph.retrieval.dense import ExactDenseIndex

    monkeypatch.setattr(ExactDenseIndex, "search", lambda self, vec, top_k=100, **kw: [])
    r = client.get("/search", params={"q": "zxqvkjwx", "method": "hybrid", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert "both-sides-empty" in body["method"]
    assert body["results"] == []
