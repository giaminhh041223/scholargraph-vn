"""SG-031 VN query manifest validation — structure, counts, split-family rule.

The manifest is an agent DRAFT pending human approval; these tests pin the
structural contract that the human gate approves (and that SG-032/SG-033 will
consume). Provenance rules (not derived from qrels docs) are recorded in the
manifest narrative and enforced by the human gate, not automatable here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# v1 (SG-031) and v2 (ADR-023, redrafted to match the OpenAlex corpus topics).
MANIFESTS = {
    "vn": PROJECT_ROOT / "data" / "annotations" / "vn_query_manifest.json",
    "vn2": PROJECT_ROOT / "data" / "annotations" / "v2" / "vn_query_manifest.json",
}


@pytest.fixture(scope="module", params=sorted(MANIFESTS))
def manifest(request) -> dict:
    path = MANIFESTS[request.param]
    if not path.is_file():
        pytest.fail(f"Missing VN query manifest: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["_ns"] = request.param
    return doc


def test_status_is_explicitly_approved(manifest):
    # Human gate satisfied 2026-09-17 (project owner approved all 30 queries
    # without edits via in-session question tool; recorded in provenance).
    assert manifest["status"] in ("approved_no_edits", "approved_with_edits")
    approval = manifest["provenance"]["human_approval"]
    assert approval and approval.get("approved_at") and approval.get("decision")
    assert "NOT derived from any qrels entry" in manifest["provenance"]["method"]


def test_counts_match_protocol(manifest):
    assert manifest["counts"] == {"dev": 10, "test": 20, "total": 30, "pilot_dev": 5}
    splits = [q["split"] for q in manifest["queries"]]
    assert splits.count("dev") == 10 and splits.count("test") == 20
    pilots = [q for q in manifest["queries"] if q["annotation_pilot"]]
    assert len(pilots) == 5 and all(q["split"] == "dev" for q in pilots)


def test_intent_families_do_not_span_splits(manifest):
    family_splits: dict[str, set[str]] = {}
    for q in manifest["queries"]:
        family_splits.setdefault(q["intent_family"], set()).add(q["split"])
    spanning = {f: s for f, s in family_splits.items() if len(s) > 1}
    assert not spanning, f"intent families spanning splits violate the protocol rule: {spanning}"


def test_query_ids_use_vn_namespace(manifest):
    ns = manifest["_ns"]
    for q in manifest["queries"]:
        qid = q["query_id"]
        assert qid == f"{ns}:{q['split']}:{qid.rsplit(':', 1)[1]}"
        # disjoint from BEIR qrels ID namespaces by construction
        assert not qid.startswith("beir:")


def test_every_query_has_text_and_domain(manifest):
    for q in manifest["queries"]:
        assert isinstance(q["text_vi"], str) and len(q["text_vi"].strip()) >= 15
        if manifest["_ns"] == "vn":
            assert q["topic_domain"] in ("biomed", "scientometrics")
        else:
            assert isinstance(q["topic_domain"], str) and q["topic_domain"]
        assert isinstance(q["intent_family"], str) and q["intent_family"]


def test_duplicate_text_rejected(manifest):
    texts = [q["text_vi"] for q in manifest["queries"]]
    assert len(texts) == len(set(texts)), "duplicate query text in manifest"
