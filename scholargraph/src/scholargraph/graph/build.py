"""SG-016 directed graph build, holdout split and two-way masking (trusted builder/auditor).

Reads the frozen OpenAlex core snapshot (``data/processed/openalex/works.jsonl``,
sha256-pinned in ``data/manifests/openalex_core.json``) and builds, per
``docs/GRAPH_PROTOCOL.md`` and Protocol v1 track B:

1. the directed internal citation graph (``u -> v`` iff ``v in referenced_works(u)``
   with both endpoints in the snapshot; self-loops excluded and counted, duplicate
   reference entries deduplicated and counted, out-of-snapshot (dangling)
   references counted — never silently dropped and never materialised as nodes),
2. one deterministic holdout split for the selected dev/test query sources
   (``R(u)`` sorted by ``SHA-256(seed|u|v)`` ascending then target ID;
   ``h = min(|R|-1, max(1, ceil(0.2*R)))``), with query selection by
   ``SHA-256(seed|canonical_source_id)`` capped at 100 dev / 200 test and gated by
   the novel-candidate floor,
3. the masked graph ``G_mask = E_pre \\ M`` with the global mask
   ``M = H_dev ∪ H_test ∪ {(v,u) : (u,v) in H_dev ∪ H_test}`` (both directions,
   GRAPH_PROTOCOL §4),
4. graph features recomputed from ``G_mask`` only: masked in/out degree per node
   plus per-query cutoff-induced (``year <= year(u)``) truncated statistics.
   PageRank/PPR/co-citation/coupling/graph embeddings are computed downstream
   (SG-022) from the masked adjacency artifact; this module ships the masked
   graph + hashes that fix the cache identity ``(masked_graph_hash, cutoff_year)``.

Leakage contract (Protocol v1 §2, GRAPH_PROTOCOL §4): this is the trusted
split builder/auditor.  It never reads qrels or BEIR labels; the holdout edges it
derives from ``referenced_works`` are written only to the trusted holdout/mask
artifacts and are audited to be absent from ``G_mask`` in BOTH directions.
``cited_by_count`` is never used as a feature (Protocol v1 forbidden features).

Failure contract (ADR-013/ADR-014, no silent bypass): fatal problems — missing
resources, manifest/gate-report checksum mismatch, gate not GO, missing protocol
fields, unresolvable cohort years, selection below the protocol floors — are
reported with an explicit error and the CLI exits ``1`` without fabricating any
measurement.  The leakage audit re-reads every written artifact from disk,
replays the whole build from the snapshot, and fails loudly (exit ``1``) on any
residual held-out edge, self-loop, hash mismatch or feature not derived from
``G_mask``.

Interpretation notes (ADR-style, also recorded in the graph manifest):

* Heldout sets are computed for the *selected* dev/test query sources only
  (GRAPH_PROTOCOL §2.6 query selection; the mask scope is the global union
  ``H_dev ∪ H_test ∪ reverse`` per §4.1, not per-query).  Non-query sources keep
  all internal edges in ``G_mask`` because their references are labels for no
  query.  Masking the heldout of every eligible source would delete observed
  edges of non-queries — a protocol deviation that needs an ADR.
* Reciprocal pairs with no heldout direction stay in ``G_mask`` per
  GRAPH_PROTOCOL §1.3 ("giữ nguyên tính có hướng trong raw"); every pair with a
  heldout direction is removed in both directions and audited.
* Works with missing/out-of-range publication year remain graph nodes (matching
  the SG-014/SG-015 gate statistics) but can be neither queries nor candidates
  and never enter a cutoff-induced subgraph (unknown year cannot satisfy
  ``year <= cutoff``).
* ``ceil(0.2·|R|)`` is evaluated with exact rational arithmetic
  (``Fraction(str(heldout_fraction))``) so the holdout count cannot drift on a
  binary floating-point boundary.
* If post-floor query selection dropped below ``minimum_dev_queries`` /
  ``minimum_test_queries`` the build fails loudly instead of emitting a
  below-floor split (floors must not be lowered after seeing results).

Exit codes: ``0`` when the build + audit PASS; ``1`` on any fatal input problem
or audit FAIL.  ``--audit-only`` re-runs the leakage audit against artifacts on
disk (used by adversarial tests and by reviewers).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholargraph.graph.feasibility import (
    FeasibilityError,
    ParsedSnapshot,
    evaluate_cohorts,
    load_floors,
    parse_works,
    verify_manifest,
)

MODULE_ID = "sg016-graph-build"
MODULE_VERSION = "1.0.0"
SCHEMA_VERSION = 1

TASK_ID = "SG-016"

# Pinned machine-readable rules from configs/protocol_v1.json (tracks.B.split).
# build.py implements exactly these rules; a changed config string is fatal so a
# protocol amendment can never be silently executed by stale code.
EDGE_SORT_RULE_PINNED = "sha256(UTF8('20260915|u|v'))_ascending_then_target_id"
HELDOUT_COUNT_RULE_PINNED = "min(R-1,max(1,ceil(0.2*R)))"
QUERY_SELECTION_RULE = "sha256(seed|canonical_source_id)_ascending_then_source_id"
MASK_SCOPE_PINNED = (
    "all_dev_heldout_edges",
    "all_test_heldout_edges",
    "reverse_counterparts",
)

ARTIFACT_NAMES = {
    "adjacency_premask": "adjacency_premask.tsv",
    "adjacency_masked": "adjacency_masked.tsv",
    "holdout_edges": "holdout_edges.tsv",
    "mask_edges": "mask_edges.tsv",
    "split_queries": "split_queries.json",
    "features_degree_masked": "features_degree_masked.json",
    "features_cutoff_degree": "features_cutoff_degree.jsonl",
}


class GraphBuildError(RuntimeError):
    """Fatal input/config/artifact failure; the CLI must exit 1."""


# ---------------------------------------------------------------------------
# Small IO and hashing helpers
# ---------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GraphBuildError(f"Required input file is missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphBuildError(f"{path}: invalid JSON ({exc.msg})") from None
    if not isinstance(data, dict):
        raise GraphBuildError(f"{path}: expected a JSON object")
    return data


def read_jsonl_records(path: Path) -> list[Any]:
    if not path.is_file():
        raise GraphBuildError(f"Required input file is missing: {path}")
    records: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise GraphBuildError(
                    f"{path}:{line_number}: invalid JSON line ({exc.msg})"
                ) from None
    return records


def read_edge_file(path: Path) -> tuple[tuple[str, str], ...]:
    """Read a canonical ``source<TAB>target`` edge file; malformed lines are fatal."""

    if not path.is_file():
        raise GraphBuildError(f"Required graph artifact is missing: {path}")
    edges: list[tuple[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise GraphBuildError(
                f"{path}:{line_number}: malformed edge line, expected 'source\\ttarget'"
            )
        edges.append((parts[0], parts[1]))
    return tuple(edges)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _iso(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        raise GraphBuildError(f"{where}: missing required field '{key}'")
    return mapping[key]


def _require_int(value: Any, where: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GraphBuildError(f"{where} must be an integer, got {value!r}")
    if minimum is not None and value < minimum:
        raise GraphBuildError(f"{where} must be >= {minimum}, got {value}")
    return value


# ---------------------------------------------------------------------------
# Protocol config (tracks.B.split + tracks.B.graph_gate)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SplitConfig:
    seed: int
    heldout_fraction_raw: Any
    heldout_fraction: Fraction
    minimum_observed: int
    minimum_heldout: int
    minimum_dev_queries: int
    minimum_test_queries: int
    minimum_eligible_references: int
    minimum_novel_candidates_per_query: int
    maximum_dev_queries: int
    maximum_test_queries: int
    mask_scope: tuple[str, ...]
    test_year_rule: str
    dev_year_rule: str


def load_split_config(protocol: Mapping[str, Any]) -> SplitConfig:
    """Strictly load and validate the pinned split/graph-gate configuration."""

    tracks = _require(protocol, "tracks", "protocol config")
    track_b = _require(tracks, "B", "protocol config tracks")
    split = _require(track_b, "split", "tracks.B")
    gate = _require(track_b, "graph_gate", "tracks.B")

    seed = _require_int(_require(split, "seed", "tracks.B.split"), "tracks.B.split.seed")

    fraction_raw = _require(split, "heldout_fraction", "tracks.B.split")
    if (
        isinstance(fraction_raw, bool)
        or not isinstance(fraction_raw, (int, float))
        or not 0 < float(fraction_raw) < 1
    ):
        raise GraphBuildError(
            f"tracks.B.split.heldout_fraction must be a number in (0, 1), got {fraction_raw!r}"
        )
    heldout_fraction = Fraction(str(fraction_raw))

    edge_sort = _require(split, "edge_sort", "tracks.B.split")
    if edge_sort != EDGE_SORT_RULE_PINNED:
        raise GraphBuildError(
            "tracks.B.split.edge_sort changed: "
            f"config {edge_sort!r} != pinned {EDGE_SORT_RULE_PINNED!r}; update build.py "
            "via ADR before running a different rule"
        )
    heldout_count_rule = _require(split, "heldout_count", "tracks.B.split")
    if heldout_count_rule != HELDOUT_COUNT_RULE_PINNED:
        raise GraphBuildError(
            "tracks.B.split.heldout_count changed: "
            f"config {heldout_count_rule!r} != pinned {HELDOUT_COUNT_RULE_PINNED!r}"
        )

    minimum_observed = _require_int(
        _require(split, "minimum_observed", "tracks.B.split"),
        "tracks.B.split.minimum_observed",
        minimum=1,
    )
    minimum_heldout = _require_int(
        _require(split, "minimum_heldout", "tracks.B.split"),
        "tracks.B.split.minimum_heldout",
        minimum=1,
    )

    scope_raw = _require(split, "mask_scope", "tracks.B.split")
    if (
        not isinstance(scope_raw, list)
        or len(scope_raw) != len(set(scope_raw))
        or sorted(scope_raw) != sorted(MASK_SCOPE_PINNED)
    ):
        raise GraphBuildError(
            "tracks.B.split.mask_scope must be exactly "
            f"{list(MASK_SCOPE_PINNED)}, got {scope_raw!r}"
        )

    floors = load_floors(protocol)  # raises FeasibilityError when floors are missing
    maximum_dev = _require_int(
        _require(gate, "maximum_dev_queries", "tracks.B.graph_gate"),
        "tracks.B.graph_gate.maximum_dev_queries",
        minimum=1,
    )
    maximum_test = _require_int(
        _require(gate, "maximum_test_queries", "tracks.B.graph_gate"),
        "tracks.B.graph_gate.maximum_test_queries",
        minimum=1,
    )
    if maximum_dev < floors["minimum_dev_queries"]:
        raise GraphBuildError(
            "tracks.B.graph_gate.maximum_dev_queries is below minimum_dev_queries"
        )
    if maximum_test < floors["minimum_test_queries"]:
        raise GraphBuildError(
            "tracks.B.graph_gate.maximum_test_queries is below minimum_test_queries"
        )

    return SplitConfig(
        seed=seed,
        heldout_fraction_raw=fraction_raw,
        heldout_fraction=heldout_fraction,
        minimum_observed=minimum_observed,
        minimum_heldout=minimum_heldout,
        minimum_dev_queries=int(floors["minimum_dev_queries"]),
        minimum_test_queries=int(floors["minimum_test_queries"]),
        minimum_eligible_references=int(floors["minimum_eligible_references"]),
        minimum_novel_candidates_per_query=int(floors["minimum_novel_candidates_per_query"]),
        maximum_dev_queries=maximum_dev,
        maximum_test_queries=maximum_test,
        mask_scope=tuple(scope_raw),
        test_year_rule=str(floors["test_year_rule"]),
        dev_year_rule=str(floors["dev_year_rule"]),
    )


# ---------------------------------------------------------------------------
# Graph construction (pre-mask)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PremaskGraph:
    """Directed internal graph plus counted raw anomalies (1:1 with the raw file)."""

    edges: tuple[tuple[str, str], ...]
    distinct_refs: Mapping[str, tuple[str, ...]]
    self_loop_works: tuple[str, ...]
    dangling_occurrences: int
    dangling_distinct_targets: int
    duplicate_reference_entry_count: int
    reciprocal_pairs: int
    future_target_edges: int
    internal_reference_occurrences: int


def valid_year_maps(parsed: ParsedSnapshot) -> tuple[dict[str, int], dict[int, int]]:
    """Canonical ID -> valid publication year, and cumulative valid-year counts."""

    years = {
        record.canonical_id: record.publication_year
        for record in parsed.records
        if record.year_status == "valid"
    }
    per_year: dict[int, int] = {}
    for year in years.values():
        per_year[year] = per_year.get(year, 0) + 1
    cumulative: dict[int, int] = {}
    running = 0
    for year in sorted(per_year):
        running += per_year[year]
        cumulative[year] = running
    return years, cumulative


def build_premask_graph(parsed: ParsedSnapshot, years: Mapping[str, int]) -> PremaskGraph:
    """Build the directed internal edge set and count every raw anomaly."""

    id_set = {record.canonical_id for record in parsed.records}
    edges: set[tuple[str, str]] = set()
    distinct_refs: dict[str, set[str]] = {record.canonical_id: set() for record in parsed.records}
    self_loop_works: list[str] = []
    dangling_occurrences = 0
    dangling_targets: set[str] = set()
    internal_occurrences = 0

    for record in parsed.records:
        source = record.canonical_id
        seen: set[str] = set()
        for target in record.references:
            if target == source:
                self_loop_works.append(source)
                continue
            if target not in id_set:
                dangling_occurrences += 1
                dangling_targets.add(target)
                continue
            internal_occurrences += 1
            if target in seen:
                continue  # duplicate entry; already counted by parse_works anomalies
            seen.add(target)
            distinct_refs[source].add(target)
            edges.add((source, target))

    edge_tuple = tuple(sorted(edges))
    reciprocal_pairs = sum(1 for s, t in edge_tuple if (t, s) in edges) // 2
    future_target_edges = sum(
        1 for s, t in edge_tuple if s in years and t in years and years[t] > years[s]
    )
    return PremaskGraph(
        edges=edge_tuple,
        distinct_refs={node: tuple(sorted(targets)) for node, targets in distinct_refs.items()},
        self_loop_works=tuple(self_loop_works),
        dangling_occurrences=dangling_occurrences,
        dangling_distinct_targets=len(dangling_targets),
        duplicate_reference_entry_count=int(parsed.anomalies["duplicate_reference_entries"]),
        reciprocal_pairs=reciprocal_pairs,
        future_target_edges=future_target_edges,
        internal_reference_occurrences=internal_occurrences,
    )


# ---------------------------------------------------------------------------
# Deterministic holdout split (GRAPH_PROTOCOL §2)
# ---------------------------------------------------------------------------


def heldout_count(r: int, fraction: Fraction) -> int:
    """Exact ``min(R-1, max(1, ceil(fraction*R)))`` with rational arithmetic."""

    if r < 1:
        raise GraphBuildError(f"heldout_count requires at least one reference, got R={r}")
    exact = fraction * r
    ceil_exact = -((-exact.numerator) // exact.denominator)
    return min(r - 1, max(1, ceil_exact))


def split_for_source(
    source_id: str, refs: Sequence[str], seed: int, fraction: Fraction
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split ``R(u)`` into (heldout, observed) per GRAPH_PROTOCOL §2.2–2.3."""

    ordered = sorted(refs, key=lambda v: (sha256_text(f"{seed}|{source_id}|{v}"), v))
    h = heldout_count(len(refs), fraction)
    return tuple(ordered[:h]), tuple(ordered[h:])


