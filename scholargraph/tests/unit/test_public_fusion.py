"""Synthetic-only hand arithmetic and adversarial tests for EXT-04B."""
import json
import os
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path
import subprocess
import sys

import pytest

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchError, SearchRequest,
    SourceResult, overall_status,
)
from scholargraph.public_search.fusion import FusionError, arxiv_base_id, fuse, normalize_doi

SHA = "a" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")


def request(**changes):
    row = dict(query="synthetic graph", sources=["openalex", "arxiv"], top_k=50,
               cap_per_source=50, year_from=None, year_to=None)
    row.update(changes)
    return SearchRequest.model_validate(row)


def paper(source="openalex", source_id="W1", **changes):
    row = dict(source=source, source_id=source_id, title="Synthetic title",
               landing_url="https://example.org/paper", retrieved_at=NOW,
               raw_sha256=SHA, parser_version="synthetic-1")
    row.update({field: None for field in NULLABLE})
    row.update(changes)
    row["authors_availability"] = "missing" if row["authors"] is None else "known"
    row["missing_fields"] = [field for field in NULLABLE if row[field] is None]
    row["field_provenance"] = {
        field: [FieldEvidence(source=source, source_id=source_id, raw_sha256=SHA, raw_field=field)]
        for field in ("source_id", "title", "landing_url", *NULLABLE) if row[field] is not None}
    return PaperRecord.model_validate(row)


def result(source="openalex", records=None, status=None):
    records = [] if records is None else records
    status = ("success" if records else "empty") if status is None else status
    return SourceResult(source=source, status=status, records=records,
        error=SearchError(kind="timeout", message="synthetic timeout", source=source,
                          retry_after_seconds=None, record_index=None) if status == "failed" else None,
        source_total=len(records) if status in {"success", "empty"} else None,
        elapsed_seconds=0.1 if status != "not_requested" else None,
        filter_coverage="none", truncated=False if status != "not_requested" else None,
        raw_references=[RawReference(raw_id=source + "-" + SHA, sha256=SHA, byte_count=1)] if records else [])


def single(records, **changes):
    return fuse([result(records=records)], request(sources=["openalex"], **changes))


def test_hand_rrf_best_original_rank_counts_and_topk():
    rows = [result(records=[paper(doi="10.1234/a"), paper(source_id="W2", doi="10.1234/b"),
                            paper(source_id="W3", doi="10.1234/a")]),
            result("arxiv", [paper("arxiv", "2401.00001v1", doi="10.1234/b"),
                             paper("arxiv", "2401.00002v1", doi="10.1234/a")])]
    output = fuse(rows, request(top_k=1))
    assert output.hits[0].canonical_id == "doi:10.1234/a"  # equal scores, canonical tie
    assert output.hits[0].score == 1/61 + 1/62
    assert output.hits[0].source_ranks == {"arxiv": 2, "openalex": 1}
    assert len(output.hits[0].source_records) == 3
    assert output.counts.model_dump() == dict(raw=5, valid=5, invalid=0, excluded_by_year=0,
                                            eligible=5, groups=2, duplicate_excess=3, returned=1)
    assert output.hits[0].display.source == "openalex"


def test_filter_keeps_original_rank_and_all_filtered_is_empty():
    records = [paper(source_id="W0", publication_year=None),
               paper(source_id="W1", publication_year=1999),
               paper(source_id="W2", publication_year=2020),
               paper(source_id="W3", publication_year=2025)]
    output = single(records, year_from=2020, year_to=2025)
    assert [h.score for h in output.hits] == [1/63, 1/64]
    assert output.counts.excluded_by_year == 2
    assert output.counts.eligible == 2
    empty = single(records, year_from=2030)
    assert empty.hits == [] and empty.counts.excluded_by_year == 4


@pytest.mark.parametrize("year,lower,upper,accepted", [
    (None, None, None, True), (None, 2020, None, False), (None, None, 2020, False),
    (2020, 2020, 2020, True), (2019, 2020, None, False), (2021, None, 2020, False)])
def test_year_bounds(year, lower, upper, accepted):
    output = single([paper(publication_year=year)], year_from=lower, year_to=upper)
    assert output.counts.returned == int(accepted)


