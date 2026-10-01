"""EXT-02 synthetic payloads/mocked HTTP; no live source requests or research labels."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from scholargraph.public_search.contracts import PublicSearchConfig, SearchRequest, load_config
from scholargraph.public_search.openalex import (
    OpenAlexSchemaError, PARSER_VERSION, SELECT_FIELDS,
    normalize_doi, parse_page, reconstruct_abstract, search,
)
from scholargraph.public_search.transport import Transport

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/public_search/sol/openalex_page.json"
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def payload():
    return json.loads(FIXTURE.read_bytes())


def body(row):
    return json.dumps(row, ensure_ascii=False).encode()


def request(**changes):
    row = dict(query="graph & C++ / Việt", sources=["openalex"], top_k=1,
               cap_per_source=2, year_from=None, year_to=None)
    row.update(changes)
    return SearchRequest.model_validate(row)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.waits.append(duration)
        self.now += duration


def transport(handler, config=None):
    cfg = load_config(ROOT / "configs/public_search.json") if config is None else config
    clock = Clock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Transport(cfg, client=client, clock=clock, sleeper=clock.sleep,
                     wall_clock=lambda: NOW, environ={}), clock, client


def page_response(row):
    return httpx.Response(200, headers={"content-type": "application/json"}, content=body(row))


def test_mapping_and_provenance():
    raw = FIXTURE.read_bytes()
    page = parse_page(raw, retrieved_at=NOW)
    assert page.count == 2 and page.per_page == 2
    first, title_only = page.records
    assert first.source_id == "W100" and first.abstract == "Graph mining Graph"
    assert first.doi == "10.1234/synthetic.a" and first.publication_year == 2024
    assert first.authors == ["Synthetic Author"] and first.citation_count == 0
    assert first.authors_availability == "known" and first.open_access_status == "open"
    assert first.venue == "Synthetic Venue" and first.license == "cc-by"
    assert first.missing_fields == ["arxiv_id"] and first.parser_version == PARSER_VERSION
    assert first.field_provenance["abstract"][0].raw_field == "abstract_inverted_index"
    assert first.field_provenance["doi"][0].raw_field == "doi"
    assert first.field_provenance["landing_url"][0].raw_field == "primary_location.landing_page_url"
    sha = hashlib.sha256(raw).hexdigest()
    assert page.raw_reference.raw_id == "openalex-" + sha
    assert page.raw_reference.byte_count == len(raw)
    assert all(r.raw_sha256 == sha for r in page.records)
    assert title_only.abstract is None and title_only.authors is None
    assert title_only.authors_availability == "missing"
    assert title_only.landing_url == "https://openalex.org/W101"
    assert set(title_only.field_provenance) == {"source_id", "title", "landing_url"}
    assert title_only.field_provenance["landing_url"][0].raw_field == "id"


def test_abstract_inverted_index_words_are_not_treated_as_leakage_labels():
    row = payload()
    row["results"] = [dict(row["results"][0], abstract_inverted_index={"labels": [0], "graph": [1]})]
    row["meta"] = dict(row["meta"], count=1, per_page=1, next_cursor=None)
    parsed = parse_page(body(row), retrieved_at=NOW)
    assert parsed.records[0].abstract == "labels graph"


@pytest.mark.parametrize("doi, expected", [
    (None, None), (" DOI: 10.1234/CASE ", "10.1234/case"),
    ("https://dx.doi.org/10.1234/Case", "10.1234/case"),
])
def test_doi_normalization(doi, expected):
    assert normalize_doi(doi) == expected


@pytest.mark.parametrize("doi", [True, 1, "", "made-up", "https://doi.org/10.1234/a?token=secret"])
def test_bad_doi(doi):
    with pytest.raises(ValueError):
        normalize_doi(doi)


@pytest.mark.parametrize("index", [
    {}, [], "text", {"a": []}, {"a": [True]}, {"a": [-1]}, {"a": [0.5]},
    {"a": [0, 0]}, {"a": [0], "b": [0]}, {"a": [1]}, {"a": [1000000000]},
    {"a": "0"}, {" ": [0]}, {"a": [0, 2]},
])
def test_bad_inverted_index(index):
    with pytest.raises(OpenAlexSchemaError):
        reconstruct_abstract(index)


@pytest.mark.parametrize("field,value", [
    ("id", None), ("id", "W100"), ("id", "https://evil.org/W100"), ("title", None),
    ("title", " "), ("publication_year", True), ("publication_year", "2024"),
    ("publication_year", 1799), ("cited_by_count", -1), ("cited_by_count", True),
    ("doi", "invalid"), ("authorships", {}), ("authorships", [{"author": {}}]),
    ("authorships", [{"author": {"display_name": 7}}]), ("primary_location", []),
    ("primary_location", {"pdf_url": "javascript:alert(1)"}),
    ("primary_location", {"landing_page_url": "https://user:secret@example.org"}),
    ("primary_location", {"source": {"display_name": False}}),
    ("primary_location", {"license": 4}), ("open_access", {"is_oa": 1}),
    ("open_access", {"oa_status": "unexpected"}),
    ("open_access", {"is_oa": False, "oa_status": "gold"}),
    ("relevance_score", True), ("relevance_score", "1.0"),
    ("relevance_score", -1), ("relevance_score", float("inf")),
])
def test_present_malformed_metadata_fails_whole_page(field, value, tmp_path):
    row = payload()
    row["results"][1][field] = value
    path = tmp_path / "synthetic-malformed.json"
    path.write_bytes(body(row))
    with pytest.raises(OpenAlexSchemaError):
        parse_page(path.read_bytes(), retrieved_at=NOW)


@pytest.mark.parametrize("field", ["id", "title"])
def test_missing_required_record(tmp_path, field):
    row = payload()
    del row["results"][1][field]
    path = tmp_path / "synthetic-missing.json"
    path.write_bytes(body(row))
    with pytest.raises(OpenAlexSchemaError) as exc:
        parse_page(path.read_bytes(), retrieved_at=NOW)
    assert exc.value.record_index == 1


def test_explicit_null_and_known_empty_authors():
    row = payload()
    row["results"][0] = dict(id="https://openalex.org/W100", title="Synthetic",
                             abstract_inverted_index=None, doi=None, primary_location=None,
                             publication_year=None, cited_by_count=None, open_access=None,
                             authorships=[])
    record = parse_page(body(row), retrieved_at=NOW).records[0]
    assert record.authors == [] and record.authors_availability == "known"
    assert "authors" not in record.missing_fields and "authors" in record.field_provenance


@pytest.mark.parametrize("flag,status,expected", [(False, "closed", "closed"), (None, "unknown", "unknown"),
                                                (None, "green", "open"), (True, None, "open")])
def test_oa_states(flag, status, expected):
    row = payload()
    row["results"][0]["open_access"] = {"is_oa": flag, "oa_status": status}
    assert parse_page(body(row), retrieved_at=NOW).records[0].open_access_status == expected


@pytest.mark.parametrize("raw", [b"not JSON", b"[]", b"{}", b'{"meta":{},"results":[]}',
                                 b'{"meta":{},"meta":{},"results":[]}', b'{"meta":{"count":NaN}}'])
def test_malformed_json(raw, tmp_path):
    path = tmp_path / "malformed.body"
    path.write_bytes(raw)
    with pytest.raises(OpenAlexSchemaError):
        parse_page(path.read_bytes(), retrieved_at=NOW)


def test_search_params_order_raw_and_top_k_not_pool_cap():
    seen = []
    def handler(req):
        seen.append(req)
        return page_response(payload())
    t, c, client = transport(handler)
    with client:
        found = search(request(), t)
    assert found.status == "success" and len(found.records) == 2
    assert [r.source_id for r in found.records] == ["W100", "W101"]
    assert found.source_total == 2 and found.truncated is False and found.elapsed_seconds == c.now
    assert seen[0].url.params["search"] == "graph & C++ / Việt"
    assert seen[0].url.params["cursor"] == "*" and seen[0].url.params["per_page"] == "2"
    assert seen[0].url.params["select"] == ",".join(SELECT_FIELDS)
    assert found.records[0].raw_sha256 == found.raw_references[0].sha256


def test_unselected_no_transport_access():
    class NoTransport:
        def __getattr__(self, _):
            pytest.fail("unselected source must not even inspect transport")
    found = search(request(sources=["arxiv"]), NoTransport())
    assert found.status == "not_requested" and found.filter_coverage == "none"
    assert found.elapsed_seconds is None and not found.raw_references


def test_valid_empty():
    row = {"meta": {"count": 0, "per_page": 2}, "results": []}
    t, _, client = transport(lambda _: page_response(row))
    with client:
        found = search(request(), t)
    assert found.status == "empty" and found.source_total == 0 and found.truncated is False
    assert found.error is None and len(found.raw_references) == 1


def cursor_payload(start, n, per_page, total, cursor):
    return {"synthetic": True, "meta": {"count": total, "per_page": per_page, "next_cursor": cursor},
            "results": [{"id": f"https://openalex.org/W{start+i}", "title": f"Synthetic {start+i}"} for i in range(n)]}


def test_cursor_pool_bound_shared_deadline():
    seen = []
    def handler(req):
        seen.append(req)
        if len(seen) == 1:
            return page_response(cursor_payload(100, 25, 25, 1000, "next"))
        return page_response(cursor_payload(125, 5, 5, 1000, "unused"))
    t, c, client = transport(handler)
    deadline = t.deadline()
    with client:
        found = search(request(cap_per_source=30), t)
    assert found.status == "success" and len(found.records) == 30 and found.source_total == 1000
    assert found.truncated is True and len(found.raw_references) == 2
    assert [r.source_id for r in found.records] == [f"W{i}" for i in range(100, 130)]
    assert seen[1].url.params["per_page"] == "5" and seen[1].url.params["cursor"] == "next"
    assert t.deadline() == deadline and c.waits == [1.0]


@pytest.mark.parametrize("mutation", ["missing_cursor", "null_cursor", "repeat_cursor", "repeated_body",
                                    "duplicate_ids", "drift_count", "short_page", "wrong_per_page"])
def test_pagination_failures(mutation):
    seen = []
    first = cursor_payload(100, 25, 25, 1000, "next")
    second = cursor_payload(125, 25, 25, 1000, "unused")
    if mutation == "missing_cursor": del first["meta"]["next_cursor"]
    if mutation == "null_cursor": first["meta"]["next_cursor"] = None
    if mutation == "repeat_cursor": first["meta"]["next_cursor"] = "*"
    if mutation == "repeated_body": second = first
    if mutation == "duplicate_ids": second["results"][0]["id"] = first["results"][0]["id"]
    if mutation == "drift_count": second["meta"]["count"] = 1001
    if mutation == "short_page": first["results"] = first["results"][:1]
    if mutation == "wrong_per_page": first["meta"]["per_page"] = 26
    def handler(req):
        seen.append(req)
        return page_response(first if len(seen) == 1 else second)
    t, _, client = transport(handler)
    with client:
        found = search(request(cap_per_source=50), t)
    assert found.status == "failed" and found.error.kind == "schema"
    assert not found.records and found.truncated is None
    assert len(seen) <= 2 and found.raw_references


def test_schema_failure_retains_raw_and_index_redacts():
    row = payload()
    row["results"][1]["title"] = None
    row["error_secret"] = "do-not-echo"
    t, _, client = transport(lambda _: page_response(row))
    with client:
        found = search(request(), t)
    assert found.status == "failed" and found.error.record_index == 1
    assert not found.records and len(found.raw_references) == 1
    assert "do-not-echo" not in found.error.message


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (429, "quota"), (502, "upstream")])
def test_transport_errors(status, kind):
    seen = []
    def handler(req):
        seen.append(req)
        return httpx.Response(status, headers={"retry-after": "31"}, text="do-not-echo")
    t, _, client = transport(handler)
    with client:
        found = search(request(), t)
    assert found.status == "failed" and found.error.kind == kind and not found.records
    assert len(seen) == 1 and "do-not-echo" not in found.error.message


def test_timeout_shared_across_pages():
    calls = []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return page_response(cursor_payload(100, 25, 25, 1000, "next"))
        raise httpx.ReadTimeout("secret-upstream", request=req)
    t, _, client = transport(handler)
    with client:
        found = search(request(cap_per_source=30), t)
    assert found.status == "failed" and found.error.kind == "timeout" and not found.records
    assert len(found.raw_references) == 1 and "secret" not in found.error.message


@pytest.mark.parametrize("kind", ["policy", "auth"])
def test_missing_policy_or_required_auth_before_network(kind):
    row = load_config(ROOT / "configs/public_search.json").model_dump()
    p = row["sources"]["openalex"]
    if kind == "policy": p.update(source_policy_verified=False, policy_evidence_sha256=None)
    else: p.update(auth_mode="bearer", key_env="SYNTHETIC_TEST_KEY")
    t, _, client = transport(lambda _: pytest.fail("no network"), PublicSearchConfig.model_validate(row))
    with client:
        found = search(request(), t)
    assert found.status == "failed" and found.error.kind == kind and found.source_total is None


def test_boundary_subprocess(tmp_path):
    path = tmp_path / "synthetic.body"
    # In-process paths are set explicitly in the child; no editable-install fallback.
    entry = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('scholargraph.public_search.openalex',run_name='__main__')"
    command = [sys.executable, "-c", entry, str(ROOT / "src"), "--payload", str(path)]
    missing = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert missing.returncode == 1 and "FAIL" in missing.stderr
    path.write_bytes(FIXTURE.read_bytes())
    good = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert good.returncode == 0 and json.loads(good.stdout)["records"] == 2
    path.write_bytes(body({"meta": {"count": 0, "per_page": 2}, "results": []}))
    empty = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert empty.returncode == 0 and json.loads(empty.stdout)["records"] == 0
    row = payload()
    del row["meta"]["count"]
    path.write_bytes(body(row))
    bad_meta = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad_meta.returncode == 1 and "FAIL" in bad_meta.stderr
    row = payload()
    del row["results"][1]["title"]
    row["results"][1]["abstract_inverted_index"] = {"abstract-only": [0]}
    path.write_bytes(body(row))
    bad_title = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad_title.returncode == 1
    row = payload()
    row["results"][0]["abstract_inverted_index"] = {"bad": [True]}
    path.write_bytes(body(row))
    bad_index = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad_index.returncode == 1
    row = payload()
    row["results"][0]["relevance_score"] = "pretend-score"
    path.write_bytes(body(row))
    bad_score = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad_score.returncode == 1
    row = payload()
    row["metadata"] = {"qrels": "SYNTHETIC FORBIDDEN SENTINEL"}
    path.write_bytes(body(row))
    bad_labels = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert bad_labels.returncode == 1


def test_search_does_not_open_files(monkeypatch):
    row = payload()
    t, _, client = transport(lambda _: page_response(row))
    def forbidden(*_args, **_kwargs):
        pytest.fail("adapter may not read labels, held-out, or any filesystem input")
    monkeypatch.setattr(Path, "open", forbidden)
    with client:
        assert search(request(), t).status == "success"


@pytest.mark.parametrize("bounds, expected", [
    ((2020, 2025), "publication_year:2020-2025"),
    ((2020, None), "publication_year:2020-2100"),
    ((None, 2025), "publication_year:1800-2025"),
])
def test_year_filter_sent_and_checked(bounds, expected):
    row = payload()
    row["results"][1]["publication_year"] = 2024
    seen = []
    def handler(req):
        seen.append(req)
        return page_response(row)
    t, _, client = transport(handler)
    with client:
        found = search(request(year_from=bounds[0], year_to=bounds[1]), t)
    assert found.status == "success" and found.filter_coverage == "server"
    assert seen[0].url.params["filter"] == expected


@pytest.mark.parametrize("year", [None, 2010, 2026])
def test_server_filter_violation_not_silently_dropped(year):
    row = payload()
    row["results"][1]["publication_year"] = year
    t, _, client = transport(lambda _: page_response(row))
    with client:
        found = search(request(year_from=2020, year_to=2025), t)
    assert found.status == "failed" and not found.records and found.error.record_index == 1
    assert len(found.raw_references) == 1


@pytest.mark.parametrize("field", ["qrels", "labels", "held_out", "heldout", "test_labels", "dev_labels"])
def test_label_metadata_is_rejected_in_temp(field, tmp_path):
    row = payload()
    row["results"][0]["metadata"] = {field: "SYNTHETIC FORBIDDEN SENTINEL"}
    path = tmp_path / "leakage-synthetic.json"
    path.write_bytes(body(row))
    with pytest.raises(OpenAlexSchemaError, match="label/held-out"):
        parse_page(path.read_bytes(), retrieved_at=NOW)


def test_duplicate_id_within_page_fails():
    row = payload()
    row["results"][1]["id"] = row["results"][0]["id"]
    with pytest.raises(OpenAlexSchemaError) as exc:
        parse_page(body(row), retrieved_at=NOW)
    assert exc.value.record_index == 1


@pytest.mark.parametrize("key, value", [("count", None), ("count", True), ("count", -1),
                                      ("per_page", True), ("per_page", 0), ("page", True)])
def test_invalid_meta_types(key, value):
    row = payload()
    row["meta"][key] = value
    with pytest.raises(OpenAlexSchemaError):
        parse_page(body(row), retrieved_at=NOW)


def test_deadline_expires_before_next_page():
    calls = []
    def handler(req):
        calls.append(req)
        return page_response(cursor_payload(100, 25, 25, 1000, "next"))
    row = load_config(ROOT / "configs/public_search.json").model_dump()
    row["deadline_seconds"] = 0.5
    t, _, client = transport(handler, PublicSearchConfig.model_validate(row))
    with client:
        found = search(request(cap_per_source=30), t)
    assert found.status == "failed" and found.error.kind == "timeout"
    assert len(calls) == 1 and len(found.raw_references) == 1 and not found.records


def test_second_page_record_index_is_global():
    calls = []
    first = cursor_payload(100, 25, 25, 1000, "next")
    second = cursor_payload(125, 5, 5, 1000, None)
    del second["results"][2]["title"]
    def handler(req):
        calls.append(req)
        return page_response(first if len(calls) == 1 else second)
    t, _, client = transport(handler)
    with client:
        found = search(request(cap_per_source=30), t)
    assert found.status == "failed" and found.error.record_index == 27
    assert len(found.raw_references) == 2 and not found.records


def test_returned_transport_hash_is_checked():
    from scholargraph.public_search.transport import TransportResponse
    class BadTransport:
        clock = staticmethod(lambda: 0.0)
        wall_clock = staticmethod(lambda: NOW)
        deadline = staticmethod(lambda: 30.0)
        def get(self, *_args, **_kwargs):
            return TransportResponse(FIXTURE.read_bytes(), "0" * 64, "application/json", 0.0, 1)
    found = search(request(), BadTransport())
    assert found.status == "failed" and found.error.kind == "schema"
    assert found.raw_references[0].sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
