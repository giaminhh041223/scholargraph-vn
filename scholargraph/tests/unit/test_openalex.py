"""Contract tests for resumable, immutable OpenAlex pilot acquisition."""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from scholargraph.ingest.openalex import (
    OpenAlexAPIError,
    OpenAlexPilotConfig,
    OpenAlexPilotDownloader,
    SnapshotIntegrityError,
    _build_report,
    canonical_openalex_work_id,
)


def _work(index: int, *, references: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/W{index}",
        "doi": f"https://doi.org/10.1234/example{index}",
        "title": f"Work {index}",
        "publication_year": 2020,
        "abstract_inverted_index": {"example": [0]},
        "authorships": [{"author": {"id": f"https://openalex.org/A{index}"}}],
        "primary_location": {
            "source": {"id": "https://openalex.org/S1", "display_name": "Example Venue"}
        },
        "cited_by_count": index,
        "referenced_works": references or [],
        "primary_topic": {"id": "https://openalex.org/T10286"},
        "topics": [{"id": "https://openalex.org/T10286", "score": 0.9}],
        "updated_date": "2026-09-01T00:00:00Z",
        "type": "article",
        "language": "en",
        "is_retracted": False,
        "is_paratext": False,
    }


def _response(request: httpx.Request, results: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        headers={
            "X-RateLimit-Limit": "1000",
            "X-RateLimit-Remaining": "999",
            "X-RateLimit-Credits-Used": "1",
            "X-RateLimit-Reset": "3600",
        },
        json={
            "meta": {
                "count": 1100,
                "page": int(request.url.params["page"]),
                "per_page": 100,
                "cost_usd": 0.0001,
            },
            "results": results,
            "group_by": [],
        },
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return (
        tmp_path / "raw",
        tmp_path / "manifests" / "openalex_pilot.json",
        tmp_path / "reports" / "openalex_pilot.json",
    )


def test_config_enforces_pilot_range_and_canonical_ids() -> None:
    with pytest.raises(ValueError, match="1,000 and 3,000"):
        OpenAlexPilotConfig("T10286", "Information Retrieval", target_count=999)
    with pytest.raises(ValueError, match="topic_id"):
        OpenAlexPilotConfig("information-retrieval", "Information Retrieval")
    with pytest.raises(ValueError, match="query parameters"):
        OpenAlexPilotConfig(
            "T10286",
            "Information Retrieval",
            endpoint="https://api.openalex.org/works?api_key=must-not-be-here",
        )

    config = OpenAlexPilotConfig(
        "https://openalex.org/T10286", " Information Retrieval ", target_count=1000
    )
    assert config.topic_id == "T10286"
    assert config.topic_name == "Information Retrieval"
    assert config.api_sample_size == 1100
    assert canonical_openalex_work_id("https://openalex.org/W123/") == "openalex:W123"


def test_transient_errors_retry_with_backoff_without_secret_in_evidence(tmp_path: Path) -> None:
    attempts = 0
    secret = "oa-secret-must-never-be-persisted"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, request=request, headers={"Retry-After": "3"})
        if attempts == 2:
            return httpx.Response(500, request=request)
        return _response(request, [_work(index) for index in range(1, 1001)])

    sleeps: list[float] = []
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": f"Bearer {secret}"},
    )
    raw, manifest, report = _paths(tmp_path)
    config = OpenAlexPilotConfig(
        "T10286",
        "Information Retrieval",
        target_count=1000,
        request_interval_seconds=0,
        backoff_initial_seconds=1,
    )
    downloader = OpenAlexPilotDownloader(
        config, raw, manifest, report, client=client, sleeper=sleeps.append
    )

    completed = downloader.download()

    assert attempts == 3
    assert sleeps == [3.0, 2.0]
    assert completed["counts"]["retries"] == 2
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file()
    )
    assert secret not in persisted
    assert "authorization" not in persisted.lower()


