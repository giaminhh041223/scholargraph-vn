"""SG-014 graph feasibility gate (pure measurements, no qrels).

Reads the frozen OpenAlex pilot snapshot and the BEIR corpus snapshots and
recomputes every graph-feasibility statistic from raw records:

* node/edge counts, self-loops, duplicate and reciprocal edges,
* isolated nodes, weakly connected components, directed density,
* publication-year cohorts and the Protocol v1 track-B cohort floors,
* DOI/title mapping coverage between the OpenAlex snapshot and BEIR corpora,
* BEIR reference-field enrichment audit (structural only).

Leakage contract: this module never reads qrels, relevance labels, or any
held-out edge list.  Graph edges come exclusively from ``referenced_works``
(OpenAlex) or the corpus reference fields (BEIR).  Qrels-based leakage audits
belong to the trusted split builder/auditor at SG-016 (Protocol v1 §2).

Failure contract (ADR-013/ADR-014, no silent bypass):

* Fatal problems — missing/unreadable/unparseable resources, empty snapshot,
  non-object records, missing or invalid IDs, duplicate node IDs, wrong-typed
  required fields, manifest checksum mismatch, missing protocol floors — are
  reported with an explicit error, the CLI exits ``1``, and no fabricated
  measurement is written.  Unmeasurable scalars are ``null`` with an error,
  never ``0``.
* Counted anomalies — self-loops, duplicate reference occurrences, reciprocal
  edge pairs, out-of-range years, out-of-snapshot references, missing
  title/abstract/year/DOI fields — are exact observations of the raw data.
  Protocol v1 track B prescribes their handling (exclude self, deduplicate
  references, mask reverse edges, drop missing years), so they are counted and
  reported 1:1 instead of failing the run; none is silently dropped.

Exit codes: ``0`` when the report was measured (the GO/NO-GO gate decision is
data, recorded in ``decision.overall`` — a NO-GO is a valid negative result);
``1`` on fatal resource or data-integrity failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_ID = "sg014-graph-feasibility"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = 1

WORK_ID_RE = re.compile(r"^W\d+$")
CANONICAL_NAMESPACE = "openalex:"

VALID_YEAR_MIN = 1900
VALID_YEAR_MAX = 2100

DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "dx.doi.org/")

ANOMALY_EXAMPLE_CAP = 20

# Gates that must pass for the overall GO decision.  Mapping/enrichment and
# coverage fields are recorded but do not gate track B by themselves; the
# binding constraints from Protocol v1 §4 B1 are the cohort floors.
GATING_CRITERIA = (
    "snapshot_provenance_integrity",
    "cohort_test_year_floor",
    "cohort_dev_year_floor",
    "minimum_novel_candidates_per_source",
    "masking_protocol_readiness",
)


class FeasibilityError(RuntimeError):
    """Fatal input/validation failure; the CLI must exit 1."""


@dataclass(frozen=True)
class WorkRecord:
    """One strictly validated OpenAlex work snapshot record."""

    canonical_id: str
    title: str | None
    has_abstract: bool
    doi_normalized: str | None
    publication_year: int | None
    year_status: str  # "valid" | "missing" | "out_of_range"
    has_venue_name: bool
    references: tuple[str, ...]  # canonical target IDs, may include self


@dataclass(frozen=True)
class ParsedSnapshot:
    """Validated snapshot: unique records plus counted non-fatal anomalies."""

    records: tuple[WorkRecord, ...]
    anomalies: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def canonical_work_id(value: Any) -> str:
    """Map any OpenAlex work URI/ID to the ``openalex:W<digits>`` namespace."""

    raw = str(value).strip().rstrip("/").rsplit("/", 1)[-1].upper()
    if not WORK_ID_RE.fullmatch(raw):
        raise ValueError(f"Invalid OpenAlex work ID: {value!r}")
    return f"{CANONICAL_NAMESPACE}{raw}"


def normalize_doi(value: Any) -> str | None:
    """Lower-case bare DOI (prefix stripped) or ``None`` when absent."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise FeasibilityError(f"DOI must be a string or null, got {type(value).__name__}")
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    for prefix in DOI_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix):].rstrip("/")
    return lowered.rstrip("/")