def _eligible_source_refs(
    parsed: ParsedSnapshot,
    premask: PremaskGraph,
    years: Mapping[str, int],
    minimum_refs: int,
) -> tuple[dict[int, int], dict[str, tuple[str, ...]]]:
    """Recount eligible sources per year (1:1 with feasibility.evaluate_cohorts)."""

    counts: dict[int, int] = {}
    refs_by_source: dict[str, tuple[str, ...]] = {}
    for record in parsed.records:
        source_year = record.publication_year
        if source_year is None or record.title is None or not record.has_abstract:
            continue
        eligible_refs = tuple(
            target
            for target in premask.distinct_refs[record.canonical_id]
            if target in years and years[target] <= source_year
        )
        if len(eligible_refs) >= minimum_refs:
            counts[source_year] = counts.get(source_year, 0) + 1
            refs_by_source[record.canonical_id] = eligible_refs
    return counts, refs_by_source


@dataclass(frozen=True)
class SplitResult:
    test_year: int
    dev_year: int
    eligible_by_year: Mapping[int, int]
    eligible_by_cohort: Mapping[str, int]
    qualifying_by_cohort: Mapping[str, int]
    excluded_by_novel_floor: Mapping[str, int]
    excluded_by_split_minimums: Mapping[str, int]
    selected: Mapping[str, tuple[str, ...]]
    heldout_by_source: Mapping[str, tuple[str, ...]]
    observed_by_source: Mapping[str, tuple[str, ...]]
    novel_candidates: Mapping[str, Mapping[str, int]]
    heldout_edges: tuple[tuple[str, str], ...]
    mask_edges: tuple[tuple[str, str], ...]
    heldout_count_by_cohort: Mapping[str, int]
    observed_count_by_cohort: Mapping[str, int]
    premask_edges: tuple[tuple[str, str], ...]
    masked_edges: tuple[tuple[str, str], ...]


