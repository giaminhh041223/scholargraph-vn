"""ScholarGraph VN — Abstract interfaces and contracts for data access and evaluation boundaries.

Following Research Protocol v1 (docs/RESEARCH_PROTOCOL.md, configs/protocol_v1.json):
- Rankers are strictly forbidden from receiving relevance judgments (qrels),
  held-out edges, or any test-label derived features.
- Evaluators are the sole components authorized to read qrels alongside run outputs.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence


FORBIDDEN_RELEVANCE_KEYS: FrozenSet[str] = frozenset({
    "qrels",
    "labels",
    "ground_truth",
    "heldout_edges",
    "test_labels",
    "heldout_positive_counts",
    "human_labels",
})


class DataLeakageError(Exception):
    """Raised when relevance labels (qrels) or held-out test data are passed to a ranker."""


class BaseRanker(ABC):
    """Base interface for all retrieval and ranking components in ScholarGraph VN.
    
    Enforces the Template Method Pattern:
    - Public method `rank()` performs strict data leakage checks before delegating.
    - Subclasses MUST implement internal hook `_rank()`, not override `rank()`.
    """

    def __init__(self, **kwargs: Any) -> None:
        for key in kwargs:
            if key.lower() in FORBIDDEN_RELEVANCE_KEYS:
                raise DataLeakageError(
                    f"Ranker constructor received forbidden relevance data ('{key}'). "
                    "Rankers must not access ground truth labels or held-out evaluation edges!"
                )

    def rank(
        self,
        query: Any,
        candidate_ids: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Public entry point for ranking candidates for a query.
        
        Strictly inspects parameters for forbidden ground truth keys before
        delegating to the internal `_rank()` implementation hook.

        Raises:
            DataLeakageError: If any forbidden relevance key is passed.
        """
        for key in kwargs:
            if key.lower() in FORBIDDEN_RELEVANCE_KEYS:
                raise DataLeakageError(
                    f"Ranker.rank() received forbidden relevance data ('{key}'). "
                    "Rankers must not access ground truth labels or held-out evaluation edges!"
                )
        return self._rank(query=query, candidate_ids=candidate_ids, **kwargs)

    @abstractmethod
    def _rank(
        self,
        query: Any,
        candidate_ids: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Internal ranking implementation hook to be overridden by subclasses."""


class BaseEvaluator(ABC):
    """Base interface for evaluation components in ScholarGraph VN.
    
    Evaluators compare system rankings (runs) against authoritative qrels
    under frozen protocol specifications.
    """

    @abstractmethod
    def evaluate(
        self,
        runs: Mapping[str, Any],
        qrels: Mapping[str, Mapping[str, int]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Compute evaluation metrics across queries.
        
        Args:
            runs: Mapping from query_id to RankingResult or list of ranked items.
            qrels: Mapping from query_id to {doc_id: relevance_score}.
            **kwargs: Additional evaluation arguments.
        """
