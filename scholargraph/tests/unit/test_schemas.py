"""Unit tests for ScholarGraph VN data schemas, interfaces, and boundary contracts.

Verifies acceptance criteria for SG-006 and addresses Codex review findings (F1-F5):
1. Validation of Paper, CitationEdge, Query, Qrel, RankedDocument, RankingResult, RunManifest.
2. Rejection of invalid IDs, nonfinite scores, out-of-range years, and self-loop citations.
3. Strict enforcement that Ranker does not accept qrels/labels via Template Method Pattern (F2).
4. Correct handling of namespace IDs and null policies (no median imputation for year, empty abstract).
5. Canonical ordering validation on direct init/deserialize of RankingResult (F4).
6. CitationEdge whitespace trimming, non-empty ID and year validation (F3).
7. Strictly decreasing scores (N - rank + 1) in TREC serialization to prevent tie-inversion (F1).
8. Synthetic provenance flag support in RunManifest and synthetic fixtures (F5).
"""

import json
import math
from pathlib import Path
import pytest
from pydantic import ValidationError

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


class TestPaperSchema:
    def test_valid_paper(self):
        p = Paper(
            id="openalex:W1001",
            doi="10.1000/182",
            title="Scientific Information Retrieval",
            abstract="A study on hybrid retrieval.",
            year=2021,
            authors=["John Doe", "Jane Roe"],
            venue="SIGIR",
            citation_count=10,
            references=["openalex:W1002"],
            synthetic=False,
        )
        assert p.id == "openalex:W1001"
        assert p.doi == "10.1000/182"
        assert p.text_content() == "Scientific Information Retrieval A study on hybrid retrieval."

    def test_null_policy_defaults(self):
        # Missing abstract defaults to empty string; missing year stays None (no median imputation)
        p = Paper(
            id="doc1",
            title="Paper without Abstract or Year",
            abstract=None,
            year=None,
        )
        assert p.abstract == ""
        assert p.year is None
        assert p.doi is None
        assert p.text_content() == "Paper without Abstract or Year"

    def test_reject_empty_id_or_title(self):
        with pytest.raises(ValidationError):
            Paper(id="   ", title="Title")
        with pytest.raises(ValidationError):
            Paper(id="doc1", title="")

    def test_reject_out_of_range_year(self):
        with pytest.raises(ValidationError, match="outside plausible scientific range"):
            Paper(id="doc1", title="Old Paper", year=1850)
        with pytest.raises(ValidationError, match="outside plausible scientific range"):
            Paper(id="doc2", title="Future Paper", year=2150)

    def test_doi_validation(self):
        assert validate_doi("10.1145/3397271.3401075") is True
        assert validate_doi("not_a_doi") is False
        assert validate_doi(None) is False

        with pytest.raises(ValidationError, match="Invalid DOI format"):
            Paper(id="doc1", title="Title", doi="invalid_doi_format")


class TestCitationEdgeSchema:
    def test_valid_edge(self):
        edge = CitationEdge(source_id="paper_a", target_id="paper_b", year=2020)
        assert edge.source_id == "paper_a"
        assert edge.target_id == "paper_b"
        assert edge.year == 2020

    def test_whitespace_normalization(self):
        # F3: source_id and target_id are stripped
        edge = CitationEdge(source_id="  paper_a  ", target_id="  paper_b  ", year=2020)
        assert edge.source_id == "paper_a"
        assert edge.target_id == "paper_b"

    def test_reject_empty_or_whitespace_edge_ids(self):
        # F3: whitespace-only strings must be rejected
        with pytest.raises(ValidationError, match="must not be empty or whitespace"):
            CitationEdge(source_id="   ", target_id="b")
        with pytest.raises(ValidationError, match="must not be empty or whitespace"):
            CitationEdge(source_id="a", target_id="   ")

    def test_reject_invalid_edge_year(self):
        # F3: edge year must satisfy [1900, 2100]
        with pytest.raises(ValidationError, match="outside plausible scientific range"):
            CitationEdge(source_id="a", target_id="b", year=9999)
        with pytest.raises(ValidationError, match="outside plausible scientific range"):
            CitationEdge(source_id="a", target_id="b", year=1800)

    def test_reject_self_loop(self):
        with pytest.raises(ValidationError, match="Self-loop citation is prohibited"):
            CitationEdge(source_id="paper_a", target_id="paper_a")
        with pytest.raises(ValidationError, match="Self-loop citation is prohibited"):
            CitationEdge(source_id="  paper_a  ", target_id="paper_a")


