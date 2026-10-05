"""SG-033 pool tooling + agreement — positive + adversarial tests (synthetic first)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from score_vn_agreement import load_labels, weighted_kappa  # noqa: E402


def test_weighted_kappa_perfect_and_degenerate():
    assert weighted_kappa([(0, 0), (1, 1), (2, 2)]) == pytest.approx(1.0)
    assert weighted_kappa([(2, 2), (2, 2), (2, 2)]) is None  # degenerate -> undefined
    k = weighted_kappa([(2, 0), (0, 2), (1, 1)])
    assert k is not None and -1.0 <= k <= 1.0
    with pytest.raises(ValueError):
        weighted_kappa([])


def test_load_labels_rejects_unlabeled_and_bad_grades(tmp_path):
    p = tmp_path / "labels.jsonl"
    p.write_text(json.dumps({"query_id": "q", "doc_id": "d", "label": None,
                             "annotator": "A", "round": "independent"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unlabeled"):
        load_labels(p)
    p.write_text(json.dumps({"query_id": "q", "doc_id": "d", "label": 5,
                             "annotator": "A", "round": "independent"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid label"):
        load_labels(p)


def test_load_labels_rejects_provenance_leak(tmp_path):
    p = tmp_path / "labels.jsonl"
    p.write_text(json.dumps({"query_id": "q", "doc_id": "d", "label": 1,
                             "annotator": "A", "round": "independent",
                             "method": "dense"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blinding"):
        load_labels(p)


def test_load_labels_rejects_blank_and_malformed(tmp_path):
    p = tmp_path / "labels.jsonl"
    p.write_text('{"query_id": "q"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed"):
        load_labels(p)
    p.write_text('{"query_id":"q","doc_id":"d","label":1,"annotator":"A","round":"independent"}\n\n',
                 encoding="utf-8")
    with pytest.raises(ValueError, match="Blank"):
        load_labels(p)


def test_agreement_cli_rejects_empty_template():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "score_vn_agreement.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 1  # template labels are null -> incomplete
    assert "unlabeled" in (proc.stdout + proc.stderr).lower()


LIVE_POOLS = [  # (annotations dir, query-ID namespace, manifest, translation cache) — ADR-023
    ("data/annotations", "vn", "data/annotations/vn_query_manifest.json",
     "data/processed/vn/translations_cache.json"),
    ("data/annotations/v2", "vn2", "data/annotations/v2/vn_query_manifest.json",
     "data/processed/vn/translations_cache_v2.json"),
]


@pytest.mark.parametrize("ann_dir,ns,manifest_rel,cache_rel", LIVE_POOLS)
def test_live_pool_blinded_and_complete(ann_dir, ns, manifest_rel, cache_rel):
    pool_path = ROOT / ann_dir / "vn_pool.json"
    if not pool_path.is_file():
        pytest.skip("VN pool not built yet in this checkout")
    doc = json.loads(pool_path.read_text(encoding="utf-8"))
    assert all(p["query_id"].startswith(f"{ns}:{p['split']}:") for p in doc["pools"])
    for rel, key in ((manifest_rel, "vn_query_manifest_sha256"), (cache_rel, "translations_cache_sha256")):
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == doc["inputs"][key], \
            f"{rel} changed after the pool was built"
    assert doc["blinded"] is True and doc["depth"] == 10 and doc["seed"] == 20260915
    assert doc["counts"] == {"queries": 30, "dev": 10, "test": 20,
                             "unique_pairs": doc["counts"]["unique_pairs"]}
    assert 1 <= doc["counts"]["unique_pairs"] <= 900
    assert doc["methods"] == ["translated_bm25", "multilingual_dense_e5", "vn_hybrid_rrf"]
    # Method names may appear ONLY in the top-level methods list (construction
    # transparency); never inside per-query rows (blinding).
    for pool in doc["pools"]:
        row_raw = json.dumps(pool, ensure_ascii=False).lower()
        for leaked in ("translated_bm25", "multilingual_dense_e5", "vn_hybrid_rrf"):
            assert leaked not in row_raw, f"pool row leaks method {leaked}"
    # Structural blinding: candidate rows carry only position/doc/title/year.
    for pool in doc["pools"]:
        for cand in pool["candidates"]:
            assert set(cand) == {"position", "doc_id", "title", "year"}, \
                f"pool row leaks extra fields: {sorted(set(cand))}"
    seen: set[tuple[str, str]] = set()
    for pool in doc["pools"]:
        assert 1 <= pool["pool_size"] <= 30
        assert len(pool["candidates"]) == pool["pool_size"]
        positions = [c["position"] for c in pool["candidates"]]
        assert positions == list(range(1, pool["pool_size"] + 1))
        for cand in pool["candidates"]:
            key = (pool["query_id"], cand["doc_id"])
            assert key not in seen, f"duplicate pair {key}"
            seen.add(key)
    assert len(seen) == doc["counts"]["unique_pairs"]
    prov = json.loads((ROOT / ann_dir / "vn_pool_provenance.json").read_text(encoding="utf-8"))
    assert set(prov["provenance"]) == {p["query_id"] for p in doc["pools"]}
    labels = (ROOT / ann_dir / "vn_labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(labels) == doc["counts"]["unique_pairs"]
    assert all(json.loads(line)["label"] is None for line in labels)


def _pool_cli(tmp_path, manifest: dict, cache: dict | None):
    mp, cp, out = tmp_path / "manifest.json", tmp_path / "cache.json", tmp_path / "out"
    out.mkdir()
    mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    if cache is not None:
        cp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_vn_pool.py"),
         "--manifest", str(mp), "--cache", str(cp), "--out-dir", str(out)],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert not any(out.iterdir()), "failed build must not write outputs"
    return proc


def _v2_inputs():
    m = json.loads((ROOT / "data/annotations/v2/vn_query_manifest.json").read_text(encoding="utf-8"))
    c = json.loads((ROOT / "data/processed/vn/translations_cache_v2.json").read_text(encoding="utf-8"))
    return m, c


@pytest.mark.parametrize("case,needle", [
    ("draft_manifest", "not human-approved"),
    ("no_approval_record", "human approval"),
    ("cache_missing_query", "incomplete"),
    ("cache_text_vi_drift", "differs from manifest"),
    ("cache_file_missing", "No such file"),
    ("29_queries", "Expected 30"),
])
def test_pool_cli_rejects_bad_inputs_exit_1(tmp_path, case, needle):
    m, c = _v2_inputs()
    if case == "draft_manifest":
        m["status"] = "draft_pending_human_approval"
    elif case == "no_approval_record":
        m["provenance"].pop("human_approval")
    elif case == "cache_missing_query":
        c["entries"].pop("vn2:test:020")
    elif case == "cache_text_vi_drift":
        m["queries"][0]["text_vi"] += " (đã sửa sau khi dịch)"
    elif case == "cache_file_missing":
        c = None
    elif case == "29_queries":
        m["queries"].pop()
    proc = _pool_cli(tmp_path, m, c)
    assert proc.returncode == 1, proc.stdout
    assert "FAIL:" in proc.stderr and needle in proc.stderr
