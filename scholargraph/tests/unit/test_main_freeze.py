"""SG-027 main-freeze validation — every pinned hash must match the live file.

A drift between ``configs/frozen_main.json`` and the working tree fails loudly:
post-freeze changes require a freeze version bump + ADR, never a silent edit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FREEZE = PROJECT_ROOT / "configs" / "frozen_main.json"


@pytest.fixture(scope="module")
def freeze() -> dict:
    if not FREEZE.is_file():
        pytest.fail(f"Missing freeze manifest: {FREEZE}")
    return json.loads(FREEZE.read_text(encoding="utf-8"))


def _sha(relative: str) -> str:
    return hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()


def test_freeze_structure(freeze):
    assert freeze["artifact_kind"] == "main_freeze"
    assert freeze["task_id"] == "SG-027"
    assert freeze["frozen_at"].endswith("+07:00")
    assert freeze["git_head"] and len(freeze["git_head"]) == 40
    assert "tuning trên test bị cấm vĩnh viễn" in freeze["freeze_rule"]


def test_all_data_hashes_match(freeze):
    for group, entries in freeze["data"].items():
        for rel, digest in entries.items():
            assert _sha(rel) == digest, f"data drift in {group}: {rel}"


def test_split_and_graph_hashes_match(freeze):
    for rel, digest in {**freeze["splits"], **freeze["graph"]}.items():
        assert _sha(rel) == digest, f"split/graph drift: {rel}"


def test_model_and_config_hashes_match(freeze):
    for rel, digest in {**freeze["models"], **freeze["configs"]}.items():
        assert _sha(rel) == digest, f"model/config drift: {rel}"


def test_dense_index_pins_match(freeze):
    for label, digest in freeze["dense_index_pins"].items():
        rel = {
            "scifact_bge": "artifacts/indexes/scifact/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
            "scidocs_bge": "artifacts/indexes/scidocs/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
            "openalex_bge": "artifacts/indexes/openalex_core_text/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
            "scifact_e5_multilingual": "artifacts/indexes/multilingual/intfloat-multilingual-e5-base__d1287505/embeddings.npy",
            "openalex_e5_multilingual": "artifacts/indexes/multilingual/e5_openalex_core_text/embeddings.npy",
        }[label]
        assert _sha(rel) == digest, f"index drift: {label}"


def test_translation_pin_matches_cache(freeze):
    pin = freeze["translation_pin"]
    assert pin["model_id"] == "Helsinki-NLP/opus-mt-vi-en"
    assert _sha("data/processed/vn/translations_cache.json") == pin["cache_sha256"]


def test_selection_matches_dev_registry(freeze):
    sel = freeze["tuning_selection"]["track_B_best"]
    registry = json.loads((PROJECT_ROOT / "artifacts/reports/b_dev_trials.json").read_text(encoding="utf-8"))
    assert registry["selection"]["best_trial_id"] == sel["trial_id"]
    assert registry["selection"]["nDCG@10"] == sel["dev_nDCG@10"]


def test_primary_comparison_covers_three_tracks(freeze):
    pc = freeze["primary_comparison"]
    assert set(pc["track_A_scifact"]) == {"bm25_positive_idf", "tfidf_protocol", "dense_bge-base", "hybrid_rrf_k60"}
    assert pc["track_B"] == ["global_pagerank_control", "ppr_age_best_g0.3_l0.0"]
    assert set(pc["track_C_vn"]) >= {"translated_bm25", "multilingual_dense_e5", "vn_hybrid_rrf"}
    assert pc["metrics"] == ["nDCG@10", "Recall@100", "MRR@10", "MAP@100", "P@5"]


def test_freeze_file_itself_is_not_self_referential(freeze):
    raw = FREEZE.read_text(encoding="utf-8")
    assert "configs/frozen_main.json" not in json.dumps(freeze["data"])