class TestQuerySchema:
    def test_valid_query(self):
        q = Query(id="q1", text="hybrid retrieval", language="en", metadata={"split": "dev"})
        assert q.id == "q1"
        assert q.language == "en"

    def test_reject_empty_id_or_text(self):
        with pytest.raises(ValidationError):
            Query(id="   ", text="valid text")
        with pytest.raises(ValidationError):
            Query(id="q1", text="   ")


class TestQrelSchema:
    def test_valid_qrel(self):
        q = Qrel(query_id="q1", doc_id="d1", score=2)
        assert q.score == 2

    def test_reject_invalid_scores(self):
        with pytest.raises(ValidationError):
            Qrel(query_id="q1", doc_id="d1", score=-1)
        with pytest.raises(ValidationError):
            Qrel(query_id="q1", doc_id="d1", score=3)


class TestRankingSchemas:
    def test_reject_nonfinite_score(self):
        with pytest.raises(ValidationError, match="finite float"):
            RankedDocument(doc_id="d1", score=float("nan"), rank=1)
        with pytest.raises(ValidationError, match="finite float"):
            RankedDocument(doc_id="d1", score=float("inf"), rank=1)

    def test_reject_empty_query_id(self):
        # F3: RankingResult rejects whitespace-only query_id
        c = RankedDocument(doc_id="d1", score=0.9, rank=1)
        with pytest.raises(ValidationError, match="query_id must not be empty or whitespace"):
            RankingResult(query_id="   ", candidates=[c])

    def test_reject_duplicate_candidates_in_ranking(self):
        c1 = RankedDocument(doc_id="d1", score=0.9, rank=1)
        c2 = RankedDocument(doc_id="d1", score=0.8, rank=2)
        with pytest.raises(ValidationError, match="Duplicate doc_id"):
            RankingResult(query_id="q1", candidates=[c1, c2])

    def test_reject_inconsistent_ranks(self):
        c1 = RankedDocument(doc_id="d1", score=0.9, rank=1)
        c2 = RankedDocument(doc_id="d2", score=0.8, rank=3)  # expected 2
        with pytest.raises(ValidationError, match="Inconsistent rank"):
            RankingResult(query_id="q1", candidates=[c1, c2])

    def test_reject_direct_noncanonical_score_order(self):
        # F4: Direct initialization with non-descending scores must raise ValidationError
        c1 = RankedDocument(doc_id="d1", score=0.1, rank=1)
        c2 = RankedDocument(doc_id="d2", score=0.9, rank=2)
        with pytest.raises(ValidationError, match="Candidates must be ordered by score descending"):
            RankingResult(query_id="q1", candidates=[c1, c2])

    def test_reject_direct_noncanonical_tie_order(self):
        # F4: Direct initialization with equal scores but non-ascending doc_id must raise ValidationError
        # 'doc_b' then 'doc_a' is invalid; 'doc_a' must precede 'doc_b'
        c1 = RankedDocument(doc_id="doc_b", score=0.5, rank=1)
        c2 = RankedDocument(doc_id="doc_a", score=0.5, rank=2)
        with pytest.raises(ValidationError, match="Tied candidates must be broken by doc_id ascending"):
            RankingResult(query_id="q1", candidates=[c1, c2])

    def test_create_sorted_canonical_tie_breaking(self):
        # Tied scores: doc_b and doc_a have identical score 0.500.
        # Canonical order: score desc, then doc_id asc (Unicode code points: 'doc_a' < 'doc_b')
        raw_candidates = [
            ("doc_b", 0.5, None),
            ("doc_c", 0.9, {"component": "bm25"}),
            ("doc_a", 0.5, None),
            ("doc_d", 0.1, None),
        ]
        result = RankingResult.create_sorted(query_id="q1", scored_candidates=raw_candidates)

        assert [c.doc_id for c in result.candidates] == ["doc_c", "doc_a", "doc_b", "doc_d"]
        assert [c.rank for c in result.candidates] == [1, 2, 3, 4]
        assert result.candidates[0].score == 0.9
        assert result.candidates[1].score == 0.5
        assert result.candidates[2].score == 0.5
        assert result.candidates[3].score == 0.1

    def test_to_trec_lines_strictly_decreasing_scores(self):
        # F1: Equal or near-tied scores must produce strictly decreasing TREC scores (N - rank + 1)
        # to prevent trec_eval comparator from inverting tie breaks.
        raw_candidates = [
            ("a", 0.50000004, None),
            ("z", 0.50000003, None),
        ]
        result = RankingResult.create_sorted("q1", raw_candidates)

        # Default strictly_decreasing_scores=True:
        # Candidate at rank 1 gets score N - 1 + 1 = 2.0
        # Candidate at rank 2 gets score N - 2 + 1 = 1.0
        trec_lines = result.to_trec_lines("scholargraph")
        assert len(trec_lines) == 2
        assert trec_lines[0] == "q1 Q0 a 1 2.000000 scholargraph"
        assert trec_lines[1] == "q1 Q0 z 2 1.000000 scholargraph"

        # Even with exactly equal raw scores:
        tied_candidates = [("doc_a", 0.5, None), ("doc_b", 0.5, None)]
        tied_result = RankingResult.create_sorted("q2", tied_candidates)
        tied_trec = tied_result.to_trec_lines("scholargraph")
        assert tied_trec[0] == "q2 Q0 doc_a 1 2.000000 scholargraph"
        assert tied_trec[1] == "q2 Q0 doc_b 2 1.000000 scholargraph"


