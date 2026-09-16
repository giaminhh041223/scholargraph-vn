"""Audited retrieval metrics for Research Protocol v1, section 6.1.

All inputs are audited before any aggregation. The locked query list determines
the macro denominator, including queries with absent runs or no positive qrels.
This evaluator consumes judgments; it must never be used as a ranker feature.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from scholargraph.data.interfaces import BaseEvaluator
from scholargraph.data.schemas import Qrel, RankedDocument, RankingResult

EVALUATOR_VERSION = "sg008-1.0.0"
METRIC_NAMES = ("nDCG@10", "Recall@100", "MRR@10", "MAP@100", "P@5")


def _check_id(value: Any, context: str) -> str:
    # Reject rather than normalize IDs at the evaluation boundary: normalization
    # here could silently merge documents or misalign the frozen split.
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ValueError(f"{context}: expected a nonempty ID without whitespace.")
    return value


def _id_set(values: Collection[str], context: str) -> set[str]:
    if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Collection):
        raise ValueError(f"{context}: expected a collection of IDs.")
    result = {_check_id(value, context) for value in values}
    if len(result) != len(values):
        raise ValueError(f"{context}: duplicate IDs.")
    return result


def _judgments(
    qrels: Mapping[str, Mapping[str, int]] | Sequence[Qrel],
    query_set: set[str],
    corpus: set[str],
) -> dict[str, dict[str, int]]:
    normalized: dict[str, dict[str, int]] = {qid: {} for qid in query_set}

    def add(qid: str, doc_id: str, score: int) -> None:
        _check_id(qid, "qrels query")
        _check_id(doc_id, "qrels document")
        if qid not in query_set:
            raise ValueError(f"Qrels query outside locked split: {qid}.")
        if doc_id not in corpus:
            raise ValueError(f"Qrel document outside corpus universe: {doc_id}.")
        if type(score) is not int or score not in (0, 1, 2):
            raise ValueError("Qrel relevance must be an integer 0, 1 or 2.")
        if doc_id in normalized[qid]:
            raise ValueError(f"Duplicate or conflicting qrel: {qid}/{doc_id}.")
        normalized[qid][doc_id] = score

    if isinstance(qrels, Mapping):
        for qid, docs in qrels.items():
            _check_id(qid, "qrels query")
            if qid not in query_set:
                raise ValueError(f"Qrels query outside locked split: {qid}.")
            if not isinstance(docs, Mapping):
                raise ValueError("Qrels values must be document-to-grade mappings.")
            for doc_id, score in docs.items():
                add(qid, doc_id, score)
    elif isinstance(qrels, Sequence) and not isinstance(qrels, (str, bytes)):
        for qrel in qrels:
            if not isinstance(qrel, Qrel):
                raise ValueError("Qrel sequence must contain Qrel objects.")
            add(qrel.query_id, qrel.doc_id, qrel.score)
    else:
        raise ValueError("Qrels must be a mapping or a sequence of Qrel objects.")
    return normalized


def _score_query(doc_ids: list[str], qrels: Mapping[str, int]) -> dict[str, float]:
    positives = sum(rel >= 1 for rel in qrels.values())
    ideal = math.fsum(
        rel / math.log2(rank + 1)
        for rank, rel in enumerate(sorted(qrels.values(), reverse=True)[:10], 1)
    )
    dcg = math.fsum(
        qrels.get(doc_id, 0) / math.log2(rank + 1)
        for rank, doc_id in enumerate(doc_ids[:10], 1)
    )
    hits = 0
    precisions = []
    for rank, doc_id in enumerate(doc_ids[:100], 1):
        if qrels.get(doc_id, 0) >= 1:
            hits += 1
            precisions.append(hits / rank)
    reciprocal_rank = next(
        (1.0 / rank for rank, doc_id in enumerate(doc_ids[:10], 1)
         if qrels.get(doc_id, 0) >= 1),
        0.0,
    )
    return {
        "nDCG@10": dcg / ideal if ideal else 0.0,
        "Recall@100": hits / positives if positives else 0.0,
        "MRR@10": reciprocal_rank,
        "MAP@100": math.fsum(precisions) / positives if positives else 0.0,
        "P@5": sum(qrels.get(doc_id, 0) >= 1 for doc_id in doc_ids[:5]) / 5.0,
    }


class ProtocolEvaluator(BaseEvaluator):
    """Compute the five fixed metrics, with explicit split/universe boundaries.

    Rankings must already follow score descending / document ID ascending order.
    No invalid candidate is silently removed and no query is dropped from macro.
    ``eligible_ids`` is the full eligible universe per query, never just C100.
    Track B requires it and a source-paper mapping to enforce explicit self policy.
    Track A also forbids literal identical query/document IDs (BEIR convention).
    Track C uses pooled metric names. Duplicate ingestion must be audited before
    constructing dict qrels; passing Qrel rows here also detects duplicate pairs.
    """

    def evaluate(
        self,
        runs: Mapping[str, RankingResult],
        qrels: Mapping[str, Mapping[str, int]] | Sequence[Qrel],
        *,
        query_ids: Sequence[str],
        corpus_ids: Collection[str],
        eligible_ids: Mapping[str, Collection[str]] | None = None,
        query_document_ids: Mapping[str, str] | None = None,
        track: str = "A",
    ) -> dict[str, Any]:
        if track not in ("A", "B", "C"):
            raise ValueError("track must be A, B or C.")
        if not isinstance(query_ids, Sequence):
            raise ValueError("query_ids must be an explicit sequence of locked query IDs.")
        query_set = _id_set(query_ids, "locked query split")
        if not query_set:
            raise ValueError("Locked query split must not be empty.")
        corpus = _id_set(corpus_ids, "corpus universe")
        if not isinstance(runs, Mapping):
            raise ValueError("Runs must map query IDs to RankingResult objects.")
        if any(_check_id(qid, "run query") not in query_set for qid in runs):
            raise ValueError("Run query outside locked split.")

        if eligible_ids is not None:
            if not isinstance(eligible_ids, Mapping) or set(eligible_ids) != query_set:
                raise ValueError("eligible_ids must cover exactly the locked query split.")
            eligible = {qid: _id_set(ids, f"eligible universe {qid}")
                        for qid, ids in eligible_ids.items()}
            if any(not ids <= corpus for ids in eligible.values()):
                raise ValueError("Eligible document outside corpus universe.")
        else:
            eligible = dict.fromkeys(query_set, corpus)

        if query_document_ids is None:
            sources: Mapping[str, str] = {}
        elif not isinstance(query_document_ids, Mapping):
            raise ValueError("query_document_ids must map query IDs to source document IDs.")
        else:
            sources = dict(query_document_ids)
        if any(_check_id(qid, "source query") not in query_set for qid in sources):
            raise ValueError("Source mapping query outside locked split.")
        if any(_check_id(doc_id, "source document") not in corpus for doc_id in sources.values()):
            raise ValueError("Source document outside corpus universe.")
        if track == "B" and (eligible_ids is None or set(sources) != query_set):
            raise ValueError("Track B requires full eligible_ids and query_document_ids mappings.")
        judgments = _judgments(qrels, query_set, corpus)

        # Rebuild a snapshot through schema validation. Frozen Pydantic models can
        # still contain mutable lists, and model_construct can bypass validation.
        ordered: dict[str, list[str]] = {}
        for qid in sorted(query_set):
            source = sources.get(qid)
            forbidden = {source} if source is not None else set()
            if track == "A":
                forbidden.add(qid)
            for doc_id, rel in judgments[qid].items():
                if rel >= 1 and (doc_id not in eligible[qid] or doc_id in forbidden):
                    raise ValueError(f"Positive qrel outside eligible universe or self-match: {qid}/{doc_id}.")
            if qid in runs:
                result = runs[qid]
                if not isinstance(result, RankingResult):
                    raise ValueError("Each run must be a RankingResult.")
                _check_id(result.query_id, "ranking query")
                for item in result.candidates:
                    if not isinstance(item, RankedDocument):
                        raise ValueError("Ranking candidates must be RankedDocument objects.")
                    _check_id(item.doc_id, "ranked document")
                result = RankingResult.model_validate(result.model_dump())
                if result.query_id != qid:
                    raise ValueError("Run mapping key does not match RankingResult.query_id.")
                ordered[qid] = [_check_id(item.doc_id, "ranked document") for item in result.candidates]
                for doc_id in ordered[qid]:
                    if doc_id not in eligible[qid] or doc_id in forbidden:
                        raise ValueError(f"Ranked document outside eligible universe or self-match: {qid}/{doc_id}.")
            else:
                ordered[qid] = []

        names = {name: name for name in METRIC_NAMES}
        if track == "C":
            names.update({"Recall@100": "pooled Recall@100", "MAP@100": "pooled MAP@100"})
        per_query = {
            qid: {names[name]: value for name, value in _score_query(ids, judgments[qid]).items()}
            for qid, ids in ordered.items()
        }
        aggregate = {
            name: math.fsum(row[name] for row in per_query.values()) / len(query_set)
            for name in names.values()
        }
        return {
            "evaluator_version": EVALUATOR_VERSION,
            "track": track,
            "per_query": per_query,
            "aggregate": aggregate,
            "audit": {
                "query_count": len(query_set),
                "no_positive_qrels_count": sum(not any(rel >= 1 for rel in row.values())
                                               for row in judgments.values()),
                "missing_ranking_count": len(query_set - set(runs)),
                # Explicitly empty rankings only; missing rankings counted above.
                "empty_ranking_count": sum(not ordered[qid] for qid in runs),
                "unjudged_counts": {qid: sum(doc_id not in judgments[qid] for doc_id in ids)
                                    for qid, ids in ordered.items()},
                "returned_counts": {qid: len(ids) for qid, ids in ordered.items()},
                "judged_zero_counts": {qid: sum(judgments[qid].get(doc_id) == 0 for doc_id in ids)
                                       for qid, ids in ordered.items()},
            },
        }
