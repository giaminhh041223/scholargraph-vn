"""SG-032 cross-lingual component tests — cache, manifest gating, diagnostics.

Model-dependent translation (first run) is exercised offline via a
pre-populated cache; the rejection paths need no model at all.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

cross_lingual = importlib.import_module("scholargraph.retrieval.cross_lingual")


@pytest.fixture()
def approved_manifest(tmp_path: Path) -> Path:
    manifest = {
        "schema_version": 1,
        "status": "approved_no_edits",
        "provenance": {"human_approval": {"decision": "Duyệt nguyên bản 30 query",
                                          "approved_at": "2026-09-17T23:55:00+07:00"},
                       "method": "topic taxonomy; NOT derived from any qrels entry"},
        "queries": [
            {"query_id": "vn:dev:001", "split": "dev", "intent_family": "vitamin-d-bone",
             "text_vi": "Bổ sung vitamin D có giúp ngăn ngừa gãy xương ở người cao tuổi không?",
             "annotation_pilot": True},
            {"query_id": "vn:test:001", "split": "test", "intent_family": "statin-diabetes",
             "text_vi": "Thuốc statin có làm tăng nguy cơ tiểu đường type 2 không?",
             "annotation_pilot": False},
        ],
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return p


def test_draft_manifest_rejected(tmp_path: Path, approved_manifest: Path):
    manifest = json.loads(approved_manifest.read_text(encoding="utf-8"))
    manifest["status"] = "draft_pending_human_approval"
    p = tmp_path / "draft.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(cross_lingual.CrossLingualError, match="not human-approved"):
        cross_lingual.load_approved_manifest(p)


def test_missing_approval_rejected(tmp_path: Path, approved_manifest: Path):
    manifest = json.loads(approved_manifest.read_text(encoding="utf-8"))
    manifest["provenance"]["human_approval"] = None
    p = tmp_path / "noapproval.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(cross_lingual.CrossLingualError, match="lacks recorded human approval"):
        cross_lingual.load_approved_manifest(p)


def test_cache_hit_never_loads_model(tmp_path: Path, approved_manifest: Path):
    cache_path = tmp_path / "cache.json"
    cache = cross_lingual.load_cache(cache_path)
    manifest = json.loads(approved_manifest.read_text(encoding="utf-8"))
    for q in manifest["queries"]:
        cache["entries"][q["query_id"]] = {"text_vi": q["text_vi"], "text_en": "cached translation",
                                           "split": q["split"], "intent_family": q["intent_family"],
                                           "decode": "greedy(num_beams=1, do_sample=False)"}
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    # No model is present in this environment path; a cache hit must not try to load one.
    result = cross_lingual.translate_manifest(approved_manifest, cache_path,
                                              model_dir=tmp_path / "no-model")
    assert set(result["entries"]) == {"vn:dev:001", "vn:test:001"}
    assert result["entries"]["vn:dev:001"]["text_en"] == "cached translation"


def test_empty_translation_rejected(tmp_path: Path, monkeypatch):
    cache_path = tmp_path / "cache.json"
    manifest_path = tmp_path / "m.json"
    manifest_path.write_text(json.dumps({
        "status": "approved_no_edits",
        "provenance": {"human_approval": {"decision": "x", "approved_at": "t"}, "method": "y"},
        "queries": [{"query_id": "vn:dev:001", "split": "dev", "intent_family": "f",
                     "text_vi": "câu hỏi", "annotation_pilot": True}],
    }, ensure_ascii=False), encoding="utf-8")

    class FakeTok:
        @classmethod
        def from_pretrained(cls, name):
            return cls()

        def __call__(self, texts, return_tensors, truncation, max_length):
            return {"input_tensors": texts}

        def decode(self, ids, skip_special_tokens):
            return "   "

    class FakeModel:
        @classmethod
        def from_pretrained(cls, name):
            return cls()

        def eval(self):
            return self

        def generate(self, **kwargs):
            return ["x"]

    monkeypatch.setattr("transformers.AutoTokenizer", FakeTok)
    monkeypatch.setattr("transformers.AutoModelForSeq2SeqLM", FakeModel)
    with pytest.raises(cross_lingual.CrossLingualError, match="Empty translation"):
        cross_lingual.translate_manifest(manifest_path, cache_path)


def test_cli_exit_1_on_unapproved_manifest(tmp_path: Path):
    bad = tmp_path / "m.json"
    bad.write_text(json.dumps({"status": "draft_pending_human_approval",
                               "provenance": {"human_approval": None, "method": "x"}, "queries": []}),
                   encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "scholargraph.retrieval.cross_lingual", "translate",
         "--manifest", str(bad), "--cache", str(tmp_path / "c.json")],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        env={"SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
             "PATH": __import__("os").environ.get("PATH", ""),
             "PYTHONPATH": str(PROJECT_ROOT / "src")})
    assert proc.returncode == 1 and "not human-approved" in (proc.stderr + proc.stdout)