class TestRunManifestSchema:
    def test_valid_manifest(self):
        m = RunManifest(
            run_id="RUN-20260915-120000-bm25-scifact-dev",
            method="bm25",
            dataset="scifact",
            split="dev",
            config_hash="0123456789abcdef0123456789abcdef",
            parameters={"k1": 1.5, "b": 0.75},
            synthetic=False,
        )
        assert m.status == "PENDING"
        assert m.parameters["k1"] == 1.5
        assert m.synthetic is False

    def test_synthetic_flag(self):
        # F5: synthetic flag supported and validated
        m = RunManifest(
            run_id="RUN-20260915-120000-bm25-scifact-dev-synth",
            method="bm25",
            dataset="scifact",
            split="dev",
            config_hash="0123456789abcdef0123456789abcdef",
            synthetic=True,
        )
        assert m.synthetic is True

    def test_reject_invalid_run_id_pattern(self):
        with pytest.raises(ValidationError, match="Invalid run_id"):
            RunManifest(
                run_id="invalid_run_id",
                method="bm25",
                dataset="scifact",
                split="dev",
                config_hash="abcdef1234567890",
            )


class TestNamespaceUtilities:
    def test_parse_namespace_id(self):
        ns, raw = parse_namespace_id("openalex:W2741809807")
        assert ns == "openalex"
        assert raw == "W2741809807"

        ns, raw = parse_namespace_id("doc_without_prefix")
        assert ns == "default"
        assert raw == "doc_without_prefix"

    def test_reject_invalid_namespace_delimiters(self):
        # F3: Empty namespace or empty raw_id when ':' is used must be rejected
        with pytest.raises(ValueError, match="both namespace and raw_id must be non-empty"):
            parse_namespace_id(":")
        with pytest.raises(ValueError, match="both namespace and raw_id must be non-empty"):
            parse_namespace_id(" : ")
        with pytest.raises(ValueError, match="both namespace and raw_id must be non-empty"):
            parse_namespace_id(":raw_only")
        with pytest.raises(ValueError, match="both namespace and raw_id must be non-empty"):
            parse_namespace_id("namespace_only:")

    def test_make_canonical_id(self):
        canon = make_canonical_id("beir_scifact", "42")
        assert canon == "beir_scifact:42"

    def test_reject_empty_namespace(self):
        with pytest.raises(ValueError):
            make_canonical_id("", "42")


