"""Contract tests for the SG-015 citation-connected OpenAlex core snapshot.

All tests are offline: the OpenAlex API is simulated with ``httpx.MockTransport``
and the pilot snapshot is a synthetic fixture.  The suite covers the pinned
plan-before-fetch flow, resumable fetch without loss or duplication,
normalization with counted transformations, and adversarial cases (tampered
cache, edited plan, changed pilot, dead hub IDs, empty cohort pages, malformed
records, missing resources, CLI exit codes) per ADR-013/ADR-014/ADR-016 §7.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from scholargraph.ingest.openalex import (
    OpenAlexAPIError,
    OpenAlexCoreConfig,
    OpenAlexCoreDownloader,
    SnapshotIntegrityError,
    core_main,
    normalize_core_record,
    rank_hub_candidates,
    run_core_postprocess,
    write_core_plan,
    write_core_plan_v2,
)

FIXED_CLOCK = lambda: datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731


def _work(
    work_id: str,
    *,
    year: int,
    title: str = "A work",
    doi: str | None = None,
    abstract: dict[str, list[int]] | None = {"x": [0]},
    references: list[str] | None = None,
    omit_referenced_works: bool = False,
    retracted: bool = False,
    paratext: bool = False,
) -> dict[str, Any]:
    record = {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "title": title,
        "publication_year": year,
        "abstract_inverted_index": abstract,
        "authorships": [{"author": {"id": "https://openalex.org/A1"}}],
        "primary_location": {"source": {"display_name": "Example Venue"}},
        "cited_by_count": 5,
        "referenced_works": references or [],
        "primary_topic": {"id": "https://openalex.org/T10286"},
        "topics": [{"id": "https://openalex.org/T10286", "score": 0.9}],
        "updated_date": "2026-09-01T00:00:00Z",
        "type": "article",
        "language": "en",
        "is_retracted": retracted,
        "is_paratext": paratext,
    }
    if omit_referenced_works:
        record.pop("referenced_works")
    return record


PILOT_WORKS = [
    _work(
        "W1", year=2001, doi="https://doi.org/10.1/A",
        references=["https://openalex.org/W111111111"],
    ),
    _work(
        "W2",
        year=2002,
        references=[
            "https://openalex.org/W111111111",
            "https://openalex.org/W222222222",
            "https://openalex.org/W111111111",
        ],
    ),
    _work("W3", year=2003, references=["https://openalex.org/W111111111"]),
    _work("W4", year=2004, references=[]),
]

HUB_RECORDS = {
    "W111111111": _work(
        "W111111111", year=1980, doi="https://doi.org/10.9/h1", title="Hub one", references=[]
    ),
    "W222222222": _work(
        "W222222222", year=1981, doi="https://doi.org/10.9/h2", title="Hub two", references=[]
    ),
}

COHORT_PAGE_1 = [
    _work(
        "W333333331",
        year=2024,
        doi="10.5/c1",
        references=[
            "https://openalex.org/W111111111",
            "https://openalex.org/W222222222",
            "https://openalex.org/W1",
        ],
    ),
    _work("W2", year=2002, title="Duplicate of pilot W2", references=[]),
]
COHORT_PAGE_2 = [
    _work(
        "W333333332", year=2024, abstract=None,
        references=["https://openalex.org/W111111111"],
    ),
    _work(
        "W333333333",
        year=2024,
        doi="https://doi.org/10.5/X3",
        references=["https://openalex.org/W333333333", "https://openalex.org/W111111111"],
    ),
]


def _small_config(pilot_path: Path, **overrides: Any) -> OpenAlexCoreConfig:
    defaults: dict[str, Any] = dict(
        pilot_works_path=pilot_path,
        per_page=2,
        candidate_hub_count=2,
        hub_id_batch_size=2,
        active_hub_max_year=2015,
        active_hub_cap=2,
        cohort_years=(2024,),
        cohort_year_order=(2024,),
        per_year_sample_cap=4,
        global_work_cap=100,
        minimum_snapshot_works=5,
        request_interval_seconds=0,
    )
    defaults.update(overrides)
    return OpenAlexCoreConfig(**defaults)


def _write_pilot(tmp_path: Path, works: list[dict[str, Any]]) -> tuple[Path, Path]:
    pilot_dir = tmp_path / "pilot"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    pilot_path = pilot_dir / "works.jsonl"
    pilot_path.write_text(
        "".join(json.dumps(work) + "\n" for work in works), encoding="utf-8"
    )
    manifest_path = tmp_path / "pilot_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "selection": {"filter": "topics.id:T10286"},
                "artifacts": {
                    "works_jsonl": {
                        "sha256": hashlib.sha256(pilot_path.read_bytes()).hexdigest()
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return pilot_path, manifest_path


def _core_handler(calls: list[str] | None = None):
    """Simulate the API: one hub batch (2 IDs) plus a 2-page cohort sample."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        filter_value = params["filter"]
        if calls is not None:
            calls.append(filter_value.split(",")[0][:40] + f"|page={params.get('page')}")
        if filter_value.startswith("openalex_id:"):
            ids = filter_value.split(":", 1)[1].split("|")
            results = [HUB_RECORDS[work_id] for work_id in ids if work_id in HUB_RECORDS]
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": len(results)}, "results": results},
            )
        page = int(params["page"])
        if page == 1:
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": 4}, "results": COHORT_PAGE_1},
            )
        if page == 2:
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": 4}, "results": COHORT_PAGE_2},
            )
        raise AssertionError(f"unexpected cohort page {page}")

    return handler


