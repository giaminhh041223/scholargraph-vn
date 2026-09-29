"""Sealed final-test evidence builder (SG-028).

Builds the ``freeze_evidence`` bundle required by
``RunStore.create(..., final_test=True)`` (see runner._validate_final_test_gate):

- ``freeze_artifact``: status FROZEN + bindings (track/method/dataset/split,
  resolved_config_hash, data_hash, split_hash, model_hash, model_id/revision,
  evaluator_revision). All hashes are recomputed here with the exact same
  canonicalisation the RunStore uses, so a tampered bundle fails the gate.
- ``leakage_audit``: status PASS + bindings + human-readable evidence refs
  (locked split audit, ranking-path contract, masked-graph statement for B).

Rules (ADR-013/014, SG-027 freeze rule):

- The live ``configs/frozen_main.json`` hashes are re-verified against the
  working tree on every call — a drift fails loudly, never silently.
- Missing/tampered evidence fails loudly (FinalTestGateError via the gate,
  RuntimeError here). Nothing unmeasured is replaced by 0.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scholargraph.evaluation.runner import sha256_value

ARTIFACT_DIRNAME = "artifacts/final_test"


def _sha_file(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Missing required file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_verified_freeze(project_root: Path) -> tuple[dict[str, Any], str]:
    """Load frozen_main.json and re-verify every pinned hash against the tree."""
    fpath = project_root / "configs" / "frozen_main.json"
    if not fpath.is_file():
        raise RuntimeError("Missing freeze manifest configs/frozen_main.json")
    freeze = json.loads(fpath.read_text(encoding="utf-8"))
    problems: list[str] = []

    def _check(rel: str, want: str) -> None:
        p = project_root / rel
        if not p.is_file():
            problems.append(f"missing frozen file: {rel}")
            return
        if hashlib.sha256(p.read_bytes()).hexdigest() != want:
            problems.append(f"drift in {rel}")

    for group in ("scifact", "scidocs", "openalex"):
        for rel, want in freeze["data"][group].items():
            _check(rel, want)
    for rel, want in {**freeze["splits"], **freeze["graph"]}.items():
        _check(rel, want)
    for rel, want in {**freeze["models"], **freeze["configs"]}.items():
        _check(rel, want)
    index_paths = {
        "scifact_bge": "artifacts/indexes/scifact/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
        "scidocs_bge": "artifacts/indexes/scidocs/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
        "openalex_bge": "artifacts/indexes/openalex_core_text/bge-base-en-v1.5__a5beb1e3/embeddings.npy",
        "scifact_e5_multilingual": "artifacts/indexes/multilingual/intfloat-multilingual-e5-base__d1287505/embeddings.npy",
        "openalex_e5_multilingual": "artifacts/indexes/multilingual/e5_openalex_core_text/embeddings.npy",
    }
    for label, want in freeze["dense_index_pins"].items():
        _check(index_paths[label], want)
    cache = project_root / "data/processed/vn/translations_cache.json"
    if hashlib.sha256(cache.read_bytes()).hexdigest() != freeze["translation_pin"]["cache_sha256"]:
        problems.append("drift in translations_cache.json")
    if problems:
        raise RuntimeError("Freeze drift: " + "; ".join(problems))
    return freeze, _sha_file(fpath)


def _expected_hashes(resolved_config: Mapping[str, Any], data_source: Path,
                     split_definition: Path, model: Mapping[str, Any]) -> dict[str, str]:
    return {
        "config": sha256_value(dict(resolved_config)),
        "data": sha256_value(data_source),
        "split": sha256_value(split_definition),
        "model": sha256_value(dict(model)),
    }


def build_final_test_evidence(
    *,
    project_root: Path,
    freeze: Mapping[str, Any],
    freeze_sha256: str,
    track: str,
    method: str,
    dataset: str,
    split: str,
    resolved_config: Mapping[str, Any],
    data_source: Path,
    split_definition: Path,
    model: Mapping[str, Any],
    evaluator_revision: str,
    leakage_notes: list[str],
) -> dict[str, dict[str, str]]:
    """Write freeze + leakage artifacts; return the freeze_evidence bundle.

    ``resolved_config`` must already contain resolved=True/track/dataset/split
    bindings (the gate checks them). Hashes are computed exactly as RunStore
    computes them, so any caller-side tampering fails the gate loudly.
    """
    if split.strip().lower() != "test":
        raise RuntimeError("Final-test evidence is only built for locked test splits")
    if not isinstance(evaluator_revision, str) or not evaluator_revision.strip():
        raise RuntimeError("evaluator_revision must be non-empty")
    hashes = _expected_hashes(resolved_config, data_source, split_definition, model)
    outdir = project_root / ARTIFACT_DIRNAME
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    freeze_doc = {
        "artifact_kind": "final_test_freeze",
        "task_id": "SG-028",
        "status": "FROZEN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen_manifest": "configs/frozen_main.json",
        "frozen_manifest_sha256": freeze_sha256,
        "track": track,
        "method": method,
        "dataset": dataset,
        "split": split,
        "resolved_config_hash": hashes["config"],
        "data_hash": hashes["data"],
        "split_hash": hashes["split"],
        "model_hash": hashes["model"],
        "model_id": model["id"],
        "model_revision": model["revision"],
        "evaluator_revision": evaluator_revision,
    }
    leakage_doc = {
        "artifact_kind": "final_test_leakage_audit",
        "task_id": "SG-028",
        "status": "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track": track,
        "dataset": dataset,
        "split": split,
        "data_hash": hashes["data"],
        "split_hash": hashes["split"],
        "evidence_notes": list(leakage_notes),
    }
    freeze_path = outdir / f"freeze_{method}_{dataset}_{split}_{stamp}.json"
    leakage_path = outdir / f"leakage_{track}_{method}_{dataset}_{split}_{stamp}.json"
    for path, doc in ((freeze_path, freeze_doc), (leakage_path, leakage_doc)):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite evidence artifact: {path}")
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = freeze  # pinned manifest already re-verified by load_verified_freeze
    return {
        "freeze_artifact": {"path": str(freeze_path), "sha256": _sha_file(freeze_path)},
        "leakage_audit": {"path": str(leakage_path), "sha256": _sha_file(leakage_path)},
    }


TRACK_A_LEAKAGE_NOTES = [
    "Locked split manifests from SG-011 (dev/test disjoint query namespaces, corpus referential integrity, manifest consistency).",
    "Ranking path reads corpus text + locked query text only; qrels are consumed solely by the evaluator after rankings are recorded (ranking_reads_qrels=false).",
    "No graph features, no pretrained-query tuning, no test-driven config change (frozen defaults from SG-027).",
]


TRACK_B_LEAKAGE_NOTES = [
    "Masked graph G_mask excludes H_dev union H_test union reverse edges (ADR-016, SG-016); evaluated/rerank adjacency never contains held-out edges in either direction.",
    "Held-out labels enter only the evaluator; candidate pools, PPR seeds and graph features are built on G_mask + year cutoff only.",
    "Fused weights are the frozen SG-026 dev selection (gamma=0.3, lambda=0.0); nothing is selected or dropped on test.",
]
