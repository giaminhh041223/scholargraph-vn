"""Data schemas, interfaces, and boundary contracts for ScholarGraph VN."""

from scholargraph.data.interfaces import (
    BaseEvaluator,
    BaseRanker,
    DataLeakageError,
)
from scholargraph.data.schemas import (
    CitationEdge,
    Paper,
    Qrel,
    Query,
    RankedDocument,
    RankingResult,
    RunManifest,
    make_canonical_id,
    parse_namespace_id,
    validate_doi,
)

__all__ = [
    "BaseEvaluator",
    "BaseRanker",
    "DataLeakageError",
    "CitationEdge",
    "Paper",
    "Qrel",
    "Query",
    "RankedDocument",
    "RankingResult",
    "RunManifest",
    "make_canonical_id",
    "parse_namespace_id",
    "validate_doi",
]