def normalize_title(value: Any) -> str | None:
    """Casefolded, whitespace-collapsed title or ``None`` when absent."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise FeasibilityError(f"Title must be a string or null, got {type(value).__name__}")
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed.casefold() if collapsed else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[Any]:
    """Read a JSONL file; blank lines are skipped, unparseable lines are fatal."""

    if not path.is_file():
        raise FeasibilityError(f"Required input file is missing: {path}")
    records: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise FeasibilityError(
                    f"{path}:{line_number}: invalid JSON line ({exc.msg})"
                ) from None
    return records


# ---------------------------------------------------------------------------
# OpenAlex snapshot parsing and statistics
# ---------------------------------------------------------------------------

def parse_works(records: Sequence[Any]) -> ParsedSnapshot:
    """Strictly validate raw OpenAlex work records.

    Fatal (raises :class:`FeasibilityError`): empty snapshot, non-object
    records, missing/blank/invalid IDs, duplicate canonical IDs, missing or
    non-list ``referenced_works``, non-string reference entries, wrong-typed
    title/abstract/year/DOI fields.

    Counted anomalies (kept, never silently dropped): self-references,
    repeated identical reference entries, out-of-range years, missing
    coverage fields.
    """

    if not records:
        raise FeasibilityError("OpenAlex snapshot is empty: no work records to audit")

    records_out: list[WorkRecord] = []
    seen: dict[str, int] = {}
    anomalies: dict[str, Any] = {
        "duplicate_reference_entries": 0,
        "out_of_range_publication_year_count": 0,
        "out_of_range_publication_year_examples": [],
        "missing_title_count": 0,
        "missing_abstract_count": 0,
        "missing_publication_year_count": 0,
        "missing_doi_count": 0,
    }

    for index, record in enumerate(records):
        where = f"record #{index}"
        if not isinstance(record, dict):
            raise FeasibilityError(f"{where}: expected a JSON object")
        if "id" not in record:
            raise FeasibilityError(f"{where}: missing required field 'id'")
        raw_id = record["id"]
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise FeasibilityError(f"{where}: 'id' must be a non-empty string")
        try:
            canonical = canonical_work_id(raw_id)
        except ValueError as exc:
            raise FeasibilityError(f"{where}: {exc}") from None
        if canonical in seen:
            raise FeasibilityError(
                f"{where}: duplicate canonical work ID {canonical} "
                f"(first seen at record #{seen[canonical]})"
            )
        seen[canonical] = index

        title = record.get("title") if "title" in record else None
        if title is not None and not isinstance(title, str):
            raise FeasibilityError(f"{where}: 'title' must be a string or null")
        if title is None or not title.strip():
            anomalies["missing_title_count"] += 1

        abstract = record.get("abstract_inverted_index") if "abstract_inverted_index" in record else None
        if abstract is not None and not isinstance(abstract, dict):
            raise FeasibilityError(
                f"{where}: 'abstract_inverted_index' must be an object or null"
            )
        if abstract is None or not abstract:
            anomalies["missing_abstract_count"] += 1

        doi_field = record.get("doi") if "doi" in record else None
        try:
            doi_normalized = normalize_doi(doi_field)
        except FeasibilityError as exc:
            raise FeasibilityError(f"{where}: {exc}") from None
        if doi_normalized is None:
            anomalies["missing_doi_count"] += 1

        if "publication_year" not in record or record["publication_year"] is None:
            year: int | None = None
            year_status = "missing"
            anomalies["missing_publication_year_count"] += 1
        else:
            raw_year = record["publication_year"]
            if isinstance(raw_year, bool) or not isinstance(raw_year, int):
                raise FeasibilityError(
                    f"{where}: 'publication_year' must be an integer or null, "
                    f"got {type(raw_year).__name__}"
                )
            if VALID_YEAR_MIN <= raw_year <= VALID_YEAR_MAX:
                year = raw_year
                year_status = "valid"
            else:
                year = None
                year_status = "out_of_range"
                anomalies["out_of_range_publication_year_count"] += 1
                if len(anomalies["out_of_range_publication_year_examples"]) < ANOMALY_EXAMPLE_CAP:
                    anomalies["out_of_range_publication_year_examples"].append(
                        {"canonical_id": canonical, "publication_year": raw_year}
                    )

        if "referenced_works" not in record:
            raise FeasibilityError(f"{where}: missing required field 'referenced_works'")
        refs = record["referenced_works"]
        if not isinstance(refs, list):
            raise FeasibilityError(
                f"{where}: 'referenced_works' must be a list, got {type(refs).__name__}"
            )
        canonical_refs: list[str] = []
        local_seen: set[str] = set()
        for position, target in enumerate(refs):
            if not isinstance(target, str):
                raise FeasibilityError(
                    f"{where}: referenced_works[{position}] must be a string, "
                    f"got {type(target).__name__}"
                )
            try:
                target_canonical = canonical_work_id(target)
            except ValueError as exc:
                raise FeasibilityError(f"{where}: referenced_works[{position}]: {exc}") from None
            if target_canonical in local_seen:
                anomalies["duplicate_reference_entries"] += 1
            local_seen.add(target_canonical)
            canonical_refs.append(target_canonical)

        location = record.get("primary_location") if "primary_location" in record else None
        has_venue = _has_venue_name(location)

        records_out.append(
            WorkRecord(
                canonical_id=canonical,
                title=title if (title is not None and title.strip()) else None,
                has_abstract=bool(abstract),
                doi_normalized=doi_normalized,
                publication_year=year,
                year_status=year_status,
                has_venue_name=has_venue,
                references=tuple(canonical_refs),
            )
        )

    return ParsedSnapshot(records=tuple(records_out), anomalies=anomalies)


def _has_venue_name(location: Any) -> bool:
    """Venue = primary_location.source.display_name or raw_source_name non-empty.

    Matches the corrected SG-013 predicate (correction artifact
    ``openalex_pilot_correction.json``): a location object with only a landing
    URL is not venue coverage.
    """

    if not isinstance(location, dict):
        return False
    source = location.get("source")
    if isinstance(source, dict):
        name = source.get("display_name")
        if isinstance(name, str) and name.strip():
            return True
    raw_name = location.get("raw_source_name")
    return isinstance(raw_name, str) and bool(raw_name.strip())


def compute_snapshot_stats(
    snapshot: ParsedSnapshot, snapshot_year: int
) -> dict[str, Any]:
    """Recompute every graph statistic from validated records (pure)."""

    records = snapshot.records
    n = len(records)
    id_set = {record.canonical_id for record in records}
    years = {
        record.canonical_id: record.publication_year
        for record in records
        if record.year_status == "valid"
    }

    reference_entries_total = sum(len(record.references) for record in records)
    internal_occurrences = 0
    unique_edges: set[tuple[str, str]] = set()
    self_loop_works: list[str] = []
    out_of_snapshot_occurrences = 0
    out_degree: dict[str, int] = {canonical: 0 for canonical in id_set}
    in_degree: dict[str, int] = {canonical: 0 for canonical in id_set}

    for record in records:
        for target in record.references:
            if target == record.canonical_id:
                self_loop_works.append(record.canonical_id)
                continue
            if target not in id_set:
                out_of_snapshot_occurrences += 1
                continue
            internal_occurrences += 1
            unique_edges.add((record.canonical_id, target))
            out_degree[record.canonical_id] += 1
            in_degree[target] += 1

    reciprocal_pairs = sum(1 for source, target in unique_edges if (target, source) in unique_edges) // 2
    nodes_with_edges = {node for edge in unique_edges for node in edge}
    isolated = id_set - nodes_with_edges
    components, largest_component = _weak_components(id_set, unique_edges)
    density = len(unique_edges) / (n * (n - 1)) if n > 1 else None

    doi_to_works: dict[str, list[str]] = {}
    for record in records:
        if record.doi_normalized is not None:
            doi_to_works.setdefault(record.doi_normalized, []).append(record.canonical_id)
    duplicated_doi_groups = {doi: ids for doi, ids in doi_to_works.items() if len(ids) > 1}

    year_distribution: dict[str, int] = {}
    for year in years.values():
        year_distribution[str(year)] = year_distribution.get(str(year), 0) + 1

    def coverage(count: int) -> dict[str, Any]:
        return {
            "count": count,
            "total": n,
            "fraction": round(count / n, 6) if n else None,
        }

    return {
        "counts": {
            "works": n,
            "unique_canonical_ids": len(id_set),
            "reference_entries_total": reference_entries_total,
            "internal_reference_occurrences": internal_occurrences,
            "unique_internal_directed_edges": len(unique_edges),
            "self_loop_count": len(self_loop_works),
            "duplicate_reference_entry_count": snapshot.anomalies["duplicate_reference_entries"],
            "reciprocal_edge_pair_count": reciprocal_pairs,
            "out_of_snapshot_reference_occurrences": out_of_snapshot_occurrences,
            "isolated_nodes": len(isolated),
            "nodes_with_at_least_one_internal_edge": len(nodes_with_edges),
            "weakly_connected_components": components,
            "largest_weak_component_size": largest_component,
            "max_internal_out_degree": max(out_degree.values()) if out_degree else None,
            "max_internal_in_degree": max(in_degree.values()) if in_degree else None,
        },
        "derived": {
            "isolated_node_fraction": round(len(isolated) / n, 6) if n else None,
            "directed_density": round(density, 12) if density is not None else None,
            "mean_internal_out_degree": round(len(unique_edges) / n, 6) if n else None,
            "largest_weak_component_fraction": round(largest_component / n, 6) if n else None,
        },
        "anomalies": {
            "self_loop_works": self_loop_works[:ANOMALY_EXAMPLE_CAP],
            "self_loop_count_exact": len(self_loop_works),
            "duplicate_reference_entry_count": snapshot.anomalies["duplicate_reference_entries"],
            "reciprocal_edge_pair_count": reciprocal_pairs,
            "out_of_range_publication_year_count": snapshot.anomalies[
                "out_of_range_publication_year_count"
            ],
            "out_of_range_publication_year_examples": snapshot.anomalies[
                "out_of_range_publication_year_examples"
            ],
            "handling": (
                "self-references are excluded from edges per Protocol v1 B2 ('khác u'); "
                "duplicate reference entries are deduplicated; reciprocal pairs are kept "
                "as directed edges and must be masked both ways at SG-016"
            ),
        },
        "coverage": {
            "title": coverage(n - snapshot.anomalies["missing_title_count"]),
            "abstract_inverted_index": coverage(n - snapshot.anomalies["missing_abstract_count"]),
            "doi": coverage(n - snapshot.anomalies["missing_doi_count"]),
            "has_any_reference": coverage(
                sum(1 for record in records if record.references)
            ),
            "valid_publication_year_1900_2100": coverage(len(years)),
            "venue_name_corrected_predicate": coverage(
                sum(1 for record in records if record.has_venue_name)
            ),
        },
        "years": {
            "valid_publication_year_count": len(years),
            "missing_publication_year_count": snapshot.anomalies["missing_publication_year_count"],
            "out_of_range_publication_year_count": snapshot.anomalies[
                "out_of_range_publication_year_count"
            ],
            "min_valid_year": min(years.values()) if years else None,
            "max_valid_year": max(years.values()) if years else None,
            "works_in_snapshot_publication_year": year_distribution.get(str(snapshot_year), 0),
            "distribution": dict(sorted(year_distribution.items(), key=lambda item: int(item[0]))),
        },
        "doi": {
            "works_with_doi": sum(len(ids) for ids in doi_to_works.values()),
            "unique_normalized_dois": len(doi_to_works),
            "duplicated_doi_groups": len(duplicated_doi_groups),
            "works_sharing_a_doi": sum(len(ids) for ids in duplicated_doi_groups.values()),
        },
        "reference_provenance": "referenced_works field only; qrels never read",
    }


def _weak_components(
    nodes: set[str], edges: set[tuple[str, str]]
) -> tuple[int, int]:
    """Weakly connected component count and largest component size (union-find)."""

    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for source, target in edges:
        root_source, root_target = find(source), find(target)
        if root_source != root_target:
            parent[root_source] = root_target

    sizes: dict[str, int] = {}
    for node in nodes:
        sizes[find(node)] = sizes.get(find(node), 0) + 1
    return len(sizes), max(sizes.values()) if sizes else 0


# ---------------------------------------------------------------------------
# Protocol v1 track-B cohort evaluation
# ---------------------------------------------------------------------------

def evaluate_cohorts(
    snapshot: ParsedSnapshot,
    snapshot_year: int,
    floors: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the Protocol v1 B1 cohort rules to the validated snapshot.

    Eligible source: valid year, non-empty title and abstract, and at least
    ``minimum_eligible_references`` distinct internal references whose target
    year is known and <= the source year.  ``test_year`` is the latest
    completed year before ``snapshot_year`` with at least
    ``minimum_test_queries`` eligible sources; ``dev_year`` is the latest year
    before ``test_year`` with at least ``minimum_dev_queries``.  No retrieval
    score or label is used anywhere.
    """

    records = snapshot.records
    id_set = {record.canonical_id for record in records}
    years = {
        record.canonical_id: record.publication_year
        for record in records
        if record.year_status == "valid"
    }
    min_refs = floors["minimum_eligible_references"]

    works_per_year: dict[int, int] = {}
    for year in years.values():
        works_per_year[year] = works_per_year.get(year, 0) + 1
    cumulative: dict[int, int] = {}
    running = 0
    for year in sorted(works_per_year):
        running += works_per_year[year]
        cumulative[year] = running

    eligible_by_year: dict[int, int] = {}
    universe_sizes: list[int] = []
    for record in records:
        source_year = record.publication_year
        if (
            source_year is None
            or record.title is None
            or not record.has_abstract
        ):
            continue
        eligible_refs = 0
        seen_targets: set[str] = set()
        for target in record.references:
            if target == record.canonical_id or target not in id_set or target in seen_targets:
                continue
            target_year = years.get(target)
            if target_year is not None and target_year <= source_year:
                eligible_refs += 1
                seen_targets.add(target)
        if eligible_refs >= min_refs:
            eligible_by_year[source_year] = eligible_by_year.get(source_year, 0) + 1
            # Pre-split conservative lower bound of the novel-candidate
            # universe: all valid-year works with year <= source year, minus
            # self, minus all internal references (observed + heldout unknown
            # pre-split; excluding all of them cannot overstate the floor).
            universe_sizes.append(cumulative[source_year] - 1 - eligible_refs)

    min_test = floors["minimum_test_queries"]
    min_dev = floors["minimum_dev_queries"]
    test_year = None
    test_year_reason = (
        f"no year before snapshot year {snapshot_year} has at least {min_test} eligible sources"
    )
    for year in sorted(eligible_by_year, reverse=True):
        if year < snapshot_year and eligible_by_year[year] >= min_test:
            test_year = year
            test_year_reason = (
                f"latest completed year before {snapshot_year} with at least {min_test} "
                f"eligible sources"
            )
            break

    dev_year = None
    dev_year_reason = "test_year is undefined, so the dev-year rule cannot select a year"
    if test_year is not None:
        for year in sorted(eligible_by_year, reverse=True):
            if year < test_year and eligible_by_year[year] >= min_dev:
                dev_year = year
                dev_year_reason = (
                    f"latest year before test_year {test_year} with at least {min_dev} "
                    f"eligible sources"
                )
                break
        else:
            dev_year_reason = (
                f"no year before test_year {test_year} has at least {min_dev} eligible sources"
            )

    max_per_year = max(eligible_by_year.values()) if eligible_by_year else 0
    universe_stats: dict[str, Any]
    if universe_sizes:
        universe_stats = {
            "sources_measured": len(universe_sizes),
            "min": min(universe_sizes),
            "median": statistics.median(universe_sizes),
            "max": max(universe_sizes),
            "sources_below_minimum_novel_candidates": sum(
                1 for size in universe_sizes
                if size < floors["minimum_novel_candidates_per_query"]
            ),
        }
    else:
        universe_stats = {
            "sources_measured": 0,
            "min": None,
            "median": None,
            "max": None,
            "sources_below_minimum_novel_candidates": None,
        }

    return {
        "eligible_definition": (
            "valid publication year; non-empty title and abstract; at least "
            f"{min_refs} distinct internal references with known target year <= source year"
        ),
        "eligible_source_count_by_publication_year": {
            str(year): count for year, count in sorted(eligible_by_year.items())
        },
        "total_eligible_sources": sum(eligible_by_year.values()),
        "max_eligible_sources_in_any_year": max_per_year,
        "test_year": test_year,
        "test_year_rule": floors["test_year_rule"],
        "test_year_reason": test_year_reason,
        "dev_year": dev_year,
        "dev_year_rule": floors["dev_year_rule"],
        "dev_year_reason": dev_year_reason,
        "novel_candidate_universe_lower_bound": universe_stats,
        "snapshot_year": snapshot_year,
        "floors_applied": {
            "minimum_test_queries": min_test,
            "minimum_dev_queries": min_dev,
            "minimum_eligible_references": min_refs,
            "minimum_novel_candidates_per_query": floors["minimum_novel_candidates_per_query"],
        },
    }