@pytest.fixture()
def pipeline(tmp_path: Path):
    pilot_path, pilot_manifest = _write_pilot(tmp_path, PILOT_WORKS)
    manifest_path = tmp_path / "manifests" / "openalex_core.json"
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    quality_path = tmp_path / "reports" / "openalex_quality.json"
    return {
        "tmp": tmp_path,
        "pilot_path": pilot_path,
        "pilot_manifest": pilot_manifest,
        "manifest_path": manifest_path,
        "raw_dir": raw_dir,
        "processed_dir": processed_dir,
        "quality_path": quality_path,
    }


def _plan(pipeline: dict[str, Path], config: OpenAlexCoreConfig) -> dict[str, Any]:
    return write_core_plan(
        config=config,
        manifest_path=pipeline["manifest_path"],
        pilot_manifest_path=pipeline["pilot_manifest"],
        clock=FIXED_CLOCK,
    )


def _fetch(
    pipeline: dict[str, Path],
    config: OpenAlexCoreConfig,
    handler,
    sleeper=lambda _: None,
) -> dict[str, Any]:
    with OpenAlexCoreDownloader(
        config,
        pipeline["raw_dir"],
        pipeline["manifest_path"],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeper,
        clock=FIXED_CLOCK,
    ) as downloader:
        return downloader.fetch()


def _postprocess(pipeline: dict[str, Path]) -> tuple[int, dict[str, Any]]:
    return run_core_postprocess(
        manifest_path=pipeline["manifest_path"],
        raw_dir=pipeline["raw_dir"],
        processed_dir=pipeline["processed_dir"],
        quality_report_path=pipeline["quality_path"],
        command=["postprocess", "test"],
        clock=FIXED_CLOCK,
    )


# ---------------------------------------------------------------------------
# Plan pinning (pin-before-fetch, ADR-016 §7)
# ---------------------------------------------------------------------------