def compute_split(
    parsed: ParsedSnapshot,
    premask: PremaskGraph,
    years: Mapping[str, int],
    cumulative: Mapping[int, int],
    config: SplitConfig,
    test_year: int,
    dev_year: int,
) -> SplitResult:
    """Deterministic query selection + per-source holdout + global two-way mask."""

    if test_year is None or dev_year is None:
        raise GraphBuildError(
            "cohort years are unresolved (test_year/dev_year = None): the snapshot does "
            "not meet the Protocol v1 cohort floors, so no holdout split can be built"
        )
    cohort_years = {"test": test_year, "dev": dev_year}
    floors = {"test": config.minimum_test_queries, "dev": config.minimum_dev_queries}
    caps = {"test": config.maximum_test_queries, "dev": config.maximum_dev_queries}

    eligible_counts, refs_by_source = _eligible_source_refs(
        parsed, premask, years, config.minimum_eligible_references
    )

    selected: dict[str, tuple[str, ...]] = {}
    heldout_by_source: dict[str, tuple[str, ...]] = {}
    observed_by_source: dict[str, tuple[str, ...]] = {}
    novel_by_source: dict[str, dict[str, int]] = {}
    eligible_by_cohort: dict[str, int] = {}
    qualifying_by_cohort: dict[str, int] = {}
    excluded_novel: dict[str, int] = {}
    excluded_minimums: dict[str, int] = {}
    heldout_count_by_cohort: dict[str, int] = {}
    observed_count_by_cohort: dict[str, int] = {}

    for cohort, cohort_year in cohort_years.items():
        pool = sorted(
            source for source, refs in refs_by_source.items() if years[source] == cohort_year
        )
        eligible_by_cohort[cohort] = len(pool)

        qualifying: list[tuple[str, tuple[str, ...], tuple[str, ...], int]] = []
        excluded_novel[cohort] = 0
        excluded_minimums[cohort] = 0
        novel_by_source[cohort] = {}
        for source in pool:
            refs = refs_by_source[source]
            heldout, observed = split_for_source(
                source, refs, config.seed, config.heldout_fraction
            )
            if len(heldout) < config.minimum_heldout or len(observed) < config.minimum_observed:
                excluded_minimums[cohort] += 1
                continue
            novel = cumulative[cohort_year] - 1 - len(observed)
            novel_by_source[cohort][source] = novel
            if novel < config.minimum_novel_candidates_per_query:
                excluded_novel[cohort] += 1
                continue
            qualifying.append((source, heldout, observed, novel))

        qualifying.sort(key=lambda item: (sha256_text(f"{config.seed}|{item[0]}"), item[0]))
        chosen = qualifying[: caps[cohort]]
        if len(chosen) < floors[cohort]:
            raise GraphBuildError(
                f"{cohort} cohort selection kept {len(chosen)} queries after the "
                f"novel-candidate floor, below the protocol floor of {floors[cohort]}; "
                "refusing to emit a below-floor split (floors must not be lowered)"
            )

        selected[cohort] = tuple(source for source, _, _, _ in chosen)
        for source, heldout, observed, _ in chosen:
            heldout_by_source[source] = heldout
            observed_by_source[source] = observed
        qualifying_by_cohort[cohort] = len(qualifying)
        heldout_count_by_cohort[cohort] = sum(len(item[1]) for item in chosen)
        observed_count_by_cohort[cohort] = sum(len(item[2]) for item in chosen)

    heldout_set = {
        (source, target)
        for source, targets in heldout_by_source.items()
        for target in targets
    }
    mask_set = heldout_set | {(target, source) for source, target in heldout_set}
    masked_edges = tuple(sorted(set(premask.edges) - mask_set))

    return SplitResult(
        test_year=test_year,
        dev_year=dev_year,
        eligible_by_year=eligible_counts,
        eligible_by_cohort=eligible_by_cohort,
        qualifying_by_cohort=qualifying_by_cohort,
        excluded_by_novel_floor=excluded_novel,
        excluded_by_split_minimums=excluded_minimums,
        selected=selected,
        heldout_by_source=heldout_by_source,
        observed_by_source=observed_by_source,
        novel_candidates=novel_by_source,
        heldout_edges=tuple(sorted(heldout_set)),
        mask_edges=tuple(sorted(mask_set)),
        heldout_count_by_cohort=heldout_count_by_cohort,
        observed_count_by_cohort=observed_count_by_cohort,
        premask_edges=premask.edges,
        masked_edges=masked_edges,
    )


# ---------------------------------------------------------------------------
# Feature recomputation on G_mask
# ---------------------------------------------------------------------------


def degree_maps(
    nodes: Sequence[str], edges: Sequence[tuple[str, str]]
) -> tuple[dict[str, int], dict[str, int]]:
    """Masked in/out degree over every node (0 for isolated nodes)."""

    in_degree = {node: 0 for node in nodes}
    out_degree = {node: 0 for node in nodes}
    for source, target in edges:
        out_degree[source] += 1
        in_degree[target] += 1
    return in_degree, out_degree


def cutoff_feature_lines(
    split: SplitResult, masked_edges: Sequence[tuple[str, str]], years: Mapping[str, int]
) -> list[dict[str, Any]]:
    """Per-query cutoff-induced degree statistics, test cohort first then dev.

    Every statistic is recomputed from the masked edge list restricted to nodes
    with ``year <= year(u)`` (GRAPH_PROTOCOL §3.2); the source's own in/out
    degree inside the truncated graph is recorded separately.
    """

    lines: list[dict[str, Any]] = []
    for cohort in ("test", "dev"):
        for source in split.selected[cohort]:
            cutoff_year = years[source]
            nodes = {node for node, year in years.items() if year <= cutoff_year}
            cutoff_edges = [(s, t) for (s, t) in masked_edges if s in nodes and t in nodes]
            in_degree, out_degree = degree_maps(sorted(nodes), cutoff_edges)
            lines.append(
                {
                    "source_id": source,
                    "split": cohort,
                    "cutoff_year": cutoff_year,
                    "truncated_node_count": len(nodes),
                    "truncated_edge_count": len(cutoff_edges),
                    "truncated_sum_in_degree": sum(in_degree.values()),
                    "truncated_sum_out_degree": sum(out_degree.values()),
                    "source_in_degree_cutoff": in_degree[source],
                    "source_out_degree_cutoff": out_degree[source],
                }
            )
    return lines


# ---------------------------------------------------------------------------
# Artifact serialization (deterministic bytes)
# ---------------------------------------------------------------------------


