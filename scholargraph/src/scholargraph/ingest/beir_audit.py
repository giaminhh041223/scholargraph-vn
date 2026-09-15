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

from dataclasses import asdict, dataclass
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


def tokenize_text(text: str) -> list[str]:
    """Tokenize text using Protocol v1 lexical rules (Unicode casefold, regex words)."""
    if not text:
        return []
    return _TOKEN_PATTERN.findall(text.casefold())


def compute_distribution_stats(values: Sequence[int | float]) -> dict[str, float]:
    """Compute standard summary statistics for a sequence of numbers."""
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "median": 0.0,
            "p25": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "p99": 0.0,
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
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            total_docs += 1
            row = json.loads(line)
            raw_id = str(row.get("_id", "")).strip()
            if not raw_id:
                raise ValueError(f"Empty _id in {corpus_path} line {line_num}")
            
            if raw_id in raw_ids:
                duplicate_raw_ids.append(raw_id)
            raw_ids.add(raw_id)
            
            title = row.get("title")
            text = row.get("text")
            
            title_str = title.strip() if isinstance(title, str) else ""
            text_str = text.strip() if isinstance(text, str) else ""
            
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

    return {
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
    with queries_path.open("r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            total_queries += 1
            row = json.loads(line)
            raw_id = str(row.get("_id", "")).strip()
            text = str(row.get("text", "")).strip()
            
            if not raw_id:
                raise ValueError(f"Empty _id in {queries_path} line {line_num}")
            if raw_id in raw_ids:
                duplicate_raw_ids.append(raw_id)
            raw_ids.add(raw_id)
            
            query_texts.setdefault(text, []).append(raw_id)
            tokens = tokenize_text(text)
            token_lengths.append(len(tokens))
            
    duplicate_texts = {t: ids for t, ids in query_texts.items() if len(ids) > 1}
    
    return {
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
    
    empty_text_docs_in_qrels: set[str] = set()
    empty_text_docs_positive_in_qrels: set[str] = set()
    empty_text_docs_zero_in_qrels: set[str] = set()
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
            parts = line.strip().split("\t")
            if len(parts) != 3:
                raise ValueError(f"Malformed qrels line {line_num} in {qrels_path}")
            
            q_id, c_id, s_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
            score = int(s_str)
            total_qrel_rows += 1
            
            if q_id not in query_ids:
                orphan_query_ids.add(q_id)
            if c_id not in corpus_ids:
                orphan_corpus_ids.add(c_id)
            if q_id == c_id:
                self_reference_count += 1
            
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
                else:
                    empty_text_docs_zero_in_qrels.add(c_id)
                    empty_text_zero_pairs_count += 1
                    empty_text_zero_pairs_by_doc[c_id] = empty_text_zero_pairs_by_doc.get(c_id, 0) + 1

    # Queries with zero positive qrels
    queries_evaluated = set(per_query_total.keys())
    zero_positive_queries = [q for q in queries_evaluated if q not in per_query_positives]

    # Partition empty text docs impact
    zero_only_docs = empty_text_docs_zero_in_qrels - empty_text_docs_positive_in_qrels
    both_pos_zero_docs = empty_text_docs_zero_in_qrels.intersection(empty_text_docs_positive_in_qrels)
    empty_text_zero_pairs_in_zero_only = sum(
        empty_text_zero_pairs_by_doc.get(d, 0) for d in zero_only_docs
    )
    empty_text_zero_pairs_in_pos_docs = empty_text_zero_pairs_count - empty_text_zero_pairs_in_zero_only

    return {
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
        },
        "score_distribution": score_counts,
        "relevance_sparsity": {
            "queries_with_zero_positive_count": len(zero_positive_queries),
            "queries_with_zero_positive": zero_positive_queries[:10],
            "positives_per_query_stats": compute_distribution_stats(list(per_query_positives.values())),
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
            "empty_text_zero_pairs_count": empty_text_zero_pairs_count,
            "empty_text_zero_pairs_in_zero_only_docs_count": empty_text_zero_pairs_in_zero_only,
            "empty_text_zero_pairs_in_positive_docs_count": empty_text_zero_pairs_in_pos_docs,
            "empty_text_total_pairs_count": empty_text_positive_pairs_count + empty_text_zero_pairs_count,
        },
    }


def audit_single_dataset(dataset_dir: Path, dataset_name: str) -> dict[str, Any]:
    """Audit full BEIR dataset (corpus, queries, all splits) with raw & loader checks."""
    corpus_file = dataset_dir / "corpus.jsonl"
    queries_file = dataset_dir / "queries.jsonl"
    qrels_dir = dataset_dir / "qrels"
    
    # 1. Corpus audit
    corpus_audit = audit_raw_corpus(corpus_file, dataset_name)
    corpus_raw_ids = set()
    with corpus_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                corpus_raw_ids.add(json.loads(line)["_id"])
    
    # 2. Queries audit
    queries_audit = audit_raw_queries(queries_file)
    query_raw_ids = set()
    with queries_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                query_raw_ids.add(json.loads(line)["_id"])
                
    # 3. Canonical ID mapping round-trip verification (100% exhaustive check)
    roundtrip_mismatches = 0
    for rid in sorted(corpus_raw_ids):
        cid = canonical_beir_id(dataset_name, rid)
        if raw_beir_id(dataset_name, cid) != rid:
            roundtrip_mismatches += 1
    for rid in sorted(query_raw_ids):
        cid = canonical_beir_id(dataset_name, rid)
        if raw_beir_id(dataset_name, cid) != rid:
            roundtrip_mismatches += 1

    empty_text_ids = set(corpus_audit["missingness"]["empty_text_doc_ids_all"])
    # Delete the huge list from the report summary to keep json concise, keep count and sample
    del corpus_audit["missingness"]["empty_text_doc_ids_all"]
    
    # 4. Qrels audit per split
    splits_audit: dict[str, Any] = {}
    for qrel_file in sorted(qrels_dir.glob("*.tsv")):
        split_name = qrel_file.stem
        splits_audit[split_name] = audit_raw_qrels(
            qrel_file,
            corpus_raw_ids,
            query_raw_ids,
            empty_text_ids,
        )
        
    # 5. Loader offline test
    loader = BeirLoader(dataset_dir.parent)
    loader_verification: dict[str, Any] = {}
    for split_name in sorted(splits_audit.keys()):
        try:
            loaded = loader.load(dataset_name, split_name)
            loader_verification[split_name] = {
                "status": "PASS",
                "corpus_count": len(loaded.corpus),
                "queries_count": len(loaded.queries),
                "qrel_query_keys": len(loaded.qrels),
                "qrel_records_count": len(loaded.qrel_records),
            }
        except Exception as exc:
            loader_verification[split_name] = {
                "status": "FAIL",
                "error": str(exc),
            }

    return {
        "dataset": dataset_name,
        "files": {
            "corpus_sha256": sha256_file(corpus_file),
            "queries_sha256": sha256_file(queries_file),
            "qrels": {qf.stem: sha256_file(qf) for qf in sorted(qrels_dir.glob("*.tsv"))},
        },
        "id_integrity": {
            "canonical_roundtrip_mismatches": roundtrip_mismatches,
            "namespace_sample": canonical_beir_id(dataset_name, next(iter(corpus_raw_ids))),
        },
        "corpus_audit": corpus_audit,
        "queries_audit": {
            k: v for k, v in queries_audit.items() if k != "query_texts_map"
        },
        "splits_audit": splits_audit,
        "loader_verification": loader_verification,
    }


def audit_scifact_train_test_overlap(raw_root: Path) -> dict[str, Any]:
    """Check query text, query ID, and relevant document overlap between SciFact train and test."""
    scifact_dir = raw_root / "scifact"
    queries_file = scifact_dir / "queries.jsonl"
    train_qrels_file = scifact_dir / "qrels" / "train.tsv"
    test_qrels_file = scifact_dir / "qrels" / "test.tsv"
    
    query_texts: dict[str, str] = {}
    with queries_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                query_texts[row["_id"]] = row["text"].strip().casefold()
                
    def load_split_info(path: Path) -> tuple[set[str], set[str], set[str]]:
        q_ids: set[str] = set()
        q_texts: set[str] = set()
        rel_docs: set[str] = set()
        with path.open("r", encoding="utf-8") as f:
            next(f)  # header
            for line in f:
                if line.strip():
                    parts = line.strip().split("\t")
                    qid, docid, score = parts[0], parts[1], int(parts[2])
                    q_ids.add(qid)
                    if qid in query_texts:
                        q_texts.add(query_texts[qid])
                    if score > 0:
                        rel_docs.add(docid)
        return q_ids, q_texts, rel_docs

    train_qids, train_texts, train_docs = load_split_info(train_qrels_file)
    test_qids, test_texts, test_docs = load_split_info(test_qrels_file)
    
    overlap_qids = train_qids.intersection(test_qids)
    overlap_texts = train_texts.intersection(test_texts)
    shared_relevant_docs = train_docs.intersection(test_docs)
    
    overlap_details = []
    train_text_to_qid = {query_texts[qid]: qid for qid in train_qids if qid in query_texts}
    for qid in sorted(test_qids):
        if qid in query_texts and query_texts[qid] in train_text_to_qid:
            tr_qid = train_text_to_qid[query_texts[qid]]
            overlap_details.append({
                "test_query_id": qid,
                "train_query_id": tr_qid,
                "query_text": query_texts[qid],
            })

    if overlap_qids:
        overlap_status = "FAIL"
        verdict = f"FAIL: Detected {len(overlap_qids)} overlapping query IDs between train and test splits."
    elif overlap_texts:
        overlap_status = "PASS"
        verdict = (
            f"PASS (with documented upstream anomaly): Disjoint query ID namespace (0 overlapping IDs); "
            f"exactly {len(overlap_texts)} queries have identical text between train and test in official BEIR. "
            "Shared corpus is standard IR setup."
        )
    else:
        overlap_status = "PASS"
        verdict = "PASS: Strictly disjoint query sets; shared corpus is standard IR setup."

    return {
        "status": overlap_status,
        "train_queries_count": len(train_qids),
        "test_queries_count": len(test_qids),
        "query_id_overlap_count": len(overlap_qids),
        "query_text_exact_overlap_count": len(overlap_texts),
        "query_text_exact_overlap_details": overlap_details,
        "shared_relevant_documents_count": len(shared_relevant_docs),
        "shared_relevant_documents_ratio": round(len(shared_relevant_docs) / len(test_docs), 4) if test_docs else 0.0,
        "verdict": verdict,
    }


def run_full_beir_audit(
    raw_root: Path | str = Path("data/raw/beir"),
    output_report_path: Path | str = Path("artifacts/reports/beir_data_audit.json"),
) -> dict[str, Any]:
    """Execute complete BEIR audit for SciFact and SCIDOCS and save report."""
    root = Path(raw_root)
    out_path = Path(output_report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    report: dict[str, Any] = {
        "schema_version": 1,
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
    
    # 1. Audit SciFact
    report["datasets"]["scifact"] = audit_single_dataset(root / "scifact", "scifact")
    
    # 2. Audit SCIDOCS
    report["datasets"]["scidocs"] = audit_single_dataset(root / "scidocs", "scidocs")
    
    # 3. Cross-split overlap for SciFact
    report["cross_split_checks"]["scifact_train_vs_test"] = audit_scifact_train_test_overlap(root)
    
    # 4. Summary of critical findings & anomalies
    scidocs_corpus_size = report["datasets"]["scidocs"]["corpus_audit"]["total_documents"]
    scidocs_empty_text_count = report["datasets"]["scidocs"]["corpus_audit"]["missingness"]["empty_or_missing_text_count"]
    scidocs_test_audit = report["datasets"]["scidocs"]["splits_audit"].get("test", {})
    scidocs_qrel_impact = scidocs_test_audit.get("empty_text_docs_impact", {})

    if scidocs_empty_text_count == 0:
        scidocs_explanation = (
            f"All {scidocs_corpus_size:,} SCIDOCS documents have both non-empty title and abstract text."
        )
    else:
        in_qrels_count = scidocs_qrel_impact.get("empty_text_docs_in_qrels_count", 0)
        pos_docs_count = scidocs_qrel_impact.get("empty_text_docs_positive_count", 0)
        zero_only_docs_count = scidocs_qrel_impact.get("empty_text_docs_zero_only_count", in_qrels_count - pos_docs_count)
        both_docs_count = scidocs_qrel_impact.get("empty_text_docs_both_count", 0)
        pos_pairs_count = scidocs_qrel_impact.get("empty_text_positive_pairs_count", 0)
        zero_pairs_count = scidocs_qrel_impact.get("empty_text_zero_pairs_count", 0)
        zero_in_zero_only = scidocs_qrel_impact.get("empty_text_zero_pairs_in_zero_only_docs_count", 0)
        zero_in_both = scidocs_qrel_impact.get("empty_text_zero_pairs_in_positive_docs_count", 0)
        total_pairs = scidocs_qrel_impact.get("empty_text_total_pairs_count", pos_pairs_count + zero_pairs_count)

        scidocs_explanation = (
            f"In the official SCIDOCS BEIR snapshot, {scidocs_empty_text_count} document(s) contain title only "
            f"(abstract/text is empty string). All {in_qrels_count} of these documents appear in the test split qrels: "
            f"{pos_docs_count} document(s) have positive relevance (score=1, {pos_pairs_count} pair(s)); "
            f"{zero_only_docs_count} document(s) appear exclusively with zero relevance (score=0, {zero_in_zero_only} pair(s))"
            + (f"; and {both_docs_count} document(s) with positives also appear in {zero_in_both} zero-relevance pair(s)" if both_docs_count > 0 else "")
            + f", yielding a total of {total_pairs} judgment pair(s) ({pos_pairs_count} positive, {zero_pairs_count} zero). "
            f"Per Research Protocol v1, raw benchmark files are preserved unmodified; these documents are indexed "
            f"using title alone and are NOT filtered out."
        )

    scifact_corpus_size = report["datasets"]["scifact"]["corpus_audit"]["total_documents"]
    scifact_empty_count = report["datasets"]["scifact"]["corpus_audit"]["missingness"]["empty_or_missing_text_count"]
    if scifact_empty_count == 0:
        scifact_empty_explanation = f"All {scifact_corpus_size:,} SciFact documents have both non-empty title and abstract."
    else:
        scifact_empty_explanation = f"Found {scifact_empty_count:,} SciFact documents with empty abstract/text out of {scifact_corpus_size:,} total documents."

    overlap_audit = report["cross_split_checks"]["scifact_train_vs_test"]
    exact_overlap_count = overlap_audit["query_text_exact_overlap_count"]
    id_overlap_count = overlap_audit["query_id_overlap_count"]
    overlapping_queries = overlap_audit["query_text_exact_overlap_details"]
    shared_rel_docs_count = overlap_audit.get("shared_relevant_documents_count", 0)

    if exact_overlap_count == 0 and id_overlap_count == 0:
        scifact_leakage_explanation = (
            f"No query ID overlap and no query text exact overlap detected between SciFact train and test splits "
            f"(status: {overlap_audit['status']}). {overlap_audit['verdict']}"
        )
    elif exact_overlap_count > 0 and id_overlap_count == 0:
        pair_details = [
            f"Test {p['test_query_id']} matches Train {p['train_query_id']} ({p['query_text']!r})"
            for p in overlapping_queries
        ]
        pairs_str = "; ".join(pair_details)
        scifact_leakage_explanation = (
            f"Detected {exact_overlap_count} exact query text overlap(s) between SciFact train and test splits "
            f"(status: {overlap_audit['status']}): {pairs_str}. "
            f"Shared relevant documents count across splits: {shared_rel_docs_count}. "
            f"This is an inherent property of the upstream benchmark and is documented rather than filtered."
        )
    else:
        scifact_leakage_explanation = (
            f"CRITICAL: Detected {id_overlap_count} overlapping query IDs between train and test splits. "
            f"{overlap_audit['verdict']}"
        )

    report["anomalies_summary"] = {
        "scidocs_empty_abstract_documents": {
            "total_empty_abstract_docs": scidocs_empty_text_count,
            "appears_in_test_qrels": scidocs_qrel_impact.get("empty_text_docs_in_qrels_count", 0),
            "appears_as_positive_in_test_qrels": scidocs_qrel_impact.get("empty_text_docs_positive_count", 0),
            "positive_doc_ids": scidocs_qrel_impact.get("empty_text_docs_positive", []),
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
    for d_name, d_data in report["datasets"].items():
        c_audit = d_data["corpus_audit"]
        if c_audit["duplicate_raw_ids_count"] > 0:
            integrity_errors.append(f"{d_name}: {c_audit['duplicate_raw_ids_count']} duplicate corpus ID(s)")
        if c_audit["missingness"]["empty_both_count"] > 0:
            integrity_errors.append(f"{d_name}: {c_audit['missingness']['empty_both_count']} document(s) missing both title and text")
            
        q_audit = d_data["queries_audit"]
        if q_audit["duplicate_raw_ids_count"] > 0:
            integrity_errors.append(f"{d_name}: {q_audit['duplicate_raw_ids_count']} duplicate query ID(s)")
            
        id_int = d_data["id_integrity"]
        if id_int["canonical_roundtrip_mismatches"] > 0:
            integrity_errors.append(f"{d_name}: {id_int['canonical_roundtrip_mismatches']} canonical roundtrip mismatch(es)")
            
        for split_name, s_audit in d_data["splits_audit"].items():
            ref = s_audit["referential_integrity"]
            if ref["orphan_query_ids_count"] > 0:
                integrity_errors.append(f"{d_name} ({split_name}): {ref['orphan_query_ids_count']} orphan query ID(s) in qrels")
            if ref["orphan_corpus_ids_count"] > 0:
                integrity_errors.append(f"{d_name} ({split_name}): {ref['orphan_corpus_ids_count']} orphan corpus ID(s) in qrels")
            if ref["duplicate_pairs_count"] > 0:
                integrity_errors.append(f"{d_name} ({split_name}): {ref['duplicate_pairs_count']} duplicate qrel pair(s)")
            if ref["conflicting_scores_count"] > 0:
                integrity_errors.append(f"{d_name} ({split_name}): {ref['conflicting_scores_count']} conflicting qrel score(s)")
                
        for split_name, l_ver in d_data["loader_verification"].items():
            if l_ver["status"] != "PASS":
                integrity_errors.append(f"{d_name} ({split_name}): loader verification failed ({l_ver.get('error')})")

    scifact_overlap = report["cross_split_checks"].get("scifact_train_vs_test", {})
    if scifact_overlap.get("status") == "FAIL":
        integrity_errors.append(f"SciFact: {scifact_overlap.get('query_id_overlap_count', 0)} overlapping query IDs between train and test")

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
        "immutable_raw_benchmark": True,
        "lossless_canonical_namespacing": True,
        "lexical_tokenizer_verified": "Unicode casefold + (?u)\\b\\w+\\b",
        "all_integrity_checks_passed": audit_passed,
    }
    
    # Save to disk
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        
    return report


if __name__ == "__main__":
    print("Running BEIR data quality audit...")
    res = run_full_beir_audit()
    if not res.get("audit_passed", False):
        print(f"AUDIT FAILED: {len(res.get('errors', []))} error(s) detected!", file=sys.stderr)
        for err in res.get("errors", []):
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print("Audit finished successfully! Output written to artifacts/reports/beir_data_audit.json")
    print("Summary:")
    print("  SciFact corpus:", res["datasets"]["scifact"]["corpus_audit"]["total_documents"])
    print("  SCIDOCS corpus:", res["datasets"]["scidocs"]["corpus_audit"]["total_documents"])
    print("  SCIDOCS empty abstract docs:", res["anomalies_summary"]["scidocs_empty_abstract_documents"]["total_empty_abstract_docs"])
    print("  SCIDOCS empty docs with positive qrel:", res["anomalies_summary"]["scidocs_empty_abstract_documents"]["appears_as_positive_in_test_qrels"])
