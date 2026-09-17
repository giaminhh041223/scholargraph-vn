"""SG-016 masked graph build: unit, adversarial tamper and CLI subprocess tests.

All fixtures are synthetic and written into pytest ``tmp_path``; none of them
touches the real OpenAlex snapshot or the produced ``data/processed/graph``
artifacts.  Per ADR-013/ADR-014 the masking pipeline must fail loudly:

* any held-out edge surviving in the masked adjacency in EITHER direction is a
  FAIL (PPR transmits along Pᵀ, so one direction is not enough),
* self-loops must never reach an adjacency artifact,
* features not derived from ``G_mask`` are detected,
* every fatal input problem (missing file, checksum mismatch, gate not GO,
  unresolvable cohort, protocol rule change) exits with code 1.

The expected counts of the main fixture are hand-computed in the docstring of
``main_fixture_works`` and asserted 1:1 against the manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import pytest

from scholargraph.graph.build import (
    EDGE_SORT_RULE_PINNED,
    GraphBuildError,
    HELDOUT_COUNT_RULE_PINNED,
    heldout_count,
    run_audit,
    run_build,
    split_for_source,
)
from scholargraph.graph.feasibility import evaluate_cohorts, load_floors, parse_works

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_YEAR = 2026
MEASURED_AT = datetime(2026, 9, 17, 12, 0, 0)
SEED = 20260915

# Canonical fixture IDs (must match the OpenAlex W<digits> shape).
A = "openalex:W101"
B = "openalex:W102"
C = "openalex:W103"
D = "openalex:W104"
E = "openalex:W105"
F = "openalex:W106"
G = "openalex:W107"
M1 = "openalex:W201"
M2 = "openalex:W202"
T1 = "openalex:W301"
T2 = "openalex:W302"
T3 = "openalex:W303"
T4 = "openalex:W304"
WDUP = "openalex:W401"
WSELF = "openalex:W402"
WDANG = "openalex:W403"
WNOABS = "openalex:W404"
WNOTITLE = "openalex:W405"
D1 = "openalex:W501"
D2 = "openalex:W502"
WNOYEAR = "openalex:W601"
WBADYEAR = "openalex:W602"
X = "openalex:W701"
Y = "openalex:W702"
U1 = "openalex:W801"
DQ = "openalex:W802"
P = "openalex:W901"
Q = "openalex:W902"

_DEFAULT = object()  # sentinel: distinguish "not given" from an explicit None


def bare(canonical: str) -> str:
    return canonical.replace("openalex:", "")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def make_work(
    wid: str,
    *,
    title: object = _DEFAULT,
    abstract: object = _DEFAULT,
    year: object = _DEFAULT,
    doi: str | None = None,
    refs: tuple[str, ...] = (),
    **overrides: object,
) -> dict:
    if title is _DEFAULT:
        title = "Title " + wid
    if abstract is _DEFAULT:
        abstract = {"word": [0]}
    if year is _DEFAULT:
        year = 2020
    record: dict = {
        "id": f"https://openalex.org/{wid}",
        "title": title,
        "abstract_inverted_index": abstract,
        "publication_year": year,
        "doi": doi,
        "referenced_works": [f"https://openalex.org/{ref}" for ref in refs],
    }
    record["primary_location"] = {"source": {"display_name": f"Venue of {wid}"}}
    record.update(overrides)
    return record


def main_fixture_works() -> list[dict]:
    """22 synthetic works; hand-computed expectations (see test_build_end_to_end).

    Valid-year works: A..G, M1, M2, T1..T4, WDUP, WSELF, WDANG, WNOABS,
    WNOTITLE, D1, D2 (20).  WNOYEAR has no year, WBADYEAR year 1899.
    Pre-mask internal edges: 31 = 2 mutual (M1<->M2) + 3+3+4+5 from T1..T4
    + 2 WDUP + 1 WSELF + 1 WDANG + 2 WNOABS + 2 WNOTITLE + 2 D1 + 2 D2
    + 1 WNOYEAR + 1 WBADYEAR.
    Test cohort 2025: T1..T4 + WDUP (5 eligible, h=1 each); dev 2024: D1, D2.
    """

    return [
        make_work(bare(A), year=2018),
        make_work(bare(B), year=2019),
        make_work(bare(C), year=2020),
        make_work(bare(D), year=2021),
        make_work(bare(E), year=2022),
        make_work(bare(F), year=2023),
        make_work(bare(G), year=2024),
        # reciprocal pair; M1 -> M2 is a future-target edge (2023 > 2022)
        make_work(bare(M1), year=2022, refs=(bare(M2),)),
        make_work(bare(M2), year=2023, refs=(bare(M1),)),
        make_work(bare(T1), year=2025, refs=(bare(A), bare(B), bare(C))),
        make_work(bare(T2), year=2025, refs=(bare(A), bare(C), bare(D))),
        make_work(bare(T3), year=2025, refs=(bare(B), bare(E), bare(F), bare(G))),
        make_work(bare(T4), year=2025, refs=(bare(A), bare(B), bare(C), bare(D), bare(E))),
        make_work(bare(WDUP), year=2025, refs=(bare(A), bare(A), bare(B))),
        make_work(bare(WSELF), year=2025, refs=(bare(WSELF), bare(A))),
        make_work(bare(WDANG), year=2025, refs=(bare(A), "W999")),
        make_work(bare(WNOABS), year=2025, refs=(bare(A), bare(B)), abstract=None),
        make_work(bare(WNOTITLE), year=2025, refs=(bare(A), bare(B)), title=None),
        make_work(bare(D1), year=2024, refs=(bare(A), bare(B))),
        make_work(bare(D2), year=2024, refs=(bare(C), bare(D))),
        make_work(bare(WNOYEAR), year=None, refs=(bare(A),)),
        make_work(bare(WBADYEAR), year=1899, refs=(bare(A),)),
    ]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_snapshot_manifest(tmp_path: Path, works_path: Path) -> Path:
    manifest = {
        "status": "COMPLETED",
        "snapshot_id": "synthetic-snapshot",
        "retrieved_completed_at": f"{SNAPSHOT_YEAR}-06-01T00:00:00+00:00",
        "artifacts": {
            "works_jsonl": {"path": str(works_path), "sha256": sha256_of(works_path)}
        },
    }
    path = tmp_path / "snapshot_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def write_protocol(
    tmp_path: Path,
    *,
    min_test: int = 2,
    min_dev: int = 2,
    min_refs: int = 2,
    min_candidates: int = 1,
    max_test: int = 10,
    max_dev: int = 10,
    edge_sort: str = EDGE_SORT_RULE_PINNED,
) -> Path:
    protocol = {
        "tracks": {
            "B": {
                "split": {
                    "seed": SEED,
                    "heldout_fraction": 0.2,
                    "minimum_observed": 1,
                    "minimum_heldout": 1,
                    "edge_sort": edge_sort,
                    "heldout_count": HELDOUT_COUNT_RULE_PINNED,
                    "mask_scope": [
                        "all_dev_heldout_edges",
                        "all_test_heldout_edges",
                        "reverse_counterparts",
                    ],
                },
                "graph_gate": {
                    "minimum_dev_queries": min_dev,
                    "minimum_test_queries": min_test,
                    "minimum_eligible_references": min_refs,
                    "minimum_novel_candidates_per_query": min_candidates,
                    "maximum_dev_queries": max_dev,
                    "maximum_test_queries": max_test,
                    "test_year_rule": "synthetic_test_rule",
                    "dev_year_rule": "synthetic_dev_rule",
                },
            }
        }
    }
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    return path


def write_gate_report(
    tmp_path: Path,
    works_path: Path,
    works_records: list[dict],
    protocol_path: Path,
    *,
    overall: str = "GO",
) -> Path:
    """Gate report matching the fixture snapshot (cohorts recomputed 1:1)."""

    parsed = parse_works(works_records)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    cohorts = evaluate_cohorts(parsed, SNAPSHOT_YEAR, load_floors(protocol))
    report = {
        "status": "MEASURED",
        "measured_at": "2026-09-17T00:14:25+00:00",
        "decision": {"overall": overall},
        "provenance": {
            "inputs": {"works_jsonl": {"sha256": sha256_of(works_path)}}
        },
        "protocol_b_cohorts": cohorts,
    }
    path = tmp_path / "gate_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def build_fixture(tmp_path: Path, works: list[dict], **protocol_kwargs: object) -> dict[str, Path]:
    works_path = tmp_path / "works.jsonl"
    write_jsonl(works_path, works)
    protocol_path = write_protocol(tmp_path, **protocol_kwargs)
    paths = {
        "works": works_path,
        "manifest": write_snapshot_manifest(tmp_path, works_path),
        "protocol": protocol_path,
        "gate": write_gate_report(tmp_path, works_path, works, protocol_path),
        "doc": tmp_path / "GRAPH_PROTOCOL.md",
        "out_dir": tmp_path / "graph",
        "graph_manifest": tmp_path / "graph_core.json",
        "audit": tmp_path / "graph_audit.json",
    }
    # The protocol doc is a required CLI input; every fixture starts complete so
    # that tampering tests hit their targeted failure mode, not "missing file".
    paths["doc"].write_text("# synthetic graph protocol\n", encoding="utf-8")
    return paths


def run_build_fixture(paths: dict[str, Path]) -> tuple[int, dict]:
    paths["doc"].write_text("# synthetic graph protocol\n", encoding="utf-8")
    return run_build(
        works_path=paths["works"],
        snapshot_manifest_path=paths["manifest"],
        protocol_path=paths["protocol"],
        gate_report_path=paths["gate"],
        protocol_doc_path=paths["doc"],
        out_dir=paths["out_dir"],
        graph_manifest_path=paths["graph_manifest"],
        audit_path=paths["audit"],
        command_argv=["synthetic"],
        measured_at=MEASURED_AT,
    )


def run_audit_fixture(paths: dict[str, Path]) -> tuple[int, dict]:
    return run_audit(
        works_path=paths["works"],
        snapshot_manifest_path=paths["manifest"],
        protocol_path=paths["protocol"],
        gate_report_path=paths["gate"],
        protocol_doc_path=paths["doc"],
        graph_manifest_path=paths["graph_manifest"],
        audit_path=paths["audit"],
        command_argv=["synthetic-audit"],
        measured_at=MEASURED_AT,
    )


def read_edges(path: Path) -> set[tuple[str, str]]:
    return {
        tuple(line.split("\t"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    }


def get_check(report: dict, check_id: str) -> dict:
    return next(check for check in report["checks"] if check["check_id"] == check_id)


def run_cli(paths: dict[str, Path], *extra: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scholargraph.graph.build",
            "--works", str(paths["works"]),
            "--manifest", str(paths["manifest"]),
            "--protocol", str(paths["protocol"]),
            "--gate-report", str(paths["gate"]),
            "--protocol-doc", str(paths["doc"]),
            "--out-dir", str(paths["out_dir"]),
            "--graph-manifest", str(paths["graph_manifest"]),
            "--audit", str(paths["audit"]),
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
    )


def built_fixture(tmp_path: Path) -> dict[str, Path]:
    """Fixture with a successful build already executed."""

    paths = build_fixture(tmp_path, main_fixture_works())
    exit_code, manifest = run_build_fixture(paths)
    assert exit_code == 0, manifest.get("errors")
    assert manifest["status"] == "COMPLETED"
    return paths


# ---------------------------------------------------------------------------
# Unit: holdout formula and deterministic split
# ---------------------------------------------------------------------------


def test_heldout_count_formula_matches_protocol():
    fraction = Fraction("0.2")
    assert heldout_count(1, fraction) == 0  # min(R-1, ...) dominates
    assert heldout_count(2, fraction) == 1  # max(1, ceil(0.4)) = 1
    assert heldout_count(4, fraction) == 1  # ceil(0.8) = 1
    assert heldout_count(5, fraction) == 1  # ceil(1.0) = 1 (exact rational)
    assert heldout_count(6, fraction) == 2  # ceil(1.2) = 2
    assert heldout_count(10, fraction) == 2
    assert heldout_count(11, fraction) == 3
    assert heldout_count(100, fraction) == 20  # min(R-1, 20)


def test_split_for_source_hash_order_and_partition():
    refs = [B, A, C]
    heldout, observed = split_for_source("openalex:W801", refs, SEED, Fraction("0.2"))
    assert len(heldout) == 1 and len(observed) == 2
    assert set(heldout) | set(observed) == set(refs)
    assert not set(heldout) & set(observed)
    expected_order = sorted(
        refs, key=lambda v: (hashlib.sha256(f"{SEED}|openalex:W801|{v}".encode()).hexdigest(), v)
    )
    assert heldout[0] == expected_order[0]
    # deterministic: same inputs -> same split
    assert split_for_source("openalex:W801", refs, SEED, Fraction("0.2")) == (heldout, observed)


# ---------------------------------------------------------------------------
# Positive end-to-end on the synthetic snapshot
# ---------------------------------------------------------------------------


def test_build_end_to_end_and_audit_pass(tmp_path):
    paths = built_fixture(tmp_path)
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))

    assert manifest["status"] == "COMPLETED"
    assert audit["status"] == "PASS"
    assert all(check["decision"] == "PASS" for check in audit["checks"])
    assert audit["qrels_used"] is False

    counts = manifest["counts"]
    assert counts["works"] == 22
    assert counts["nodes"] == 22
    assert counts["valid_year_nodes"] == 20
    assert counts["internal_directed_edges_premask"] == 31
    assert counts["edges_removed_by_mask"] == 7
    assert counts["internal_directed_edges_postmask"] == 24
    assert counts["self_loop_works_removed"] == 1
    assert counts["duplicate_reference_entry_count"] == 1
    assert counts["reciprocal_edge_pairs_premask"] == 1
    assert counts["reciprocal_edge_pairs_postmask"] == 1
    assert counts["reciprocal_pairs_with_heldout_direction"] == 0
    assert counts["out_of_snapshot_reference_occurrences"] == 1
    assert counts["future_target_edges_both_years_known"] == 1
    assert counts["missing_title_count"] == 1
    assert counts["missing_abstract_count"] == 1
    assert counts["missing_publication_year_count"] == 1
    assert counts["out_of_range_publication_year_count"] == 1

    holdout = manifest["holdout"]
    assert holdout["test_year"] == 2025 and holdout["dev_year"] == 2024
    assert holdout["eligible_sources_by_cohort"] == {"test": 5, "dev": 2}
    assert holdout["selected_queries"] == {"test": 5, "dev": 2}
    assert holdout["heldout_edges_by_cohort"] == {"test": 5, "dev": 2}
    assert holdout["heldout_edges_total"] == 7
    assert holdout["mask_edges_total"] == 14
    assert holdout["mask_reverse_only_absent_from_premask"] == 7

    # the required hashes exist and match the files on disk
    for name in ("adjacency_premask", "adjacency_masked", "holdout_edges", "mask_edges"):
        entry = manifest["hashes"][name]
        assert entry["sha256"] == sha256_of(paths["out_dir"] / f"{name}.tsv")
    assert manifest["graph_hash"] == manifest["hashes"]["adjacency_masked"]["sha256"]
    assert manifest["mask_hash"] == manifest["hashes"]["mask_edges"]["sha256"]
    assert manifest["split_hash"] == manifest["hashes"]["split_queries"]["sha256"]


def test_holdout_partition_and_year_legality(tmp_path):
    paths = built_fixture(tmp_path)
    split_payload = json.loads(
        (paths["out_dir"] / "split_queries.json").read_text(encoding="utf-8")
    )
    holdout = read_edges(paths["out_dir"] / "holdout_edges.tsv")
    works_jsonl = [
        json.loads(line)
        for line in paths["works"].read_text(encoding="utf-8").splitlines()
        if line
    ]
    years = {
        "openalex:" + w["id"].rsplit("/", 1)[-1]: w["publication_year"] for w in works_jsonl
    }
    refs = {
        "openalex:" + w["id"].rsplit("/", 1)[-1]: {
            "openalex:" + t.rsplit("/", 1)[-1] for t in w["referenced_works"]
        }
        for w in works_jsonl
    }

    for cohort in ("test", "dev"):
        year = split_payload["cohorts"][cohort]["year"]
        for source in split_payload["cohorts"][cohort]["selected"]:
            heldout = {v for u, v in holdout if u == source}
            year_legal = {
                t
                for t in refs[source]
                if t != source and years.get(t) is not None and years[t] <= year
            }
            r = len(year_legal)
            assert len(heldout) == min(r - 1, max(1, -((-(r * 1)) // 5)))
            assert heldout <= year_legal  # heldout drawn from year-legal R(u)
            assert r - len(heldout) >= 1  # minimum_observed
            for v in heldout:
                assert years[v] is not None and years[v] <= year


def test_mask_removes_holdout_in_both_directions(tmp_path):
    paths = built_fixture(tmp_path)
    premask = read_edges(paths["out_dir"] / "adjacency_premask.tsv")
    masked = read_edges(paths["out_dir"] / "adjacency_masked.tsv")
    holdout = read_edges(paths["out_dir"] / "holdout_edges.tsv")
    mask = read_edges(paths["out_dir"] / "mask_edges.tsv")

    assert mask == holdout | {(v, u) for u, v in holdout}
    assert not any(edge in masked for edge in mask)
    assert not any((v, u) in masked for u, v in holdout)
    assert masked == premask - mask
    assert len(masked) == len(premask) - 7


def test_self_loops_removed_and_counted(tmp_path):
    paths = built_fixture(tmp_path)
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    premask = read_edges(paths["out_dir"] / "adjacency_premask.tsv")
    masked = read_edges(paths["out_dir"] / "adjacency_masked.tsv")
    assert manifest["counts"]["self_loop_works_removed"] == 1
    assert WSELF in manifest["counts"]["self_loop_works"]
    assert all(u != v for u, v in premask)
    assert all(u != v for u, v in masked)


def test_dangling_reference_counted_not_materialised(tmp_path):
    paths = built_fixture(tmp_path)
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    assert manifest["counts"]["out_of_snapshot_reference_occurrences"] == 1
    assert manifest["counts"]["out_of_snapshot_distinct_targets"] == 1
    premask = read_edges(paths["out_dir"] / "adjacency_premask.tsv")
    masked = read_edges(paths["out_dir"] / "adjacency_masked.tsv")
    # W999 never becomes a node or an edge endpoint
    assert not any("W999" in endpoint for edge in premask | masked for endpoint in edge)


def test_duplicate_reference_dedup_counted(tmp_path):
    paths = built_fixture(tmp_path)
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    premask = read_edges(paths["out_dir"] / "adjacency_premask.tsv")
    assert manifest["counts"]["duplicate_reference_entry_count"] == 1
    assert sum(1 for u, v in premask if u == WDUP) == 2  # A and B once each


def test_missing_fields_counted_not_dropped(tmp_path):
    paths = built_fixture(tmp_path)
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    counts = manifest["counts"]
    assert counts["missing_title_count"] == 1
    assert counts["missing_abstract_count"] == 1
    assert counts["missing_publication_year_count"] == 1
    assert counts["out_of_range_publication_year_count"] == 1
    assert counts["missing_doi_count"] == 22  # fixture has no DOI anywhere
    # missing-year works stay as graph nodes
    assert counts["nodes"] == counts["works"] == 22


def test_query_selection_order_deterministic_and_capped(tmp_path):
    paths = built_fixture(tmp_path)
    split_payload = json.loads(
        (paths["out_dir"] / "split_queries.json").read_text(encoding="utf-8")
    )
    for cohort in ("test", "dev"):
        selected = split_payload["cohorts"][cohort]["selected"]
        expected_order = sorted(
            selected, key=lambda u: (hashlib.sha256(f"{SEED}|{u}".encode()).hexdigest(), u)
        )
        assert selected == expected_order
        assert len(selected) <= split_payload["cohorts"][cohort]["cap"]
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    assert manifest["split_hash"] == sha256_of(paths["out_dir"] / "split_queries.json")


def test_reciprocal_pair_with_heldout_direction_masked_both_ways(tmp_path):
    """A heldout edge whose reverse counterpart is a real internal edge."""

    works = [
        make_work(bare(X), year=2018, refs=(bare(U1),)),  # reverse of U1->X
        make_work(bare(Y), year=2019, refs=(bare(U1),)),  # reverse of U1->Y
        make_work(bare(U1), year=2025, refs=(bare(X), bare(Y))),
        make_work(bare(DQ), year=2024, refs=(bare(X), bare(Y))),
    ]
    paths = build_fixture(tmp_path, works, min_test=1, min_dev=1)
    exit_code, manifest = run_build_fixture(paths)
    assert exit_code == 0, manifest.get("errors")
    masked = read_edges(paths["out_dir"] / "adjacency_masked.tsv")
    holdout = read_edges(paths["out_dir"] / "holdout_edges.tsv")
    premask = read_edges(paths["out_dir"] / "adjacency_premask.tsv")
    assert len(holdout) == 2  # U1 (test) + DQ (dev), h=1 each
    # both mutual pairs exist pre-mask
    assert (U1, X) in premask and (X, U1) in premask
    assert (U1, Y) in premask and (Y, U1) in premask
    for u, v in holdout:
        assert (u, v) not in masked
        assert (v, u) not in masked  # reverse counterpart removed from the adjacency
    # exactly one of the two reverses survives (the non-heldout one)
    survivors = {(X, U1), (Y, U1)} & masked
    assert len(survivors) == 1
    assert manifest["counts"]["reciprocal_edge_pairs_premask"] == 2
    assert manifest["counts"]["reciprocal_edge_pairs_postmask"] == 1
    assert manifest["counts"]["reciprocal_pairs_with_heldout_direction"] == 1


def test_cutoff_features_recorded_per_query(tmp_path):
    paths = built_fixture(tmp_path)
    lines = [
        json.loads(line)
        for line in (paths["out_dir"] / "features_cutoff_degree.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(lines) == 7  # 5 test + 2 dev queries
    masked = read_edges(paths["out_dir"] / "adjacency_masked.tsv")
    by_source = {line["source_id"]: line for line in lines}
    for line in lines:
        assert line["cutoff_year"] >= 2024
        assert line["truncated_edge_count"] <= len(masked)
        assert line["source_out_degree_cutoff"] >= 1
    t1 = by_source[T1]
    # T1 -> {A, B, C}: one heldout, two observed; cutoff 2025 covers every
    # valid-year node, but the WNOYEAR/WBADYEAR edges leave the induced subgraph
    # (unknown/invalid year cannot satisfy year <= cutoff, GRAPH_PROTOCOL §3.2).
    assert t1["source_out_degree_cutoff"] == 2
    assert t1["truncated_edge_count"] == len(masked) - 2


# ---------------------------------------------------------------------------
# Adversarial tampering: every residual must FAIL the audit (exit 1)
# ---------------------------------------------------------------------------


def test_tamper_heldout_edge_into_masked_adjacency_fails(tmp_path):
    paths = built_fixture(tmp_path)
    victim = sorted(read_edges(paths["out_dir"] / "holdout_edges.tsv"))[0]
    with (paths["out_dir"] / "adjacency_masked.tsv").open("a", encoding="utf-8") as handle:
        handle.write(f"{victim[0]}\t{victim[1]}\n")
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert report["status"] == "FAIL"
    check = get_check(report, "two_way_heldout_residual")
    assert check["decision"] == "FAIL"
    assert check["measured"]["residual_same_direction"] == 1


def test_tamper_reverse_counterpart_into_masked_adjacency_fails(tmp_path):
    paths = built_fixture(tmp_path)
    victim = sorted(read_edges(paths["out_dir"] / "holdout_edges.tsv"))[0]
    with (paths["out_dir"] / "adjacency_masked.tsv").open("a", encoding="utf-8") as handle:
        handle.write(f"{victim[1]}\t{victim[0]}\n")
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    check = get_check(report, "two_way_heldout_residual")
    assert check["decision"] == "FAIL"
    assert check["measured"]["residual_reverse_direction"] == 1


def test_tamper_self_loop_into_masked_adjacency_fails(tmp_path):
    paths = built_fixture(tmp_path)
    with (paths["out_dir"] / "adjacency_masked.tsv").open("a", encoding="utf-8") as handle:
        handle.write(f"{A}\t{A}\n")
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    check = get_check(report, "masked_adjacency_set_identity")
    assert check["decision"] == "FAIL"
    assert check["measured"]["self_loop_residue"] == 1


def test_tamper_premask_adjacency_detected(tmp_path):
    paths = built_fixture(tmp_path)
    with (paths["out_dir"] / "adjacency_premask.tsv").open("a", encoding="utf-8") as handle:
        handle.write(f"{G}\t{T1}\n")  # fabricated edge
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "premask_adjacency_replay")["decision"] == "FAIL"


def test_tamper_holdout_file_detected(tmp_path):
    paths = built_fixture(tmp_path)
    lines = (paths["out_dir"] / "holdout_edges.tsv").read_text(encoding="utf-8").splitlines()
    (paths["out_dir"] / "holdout_edges.tsv").write_text(
        "\n".join(lines[1:]) + "\n", encoding="utf-8"
    )
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "holdout_split_replay")["decision"] == "FAIL"


def test_tamper_mask_file_detected(tmp_path):
    paths = built_fixture(tmp_path)
    path = paths["out_dir"] / "mask_edges.tsv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = f"{A}\topenalex:W888"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "mask_edges_replay")["decision"] == "FAIL"


def test_features_from_premask_graph_fail_audit(tmp_path):
    """Degree features derived from the PRE-mask graph are a leakage failure."""

    paths = built_fixture(tmp_path)
    premask = read_edges(paths["out_dir"] / "adjacency_premask.tsv")
    nodes = sorted({n for edge in premask for n in edge})
    in_degree = {node: 0 for node in nodes}
    out_degree = {node: 0 for node in nodes}
    for u, v in premask:
        out_degree[u] += 1
        in_degree[v] += 1
    payload = {
        "schema_version": 1,
        "artifact_type": "graph_degree_features",
        "task_id": "SG-016",
        "derived_from": "adjacency_masked.tsv",
        "cutoff": "none_full_masked_graph",
        "edge_count": len(premask),
        "in_degree": in_degree,
        "out_degree": out_degree,
    }
    (paths["out_dir"] / "features_degree_masked.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "degree_features_recomputed_from_masked")["decision"] == "FAIL"


def test_tamper_cutoff_features_fail_audit(tmp_path):
    paths = built_fixture(tmp_path)
    feature_path = paths["out_dir"] / "features_cutoff_degree.jsonl"
    lines = [
        json.loads(line)
        for line in feature_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    lines[0]["truncated_edge_count"] += 1
    feature_path.write_text(
        "".join(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n" for line in lines),
        encoding="utf-8",
    )
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "cutoff_features_recomputed_from_masked")["decision"] == "FAIL"


def test_tamper_manifest_counts_fail_audit(tmp_path):
    paths = built_fixture(tmp_path)
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    manifest["counts"]["internal_directed_edges_postmask"] += 5
    paths["graph_manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "manifest_counts_consistent")["decision"] == "FAIL"


def test_tamper_split_payload_fails_audit(tmp_path):
    paths = built_fixture(tmp_path)
    payload = json.loads(
        (paths["out_dir"] / "split_queries.json").read_text(encoding="utf-8")
    )
    payload["cohorts"]["test"]["selected"][0] = "openalex:W888"
    (paths["out_dir"] / "split_queries.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert get_check(report, "holdout_split_replay")["decision"] == "FAIL"
    assert get_check(report, "artifact_hashes_match_manifest")["decision"] == "FAIL"


def test_malformed_edge_line_fails_audit(tmp_path):
    paths = built_fixture(tmp_path)
    path = paths["out_dir"] / "adjacency_masked.tsv"
    path.write_text(path.read_text(encoding="utf-8") + "not-an-edge\n", encoding="utf-8")
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 1
    assert report["errors"] and "malformed edge line" in report["errors"][0]


def test_reproducible_builds_identical_hashes(tmp_path):
    first = build_fixture(tmp_path / "run1", main_fixture_works())
    code1, manifest1 = run_build_fixture(first)
    second = build_fixture(tmp_path / "run2", main_fixture_works())
    code2, manifest2 = run_build_fixture(second)
    assert code1 == code2 == 0
    for name in manifest1["hashes"]:
        assert manifest1["hashes"][name]["sha256"] == manifest2["hashes"][name]["sha256"], name
    assert manifest1["graph_hash"] == manifest2["graph_hash"]
    assert manifest1["mask_hash"] == manifest2["mask_hash"]
    assert manifest1["split_hash"] == manifest2["split_hash"]
    assert manifest1["counts"] == manifest2["counts"]
    assert manifest1["holdout"] == manifest2["holdout"]


def test_audit_only_passes_on_clean_build(tmp_path):
    paths = built_fixture(tmp_path)
    exit_code, report = run_audit_fixture(paths)
    assert exit_code == 0
    assert report["status"] == "PASS"


# ---------------------------------------------------------------------------
# Fatal inputs: CLI subprocess must exit 1 (ADR-013)
# ---------------------------------------------------------------------------


def test_cli_build_exit_0(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    paths["doc"].write_text("# synthetic graph protocol\n", encoding="utf-8")
    result = run_cli(paths)
    assert result.returncode == 0, result.stderr
    assert "Graph masked split built" in result.stdout


def test_cli_missing_works_exit_1(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    paths["works"].unlink()
    result = run_cli(paths)
    assert result.returncode == 1
    assert "Required input file is missing" in result.stderr


def test_cli_manifest_hash_mismatch_exit_1(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["artifacts"]["works_jsonl"]["sha256"] = "0" * 64
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    result = run_cli(paths)
    assert result.returncode == 1
    assert "sha256 mismatch" in result.stderr


def test_cli_unresolvable_cohort_exit_1(tmp_path):
    paths = build_fixture(
        tmp_path, main_fixture_works(), min_test=50, min_dev=30, max_test=50, max_dev=30
    )
    result = run_cli(paths)
    assert result.returncode == 1
    assert "cohort years unresolved" in result.stderr


def test_cli_gate_not_go_blocks_build(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    gate["decision"]["overall"] = "NO_GO"
    paths["gate"].write_text(json.dumps(gate), encoding="utf-8")
    result = run_cli(paths)
    assert result.returncode == 1
    assert "SG-016 is blocked" in result.stderr
    manifest = json.loads(paths["graph_manifest"].read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"


def test_cli_gate_report_hash_mismatch_exit_1(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    gate["provenance"]["inputs"]["works_jsonl"]["sha256"] = "1" * 64
    paths["gate"].write_text(json.dumps(gate), encoding="utf-8")
    result = run_cli(paths)
    assert result.returncode == 1
    assert "gate report works sha256 mismatch" in result.stderr


def test_cli_protocol_rule_change_rejected(tmp_path):
    paths = build_fixture(
        tmp_path,
        main_fixture_works(),
        edge_sort="sha256(UTF8('99999999|u|v'))_ascending_then_target_id",
    )
    result = run_cli(paths)
    assert result.returncode == 1
    assert "edge_sort changed" in result.stderr


def test_cli_missing_protocol_field_exit_1(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    protocol = json.loads(paths["protocol"].read_text(encoding="utf-8"))
    del protocol["tracks"]["B"]["split"]["heldout_fraction"]
    paths["protocol"].write_text(json.dumps(protocol), encoding="utf-8")
    result = run_cli(paths)
    assert result.returncode == 1
    assert "heldout_fraction" in result.stderr


def test_cli_audit_only_exit_1_after_tamper(tmp_path):
    paths = built_fixture(tmp_path)
    masked = read_edges(paths["out_dir"] / "adjacency_masked.tsv")
    forged = f"{A}\t{B}" if (A, B) not in masked else f"{B}\t{C}"
    with (paths["out_dir"] / "adjacency_masked.tsv").open("a", encoding="utf-8") as handle:
        handle.write(forged + "\n")
    result = run_cli(paths, "--audit-only")
    assert result.returncode == 1
    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))
    assert audit["status"] == "FAIL"


def test_novel_floor_below_floor_selection_is_fatal(tmp_path):
    """If the novel-candidate floor filters every query, the build must fail."""

    works = [
        make_work(bare(P), year=2018),
        make_work(bare(Q), year=2019),
        make_work(bare(T1), year=2025, refs=(bare(P), bare(Q))),
        make_work(bare(T2), year=2025, refs=(bare(P), bare(Q))),
        make_work(bare(D1), year=2024, refs=(bare(P), bare(Q))),
    ]
    paths = build_fixture(tmp_path, works, min_test=1, min_dev=1, min_candidates=100)
    result = run_cli(paths)
    assert result.returncode == 1
    assert "below the protocol floor" in result.stderr


def test_split_minimums_and_novel_floor_exclusions_counted(tmp_path):
    works = [
        make_work(bare(P), year=2018),
        make_work(bare(Q), year=2019),
        make_work(bare(T1), year=2025, refs=(bare(P), bare(Q))),
        make_work(bare(T2), year=2025, refs=(bare(P),)),  # R=1 -> h=0 -> excluded
        make_work(bare(D1), year=2024, refs=(bare(P), bare(Q))),
    ]
    paths = build_fixture(tmp_path, works, min_test=1, min_dev=1, min_refs=1)
    exit_code, manifest = run_build_fixture(paths)
    assert exit_code == 0, manifest.get("errors")
    assert manifest["holdout"]["excluded_by_split_minimums"] == {"test": 1, "dev": 0}
    assert manifest["holdout"]["selected_queries"] == {"test": 1, "dev": 1}
    split_payload = json.loads(
        (paths["out_dir"] / "split_queries.json").read_text(encoding="utf-8")
    )
    assert split_payload["cohorts"]["test"]["selected"] == [T1]


def test_duplicate_canonical_ids_fatal(tmp_path):
    works = main_fixture_works()
    paths = build_fixture(tmp_path, works)  # manifest/gate pinned to clean works
    duplicated = works + [dict(works[0])]  # exact duplicate record on disk only
    write_jsonl(paths["works"], duplicated)
    result = run_cli(paths)
    assert result.returncode == 1
    assert "duplicate canonical work ID" in result.stderr


def test_cli_empty_snapshot_exit_1(tmp_path):
    paths = build_fixture(tmp_path, main_fixture_works())
    paths["works"].write_text("", encoding="utf-8")
    # the manifest hash no longer matches the empty file, which must fail first
    result = run_cli(paths)
    assert result.returncode == 1
