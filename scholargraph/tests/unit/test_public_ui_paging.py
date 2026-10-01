"""Synthetic, schema-validated pagination/race/identity regressions (EXT-07G)."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

from scholargraph.public_search.contracts import PaperRecord, SearchEnvelope, SearchRequest, SearchSnapshot, SourceResult
from scholargraph.public_search.fusion import fuse

ROOT = Path(__file__).resolve().parents[2]


def test_partial_paging_races_and_snapshot_identity(tmp_path):
    examples = json.loads((ROOT / "tests/fixtures/public_search/gemini/ux_examples.json").read_text(encoding="utf-8"))["examples"]
    base = examples["example_06_tt05_success_plus_failed_partial_failure_with_hits"]["envelope"]
    survivor = next(s for s in base["snapshot"]["source_results"] if s["status"] == "success")
    failed = next(s for s in base["snapshot"]["source_results"] if s["status"] == "failed")
    records = []
    for i in range(25):
        rec = copy.deepcopy(survivor["records"][0])
        rec.update(source_id=f"W{990000+i}", title=f"Synthetic audit paper {i+1}", doi=None, arxiv_id=None, landing_url=f"https://openalex.org/W{990000+i}")
        rec["missing_fields"] = sorted(set(rec["missing_fields"]) | {"doi", "arxiv_id"})
        for field in ("doi", "arxiv_id"):
            if field in rec["field_provenance"]:
                del rec["field_provenance"][field]
        for evidence in rec["field_provenance"].values():
            for row in evidence:
                row["source_id"] = rec["source_id"]
        records.append(PaperRecord.model_validate_json(json.dumps(rec)))
    request = SearchRequest(query="synthetic audit boundary", sources=["openalex", "arxiv"], top_k=25, cap_per_source=25, year_from=None, year_to=None, refresh=False)
    sr = copy.deepcopy(survivor)
    sr.update(records=[r.model_dump(mode="json") for r in records], source_total=25, truncated=False)
    sources = [SourceResult.model_validate_json(json.dumps(sr)), SourceResult.model_validate_json(json.dumps(failed))]
    snap = copy.deepcopy(base["snapshot"])
    snap.update(snapshot_id="audit-partial-25", request=request.model_dump(mode="json"), source_results=[s.model_dump(mode="json") for s in sources], fusion=fuse(sources, request).model_dump(mode="json"))
    partial = copy.deepcopy(base)
    partial["snapshot"] = SearchSnapshot.model_validate_json(json.dumps(snap)).model_dump(mode="json")
    partial = SearchEnvelope.model_validate_json(json.dumps(partial))
    empty = sources[1].model_dump(mode="json")
    empty.update(status="empty", error=None, source_total=0, truncated=False)
    sources[1] = SourceResult.model_validate_json(json.dumps(empty))
    snap.update(snapshot_id="audit-success-25", source_results=[s.model_dump(mode="json") for s in sources], fusion=fuse(sources, request).model_dump(mode="json"), overall="success")
    success = SearchEnvelope(schema_version=1, contract_version="1.0.0", overall="success", snapshot=SearchSnapshot.model_validate_json(json.dumps(snap)), errors=[], cached=False, stale=False)
    fixture = tmp_path / "envelopes.json"
    fixture.write_text(json.dumps({"synthetic": True, "partial": partial.model_dump(mode="json"), "success": success.model_dump(mode="json")}), encoding="utf-8")
    node = shutil.which("node")
    assert node is not None, "Node.js is required for executable UI regression"
    result = subprocess.run([node, str(ROOT / "tests/fixtures/public_search/gemini/ui/paging_test_runner.js"), str(fixture)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PAGING REGRESSION PASS: 5 cases" in result.stdout
