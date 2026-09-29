"""Data quality and integrity audit for frozen BEIR benchmarks.

Performs exhaustive verification of:
1. ID uniqueness and lossless canonical mapping.
2. Referential integrity between qrels, corpus and queries.
3. Missing text / abstract anomalies (e.g. 344 empty-text SCIDOCS docs).
4. Lexical token length distributions following Protocol v1 tokenizer.
5. Label distributions, relevance sparsity, and cross-split disjointness.
6. Exact text duplicates across queries and corpus.

Exports findings to artifacts/reports/beir_data_audit.json without modifying
raw benchmarks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Mapping, Sequence

from scholargraph.ingest.beir_loader import (
    BeirLoader,
    canonical_beir_id,
    raw_beir_id,
    sha256_file,
)

# Protocol v1 standard lexical tokenizer regex: (?u)\b\w+\b
_TOKEN_PATTERN = re.compile(r"(?u)\b\w+\b")

REQUIRED_SPLITS: dict[str, tuple[str, ...]] = {
    "scifact": ("train", "test"),
    "scidocs": ("test",),
}


def tokenize_text(text: str) -> list[str]:
    """Tokenize text using Protocol v1 lexical rules (Unicode casefold, regex words)."""
    if not text:
        return []
    return _TOKEN_PATTERN.findall(text.casefold())


def compute_distribution_stats(values: Sequence[int | float]) -> dict[str, int | float | None]:
    """Compute standard summary statistics for a sequence of numbers."""
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "median": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "p99": None,
        }
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mean_val = sum(sorted_vals) / n
    variance = sum((x - mean_val) ** 2 for x in sorted_vals) / n if n > 1 else 0.0
    std_val = math.sqrt(variance)

    def percentile(p: float) -> float:
        if n == 1:
            return float(sorted_vals[0])
        rank = p * (n - 1)
        lower = int(math.floor(rank))
        upper = int(math.ceil(rank))
        weight = rank - lower
        return float(sorted_vals[lower] * (1.0 - weight) + sorted_vals[upper] * weight)

    return {
        "count": n,
        "min": float(sorted_vals[0]),
        "max": float(sorted_vals[-1]),
        "mean": round(mean_val, 3),
        "std": round(std_val, 3),
        "median": round(percentile(0.50), 3),
        "p25": round(percentile(0.25), 3),
        "p75": round(percentile(0.75), 3),
        "p90": round(percentile(0.90), 3),
        "p99": round(percentile(0.99), 3),
    }


def _raw_id(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ValueError(f"Invalid _id in {location}: expected nonempty string without whitespace")
    return value


def _read_rows(path: Path):
    def unique_fields(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError(f"Duplicate JSON field '{key}' in {path}")
            row[key] = value
        return row

    def invalid_constant(value):
        raise ValueError(f"Nonfinite JSON value '{value}' in {path}")

    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line, object_pairs_hook=unique_fields, parse_constant=invalid_constant)
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object in {path} line {number}")
            if "_id" not in row:
                raise ValueError(f"Missing _id in {path} line {number}")
            _raw_id(row["_id"], f"{path} line {number}")
            yield row


def _optional_text(row: dict, key: str, location: str) -> str:
    # Missing/null text fields are an explicitly measured anomaly. A supplied
    # non-string value is malformed, never coerced into a fake empty field.
    if key not in row or row[key] is None:
        return ""
    if not isinstance(row[key], str):
        raise ValueError(f"Invalid {key} type in {location}: expected string or null")
    return row[key].strip()


def audit_raw_corpus(corpus_path: Path, dataset_name: str) -> dict[str, Any]:
    """Audit raw corpus.jsonl for missing fields, lengths, duplicates and anomalies."""
    raw_ids: set[str] = set()
    duplicate_raw_ids: list[str] = []

    missing_title_count = 0
    missing_text_count = 0
    missing_both_count = 0

    empty_text_doc_ids: list[str] = []
    empty_title_doc_ids: list[str] = []

    title_token_lengths: list[int] = []
    text_token_lengths: list[int] = []
    combined_token_lengths: list[int] = []

    title_texts: dict[str, str] = {}  # text -> doc_id
    duplicate_titles_count = 0

    year_distribution: dict[str, int] = {"present": 0, "missing": 0}
    author_distribution: dict[str, int] = {"has_authors": 0, "no_authors": 0}

    total_docs = 0
    for row in _read_rows(corpus_path):
        total_docs += 1
        raw_id = row["_id"]

        if raw_id in raw_ids:
            duplicate_raw_ids.append(raw_id)
        raw_ids.add(raw_id)

        title_str = _optional_text(row, "title", str(corpus_path))
        text_str = _optional_text(row, "text", str(corpus_path))

        if not title_str:
            missing_title_count += 1
            empty_title_doc_ids.append(raw_id)
        if not text_str:
            missing_text_count += 1
            empty_text_doc_ids.append(raw_id)
        if not title_str and not text_str:
            missing_both_count += 1

        t_tokens = tokenize_text(title_str)
        b_tokens = tokenize_text(text_str)
        c_tokens = tokenize_text(f"{title_str} {text_str}".strip())

        title_token_lengths.append(len(t_tokens))
        text_token_lengths.append(len(b_tokens))
        combined_token_lengths.append(len(c_tokens))

        if title_str:
            if title_str in title_texts:
                duplicate_titles_count += 1
            else:
                title_texts[title_str] = raw_id

        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Invalid metadata object in {corpus_path}: {raw_id}")
        if isinstance(metadata, dict):
            year = metadata.get("year")
            if year is not None and str(year).strip():
                year_distribution["present"] += 1
            else:
                year_distribution["missing"] += 1

            authors = metadata.get("authors", [])
            if isinstance(authors, list) and len(authors) > 0:
                author_distribution["has_authors"] += 1
            else:
                author_distribution["no_authors"] += 1

    if total_docs == 0:
        raise ValueError(f"Empty corpus: {corpus_path}")
    return {
        "status": "PASS",
        "total_documents": total_docs,
        "unique_raw_ids": len(raw_ids),
        "duplicate_raw_ids_count": len(duplicate_raw_ids),
        "duplicate_raw_ids": duplicate_raw_ids[:10],
        "missingness": {
            "empty_or_missing_title_count": missing_title_count,
            "empty_or_missing_text_count": missing_text_count,
            "empty_both_count": missing_both_count,
            "empty_text_doc_sample": empty_text_doc_ids[:10],
            "empty_text_doc_ids_all": empty_text_doc_ids,
        },
        "token_lengths": {
            "title": compute_distribution_stats(title_token_lengths),
            "text": compute_distribution_stats(text_token_lengths),
            "combined": compute_distribution_stats(combined_token_lengths),
        },
        "metadata_coverage": {
            "year": year_distribution,
            "authors": author_distribution,
        },
        "duplicate_titles_count": duplicate_titles_count,
    }


def audit_raw_queries(queries_path: Path) -> dict[str, Any]:
    """Audit queries.jsonl for uniqueness, token lengths and exact duplicate texts."""
    raw_ids: set[str] = set()
    duplicate_raw_ids: list[str] = []
    query_texts: dict[str, list[str]] = {}  # text -> list of raw_ids
    token_lengths: list[int] = []

    total_queries = 0
    for row in _read_rows(queries_path):
        total_queries += 1
        raw_id = row["_id"]
        if "text" not in row or not isinstance(row["text"], str) or not row["text"].strip():
            raise ValueError(f"Missing or invalid query text in {queries_path}: {raw_id}")
        text = row["text"].strip()
        if raw_id in raw_ids:
            duplicate_raw_ids.append(raw_id)
        raw_ids.add(raw_id)

        query_texts.setdefault(text, []).append(raw_id)
        tokens = tokenize_text(text)
        token_lengths.append(len(tokens))

    if total_queries == 0:
        raise ValueError(f"Empty queries: {queries_path}")
    duplicate_texts = {t: ids for t, ids in query_texts.items() if len(ids) > 1}

    return {
        "status": "PASS",
        "total_queries": total_queries,
        "unique_raw_ids": len(raw_ids),
        "duplicate_raw_ids_count": len(duplicate_raw_ids),
        "duplicate_query_texts_count": len(duplicate_texts),
        "duplicate_query_texts_sample": [
            {"text": t, "query_ids": ids} for t, ids in list(duplicate_texts.items())[:5]
        ],
        "token_lengths": compute_distribution_stats(token_lengths),
        "query_texts_map": {t: ids[0] for t, ids in query_texts.items()},
    }


def audit_raw_qrels(
    qrels_path: Path,
    corpus_ids: set[str],
    query_ids: set[str],
    empty_text_doc_ids: set[str],
) -> dict[str, Any]:
    """Audit qrels.tsv for referential integrity, score distribution and anomalies."""
    total_qrel_rows = 0
    orphan_query_ids: set[str] = set()
    orphan_corpus_ids: set[str] = set()
    duplicate_pairs: list[tuple[str, str]] = []
    conflicting_scores: list[tuple[str, str, int, int]] = []
    seen_pairs: dict[tuple[str, str], int] = {}

    score_counts: dict[str, int] = {}
    per_query_positives: dict[str, int] = {}
    per_query_total: dict[str, int] = {}
    doc_relevance_mentions: dict[str, int] = {}
    self_reference_count = 0
    positive_self_reference_count = 0

    empty_text_docs_in_qrels: set[str] = set()
    empty_text_docs_positive_in_qrels: set[str] = set()
    empty_text_docs_zero_in_qrels: set[str] = set()
    empty_text_positive_scores: set[int] = set()
    empty_text_positive_pairs_count = 0
    empty_text_zero_pairs_count = 0
    empty_text_zero_pairs_by_doc: dict[str, int] = {}

    with qrels_path.open("r", encoding="utf-8") as handle:
        header = handle.readline().strip().split("\t")
        expected_header = ["query-id", "corpus-id", "score"]
        if header != expected_header:
            raise ValueError(f"Invalid qrels header {header} in {qrels_path}")

        for line_num, line in enumerate(handle, start=2):
            if not line.strip():
                continue
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) != 3:
                raise ValueError(f"Malformed qrels line {line_num} in {qrels_path}")

            q_id, c_id, s_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
            _raw_id(parts[0], f"{qrels_path} line {line_num}")
            _raw_id(parts[1], f"{qrels_path} line {line_num}")
            try:
                score = int(s_str)
            except ValueError:
                raise ValueError(f"Non-integer score '{s_str}' at line {line_num} in {qrels_path}")
            if score not in (0, 1, 2):
                raise ValueError(f"Score outside [0, 2] at line {line_num} in {qrels_path}")
            total_qrel_rows += 1

            if q_id not in query_ids:
                orphan_query_ids.add(q_id)
            if c_id not in corpus_ids:
                orphan_corpus_ids.add(c_id)
            if q_id == c_id:
                self_reference_count += 1
                positive_self_reference_count += int(score > 0)

            pair = (q_id, c_id)
            if pair in seen_pairs:
                duplicate_pairs.append(pair)
                if seen_pairs[pair] != score:
                    conflicting_scores.append((q_id, c_id, seen_pairs[pair], score))
            else:
                seen_pairs[pair] = score

            score_counts[str(score)] = score_counts.get(str(score), 0) + 1
            per_query_total[q_id] = per_query_total.get(q_id, 0) + 1
            if score > 0:
                per_query_positives[q_id] = per_query_positives.get(q_id, 0) + 1
                doc_relevance_mentions[c_id] = doc_relevance_mentions.get(c_id, 0) + 1

            if c_id in empty_text_doc_ids:
                empty_text_docs_in_qrels.add(c_id)
                if score > 0:
                    empty_text_docs_positive_in_qrels.add(c_id)
                    empty_text_positive_pairs_count += 1
                    empty_text_positive_scores.add(score)
                else:
                    empty_text_docs_zero_in_qrels.add(c_id)
                    empty_text_zero_pairs_count += 1
                    empty_text_zero_pairs_by_doc[c_id] = empty_text_zero_pairs_by_doc.get(c_id, 0) + 1

    # Queries with zero positive qrels
    queries_evaluated = set(per_query_total.keys())
    if total_qrel_rows == 0:
        raise ValueError(f"Empty qrels split: {qrels_path}")
    zero_positive_queries = sorted(q for q in queries_evaluated if q not in per_query_positives)

    # Partition empty text docs impact
    zero_only_docs = empty_text_docs_zero_in_qrels - empty_text_docs_positive_in_qrels
    both_pos_zero_docs = empty_text_docs_zero_in_qrels.intersection(empty_text_docs_positive_in_qrels)
    empty_text_zero_pairs_in_zero_only = sum(
        empty_text_zero_pairs_by_doc.get(d, 0) for d in zero_only_docs
    )
    empty_text_zero_pairs_in_pos_docs = empty_text_zero_pairs_count - empty_text_zero_pairs_in_zero_only

    return {
        "status": "PASS",
        "total_rows": total_qrel_rows,
        "unique_queries_in_qrels": len(queries_evaluated),
        "referential_integrity": {
            "orphan_query_ids_count": len(orphan_query_ids),
            "orphan_query_ids": sorted(list(orphan_query_ids))[:10],
            "orphan_corpus_ids_count": len(orphan_corpus_ids),
            "orphan_corpus_ids": sorted(list(orphan_corpus_ids))[:10],
            "duplicate_pairs_count": len(duplicate_pairs),
            "conflicting_scores_count": len(conflicting_scores),
            "self_reference_count": self_reference_count,
            "positive_self_reference_count": positive_self_reference_count,
        },
        "score_distribution": score_counts,
        "relevance_sparsity": {
            "queries_with_zero_positive_count": len(zero_positive_queries),
            "queries_with_zero_positive": zero_positive_queries[:10],
            "positives_per_query_stats": compute_distribution_stats([per_query_positives.get(q, 0) for q in sorted(queries_evaluated)]),
            "total_judgments_per_query_stats": compute_distribution_stats(list(per_query_total.values())),
            "unique_relevant_documents": len(doc_relevance_mentions),
        },
        "empty_text_docs_impact": {
            "empty_text_docs_in_qrels_count": len(empty_text_docs_in_qrels),
            "empty_text_docs_in_qrels": sorted(list(empty_text_docs_in_qrels)),
            "empty_text_docs_positive_count": len(empty_text_docs_positive_in_qrels),
            "empty_text_docs_positive": sorted(list(empty_text_docs_positive_in_qrels)),
            "empty_text_docs_zero_only_count": len(zero_only_docs),
            "empty_text_docs_both_count": len(both_pos_zero_docs),
            "empty_text_positive_pairs_count": empty_text_positive_pairs_count,
            "empty_text_positive_scores": sorted(list(empty_text_positive_scores)),
            "empty_text_zero_pairs_count": empty_text_zero_pairs_count,
            "empty_text_zero_pairs_in_zero_only_docs_count": empty_text_zero_pairs_in_zero_only,
            "empty_text_zero_pairs_in_positive_docs_count": empty_text_zero_pairs_in_pos_docs,
            "empty_text_total_pairs_count": empty_text_positive_pairs_count + empty_text_zero_pairs_count,
        },
    }


def _failed(error: str, fields: Sequence[str]) -> dict[str, Any]:
    """Unavailable measurements are null, never successful zero observations."""
    return {"status": "FAIL", "error": error, **dict.fromkeys(fields)}


CORPUS_FIELDS = ("total_documents", "unique_raw_ids", "duplicate_raw_ids_count",
                 "duplicate_raw_ids", "missingness", "token_lengths", "metadata_coverage",
                 "duplicate_titles_count")
QUERY_FIELDS = ("total_queries", "unique_raw_ids", "duplicate_raw_ids_count",
                "duplicate_query_texts_count", "duplicate_query_texts_sample", "token_lengths")
QREL_FIELDS = ("total_rows", "unique_queries_in_qrels", "referential_integrity",
               "score_distribution", "relevance_sparsity", "empty_text_docs_impact")
OVERLAP_FIELDS = ("train_queries_count", "test_queries_count", "query_id_overlap_count",
                  "query_text_exact_overlap_count", "query_text_exact_overlap_details",
                  "shared_relevant_documents_count", "shared_relevant_documents_ratio")


def audit_single_dataset(dataset_dir: Path, dataset_name: str) -> dict[str, Any]:
    """Audit each required component; dependency failures remain unmeasured."""
    required = REQUIRED_SPLITS[dataset_name]
    errors: list[str] = []
    corpus_file, queries_file = dataset_dir / "corpus.jsonl", dataset_dir / "queries.jsonl"
    corpus_ids, query_ids = None, None

    def read_component(file, label, fields, action):
        try:
            if not file.is_file():
                raise ValueError(f"missing required {label} file: {file}")
            return action()
        except Exception as exc:
            error = f"{dataset_name}: {label} audit failed ({exc})"
            errors.append(error)
            return _failed(error, fields)

    corpus = read_component(corpus_file, "corpus", CORPUS_FIELDS,
                            lambda: audit_raw_corpus(corpus_file, dataset_name))
    queries = read_component(queries_file, "queries", QUERY_FIELDS,
                             lambda: audit_raw_queries(queries_file))
    if corpus["status"] == "PASS":
        corpus_ids = {row["_id"] for row in _read_rows(corpus_file)}
        empty_ids = set(corpus["missingness"].pop("empty_text_doc_ids_all"))
    if queries["status"] == "PASS":
        query_ids = {row["_id"] for row in _read_rows(queries_file)}
        del queries["query_texts_map"]
    if corpus_ids is not None and query_ids is not None:
        roundtrip = sum(raw_beir_id(dataset_name, canonical_beir_id(dataset_name, rid)) != rid
                        for rid in sorted(corpus_ids | query_ids))
        id_integrity = {"status": "PASS", "canonical_roundtrip_mismatches": roundtrip,
                        "namespace_sample": canonical_beir_id(dataset_name, min(corpus_ids))}
    else:
        id_integrity = _failed("Corpus/query IDs unavailable", ("canonical_roundtrip_mismatches", "namespace_sample"))

    found = {p.stem: p for p in sorted((dataset_dir / "qrels").glob("*.tsv"))}
    missing = [split for split in required if split not in found]
    splits, verification = {}, {}
    for split in sorted(set(found) | set(required)):
        if split not in found:
            error = f"{dataset_name}: missing required split '{split}' in qrels"
            errors.append(error)
            splits[split] = _failed(error, QREL_FIELDS)
        elif corpus_ids is None or query_ids is None:
            error = f"{dataset_name} ({split}): cannot audit qrels; corpus/query audit failed"
            errors.append(error)
            splits[split] = _failed(error, QREL_FIELDS)
        else:
            splits[split] = read_component(found[split], f"qrels ({split})", QREL_FIELDS,
                lambda: audit_raw_qrels(found[split], corpus_ids, query_ids, empty_ids))
        try:
            loaded = BeirLoader(dataset_dir.parent).load(dataset_name, split)
            verification[split] = {"status": "PASS", "corpus_count": len(loaded.corpus),
                                   "queries_count": len(loaded.queries), "qrel_query_keys": len(loaded.qrels),
                                   "qrel_records_count": len(loaded.qrel_records)}
        except Exception as exc:
            verification[split] = _failed(str(exc), ("corpus_count", "queries_count", "qrel_query_keys", "qrel_records_count"))
    return {"dataset": dataset_name, "errors": errors, "required_splits": list(required),
            "missing_required_splits": missing,
            "files": {"corpus_sha256": sha256_file(corpus_file) if corpus_file.is_file() else None,
                      "queries_sha256": sha256_file(queries_file) if queries_file.is_file() else None,
                      "qrels": {split: sha256_file(file) for split, file in found.items()}},
            "id_integrity": id_integrity, "corpus_audit": corpus, "queries_audit": queries,
            "splits_audit": splits, "loader_verification": verification}


def audit_scifact_train_test_overlap(raw_root: Path) -> dict[str, Any]:
    """Measure overlap only after validating complete required query/split inputs.

    Exact text means strip + casefold; details enumerate every matching pair.
    Shared relevant corpus documents are normal IR setup, not query leakage.
    """
    directory = raw_root / "scifact"
    try:
        missing = [f"{split}.tsv" for split in ("train", "test")
                   if not (directory / "qrels" / f"{split}.tsv").is_file()]
        if missing:
            raise ValueError(f"Missing required SciFact split(s): {', '.join(missing)}")
        query_audit = audit_raw_queries(directory / "queries.jsonl")
        if query_audit["duplicate_raw_ids_count"]:
            raise ValueError("Duplicate query IDs prevent a reliable overlap audit")
        texts = {row["_id"]: row["text"].strip().casefold() for row in _read_rows(directory / "queries.jsonl")}

        def split_info(split):
            file = directory / "qrels" / f"{split}.tsv"
            # Full corpus references are audited by audit_single_dataset. Here
            # collect IDs solely to validate the split rows and query membership.
            rows = [line.rstrip("\r\n").split("\t") for line in file.read_text(encoding="utf-8").splitlines()[1:] if line.strip()]
            docs = {parts[1] for parts in rows if len(parts) == 3}
            check = audit_raw_qrels(file, docs, set(texts), set())
            ref = check["referential_integrity"]
            if any(ref[key] for key in ("orphan_query_ids_count", "duplicate_pairs_count", "conflicting_scores_count", "positive_self_reference_count")):
                raise ValueError(f"Invalid qrels references/pairs in {file}")
            return ({parts[0] for parts in rows}, {parts[1] for parts in rows if int(parts[2]) > 0})

        train_ids, train_docs = split_info("train")
        test_ids, test_docs = split_info("test")
        ids_overlap = train_ids & test_ids
        text_overlap = {texts[q] for q in train_ids} & {texts[q] for q in test_ids}
        details = [{"test_query_id": te, "train_query_id": tr, "query_text": texts[te]}
                   for te in sorted(test_ids) for tr in sorted(train_ids) if texts[te] == texts[tr]]
        status = "FAIL" if ids_overlap else "PASS"
        verdict = (f"FAIL: Detected {len(ids_overlap)} overlapping query IDs between train and test splits."
                   if ids_overlap else
                   f"PASS: Disjoint query IDs; {len(text_overlap)} distinct normalized query text overlap(s), {len(details)} matching pair(s). Shared corpus is standard IR setup.")
        return {"status": status, "train_queries_count": len(train_ids), "test_queries_count": len(test_ids),
                "query_id_overlap_count": len(ids_overlap), "query_text_exact_overlap_count": len(text_overlap),
                "query_text_exact_overlap_details": details, "shared_relevant_documents_count": len(train_docs & test_docs),
                "shared_relevant_documents_ratio": round(len(train_docs & test_docs) / len(test_docs), 4) if test_docs else None,
                "verdict": verdict}
    except Exception as exc:
        return {**_failed(str(exc), OVERLAP_FIELDS), "verdict": f"FAIL: {exc}"}


def _snapshot_hashes(root: Path) -> dict[str, Any]:
    try:
        if not root.is_dir():
            raise ValueError(f"Missing raw snapshot directory: {root}")
        return {"status": "PASS", "sha256": {
            file.relative_to(root).as_posix(): sha256_file(file)
            for file in sorted(root.rglob("*")) if file.is_file()
        }}
    except Exception as exc:
        return _failed(str(exc), ("sha256",))


def run_full_beir_audit(
    raw_root: Path | str = Path("data/raw/beir"),
    output_report_path: Path | str = Path("artifacts/reports/beir_data_audit.json"),
) -> dict[str, Any]:
    """Execute complete BEIR audit for SciFact and SCIDOCS and save report."""
    root = Path(raw_root)
    out_path = Path(output_report_path)
    if out_path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Audit output must be outside the raw benchmark directory")
    if out_path.exists() and any(out_path.samefile(file) for file in root.rglob("*") if file.is_file()):
        raise ValueError("Audit output aliases a raw benchmark file")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    input_before = _snapshot_hashes(root)

    report: dict[str, Any] = {
        "schema_version": 2,
        "auditor_revision": "sg010-2.0.0",
        "auditor_source_sha256": sha256_file(Path(__file__)),
        "task": "SG-010",
        "title": "BEIR Data Quality and Integrity Audit",
        "audit_timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "audit_passed": True,
        "errors": [],
        "datasets": {},
        "cross_split_checks": {},
        "anomalies_summary": {},
        "protocol_compliance": {},
    }

    for dataset in REQUIRED_SPLITS:
        try:
            report["datasets"][dataset] = audit_single_dataset(root / dataset, dataset)
        except Exception as exc:
            error = f"{dataset}: audit execution failed ({exc})"
            report["datasets"][dataset] = {
                "dataset": dataset, "errors": [error], "required_splits": list(REQUIRED_SPLITS[dataset]),
                "missing_required_splits": None, "files": None,
                "id_integrity": _failed(error, ("canonical_roundtrip_mismatches", "namespace_sample")),
                "corpus_audit": _failed(error, CORPUS_FIELDS), "queries_audit": _failed(error, QUERY_FIELDS),
                "splits_audit": {split: _failed(error, QREL_FIELDS) for split in REQUIRED_SPLITS[dataset]},
                "loader_verification": {split: _failed(error, ()) for split in REQUIRED_SPLITS[dataset]},
            }
    report["cross_split_checks"]["scifact_train_vs_test"] = audit_scifact_train_test_overlap(root)

    # 4. Summary of critical findings & anomalies
    scidocs_data = report["datasets"]["scidocs"]
    scidocs_corpus_audit = scidocs_data["corpus_audit"]
    scidocs_corpus_size = scidocs_corpus_audit["total_documents"]
    scidocs_empty_text_count = scidocs_corpus_audit["missingness"]["empty_or_missing_text_count"] if scidocs_corpus_audit["status"] == "PASS" else None
    scidocs_empty_title_count = scidocs_corpus_audit["missingness"]["empty_or_missing_title_count"] if scidocs_corpus_audit["status"] == "PASS" else None
    scidocs_test_audit = scidocs_data["splits_audit"]["test"]

    if scidocs_corpus_audit["status"] == "FAIL":
        scidocs_qrel_impact = None
        scidocs_explanation = (
            f"FAIL: SCIDOCS corpus audit failed: {scidocs_corpus_audit['error']}."
        )
    elif scidocs_test_audit is None:
        scidocs_qrel_impact = None
        scidocs_explanation = (
            f"SCIDOCS required test split is missing from snapshot; cannot assess qrel impact for "
            f"{scidocs_empty_text_count} empty-abstract document(s)."
        )
    elif scidocs_test_audit["status"] == "FAIL":
        scidocs_qrel_impact = None
        scidocs_explanation = (
            f"FAIL: SCIDOCS test split audit failed: {scidocs_test_audit['error']}."
        )
    elif scidocs_empty_text_count == 0 and scidocs_empty_title_count == 0:
        scidocs_qrel_impact = scidocs_test_audit["empty_text_docs_impact"]
        scidocs_explanation = (
            f"All {scidocs_corpus_size:,} SCIDOCS documents have both non-empty title and abstract text."
        )
    elif scidocs_empty_text_count == 0 and scidocs_empty_title_count > 0:
        scidocs_qrel_impact = scidocs_test_audit["empty_text_docs_impact"]
        scidocs_explanation = (
            f"All {scidocs_corpus_size:,} SCIDOCS documents have non-empty abstract text; "
            f"{scidocs_empty_title_count:,} document(s) have empty title (text-only)."
        )
    elif scidocs_empty_text_count > 0 and scidocs_empty_title_count == 0:
        scidocs_qrel_impact = scidocs_test_audit["empty_text_docs_impact"]
        in_qrels_count = scidocs_qrel_impact["empty_text_docs_in_qrels_count"]
        pos_docs_count = scidocs_qrel_impact["empty_text_docs_positive_count"]
        zero_only_docs_count = scidocs_qrel_impact["empty_text_docs_zero_only_count"]
        both_docs_count = scidocs_qrel_impact["empty_text_docs_both_count"]
        pos_pairs_count = scidocs_qrel_impact["empty_text_positive_pairs_count"]
        zero_pairs_count = scidocs_qrel_impact["empty_text_zero_pairs_count"]
        zero_in_zero_only = scidocs_qrel_impact["empty_text_zero_pairs_in_zero_only_docs_count"]
        zero_in_both = scidocs_qrel_impact["empty_text_zero_pairs_in_positive_docs_count"]
        total_pairs = scidocs_qrel_impact["empty_text_total_pairs_count"]

        provenance_desc = f"In the SCIDOCS dataset snapshot ({scidocs_corpus_size:,} docs)"

        if in_qrels_count == scidocs_empty_text_count:
            presence_str = f"All {in_qrels_count} of these documents appear in the test split qrels"
        elif in_qrels_count > 0:
            presence_str = f"{in_qrels_count} of these {scidocs_empty_text_count} document(s) appear in the test split qrels"
        else:
            presence_str = f"None of these {scidocs_empty_text_count} document(s) appear in the test split qrels"

        pos_scores = scidocs_qrel_impact["empty_text_positive_scores"]
        if len(pos_scores) == 1:
            score_desc = f"score={pos_scores[0]}"
        elif len(pos_scores) > 1:
            score_desc = f"scores in {pos_scores}"
        else:
            score_desc = "positive score"

        breakdown_parts = []
        if pos_docs_count > 0:
            breakdown_parts.append(f"{pos_docs_count} document(s) have positive relevance ({score_desc}, {pos_pairs_count} pair(s))")
        if zero_only_docs_count > 0:
            breakdown_parts.append(f"{zero_only_docs_count} document(s) appear exclusively with zero relevance (score=0, {zero_in_zero_only} pair(s))")
        if both_docs_count > 0:
            breakdown_parts.append(f"{both_docs_count} document(s) with positives also appear in {zero_in_both} zero-relevance pair(s)")

        breakdown_str = "; ".join(breakdown_parts) if breakdown_parts else "0 judgments"

        scidocs_explanation = (
            f"{provenance_desc}, {scidocs_empty_text_count} document(s) contain title only "
            f"(abstract/text is missing, null or blank). {presence_str}: "
            f"{breakdown_str}, yielding a total of {total_pairs} judgment pair(s) "
            f"({pos_pairs_count} positive, {zero_pairs_count} zero). "
            f"Per Research Protocol v1, raw benchmark files are preserved unmodified; these documents must be indexed "
            f"using title alone by downstream retrievers; this audit does not verify index construction."
        )
    else:
        scidocs_qrel_impact = scidocs_test_audit["empty_text_docs_impact"]
        scidocs_explanation = (
            f"Found {scidocs_empty_text_count:,} SCIDOCS document(s) with empty abstract/text and "
            f"{scidocs_empty_title_count:,} document(s) with empty title out of {scidocs_corpus_size:,} total documents."
        )

    scifact_data = report["datasets"]["scifact"]
    scifact_corpus_audit = scifact_data["corpus_audit"]
    scifact_corpus_size = scifact_corpus_audit["total_documents"]
    scifact_empty_count = scifact_corpus_audit["missingness"]["empty_or_missing_text_count"] if scifact_corpus_audit["status"] == "PASS" else None
    scifact_empty_title_count = scifact_corpus_audit["missingness"]["empty_or_missing_title_count"] if scifact_corpus_audit["status"] == "PASS" else None

    if scifact_corpus_audit["status"] == "FAIL":
        scifact_empty_explanation = f"FAIL: SciFact corpus audit failed: {scifact_corpus_audit['error']}."
    elif scifact_empty_count == 0 and scifact_empty_title_count == 0:
        scifact_empty_explanation = f"All {scifact_corpus_size:,} SciFact documents have both non-empty title and abstract."
    elif scifact_empty_count == 0 and scifact_empty_title_count > 0:
        scifact_empty_explanation = (
            f"All {scifact_corpus_size:,} SciFact documents have non-empty abstract text; "
            f"{scifact_empty_title_count:,} document(s) have empty title (text-only)."
        )
    elif scifact_empty_count > 0 and scifact_empty_title_count == 0:
        scifact_empty_explanation = f"Found {scifact_empty_count:,} SciFact documents with empty abstract/text out of {scifact_corpus_size:,} total documents."
    else:
        scifact_empty_explanation = (
            f"Found {scifact_empty_count:,} SciFact documents with empty abstract/text and "
            f"{scifact_empty_title_count:,} document(s) with empty title out of {scifact_corpus_size:,} total documents."
        )

    overlap_audit = report["cross_split_checks"]["scifact_train_vs_test"]
    exact_overlap_count = overlap_audit["query_text_exact_overlap_count"]
    id_overlap_count = overlap_audit["query_id_overlap_count"]
    overlapping_queries = overlap_audit["query_text_exact_overlap_details"]
    shared_rel_docs_count = overlap_audit["shared_relevant_documents_count"]

    if overlap_audit["status"] == "FAIL":
        if "error" in overlap_audit:
            scifact_leakage_explanation = (
                f"FAIL: Cannot audit query leakage between SciFact train and test splits: {overlap_audit['error']}."
            )
        else:
            scifact_leakage_explanation = (
                f"FAIL: Detected query ID collision between SciFact train and test splits. {overlap_audit['verdict']}"
            )
    elif exact_overlap_count > 0:
        pair_details = [
            f"Test {p['test_query_id']} matches Train {p['train_query_id']} ({p['query_text']!r})"
            for p in overlapping_queries
        ]
        pairs_str = "; ".join(pair_details)
        scifact_leakage_explanation = (
            f"Detected {exact_overlap_count} exact query text overlap(s) between SciFact train and test splits "
            f"(status: {overlap_audit['status']}): {pairs_str}. "
            f"Shared relevant documents count across splits: {shared_rel_docs_count}. "
            f"This is an observed property of this input snapshot; text overlap must be handled by the split policy before tuning, without modifying raw files."
        )
    else:
        scifact_leakage_explanation = (
            f"No query ID overlap and no query text exact overlap detected between SciFact train and test splits "
            f"(status: PASS). {overlap_audit['verdict']}"
        )

    report["anomalies_summary"] = {
        "scidocs_empty_abstract_documents": {
            "total_empty_abstract_docs": scidocs_empty_text_count,
            "appears_in_test_qrels": scidocs_qrel_impact["empty_text_docs_in_qrels_count"] if scidocs_qrel_impact is not None else None,
            "appears_as_positive_in_test_qrels": scidocs_qrel_impact["empty_text_docs_positive_count"] if scidocs_qrel_impact is not None else None,
            "positive_doc_ids": scidocs_qrel_impact["empty_text_docs_positive"] if scidocs_qrel_impact is not None else None,
            "explanation": scidocs_explanation,
        },
        "scifact_empty_text_documents": {
            "total_empty_abstract_docs": scifact_empty_count,
            "explanation": scifact_empty_explanation,
        },
        "scifact_train_test_query_leakage": {
            "query_id_overlap_count": id_overlap_count,
            "query_text_exact_overlap_count": exact_overlap_count,
            "overlapping_queries": overlapping_queries,
            "explanation": scifact_leakage_explanation,
        },
        "referential_integrity_status": "",
    }

    # 5. Dynamic integrity gate evaluation
    integrity_errors: list[str] = []
    for d_name, data in report["datasets"].items():
        integrity_errors.extend(data["errors"])
        for component in ("corpus_audit", "queries_audit", "id_integrity"):
            if data[component]["status"] != "PASS":
                integrity_errors.append(f"{d_name}: {component} failed ({data[component]['error']})")
        corpus, queries = data["corpus_audit"], data["queries_audit"]
        if corpus["status"] == "PASS":
            if corpus["duplicate_raw_ids_count"]:
                integrity_errors.append(f"{d_name}: {corpus['duplicate_raw_ids_count']} duplicate corpus ID(s)")
            if corpus["missingness"]["empty_both_count"]:
                integrity_errors.append(f"{d_name}: {corpus['missingness']['empty_both_count']} document(s) missing both title and text")
        if queries["status"] == "PASS" and queries["duplicate_raw_ids_count"]:
            integrity_errors.append(f"{d_name}: {queries['duplicate_raw_ids_count']} duplicate query ID(s)")
        if data["id_integrity"]["status"] == "PASS" and data["id_integrity"]["canonical_roundtrip_mismatches"]:
            integrity_errors.append(f"{d_name}: canonical roundtrip mismatches")
        for split, check in data["splits_audit"].items():
            if check["status"] != "PASS":
                integrity_errors.append(f"{d_name} ({split}): {check['error']}")
                continue
            for key, label in (("orphan_query_ids_count", "orphan query IDs"), ("orphan_corpus_ids_count", "orphan corpus IDs"),
                               ("duplicate_pairs_count", "duplicate qrel pairs"), ("conflicting_scores_count", "conflicting qrel scores"),
                               ("positive_self_reference_count", "positive self-reference qrels")):
                if check["referential_integrity"][key]:
                    integrity_errors.append(f"{d_name} ({split}): {check['referential_integrity'][key]} {label}")
        for split, check in data["loader_verification"].items():
            if check["status"] != "PASS":
                integrity_errors.append(f"{d_name} ({split}): loader verification failed ({check['error']})")
    overlap = report["cross_split_checks"]["scifact_train_vs_test"]
    if overlap["status"] != "PASS":
        integrity_errors.append(f"SciFact: {overlap['verdict']}")

    input_after = _snapshot_hashes(root)
    raw_unchanged = (input_before["status"] == "PASS" and input_after["status"] == "PASS"
                     and input_before["sha256"] == input_after["sha256"])
    report["input_integrity"] = {"before": input_before, "after": input_after,
                                 "unchanged_during_audit": raw_unchanged}
    if not raw_unchanged:
        integrity_errors.append("Raw snapshot changed during audit or input hashes unavailable")

    integrity_errors = list(dict.fromkeys(integrity_errors))
    audit_passed = (len(integrity_errors) == 0)
    report["audit_passed"] = audit_passed
    report["errors"] = integrity_errors
    if audit_passed:
        report["anomalies_summary"]["referential_integrity_status"] = (
            "100% PASS; zero orphan queries, zero orphan documents, zero duplicate qrel rows."
        )
    else:
        report["anomalies_summary"]["referential_integrity_status"] = (
            f"FAIL: {len(integrity_errors)} integrity violation(s) detected: {'; '.join(integrity_errors)}"
        )

    report["protocol_compliance"] = {
        "no_test_filtering": True,
        "immutable_raw_benchmark": raw_unchanged,
        "lossless_canonical_namespacing": all(d["id_integrity"]["status"] == "PASS" and d["id_integrity"]["canonical_roundtrip_mismatches"] == 0 for d in report["datasets"].values()),
        "lexical_tokenizer_verified": "Unicode casefold + (?u)\\b\\w+\\b",
        "all_integrity_checks_passed": audit_passed,
    }

    # Save to disk
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)

    return report


if __name__ == "__main__":
    raw_path = Path("data/raw/beir")
    out_path = Path("artifacts/reports/beir_data_audit.json")
    if len(sys.argv) > 1 and sys.argv[1].strip():
        raw_path = Path(sys.argv[1].strip())
    if len(sys.argv) > 2 and sys.argv[2].strip():
        out_path = Path(sys.argv[2].strip())

    print("Running BEIR data quality audit...")
    try:
        res = run_full_beir_audit(raw_root=raw_path, output_report_path=out_path)
    except Exception as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    if not res["audit_passed"]:
        print(f"AUDIT FAILED: {len(res['errors'])} error(s) detected!", file=sys.stderr)
        for err in res["errors"]:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print(f"Audit finished successfully! Output written to {out_path}")
    print("Summary:")
    print("  SciFact corpus:", res["datasets"]["scifact"]["corpus_audit"]["total_documents"])
    print("  SCIDOCS corpus:", res["datasets"]["scidocs"]["corpus_audit"]["total_documents"])
    print("  SCIDOCS empty abstract docs:", res["anomalies_summary"]["scidocs_empty_abstract_documents"]["total_empty_abstract_docs"])
    print("  SCIDOCS empty docs with positive qrel:", res["anomalies_summary"]["scidocs_empty_abstract_documents"]["appears_as_positive_in_test_qrels"])