# ---------------------------------------------------------------------------
# BEIR corpus reference-field audit and mapping probes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BeirCorpus:
    """Validated BEIR corpus records plus reference edges (structural only)."""

    dataset: str
    doc_ids: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    reference_entries_total: int
    internal_reference_occurrences: int
    out_of_corpus_reference_occurrences: int
    docs_with_top_level_references: int
    docs_with_metadata_references: int
    docs_with_metadata_year: int
    docs_with_metadata_doi: int
    docs_with_top_level_doi: int
    docs_with_nonempty_title: int
    titles: dict[str, str]
    dois: dict[str, str]
    anomalies: dict[str, Any]


def parse_beir_corpus(dataset: str, records: Sequence[Any]) -> BeirCorpus:
    """Strictly validate one BEIR corpus and extract its internal reference edges.

    References may live at top level (``references``) or inside ``metadata``
    (``metadata.references``).  A record carrying both with different content
    is a fatal ambiguity; identical content is counted once per location.
    Edge resolution runs after every ID is known, so references to documents
    that appear later in the file are counted.
    """

    if not records:
        raise FeasibilityError(f"BEIR corpus '{dataset}' is empty: no documents to audit")

    doc_ids: list[str] = []
    seen: dict[str, int] = {}
    titles: dict[str, str] = {}
    dois: dict[str, str] = {}
    reference_lists: dict[str, list[str]] = {}
    reference_entries_total = 0
    docs_top_refs = 0
    docs_meta_refs = 0
    docs_meta_year = 0
    docs_meta_doi = 0
    docs_top_doi = 0
    docs_with_title = 0
    self_loops = 0
    duplicate_reference_entries = 0

    # Pass 1: strict validation and field collection.
    for index, record in enumerate(records):
        where = f"{dataset} corpus record #{index}"
        if not isinstance(record, dict):
            raise FeasibilityError(f"{where}: expected a JSON object")
        if "_id" not in record:
            raise FeasibilityError(f"{where}: missing required field '_id'")
        doc_id = record["_id"]
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise FeasibilityError(f"{where}: '_id' must be a non-empty string")
        if doc_id in seen:
            raise FeasibilityError(
                f"{where}: duplicate corpus ID {doc_id!r} "
                f"(first seen at record #{seen[doc_id]})"
            )
        seen[doc_id] = index
        doc_ids.append(doc_id)

        title = record.get("title") if "title" in record else None
        if title is not None and not isinstance(title, str):
            raise FeasibilityError(f"{where}: 'title' must be a string or null")
        normalized_title = normalize_title(title) if title is not None else None
        if normalized_title:
            docs_with_title += 1
            titles.setdefault(normalized_title, doc_id)

        metadata = record.get("metadata") if "metadata" in record else None
        if metadata is not None and not isinstance(metadata, dict):
            raise FeasibilityError(f"{where}: 'metadata' must be an object or null")

        top_refs = record.get("references") if "references" in record else None
        if top_refs is not None and not isinstance(top_refs, list):
            raise FeasibilityError(f"{where}: top-level 'references' must be a list or null")
        meta_refs = metadata.get("references") if isinstance(metadata, dict) else None
        if meta_refs is not None and not isinstance(meta_refs, list):
            raise FeasibilityError(f"{where}: 'metadata.references' must be a list or null")
        if top_refs is not None and meta_refs is not None and top_refs != meta_refs:
            raise FeasibilityError(
                f"{where}: ambiguous references — top-level and metadata.references differ"
            )

        reference_list: list[str] | None = None
        if top_refs is not None:
            docs_top_refs += 1 if top_refs else 0
            if top_refs:
                reference_list = top_refs
        if meta_refs is not None:
            docs_meta_refs += 1 if meta_refs else 0
            if reference_list is None and meta_refs:
                reference_list = meta_refs

        if reference_list:
            validated: list[str] = []
            local_seen: set[str] = set()
            for position, target in enumerate(reference_list):
                if not isinstance(target, str):
                    raise FeasibilityError(
                        f"{where}: references[{position}] must be a string, "
                        f"got {type(target).__name__}"
                    )
                if not target.strip():
                    raise FeasibilityError(f"{where}: references[{position}] is blank")
                reference_entries_total += 1
                if target == doc_id:
                    self_loops += 1
                if target in local_seen:
                    duplicate_reference_entries += 1
                local_seen.add(target)
                validated.append(target)
            reference_lists[doc_id] = validated

        if isinstance(metadata, dict):
            year = metadata.get("year")
            if isinstance(year, int) or (isinstance(year, str) and year.strip().isdigit()):
                docs_meta_year += 1
            meta_doi = metadata.get("doi")
            if isinstance(meta_doi, str) and meta_doi.strip():
                docs_meta_doi += 1
                normalized = normalize_doi(meta_doi)
                if normalized is not None:
                    dois.setdefault(normalized, doc_id)
        top_doi = record.get("doi") if "doi" in record else None
        if isinstance(top_doi, str) and top_doi.strip():
            docs_top_doi += 1
            normalized = normalize_doi(top_doi)
            if normalized is not None:
                dois.setdefault(normalized, doc_id)

    # Pass 2: resolve edges with the complete ID universe.
    id_set = set(doc_ids)
    edge_list: list[tuple[str, str]] = []
    edges: set[tuple[str, str]] = set()
    internal_occurrences = 0
    out_of_corpus = 0
    for doc_id, targets in reference_lists.items():
        for target in targets:
            if target == doc_id:
                continue
            if target not in id_set:
                out_of_corpus += 1
                continue
            internal_occurrences += 1
            if (doc_id, target) not in edges:
                edges.add((doc_id, target))
                edge_list.append((doc_id, target))

    return BeirCorpus(
        dataset=dataset,
        doc_ids=tuple(doc_ids),
        edges=tuple(edge_list),
        reference_entries_total=reference_entries_total,
        internal_reference_occurrences=internal_occurrences,
        out_of_corpus_reference_occurrences=out_of_corpus,
        docs_with_top_level_references=docs_top_refs,
        docs_with_metadata_references=docs_meta_refs,
        docs_with_metadata_year=docs_meta_year,
        docs_with_metadata_doi=docs_meta_doi,
        docs_with_top_level_doi=docs_top_doi,
        docs_with_nonempty_title=docs_with_title,
        titles=titles,
        dois=dois,
        anomalies={
            "self_loop_count": self_loops,
            "duplicate_reference_entry_count": duplicate_reference_entries,
        },
    )