def test_same_title_different_doi_and_no_ids_do_not_merge():
    output = single([paper(source_id="W1", doi="10.1234/a"),
                     paper(source_id="W2", doi="10.1234/b"), paper(source_id="W3")])
    assert output.counts.groups == 3
    assert {h.canonical_id for h in output.hits} == {"doi:10.1234/a", "doi:10.1234/b", "openalex:W3"}


def test_versions_unique_doi_and_same_source_duplicates_merge():
    rows = [paper("arxiv", "2401.00001v2", arxiv_id="2401.00001v2", doi="10.1234/A"),
            paper("arxiv", "2401.00001v1", arxiv_id="2401.00001v1"),
            paper("arxiv", "2401.00001v1", arxiv_id="2401.00001v1", title="Changed title")]
    before = [r.model_dump_json() for r in rows]
    output = fuse([result("arxiv", rows)], request(sources=["arxiv"]))
    hit = output.hits[0]
    assert hit.canonical_id == "doi:10.1234/a" and hit.score == 1/61
    assert hit.display.source_id == "2401.00001v1"
    assert len(hit.source_records) == 3 and "title" in hit.conflicts and "arxiv_id" in hit.conflicts
    assert [r.model_dump_json() for r in rows] == before
    assert hit.display in rows


def test_multi_doi_does_not_bridge_and_exposes_conflicts():
    rows = [paper("arxiv", "2401.00001v1", arxiv_id="2401.00001v1", doi="10.1234/a"),
            paper("arxiv", "2401.00001v2", arxiv_id="2401.00001v2", doi="10.1234/b"),
            paper("arxiv", "2401.00001v3", arxiv_id="2401.00001v3")]
    output = fuse([result("arxiv", rows)], request(sources=["arxiv"]))
    assert output.counts.groups == 3 and output.counts.duplicate_excess == 0
    assert {h.canonical_id for h in output.hits} == {"doi:10.1234/a", "doi:10.1234/b", "arxiv:2401.00001"}
    for hit in output.hits:
        assert len(hit.conflicts["doi"]) == 2
        assert len(hit.source_records) == 1


def test_shared_source_id_with_disagreeing_doi_stays_split():
    records = [paper(doi="10.1234/a"), paper(doi="10.1234/b"), paper()]
    for i, record in enumerate(records[:2]):
        record.field_provenance["doi"] = [FieldEvidence(source="openalex", source_id="W1",
            raw_sha256=SHA, raw_field=f"results[{i}].doi")]
    output = single(records)
    assert output.counts.groups == 3
    assert all(len(h.conflicts["doi"]) == 2 for h in output.hits)


def test_filter_precedes_alias_conflict_resolution():
    output = single([paper(arxiv_id="2401.00001v1", doi="10.1234/a", publication_year=2020),
                     paper(source_id="W2", arxiv_id="2401.00001v2", doi="10.1234/b", publication_year=2010),
                     paper(source_id="W3", arxiv_id="2401.00001v3", publication_year=2020)], year_from=2020)
    assert output.counts.groups == 1 and output.counts.excluded_by_year == 1
    assert output.hits[0].canonical_id == "doi:10.1234/a"


def test_alias_chain_with_multiple_doi_is_not_transitive_doi_merge():
    rows = [paper(source_id="W1", arxiv_id="2401.00001v1", doi="10.1234/a"),
            paper(source_id="W1", arxiv_id="2401.00002v1"),
            paper(source_id="W2", arxiv_id="2401.00002v1", doi="10.1234/b"),
            paper(source_id="W3", arxiv_id="2401.00001v2")]
    output = single(rows)
    assert output.counts.groups == 3 and output.counts.duplicate_excess == 1
    ambiguous = next(h for h in output.hits if h.canonical_id.startswith("arxiv:"))
    assert len(ambiguous.source_records) == 2 and len(ambiguous.conflicts["doi"]) == 2


def test_display_is_whole_record_and_missing_fields_not_filled():
    oa = paper(doi="10.1234/A", authors=[])
    ax = paper("arxiv", "2401.00001v2", doi="10.1234/a", abstract="Only arXiv abstract",
               publication_year=2025, arxiv_id="2401.00001v2")
    output = fuse([result(records=[oa]), result("arxiv", [ax])], request())
    hit = output.hits[0]
    assert hit.display == oa and hit.display.abstract is None and hit.display.publication_year is None
    assert hit.display.authors == [] and hit.display.authors_availability == "known"
    assert "abstract" in hit.display.missing_fields and hit.source_records == [oa, ax]
    assert "doi" not in hit.conflicts  # DOI capitalization is identity normalization
    assert all(e.source == "openalex" for items in hit.display.field_provenance.values() for e in items)


