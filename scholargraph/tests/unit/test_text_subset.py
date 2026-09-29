"""ADR-017 text-subset builder tests (SG-026 follow-up, SG-019 delta)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholargraph.retrieval.dense import CORPUS_SPECS, read_corpus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
SUBSET = PROJECT_ROOT / "data" / "processed" / "openalex" / "works_text.jsonl"
MANIFEST = PROJECT_ROOT / "data" / "manifests" / "openalex_core_text.json"
FROZEN_MAIN = PROJECT_ROOT / "configs" / "frozen_main.json"
EXCLUDED = {"openalex:W126924136"}


def test_spec_registered() -> None:
    assert CORPUS_SPECS["openalex_core_text"]["kind"] == "openalex"
    assert CORPUS_SPECS["openalex_core_text"]["manifest_path"] == "data/manifests/openalex_core_text.json"


def test_subset_counts_and_exclusion() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["status"] == "COMPLETED"
    assert m["counts"] == {"parent_works": 18251, "text_works": 18250, "excluded": 1}
    assert {d["id"] for d in m["excluded_textless_works"]} == EXCLUDED
    assert m["postprocess"] == {"processed_works": 18250, "output_order": "canonical ID ascending"}


def test_subset_readable_by_encoder_loader() -> None:
    corpus = read_corpus("openalex_core_text", PROJECT_ROOT)
    assert len(corpus.doc_ids) == 18250
    assert not (set(corpus.doc_ids) & EXCLUDED)
    assert tuple(sorted(corpus.doc_ids)) == corpus.doc_ids


def test_builder_rerun_deterministic(tmp_path: Path) -> None:
    old = json.loads(MANIFEST.read_text(encoding="utf-8"))
    freeze = json.loads(FROZEN_MAIN.read_text(encoding="utf-8"))
    pinned_sha = freeze["data"]["openalex"]["data/processed/openalex/works_text.jsonl"]
    out_data = tmp_path / "works_text.jsonl"
    out_manifest = tmp_path / "openalex_core_text.json"
    env = dict(os.environ, PYTHONPATH="src")
    r = subprocess.run(
        [
            str(PYTHON),
            "scripts/build_openalex_text_subset.py",
            "--output-data",
            str(out_data),
            "--output-manifest",
            str(out_manifest),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    after = json.loads(out_manifest.read_text(encoding="utf-8"))
    actual_sha = hashlib.sha256(out_data.read_bytes()).hexdigest()
    assert actual_sha == pinned_sha
    assert after["artifacts"]["works_jsonl"]["sha256"] == pinned_sha
    assert after["artifacts"]["works_jsonl"]["sha256"] == old["artifacts"]["works_jsonl"]["sha256"]
    assert after["counts"] == old["counts"]


def test_builder_missing_input_exits_1(tmp_path: Path) -> None:
    out_data = tmp_path / "works_text.jsonl"
    out_manifest = tmp_path / "openalex_core_text.json"
    missing_input = tmp_path / "nonexistent_works.jsonl"
    env = dict(os.environ, PYTHONPATH="src")
    r = subprocess.run(
        [
            str(PYTHON),
            "scripts/build_openalex_text_subset.py",
            "--input-data",
            str(missing_input),
            "--output-data",
            str(out_data),
            "--output-manifest",
            str(out_manifest),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
    )
    assert r.returncode == 1
    assert "FAIL:" in r.stderr
    assert not out_data.exists()
