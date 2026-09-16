"""SG-014 graph feasibility gate: unit, adversarial and CLI subprocess tests.

All fixtures are synthetic and written into pytest ``tmp_path``; none of them
touches the real OpenAlex/BEIR snapshots.  Per ADR-013/ADR-014 every fatal
input problem (missing resource, malformed JSONL, duplicate IDs, invalid
fields, manifest hash mismatch) must surface as an explicit failure with CLI
exit code 1 and must never be replaced by a fabricated measurement.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scholargraph.graph.feasibility import (
    FeasibilityError,
    beir_corpus_stats,
    canonical_work_id,
    compute_mapping,
    compute_snapshot_stats,
    evaluate_cohorts,
    evaluate_gate,
    load_floors,
    normalize_doi,
    normalize_title,
    parse_beir_corpus,
    parse_works,
    run_feasibility,
)

SNAPSHOT_YEAR = 2026

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def make_work(
    wid: str,
    *,
    title: str | None = None,
    abstract: dict | None = {"word": [0]},
    year: int | None = 2020,
    doi: str | None = None,
    refs: tuple[str, ...] = (),
    venue: bool = True,
    **overrides: object,
) -> dict:
    if title is None:
        title = "Title " + wid
    record: dict = {
        "id": f"https://openalex.org/{wid}",
        "title": title,
        "abstract_inverted_index": abstract,
        "publication_year": year,
        "doi": doi,
        "referenced_works": [f"https://openalex.org/{ref}" for ref in refs],
    }
    record["primary_location"] = (
        {"source": {"display_name": f"Venue of {wid}"}} if venue
        else {"landing_page_url": "https://example.org"}
    )
    record.update(overrides)
    return record


def write_jsonl(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_protocol(
    tmp_path: Path,
    *,
    min_dev: int = 30,
    min_test: int = 50,
    min_refs: int = 2,
    min_candidates: int = 100,
    **extra: object,
) -> Path:
    protocol = {
        "tracks": {
            "B": {
                "graph_gate": {
                    "minimum_dev_queries": min_dev,
                    "minimum_test_queries": min_test,
                    "minimum_eligible_references": min_refs,
                    "minimum_novel_candidates_per_query": min_candidates,
                    "test_year_rule": "synthetic_test_rule",
                    "dev_year_rule": "synthetic_dev_rule",
                    **extra,
                }
            }
        }
    }
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    return path


def write_manifest(tmp_path: Path, works_path: Path, *, year: int = SNAPSHOT_YEAR) -> Path:
    manifest = {
        "status": "COMPLETED",
        "snapshot_id": "synthetic-snapshot",
        "retrieved_completed_at": f"{year}-06-01T00:00:00+00:00",
        "artifacts": {
            "works_jsonl": {"path": str(works_path), "sha256": sha256_of(works_path)}
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def build_fixture(
    tmp_path: Path,
    works: list[dict],
    *,
    scifact: list[dict] | None = None,
    scidocs: list[dict] | None = None,
    protocol_kwargs: dict | None = None,
    manifest_year: int = SNAPSHOT_YEAR,
) -> dict[str, Path]:
    works_path = tmp_path / "works.jsonl"
    write_jsonl(works_path, works)
    scifact_path = tmp_path / "scifact_corpus.jsonl"
    write_jsonl(scifact_path, scifact if scifact is not None else [make_beir_doc("sf1", "SciFact Doc")])
    scidocs_path = tmp_path / "scidocs_corpus.jsonl"
    write_jsonl(scidocs_path, scidocs if scidocs is not None else [make_beir_doc("sd1", "SciDocs Doc")])
    return {
        "works": works_path,
        "manifest": write_manifest(tmp_path, works_path, year=manifest_year),
        "protocol": write_protocol(tmp_path, **(protocol_kwargs or {})),
        "scifact": scifact_path,
        "scidocs": scidocs_path,
        "masking_doc": tmp_path / "GRAPH_PROTOCOL.md",
        "report": tmp_path / "report.json",
    }


def make_beir_doc(
    doc_id: str,
    title: str | None = "Doc",
    *,
    refs: list[str] | None = None,
    metadata: dict | None = None,
    **overrides: object,
) -> dict:
    record: dict = {"_id": doc_id, "title": title, "text": "body"}
    record["metadata"] = {} if metadata is None else metadata
    if refs is not None:
        record["references"] = refs
    record.update(overrides)
    return record


def run_gate(paths: dict[str, Path], *, masking_doc: bool = True) -> tuple[int, dict]:
    masking_path = paths["masking_doc"]
    if masking_doc:
        masking_path.write_text("# synthetic masking doc\n", encoding="utf-8")
    elif masking_path.exists():
        masking_path.unlink()
    return run_feasibility(
        works_path=paths["works"],
        manifest_path=paths["manifest"],
        protocol_path=paths["protocol"],
        scifact_corpus_path=paths["scifact"],
        scidocs_corpus_path=paths["scidocs"],
        report_path=paths["report"],
        command_argv=["synthetic"],
        measured_at=datetime(2026, 9, 16, 12, 0, 0),
        masking_doc_path=masking_path if masking_doc else None,
    )


def run_cli(paths: dict[str, Path], *, masking_doc: bool = True) -> subprocess.CompletedProcess:
    if masking_doc:
        paths["masking_doc"].write_text("# synthetic masking doc\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [
            sys.executable, "-m", "scholargraph.graph.feasibility",
            "--works", str(paths["works"]),
            "--manifest", str(paths["manifest"]),
            "--protocol", str(paths["protocol"]),
            "--scifact-corpus", str(paths["scifact"]),
            "--scidocs-corpus", str(paths["scidocs"]),
            "--report", str(paths["report"]),
            "--masking-doc", str(paths["masking_doc"]),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
    )


def graph_fixture_works() -> list[dict]:
    """A: refs [B, C, self, out-of-snapshot Z, duplicate B]; B<->C reciprocal; D isolated."""

    return [
        make_work("W1", title="Alpha Paper", year=2020,
                  doi="https://doi.org/10.1/Alpha", refs=("W2", "W3", "W1", "W999", "W2")),
        make_work("W2", year=2019, refs=("W3",)),
        make_work("W3", year=2018, refs=("W2",)),
        make_work("W4", year=2021, refs=()),
    ]


# ---------------------------------------------------------------------------
# Unit: normalization helpers
# ---------------------------------------------------------------------------

def test_canonical_work_id_normalizes_uri():
    assert canonical_work_id("https://openalex.org/W123/") == "openalex:W123"
    assert canonical_work_id("W42") == "openalex:W42"


def test_canonical_work_id_rejects_invalid():
    with pytest.raises(ValueError):
        canonical_work_id("https://openalex.org/X1")
    with pytest.raises(ValueError):
        canonical_work_id("")


def test_normalize_doi_strips_prefix_and_casefolds():
    assert normalize_doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert normalize_doi("dx.doi.org/10.1/x") == "10.1/x"
    assert normalize_doi("   ") is None
    assert normalize_doi(None) is None


def test_normalize_doi_rejects_non_string():
    with pytest.raises(FeasibilityError):
        normalize_doi(123)


def test_normalize_title_collapses_whitespace_and_casefolds():
    assert normalize_title("  A   B\tC ") == "a b c"
    assert normalize_title("") is None
    assert normalize_title(None) is None


# ---------------------------------------------------------------------------
# Unit: snapshot parsing and graph statistics
# ---------------------------------------------------------------------------

def test_parse_works_counts_anomalies_without_dropping():
    snapshot = parse_works(graph_fixture_works())
    assert len(snapshot.records) == 4
    assert snapshot.anomalies["duplicate_reference_entries"] == 1
    record_w1 = snapshot.records[0]
    assert record_w1.references == (
        "openalex:W2", "openalex:W3", "openalex:W1", "openalex:W999", "openalex:W2",
    )


def test_compute_snapshot_stats_counts_edges_isolated_components():
    stats = compute_snapshot_stats(parse_works(graph_fixture_works()), SNAPSHOT_YEAR)
    counts = stats["counts"]
    assert counts["works"] == 4
    assert counts["reference_entries_total"] == 7
    # internal occurrences: W1->W2, W1->W3, W1->W2(dup), W2->W3, W3->W2
    assert counts["internal_reference_occurrences"] == 5
    assert counts["unique_internal_directed_edges"] == 4
    assert counts["self_loop_count"] == 1
    assert counts["duplicate_reference_entry_count"] == 1
    assert counts["reciprocal_edge_pair_count"] == 1
    assert counts["out_of_snapshot_reference_occurrences"] == 1
    assert counts["isolated_nodes"] == 1
    assert counts["weakly_connected_components"] == 2
    assert counts["largest_weak_component_size"] == 3
    assert stats["derived"]["directed_density"] == round(4 / 12, 12)
    assert stats["derived"]["isolated_node_fraction"] == round(1 / 4, 6)
    assert stats["coverage"]["doi"]["count"] == 1
    assert stats["coverage"]["has_any_reference"]["count"] == 3
    assert stats["coverage"]["venue_name_corrected_predicate"]["count"] == 4


def test_venue_predicate_requires_source_name_not_landing_url():
    records = [
        make_work("W1", venue=True),
        make_work("W2", venue=False),
    ]
    stats = compute_snapshot_stats(parse_works(records), SNAPSHOT_YEAR)
    assert stats["coverage"]["venue_name_corrected_predicate"]["count"] == 1


def test_self_loops_are_excluded_from_edges_but_counted():
    stats = compute_snapshot_stats(parse_works(graph_fixture_works()), SNAPSHOT_YEAR)
    assert stats["counts"]["self_loop_count"] == 1
    assert stats["anomalies"]["self_loop_count_exact"] == 1
    assert stats["anomalies"]["self_loop_works"] == ["openalex:W1"]
    # edge set must not contain the self-loop
    assert stats["counts"]["unique_internal_directed_edges"] == 4


# ---------------------------------------------------------------------------
# Unit: cohorts, floors, mapping, BEIR corpus
# ---------------------------------------------------------------------------

def cohort_fixture() -> list[dict]:
    """Two eligible sources in 2025 (refs to 2023), one eligible in 2024."""

    filler = [make_work(f"W91{i}", year=2023, refs=()) for i in range(3)]
    return [
        make_work("W901", year=2025, refs=("W910", "W911")),
        make_work("W902", year=2025, refs=("W912", "W911")),
        make_work("W903", year=2024, refs=("W910", "W912")),
        *filler,
    ]


def test_evaluate_cohorts_selects_latest_completed_years():
    snapshot = parse_works(cohort_fixture())
    floors = {
        "minimum_dev_queries": 1,
        "minimum_test_queries": 2,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 1,
        "test_year_rule": "t",
        "dev_year_rule": "d",
    }
    cohorts = evaluate_cohorts(snapshot, SNAPSHOT_YEAR, floors)
    assert cohorts["test_year"] == 2025
    assert cohorts["dev_year"] == 2024
    assert cohorts["eligible_source_count_by_publication_year"] == {"2024": 1, "2025": 2}


def test_evaluate_cohorts_without_eligible_sources_reports_nulls_not_zero():
    snapshot = parse_works([make_work("W1", year=2020, refs=())])
    floors = {
        "minimum_dev_queries": 30,
        "minimum_test_queries": 50,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 100,
        "test_year_rule": "t",
        "dev_year_rule": "d",
    }
    cohorts = evaluate_cohorts(snapshot, SNAPSHOT_YEAR, floors)
    assert cohorts["test_year"] is None
    assert cohorts["dev_year"] is None
    assert cohorts["total_eligible_sources"] == 0
    universe = cohorts["novel_candidate_universe_lower_bound"]
    assert universe["sources_measured"] == 0
    assert universe["min"] is None
    assert universe["median"] is None
    assert universe["max"] is None
    assert universe["sources_below_minimum_novel_candidates"] is None


def test_future_references_do_not_make_a_source_eligible():
    snapshot = parse_works([
        make_work("W901", year=2023, refs=("W910", "W911")),
        make_work("W910", year=2024, refs=()),
        make_work("W911", year=2024, refs=()),
    ])
    floors = {
        "minimum_dev_queries": 1,
        "minimum_test_queries": 1,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 1,
        "test_year_rule": "t",
        "dev_year_rule": "d",
    }
    cohorts = evaluate_cohorts(snapshot, SNAPSHOT_YEAR, floors)
    assert cohorts["eligible_source_count_by_publication_year"] == {}


def test_load_floors_missing_gate_is_fatal(tmp_path):
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps({"tracks": {}}), encoding="utf-8")
    with pytest.raises(FeasibilityError):
        load_floors(json.loads(protocol_path.read_text(encoding="utf-8")))


def test_load_floors_rejects_non_integer_floor(tmp_path):
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(
        json.dumps(
            {
                "tracks": {
                    "B": {
                        "graph_gate": {
                            "minimum_dev_queries": "30",
                            "minimum_test_queries": 50,
                            "minimum_eligible_references": 2,
                            "minimum_novel_candidates_per_query": 100,
                            "test_year_rule": "t",
                            "dev_year_rule": "d",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FeasibilityError):
        load_floors(json.loads(protocol_path.read_text(encoding="utf-8")))


def test_compute_mapping_doi_and_title_with_collision_sign():
    snapshot = parse_works([
        make_work("W1", title="Alpha  Paper", doi="https://doi.org/10.1/Alpha"),
        make_work("W2", title="Beta Study"),
    ])
    corpora = [
        parse_beir_corpus("ds", [
            make_beir_doc("d1", "Alpha Paper", metadata={"doi": "10.1/ALPHA"}),
            make_beir_doc("d2", "Gamma"),
            make_beir_doc("d3", "Gamma"),
        ]),
    ]
    mapping = compute_mapping(snapshot, corpora)
    assert mapping["doi_mapping"]["doi_matches"] == 1
    assert mapping["doi_mapping"]["doi_matches_per_dataset"] == {"ds": 1}
    title = mapping["provisional_exact_title_probe"]["per_dataset"]["ds"]
    assert title["exact_normalized_title_matches"] == 1
    # two distinct docs share the title "gamma" -> exactly one collision
    assert title["beir_normalized_title_collisions"] == 1
    assert title["distinct_beir_docs_matched"] == 1


def test_parse_beir_corpus_metadata_references_and_out_of_corpus():
    corpus = parse_beir_corpus("ds", [
        make_beir_doc("d1", "One", metadata={"references": ["d2", "d2", "missing", "d1"]}),
        make_beir_doc("d2", "Two", metadata={"year": 2020, "doi": "10.1/x"}),
    ])
    stats = beir_corpus_stats(corpus)
    assert stats["counts"]["documents"] == 2
    assert stats["counts"]["reference_entries_total"] == 4
    assert stats["counts"]["internal_reference_occurrences_within_corpus"] == 2
    assert stats["counts"]["unique_internal_directed_edges"] == 1
    assert stats["counts"]["out_of_corpus_reference_occurrences"] == 1
    assert stats["counts"]["self_loop_count"] == 1
    assert stats["counts"]["duplicate_reference_entry_count"] == 1
    assert stats["counts"]["docs_with_metadata_references"] == 1
    assert stats["counts"]["docs_with_doi"] == 1
    assert stats["reference_field_location"] == "metadata.references"


def test_parse_beir_corpus_ambiguous_references_is_fatal():
    with pytest.raises(FeasibilityError):
        parse_beir_corpus("ds", [
            make_beir_doc("d1", "One", refs=["d2"], metadata={"references": ["d3"]}),
            make_beir_doc("d2", "Two"),
            make_beir_doc("d3", "Three"),
        ])


def test_parse_beir_corpus_duplicate_ids_and_empty_are_fatal():
    with pytest.raises(FeasibilityError):
        parse_beir_corpus("ds", [make_beir_doc("d1"), make_beir_doc("d1")])
    with pytest.raises(FeasibilityError):
        parse_beir_corpus("ds", [])


def test_evaluate_gate_no_go_records_evidence_and_requirements():
    snapshot = parse_works([make_work("W1", year=2020, refs=())])
    stats = compute_snapshot_stats(snapshot, SNAPSHOT_YEAR)
    floors = {
        "minimum_dev_queries": 30,
        "minimum_test_queries": 50,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 100,
        "test_year_rule": "t",
        "dev_year_rule": "d",
    }
    cohorts = evaluate_cohorts(snapshot, SNAPSHOT_YEAR, floors)
    mapping = compute_mapping(snapshot, [])
    decision = evaluate_gate(stats, cohorts, mapping, [], True)
    assert decision["overall"] == "NO_GO"
    assert decision["binding_no_go_evidence"]
    assert decision["sg015_requirements_if_no_go"]
    assert decision["scope_dependency_adjustments"]
    criteria = {c["criterion_id"]: c["decision"] for c in decision["criteria"]}
    assert criteria["cohort_test_year_floor"] == "NO_GO"
    assert criteria["cohort_dev_year_floor"] == "NO_GO"
    assert criteria["minimum_novel_candidates_per_source"] == "NO_GO"
    assert criteria["snapshot_provenance_integrity"] == "GO"


def test_evaluate_gate_go_when_all_floors_met():
    works = [make_work(f"W{i}", year=2019, refs=(f"W{i + 1}",)) for i in range(110)]
    works.append(make_work("W2020", year=2020, refs=("W0",)))
    snapshot = parse_works(works)
    stats = compute_snapshot_stats(snapshot, SNAPSHOT_YEAR)
    floors = {
        "minimum_dev_queries": 1,
        "minimum_test_queries": 1,
        "minimum_eligible_references": 1,
        "minimum_novel_candidates_per_query": 100,
        "test_year_rule": "t",
        "dev_year_rule": "d",
    }
    cohorts = evaluate_cohorts(snapshot, SNAPSHOT_YEAR, floors)
    mapping = compute_mapping(snapshot, [])
    decision = evaluate_gate(stats, cohorts, mapping, [], True)
    assert decision["overall"] == "GO"
    assert decision["sg015_requirements_if_no_go"] == []


def test_evaluate_gate_masking_criterion_follows_document_presence():
    snapshot = parse_works([make_work("W1", year=2020, refs=())])
    stats = compute_snapshot_stats(snapshot, SNAPSHOT_YEAR)
    floors = {
        "minimum_dev_queries": 30,
        "minimum_test_queries": 50,
        "minimum_eligible_references": 2,
        "minimum_novel_candidates_per_query": 100,
        "test_year_rule": "t",
        "dev_year_rule": "d",
    }
    cohorts = evaluate_cohorts(snapshot, SNAPSHOT_YEAR, floors)
    mapping = compute_mapping(snapshot, [])
    documented = evaluate_gate(stats, cohorts, mapping, [], True)
    undocumented = evaluate_gate(stats, cohorts, mapping, [], False)
    criteria_documented = {
        c["criterion_id"]: c["decision"] for c in documented["criteria"]
    }
    criteria_undocumented = {
        c["criterion_id"]: c["decision"] for c in undocumented["criteria"]
    }
    assert criteria_documented["masking_protocol_readiness"] == "GO"
    assert criteria_undocumented["masking_protocol_readiness"] == "NO_GO"


# ---------------------------------------------------------------------------
# Integration over tmp_path fixtures: measured runs and fatal failures
# ---------------------------------------------------------------------------

def test_run_feasibility_measures_no_go_and_records_provenance(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    exit_code, report = run_gate(paths)
    assert exit_code == 0
    assert report["status"] == "MEASURED"
    assert report["qrels_used"] is False
    assert report["decision"]["overall"] == "NO_GO"
    assert report["openalex_snapshot"]["counts"]["works"] == 4
    provenance = report["provenance"]["inputs"]
    assert provenance["works_jsonl"]["sha256"] == sha256_of(paths["works"])
    assert report["provenance"]["snapshot_verification"]["snapshot_id"] == "synthetic-snapshot"
    assert report["leakage_audit"]["status"] == "deferred_to_SG016"
    on_disk = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert on_disk["decision"]["overall"] == "NO_GO"


def test_run_feasibility_masking_doc_absent_is_reflected(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    exit_code, report = run_gate(paths, masking_doc=False)
    assert exit_code == 0
    criteria = {c["criterion_id"]: c["decision"] for c in report["decision"]["criteria"]}
    assert criteria["masking_protocol_readiness"] == "NO_GO"


def test_missing_works_file_fails_with_exit_1(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    paths["works"].unlink()
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert "missing" in report["errors"][0].lower()
    assert "openalex_snapshot" not in report


def test_missing_each_required_input_fails(tmp_path):
    for key in ("manifest", "protocol", "scifact", "scidocs"):
        scenario_dir = tmp_path / key
        scenario_dir.mkdir()
        scenario = build_fixture(scenario_dir, graph_fixture_works())
        scenario[key].unlink()
        exit_code, report = run_gate(scenario)
        assert exit_code == 1, key
        assert report["status"] == "FAIL", key
        assert "missing" in report["errors"][0].lower(), key


def test_malformed_jsonl_is_fatal(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    paths["works"].write_text(
        json.dumps(make_work("W1")) + "\n{not json}\n", encoding="utf-8"
    )
    paths["manifest"] = write_manifest(tmp_path, paths["works"])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert "invalid json" in report["errors"][0].lower()


def test_duplicate_work_ids_are_fatal(tmp_path):
    paths = build_fixture(tmp_path, [
        make_work("W1", year=2020),
        make_work("W1", year=2021),
    ])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert "duplicate canonical work id" in report["errors"][0].lower()


def test_empty_works_snapshot_is_fatal(tmp_path):
    paths = build_fixture(tmp_path, [])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert "empty" in report["errors"][0].lower()


def test_invalid_work_id_is_fatal(tmp_path):
    paths = build_fixture(tmp_path, [make_work("X1", year=2020)])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"


def test_missing_referenced_works_field_is_fatal(tmp_path):
    record = make_work("W1", year=2020)
    del record["referenced_works"]
    paths = build_fixture(tmp_path, [record])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert "referenced_works" in report["errors"][0]


def test_non_integer_publication_year_is_fatal(tmp_path):
    paths = build_fixture(tmp_path, [make_work("W1", year="2020")])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"


def test_manifest_hash_mismatch_is_fatal(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    write_jsonl(paths["works"], graph_fixture_works() + [make_work("W5", year=2022)])
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert "sha256 mismatch" in report["errors"][0].lower()


def test_manifest_not_completed_is_fatal(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["status"] = "PARTIAL"
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    exit_code, report = run_gate(paths)
    assert exit_code == 1
    assert "completed" in report["errors"][0].lower()


def test_unmeasured_measurements_are_null_not_zero(tmp_path):
    paths = build_fixture(tmp_path, [make_work("W1", year=2020, refs=())])
    exit_code, report = run_gate(paths)
    assert exit_code == 0
    universe = report["protocol_b_cohorts"]["novel_candidate_universe_lower_bound"]
    assert universe["min"] is None
    assert universe["median"] is None
    assert universe["max"] is None
    assert universe["sources_below_minimum_novel_candidates"] is None
    assert report["protocol_b_cohorts"]["test_year"] is None


# ---------------------------------------------------------------------------
# CLI subprocess (ADR-013: exit code contract verified for real)
# ---------------------------------------------------------------------------

def test_cli_subprocess_exit_1_on_missing_works_file(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    paths["works"].unlink()
    proc = run_cli(paths)
    assert proc.returncode == 1
    assert "FEASIBILITY FAILED" in proc.stderr


def test_cli_subprocess_exit_1_on_corrupt_snapshot(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    paths["works"].write_text("[1, 2]\n", encoding="utf-8")
    proc = run_cli(paths)
    assert proc.returncode == 1
    assert "FEASIBILITY FAILED" in proc.stderr
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"


def test_cli_subprocess_exit_0_with_measured_no_go_report(tmp_path):
    paths = build_fixture(tmp_path, graph_fixture_works())
    proc = run_cli(paths)
    assert proc.returncode == 0
    assert "decision=NO_GO" in proc.stdout
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["status"] == "MEASURED"
    assert report["decision"]["overall"] == "NO_GO"
    assert report["qrels_used"] is False
