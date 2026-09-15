"""ScholarGraph VN — Abstract interfaces and contracts for data access and evaluation boundaries.

Following Research Protocol v1:
- Rankers are strictly forbidden from receiving relevance judgments (qrels),
  held-out edges, or any test-label derived features.
- Evaluators are the sole components authorized to read qrels alongside run outputs.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional, Sequence


class DataLeakageError(Exception):
    """Raised when relevance labels (qrels) or held-out test data are passed to a ranker."""


class BaseRanker(ABC):
    """Base interface for all retrieval and ranking components in ScholarGraph VN.
    
    A ranker may accept queries, eligible candidate pools, corpus text, and permitted
    observed graph edges. It MUST NEVER accept qrels or ground truth relevance labels.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "qrels" in kwargs or "labels" in kwargs:
            raise DataLeakageError(
                "Ranker constructor received forbidden relevance data ('qrels' or 'labels'). "
                "Rankers must not access ground truth labels!"
            )

    @abstractmethod
    def rank(
        self,
        query: Any,
        candidate_ids: Optional[Sequence[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Produce a ranked list of candidates for a given query.
        
        Args:
            query: Query instance.
            candidate_ids: Optional restricted universe of eligible document IDs.
            **kwargs: Extra non-privileged ranking parameters.

        Raises:
            DataLeakageError: If 'qrels' or 'labels' are present in kwargs.
        """
        if "qrels" in kwargs or "labels" in kwargs:
            raise DataLeakageError(
                "Ranker.rank() received forbidden relevance data ('qrels' or 'labels'). "
                "Rankers must not access ground truth labels!"
            )


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
