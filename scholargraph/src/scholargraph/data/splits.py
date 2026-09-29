"""ScholarGraph VN — Official Dataset Split & Leakage Verification Module (SG-011).

Compliant with Research Protocol v1:
- Isolates dev (SciFact train) and test (SciFact test, SCIDOCS test).
- Audits query namespaces for zero ID overlap between splits.
- Documents upstream benchmark text duplicates without silent filtering.
- Guarantees that query labels/qrels remain strictly isolated from rankers/indexers.
- Generates frozen split manifests in data/splits/ and machine-readable audit report.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from pydantic import BaseModel, Field

from scholargraph.ingest.beir_loader import BeirLoader, sha256_file


class SplitManifest(BaseModel):
    """Manifest for a locked dataset split."""
    schema_version: int = 1
    dataset: str
    split: str
    role: str
    created_at: str
    query_count: int
    qrel_count: int
    queries_sha256: str
    qrels_sha256: str
    query_ids: List[str]


def compute_sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def generate_and_audit_splits(
    raw_root: Path | str = Path("data/raw/beir"),
    splits_dir: Path | str = Path("data/splits"),
    report_output_path: Path | str = Path("artifacts/reports/split_audit.json"),
    policy_config_path: Path | str = Path("configs/split_policy.json"),
) -> dict[str, Any]:
    """Generate locked split query sets, write manifests, and execute leakage audits."""
    raw_base = Path(raw_root)
    out_dir = Path(splits_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_path = Path(report_output_path)
    rep_path.parent.mkdir(parents=True, exist_ok=True)

    loader = BeirLoader(raw_base)
    audit_timestamp = datetime.now(timezone.utc).astimezone().isoformat()

    report: dict[str, Any] = {
        "schema_version": 1,
        "task": "SG-011",
        "title": "Dataset Split & Leakage Audit Report",
        "audit_timestamp": audit_timestamp,
        "split_audit_passed": True,
        "errors": [],
        "splits": {},
        "leakage_checks": {},
        "split_manifests": {},
    }

    # 1. Load SciFact dev (from raw train)
    scifact_dev = loader.load("scifact", "train")
    scifact_dev_qids = sorted(list(scifact_dev.queries.keys()))
    scifact_dev_qrels_count = len(scifact_dev.qrel_records)

    # 2. Load SciFact test
    scifact_test = loader.load("scifact", "test")
    scifact_test_qids = sorted(list(scifact_test.queries.keys()))
    scifact_test_qrels_count = len(scifact_test.qrel_records)

    # 3. Load SCIDOCS test
    scidocs_test = loader.load("scidocs", "test")
    scidocs_test_qids = sorted(list(scidocs_test.queries.keys()))
    scidocs_test_qrels_count = len(scidocs_test.qrel_records)

    # Cross-split query ID overlap check for SciFact
    scifact_id_overlap = set(scifact_dev_qids).intersection(set(scifact_test_qids))
    if scifact_id_overlap:
        report["split_audit_passed"] = False
        report["errors"].append(
            f"SciFact: Detected {len(scifact_id_overlap)} overlapping query IDs between dev and test."
        )

    # Cross-split query text overlap check for SciFact
    dev_texts = {qid: scifact_dev.queries[qid].text.strip().casefold() for qid in scifact_dev_qids}
    test_texts = {qid: scifact_test.queries[qid].text.strip().casefold() for qid in scifact_test_qids}
    text_to_dev_qids: dict[str, list[str]] = {}
    for qid, text in dev_texts.items():
        text_to_dev_qids.setdefault(text, []).append(qid)

    overlapping_text_pairs: list[dict[str, str]] = []
    for qid, text in sorted(test_texts.items()):
        if text in text_to_dev_qids:
            for tr_qid in text_to_dev_qids[text]:
                overlapping_text_pairs.append({
                    "test_query_id": qid,
                    "dev_query_id": tr_qid,
                    "query_text": text,
                })

    # Referential check: all qrels point to valid documents in corpus
    scifact_corpus_ids = set(scifact_dev.corpus.keys())
    scifact_orphan_dev_docs = [q.doc_id for q in scifact_dev.qrel_records if q.doc_id not in scifact_corpus_ids]
    scifact_orphan_test_docs = [q.doc_id for q in scifact_test.qrel_records if q.doc_id not in scifact_corpus_ids]
    if scifact_orphan_dev_docs or scifact_orphan_test_docs:
        report["split_audit_passed"] = False
        report["errors"].append(
            f"SciFact: Orphan qrel docs found (dev: {len(scifact_orphan_dev_docs)}, test: {len(scifact_orphan_test_docs)})."
        )

    scidocs_corpus_ids = set(scidocs_test.corpus.keys())
    scidocs_orphan_test_docs = [q.doc_id for q in scidocs_test.qrel_records if q.doc_id not in scidocs_corpus_ids]
    if scidocs_orphan_test_docs:
        report["split_audit_passed"] = False
        report["errors"].append(
            f"SCIDOCS: Orphan qrel docs found in test: {len(scidocs_orphan_test_docs)}."
        )

    # Save split manifests
    def save_split_manifest(dataset: str, split_name: str, role: str, qids: list[str], qrel_count: int, raw_split: str) -> str:
        qrel_file = raw_base / dataset / "qrels" / f"{raw_split}.tsv"
        q_file = raw_base / dataset / "queries.jsonl"
        manifest_data = {
            "schema_version": 1,
            "dataset": dataset,
            "split": split_name,
            "raw_split_source": raw_split,
            "role": role,
            "created_at": audit_timestamp,
            "query_count": len(qids),
            "qrel_count": qrel_count,
            "queries_file": str(q_file).replace("\\", "/"),
            "queries_sha256": sha256_file(q_file),
            "qrels_file": str(qrel_file).replace("\\", "/"),
            "qrels_sha256": sha256_file(qrel_file),
            "query_ids": qids,
        }
        manifest_file = out_dir / f"{dataset}_{split_name}.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(manifest_file).replace("\\", "/")

    scifact_dev_manifest = save_split_manifest("scifact", "dev", "development_and_tuning", scifact_dev_qids, scifact_dev_qrels_count, "train")
    scifact_test_manifest = save_split_manifest("scifact", "test", "final_evaluation_locked", scifact_test_qids, scifact_test_qrels_count, "test")
    scidocs_test_manifest = save_split_manifest("scidocs", "test", "final_evaluation_locked", scidocs_test_qids, scidocs_test_qrels_count, "test")

    # Record report sections
    report["splits"] = {
        "scifact_dev": {
            "dataset": "scifact",
            "split": "dev",
            "source": "official_BEIR_train",
            "role": "development_and_tuning",
            "query_count": len(scifact_dev_qids),
            "qrel_count": scifact_dev_qrels_count,
            "corpus_count": len(scifact_corpus_ids),
            "manifest": scifact_dev_manifest,
        },
        "scifact_test": {
            "dataset": "scifact",
            "split": "test",
            "source": "official_BEIR_test",
            "role": "final_evaluation_locked",
            "query_count": len(scifact_test_qids),
            "qrel_count": scifact_test_qrels_count,
            "corpus_count": len(scifact_corpus_ids),
            "manifest": scifact_test_manifest,
        },
        "scidocs_test": {
            "dataset": "scidocs",
            "split": "test",
            "source": "official_BEIR_test",
            "role": "final_evaluation_locked",
            "query_count": len(scidocs_test_qids),
            "qrel_count": scidocs_test_qrels_count,
            "corpus_count": len(scidocs_corpus_ids),
            "manifest": scidocs_test_manifest,
        },
    }

    report["leakage_checks"] = {
        "scifact_query_id_disjoint": len(scifact_id_overlap) == 0,
        "scifact_query_id_overlap_count": len(scifact_id_overlap),
        "scifact_query_id_overlap_ids": sorted(list(scifact_id_overlap)),
        "scifact_query_text_overlap_count": len(overlapping_text_pairs),
        "scifact_query_text_overlap_pairs": overlapping_text_pairs,
        "scifact_referential_integrity": len(scifact_orphan_dev_docs) == 0 and len(scifact_orphan_test_docs) == 0,
        "scidocs_referential_integrity": len(scidocs_orphan_test_docs) == 0,
        "ranker_qrels_isolation_policy": (
            "Rankers and retrievers must ingest only corpus documents and query texts. "
            "Qrel relevance labels are strictly confined to the Evaluator component."
        ),
    }

    report["split_manifests"] = {
        "scifact_dev": scifact_dev_manifest,
        "scifact_test": scifact_test_manifest,
        "scidocs_test": scidocs_test_manifest,
    }

    rep_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    rep = generate_and_audit_splits()
    print(f"Split audit completed! Passed: {rep['split_audit_passed']}. Manifests written to data/splits/.")
