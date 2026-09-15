"""ScholarGraph VN — Authoritative data models, schemas, and validators.

Compliant with Research Protocol v1 (docs/RESEARCH_PROTOCOL.md, configs/protocol_v1.json):
- Clear distinction between canonical Paper ID, DOI, Query ID, and Qrel Label.
- Strict validation of IDs, years, scores, self-loops, and ranking ties.
- Null policy: empty string for missing abstract; None for missing year (no median imputation).
- Synthetic flag policy: fixture data and synthetic runs marked with synthetic=True.
- TREC serialization: strictly decreasing order scores (N - rank + 1) per protocol §6.1.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# Standard DOI prefix regex pattern (e.g. 10.xxxx/yyyy)
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")

# Run ID pattern per protocol: RUN-YYYYMMDD-HHMMSS-method-dataset-split[-unique_suffix]
RUN_ID_PATTERN = re.compile(r"^RUN-\d{8}-\d{6}-[\w\-]+$")


def validate_doi(doi: Optional[str]) -> bool:
    """Check whether a given string matches standard DOI format."""
    if not doi:
        return False
    return bool(DOI_PATTERN.match(doi.strip()))


def parse_namespace_id(prefixed_id: str) -> Tuple[str, str]:
    """Parse a namespaced ID (e.g. 'openalex:W12345' or 'beir:scifact:doc1') into (namespace, raw_id).
    
    If no namespace delimiter ':' is present, defaults to namespace 'default'.
    Both namespace and raw_id must be non-empty and non-whitespace.
    """
    if not prefixed_id or not prefixed_id.strip():
        raise ValueError("ID must not be empty or whitespace.")
    prefixed_id = prefixed_id.strip()
    if ":" in prefixed_id:
        parts = prefixed_id.split(":", 1)
        ns = parts[0].strip()
        raw = parts[1].strip()
        if not ns or not raw:
            raise ValueError(
                f"Invalid namespaced ID '{prefixed_id}': both namespace and raw_id must be non-empty."
            )
        return ns, raw
    return "default", prefixed_id


def make_canonical_id(namespace: str, raw_id: str) -> str:
    """Format a canonical namespaced ID."""
    namespace = namespace.strip()
    raw_id = raw_id.strip()
    if not namespace or not raw_id:
        raise ValueError("Both namespace and raw_id must be non-empty.")
    return f"{namespace}:{raw_id}"


class Paper(BaseModel):
    """Academic paper entity representing a document in the corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., min_length=1, description="Canonical document ID")
    doi: Optional[str] = Field(default=None, description="Digital Object Identifier")
    title: str = Field(..., min_length=1, description="Paper title")
    abstract: str = Field(default="", description="Paper abstract. Missing abstracts default to empty string.")
    year: Optional[int] = Field(default=None, description="Publication year. Excluded from Track B if None; never imputed.")
    authors: List[str] = Field(default_factory=list, description="List of author names")
    venue: Optional[str] = Field(default=None, description="Publication venue or journal")
    citation_count: Optional[int] = Field(default=None, ge=0, description="Observed citation count")
    references: List[str] = Field(default_factory=list, description="List of cited canonical paper IDs")
    synthetic: bool = Field(default=False, description="True if synthetic fixture data")

    @field_validator("id", "title")
    @classmethod
    def check_non_empty_str(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field must not be empty or whitespace.")
        return s

    @field_validator("doi")
    @classmethod
    def check_doi_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if not validate_doi(s):
            raise ValueError(f"Invalid DOI format: '{s}'. Expected '10.xxxx/...'.")
        return s

    @field_validator("abstract", mode="before")
    @classmethod
    def normalize_abstract(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("year")
    @classmethod
    def validate_year_range(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if v < 1900 or v > 2100:
            raise ValueError(f"Year {v} is outside plausible scientific range [1900, 2100].")
        return v

    def text_content(self) -> str:
        """Combine title and abstract according to protocol §5.1: title + ' ' + abstract."""
        if self.abstract:
            return f"{self.title} {self.abstract}".strip()
        return self.title.strip()


class CitationEdge(BaseModel):
    """Directed citation relation from source (citing) to target (cited)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(..., min_length=1, description="Citing paper canonical ID")
    target_id: str = Field(..., min_length=1, description="Cited paper canonical ID")
    year: Optional[int] = Field(default=None, description="Source paper publication year for temporal cutoff")
    synthetic: bool = Field(default=False, description="True if synthetic fixture data")

    @field_validator("source_id", "target_id")
    @classmethod
    def check_non_empty_edge_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Edge paper ID must not be empty or whitespace.")
        return s

    @field_validator("year")
    @classmethod
    def validate_edge_year_range(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if v < 1900 or v > 2100:
            raise ValueError(f"Citation edge year {v} is outside plausible scientific range [1900, 2100].")
        return v

    @model_validator(mode="after")
    def validate_no_self_loop(self) -> CitationEdge:
        if self.source_id.strip() == self.target_id.strip():
            raise ValueError(f"Self-loop citation is prohibited: source '{self.source_id}' equals target.")
        return self


class Query(BaseModel):
    """Information need or search query entity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., min_length=1, description="Query ID")
    text: str = Field(..., min_length=1, description="Query text content")
    language: str = Field(default="en", description="Query language code (e.g. 'en', 'vi')")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata such as query family or split")
    synthetic: bool = Field(default=False, description="True if synthetic fixture query")

    @field_validator("id", "text")
    @classmethod
    def check_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field must not be empty or whitespace.")
        return s


class Qrel(BaseModel):
    """Ground truth relevance judgment between a query and a document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str = Field(..., min_length=1, description="Query ID")
    doc_id: str = Field(..., min_length=1, description="Canonical document ID")
    score: int = Field(..., ge=0, le=2, description="Relevance grade (0: irrelevant, 1: partially, 2: directly)")
    iteration: int = Field(default=0, ge=0, description="TREC iteration field, typically 0")
    annotator_id: Optional[str] = Field(default=None, description="Annotator identifier for Track C pooled judgments")
    synthetic: bool = Field(default=False, description="True if synthetic fixture qrel")

    @field_validator("query_id", "doc_id")
    @classmethod
    def check_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("ID must not be empty or whitespace.")
        return s


class RankedDocument(BaseModel):
    """Single document within a ranked candidate list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str = Field(..., min_length=1, description="Canonical document ID")
    score: float = Field(..., description="Finite ranking score")
    rank: int = Field(..., ge=1, description="1-based rank position")
    explanation: Optional[Dict[str, Any]] = Field(default=None, description="Component score attribution")

    @field_validator("doc_id")
    @classmethod
    def check_doc_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("doc_id must not be empty.")
        return s

    @field_validator("score")
    @classmethod
    def check_finite_score(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"Ranking score must be a finite float; received {v}.")
        return v


class RankingResult(BaseModel):
    """Ordered ranking result for a single query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str = Field(..., min_length=1, description="Query ID")
    candidates: List[RankedDocument] = Field(default_factory=list, description="Ordered candidate list")

    @field_validator("query_id")
    @classmethod
    def check_query_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("query_id must not be empty or whitespace.")
        return s

    @model_validator(mode="after")
    def validate_unique_docs_and_canonical_order(self) -> RankingResult:
        seen = set()
        for idx, item in enumerate(self.candidates):
            if item.doc_id in seen:
                raise ValueError(
                    f"Duplicate doc_id '{item.doc_id}' detected at candidate index {idx} "
                    f"for query '{self.query_id}'."
                )
            seen.add(item.doc_id)
            if item.rank != idx + 1:
                raise ValueError(
                    f"Inconsistent rank at index {idx}: item rank is {item.rank}, expected {idx + 1}."
                )
            # Enforce canonical ordering on direct initialization / deserialization:
            # 1. score descending
            # 2. doc_id ascending (Unicode code points)
            if idx > 0:
                prev = self.candidates[idx - 1]
                if item.score > prev.score:
                    raise ValueError(
                        f"Non-canonical order at index {idx}: score {item.score} > previous score {prev.score}. "
                        "Candidates must be ordered by score descending."
                    )
                if item.score == prev.score and item.doc_id <= prev.doc_id:
                    raise ValueError(
                        f"Non-canonical tie order at index {idx}: tied score {item.score} but doc_id '{item.doc_id}' "
                        f"<= previous doc_id '{prev.doc_id}'. Tied candidates must be broken by doc_id ascending."
                    )
        return self

    @classmethod
    def create_sorted(
        cls,
        query_id: str,
        scored_candidates: Sequence[Tuple[str, float, Optional[Dict[str, Any]]]],
    ) -> RankingResult:
        """Factory method to construct a canonical RankingResult from raw (doc_id, score, explanation) tuples.
        
        Canonical sort order per Research Protocol §5.1 / §6.1:
        1. score descending
        2. doc_id ascending by Unicode code points (lexicographical)
        """
        sorted_items = sorted(
            scored_candidates,
            key=lambda item: (-item[1], item[0]),
        )
        ranked = [
            RankedDocument(
                doc_id=doc_id,
                score=score,
                rank=idx + 1,
                explanation=expl,
            )
            for idx, (doc_id, score, expl) in enumerate(sorted_items)
        ]
        return cls(query_id=query_id, candidates=ranked)

    def to_trec_lines(
        self,
        run_id: str = "scholargraph",
        strictly_decreasing_scores: bool = True,
    ) -> List[str]:
        """Serialize ranking to standard TREC run format: query_id Q0 doc_id rank score run_id.
        
        Per Research Protocol §6.1 and configs/protocol_v1.json:
        trec_eval sorts by score descending and breaks ties by doc_id descending, which reverses
        our canonical doc_id ascending tie-breaker.
        When strictly_decreasing_scores=True (default), output score is strictly decreasing:
            score = N - rank + 1
        This completely prevents ties in TREC files and guarantees trec_eval respects the exact
        canonical ordering of RankingResult. Raw scores are preserved separately in the artifact.
        """
        n_candidates = len(self.candidates)
        lines = []
        for doc in self.candidates:
            if strictly_decreasing_scores:
                trec_score = float(n_candidates - doc.rank + 1)
            else:
                trec_score = doc.score
            lines.append(f"{self.query_id} Q0 {doc.doc_id} {doc.rank} {trec_score:.6f} {run_id}")
        return lines


class RunManifest(BaseModel):
    """Metadata manifest documenting an experimental run's provenance and reproducibility."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(..., min_length=1, description="Canonical run identifier")
    protocol_version: str = Field(default="1.0.0", description="Research protocol version")
    method: str = Field(..., min_length=1, description="Method name, e.g. bm25, dense, hybrid_rrf, hybrid_ppr")
    dataset: str = Field(..., min_length=1, description="Dataset name, e.g. scifact, scidocs, openalex")
    split: str = Field(..., min_length=1, description="Split evaluated, e.g. dev, test")
    status: str = Field(default="PENDING", pattern="^(PENDING|RUNNING|COMPLETED|FAILED)$")
    config_hash: str = Field(..., min_length=8, description="SHA-256 hash of configuration")
    data_hash: Optional[str] = Field(default=None, description="Hash of dataset and split")
    split_hash: Optional[str] = Field(default=None, description="Hash of train/dev/test split definition")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Hyperparameters and run options")
    hardware_info: Dict[str, Any] = Field(default_factory=dict, description="CPU/GPU and OS environment details")
    metrics: Optional[Dict[str, float]] = Field(default=None, description="Aggregate metric results")
    synthetic: bool = Field(default=False, description="True if synthetic fixture run; excluded from research tables")
    error_message: Optional[str] = Field(default=None, description="Failure details if status is FAILED")

    @field_validator("run_id")
    @classmethod
    def validate_run_id_pattern(cls, v: str) -> str:
        s = v.strip()
        if not RUN_ID_PATTERN.match(s):
            raise ValueError(
                f"Invalid run_id: '{s}'. Expected pattern 'RUN-YYYYMMDD-HHMMSS-method-dataset-split[-suffix]'."
            )
        return s