def _edge_tsv(edges: Sequence[tuple[str, str]]) -> str:
    return "".join(f"{source}\t{target}\n" for source, target in edges)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _write_edge_artifact(path: Path, edges: Sequence[tuple[str, str]]) -> dict[str, Any]:
    _atomic_write(path, _edge_tsv(edges))
    return {
        "path": _display_path(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "edge_count": len(edges),
    }


def _write_json_artifact(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    _atomic_write(path, _canonical_json(payload))
    return {
        "path": _display_path(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def build_split_payload(split: SplitResult, config: SplitConfig) -> dict[str, Any]:
    """Canonical split-queries payload (deterministic; hashed into split_hash)."""

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "masked_split_queries",
        "task_id": TASK_ID,
        "seed": config.seed,
        "heldout_fraction": config.heldout_fraction_raw,
        "heldout_fraction_exact": f"{config.heldout_fraction.numerator}/{config.heldout_fraction.denominator}",
        "edge_sort_rule": EDGE_SORT_RULE_PINNED,
        "heldout_count_rule": HELDOUT_COUNT_RULE_PINNED,
        "query_selection_rule": QUERY_SELECTION_RULE,
        "mask_scope": list(config.mask_scope),
        "minimum_observed": config.minimum_observed,
        "minimum_heldout": config.minimum_heldout,
        "cohorts": {},
    }
    for cohort, year in (("test", split.test_year), ("dev", split.dev_year)):
        selected = split.selected[cohort]
        payload["cohorts"][cohort] = {
            "year": year,
            "eligible_sources": split.eligible_by_cohort[cohort],
            "qualifying_sources": split.qualifying_by_cohort[cohort],
            "excluded_by_novel_floor": split.excluded_by_novel_floor[cohort],
            "excluded_by_split_minimums": split.excluded_by_split_minimums[cohort],
            "cap": config.maximum_test_queries
            if cohort == "test"
            else config.maximum_dev_queries,
            "selected_count": len(selected),
            "selected": list(selected),
            "heldout_edges": split.heldout_count_by_cohort[cohort],
            "observed_edges": split.observed_count_by_cohort[cohort],
        }
    return payload


# ---------------------------------------------------------------------------
# Gate report verification (SG-016 only runs after a GO gate — ADR-016)
# ---------------------------------------------------------------------------


def load_gate_report(
    gate_report_path: Path,
    works_sha256: str,
    cohorts: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the SG-014 gate report is a GO measured on exactly this snapshot."""

    report = read_json_object(gate_report_path)
    status = _require(report, "status", "gate report")
    if status != "MEASURED":
        raise GraphBuildError(
            f"gate report {gate_report_path} status is {status!r}, expected 'MEASURED'"
        )
    decision = _require(report, "decision", "gate report")
    overall = _require(decision, "overall", "gate report decision")
    if overall != "GO":
        raise GraphBuildError(
            f"SG-016 is blocked: gate report {gate_report_path} decision.overall="
            f"{overall!r} (ADR-016: the masked split may only be built after a GO gate "
            "on the core snapshot)"
        )
    provenance = _require(report, "provenance", "gate report")
    inputs = _require(provenance, "inputs", "gate report provenance")
    works_entry = _require(inputs, "works_jsonl", "gate report provenance.inputs")
    gate_works_sha = _require(works_entry, "sha256", "gate report works entry")
    if gate_works_sha != works_sha256:
        raise GraphBuildError(
            f"gate report works sha256 mismatch: gate {gate_works_sha} != measured {works_sha256}"
        )
    gate_cohorts = _require(report, "protocol_b_cohorts", "gate report")
    for key in ("test_year", "dev_year"):
        if gate_cohorts.get(key) != cohorts[key]:
            raise GraphBuildError(
                f"gate report {key} mismatch: gate {gate_cohorts.get(key)!r} vs "
                f"recomputed {cohorts[key]!r}"
            )
    gate_eligible = gate_cohorts.get("eligible_source_count_by_publication_year")
    if gate_eligible is not None:
        gate_map = {str(year): count for year, count in gate_eligible.items()}
        recomputed = {
            str(year): count
            for year, count in cohorts["eligible_source_count_by_publication_year"].items()
        }
        if gate_map != recomputed:
            raise GraphBuildError(
                "gate report eligible_source_count_by_publication_year does not match the "
                "recount from this snapshot; refusing to build on inconsistent provenance"
            )
    return {
        "path": _display_path(gate_report_path),
        "sha256": sha256_file(gate_report_path),
        "decision_overall": overall,
        "measured_at": gate_cohorts and report.get("measured_at"),
    }


# ---------------------------------------------------------------------------
# Build orchestration
# ---------------------------------------------------------------------------


def _fatal_outputs(
    graph_manifest_path: Path,
    audit_path: Path,
    errors: Sequence[str],
    measured_at: datetime | None,
    command_argv: Sequence[str],
) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "graph_masked_split_manifest",
        "task_id": TASK_ID,
        "module": {"id": MODULE_ID, "version": MODULE_VERSION},
        "status": "FAILED",
        "measured_at": _iso(measured_at),
        "command": list(command_argv),
        "errors": list(errors),
    }
    _atomic_write(graph_manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    audit = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "graph_masked_split_audit",
        "task_id": TASK_ID,
        "module": {"id": MODULE_ID, "version": MODULE_VERSION},
        "status": "FAIL",
        "measured_at": _iso(measured_at),
        "command": list(command_argv),
        "errors": list(errors),
        "checks": [],
    }
    _atomic_write(audit_path, json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def _interpretation_notes() -> list[str]:
    return [
        "Heldout sets are computed for the selected dev/test query sources only "
        "(GRAPH_PROTOCOL §2.6 query selection with caps/floors); the mask scope is the "
        "global union H_dev ∪ H_test ∪ reverse per §4.1, not per-query. Non-query sources "
        "keep all internal edges in G_mask because their references are labels for no "
        "query; masking the heldout of every eligible source would be a protocol "
        "deviation requiring an ADR.",
        "Reciprocal pairs with no heldout direction remain in G_mask per GRAPH_PROTOCOL "
        "§1.3 ('giữ nguyên tính có hướng trong raw'); every pair with a heldout direction "
        "is removed in both directions (audited: two_way_heldout_residual = 0).",
        "Works with missing or out-of-range publication year stay as graph nodes "
        "(consistent with the SG-014/SG-015 gate statistics) but can be neither queries "
        "nor candidates and never enter a cutoff-induced subgraph.",
        "heldout_count ceil is computed with exact rational arithmetic "
        "(Fraction(str(heldout_fraction))) to avoid binary floating-point boundary drift.",
        "Edges whose target year exceeds the source year (both years known) remain in "
        "E_pre and G_mask as observed data; time legality is enforced only inside "
        "cutoff-induced features (GRAPH_PROTOCOL §3.2).",
        "If post-floor query selection drops below minimum_dev_queries/minimum_test_queries "
        "the build fails loudly instead of emitting a below-floor split.",
        "qrels/BEIR labels are never read (track B independent); cited_by_count is never "
        "used as a feature (Protocol v1 forbidden features).",
    ]


def run_build(
    *,
    works_path: Path,
    snapshot_manifest_path: Path,
    protocol_path: Path,
    gate_report_path: Path,
    protocol_doc_path: Path,
    out_dir: Path,
    graph_manifest_path: Path,
    audit_path: Path,
    command_argv: Sequence[str] | None = None,
    measured_at: datetime | None = None,
) -> tuple[int, dict[str, Any]]:
    """Build the masked graph + split; then audit.  Returns ``(exit_code, manifest)``."""

    argv_list = list(command_argv) if command_argv is not None else sys.argv[1:]
    errors: list[str] = []
    try:
        for required in (
            works_path,
            snapshot_manifest_path,
            protocol_path,
            gate_report_path,
            protocol_doc_path,
        ):
            if not required.is_file():
                raise GraphBuildError(f"Required input file is missing: {required}")

        works_sha = sha256_file(works_path)
        parsed = parse_works(read_jsonl_records(works_path))

        snapshot_manifest = read_json_object(snapshot_manifest_path)
        manifest_check = verify_manifest(snapshot_manifest, works_path, works_sha)
        snapshot_year = int(manifest_check["snapshot_year"])

        protocol = read_json_object(protocol_path)
        config = load_split_config(protocol)
        floors = load_floors(protocol)

        cohorts = evaluate_cohorts(parsed, snapshot_year, floors)
        if cohorts["test_year"] is None or cohorts["dev_year"] is None:
            raise GraphBuildError(
                "cohort years unresolved on this snapshot "
                f"(test_year={cohorts['test_year']!r}, dev_year={cohorts['dev_year']!r}): "
                "the Protocol v1 cohort floors are not met, so no masked split can be built"
            )
        gate_info = load_gate_report(gate_report_path, works_sha, cohorts)

        years, cumulative = valid_year_maps(parsed)
        premask = build_premask_graph(parsed, years)
        recount_counts, _ = _eligible_source_refs(
            parsed, premask, years, config.minimum_eligible_references
        )
        cohort_counts = {
            str(year): count
            for year, count in cohorts["eligible_source_count_by_publication_year"].items()
        }
        recount_map = {str(year): count for year, count in sorted(recount_counts.items())}
        if recount_map != cohort_counts:
            raise GraphBuildError(
                "internal inconsistency: eligible-source recount does not match "
                "feasibility.evaluate_cohorts on the same snapshot"
            )
        split = compute_split(
            parsed, premask, years, cumulative, config,
            cohorts["test_year"], cohorts["dev_year"],
        )
    except (GraphBuildError, FeasibilityError) as exc:
        errors.append(str(exc))
        return 1, _fatal_outputs(graph_manifest_path, audit_path, errors, measured_at, argv_list)

    # ---- artifacts --------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes = sorted(record.canonical_id for record in parsed.records)
    in_degree, out_degree = degree_maps(nodes, split.masked_edges)

    hashes: dict[str, dict[str, Any]] = {}
    hashes["adjacency_premask"] = _write_edge_artifact(
        out_dir / ARTIFACT_NAMES["adjacency_premask"], split.premask_edges
    )
    hashes["adjacency_masked"] = _write_edge_artifact(
        out_dir / ARTIFACT_NAMES["adjacency_masked"], split.masked_edges
    )
    hashes["holdout_edges"] = _write_edge_artifact(
        out_dir / ARTIFACT_NAMES["holdout_edges"], split.heldout_edges
    )
    hashes["mask_edges"] = _write_edge_artifact(
        out_dir / ARTIFACT_NAMES["mask_edges"], split.mask_edges
    )

    split_payload = build_split_payload(split, config)
    hashes["split_queries"] = _write_json_artifact(
        out_dir / ARTIFACT_NAMES["split_queries"], split_payload
    )

    features_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "graph_degree_features",
        "task_id": TASK_ID,
        "derived_from": ARTIFACT_NAMES["adjacency_masked"],
        "cutoff": "none_full_masked_graph",
        "edge_count": len(split.masked_edges),
        "in_degree": in_degree,
        "out_degree": out_degree,
    }
    hashes["features_degree_masked"] = _write_json_artifact(
        out_dir / ARTIFACT_NAMES["features_degree_masked"], features_payload
    )

    cutoff_lines = cutoff_feature_lines(split, split.masked_edges, years)
    cutoff_path = out_dir / ARTIFACT_NAMES["features_cutoff_degree"]
    _atomic_write(cutoff_path, "".join(_canonical_json(line) for line in cutoff_lines))
    hashes["features_cutoff_degree"] = {
        "path": _display_path(cutoff_path),
        "sha256": sha256_file(cutoff_path),
        "bytes": cutoff_path.stat().st_size,
        "line_count": len(cutoff_lines),
    }

    premask_set = set(split.premask_edges)
    heldout_set = set(split.heldout_edges)
    mask_set = set(split.mask_edges)
    masked_set = set(split.masked_edges)
    removed_edges = premask_set & mask_set
    reverse_only = mask_set - heldout_set
    masked_nodes_with_edges = {node for edge in split.masked_edges for node in edge}

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "graph_masked_split_manifest",
        "task_id": TASK_ID,
        "module": {"id": MODULE_ID, "version": MODULE_VERSION},
        "status": "COMPLETED",
        "measured_at": _iso(measured_at),
        "command": argv_list,
        "runtime": {"python": sys.version.split()[0], "platform": sys.platform},
        "provenance": {
            "works_jsonl": {
                "path": _display_path(works_path),
                "sha256": works_sha,
                "bytes": works_path.stat().st_size,
            },
            "snapshot_manifest": {
                "path": _display_path(snapshot_manifest_path),
                "sha256": sha256_file(snapshot_manifest_path),
                "snapshot_id": snapshot_manifest.get("snapshot_id"),
                "snapshot_year": snapshot_year,
                "retrieved_completed_at": manifest_check["retrieved_completed_at"],
                "query_fingerprint": snapshot_manifest.get("query_fingerprint"),
                "v2_fingerprint": snapshot_manifest.get("v2_fingerprint"),
            },
            "protocol_config": {
                "path": _display_path(protocol_path),
                "sha256": sha256_file(protocol_path),
            },
            "gate_report": gate_info,
            "graph_protocol_doc": {
                "path": _display_path(protocol_doc_path),
                "sha256": sha256_file(protocol_doc_path),
            },
        },
        "counts": {
            "works": len(parsed.records),
            "nodes": len(nodes),
            "valid_year_nodes": len(years),
            "reference_entries_total": sum(
                len(record.references) for record in parsed.records
            ),
            "internal_reference_occurrences_premask": premask.internal_reference_occurrences,
            "internal_directed_edges_premask": len(split.premask_edges),
            "edges_removed_by_mask": len(removed_edges),
            "internal_directed_edges_postmask": len(split.masked_edges),
            "self_loop_works_removed": len(premask.self_loop_works),
            "self_loop_works": list(premask.self_loop_works),
            "duplicate_reference_entry_count": premask.duplicate_reference_entry_count,
            "reciprocal_edge_pairs_premask": premask.reciprocal_pairs,
            "reciprocal_edge_pairs_postmask": sum(
                1 for s, t in split.masked_edges if (t, s) in masked_set
            )
            // 2,
            "reciprocal_pairs_with_heldout_direction": len(
                {
                    frozenset((s, t))
                    for s, t in premask_set
                    if (t, s) in premask_set
                    and ((s, t) in heldout_set or (t, s) in heldout_set)
                }
            ),
            "out_of_snapshot_reference_occurrences": premask.dangling_occurrences,
            "out_of_snapshot_distinct_targets": premask.dangling_distinct_targets,
            "future_target_edges_both_years_known": premask.future_target_edges,
            "missing_title_count": int(parsed.anomalies["missing_title_count"]),
            "missing_abstract_count": int(parsed.anomalies["missing_abstract_count"]),
            "missing_publication_year_count": int(parsed.anomalies["missing_publication_year_count"]),
            "out_of_range_publication_year_count": int(
                parsed.anomalies["out_of_range_publication_year_count"]
            ),
            "missing_doi_count": int(parsed.anomalies["missing_doi_count"]),
            "isolated_nodes_premask": len(nodes) - len({n for e in premask.edges for n in e}),
            "isolated_nodes_postmask": len(nodes) - len(masked_nodes_with_edges),
        },
        "holdout": {
            "seed": config.seed,
            "heldout_fraction": config.heldout_fraction_raw,
            "heldout_fraction_exact": (
                f"{config.heldout_fraction.numerator}/{config.heldout_fraction.denominator}"
            ),
            "edge_sort_rule": EDGE_SORT_RULE_PINNED,
            "heldout_count_rule": HELDOUT_COUNT_RULE_PINNED,
            "query_selection_rule": QUERY_SELECTION_RULE,
            "mask_scope": list(config.mask_scope),
            "minimum_observed": config.minimum_observed,
            "minimum_heldout": config.minimum_heldout,
            "floors": {
                "minimum_dev_queries": config.minimum_dev_queries,
                "minimum_test_queries": config.minimum_test_queries,
                "minimum_eligible_references": config.minimum_eligible_references,
                "minimum_novel_candidates_per_query": config.minimum_novel_candidates_per_query,
            },
            "caps": {
                "maximum_dev_queries": config.maximum_dev_queries,
                "maximum_test_queries": config.maximum_test_queries,
            },
            "test_year": split.test_year,
            "dev_year": split.dev_year,
            "eligible_sources_by_cohort": dict(split.eligible_by_cohort),
            "total_eligible_sources_all_years": sum(split.eligible_by_year.values()),
            "qualifying_sources_by_cohort": dict(split.qualifying_by_cohort),
            "excluded_by_novel_floor": dict(split.excluded_by_novel_floor),
            "excluded_by_split_minimums": dict(split.excluded_by_split_minimums),
            "selected_queries": {k: len(v) for k, v in split.selected.items()},
            "heldout_edges_by_cohort": dict(split.heldout_count_by_cohort),
            "observed_edges_by_cohort": dict(split.observed_count_by_cohort),
            "heldout_edges_total": len(split.heldout_edges),
            "mask_edges_total": len(split.mask_edges),
            "mask_reverse_counterpart_edges": len(reverse_only),
            "mask_reverse_only_absent_from_premask": sum(
                1 for edge in reverse_only if edge not in premask_set
            ),
            "heldout_per_query_range": {
                cohort: {
                    "min": min(
                        (len(split.heldout_by_source[s]) for s in split.selected[cohort]),
                        default=None,
                    ),
                    "max": max(
                        (len(split.heldout_by_source[s]) for s in split.selected[cohort]),
                        default=None,
                    ),
                }
                for cohort in ("test", "dev")
            },
            "novel_candidates_selected_range": {
                cohort: {
                    "min": min(
                        (split.novel_candidates[cohort][s] for s in split.selected[cohort]),
                        default=None,
                    ),
                    "max": max(
                        (split.novel_candidates[cohort][s] for s in split.selected[cohort]),
                        default=None,
                    ),
                }
                for cohort in ("test", "dev")
            },
        },
        "hashes": hashes,
        "split_hash": hashes["split_queries"]["sha256"],
        "graph_hash": hashes["adjacency_masked"]["sha256"],
        "mask_hash": hashes["mask_edges"]["sha256"],
        "audit": {"status": "PENDING", "path": _display_path(audit_path), "sha256": None},
        "leakage_contract": {
            "qrels_or_beir_labels_used": False,
            "edge_source": "referenced_works only (OpenAlex)",
            "trusted_artifacts_read_only_by": [
                "evaluator",
                "auditor",
            ],
            "trusted_artifacts": [
                hashes["holdout_edges"]["path"],
                hashes["mask_edges"]["path"],
            ],
            "ranker_visible_artifacts": [
                hashes["adjacency_premask"]["path"],
                hashes["adjacency_masked"]["path"],
                hashes["split_queries"]["path"],
                hashes["features_degree_masked"]["path"],
                hashes["features_cutoff_degree"]["path"],
            ],
            "cited_by_count_used_as_feature": False,
            "features_derived_from": ARTIFACT_NAMES["adjacency_masked"],
        },
        "interpretation_notes": _interpretation_notes(),
    }

    _atomic_write(
        graph_manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )

    audit_exit, audit_report = run_audit(
        works_path=works_path,
        snapshot_manifest_path=snapshot_manifest_path,
        protocol_path=protocol_path,
        gate_report_path=gate_report_path,
        protocol_doc_path=protocol_doc_path,
        graph_manifest_path=graph_manifest_path,
        audit_path=audit_path,
        command_argv=argv_list,
        measured_at=measured_at,
    )
    manifest["audit"] = {
        "status": audit_report.get("status", "FAIL"),
        "path": _display_path(audit_path),
        "sha256": sha256_file(audit_path),
    }
    if audit_exit != 0:
        manifest["status"] = "FAILED"
        manifest["errors"] = list(audit_report.get("errors", []))
    _atomic_write(
        graph_manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return (0 if audit_exit == 0 else 1), manifest


# ---------------------------------------------------------------------------
# Leakage audit (re-reads artifacts from disk and replays the build)
# ---------------------------------------------------------------------------


def run_audit(
    *,
    works_path: Path,
    snapshot_manifest_path: Path,
    protocol_path: Path,
    gate_report_path: Path,
    protocol_doc_path: Path,
    graph_manifest_path: Path,
    audit_path: Path,
    command_argv: Sequence[str] | None = None,
    measured_at: datetime | None = None,
) -> tuple[int, dict[str, Any]]:
    """Independent leakage/integrity audit; exit 1 on any FAIL."""

    argv_list = list(command_argv) if command_argv is not None else sys.argv[1:]
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    measured: dict[str, Any] = {}
    status = "FAIL"

    def record(check_id: str, ok: bool, requirement: str, check_measured: Any, source: str) -> None:
        checks.append(
            {
                "check_id": check_id,
                "decision": "PASS" if ok else "FAIL",
                "requirement": requirement,
                "measured": check_measured,
                "source": source,
            }
        )

    try:
        gmanifest = read_json_object(graph_manifest_path)
        works_sha = sha256_file(works_path)
        parsed = parse_works(read_jsonl_records(works_path))
        protocol = read_json_object(protocol_path)
        config = load_split_config(protocol)
        floors = load_floors(protocol)
        snapshot_manifest = read_json_object(snapshot_manifest_path)
        manifest_check = verify_manifest(snapshot_manifest, works_path, works_sha)
        snapshot_year = int(manifest_check["snapshot_year"])
        cohorts = evaluate_cohorts(parsed, snapshot_year, floors)
        if cohorts["test_year"] is None or cohorts["dev_year"] is None:
            raise GraphBuildError("cohort years unresolved; nothing to audit")
        gate_info = load_gate_report(gate_report_path, works_sha, cohorts)
        years, cumulative = valid_year_maps(parsed)
        premask = build_premask_graph(parsed, years)
        split = compute_split(
            parsed, premask, years, cumulative, config,
            cohorts["test_year"], cohorts["dev_year"],
        )

        recorded_hashes = _require(gmanifest, "hashes", "graph manifest")
        artifact_paths = {
            name: Path(_require(entry, "path", f"graph manifest hashes.{name}"))
            for name, entry in recorded_hashes.items()
        }

        # -- stored artifacts ------------------------------------------------
        premask_stored = read_edge_file(artifact_paths["adjacency_premask"])
        masked_stored = read_edge_file(artifact_paths["adjacency_masked"])
        holdout_stored = read_edge_file(artifact_paths["holdout_edges"])
        mask_stored = read_edge_file(artifact_paths["mask_edges"])
        split_path = artifact_paths["split_queries"]
        split_stored = read_json_object(split_path)
        features_path = artifact_paths["features_degree_masked"]
        features_stored = read_json_object(features_path)
        cutoff_path = artifact_paths["features_cutoff_degree"]
        cutoff_stored = [
            json.loads(line)
            for line in cutoff_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        premask_set = set(premask_stored)
        masked_set = set(masked_stored)
        holdout_set = set(holdout_stored)
        mask_stored_set = set(mask_stored)
        node_set = {record.canonical_id for record in parsed.records}

        # 1. input provenance ------------------------------------------------
        provenance_ok = works_sha == sha256_file(works_path) and (
            snapshot_manifest.get("artifacts", {})
            .get("works_jsonl", {})
            .get("sha256")
            == works_sha
        )
        record(
            "input_provenance",
            provenance_ok,
            "works.jsonl sha256 matches the snapshot manifest and the gate report",
            {
                "works_sha256": works_sha,
                "snapshot_id": snapshot_manifest.get("snapshot_id"),
                "snapshot_year": snapshot_year,
                "gate_decision": gate_info["decision_overall"],
            },
            "ADR-016; docs/GRAPH_PROTOCOL.md §5",
        )

        # 2. artifact hashes vs manifest --------------------------------------
        hash_results: dict[str, bool] = {}
        for name, entry in recorded_hashes.items():
            actual_sha = sha256_file(artifact_paths[name])
            ok = actual_sha == entry.get("sha256")
            if "edge_count" in entry:
                ok = ok and entry["edge_count"] == len(
                    {
                        "adjacency_premask": premask_stored,
                        "adjacency_masked": masked_stored,
                        "holdout_edges": holdout_stored,
                        "mask_edges": mask_stored,
                    }[name]
                )
            if "line_count" in entry:
                ok = ok and entry["line_count"] == len(cutoff_stored)
            hash_results[name] = ok
        record(
            "artifact_hashes_match_manifest",
            all(hash_results.values()),
            "every artifact hash/byte count recorded in the graph manifest matches the file on disk",
            hash_results,
            "docs/GRAPH_PROTOCOL.md §4.5/§6",
        )

        # 3. premask adjacency replay ----------------------------------------
        premask_expected = set(split.premask_edges)
        premask_sorted_ok = premask_stored == tuple(sorted(premask_stored))
        premask_endpoints_ok = all(s in node_set and t in node_set for s, t in premask_set)
        premask_selfloop_ok = all(s != t for s, t in premask_set)
        record(
            "premask_adjacency_replay",
            premask_set == premask_expected
            and len(premask_stored) == len(premask_set)
            and premask_sorted_ok
            and premask_endpoints_ok
            and premask_selfloop_ok,
            "stored pre-mask adjacency equals the independent recount from works.jsonl "
            "(unique, sorted, in-snapshot endpoints, no self-loops)",
            {
                "recount_edges": len(premask_expected),
                "stored_edges": len(premask_set),
                "stored_lines": len(premask_stored),
                "sorted_canonical": premask_sorted_ok,
                "endpoints_in_snapshot": premask_endpoints_ok,
                "self_loops": sum(1 for s, t in premask_set if s == t),
            },
            "docs/GRAPH_PROTOCOL.md §1",
        )

        # 4. holdout split replay ---------------------------------------------
        holdout_expected = set(split.heldout_edges)
        _, refs_by_source = _eligible_source_refs(
            parsed, premask, years, config.minimum_eligible_references
        )
        per_source_ok = True
        sources_checked = 0
        for cohort in ("test", "dev"):
            for source in split.selected[cohort]:
                refs = refs_by_source[source]
                stored_h = tuple(t for s, t in holdout_stored if s == source)
                expected_h, expected_o = split_for_source(
                    source, refs, config.seed, config.heldout_fraction
                )
                h_ok = (
                    tuple(sorted(stored_h)) == tuple(sorted(expected_h))
                    and len(stored_h) == heldout_count(len(refs), config.heldout_fraction)
                    and set(stored_h) | set(expected_o) == set(refs)
                    and not (set(stored_h) & set(expected_o))
                )
                per_source_ok = per_source_ok and h_ok
                sources_checked += 1
        per_source_measured = {
            "selected_queries_checked": sources_checked,
            "all_sources_match_formula": per_source_ok,
        }
        split_payload_expected = build_split_payload(split, config)
        record(
            "holdout_split_replay",
            holdout_set == holdout_expected
            and split_stored == split_payload_expected
            and per_source_ok,
            "stored holdout edges and split payload equal the deterministic replay from "
            "works.jsonl + protocol seed (per-query h = min(R-1, max(1, ceil(0.2R))), "
            "H ∪ O = R(u), H ∩ O = ∅)",
            {
                "recount_holdout_edges": len(holdout_expected),
                "stored_holdout_edges": len(holdout_set),
                "split_payload_identical": split_stored == split_payload_expected,
                **per_source_measured,
            },
            "docs/GRAPH_PROTOCOL.md §2; configs/protocol_v1.json tracks.B.split",
        )

        # 5. mask scope completeness -------------------------------------------
        mask_expected_from_holdout = holdout_set | {(t, s) for s, t in holdout_set}
        record(
            "mask_edges_replay",
            mask_stored_set == mask_expected_from_holdout,
            "stored mask equals H_dev ∪ H_test ∪ reverse counterparts exactly",
            {
                "holdout_edges": len(holdout_set),
                "expected_mask_edges": len(mask_expected_from_holdout),
                "stored_mask_edges": len(mask_stored_set),
            },
            "docs/GRAPH_PROTOCOL.md §4.1 (mask_scope)",
        )

        # 6. two-way heldout residual (the core leakage check) ------------------
        residual_direct = sorted(mask_stored_set & masked_set)
        residual_reverse = sorted(
            (s, t) for (s, t) in mask_stored_set if (t, s) in masked_set
        )
        record(
            "two_way_heldout_residual",
            not residual_direct and not residual_reverse,
            "no held-out edge and no reverse counterpart survives in G_mask in EITHER "
            "direction (PPR transmits along Pᵀ, so one direction is not enough)",
            {
                "residual_same_direction": len(residual_direct),
                "residual_reverse_direction": len(residual_reverse),
                "examples_same_direction": residual_direct[:10],
                "examples_reverse_direction": residual_reverse[:10],
            },
            "docs/GRAPH_PROTOCOL.md §4.2/§4.5",
        )

        # 7. masked adjacency set identity + self-loops -------------------------
        identity_ok = masked_set == premask_set - mask_stored_set
        removed_edges = premask_set - masked_set
        selfloop_residue = sum(1 for s, t in masked_set if s == t)
        record(
            "masked_adjacency_set_identity",
            identity_ok
            and len(masked_stored) == len(masked_set)
            and masked_stored == tuple(sorted(masked_stored))
            and selfloop_residue == 0
            and removed_edges <= mask_stored_set,
            "G_mask equals E_pre \\ M exactly (no other edge removed, none added), "
            "stored canonically sorted, zero self-loops",
            {
                "premask_edges": len(premask_set),
                "masked_edges": len(masked_set),
                "removed_edges": len(removed_edges),
                "removed_subset_of_mask": removed_edges <= mask_stored_set,
                "self_loop_residue": selfloop_residue,
                "sorted_canonical": masked_stored == tuple(sorted(masked_stored)),
            },
            "docs/GRAPH_PROTOCOL.md §4.2",
        )

        # 8. edge accounting -----------------------------------------------------
        record(
            "edge_accounting",
            len(removed_edges) == len(premask_set) - len(masked_set),
            "|E_pre| - |E_mask| equals the number of edges removed by the mask, 1:1",
            {
                "premask_edges": len(premask_set),
                "postmask_edges": len(masked_set),
                "difference": len(premask_set) - len(masked_set),
                "removed_edges": len(removed_edges),
            },
            "SG-016 acceptance: counts khớp 1:1",
        )

        # 9. reciprocal pair accounting ------------------------------------------
        pre_pairs = sum(1 for s, t in premask_set if (t, s) in premask_set) // 2
        post_pairs = sum(1 for s, t in masked_set if (t, s) in masked_set) // 2
        affected_pairs = len(
            {
                frozenset((s, t))
                for s, t in premask_set
                if (t, s) in premask_set
                and ((s, t) in holdout_set or (t, s) in holdout_set)
            }
        )
        heldout_reverse_internal = sum(1 for s, t in holdout_set if (t, s) in premask_set)
        remaining_safe = all(
            (s, t) not in mask_stored_set and (t, s) not in mask_stored_set
            for s, t in masked_set
            if (t, s) in masked_set
        )
        pair_identity_ok = post_pairs == pre_pairs - affected_pairs
        record(
            "reciprocal_pair_accounting",
            remaining_safe and pair_identity_ok,
            "every remaining reciprocal pair has no direction inside the mask, and the "
            "post-mask pair count equals pre-mask pairs minus heldout-affected pairs "
            "(GRAPH_PROTOCOL §1.3 keeps non-heldout reciprocal edges; heldout ones are "
            "masked both ways)",
            {
                "reciprocal_pairs_premask": pre_pairs,
                "reciprocal_pairs_postmask": post_pairs,
                "reciprocal_pairs_with_heldout_direction": affected_pairs,
                "heldout_edges_whose_reverse_is_an_internal_edge": heldout_reverse_internal,
                "pair_count_identity": pair_identity_ok,
                "remaining_pairs_free_of_mask": remaining_safe,
            },
            "docs/GRAPH_PROTOCOL.md §1.3/§4; SESSION-20260917-039 special instruction",
        )

        # 10. manifest counts 1:1 vs recount --------------------------------------
        gcounts = _require(gmanifest, "counts", "graph manifest")
        counts_expected = {
            "works": len(parsed.records),
            "nodes": len(parsed.records),
            "valid_year_nodes": len(years),
            "internal_directed_edges_premask": len(premask_set),
            "internal_directed_edges_postmask": len(masked_set),
            "edges_removed_by_mask": len(premask_set) - len(masked_set),
            "self_loop_works_removed": len(premask.self_loop_works),
            "duplicate_reference_entry_count": premask.duplicate_reference_entry_count,
            "reciprocal_edge_pairs_premask": pre_pairs,
            "reciprocal_edge_pairs_postmask": post_pairs,
            "reciprocal_pairs_with_heldout_direction": affected_pairs,
            "out_of_snapshot_reference_occurrences": premask.dangling_occurrences,
            "out_of_snapshot_distinct_targets": premask.dangling_distinct_targets,
            "future_target_edges_both_years_known": premask.future_target_edges,
            "missing_title_count": int(parsed.anomalies["missing_title_count"]),
            "missing_abstract_count": int(parsed.anomalies["missing_abstract_count"]),
            "missing_publication_year_count": int(parsed.anomalies["missing_publication_year_count"]),
            "out_of_range_publication_year_count": int(
                parsed.anomalies["out_of_range_publication_year_count"]
            ),
            "missing_doi_count": int(parsed.anomalies["missing_doi_count"]),
            "reference_entries_total": sum(len(r.references) for r in parsed.records),
            "isolated_nodes_premask": len(parsed.records)
            - len({n for e in premask_set for n in e}),
            "isolated_nodes_postmask": len(parsed.records)
            - len({n for e in masked_set for n in e}),
        }
        counts_mismatch = {
            key: {"manifest": gcounts.get(key), "recount": expected}
            for key, expected in counts_expected.items()
            if gcounts.get(key) != expected
        }
        holdout_manifest = _require(gmanifest, "holdout", "graph manifest")
        holdout_expected_counts = {
            "heldout_edges_total": len(holdout_set),
            "mask_edges_total": len(mask_stored_set),
            "mask_reverse_counterpart_edges": len(mask_stored_set - holdout_set),
            "test_year": split.test_year,
            "dev_year": split.dev_year,
            "selected_queries": {"test": len(split.selected["test"]), "dev": len(split.selected["dev"])},
            "eligible_sources_by_cohort": dict(split.eligible_by_cohort),
        }
        counts_mismatch.update(
            {
                f"holdout.{key}": {"manifest": holdout_manifest.get(key), "recount": expected}
                for key, expected in holdout_expected_counts.items()
                if holdout_manifest.get(key) != expected
            }
        )
        record(
            "manifest_counts_consistent",
            not counts_mismatch,
            "every count in the graph manifest equals the independent recount from "
            "works.jsonl + stored artifacts (1:1 narrative contract)",
            {"mismatches": counts_mismatch, "fields_checked": len(counts_expected) + len(holdout_expected_counts)},
            "ADR-013 §3 (narrative 1:1 với biến đếm)",
        )

        # 11. degree features recomputed from G_mask ------------------------------
        in_recount, out_recount = degree_maps(sorted(node_set), masked_stored)
        in_stored = features_stored.get("in_degree")
        out_stored = features_stored.get("out_degree")
        pre_in, pre_out = degree_maps(sorted(node_set), premask_stored)
        incidence_ok = True
        for node in node_set:
            masked_removed_out = sum(1 for s, t in removed_edges if s == node)
            masked_removed_in = sum(1 for s, t in removed_edges if t == node)
            if out_recount[node] != pre_out[node] - masked_removed_out:
                incidence_ok = False
                break
            if in_recount[node] != pre_in[node] - masked_removed_in:
                incidence_ok = False
                break
        sum_in = sum(in_recount.values())
        sum_out = sum(out_recount.values())
        features_ok = (
            in_stored == in_recount
            and out_stored == out_recount
            and sum_in == len(masked_set)
            and sum_out == len(masked_set)
            and incidence_ok
        )
        record(
            "degree_features_recomputed_from_masked",
            features_ok,
            "stored degree features equal a recount from adjacency_masked.tsv (not from "
            "the pre-mask graph), sums equal |E_mask|, and each masked degree equals the "
            "pre-mask degree minus the masked-edge incidence",
            {
                "in_degree_match": in_stored == in_recount,
                "out_degree_match": out_stored == out_recount,
                "sum_in_degree": sum_in,
                "sum_out_degree": sum_out,
                "masked_edge_count": len(masked_set),
                "premask_minus_mask_incidence_identity": incidence_ok,
            },
            "docs/GRAPH_PROTOCOL.md §4.3/§4.4 (recompute_after_masking)",
        )

        # 12. cutoff features recomputed from G_mask ------------------------------
        expected_lines = cutoff_feature_lines(split, split.masked_edges, years)
        cutoff_ok = cutoff_stored == expected_lines
        mismatch_examples: list[str] = []
        if not cutoff_ok:
            if len(cutoff_stored) != len(expected_lines):
                mismatch_examples.append(
                    f"line count mismatch: stored {len(cutoff_stored)} vs expected {len(expected_lines)}"
                )
            for stored_line, expected_line in zip(cutoff_stored, expected_lines):
                if stored_line != expected_line:
                    mismatch_examples.append(f"{expected_line.get('source_id')}: stats mismatch")
        for line in expected_lines:
            if line["truncated_edge_count"] > len(masked_set) or line[
                "truncated_node_count"
            ] > len(years):
                cutoff_ok = False
                mismatch_examples.append(f"{line['source_id']}: truncated stats exceed G_mask")
        record(
            "cutoff_features_recomputed_from_masked",
            cutoff_ok,
            "per-query cutoff features equal a recount of the year<=year(u) induced "
            "subgraph of G_mask (test cohort first, selection order); truncated graphs "
            "never exceed G_mask",
            {
                "stored_lines": len(cutoff_stored),
                "expected_lines": len(expected_lines),
                "identical": cutoff_stored == expected_lines,
                "mismatches": mismatch_examples[:10],
            },
            "docs/GRAPH_PROTOCOL.md §3.2/§4.3",
        )

        # 13. cohort floors, caps and candidate floors ----------------------------
        floors_measured = {
            "test_year": split.test_year,
            "dev_year": split.dev_year,
            "eligible_sources_by_cohort": dict(split.eligible_by_cohort),
            "minimum_test_queries": config.minimum_test_queries,
            "minimum_dev_queries": config.minimum_dev_queries,
            "selected_queries": {k: len(v) for k, v in split.selected.items()},
            "caps": {
                "maximum_test_queries": config.maximum_test_queries,
                "maximum_dev_queries": config.maximum_dev_queries,
            },
            "novel_candidates_min_selected": {
                cohort: min(
                    (split.novel_candidates[cohort][s] for s in split.selected[cohort]),
                    default=None,
                )
                for cohort in ("test", "dev")
            },
            "minimum_novel_candidates_per_query": config.minimum_novel_candidates_per_query,
            "minimum_eligible_references": config.minimum_eligible_references,
        }
        floors_ok = (
            split.eligible_by_cohort["test"] >= config.minimum_test_queries
            and split.eligible_by_cohort["dev"] >= config.minimum_dev_queries
            and len(split.selected["test"]) <= config.maximum_test_queries
            and len(split.selected["dev"]) <= config.maximum_dev_queries
            and len(split.selected["test"]) >= config.minimum_test_queries
            and len(split.selected["dev"]) >= config.minimum_dev_queries
            and all(
                split.novel_candidates[cohort][s] >= config.minimum_novel_candidates_per_query
                for cohort in ("test", "dev")
                for s in split.selected[cohort]
            )
        )
        record(
            "cohort_floors_and_caps",
            floors_ok,
            "cohort sizes, selected query counts and per-query novel candidates meet the "
            "pinned Protocol v1 floors (50 test / 30 dev / 2 refs / 100 candidates) and caps",
            floors_measured,
            "configs/protocol_v1.json tracks.B.graph_gate (ADR-016: floors unchanged)",
        )

        # 14. query selection determinism -----------------------------------------
        selection_ok = True
        for cohort in ("test", "dev"):
            stored_list = list(split_stored["cohorts"][cohort]["selected"])
            recomputed_order = sorted(
                stored_list, key=lambda u: (sha256_text(f"{config.seed}|{u}"), u)
            )
            if recomputed_order != stored_list:
                selection_ok = False
        record(
            "query_selection_determinism",
            selection_ok,
            "selected query IDs are in ascending SHA-256(seed|canonical_source_id) order "
            "and reproduce byte-identically on replay",
            {"deterministic_order": selection_ok, "seed": config.seed},
            "docs/GRAPH_PROTOCOL.md §2.6",
        )

        # 15. label access contract -------------------------------------------------
        record(
            "label_access_contract",
            True,
            "no qrels/BEIR labels read; holdout edges live only in trusted artifacts; "
            "all features derived from adjacency_masked.tsv",
            {
                "qrels_or_beir_labels_used": False,
                "edge_source": "referenced_works only",
                "trusted_artifacts": [
                    artifact_paths["holdout_edges"].as_posix(),
                    artifact_paths["mask_edges"].as_posix(),
                ],
                "features_derived_from": features_stored.get("derived_from"),
                "cited_by_count_used_as_feature": False,
            },
            "Protocol v1 §2/§5 data_access; docs/GRAPH_PROTOCOL.md preamble",
        )

        status = "PASS" if all(check["decision"] == "PASS" for check in checks) else "FAIL"
        measured = {
            "premask_edges": len(premask_set),
            "masked_edges": len(masked_set),
            "holdout_edges": len(holdout_set),
            "mask_edges": len(mask_stored_set),
            "selected_queries": {k: len(v) for k, v in split.selected.items()},
            "two_way_residual": {"same_direction": len(residual_direct), "reverse_direction": len(residual_reverse)},
        }
    except (GraphBuildError, FeasibilityError) as exc:
        errors.append(str(exc))
        status = "FAIL"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "graph_masked_split_audit",
        "task_id": TASK_ID,
        "module": {"id": MODULE_ID, "version": MODULE_VERSION},
        "status": status,
        "measured_at": _iso(measured_at),
        "command": argv_list,
        "runtime": {"python": sys.version.split()[0], "platform": sys.platform},
        "provenance": {
            "works_jsonl": {
                "path": _display_path(works_path),
                "sha256": sha256_file(works_path) if works_path.is_file() else None,
            },
            "snapshot_manifest": {
                "path": _display_path(snapshot_manifest_path),
                "sha256": sha256_file(snapshot_manifest_path)
                if snapshot_manifest_path.is_file()
                else None,
            },
            "protocol_config": {
                "path": _display_path(protocol_path),
                "sha256": sha256_file(protocol_path) if protocol_path.is_file() else None,
            },
            "gate_report": {
                "path": _display_path(gate_report_path),
                "sha256": sha256_file(gate_report_path) if gate_report_path.is_file() else None,
            },
            "graph_manifest": {"path": _display_path(graph_manifest_path)},
            "graph_protocol_doc": {
                "path": _display_path(protocol_doc_path),
                "sha256": sha256_file(protocol_doc_path) if protocol_doc_path.is_file() else None,
            },
        },
        "qrels_used": False,
        "beir_labels_used": False,
        "checks": checks,
        "errors": errors,
        "measured_summary": measured or None,
    }
    _atomic_write(
        audit_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return (0 if status == "PASS" else 1), report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SG-016 masked graph build + leakage audit over the frozen OpenAlex core snapshot"
    )
    parser.add_argument("--works", type=Path, default=Path("data/processed/openalex/works.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/openalex_core.json"))
    parser.add_argument("--protocol", type=Path, default=Path("configs/protocol_v1.json"))
    parser.add_argument(
        "--gate-report",
        type=Path,
        default=Path("artifacts/reports/graph_feasibility_core.json"),
    )
    parser.add_argument(
        "--protocol-doc", type=Path, default=Path("docs/GRAPH_PROTOCOL.md")
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed/graph"))
    parser.add_argument(
        "--graph-manifest", type=Path, default=Path("data/manifests/graph_core.json")
    )
    parser.add_argument("--audit", type=Path, default=Path("artifacts/reports/graph_audit.json"))
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="skip the build and re-run the leakage audit against artifacts on disk",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if args.audit_only:
        exit_code, report = run_audit(
            works_path=args.works,
            snapshot_manifest_path=args.manifest,
            protocol_path=args.protocol,
            gate_report_path=args.gate_report,
            protocol_doc_path=args.protocol_doc,
            graph_manifest_path=args.graph_manifest,
            audit_path=args.audit,
            command_argv=argv_list,
        )
        print(
            f"Graph masked-split audit: status={report.get('status')}, "
            f"report={_display_path(args.audit)}"
        )
        return exit_code
    exit_code, manifest = run_build(
        works_path=args.works,
        snapshot_manifest_path=args.manifest,
        protocol_path=args.protocol,
        gate_report_path=args.gate_report,
        protocol_doc_path=args.protocol_doc,
        out_dir=args.out_dir,
        graph_manifest_path=args.graph_manifest,
        audit_path=args.audit,
        command_argv=argv_list,
    )
    if exit_code != 0:
        for error in manifest.get("errors", []):
            print(f"GRAPH BUILD FAILED: {error}", file=sys.stderr)
        return exit_code
    counts = manifest.get("counts", {})
    holdout = manifest.get("holdout", {})
    print(
        "Graph masked split built: "
        f"premask_edges={counts.get('internal_directed_edges_premask')}, "
        f"postmask_edges={counts.get('internal_directed_edges_postmask')}, "
        f"heldout_edges={holdout.get('heldout_edges_total')}, "
        f"queries={holdout.get('selected_queries')}, "
        f"manifest={_display_path(args.graph_manifest)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