@pytest.mark.parametrize("field,value", [("status", "empty"), ("source_total", -1),
    ("elapsed_seconds", float("inf")), ("elapsed_seconds", None), ("truncated", 1),
    ("raw_references", []), ("qrels", {}), ("records", "text only")])
def test_source_model_copy_cannot_bypass_schema(field, value):
    bad = result(records=[paper()]).model_copy(update={field: value})
    with pytest.raises(FusionError):
        fuse([bad], request(sources=["openalex"]))


def test_typed_boundaries_and_request_mutable_sources():
    with pytest.raises(FusionError): fuse([], {})
    with pytest.raises(FusionError): fuse([{}], request())
    with pytest.raises(FusionError): fuse((), request())
    req = request(sources=["openalex"])
    req.sources.append("openalex")
    with pytest.raises(FusionError): fuse([result()], req)


def test_exact_duplicates_keep_count_and_evidence_without_score_inflation():
    row = paper()
    output = single([row, row])
    assert output.hits[0].source_records == [row, row]
    assert output.hits[0].score == 1/61 and output.counts.duplicate_excess == 1


def test_full_pool_cap_and_topk_count_identities():
    rows = [result(source, [paper(source, str(i), doi=f"10.1234/{i}") for i in range(50)])
            for source in ["arxiv", "openalex"]]
    output = fuse(rows, request(top_k=7))
    assert output.counts.model_dump() == dict(raw=100, valid=100, invalid=0, excluded_by_year=0,
                                            eligible=100, groups=50, duplicate_excess=50, returned=7)
    assert [h.rank for h in output.hits] == list(range(1, 8))
    assert output.hits[0].score == 2/61


def test_source_result_permutations_and_duplicate_order_are_deterministic():
    a = paper(doi="10.1234/a", title="A")
    b = paper(doi="10.1234/a", title="B")
    other = result("arxiv", [paper("arxiv", "2401.00001v1", doi="10.1234/a")])
    expected = fuse([result(records=[a, b]), other], request())
    for duplicates in permutations([a, b]):
        for sources in permutations([result(records=list(duplicates)), other]):
            assert fuse(list(sources), request()) == expected
    reversed_ranks = single([paper(source_id="W2"), paper()])
    assert reversed_ranks.hits[0].canonical_id == "openalex:W2"


@pytest.mark.parametrize("states,expected", [
    (("empty", "empty"), "empty"), (("failed", "empty"), "partial_failure"),
    (("failed", "failed"), "failed"), (("success", "failed"), "partial_failure"),
    (("success", "empty"), "success")])
def test_failed_empty_states_and_no_fabricated_counts(states, expected):
    rows = [result(s, [paper(s)] if state == "success" else [], state)
            for s, state in zip(["openalex", "arxiv"], states)]
    output = fuse(rows, request())
    assert overall_status(rows, request(), len(output.hits)) == expected
    assert output.counts.raw == sum(len(r.records) for r in rows)


def test_not_selected_is_valid_only_when_not_attempted():
    rows = [result(records=[paper()]), result("arxiv", status="not_requested")]
    assert fuse(rows, request(sources=["openalex"])).counts.raw == 1
    with pytest.raises(FusionError):
        fuse(rows, request())


@pytest.mark.parametrize("rows", [[], [result(), result()], [result("arxiv")]])
def test_missing_duplicate_or_wrong_selected_source(rows):
    with pytest.raises(FusionError):
        fuse(rows, request(sources=["openalex"]))


def test_unselected_attempted_and_cap_total_violation():
    with pytest.raises(FusionError):
        fuse([result(), result("arxiv")], request(sources=["openalex"]))
    with pytest.raises(FusionError):
        single([paper(), paper(source_id="W2")], cap_per_source=1)
    bad = result(records=[paper()]).model_copy(update={"source_total": 0})
    with pytest.raises(FusionError):
        fuse([bad], request(sources=["openalex"]))