def beir_corpus_stats(corpus: BeirCorpus) -> dict[str, Any]:
    """Statistics for one validated BEIR corpus (pure)."""

    total_docs = len(corpus.doc_ids)
    edge_set = set(corpus.edges)
    reciprocal_pairs = sum(1 for s, t in edge_set if (t, s) in edge_set) // 2
    nodes_with_edges = {node for edge in edge_set for node in edge}
    doi_count = len(corpus.dois)

    return {
        "dataset": corpus.dataset,
        "counts": {
            "documents": total_docs,
            "reference_entries_total": corpus.reference_entries_total,
            "internal_reference_occurrences_within_corpus": corpus.internal_reference_occurrences,
            "unique_internal_directed_edges": len(edge_set),
            "docs_with_top_level_references": corpus.docs_with_top_level_references,
            "docs_with_metadata_references": corpus.docs_with_metadata_references,
            "docs_without_any_reference_list": total_docs - max(
                corpus.docs_with_top_level_references, corpus.docs_with_metadata_references
            ),
            "self_loop_count": corpus.anomalies["self_loop_count"],
            "duplicate_reference_entry_count": corpus.anomalies["duplicate_reference_entry_count"],
            "reciprocal_edge_pair_count": reciprocal_pairs,
            "out_of_corpus_reference_occurrences": corpus.out_of_corpus_reference_occurrences,
            "docs_with_metadata_year": corpus.docs_with_metadata_year,
            "docs_with_doi": doi_count,
        },
        "graph_connectivity": {
            "docs_with_at_least_one_internal_edge": len(nodes_with_edges),
            "isolated_docs_in_reference_graph": total_docs - len(nodes_with_edges)
            if edge_set
            else total_docs,
        },
        "reference_field_location": (
            "metadata.references"
            if corpus.docs_with_metadata_references
            else ("top_level_references" if corpus.docs_with_top_level_references else "absent")
        ),
        "provenance": (
            "structural audit of corpus reference fields only; qrels and queries "
            "are not read by this module (label-leakage audit is SG-016 scope)"
        ),
    }


