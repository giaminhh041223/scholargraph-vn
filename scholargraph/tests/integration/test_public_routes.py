"""FastAPI public route tests with an injected synthetic service."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scholargraph.api.app import app
from scholargraph.api.public_routes import set_public_service
from tests.unit.test_public_service import MemoryStore, adapters_for, make_service, request


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