@pytest.mark.parametrize("field,value", [
    ("title", None), ("title", ""), ("publication_year", True), ("publication_year", "2020"),
    ("publication_year", 1799), ("citation_count", -1), ("citation_count", float("nan")),
    ("landing_url", "javascript:alert(1)"), ("authors", [True]), ("doi", "https://doi.org/10.1234/a"),
    ("arxiv_id", "arbitrary"), ("arxiv_id", "2401.00001v0"), ("raw_sha256", "bad"),
    ("qrels", {}), ("labels", {}), ("held_out", []), ("rank", 0), ("rank", -1),
    ("score", float("inf")), ("score", float("nan"))])
def test_construct_and_mutable_nested_bypass_rejected(field, value):
    row = paper().model_dump()
    row[field] = value
    forged = (paper().model_copy(update={field: value}) if field not in PaperRecord.model_fields
              else PaperRecord.model_construct(**row))
    bad = result(records=[paper()])
    bad.records[0] = forged
    with pytest.raises(FusionError):
        fuse([bad], request(sources=["openalex"]))


def test_nested_evidence_mutation_and_missing_construct_field_rejected():
    bad = result(records=[paper()])
    bad.records[0].field_provenance["title"][0].__dict__["source_id"] = "wrong"
    with pytest.raises(FusionError):
        fuse([bad], request(sources=["openalex"]))


def test_mutated_noncanonical_text_is_not_silently_rewritten():
    bad = result(records=[paper().model_copy(update={"title": "  Changed  "})])
    with pytest.raises(FusionError):
        fuse([bad], request(sources=["openalex"]))
    req = request().model_copy(update={"sources": ["openalex", "arxiv"]})
    with pytest.raises(FusionError):
        fuse([result(), result("arxiv")], req)
    row = paper().model_dump(); del row["title"]
    bad.records[0] = PaperRecord.model_construct(**row)
    with pytest.raises(FusionError):
        fuse([bad], request(sources=["openalex"]))


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), "1"])
def test_request_mutation_invalid_budget(value):
    with pytest.raises(FusionError):
        fuse([result()], request(sources=["openalex"]).model_copy(update={"top_k": value}))


@pytest.mark.parametrize("raw", ["  DOI: 10.1234/ABC ", "https://doi.org/10.1234/ABC", "http://dx.doi.org/10.1234/ABC"])
def test_normalize_explicit_doi(raw):
    assert normalize_doi(raw) == "10.1234/abc"


@pytest.mark.parametrize("raw", [True, "bad", "10.1234/with space", "https://evil.org/10.1234/a",
                                 "https://doi.org/10.1234/a?token=hidden", "https://doi.org:bad/10.1234/a"])
def test_bad_doi(raw):
    with pytest.raises(FusionError): normalize_doi(raw)


@pytest.mark.parametrize("raw,expected", [("2401.00001v2", "2401.00001"),
                                          ("hep-th/9901001v10", "hep-th/9901001"), ("math.GT/0301001", "math.gt/0301001")])
def test_arxiv_base(raw, expected):
    assert arxiv_base_id(raw) == expected


def test_legacy_canonical_is_base_id_even_with_uppercase_source_id():
    rows = [paper("arxiv", "math.GT/0301001v2", arxiv_id="math.GT/0301001v2"),
            paper("arxiv", "math.GT/0301001v1", arxiv_id="math.GT/0301001v1")]
    output = fuse([result("arxiv", rows)], request(sources=["arxiv"]))
    assert output.counts.groups == 1 and output.hits[0].canonical_id == "arxiv:math.gt/0301001"
    assert {r.arxiv_id for r in output.hits[0].source_records} == {"math.GT/0301001v1", "math.GT/0301001v2"}


def run_cli(tmp_path, request_text=None, results_text=None, extra=()):
    req = tmp_path / "request.json"; src = tmp_path / "sources.json"
    if request_text is not None: req.write_text(request_text, encoding="utf-8")
    if results_text is not None: src.write_text(results_text, encoding="utf-8")
    return subprocess.run([sys.executable, "-m", "scholargraph.public_search.fusion",
                           "--request", str(req), "--source-results", str(src), *extra],
                          text=True, capture_output=True, timeout=20, env=os.environ.copy())


def wire(rows):
    return "[" + ",".join(row.model_dump_json() for row in rows) + "]"


