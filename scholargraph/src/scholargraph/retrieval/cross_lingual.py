"""Cross-lingual VN→EN retrieval components — task SG-032.

Parts:
- ``translate_manifest``: deterministic opus-mt-vi-en translation of the
  approved VN query manifest with a persistent cache. Greedy decode; a cache
  hit never reloads the model; re-running reproduces the cache byte-identically
  (modulo nothing — entries are only added, never rewritten).
- ``raw_vi_bm25_diagnostic``: ORIGINAL_VI_BM25 diagnostic — Vietnamese query
  tokens scored against the English corpus under the protocol tokenizer.
  Reported with coverage limits; NEVER a pool method (Protocol v1 §7).

No silent bypass: a missing manifest, missing model, or empty translation
fails loudly with exit 1. Paid-LLM dependency: none (local opus-mt only).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scholargraph.retrieval.bm25 import tokenize

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MISSING = "[không có]"


class CrossLingualError(RuntimeError):
    """Fatal failure; the CLI must exit 1."""


def _require_file(path: Path, what: str) -> Path:
    if not path.is_file():
        raise CrossLingualError(f"Missing {what}: {path}")
    return path


def load_approved_manifest(path: Path) -> dict[str, Any]:
    _require_file(path, "VN query manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") not in ("approved_no_edits", "approved_with_edits"):
        raise CrossLingualError(
            f"VN query manifest is not human-approved (status={manifest.get('status')!r}); "
            "SG-032 must not consume a draft.")
    if not manifest.get("provenance", {}).get("human_approval"):
        raise CrossLingualError("VN query manifest lacks recorded human approval.")
    return manifest


def load_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "artifact_kind": "vn_translation_cache",
                "model_id": "Helsinki-NLP/opus-mt-vi-en", "entries": {}}
    cache = json.loads(path.read_text(encoding="utf-8"))
    if cache.get("artifact_kind") != "vn_translation_cache":
        raise CrossLingualError(f"Unexpected cache artifact_kind: {cache.get('artifact_kind')!r}")
    return cache


def translate_manifest(manifest_path: Path, cache_path: Path,
                       model_dir: Path | None = None) -> dict[str, Any]:
    """Translate every approved query once; cached entries are never recomputed."""
    manifest = load_approved_manifest(manifest_path)
    cache = load_cache(cache_path)
    queries = manifest["queries"]

    missing = [q for q in queries if q["query_id"] not in cache["entries"]]
    if missing:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - environment guard
            raise CrossLingualError(f"transformers unavailable for translation: {exc}")
        model_name = cache["model_id"]
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        except Exception as exc:
            raise CrossLingualError(f"Failed to load translation model {model_name!r}: {exc}")
        model.eval()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        for query in missing:
            text = query["text_vi"]
            batch = tokenizer([text], return_tensors="pt", truncation=True, max_length=512)
            generated = model.generate(**batch, num_beams=1, do_sample=False, max_new_tokens=256)
            translated = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
            if not translated:
                raise CrossLingualError(f"Empty translation for {query['query_id']}")
            cache["entries"][query["query_id"]] = {
                "text_vi": text,
                "text_en": translated,
                "split": query["split"],
                "intent_family": query["intent_family"],
                "decode": "greedy(num_beams=1, do_sample=False)",
            }
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    uncovered = [q["query_id"] for q in queries if q["query_id"] not in cache["entries"]]
    if uncovered:
        raise CrossLingualError(f"Translation cache incomplete after run: {uncovered}")
    return cache


def raw_vi_bm25_diagnostic(manifest_path: Path, corpus_path: Path, top_k: int = 10) -> dict[str, Any]:
    """ORIGINAL_VI_BM25 diagnostic: raw Vietnamese tokens vs English corpus."""
    from scholargraph.retrieval.bm25 import BM25Index, load_corpus

    _require_file(corpus_path, "frozen corpus")
    manifest = load_approved_manifest(manifest_path)
    corpus = load_corpus(corpus_path, dataset="scifact")
    index = BM25Index(dict(corpus.texts), k1=1.5, b=0.75)
    results = []
    zero_token = 0
    for query in manifest["queries"]:
        tokens = tokenize(query["text_vi"])
        if not tokens:
            zero_token += 1
            results.append({"query_id": query["query_id"], "tokens": 0, "top1": None, "top1_score": None})
            continue
        hits = index.rank(query["text_vi"], top_k=top_k)
        results.append({"query_id": query["query_id"], "tokens": len(tokens),
                        "top1": hits[0][0] if hits else None,
                        "top1_score": hits[0][1] if hits else None})
    return {
        "schema_version": 1,
        "artifact_kind": "original_vi_bm25_diagnostic",
        "diagnostic_only": True,
        "never_a_pool_method": True,
        "counts": {"queries": len(manifest["queries"]), "zero_token_queries": zero_token},
        "coverage_limit": "Vietnamese tokens almost never match English corpus terms; overlap is expected near zero",
        "results": results,
    }


def _load_multilingual_config(path: Path) -> dict[str, Any]:
    _require_file(path, "multilingual encoder config")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("model_id", "revision", "pooling", "normalize", "l2_normalize",
                "embedding_dimension", "max_length", "license", "missing_embedding"):
        if key not in cfg or cfg[key] in (None, ""):
            raise CrossLingualError(f"Multilingual config missing required field {key!r}: {path}")
    if cfg["pooling"] != "mean":
        raise CrossLingualError(f"Only mean pooling is supported for multilingual candidates, got {cfg['pooling']!r}")
    if cfg["l2_normalize"] is not True or cfg["normalize"] is not True:
        raise CrossLingualError("Protocol dense block requires l2_normalize=true/normalize=true.")
    if cfg["missing_embedding"] != "fail_not_drop_document":
        raise CrossLingualError("missing_embedding must be fail_not_drop_document.")
    return cfg


class MultilingualEncoder:
    """Mean-pooling multilingual encoder with query-only prefixes (e5) or none."""

    def __init__(self, cfg: dict[str, Any], snapshot_dir: Path | None = None):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise CrossLingualError(f"torch/transformers unavailable: {exc}")
        self._torch = torch
        name = cfg["model_id"]
        source = str(snapshot_dir) if snapshot_dir else name
        self.tokenizer = AutoTokenizer.from_pretrained(source)
        self.model = AutoModel.from_pretrained(source)
        self.model.eval()
        self.cfg = cfg
        self.query_prefix = cfg.get("prefix") or ""
        self.passage_prefix = cfg.get("passage_prefix") or ""

    def encode(self, texts: list[str], is_query: bool = False, batch_size: int = 32) -> list[list[float]]:
        torch = self._torch
        prefix = self.query_prefix if is_query else self.passage_prefix
        out: list[list[float]] = []
        max_length = self.cfg["max_length"]
        for start in range(0, len(texts), batch_size):
            batch = [prefix + t for t in texts[start:start + batch_size]]
            encoded = self.tokenizer(batch, padding=True, truncation=True,
                                     max_length=max_length, return_tensors="pt")
            with torch.no_grad():
                hidden = self.model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            out.extend(pooled.tolist())
        return out


def encode_corpus_multilingual(cfg_path: Path, corpus_path: Path, output_dir: Path,
                               batch_size: int = 32, max_docs: int | None = None) -> dict[str, Any]:
    """Encode the frozen corpus with a multilingual candidate; shard-free single pass.

    Writes embeddings.npy (rows aligned to doc_ids.json order), manifest with
    checksums, measured throughput, and revision pin. ``max_docs`` encodes only
    the first N docs for pilot comparisons (manifest records the sampling; the
    full-corpus encode for the pinned model is a separate, complete run).
    """
    import hashlib
    import time

    import numpy as np

    from scholargraph.retrieval.dense import _beir_document_text

    cfg = _load_multilingual_config(cfg_path)
    _require_file(corpus_path, "frozen corpus")
    doc_ids: list[str] = []
    texts: list[str] = []
    for lineno, line in enumerate(corpus_path.read_text(encoding="utf-8").rstrip("\n").split("\n"), 1):
        if not line.strip():
            raise CrossLingualError(f"Blank line in {corpus_path} at {lineno}")
        row = json.loads(line)
        raw_id = str(row["_id"])
        text, _, _ = _beir_document_text(row, raw_id, corpus_path, lineno)
        doc_ids.append(f"beir:scifact:{raw_id}")
        texts.append(text)
    if max_docs is not None:
        if max_docs <= 0:
            raise CrossLingualError(f"max_docs must be positive, got {max_docs}")
        doc_ids = doc_ids[:max_docs]
        texts = texts[:max_docs]
    if not doc_ids:
        raise CrossLingualError(f"Corpus is empty: {corpus_path}")

    import torch  # guarded by MultilingualEncoder init below anyway

    snapshot_dir = cfg.get("snapshot_local")
    snap = PROJECT_ROOT / snapshot_dir / "snapshots" / cfg["revision"] if snapshot_dir else None
    encoder = MultilingualEncoder(cfg, snap)
    started = time.perf_counter()
    vectors = encoder.encode(texts, is_query=False, batch_size=batch_size)
    elapsed = time.perf_counter() - started
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.shape != (len(doc_ids), cfg["embedding_dimension"]):
        raise CrossLingualError(f"Unexpected embedding shape {matrix.shape}")

    output_dir.mkdir(parents=True, exist_ok=True)
    npy_path = output_dir / "embeddings.npy"
    ids_path = output_dir / "doc_ids.json"
    np.save(npy_path, matrix)
    ids_path.write_text(json.dumps(doc_ids, ensure_ascii=False, indent=1), encoding="utf-8")

    def sha256(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    manifest = {
        "schema_version": 1,
        "artifact_kind": "multilingual_embedding_index",
        "task_id": "SG-032",
        "model_id": cfg["model_id"],
        "model_revision": cfg["revision"],
        "pooling": cfg["pooling"],
        "embedding_dimension": cfg["embedding_dimension"],
        "max_length": cfg["max_length"],
        "doc_count": len(doc_ids),
        "sampled": max_docs is not None,
        "sample_note": ("PILOT SAMPLE — first N docs only; full-corpus encode for the pinned "
                        "model is a separate complete run" if max_docs is not None else None),
        "throughput_docs_per_second": round(len(doc_ids) / elapsed, 3),
        "encode_seconds": round(elapsed, 3),
        "gpu": "not_measured_local",
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "embeddings_sha256": sha256(npy_path),
        "doc_ids_sha256": sha256(ids_path),
        "config_sha256": sha256(cfg_path),
        "status": "COMPLETED",
    }
    (output_dir / "index_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def pilot_search_multilingual(cfg_path: Path, index_dir: Path,
                              manifest_path: Path, top_k: int = 5) -> dict[str, Any]:
    """Encode the 5 pilot VN queries (original Vietnamese) and rank descriptively."""
    import numpy as np

    cfg = _load_multilingual_config(cfg_path)
    manifest = load_approved_manifest(manifest_path)
    index_dir = Path(index_dir)
    ids = json.loads((index_dir / "doc_ids.json").read_text(encoding="utf-8"))
    matrix = np.load(index_dir / "embeddings.npy")
    snap = PROJECT_ROOT / cfg["snapshot_local"] / "snapshots" / cfg["revision"] if cfg.get("snapshot_local") else None
    encoder = MultilingualEncoder(cfg, snap)

    pilot = [q for q in manifest["queries"] if q.get("annotation_pilot")]
    if len(pilot) != 5:
        raise CrossLingualError(f"Expected 5 pilot queries, found {len(pilot)}")
    vectors = encoder.encode([q["text_vi"] for q in pilot], is_query=True)
    results = []
    for query, vec in zip(pilot, vectors):
        v = np.asarray(vec, dtype=np.float32)
        scores = matrix @ v
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], ids[i]))[:top_k]
        results.append({"query_id": query["query_id"], "intent_family": query["intent_family"],
                        "top": [{"doc_id": ids[i], "score": round(float(scores[i]), 4)} for i in order]})
    return {"schema_version": 1, "artifact_kind": "multilingual_pilot_search",
            "model_id": cfg["model_id"], "model_revision": cfg["revision"],
            "note": "descriptive top-5 for technical pilot; NO relevance metrics (labels at SG-033)",
            "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-lingual VN tools (SG-032).")
    sub = parser.add_subparsers(dest="command", required=True)
    tr = sub.add_parser("translate")
    tr.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/annotations/vn_query_manifest.json")
    tr.add_argument("--cache", type=Path, default=PROJECT_ROOT / "data/processed/vn/translations_cache.json")
    diag = sub.add_parser("raw-vi-diagnostic")
    diag.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/annotations/vn_query_manifest.json")
    diag.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "data/raw/beir/scifact/corpus.jsonl")
    diag.add_argument("--top-k", type=int, default=10)
    enc = sub.add_parser("encode-multilingual")
    enc.add_argument("--config", type=Path, required=True)
    enc.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "data/raw/beir/scifact/corpus.jsonl")
    enc.add_argument("--output-dir", type=Path, required=True)
    enc.add_argument("--batch-size", type=int, default=32)
    enc.add_argument("--max-docs", type=int, default=None)
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--config", type=Path, required=True)
    pilot.add_argument("--index-dir", type=Path, required=True)
    pilot.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/annotations/vn_query_manifest.json")
    pilot.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        if args.command == "translate":
            cache = translate_manifest(args.manifest, args.cache)
            print(f"Translation cache: {len(cache['entries'])} entries -> {args.cache}")
        elif args.command == "raw-vi-diagnostic":
            diag = raw_vi_bm25_diagnostic(args.manifest, args.corpus, args.top_k)
            out = PROJECT_ROOT / "artifacts/reports/vi_bm25_diagnostic.json"
            out.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Diagnostic: {diag['counts']} -> {out}")
        elif args.command == "encode-multilingual":
            manifest = encode_corpus_multilingual(args.config, args.corpus, args.output_dir,
                                                  batch_size=args.batch_size, max_docs=args.max_docs)
            print(f"Multilingual encode: {manifest['doc_count']} docs, "
                  f"{manifest['throughput_docs_per_second']} docs/s -> {args.output_dir}")
        else:
            results = pilot_search_multilingual(args.config, args.index_dir, args.manifest, args.top_k)
            out = PROJECT_ROOT / f"artifacts/reports/multilingual_pilot_{args.config.stem}.json"
            out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Pilot search -> {out}")
    except CrossLingualError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
