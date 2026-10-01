"""FastAPI public route tests with an injected synthetic service."""
import json
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scholargraph.api.app import app
from scholargraph.api.public_routes import set_public_service
from tests.unit.test_public_service import MemoryStore, adapters_for, cfg, make_service, request


application = importlib.import_module("scholargraph.api.app")
public_routes = importlib.import_module("scholargraph.api.public_routes")


@pytest.fixture()
def client(tmp_path):
    service = make_service(tmp_path, store=MemoryStore(), calls=[])
    set_public_service(service)
    yield TestClient(app)
    set_public_service(None)


def test_search_and_results_use_contract_envelope(client):
    response = client.get("/public/search", params={"query": "synthetic", "sources": "openalex,arxiv"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"] == "success" and payload["snapshot"]
    result = client.get("/public/results/" + payload["snapshot"]["snapshot_id"])
    assert result.status_code == 200 and result.json()["contract_version"] == "1.0.0"


def test_invalid_request_missing_query_is_422_envelope(client):
    response = client.get("/public/search", params={"sources": "openalex"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["overall"] == "failed" and payload["errors"][0]["kind"] == "request"


def test_partial_failure_is_non_2xx_and_preserves_snapshot(client, tmp_path):
    service = make_service(tmp_path, store=MemoryStore(), calls=[], adapters=adapters_for([], failed=True))
    # Replace only one selected adapter with a valid success to exercise mixed state.
    from tests.unit.test_public_service import source_result_success, source_result_failed
    service._adapters = {"openalex": lambda r, t: source_result_success("openalex"),
                         "arxiv": lambda r, t: source_result_failed("arxiv")}
    set_public_service(service)
    response = client.get("/public/search", params={"query": "synthetic"})
    assert response.status_code == 504 and response.json()["overall"] == "partial_failure"
    assert response.json()["snapshot"] is not None


def test_library_export_and_invalid_route(client):
    search = client.get("/public/search", params={"query": "synthetic"}).json()
    hit = search["snapshot"]["fusion"]["hits"][0]
    saved = client.post("/public/library", json={"snapshot_id": search["snapshot"]["snapshot_id"], "canonical_id": hit["canonical_id"]})
    assert saved.status_code == 200 and saved.json()["entry"]["canonical_id"] == hit["canonical_id"]
    assert client.get("/public/library").status_code == 200
    assert client.get("/public/library/export", params={"format": "json"}).status_code == 200
    bad = client.get("/public/library/export", params={"format": "xml"})
    assert bad.status_code == 422 and bad.json()["overall"] == "failed"


def test_public_ui_and_assets_do_not_load_offline_or_public_services(monkeypatch):
    def unavailable():
        pytest.fail("Serving the public page or its assets must not load a search service")

    monkeypatch.setattr(application, "get_service", unavailable)
    monkeypatch.setattr(public_routes, "get_public_service", unavailable)
    with TestClient(app) as browser:
        page = browser.get("/public/ui")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        assert 'id="public-search-form"' in page.text
        assert 'src="/static/public_search.js"' in page.text
        assert 'href="/static/public_search.css"' in page.text
        for asset in ("/static/public_search.js", "/static/public_search.css"):
            response = browser.get(asset)
            assert response.status_code == 200 and response.content


def test_offline_page_links_to_rendered_public_ui(monkeypatch):
    monkeypatch.setattr(application, "get_service", lambda: SimpleNamespace(doc_count=1))
    with TestClient(app) as browser:
        page = browser.get("/")
        assert page.status_code == 200
        assert 'href="/public/ui" id="link-public-search"' in page.text
        assert browser.get("/public/ui").status_code == 200


def test_public_root_retains_json_readiness(client):
    response = client.get("/public")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ready", "contract_version": "1.0.0",
                               "sources": ["openalex", "arxiv"]}


def test_missing_storage_fails_readiness_while_public_ui_remains_accessible(tmp_path, monkeypatch):
    config = cfg(tmp_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "public_search.json").write_bytes(config.read_bytes())
    monkeypatch.setattr(public_routes, "PROJECT_ROOT", tmp_path)
    set_public_service(None)
    try:
        with TestClient(app) as browser:
            assert browser.get("/public/ui").status_code == 200
            response = browser.get("/public")
        assert response.status_code == 500
        assert response.json()["overall"] == "failed"
        assert response.json()["snapshot"] is None
        assert response.json()["errors"][0]["kind"] == "storage"
        assert not (tmp_path / "data/public_search/service-test/library.sqlite3").exists()
    finally:
        set_public_service(None)