class PlainUncooperativeRanker(BaseRanker):
    """Subclass that implements only _rank hook and does NOT call super in its ranking logic (F2)."""

    def _rank(self, query, candidate_ids=None, **kwargs):
        # Plain implementation without super calls
        candidates = [("d1", 0.9, None), ("d2", 0.8, None)]
        return RankingResult.create_sorted(query.id, candidates)


class TestRankerInterfaceProtection:
    def test_ranker_refuses_forbidden_keys_in_constructor(self):
        # F2: Test forbidden relevance keys at construction
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            PlainUncooperativeRanker(qrels={"q1": {"d1": 1}})
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            PlainUncooperativeRanker(heldout_edges=[("u", "v")])
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            PlainUncooperativeRanker(test_labels={"q1": {"d1": 1}})

    def test_ranker_refuses_forbidden_keys_in_rank_call(self):
        # F2: Even when subclass does not call super(), rank() template method intercepts forbidden keys
        ranker = PlainUncooperativeRanker()
        q = Query(id="q1", text="test")

        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            ranker.rank(query=q, qrels={"q1": {"d1": 1}})
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            ranker.rank(query=q, labels={"q1": {"d1": 1}})
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            ranker.rank(query=q, heldout_edges=[("u", "v")])
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            ranker.rank(query=q, ground_truth={"q1": {"d1": 1}})
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            ranker.rank(query=q, test_labels={"q1": {"d1": 1}})
        with pytest.raises(DataLeakageError, match="forbidden relevance data"):
            ranker.rank(query=q, human_labels={"q1": {"d1": 1}})

    def test_ranker_executes_normally_without_leakage(self):
        ranker = PlainUncooperativeRanker()
        q = Query(id="q1", text="safe query")
        res = ranker.rank(query=q, candidate_ids=["d1", "d2"])
        assert res.query_id == "q1"
        assert len(res.candidates) == 2


class TestSyntheticFixturesLoading:
    @pytest.fixture
    def fixtures_dir(self):
        return Path(__file__).resolve().parent.parent / "fixtures"

    def test_load_synthetic_papers(self, fixtures_dir):
        path = fixtures_dir / "synthetic_papers.jsonl"
        assert path.exists()

        papers = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    paper = Paper(**data)
                    assert paper.synthetic is True
                    papers.append(paper)

        assert len(papers) == 6
        # Test null policy coverage in fixtures
        p5 = next(p for p in papers if p.id == "synth:paper_005")
        assert p5.abstract == ""
        p6 = next(p for p in papers if p.id == "synth:paper_006")
        assert p6.year is None

    def test_load_synthetic_queries(self, fixtures_dir):
        path = fixtures_dir / "synthetic_queries.json"
        assert path.exists()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            queries = [Query(**item) for item in data]

        assert len(queries) == 3
        assert queries[2].language == "vi"

    def test_load_synthetic_qrels(self, fixtures_dir):
        path = fixtures_dir / "synthetic_qrels.json"
        assert path.exists()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            qrels = [Qrel(**item) for item in data]

        assert len(qrels) == 5
        assert all(q.score in (1, 2) for q in qrels)

    def test_load_synthetic_manifest(self, fixtures_dir):
        path = fixtures_dir / "synthetic_manifest.json"
        assert path.exists()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            manifest = RunManifest(**data)

        assert manifest.status == "COMPLETED"
        assert manifest.metrics["ndcg_at_10"] == 0.6850
        # F5: synthetic flag in fixture manifest
        assert manifest.synthetic is True