def test_plan_is_pinned_before_fetch_and_never_mutated(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    planned = _plan(pipeline, config)

    assert planned["status"] == "PLANNED"
    assert planned["task_id"] == "SG-015"
    assert "fetch" not in planned and "execution" not in planned
    candidates = planned["sampling_plan"]["hub_selection"]["hub_candidates"]
    # H1 is referenced by 3 pilot works, H2 by 1 -> deterministic ranking.
    assert [c["openalex_id"] for c in candidates] == ["W111111111", "W222222222"]
    assert [c["distinct_pilot_sources"] for c in candidates] == [3, 1]
    assert planned["sampling_plan"]["invariants"]["floors"] == {
        "minimum_test_queries": 50,
        "minimum_dev_queries": 30,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 100,
    }
    assert planned["sampling_plan"]["invariants"]["qrels_used"] is False
    assert planned["sampling_plan"]["invariants"]["beir_data_used_for_sampling"] is False

    # Refuses to overwrite an existing manifest.
    with pytest.raises(SnapshotIntegrityError, match="Refusing to overwrite"):
        _plan(pipeline, config)


def test_fetch_without_pinned_plan_is_fatal(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    with OpenAlexCoreDownloader(
        config,
        pipeline["raw_dir"],
        pipeline["manifest_path"],
        client=httpx.Client(transport=httpx.MockTransport(_core_handler())),
    ) as downloader:
        with pytest.raises(SnapshotIntegrityError, match="pin-before-fetch"):
            downloader.fetch()


def test_fetch_rejects_edited_plan_fingerprint(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    manifest = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    manifest["sampling_plan"]["cohort_selection"]["per_year_sample_cap"] = 999999
    pipeline["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError, match="fingerprint mismatch"):
        _fetch(pipeline, config, _core_handler())


def test_fetch_rejects_pilot_file_changed_after_plan(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    pilot = json.loads(pipeline["pilot_path"].read_text(encoding="utf-8").splitlines()[0])
    with pipeline["pilot_path"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_work("W999", year=2020)) + "\n")
    assert pilot["id"].endswith("W1")  # original pilot untouched by the append above
    with pytest.raises(SnapshotIntegrityError, match="changed after the plan was pinned"):
        _fetch(pipeline, config, _core_handler())


# ---------------------------------------------------------------------------
# Full pipeline: counts, normalization, determinism
# ---------------------------------------------------------------------------


def test_full_pipeline_measures_expected_counts(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    fetched = _fetch(pipeline, config, _core_handler())
    assert fetched["status"] == "FETCHED"
    execution = fetched["execution"]
    assert execution["snapshot_composition"] == {
        "pilot_works": 4,
        "hub_works_merged": 2,
        "cohort_only_works": 3,
        "total_unique_works": 9,
    }
    assert execution["duplicates_and_overlaps"]["cohort_records_already_in_pilot"] == 1
    assert execution["hubs"]["active_hubs_used"] == 2

    exit_code, completed = _postprocess(pipeline)
    assert exit_code == 0
    assert completed["status"] == "COMPLETED"

    # The pinned plan survives fetch and postprocess unchanged.
    final = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    planned = json.loads(
        json.dumps(final)
    )  # parse round-trip guard
    assert final["sampling_plan"] == planned["sampling_plan"]
    assert final["status"] == "COMPLETED"
    assert final["artifacts"]["works_jsonl"]["path"].endswith("processed/works.jsonl")

    report = json.loads(pipeline["quality_path"].read_text(encoding="utf-8"))
    assert report["status"] == "MEASURED"
    assert report["qrels_used"] is False
    counts = report["counts"]
    assert counts["works"] == 9
    assert counts["unique_canonical_ids"] == 9
    assert counts["reference_entries_total"] == 11
    assert counts["internal_reference_occurrences"] == 10
    assert counts["unique_internal_directed_edges"] == 9
    assert counts["self_loop_count"] == 1
    assert counts["duplicate_reference_entry_count"] == 1
    assert counts["isolated_nodes"] == 1
    assert counts["weakly_connected_components"] == 2
    assert counts["largest_weak_component_size"] == 8
    # In/out degrees follow gate semantics: counted per reference occurrence.
    assert counts["max_internal_in_degree"] == 7
    assert counts["max_internal_out_degree"] == 3

    # Eligibility (Protocol v1 track-B definition, independent recount):
    # W2 (2002) cites W111111111(1980) and W222222222(1981); W333333331 (2024) cites both hubs and W1.
    cohorts = report["protocol_b_cohorts_independent_recount"]
    assert cohorts["eligible_source_count_by_publication_year"] == {"2002": 1, "2024": 1}
    assert cohorts["total_eligible_sources"] == 2
    assert cohorts["floors_applied"]["minimum_test_queries"] == 50

    # DOI normalization counted per transformation.
    doi = report["doi_normalization"]["transformations"]
    assert doi["doi_normalized"] == 4
    assert doi["doi_prefix_stripped"] == 4
    assert doi["doi_case_normalized"] == 2
    assert report["metadata_transformations"]["reference_ids_canonicalized"] == 11

    works = [
        json.loads(line)
        for line in (pipeline["processed_dir"] / "works.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    by_id = {work["id"].rsplit("/", 1)[-1]: work for work in works}
    assert by_id["W1"]["doi"] == "10.1/a"
    assert by_id["W333333333"]["doi"] == "10.5/x3"
    assert by_id["W333333333"]["referenced_works"] == ["W333333333", "W111111111"]
    assert by_id["W2"]["doi"] is None  # pilot record wins over the cohort duplicate
    assert [w["id"].rsplit("/", 1)[-1] for w in works] == sorted(
        w["id"].rsplit("/", 1)[-1] for w in works
    )


def test_postprocess_is_idempotent_and_detects_processed_tampering(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    _fetch(pipeline, config, _core_handler())
    exit_code, _ = _postprocess(pipeline)
    assert exit_code == 0
    processed_bytes = (pipeline["processed_dir"] / "works.jsonl").read_bytes()

    exit_code, manifest = _postprocess(pipeline)
    assert exit_code == 0
    assert manifest["status"] == "COMPLETED"
    assert (pipeline["processed_dir"] / "works.jsonl").read_bytes() == processed_bytes

    processed_path = pipeline["processed_dir"] / "works.jsonl"
    with processed_path.open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    exit_code, failure = _postprocess(pipeline)
    assert exit_code == 1
    assert "hash mismatch" in failure["errors"][0]


def test_two_independent_runs_produce_identical_works_bytes(tmp_path: Path) -> None:
    outputs = []
    for run in ("a", "b"):
        base = tmp_path / run
        base.mkdir()
        pilot_path, pilot_manifest = _write_pilot(base, PILOT_WORKS)
        config = _small_config(pilot_path)
        manifest_path = base / "openalex_core.json"
        write_core_plan(
            config=config,
            manifest_path=manifest_path,
            pilot_manifest_path=pilot_manifest,
            clock=FIXED_CLOCK,
        )
        with OpenAlexCoreDownloader(
            config,
            base / "raw",
            manifest_path,
            client=httpx.Client(transport=httpx.MockTransport(_core_handler())),
            clock=FIXED_CLOCK,
        ) as downloader:
            downloader.fetch()
        outputs.append((base / "raw" / "works.jsonl").read_bytes())
    assert outputs[0] == outputs[1]


# ---------------------------------------------------------------------------
# Resume: no loss, no duplication, cached pages authoritative
# ---------------------------------------------------------------------------


def test_resume_completes_without_refetch_or_loss(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"], max_retries=0)
    _plan(pipeline, config)

    first_calls: list[str] = []

    def interrupted_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["filter"].startswith("openalex_id:"):
            first_calls.append("hubs")
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": 2}, "results": list(HUB_RECORDS.values())},
            )
        first_calls.append(f"cohort-{params['page']}")
        if int(params["page"]) == 2:
            return httpx.Response(500, request=request)
        return httpx.Response(
            200, request=request, json={"meta": {"count": 4}, "results": COHORT_PAGE_1}
        )

    with pytest.raises(OpenAlexAPIError, match="HTTP 500"):
        _fetch(pipeline, config, interrupted_handler)
    assert first_calls == ["hubs", "cohort-1", "cohort-2"]
    assert (pipeline["raw_dir"] / "pages" / "page-00002.json").exists()

    # Losing the checkpoint must not matter: verified raw pages are the truth.
    (pipeline["raw_dir"] / "checkpoint.json").unlink()
    resumed_calls: list[str] = []
    fetched = _fetch(pipeline, config, _core_handler(resumed_calls))
    assert len(resumed_calls) == 1
    assert resumed_calls[0].startswith("cites:") and resumed_calls[0].endswith("|page=2")
    assert fetched["execution"]["snapshot_composition"]["total_unique_works"] == 9

    # Resume output equals an uninterrupted run byte for byte.
    reference = tmp_path_reference(pipeline)
    assert (pipeline["raw_dir"] / "works.jsonl").read_bytes() == reference


def tmp_path_reference(pipeline: dict[str, Path]) -> bytes:
    """Produce the uninterrupted-run works.jsonl bytes in a sibling directory."""

    base = pipeline["tmp"] / "reference_run"
    if not (base / "raw" / "works.jsonl").exists():
        base.mkdir(parents=True, exist_ok=True)
        pilot_path, pilot_manifest = _write_pilot(base, PILOT_WORKS)
        config = _small_config(pilot_path)
        manifest_path = base / "openalex_core.json"
        write_core_plan(
            config=config,
            manifest_path=manifest_path,
            pilot_manifest_path=pilot_manifest,
            clock=FIXED_CLOCK,
        )
        with OpenAlexCoreDownloader(
            config,
            base / "raw",
            manifest_path,
            client=httpx.Client(transport=httpx.MockTransport(_core_handler())),
            clock=FIXED_CLOCK,
        ) as downloader:
            downloader.fetch()
    return (base / "raw" / "works.jsonl").read_bytes()


def test_tampered_cached_page_is_detected(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    pages = pipeline["raw_dir"] / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    bogus = {
        "schema_version": 1,
        "query_fingerprint": "0" * 64,
        "phase": "hubs",
        "phase_key": "hub-batch-0",
        "page_in_phase": 1,
        "page_number": 1,
        "payload": {"meta": {}, "results": []},
        "payload_sha256": "not-the-real-hash",
    }
    (pages / "page-00001.json").write_text(json.dumps(bogus), encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError, match="belongs to another plan"):
        _fetch(pipeline, config, _core_handler())


# ---------------------------------------------------------------------------
# Adversarial data handling
# ---------------------------------------------------------------------------


def test_dead_hub_ids_are_counted_not_fatal(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["filter"].startswith("openalex_id:"):
            # H2 no longer resolves on the live API.
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": 1}, "results": [HUB_RECORDS["W111111111"]]},
            )
        results = [
            _work("W333333334", year=2024, references=["https://openalex.org/W111111111", "https://openalex.org/W222222222"])
        ]
        return httpx.Response(
            200, request=request, json={"meta": {"count": 1}, "results": results}
        )

    _plan(pipeline, config)
    fetched = _fetch(pipeline, config, handler)
    hubs = fetched["execution"]["hubs"]
    assert hubs["active_hubs"] == ["W111111111"]
    assert hubs["active_hubs_used"] == 1
    assert hubs["exclusions"]["unresolvable"] == 1
    assert hubs["exclusions"]["unresolvable_ids"] == ["W222222222"]


def test_empty_first_cohort_page_is_fatal(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["filter"].startswith("openalex_id:"):
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": 2}, "results": list(HUB_RECORDS.values())},
            )
        return httpx.Response(200, request=request, json={"meta": {"count": 0}, "results": []})

    _plan(pipeline, config)
    with pytest.raises(OpenAlexAPIError, match="empty first page"):
        _fetch(pipeline, config, handler)


def test_below_minimum_snapshot_works_fails_loudly(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"], minimum_snapshot_works=50)
    _plan(pipeline, config)
    with pytest.raises(SnapshotIntegrityError, match="requires at least 50"):
        _fetch(pipeline, config, _core_handler())


def test_missing_referenced_works_key_is_filled_and_counted(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    _fetch(pipeline, config, _core_handler())
    # Corrupt the raw snapshot in place?  No — instead postprocess a copy with
    # a raw record missing the referenced_works key via a dedicated manifest.
    raw_dir = pipeline["tmp"] / "raw_missing"
    raw_dir.mkdir()
    records = [
        _work("W1", year=2001, references=["https://openalex.org/W111111111"]),
        _work("W2", year=2002, omit_referenced_works=True),
    ]
    (raw_dir / "works.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    processed, transforms = normalize_core_record(records[1])
    assert processed["referenced_works"] == []
    assert transforms["referenced_works_key_filled"] == 1

    # And the strict gate-facing invariant: normalization never keeps the key absent.
    for record in records:
        normalized, _ = normalize_core_record(record)
        assert "referenced_works" in normalized


def test_malformed_raw_record_fails_postprocess(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    _fetch(pipeline, config, _core_handler())
    raw_works = pipeline["raw_dir"] / "works.jsonl"
    original = raw_works.read_bytes()
    raw_works.write_text(
        json.dumps({"id": "not-an-openalex-id"}) + "\n", encoding="utf-8"
    )
    # Simulate an authorized raw update: refresh the pinned raw hash so the
    # malformed-record path (not the hash guard) is what fails.
    manifest = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    manifest["artifacts"]["raw_works_jsonl"]["sha256"] = hashlib.sha256(
        raw_works.read_bytes()
    ).hexdigest()
    pipeline["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    exit_code, failure = _postprocess(pipeline)
    assert exit_code == 1
    assert any("Invalid OpenAlex work ID" in error for error in failure["errors"])
    raw_works.write_bytes(original)


def test_normalize_core_record_is_idempotent_and_strict() -> None:
    record = _work(
        "W1",
        year=2001,
        doi="  https://DOI.org/10.1/A ",
        references=["https://openalex.org/W111111111", "W222222222"],
    )
    once, transforms_once = normalize_core_record(record)
    twice, transforms_twice = normalize_core_record(once)
    assert once == twice  # output is a fixed point
    assert set(transforms_twice.values()) == {0}  # re-normalizing changes nothing
    assert once["doi"] == "10.1/a"
    assert transforms_once["doi_normalized"] == 1
    assert transforms_once["doi_prefix_stripped"] == 1
    assert transforms_once["doi_case_normalized"] == 1
    assert once["referenced_works"] == ["W111111111", "W222222222"]
    assert transforms_once["reference_ids_canonicalized"] == 1  # the URI form only

    with pytest.raises(SnapshotIntegrityError, match="must be a string"):
        normalize_core_record(_work("W1", year=2001, doi=123))
    with pytest.raises(SnapshotIntegrityError, match="must be an integer"):
        normalize_core_record(
            {**_work("W1", year=2001), "publication_year": "2001"}
        )
    with pytest.raises(SnapshotIntegrityError, match="must be an object"):
        normalize_core_record(
            {**_work("W1", year=2001), "abstract_inverted_index": "text"}
        )
    with pytest.raises(SnapshotIntegrityError, match="must be a list"):
        normalize_core_record({**_work("W1", year=2001), "referenced_works": "W111111111"})
    with pytest.raises(SnapshotIntegrityError, match="Invalid OpenAlex work ID"):
        normalize_core_record({**_work("W1", year=2001), "id": "X1"})


def test_rank_hub_candidates_requires_valid_pilot_ids() -> None:
    with pytest.raises(SnapshotIntegrityError, match="valid 'id'"):
        rank_hub_candidates([{"id": "bogus"}], 2)
    with pytest.raises(SnapshotIntegrityError, match="must be a list"):
        rank_hub_candidates(
            [{"id": "https://openalex.org/W1", "referenced_works": "W2"}], 2
        )


# ---------------------------------------------------------------------------
# Secrets, CLI exit codes
# ---------------------------------------------------------------------------


def test_api_credentials_are_never_persisted(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    secret = "synthetic-bearer-secret-never-persist"
    with OpenAlexCoreDownloader(
        config,
        pipeline["raw_dir"],
        pipeline["manifest_path"],
        api_key=secret,
        client=httpx.Client(transport=httpx.MockTransport(_core_handler())),
        clock=FIXED_CLOCK,
    ) as downloader:
        downloader.fetch()
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in pipeline["tmp"].rglob("*")
        if path.is_file()
    )
    assert secret not in persisted
    assert "authorization" not in persisted.lower()


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    src_root = Path(__file__).resolve().parents[2] / "src"
    env = {**os.environ, "PYTHONPATH": str(src_root)}
    return subprocess.run(
        [sys.executable, "-m", "scholargraph.ingest.openalex", "core", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cli_plan_with_missing_pilot_file_exits_1(tmp_path: Path) -> None:
    result = _run_cli(
        [
            "plan",
            "--pilot-works",
            str(tmp_path / "missing" / "works.jsonl"),
            "--pilot-manifest",
            str(tmp_path / "missing" / "manifest.json"),
            "--manifest",
            str(tmp_path / "out.json"),
            "--per-year-sample-cap",
            "4",
            "--minimum-snapshot-works",
            "5",
            "--candidate-hub-count",
            "2",
            "--cohort-years",
            "2024",
            "--cohort-year-order",
            "2024",
        ],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "CORE FAILED" in result.stderr


def test_cli_fetch_without_manifest_exits_1(pipeline) -> None:
    result = _run_cli(
        [
            "fetch",
            "--pilot-works",
            str(pipeline["pilot_path"]),
            "--pilot-manifest",
            str(pipeline["pilot_manifest"]),
            "--manifest",
            str(pipeline["manifest_path"]),
            "--raw-dir",
            str(pipeline["raw_dir"]),
        ],
        cwd=pipeline["tmp"],
    )
    assert result.returncode == 1
    assert "pin-before-fetch" in result.stderr


def test_cli_postprocess_with_missing_raw_works_exits_1(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    # Force the manifest into FETCHED-like state without a raw snapshot on disk.
    manifest = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    manifest["status"] = "FETCHED"
    pipeline["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    result = _run_cli(
        [
            "postprocess",
            "--manifest",
            str(pipeline["manifest_path"]),
            "--raw-dir",
            str(pipeline["raw_dir"]),
            "--processed-dir",
            str(pipeline["processed_dir"]),
            "--quality-report",
            str(pipeline["quality_path"]),
        ],
        cwd=pipeline["tmp"],
    )
    assert result.returncode == 1
    assert "CORE POSTPROCESS FAILED" in result.stderr


def test_core_main_plan_and_postprocess_contract(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    # plan via in-process CLI
    argv = [
        "plan",
        "--pilot-works",
        str(pipeline["pilot_path"]),
        "--pilot-manifest",
        str(pipeline["pilot_manifest"]),
        "--manifest",
        str(pipeline["manifest_path"]),
        "--per-page",
        "2",
        "--candidate-hub-count",
        "2",
        "--hub-id-batch-size",
        "2",
        "--active-hub-max-year",
        "2015",
        "--active-hub-cap",
        "2",
        "--cohort-years",
        "2024",
        "--cohort-year-order",
        "2024",
        "--per-year-sample-cap",
        "4",
        "--global-work-cap",
        "100",
        "--minimum-snapshot-works",
        "5",
        "--request-interval",
        "0",
    ]
    assert core_main(argv) == 0
    manifest = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["status"] == "PLANNED"
    # plan refuses to run twice even through the CLI.
    assert core_main(argv) == 1


# ---------------------------------------------------------------------------
# Extension plan (v2): historical depth for the novel-candidate floor
# ---------------------------------------------------------------------------


def _extension_probe_handler(pool_count: int = 500):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        filter_value = params["filter"]
        if filter_value.startswith("topics.id:") and "sample" not in params:
            return httpx.Response(
                200, request=request, json={"meta": {"count": pool_count}, "results": []}
            )
        raise AssertionError(f"unexpected probe request: {filter_value[:60]}")

    return handler


def _extension_fetch_handler(probe_handler, bucket_records, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        filter_value = params["filter"]
        if filter_value.startswith("topics.id:") and "sample" not in params:
            return probe_handler(request)
        if filter_value.startswith("topics.id:"):
            year = int(filter_value.rsplit(":", 1)[1])
            if calls is not None:
                calls.append(year)
            results = bucket_records.get(year, [])
            return httpx.Response(
                200,
                request=request,
                json={"meta": {"count": len(results)}, "results": results},
            )
        return _core_handler()(request)

    return handler


def _write_gate_report(tmp_path: Path, overall: str) -> Path:
    gate = tmp_path / "reports" / "graph_feasibility_core.json"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(
        json.dumps({"decision": {"overall": overall}, "measured_at": "2026-09-17T00:00:00+00:00"}),
        encoding="utf-8",
    )
    return gate


def _extension_bucket_records() -> dict:
    return {
        1972: [_work("W555000001", year=1972, title=f"Old {i}") for i in range(1, 4)],
        1973: [_work("W555000002", year=1973, title="Old b"), HUB_RECORDS["W111111111"]],
        1974: [],  # empty bucket: recorded, not fatal
        1975: [_work("W555000003", year=1975, title="Old c")],
    }


def _complete_v1_pipeline(pipeline) -> dict:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    _fetch(pipeline, config, _core_handler())
    exit_code, manifest = _postprocess(pipeline)
    assert exit_code == 0 and manifest["status"] == "COMPLETED"
    return manifest


def test_extension_plan_requires_completed_manifest_and_no_go_gate(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    gate = _write_gate_report(pipeline["tmp"], "NO_GO")
    # A missing manifest cannot be extended.
    with pytest.raises(SnapshotIntegrityError, match="COMPLETED"):
        write_core_plan_v2(
            config=config,
            manifest_path=pipeline["manifest_path"],
            gate_report_path=gate,
            client=httpx.Client(transport=httpx.MockTransport(_extension_probe_handler())),
            clock=FIXED_CLOCK,
        )
    # A PLANNED (not yet COMPLETED) manifest cannot be extended either.
    _plan(pipeline, config)
    with pytest.raises(SnapshotIntegrityError, match="COMPLETED"):
        write_core_plan_v2(
            config=config,
            manifest_path=pipeline["manifest_path"],
            gate_report_path=gate,
            client=httpx.Client(transport=httpx.MockTransport(_extension_probe_handler())),
            clock=FIXED_CLOCK,
        )
    # Complete the v1 pipeline (the manifest was already planned above).
    _fetch(pipeline, config, _core_handler())
    exit_code, manifest = _postprocess(pipeline)
    assert exit_code == 0 and manifest["status"] == "COMPLETED"
    # The missing gate report must be fatal.
    with pytest.raises(SnapshotIntegrityError, match="gate report is missing"):
        write_core_plan_v2(
            config=config,
            manifest_path=pipeline["manifest_path"],
            gate_report_path=pipeline["tmp"] / "missing_gate.json",
            clock=FIXED_CLOCK,
        )
    # A GO gate makes an extension unjustified.
    go_gate = _write_gate_report(pipeline["tmp"], "GO")
    with pytest.raises(SnapshotIntegrityError, match="not NO_GO"):
        write_core_plan_v2(
            config=config,
            manifest_path=pipeline["manifest_path"],
            gate_report_path=go_gate,
            clock=FIXED_CLOCK,
        )


def test_extension_plan_pins_fingerprint_and_proves_sufficiency(pipeline) -> None:
    _complete_v1_pipeline(pipeline)
    gate = _write_gate_report(pipeline["tmp"], "NO_GO")
    config = _small_config(pipeline["pilot_path"], global_work_cap=2000)
    updated = write_core_plan_v2(
        config=config,
        manifest_path=pipeline["manifest_path"],
        gate_report_path=gate,
        client=httpx.Client(transport=httpx.MockTransport(_extension_probe_handler(500))),
        clock=FIXED_CLOCK,
    )
    assert updated["status"] == "EXTEND_PLANNED"
    plan_v2 = updated["sampling_plan_v2"]
    assert plan_v2["v1_gate_evidence"]["overall"] == "NO_GO"
    assert plan_v2["recruitment"]["first_year"] == 1972
    assert plan_v2["recruitment"]["last_year"] == 1979
    assert all(count == 200 for count in plan_v2["recruitment"]["year_buckets"].values())
    assert plan_v2["safety_verification"]["first_year_cumulative_lower_bound"] >= 180
    assert plan_v2["invariants"]["floors"] == {
        "minimum_test_queries": 50,
        "minimum_dev_queries": 30,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 100,
    }
    # Re-pinning is refused: the manifest is no longer COMPLETED once the v2
    # plan is pinned (EXTEND_PLANNED), and sampling_plan_v2 already exists.
    with pytest.raises(SnapshotIntegrityError, match="COMPLETED"):
        write_core_plan_v2(
            config=config,
            manifest_path=pipeline["manifest_path"],
            gate_report_path=gate,
            clock=FIXED_CLOCK,
        )


def test_extension_fetch_merges_dedups_and_repostprocesses(pipeline) -> None:
    _complete_v1_pipeline(pipeline)
    gate = _write_gate_report(pipeline["tmp"], "NO_GO")
    config = _small_config(pipeline["pilot_path"], global_work_cap=2000)
    write_core_plan_v2(
        config=config,
        manifest_path=pipeline["manifest_path"],
        gate_report_path=gate,
        client=httpx.Client(transport=httpx.MockTransport(_extension_probe_handler(500))),
        clock=FIXED_CLOCK,
    )
    v1_works_bytes = (pipeline["raw_dir"] / "works.jsonl").read_bytes()
    bucket_records = _extension_bucket_records()
    calls = []
    fetched = _fetch(
        pipeline,
        config,
        _extension_fetch_handler(_extension_probe_handler(500), bucket_records, calls),
    )
    assert fetched["status"] == "FETCHED"
    execution = fetched["execution_extension"]
    # The recorded extension page count must equal the extension pages
    # actually cached on disk (regression: a fresh run previously recorded 0).
    cached_extension_pages = sum(
        1
        for path in sorted((pipeline["raw_dir"] / "pages").glob("page-*.json"))
        if json.loads(path.read_text(encoding="utf-8")).get("phase") == "extension"
    )
    assert execution["pages"] == cached_extension_pages == 8
    assert execution["duplicates"]["extension_records_already_in_snapshot"] == 1
    assert execution["duplicates"]["within_extension_duplicates"] == 2
    assert execution["per_bucket"]["1974"]["empty"] is True
    assert execution["new_works_added"] == 3
    assert execution["total_unique_works"] == 12
    assert set(calls) == {1972, 1973, 1974, 1975, 1976, 1977, 1978, 1979}
    merged = [
        json.loads(line)
        for line in (pipeline["raw_dir"] / "works.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(merged) == 12
    v1_ids = {
        json.loads(line)["id"] for line in v1_works_bytes.decode("utf-8").splitlines()
    }
    assert v1_ids <= {work["id"] for work in merged}
    manifest_now = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    pages = sorted((pipeline["raw_dir"] / "pages").glob("page-*.json"))
    assert len(pages) == len(manifest_now["artifacts"]["raw_pages"])

    exit_code, manifest = _postprocess(pipeline)
    assert exit_code == 0 and manifest["status"] == "COMPLETED"
    report = json.loads(pipeline["quality_path"].read_text(encoding="utf-8"))
    assert report["counts"]["works"] == 12
    assert report["sampling_execution"]["extension"]["new_works_added"] == 3
    works_ids = {
        json.loads(line)["id"]
        for line in (pipeline["processed_dir"] / "works.jsonl")
        .read_text(encoding="utf-8").splitlines()
    }
    assert "https://openalex.org/W555000001" in works_ids


def test_extension_fetch_rejects_edited_v2_plan(pipeline) -> None:
    _complete_v1_pipeline(pipeline)
    gate = _write_gate_report(pipeline["tmp"], "NO_GO")
    config = _small_config(pipeline["pilot_path"], global_work_cap=2000)
    write_core_plan_v2(
        config=config,
        manifest_path=pipeline["manifest_path"],
        gate_report_path=gate,
        client=httpx.Client(transport=httpx.MockTransport(_extension_probe_handler(500))),
        clock=FIXED_CLOCK,
    )
    manifest = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    manifest["sampling_plan_v2"]["recruitment"]["first_year"] = 1900
    pipeline["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError, match="v2 plan was edited"):
        _fetch(
            pipeline,
            config,
            _extension_fetch_handler(_extension_probe_handler(500), {}),
        )


def test_extension_cap_enforcement(pipeline) -> None:
    _complete_v1_pipeline(pipeline)
    gate = _write_gate_report(pipeline["tmp"], "NO_GO")
    config = _small_config(pipeline["pilot_path"], global_work_cap=12)
    # The projection (9 existing + 8 buckets x 200) exceeds the pinned cap, so
    # the extension plan must be refused before anything is pinned or fetched.
    with pytest.raises(SnapshotIntegrityError, match="exceeding the pinned"):
        write_core_plan_v2(
            config=config,
            manifest_path=pipeline["manifest_path"],
            gate_report_path=gate,
            client=httpx.Client(transport=httpx.MockTransport(_extension_probe_handler(500))),
            clock=FIXED_CLOCK,
        )
    manifest = json.loads(pipeline["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETED"
    assert "sampling_plan_v2" not in manifest


def test_cli_extend_plan_requires_completed_manifest(pipeline) -> None:
    config = _small_config(pipeline["pilot_path"])
    _plan(pipeline, config)
    gate = _write_gate_report(pipeline["tmp"], "NO_GO")
    argv = [
        "extend-plan",
        "--pilot-works",
        str(pipeline["pilot_path"]),
        "--pilot-manifest",
        str(pipeline["pilot_manifest"]),
        "--manifest",
        str(pipeline["manifest_path"]),
        "--gate-report",
        str(gate),
        "--per-year-sample-cap",
        "4",
        "--minimum-snapshot-works",
        "5",
        "--global-work-cap",
        "100",
        "--candidate-hub-count",
        "2",
        "--cohort-years",
        "2024",
        "--cohort-year-order",
        "2024",
        "--request-interval",
        "0",
    ]
    assert core_main(argv) == 1
