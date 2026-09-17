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
    args = parser.parse_args(argv)
    try:
        if args.command == "translate":
            cache = translate_manifest(args.manifest, args.cache)
            print(f"Translation cache: {len(cache['entries'])} entries -> {args.cache}")
        else:
            diag = raw_vi_bm25_diagnostic(args.manifest, args.corpus, args.top_k)
            out = PROJECT_ROOT / "artifacts/reports/vi_bm25_diagnostic.json"
            out.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Diagnostic: {diag['counts']} -> {out}")
    except CrossLingualError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