def test_upstream_error_and_network_exception_cannot_echo_secret(tmp_path: Path) -> None:
    secret = "synthetic-secret-for-regression"

    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            request=request,
            json={
                "error": {
                    "message": f"Invalid Authorization: Bearer {secret}",
                    "debug": {"api_key": secret},
                }
            },
        )

    config = OpenAlexPilotConfig("T10286", "Information Retrieval", target_count=1000)
    raw, manifest, report = _paths(tmp_path)
    rejected_downloader = OpenAlexPilotDownloader(
        config,
        raw,
        manifest,
        report,
        api_key=secret,
        client=httpx.Client(
            transport=httpx.MockTransport(rejected),
            headers={"Authorization": f"Bearer {secret}"},
        ),
    )
    with pytest.raises(OpenAlexAPIError) as caught:
        rejected_downloader._fetch_page(1)
    rendered = "".join(
        traceback.format_exception(caught.type, caught.value, caught.tb)
    )
    assert secret not in str(caught.value)
    assert secret not in rendered
    assert "upstream JSON error details omitted" in str(caught.value)

    def broken_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError(
            f"proxy echoed Authorization: Bearer {secret}", request=request
        )

    network_downloader = OpenAlexPilotDownloader(
        OpenAlexPilotConfig(
            "T10286", "Information Retrieval", target_count=1000, max_retries=0
        ),
        raw,
        manifest,
        report,
        client=httpx.Client(transport=httpx.MockTransport(broken_transport)),
    )
    with pytest.raises(OpenAlexAPIError) as network_error:
        network_downloader._fetch_page(1)
    assert secret not in str(network_error.value)
    assert str(network_error.value).endswith("after RemoteProtocolError; cached evidence was preserved.")


def test_retry_after_is_not_shortened_and_supports_http_date_and_quota_reset(
    tmp_path: Path,
) -> None:
    fixed_now = datetime(2026, 9, 15, 15, 0, 0, tzinfo=timezone.utc)
    retry_date = format_datetime(fixed_now + timedelta(seconds=180), usegmt=True)
    scenarios = [
        ({"Retry-After": "120"}, 120.0),
        ({"Retry-After": retry_date}, 180.0),
        (
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "240",
            },
            240.0,
        ),
    ]

    for index, (headers, expected_delay) in enumerate(scenarios):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, request=request, headers=headers)
            return _response(request, [_work(1)])

        sleeps: list[float] = []
        raw, manifest, report = _paths(tmp_path / str(index))
        downloader = OpenAlexPilotDownloader(
            OpenAlexPilotConfig(
                "T10286",
                "Information Retrieval",
                target_count=1000,
                max_backoff_seconds=60,
            ),
            raw,
            manifest,
            report,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleeper=sleeps.append,
            clock=lambda: fixed_now,
        )
        downloader._fetch_page(1)
        assert sleeps == [expected_delay]


