"""EXT-06 adversarial integration checks using temporary synthetic stores."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import builtins
import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from scholargraph.api.app import app
from scholargraph.api.public_routes import set_public_service
from tests.unit.test_public_service import (
    MemoryStore,
    adapters_for,
    cfg,
    make_service,
)
from scholargraph.public_search.contracts import load_config, SearchRequest
from scholargraph.public_search.store import initialize_store, open_existing
from scholargraph.public_search.transport import Transport
import httpx
import pytest


PYTHON = sys.executable
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "search_public.py"


def run_cli(tmp_path: Path, *args: str, config: Path | None = None) -> subprocess.CompletedProcess[str]:
    config = cfg(tmp_path) if config is None else config
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    return subprocess.run(
        [PYTHON, str(SCRIPT), "--project-root", str(tmp_path), "--config", str(config), *args],
        text=True, capture_output=True, timeout=30, env=env,
    )


def test_missing_config_and_duplicate_json_fail_closed(tmp_path: Path) -> None:
    missing = run_cli(tmp_path, "init-storage", config=tmp_path / "missing.json")
    assert missing.returncode == 1 and "Traceback" not in missing.stderr

    valid = cfg(tmp_path)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"query":"x","query":"y"}', encoding="utf-8")
    result = run_cli(tmp_path, "search", "--request", str(duplicate), config=valid)
    assert result.returncode == 1 and "Traceback" not in result.stderr


def test_corrupt_store_is_not_rebuilt(tmp_path: Path) -> None:
    init = run_cli(tmp_path, "init-storage")
    assert init.returncode == 0
    db = tmp_path / "data/public_search/service-test/library.sqlite3"
    before = b"corrupt sqlite sentinel"
    db.write_bytes(before)
    result = run_cli(tmp_path, "search", "--query", "x")
    assert result.returncode == 1 and "Traceback" not in result.stderr
    assert db.read_bytes() == before


def test_partial_failure_is_non_2xx_and_keeps_snapshot(tmp_path: Path) -> None:
    service = make_service(tmp_path, store=MemoryStore(), calls=[], adapters=adapters_for([], failed=True))
    set_public_service(service)
    try:
        response = TestClient(app).get("/public/search", params={"query": "synthetic"})
        assert response.status_code >= 400
        payload = response.json()
        assert payload["overall"] == "failed" and payload["snapshot"] is not None
    finally:
        set_public_service(None)


def test_service_does_not_touch_label_or_qrels_sentinels(tmp_path: Path) -> None:
    core = tmp_path / "core"
    core.mkdir()
    sentinels = [core / "labels.sentinel", core / "qrels.sentinel", core / "heldout.sentinel"]
    for path in sentinels:
        path.write_text("DO NOT READ OR MODIFY", encoding="utf-8")
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sentinels}
    real_open = builtins.open
    real_io_open = io.open

    def deny_core_reads(file, *args, **kwargs):
        candidate = Path(file).resolve() if not isinstance(file, int) else None
        if candidate in {path.resolve() for path in sentinels}:
            raise AssertionError(f"online service attempted forbidden core read: {candidate.name}")
        return real_open(file, *args, **kwargs)

    # Hash checks alone only detect mutation.  Intercepting the actual OS read
    # makes this a leakage test even when the service reads and restores bytes.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(builtins, "open", deny_core_reads)
    def deny_pathlib_reads(file, *args, **kwargs):
        candidate = Path(file).resolve() if not isinstance(file, int) else None
        if candidate in {path.resolve() for path in sentinels}:
            raise AssertionError(f"online service attempted forbidden core read: {candidate.name}")
        return real_io_open(file, *args, **kwargs)
    monkeypatch.setattr(io, "open", deny_pathlib_reads)
    service = make_service(tmp_path, store=MemoryStore(), calls=[])
    try:
        # Calibrate both hooks: Path.read_text uses io.open, not builtins.open.
        with pytest.raises(AssertionError):
            sentinels[0].read_text()
        with pytest.raises(AssertionError):
            open(sentinels[1])
        service.search({"query": "synthetic", "sources": ["openalex", "arxiv"], "top_k": 1,
                        "cap_per_source": 1, "year_from": None, "year_to": None, "refresh": False})
    finally:
        monkeypatch.undo()
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in hashes.items())
    source = Path(importlib.import_module(service.__class__.__module__).__file__)
    assert "qrels" not in source.read_text(encoding="utf-8").lower()
    assert "labels" not in source.read_text(encoding="utf-8").lower()


def test_mock_http_adapters_store_snapshot_and_export_without_live_network(tmp_path: Path) -> None:
    """Exercise the real OpenAlex/arXiv adapters through injected HTTP transport."""
    config_path = cfg(tmp_path)
    config = load_config(config_path)
    initialize_store(tmp_path, config).close()
    calls: list[str] = []
    openalex_body = (Path(__file__).parents[1] / "fixtures/public_search/sol/openalex_page.json").read_bytes()
    arxiv_body = (Path(__file__).parents[1] / "fixtures/public_search/gemini/arxiv/valid_feed.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "openalex" in str(request.url):
            return httpx.Response(200, headers={"content-type": "application/json"}, content=openalex_body)
        return httpx.Response(200, headers={"content-type": "application/atom+xml"}, content=arxiv_body)

    def transport_factory(config_model):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return Transport(config_model, client=client, environ={})

    service = __import__("scholargraph.public_search.service", fromlist=["PublicSearchService"]).PublicSearchService(
        tmp_path, config_path, store=open_existing(tmp_path, config), transport_factory=transport_factory,
    )
    envelope = service.search(SearchRequest.model_validate({"query": "electron", "sources": ["openalex", "arxiv"],
        "top_k": 2, "cap_per_source": 2, "year_from": None, "year_to": None, "refresh": True}))
    assert envelope.overall == "success" and envelope.snapshot is not None
    assert len(calls) == 2
    raw_dir = tmp_path / "data/public_search/service-test/raw"
    assert any(raw_dir.iterdir())
    assert service.export_library("json") == b"[]"  # no implicit library writes


@pytest.mark.parametrize(("overall", "expected_exit"), (("empty", 0), ("partial_failure", 1)))
def test_cli_exit_truth_table_with_injected_local_service(tmp_path: Path, overall: str, expected_exit: int) -> None:
    """A subprocess harness verifies CLI status mapping without network access."""
    harness = tmp_path / "cli_harness.py"
    harness.write_text(
        """import sys\nfrom types import SimpleNamespace\nfrom scripts import search_public\nclass FakeEnvelope:\n    def __init__(self, overall):\n        self.overall = overall\n        self.errors = [] if overall == 'empty' else [SimpleNamespace()]\n    def model_dump_json(self):\n        return '{\\"overall\\":\\"' + self.overall + '\\"}'\nclass FakeService:\n    def search(self, request):\n        return FakeEnvelope(sys.argv[1])\nsearch_public._service = lambda args: FakeService()\nsys.exit(search_public.main(['search', '--query', 'synthetic', '--sources', 'openalex']))\n""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src") + os.pathsep + str(Path(__file__).resolve().parents[2])
    result = subprocess.run([PYTHON, str(harness), overall], text=True, capture_output=True, env=env, timeout=30)
    assert result.returncode == expected_exit
    assert json.loads(result.stdout)["overall"] == overall