def compute_mapping(
    snapshot: ParsedSnapshot, corpora: Sequence[BeirCorpus]
) -> dict[str, Any]:
    """DOI and provisional exact-title mapping coverage (no qrels involved)."""

    snapshot_dois = {
        record.doi_normalized: record.canonical_id
        for record in snapshot.records
        if record.doi_normalized is not None
    }
    doi_match_count = 0
    per_dataset_doi: dict[str, int] = {}
    for corpus in corpora:
        matches = sum(1 for doi in corpus.dois if doi in snapshot_dois)
        per_dataset_doi[corpus.dataset] = matches
        doi_match_count += matches

    snapshot_titles = {
        normalize_title(record.title): record.canonical_id
        for record in snapshot.records
        if record.title is not None
    }
    snapshot_title_collisions = (
        sum(1 for record in snapshot.records if record.title is not None)
        - len(snapshot_titles)
    )
    per_dataset_title: dict[str, Any] = {}
    for corpus in corpora:
        shared = set(snapshot_titles) & set(corpus.titles)
        per_dataset_title[corpus.dataset] = {
            "exact_normalized_title_matches": len(shared),
            "distinct_openalex_works_matched": len({snapshot_titles[t] for t in shared}),
            "distinct_beir_docs_matched": len({corpus.titles[t] for t in shared}),
            "beir_normalized_title_collisions": corpus.docs_with_nonempty_title
            - len(corpus.titles),
        }

    return {
        "doi_mapping": {
            "openalex_works_with_doi": len(snapshot_dois),
            "openalex_unique_normalized_dois": len(snapshot_dois),
            "beir_docs_with_doi": sum(len(corpus.dois) for corpus in corpora),
            "beir_unique_normalized_dois": len(
                {doi for corpus in corpora for doi in corpus.dois}
            ),
            "doi_matches": doi_match_count,
            "doi_matches_per_dataset": per_dataset_doi,
            "verdict": (
                "DOI join infeasible: the BEIR corpus snapshots expose no DOI field"
                if doi_match_count == 0 and not any(corpus.dois for corpus in corpora)
                else "doi join measured on normalized bare DOIs"
            ),
        },
        "provisional_exact_title_probe": {
            "openalex_works_with_title": len(snapshot_titles),
            "openalex_normalized_title_collisions": snapshot_title_collisions,
            "per_dataset": per_dataset_title,
            "limitation": (
                "exact casefolded-whitespace-collapsed title equality only; no version, "
                "author, or venue disambiguation; a positive/negative mapping decision "
                "must not be built on this probe alone"
            ),
        },
        "provenance": "mapping measured on snapshot fields only; no external data fetched",
    }


# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------