def test_report_distinguishes_location_presence_from_actual_venue_name() -> None:
    works = [_work(index) for index in range(1, 5)]
    works[1]["primary_location"] = {
        "source": None,
        "raw_source_name": "Proceedings of ExampleConf",
        "landing_page_url": "https://example.test/2",
    }
    works[2]["primary_location"] = {
        "source": None,
        "raw_source_name": None,
        "landing_page_url": "https://example.test/3",
    }
    works[3]["primary_location"] = None
    page = {
        "payload": {"meta": {"cost_usd": 0.0001}, "results": works},
        "request_elapsed_seconds": 0.1,
        "retry_count": 0,
        "rate_limit": {},
    }

    report = _build_report(
        OpenAlexPilotConfig("T10286", "Information Retrieval", target_count=1000),
        [page],
        works,
        datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    assert report["coverage"]["primary_location"] == {"count": 3, "fraction": 0.75}
    assert report["coverage"]["venue"] == {"count": 2, "fraction": 0.5}


def test_resume_reuses_verified_pages_and_deduplicates_across_pages(tmp_path: Path) -> None:
    raw, manifest, report = _paths(tmp_path)
    config = OpenAlexPilotConfig(
        "T10286", "Information Retrieval", target_count=1000, request_interval_seconds=0
    )
    first_calls: list[int] = []

    def interrupted_handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        first_calls.append(page)
        if page == 1:
            return _response(request, [_work(index) for index in range(1, 101)])
        return httpx.Response(400, request=request, json={"message": "intentional interruption"})

    first = OpenAlexPilotDownloader(
        config,
        raw,
        manifest,
        report,
        client=httpx.Client(transport=httpx.MockTransport(interrupted_handler)),
        sleeper=lambda _: None,
    )
    with pytest.raises(OpenAlexAPIError, match="HTTP 400: upstream JSON error details omitted"):
        first.download()
    assert first_calls == [1, 2]
    assert (raw / "pages" / "page-00001.json").exists()

    # A checkpoint can be lost in a crash; verified raw pages remain authoritative.
    (raw / "checkpoint.json").unlink()
    resumed_calls: list[int] = []

    def resumed_handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        resumed_calls.append(page)
        if page == 2:
            # W100 is repeated across the page boundary.
            results = [_work(index) for index in range(100, 200)]
        elif 3 <= page <= 10:
            start = page * 100 - 100
            results = [_work(index) for index in range(start, start + 100)]
        elif page == 11:
            results = [_work(index) for index in range(1000, 1100)]
        else:  # pragma: no cover - guards accidental over-fetch
            raise AssertionError(f"unexpected page {page}")
        return _response(request, results)

    resumed = OpenAlexPilotDownloader(
        config,
        raw,
        manifest,
        report,
        client=httpx.Client(transport=httpx.MockTransport(resumed_handler)),
        sleeper=lambda _: None,
    )
    completed = resumed.download()

    assert resumed_calls == list(range(2, 12))
    assert completed["counts"]["selected_unique_works"] == 1000
    assert completed["counts"]["duplicates_dropped_before_selection"] == 1
    works = [json.loads(line) for line in (raw / "works.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(works) == 1000
    assert len({work["id"] for work in works}) == 1000
    assert works[0]["id"].endswith("/W1")
    assert works[-1]["id"].endswith("/W1000")
    checkpoint = json.loads((raw / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["status"] == "COMPLETED"
    assert checkpoint["unique_records_seen"] == 1099
    assert checkpoint["duplicates_dropped"] == 1

    no_network_calls = 0

    def forbidden_handler(_: httpx.Request) -> httpx.Response:
        nonlocal no_network_calls
        no_network_calls += 1
        raise AssertionError("completed snapshot must not call the network")

    reopened = OpenAlexPilotDownloader(
        config,
        raw,
        manifest,
        report,
        client=httpx.Client(transport=httpx.MockTransport(forbidden_handler)),
    )
    assert reopened.download()["snapshot_id"] == completed["snapshot_id"]
    assert no_network_calls == 0


def test_completed_snapshot_detects_tampering(tmp_path: Path) -> None:
    raw, manifest, report = _paths(tmp_path)
    config = OpenAlexPilotConfig(
        "T10286", "Information Retrieval", target_count=1000, request_interval_seconds=0
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, [_work(index) for index in range(1, 1001)])

    downloader = OpenAlexPilotDownloader(
        config,
        raw,
        manifest,
        report,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    downloader.download()
    with (raw / "works.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")

    with pytest.raises(SnapshotIntegrityError, match="artifact mismatch"):
        downloader.download()


def test_completed_snapshot_checks_manifest_hash_for_raw_pages(tmp_path: Path) -> None:
    raw, manifest, report = _paths(tmp_path)
    config = OpenAlexPilotConfig(
        "T10286", "Information Retrieval", target_count=1000, request_interval_seconds=0
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, [_work(index) for index in range(1, 1001)])

    downloader = OpenAlexPilotDownloader(
        config,
        raw,
        manifest,
        report,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    downloader.download()
    page_path = raw / "pages" / "page-00001.json"
    # Whitespace keeps the embedded payload hash valid, so only the completed
    # manifest's whole-file hash can detect this mutation.
    with page_path.open("a", encoding="utf-8") as handle:
        handle.write("\n")

    with pytest.raises(SnapshotIntegrityError, match="raw-page mismatch"):
        downloader.download()