@pytest.mark.parametrize("state,code", [("success", 0), ("empty", 0), ("failed", 1)])
def test_cli_valid_states(tmp_path, state, code):
    rows = [result(records=[paper()] if state == "success" else [], status=state)]
    run = run_cli(tmp_path, request(sources=["openalex"]).model_dump_json(), wire(rows))
    assert run.returncode == code
    output = json.loads(run.stdout)
    assert output["counts"]["returned"] == int(state == "success")


@pytest.mark.parametrize("case", ["missing_request", "missing_results", "syntax", "duplicate", "nonfinite",
                                 "missing_title", "text_only", "bad_year", "labels", "held_out", "rank",
                                 "missing_source", "args", "wrong_root"])
def test_cli_adversarial_tmp_path(tmp_path, case):
    req = request(sources=["openalex"]).model_dump_json()
    rows = json.loads(wire([result(records=[paper()])]))
    extra = ()
    if case == "missing_request": req = None
    elif case == "missing_results": rows = None
    elif case == "syntax": req = '{"query":'
    elif case == "duplicate": req = req[:-1] + ',"query":"SENTINEL_SECRET"}'
    elif case == "nonfinite": req = req.replace('"top_k":50', '"top_k":NaN')
    elif case in {"missing_title", "text_only"}:
        del rows[0]["records"][0]["title"]
        if case == "text_only": rows[0]["records"][0]["abstract"] = "SENTINEL_SECRET"
    elif case == "bad_year": rows[0]["records"][0]["publication_year"] = True
    elif case in {"labels", "held_out", "rank"}: rows[0]["records"][0][case] = "SENTINEL_SECRET"
    elif case == "missing_source": rows = []
    elif case == "args": extra = ("--unknown", "SENTINEL_SECRET")
    elif case == "wrong_root": rows = {}
    run = run_cli(tmp_path, req, None if rows is None else json.dumps(rows), extra)
    assert run.returncode == 1 and run.stderr.startswith("FAIL:")
    assert "SENTINEL_SECRET" not in run.stdout + run.stderr and "Traceback" not in run.stderr


def test_cli_no_args_is_exit1():
    run = subprocess.run([sys.executable, "-m", "scholargraph.public_search.fusion"],
                         capture_output=True, text=True, timeout=20)
    assert run.returncode == 1 and run.stderr.startswith("FAIL:")


def test_cli_partial_failure_retains_valid_hits_but_exit1(tmp_path):
    run = run_cli(tmp_path, request().model_dump_json(),
                  wire([result(records=[paper()]), result("arxiv", status="failed")]))
    assert run.returncode == 1 and json.loads(run.stdout)["counts"]["returned"] == 1
    assert run.stderr == "FAIL: selected source failed\n"


def test_cli_synthetic_fixture_and_hand_expected(tmp_path):
    root = Path(__file__).resolve().parents[1] / "fixtures/public_search/sol/fusion"
    fixture = json.loads((root / "hand_rrf.json").read_text(encoding="utf-8"))
    sidecar = json.loads((root / "hand_rrf.sidecar.json").read_text(encoding="utf-8"))
    assert sidecar["synthetic"] and sidecar["not_live_evidence"] and sidecar["not_for_production_fallback"]
    run = run_cli(tmp_path, json.dumps(fixture["request"]), json.dumps(fixture["source_results"]))
    assert run.returncode == 0
    output = json.loads(run.stdout)
    assert output["counts"] == fixture["expected_counts"]
    assert [h["canonical_id"] for h in output["hits"]] == ["doi:10.1234/a", "doi:10.1234/b"]
    assert [h["score"] for h in output["hits"]] == [1/61 + 1/62, 1/61 + 1/62]


def test_fuse_has_no_file_or_network_access(monkeypatch, tmp_path):
    (tmp_path / "held_out.json").write_text("SENTINEL_SECRET", encoding="utf-8")
    rows = [result(records=[paper()])]
    req = request(sources=["openalex"])
    import socket
    def denied(*args, **kwargs):
        raise AssertionError("unexpected resource access")
    monkeypatch.setattr(Path, "open", denied)
    monkeypatch.setattr("builtins.open", denied)
    monkeypatch.setattr(socket, "socket", denied)
    assert fuse(rows, req).counts.returned == 1