def evaluate_gate(
    snapshot_stats: Mapping[str, Any],
    cohorts: Mapping[str, Any],
    mapping: Mapping[str, Any],
    beir_stats: Sequence[Mapping[str, Any]],
    masking_protocol_documented: bool,
) -> dict[str, Any]:
    """Deterministic GO/NO-GO gate per Protocol v1 §4 B1 (pure)."""

    counts = snapshot_stats["counts"]
    integrity_pass = (
        counts["works"] > 0 and counts["unique_canonical_ids"] == counts["works"]
    )
    test_floor = cohorts["floors_applied"]["minimum_test_queries"]
    dev_floor = cohorts["floors_applied"]["minimum_dev_queries"]
    test_year_pass = cohorts["test_year"] is not None
    dev_year_pass = cohorts["dev_year"] is not None
    universe = cohorts["novel_candidate_universe_lower_bound"]
    candidates_pass = (
        universe["sources_measured"] > 0
        and universe["sources_below_minimum_novel_candidates"] == 0
    )

    criteria: list[dict[str, Any]] = [
        {
            "criterion_id": "snapshot_provenance_integrity",
            "decision": "GO" if integrity_pass else "NO_GO",
            "requirement": (
                "snapshot non-empty; every record maps to one unique canonical ID; "
                "manifest sha256 verified"
            ),
            "measured": {
                "works": counts["works"],
                "unique_canonical_ids": counts["unique_canonical_ids"],
            },
            "source": "Protocol v1 §2 (raw snapshot immutability) and ADR-013",
        },
        {
            "criterion_id": "cohort_test_year_floor",
            "decision": "GO" if test_year_pass else "NO_GO",
            "requirement": (
                f"a test_year before the snapshot year with at least {test_floor} "
                "eligible sources exists"
            ),
            "measured": {
                "test_year": cohorts["test_year"],
                "max_eligible_sources_in_any_year": cohorts["max_eligible_sources_in_any_year"],
                "reason": cohorts["test_year_reason"],
            },
            "source": "configs/protocol_v1.json tracks.B.graph_gate (test_year_rule)",
        },
        {
            "criterion_id": "cohort_dev_year_floor",
            "decision": "GO" if dev_year_pass else "NO_GO",
            "requirement": (
                f"a dev_year before test_year with at least {dev_floor} eligible sources exists"
            ),
            "measured": {
                "dev_year": cohorts["dev_year"],
                "reason": cohorts["dev_year_reason"],
            },
            "source": "configs/protocol_v1.json tracks.B.graph_gate (dev_year_rule)",
        },
        {
            "criterion_id": "minimum_novel_candidates_per_source",
            "decision": "GO" if candidates_pass else "NO_GO",
            "requirement": (
                f"every eligible source keeps at least "
                f"{cohorts['floors_applied']['minimum_novel_candidates_per_query']} novel "
                "eligible candidates"
            ),
            "measured": universe,
            "source": "configs/protocol_v1.json tracks.B.graph_gate "
                      "(minimum_novel_candidates_per_query)",
        },
        {
            "criterion_id": "internal_edge_availability",
            "decision": "RECORDED",
            "requirement": "directed internal citation edges exist inside the snapshot",
            "measured": {
                "unique_internal_directed_edges": counts["unique_internal_directed_edges"],
                "internal_reference_occurrences": counts["internal_reference_occurrences"],
                "out_of_snapshot_reference_occurrences":
                    counts["out_of_snapshot_reference_occurrences"],
            },
            "source": "Protocol v1 §4 B1 (audit fields)",
        },
        {
            "criterion_id": "doi_id_mapping_openalex_beir",
            "decision": "RECORDED",
            "requirement": (
                "mapping capability between OpenAlex snapshot and BEIR corpora "
                "(track B is OpenAlex-only; BEIR enrichment is out of track B scope)"
            ),
            "measured": mapping["doi_mapping"],
            "source": "Protocol v1 §4 B1 (DOI/ID mapping audit field)",
        },
        {
            "criterion_id": "beir_reference_enrichment_feasibility",
            "decision": "RECORDED",
            "requirement": (
                "whether BEIR corpus reference fields could serve as an alternative "
                "citation graph (timeboxed evaluation)"
            ),
            "measured": {entry["dataset"]: entry for entry in beir_stats},
            "source": "SG-014 task card (timebox BEIR enrichment)",
        },
        {
            "criterion_id": "masking_protocol_readiness",
            "decision": "GO" if masking_protocol_documented else "NO_GO",
            "requirement": (
                "holdout/cutoff/masking design documented before any graph experiment "
                "(docs/GRAPH_PROTOCOL.md); verification on real masked graph is SG-016"
            ),
            "measured": {
                "design_document": "docs/GRAPH_PROTOCOL.md",
                "design_document_present": masking_protocol_documented,
                "two_way_masking_defined": masking_protocol_documented,
            },
            "source": "Protocol v1 §4 B2 and SG-014 task card",
        },
    ]

    gating = {criterion["criterion_id"]: criterion["decision"] for criterion in criteria}
    overall = "GO" if all(gating[name] == "GO" for name in GATING_CRITERIA) else "NO_GO"

    decision: dict[str, Any] = {
        "overall": overall,
        "overall_rule": (
            "overall GO iff every gating criterion is GO; RECORDED criteria are "
            "context, not gates; a NO-GO is a valid measured outcome, not a run failure"
        ),
        "gating_criteria": GATING_CRITERIA,
        "criteria": criteria,
        "binding_no_go_evidence": [],
        "sg015_requirements_if_no_go": [],
        "scope_dependency_adjustments": [],
    }
    if overall == "NO_GO":
        decision["binding_no_go_evidence"] = [
            {
                "criterion_id": "cohort_test_year_floor",
                "evidence": (
                    f"max eligible sources in any year = "
                    f"{cohorts['max_eligible_sources_in_any_year']}; "
                    f"test_year = {cohorts['test_year']} ({cohorts['test_year_reason']})"
                ),
            },
            {
                "criterion_id": "cohort_dev_year_floor",
                "evidence": f"dev_year = {cohorts['dev_year']} ({cohorts['dev_year_reason']})",
            },
            {
                "criterion_id": "graph_sparsity_context",
                "evidence": (
                    f"{counts['isolated_nodes']}/{counts['works']} isolated nodes, "
                    f"{counts['unique_internal_directed_edges']} unique internal directed "
                    f"edges out of {counts['reference_entries_total']} reference entries"
                ),
            },
        ]
        decision["sg015_requirements_if_no_go"] = [
            "Replace the seeded random topic sample with a citation-connected snapshot "
            "strategy (for example iterative referenced_works/cited_by expansion around "
            "seed works, or a venue/year cohort with high internal citation density), "
            "recorded in a manifest and ADR before any download.",
            "Keep every Protocol v1 floor unchanged (minimum_test_queries=50, "
            "minimum_dev_queries=30, minimum_eligible_references=2, "
            "minimum_novel_candidates_per_query=100); floors must not be lowered after "
            "looking at results.",
            "Re-run this feasibility CLI on the SG-015 core snapshot and require every "
            "gating criterion GO before SG-016 builds any masked split.",
            "Pin the core snapshot with a manifest (sha256, timestamps, filter, seed) and "
            "freeze it; no silent snapshot change afterwards.",
            "Handle raw-data anomalies per docs/GRAPH_PROTOCOL.md (exclude self-references, "
            "deduplicate reference entries, mask reciprocal pairs both ways) with counts "
            "reported, never silently dropped.",
        ]
        decision["scope_dependency_adjustments"] = [
            "SG-016 (graph and masked split) stays blocked until the SG-015 core snapshot "
            "passes a re-run of this gate with overall=GO.",
            "BEIR enrichment is not adopted: SciFact exposes no reference field and the "
            "SCIDOCS reference graph is out of track-B protocol shape (its queries are "
            "not corpus nodes; track A forbids graph/external metadata); the SCIDOCS "
            "reference-field counts stay recorded for the record only.",
            "OpenAlex-to-BEIR mapping cannot rely on DOI (BEIR corpora expose no DOI); "
            "any future cross-corpus mapping needs its own ADR and audit.",
            "Track A (BEIR text benchmark) is unaffected by this gate.",
        ]
    return decision


