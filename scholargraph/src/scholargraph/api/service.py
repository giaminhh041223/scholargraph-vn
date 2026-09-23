"""Search service over frozen data — task SG-035 (no qrels, no synthetic results).

Backends (all real, CPU):
- lexical: protocol BM25 (k1=1.5, b=0.75) over the frozen SciFact corpus,
- dense: exact cosine over the SG-019 scifact index (bge-base-en-v1.5),
- hybrid: RRF k=60 fusion of the two top-k lists (SG-020),
- recommend: dense top-N similar papers excluding self.

Every response carries snapshot/method IDs. Unknown docs → 404, empty
queries / bad paging → 400. Missing metadata is null, never fabricated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from scholargraph.ingest.beir_loader import canonical_beir_id, sha256_file
from scholargraph.retrieval.bm25 import BM25Index, load_corpus
from scholargraph.retrieval.dense import (
    ExactDenseIndex,
    HfLocalEncoder,
    _snapshot_dir_from_record,
    apply_query_prefix,
    load_dense_encoder_config,
    verify_model_snapshot,
)
from scholargraph.retrieval.hybrid import rrf_fuse

SNAPSHOT_ID = "beir-scifact-frozen"
METHOD_IDS = {
    "bm25": "bm25-positive-idf-k1_1.5-b_0.75",
    "dense": "dense-bge-base-en-v1.5-a5beb1e3-cosine",
    "hybrid": "hybrid-rrf-k60-bm25-dense",
    "recommend": "recommend-dense-cosine-excl-self",
}


class ServiceError(Exception):
    """Fatal service error mapped to an HTTP error response."""


class SearchService:
    """Loaded once at app startup; read-only afterwards."""

    def __init__(self, project_root: Path | str) -> None:
        root = Path(project_root)
        corpus_path = root / "data" / "raw" / "beir" / "scifact" / "corpus.jsonl"
        corpus = load_corpus(corpus_path, dataset="scifact")
        self._texts: dict[str, str] = dict(corpus.texts)
        self._titles: dict[str, str] = {}
        for line in corpus_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                raise ServiceError("Blank line in corpus file")
            row = json.loads(line)
            cid = canonical_beir_id("scifact", str(row["_id"]))
            self._titles[cid] = str(row.get("title") or "")
        self.corpus_sha256 = sha256_file(corpus_path)
        self.doc_count = corpus.document_count
        self.bm25 = BM25Index(self._texts, k1=1.5, b=0.75)
        cfg = load_dense_encoder_config(
            root / "configs" / "models" / "dense_encoder.json",
            root / "configs" / "protocol_v1.json")
        snap = verify_model_snapshot(root, cfg, verify_remote=False)
        self._dense_config = cfg
        self._encoder = HfLocalEncoder(snapshot_dir=_snapshot_dir_from_record(snap),
                                       config=cfg, device="cpu")
        self.index = ExactDenseIndex.load(root / "artifacts" / "indexes" / "scifact"
                                          / "bge-base-en-v1.5__a5beb1e3")
        self.model_revision = cfg.revision

    def _require_top_k(self, top_k: Any) -> int:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
            raise ServiceError(f"top_k must be an integer in [1,100], got {top_k!r}")
        return top_k

    def _paper(self, doc_id: str) -> dict[str, Any]:
        if doc_id not in self._texts:
            raise ServiceError(f"Unknown document: {doc_id}")
        # A missing title is recorded missing data (rendered downstream as null,
        # never a fabricated value); doc_id presence is enforced via _texts above.
        title = self._titles.get(doc_id, "")
        text = self._texts[doc_id]
        abstract = text[len(title) + 1:] if title and text.startswith(title + " ") else text
        return {"doc_id": doc_id, "title": title or None,
                "abstract": abstract or None, "year": None, "doi": None,
                "snapshot": SNAPSHOT_ID}

    def search(self, query: str, method: str = "bm25", top_k: int = 10) -> dict[str, Any]:
        from scholargraph.retrieval.bm25 import BM25EmptyQueryError, tokenize
        if not isinstance(query, str) or not query.strip():
            raise ServiceError("Empty query text")
        if method not in ("bm25", "dense", "hybrid"):
            raise ServiceError(f"Unknown method: {method}")
        top_k = self._require_top_k(top_k)
        if not tokenize(query):
            raise ServiceError("Query has zero tokens under the protocol tokenizer")
        method_id = METHOD_IDS[method]
        if method == "bm25":
            hits = self.bm25.rank(query, top_k=top_k)
            rows = [{"doc_id": d, "score": s, "method": METHOD_IDS["bm25"]} for d, s in hits]
        elif method == "dense":
            vec = self._encoder.encode(apply_query_prefix([query], self._dense_config.prefix))[0]
            hits = self.index.search(vec, top_k=top_k)
            rows = [{"doc_id": d, "score": s, "method": METHOD_IDS["dense"]} for d, s in hits]
        else:
            b = self.bm25.rank(query, top_k=100)
            vec = self._encoder.encode(apply_query_prefix([query], self._dense_config.prefix))[0]
            d = self.index.search(vec, top_k=100)
            if b and d:
                fused = rrf_fuse([x[0] for x in b], [x[0] for x in d])[:top_k]
                rows = [{"doc_id": r["doc_id"], "score": r["rrf"],
                         "method": METHOD_IDS["hybrid"]} for r in fused]
                method_id = METHOD_IDS["hybrid"]
            elif d:
                # Lexical side empty (e.g. zero token overlap, common for
                # Vietnamese queries): fall back to the dense order, labelled
                # honestly instead of failing. rrf_fuse itself stays strict.
                rows = [{"doc_id": doc, "score": s,
                         "method": METHOD_IDS["dense"] + "+hybrid-fallback-lexical-empty"}
                        for doc, s in d[:top_k]]
                method_id = METHOD_IDS["hybrid"] + "+fallback-dense-only"
            elif b:
                rows = [{"doc_id": doc, "score": s,
                         "method": METHOD_IDS["bm25"] + "+hybrid-fallback-dense-empty"}
                        for doc, s in b[:top_k]]
                method_id = METHOD_IDS["hybrid"] + "+fallback-lexical-only"
            else:
                rows = []
                method_id = METHOD_IDS["hybrid"] + "+both-sides-empty"
        for r in rows:
            paper = self._paper(r["doc_id"])
            r["title"] = paper["title"]
            abs_ = paper["abstract"] or ""
            r["snippet"] = (abs_[:200] + "…") if len(abs_) > 200 else (abs_ or None)
        return {"query": query, "method": method_id, "snapshot": SNAPSHOT_ID,
                "results": rows}

    def paper(self, doc_id: str) -> dict[str, Any]:
        return self._paper(doc_id)

    def recommend(self, doc_id: str, top_k: int = 10) -> dict[str, Any]:
        top_k = self._require_top_k(top_k)
        if doc_id not in self._texts:
            raise ServiceError(f"Unknown document: {doc_id}")
        import numpy as np
        idx = self.index.doc_ids.index(doc_id)
        vec = np.asarray(self.index.matrix[idx], dtype=np.float32)
        hits = self.index.search(vec, top_k=top_k + 1,
                                 exclude_doc_ids=frozenset({doc_id}))[:top_k]
        return {"doc_id": doc_id, "method": METHOD_IDS["recommend"],
                "snapshot": SNAPSHOT_ID,
                "results": [{"doc_id": d, "score": s, "title": self._titles.get(d) or None,
                             "snippet": self._snippet(d)} for d, s in hits]}

    def _snippet(self, doc_id: str) -> str | None:
        paper = self._paper(doc_id)
        abs_ = paper["abstract"] or ""
        return ((abs_[:200] + "…") if len(abs_) > 200 else (abs_ or None))

    def search_filter(self, query: str, method: str, top_k: int,
                      title_must_contain: str | None = None) -> dict[str, Any]:
        """Search with an optional title substring filter (real filtering)."""
        res = self.search(query, method, 100 if title_must_contain else top_k)
        if title_must_contain:
            needle = title_must_contain.casefold()
            res["results"] = [r for r in res["results"]
                              if needle in (self._titles.get(r["doc_id"]) or "").casefold()][:top_k]
            res["filter"] = {"title_must_contain": title_must_contain}
        return res