# ---------------------------------------------------------------------------
# Provenance and report assembly
# ---------------------------------------------------------------------------

def load_floors(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Extract track-B graph-gate floors from the protocol config; missing = fatal."""

    gate = (
        protocol.get("tracks", {})
        .get("B", {})
        .get("graph_gate")
    )
    required = (
        "minimum_dev_queries",
        "minimum_test_queries",
        "minimum_eligible_references",
        "minimum_novel_candidates_per_query",
        "test_year_rule",
        "dev_year_rule",
    )
    if not isinstance(gate, dict):
        raise FeasibilityError("protocol config lacks tracks.B.graph_gate object")
    missing = [key for key in required if key not in gate]
    if missing:
        raise FeasibilityError(
            f"protocol config tracks.B.graph_gate lacks required floors: {missing}"
        )
    floors: dict[str, Any] = {}
    for key in required:
        value = gate[key]
        if key.startswith("minimum_") and (isinstance(value, bool) or not isinstance(value, int)):
            raise FeasibilityError(f"protocol floor {key} must be an integer, got {value!r}")
        if key.endswith("_rule") and (not isinstance(value, str) or not value.strip()):
            raise FeasibilityError(f"protocol rule {key} must be a non-empty string")
        floors[key] = value
    return floors


def verify_manifest(
    manifest: Mapping[str, Any], works_path: Path, works_sha256: str
) -> dict[str, Any]:
    """Cross-check the snapshot manifest against the works file actually read."""

    if manifest.get("status") != "COMPLETED":
        raise FeasibilityError("snapshot manifest status is not COMPLETED")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("works_jsonl"), dict):
        raise FeasibilityError("snapshot manifest lacks artifacts.works_jsonl object")
    entry = artifacts["works_jsonl"]
    expected_sha = entry.get("sha256")
    if not isinstance(expected_sha, str) or not expected_sha:
        raise FeasibilityError("snapshot manifest works_jsonl entry lacks sha256")
    if expected_sha != works_sha256:
        raise FeasibilityError(
            "works.jsonl sha256 mismatch: manifest "
            f"{expected_sha} != measured {works_sha256}"
        )
    completed_at = manifest.get("retrieved_completed_at")
    if not isinstance(completed_at, str) or len(completed_at) < 4 or not completed_at[:4].isdigit():
        raise FeasibilityError(
            "snapshot manifest lacks a parsable retrieved_completed_at timestamp"
        )
    snapshot_year = int(completed_at[:4])
    return {
        "verified": True,
        "snapshot_id": manifest.get("snapshot_id"),
        "manifest_sha256_of_works": expected_sha,
        "snapshot_year": snapshot_year,
        "retrieved_completed_at": completed_at,
    }


def build_report(
    *,
    works_path: Path,
    manifest_path: Path,
    protocol_path: Path,
    scifact_corpus_path: Path,
    scidocs_corpus_path: Path,
    report_path: Path,
    manifest_check: Mapping[str, Any],
    snapshot_stats: Mapping[str, Any],
    cohorts: Mapping[str, Any],
    scifact_stats: Mapping[str, Any],
    scidocs_stats: Mapping[str, Any],
    mapping: Mapping[str, Any],
    decision: Mapping[str, Any],
    measured_at: datetime,
    command_argv: Sequence[str],
) -> dict[str, Any]:
    """Assemble the machine-readable gate report (pure aside from stat calls)."""

    inputs = {}
    for label, path in (
        ("works_jsonl", works_path),
        ("snapshot_manifest", manifest_path),
        ("protocol_config", protocol_path),
        ("scifact_corpus", scifact_corpus_path),
        ("scidocs_corpus", scidocs_corpus_path),
    ):
        inputs[label] = {
            "path": _display_path(path),
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "graph_feasibility_gate",
        "task_id": "SG-014",
        "module": {"id": MODULE_ID, "version": MODULE_VERSION},
        "status": "MEASURED",
        "measured_at": _iso(measured_at),
        "command": list(command_argv),
        "runtime": {"python": sys.version.split()[0], "platform": sys.platform},
        "provenance": {
            "inputs": inputs,
            "snapshot_verification": dict(manifest_check),
            "exit_code_semantics": {
                "0": "report measured (gate decision may still be NO_GO — data, not failure)",
                "1": "fatal missing resource / data integrity failure; no fabricated stats",
            },
        },
        "openalex_snapshot": dict(snapshot_stats),
        "protocol_b_cohorts": dict(cohorts),
        "beir_reference_enrichment": {
            "scifact": dict(scifact_stats),
            "scidocs": dict(scidocs_stats),
        },
        "mapping": dict(mapping),
        "qrels_used": False,
        "leakage_audit": {
            "status": "deferred_to_SG016",
            "reason": (
                "this gate runs pre-label per Protocol v1 §2: it reads no qrels and no "
                "heldout edge list; the masked-split leakage audit belongs to the trusted "
                "split builder/auditor at SG-016"
            ),
        },
        "decision": dict(decision),
        "known_limitations": [
            (
                f"The audited snapshot is a {snapshot_stats['counts']['works']}-work sample "
                "from the pinned manifest sampling plan; its sparsity is "
                "measured evidence for this snapshot only and is not an estimate for any "
                "other sampling strategy."
            ),
            "OpenAlex referenced_works contains only references OpenAlex successfully "
            "matched to another work.",
            "The novel-candidate universe is a pre-split conservative lower bound "
            "(all valid-year works with year <= source year, minus self, minus all "
            "internal references of the source).",
            "BEIR reference-field findings are structural only; no qrels, queries, or "
            "relevance labels were read by this module.",
        ],
    }


def run_feasibility(
    works_path: Path,
    manifest_path: Path,
    protocol_path: Path,
    scifact_corpus_path: Path,
    scidocs_corpus_path: Path,
    report_path: Path,
    command_argv: Sequence[str] | None = None,
    measured_at: datetime | None = None,
    masking_doc_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run the full gate; return ``(exit_code, report_or_error)``.

    Fatal failures produce ``exit_code=1`` and a FAIL report (no fabricated
    measurements); a measured gate decision (GO or NO_GO) exits ``0``.
    ``masking_doc_path`` is checked for existence only (the holdout/cutoff/
    masking design document, ``docs/GRAPH_PROTOCOL.md`` in production).
    """

    errors: list[str] = []
    try:
        for required in (works_path, manifest_path, protocol_path,
                         scifact_corpus_path, scidocs_corpus_path):
            if not required.is_file():
                raise FeasibilityError(f"Required input file is missing: {required}")
        works_sha256 = _sha256_file(works_path)
        works_records = _read_jsonl(works_path)
        snapshot = parse_works(works_records)

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            raise FeasibilityError("snapshot manifest must be a JSON object")
        manifest_check = verify_manifest(manifest, works_path, works_sha256)

        with protocol_path.open("r", encoding="utf-8") as handle:
            protocol = json.load(handle)
        if not isinstance(protocol, dict):
            raise FeasibilityError("protocol config must be a JSON object")
        floors = load_floors(protocol)

        scifact_records = _read_jsonl(scifact_corpus_path)
        scifact_corpus = parse_beir_corpus("scifact", scifact_records)
        scidocs_records = _read_jsonl(scidocs_corpus_path)
        scidocs_corpus = parse_beir_corpus("scidocs", scidocs_records)
    except FeasibilityError as exc:
        errors.append(str(exc))
        report = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "graph_feasibility_gate",
            "task_id": "SG-014",
            "module": {"id": MODULE_ID, "version": MODULE_VERSION},
            "status": "FAIL",
            "errors": errors,
            "measured_at": _iso(measured_at or datetime.now(timezone.utc)),
            "command": list(command_argv or sys.argv[1:]),
        }
        _write_report(report_path, report)
        return 1, report

    snapshot_year = int(manifest_check["snapshot_year"])
    masking_documented = bool(
        masking_doc_path is not None and masking_doc_path.is_file()
    )
    snapshot_stats = compute_snapshot_stats(snapshot, snapshot_year)
    cohorts = evaluate_cohorts(snapshot, snapshot_year, floors)
    scifact_stats = beir_corpus_stats(scifact_corpus)
    scidocs_stats = beir_corpus_stats(scidocs_corpus)
    mapping = compute_mapping(snapshot, [scifact_corpus, scidocs_corpus])
    decision = evaluate_gate(
        snapshot_stats,
        cohorts,
        mapping,
        [scifact_stats, scidocs_stats],
        masking_documented,
    )

    report = build_report(
        works_path=works_path,
        manifest_path=manifest_path,
        protocol_path=protocol_path,
        scifact_corpus_path=scifact_corpus_path,
        scidocs_corpus_path=scidocs_corpus_path,
        report_path=report_path,
        manifest_check=manifest_check,
        snapshot_stats=snapshot_stats,
        cohorts=cohorts,
        scifact_stats=scifact_stats,
        scidocs_stats=scidocs_stats,
        mapping=mapping,
        decision=decision,
        measured_at=measured_at or datetime.now(timezone.utc),
        command_argv=command_argv or sys.argv[1:],
    )
    _write_report(report_path, report)
    return 0, report


def _write_report(report_path: Path, report: Mapping[str, Any]) -> None:
    """Atomically persist the report; an unwritable path is itself fatal."""

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary = report_path.with_name(f".{report_path.name}.tmp-{os.getpid()}")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(report_path)
        finally:
            if temporary.exists():
                temporary.unlink()
    except OSError as exc:
        raise FeasibilityError(f"cannot write report to {report_path}: {exc}") from None


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SG-014 graph feasibility gate over the frozen OpenAlex/BEIR snapshots"
    )
    parser.add_argument("--works", type=Path, required=True,
                        help="OpenAlex snapshot works.jsonl")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="snapshot manifest (sha256 cross-check, snapshot year)")
    parser.add_argument("--protocol", type=Path, required=True,
                        help="protocol config providing track-B graph-gate floors")
    parser.add_argument("--scifact-corpus", type=Path, required=True,
                        help="BEIR SciFact corpus.jsonl")
    parser.add_argument("--scidocs-corpus", type=Path, required=True,
                        help="BEIR SCIDOCS corpus.jsonl")
    parser.add_argument("--report", type=Path,
                        default=Path("artifacts/reports/graph_feasibility.json"))
    parser.add_argument("--masking-doc", type=Path,
                        default=Path("docs/GRAPH_PROTOCOL.md"),
                        help="holdout/cutoff/masking design document whose "
                             "presence feeds the masking_protocol_readiness criterion")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    try:
        exit_code, report = run_feasibility(
            works_path=args.works,
            manifest_path=args.manifest,
            protocol_path=args.protocol,
            scifact_corpus_path=args.scifact_corpus,
            scidocs_corpus_path=args.scidocs_corpus,
            report_path=args.report,
            command_argv=argv_list,
            masking_doc_path=args.masking_doc,
        )
    except FeasibilityError as exc:
        print(f"FEASIBILITY FAILED: {exc}", file=sys.stderr)
        return 1
    if exit_code != 0:
        for error in report.get("errors", []):
            print(f"FEASIBILITY FAILED: {error}", file=sys.stderr)
        return exit_code
    decision = report["decision"]["overall"]
    print(
        f"Graph feasibility gate measured: decision={decision}, "
        f"report={_display_path(args.report)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
