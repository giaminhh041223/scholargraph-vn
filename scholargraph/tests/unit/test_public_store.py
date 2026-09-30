"""Synthetic SQLite store tests for EXT-04A, temp only, no live data."""
import hashlib
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
import pytest
from scholargraph.public_search.contracts import FusionCounts
from scholargraph.public_search.contracts import FusionResult
from scholargraph.public_search.contracts import PaperRecord
from scholargraph.public_search.contracts import RankedHit
from scholargraph.public_search.contracts import RawReference
from scholargraph.public_search.contracts import SearchError
from scholargraph.public_search.contracts import SearchRequest
from scholargraph.public_search.contracts import SearchSnapshot
from scholargraph.public_search.contracts import SourceResult
from scholargraph.public_search.contracts import cache_key
from scholargraph.public_search.contracts import digest
from scholargraph.public_search.contracts import load_config
from scholargraph.public_search.store import StoreError
from scholargraph.public_search.store import initialize_store
from scholargraph.public_search.store import open_existing
ROOT = Path(__file__).resolve().parents[2]
ADAPTER_SHA = "b" * 64


def muse_config(tmp_root: Path):
    base = json.loads((ROOT / "configs" / "public_search.json").read_text(encoding="utf-8"))
    base["data_root"] = "data/public_search/muse"
    cfg_path = tmp_root / "cfg.json"
    cfg_path.write_text(json.dumps(base), encoding="utf-8")
    return load_config(cfg_path)


def make_request():
    return SearchRequest.model_validate({"query": "graph mining", "sources": ["openalex", "arxiv"], "top_k": 10, "cap_per_source": 10, "year_from": None, "year_to": None, "refresh": False})

def paper_for(source: str, sid: str, sha: str, title="Synthetic title"):
    nullable = ["abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url", "license", "open_access_status", "citation_count", "authors"]
    row = {"source": source, "source_id": sid, "title": title, "landing_url": "https://example.org/" + sid, "retrieved_at": datetime(2026, 9, 30, tzinfo=timezone.utc), "raw_sha256": sha, "parser_version": "synthetic-1", "authors_availability": "missing", "missing_fields": nullable, "field_provenance": {}}
    row.update({name: None for name in nullable})
    row["field_provenance"] = {key: [{"source": source, "source_id": sid, "raw_sha256": sha, "raw_field": key}] for key in ["title", "source_id", "landing_url"]}
    return PaperRecord.model_validate(row)


def build_snapshot(config, snapshot_id: str, kind="success", fetched=None, expires=None):
    req = make_request()
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    if fetched is None:
        fetched = now
    if expires is None:
        expires = now + timedelta(days=1)
    adapter = {s: ADAPTER_SHA for s in req.sources}
    cfg_digest = digest(config)
    raws: dict[str, bytes] = {}
    results = []
    if kind == "success":
        body = ("{\"synthetic\": \"" + snapshot_id + "\"}").encode("utf-8")
        sha = hashlib.sha256(body).hexdigest()
        rid = "openalex-" + sha
        raws[rid] = body
        rec = paper_for("openalex", "W1", sha)
        results.append(SourceResult(source="openalex", status="success", records=[rec], error=None, source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[RawReference(raw_id=rid, sha256=sha, byte_count=len(body))]))
        results.append(SourceResult(source="arxiv", status="empty", records=[], error=None, source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[]))
        hit = RankedHit(canonical_id="synthetic:W1", rank=1, score=1.0 / 61.0, display=rec, source_records=[rec], source_ranks={"openalex": 1}, conflicts={})
        counts = FusionCounts(raw=1, valid=1, invalid=0, excluded_by_year=0, eligible=1, groups=1, duplicate_excess=0, returned=1)
        fusion = FusionResult(hits=[hit], counts=counts)
        overall = "success"
    elif kind == "empty":
        for s in req.sources:
            results.append(SourceResult(source=s, status="empty", records=[], error=None, source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[]))
        fusion = FusionResult(hits=[], counts=FusionCounts(raw=0, valid=0, invalid=0, excluded_by_year=0, eligible=0, groups=0, duplicate_excess=0, returned=0))
        overall = "empty"
    elif kind == "partial":
        body = ("{\"synthetic-partial\": \"" + snapshot_id + "\"}").encode("utf-8")
        sha = hashlib.sha256(body).hexdigest()
        rid = "openalex-" + sha
        raws[rid] = body
        rec = paper_for("openalex", "W1", sha)
        results.append(SourceResult(source="openalex", status="success", records=[rec], error=None, source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[RawReference(raw_id=rid, sha256=sha, byte_count=len(body))]))
        results.append(SourceResult(source="arxiv", status="failed", records=[], error=SearchError(kind="timeout", message="synthetic timeout", source="arxiv", retry_after_seconds=None, record_index=None), source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[]))
        hit = RankedHit(canonical_id="synthetic:W1", rank=1, score=1.0 / 61.0, display=rec, source_records=[rec], source_ranks={"openalex": 1}, conflicts={})
        counts = FusionCounts(raw=1, valid=1, invalid=0, excluded_by_year=0, eligible=1, groups=1, duplicate_excess=0, returned=1)
        fusion = FusionResult(hits=[hit], counts=counts)
        overall = "partial_failure"
    else:
        for s in req.sources:
            results.append(SourceResult(source=s, status="failed", records=[], error=SearchError(kind="timeout", message="synthetic timeout", source=s, retry_after_seconds=None, record_index=None), source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[]))
        fusion = FusionResult(hits=[], counts=FusionCounts(raw=0, valid=0, invalid=0, excluded_by_year=0, eligible=0, groups=0, duplicate_excess=0, returned=0))
        overall = "failed"
    snap = SearchSnapshot(schema_version=1, contract_version="1.0.0", snapshot_id=snapshot_id, request=req, config_sha256=cfg_digest, adapter_sha256=adapter, source_results=results, fusion=fusion, overall=overall, fetched_at=fetched, expires_at=expires)
    key = cache_key(req, config, adapter)
    return snap, raws, key


def test_init_fresh_and_idempotent(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj"
    proj.mkdir()
    first = initialize_store(proj, cfg)
    first.close()
    second = initialize_store(proj, cfg)
    second.close()
    third = open_existing(proj, cfg)
    third.close()


def test_open_missing_db_fails_without_create(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj2"
    proj.mkdir()
    with pytest.raises(StoreError) as exc:
        open_existing(proj, cfg)
    assert exc.value.error.kind == "storage"
    assert not (proj / "data" / "public_search" / "muse").exists()


def test_init_with_existing_evidence_refuses_rebuild(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj3"
    proj.mkdir()
    data = proj / "data" / "public_search" / "muse"
    data.mkdir(parents=True)
    (data / "store.json").write_text("{\"stale\": true}", encoding="utf-8")
    with pytest.raises(StoreError):
        initialize_store(proj, cfg)
    with pytest.raises(StoreError):
        open_existing(proj, cfg)


def test_db_missing_with_marker_both_fail(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj4"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    store.close()
    data = proj / "data" / "public_search" / "muse"
    (data / "library.sqlite3").unlink()
    with pytest.raises(StoreError):
        open_existing(proj, cfg)
    with pytest.raises(StoreError):
        initialize_store(proj, cfg)
    assert not (data / "library.sqlite3").exists()


def test_save_and_load_success(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj5"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-success-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    hit = store.load_cache(key, now=now)
    assert hit is not None and hit.snapshot_id == "snap-success-1"
    back = store.read_snapshot("snap-success-1")
    assert back.snapshot_id == "snap-success-1"
    assert store.load_cache("f" * 64, now=now) is None
    store.close()


def test_empty_is_cached_success(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj6"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-empty-1", "empty")
    assert raws == {}
    store.save_snapshot(snap, raws, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    assert store.load_cache(key, now=now) is not None
    store.close()


def test_failed_partial_do_not_move_pointer(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj7"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    good, good_raw, key = build_snapshot(cfg, "snap-good-1", "success")
    store.save_snapshot(good, good_raw, cache_key=key)
    bad, bad_raw, bad_key = build_snapshot(cfg, "snap-failed-1", "failed")
    assert bad_key == key
    store.save_snapshot(bad, bad_raw, cache_key=bad_key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    assert store.load_cache(key, now=now).snapshot_id == "snap-good-1"
    assert store.load_cache(key, now=now).snapshot_id == "snap-good-1"
    assert store.read_snapshot("snap-failed-1").overall == "failed"
    part, part_raw, part_key = build_snapshot(cfg, "snap-part-1", "partial")
    store.save_snapshot(part, part_raw, cache_key=part_key)
    assert store.load_cache(key, now=now).snapshot_id == "snap-good-1"
    store.close()


def test_ttl_and_refresh_success_failure(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj8"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    base = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    snap, raws, key = build_snapshot(cfg, "snap-ttl-1", "success", fetched=base, expires=base + timedelta(seconds=10))
    store.save_snapshot(snap, raws, cache_key=key)
    assert store.load_cache(key, now=base + timedelta(seconds=5)) is not None
    assert store.load_cache(key, now=base + timedelta(seconds=11)) is None
    assert store.read_snapshot("snap-ttl-1").snapshot_id == "snap-ttl-1"
    snap2, raws2, key2 = build_snapshot(cfg, "snap-ttl-2", "success", fetched=base + timedelta(seconds=12), expires=base + timedelta(seconds=100))
    assert key2 == key
    store.save_snapshot(snap2, raws2, cache_key=key)
    assert store.load_cache(key, now=base + timedelta(seconds=13)).snapshot_id == "snap-ttl-2"
    bad, bad_raw, bad_key = build_snapshot(cfg, "snap-ttl-bad", "failed", fetched=base + timedelta(seconds=14), expires=base + timedelta(seconds=100))
    store.save_snapshot(bad, bad_raw, cache_key=key)
    assert store.load_cache(key, now=base + timedelta(seconds=15)).snapshot_id == "snap-ttl-2"
    store.close()


def test_missing_raw_fails_everywhere(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj9"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-raw-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    store.save_paper("snap-raw-1", "synthetic:W1", now=now)
    raw_id = list(raws.keys())[0]
    (proj / "data" / "public_search" / "muse" / "raw" / raw_id).unlink()
    with pytest.raises(StoreError):
        store.load_cache(key, now=now)
    with pytest.raises(StoreError):
        store.read_snapshot("snap-raw-1")
    with pytest.raises(StoreError):
        store.save_paper("snap-raw-1", "synthetic:W1", now=now)
    with pytest.raises(StoreError):
        store.list_library(offset=0, limit=10)
    with pytest.raises(StoreError):
        store.export_library("json")
    store.close()


def test_wrong_hash_and_keyset_fail(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj10"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-hash-1", "success")
    raw_id = list(raws.keys())[0]
    tampered = {raw_id: b"tampered bytes"}
    with pytest.raises(StoreError):
        store.save_snapshot(snap, tampered, cache_key=key)
    with pytest.raises(StoreError):
        store.save_snapshot(snap, {}, cache_key=key)
    extra = dict(raws)
    extra["openalex-" + "c" * 64] = b"extra"
    with pytest.raises(StoreError):
        store.save_snapshot(snap, extra, cache_key=key)
    store.close()


def test_immutable_ids_rejected(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj11"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-imm-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    snap2, raws2, key2 = build_snapshot(cfg, "snap-imm-1", "empty")
    with pytest.raises(StoreError):
        store.save_snapshot(snap2, raws2, cache_key=key2)
    raw_id = list(raws.keys())[0]
    data_dir = proj / "data" / "public_search" / "muse" / "raw" / raw_id
    assert data_dir.read_bytes() == raws[raw_id]
    store.close()


def test_malformed_scores_and_records_fail(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj12"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-mal-1", "success")
    bad_row = snap.model_dump()
    bad_row["fusion"]["hits"][0]["score"] = float("nan")
    with pytest.raises(Exception):
        SearchSnapshot.model_validate(bad_row)
    bad_row2 = snap.model_dump()
    bad_row2["fusion"]["hits"][0]["score"] = True
    with pytest.raises(Exception):
        SearchSnapshot.model_validate(bad_row2)
    with pytest.raises(StoreError):
        store.save_snapshot(snap, {"wrong": b"x"}, cache_key=key)
    store.close()


def test_leakage_fields_rejected_on_read(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj13"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-leak-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    store.close()
    import sqlite3
    db = proj / "data" / "public_search" / "muse" / "library.sqlite3"
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT snapshot_json FROM snapshots WHERE snapshot_id = ?", ("snap-leak-1",)).fetchone()
    payload = json.loads(row[0])
    payload["qrels"] = "FORBIDDEN"
    conn.execute("UPDATE snapshots SET snapshot_json = ? WHERE snapshot_id = ?", (json.dumps(payload), "snap-leak-1"))
    conn.commit()
    conn.close()
    reopened = open_existing(proj, cfg)
    with pytest.raises(StoreError):
        reopened.read_snapshot("snap-leak-1")
    reopened.close()


def test_unknown_ids_paging_format_fail(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj14"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-unk-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(StoreError):
        store.read_snapshot("no-such-id")
    with pytest.raises(StoreError):
        store.save_paper("no-such-id", "synthetic:W1", now=now)
    with pytest.raises(StoreError):
        store.save_paper("snap-unk-1", "no-such-paper", now=now)
    with pytest.raises(StoreError):
        store.list_library(offset=-1, limit=10)
    with pytest.raises(StoreError):
        store.list_library(offset=0, limit=0)
    with pytest.raises(StoreError):
        store.list_library(offset=0, limit=101)
    with pytest.raises(StoreError):
        store.list_library(offset=True, limit=10)
    with pytest.raises(StoreError):
        store.export_library("xml")
    with pytest.raises(StoreError):
        store.load_cache("not-hex", now=now)
    store.close()


def test_duplicate_save_and_partial_badge(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj15"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-dup-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    first_time = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    second_time = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    e1 = store.save_paper("snap-dup-1", "synthetic:W1", now=first_time)
    e2 = store.save_paper("snap-dup-1", "synthetic:W1", now=second_time)
    assert e1.saved_at == e2.saved_at == first_time
    assert e1.incomplete_sources is False
    part, part_raw, part_key = build_snapshot(cfg, "snap-part-2", "partial")
    store.save_snapshot(part, part_raw, cache_key=part_key)
    e3 = store.save_paper("snap-part-2", "synthetic:W1", now=second_time)
    assert e3.canonical_id == "synthetic:W1"
    assert e3.saved_at == first_time
    store.close()


def test_partial_new_paper_badge_true(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj15b"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    part, part_raw, part_key = build_snapshot(cfg, "snap-only-part", "partial")
    store.save_snapshot(part, part_raw, cache_key=part_key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    entry = store.save_paper("snap-only-part", "synthetic:W1", now=now)
    assert entry.incomplete_sources is True
    store.close()


def test_list_pagination_deterministic(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj16"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-page-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    store.save_paper("snap-page-1", "synthetic:W1", now=now)
    assert store.list_library(offset=0, limit=100) is not None
    assert len(store.list_library(offset=0, limit=1)) == 1
    assert store.list_library(offset=5, limit=10) == []
    first = store.list_library(offset=0, limit=10)
    second = store.list_library(offset=0, limit=10)
    assert [e.canonical_id for e in first] == [e.canonical_id for e in second]
    store.close()


def test_db_corruption_fails(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj17"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    store.close()
    db = proj / "data" / "public_search" / "muse" / "library.sqlite3"
    db.write_bytes(b"corrupted-not-sqlite")
    with pytest.raises(StoreError):
        open_existing(proj, cfg)
    with pytest.raises(StoreError):
        initialize_store(proj, cfg)


def test_marker_mismatch_fails(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj18"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    store.close()
    marker = proj / "data" / "public_search" / "muse" / "store.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["config_sha256"] = "c" * 64
    marker.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StoreError):
        open_existing(proj, cfg)
    base = json.loads((ROOT / "configs" / "public_search.json").read_text(encoding="utf-8"))
    base["data_root"] = "data/public_search/muse"
    base["cache_ttl_seconds"] = 99999
    other_path = tmp_path / "other.json"
    other_path.write_text(json.dumps(base), encoding="utf-8")
    other_cfg = load_config(other_path)
    with pytest.raises(StoreError):
        open_existing(proj, other_cfg)


def test_unsafe_raw_id_rejected(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj19"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-safe-1", "success")
    raw_id = list(raws.keys())[0]
    assert ".." not in raw_id and "/" not in raw_id
    bad_dict = snap.model_dump()
    bad_dict["source_results"][0]["raw_references"][0]["raw_id"] = "../escape"
    unsafe = SearchSnapshot.model_validate(bad_dict)
    bad_raws = {"../escape": raws[raw_id]}
    with pytest.raises(StoreError):
        store.save_snapshot(unsafe, bad_raws, cache_key=key)
    store.close()
    data = proj / "data" / "public_search" / "muse" / "raw" / raw_id
    assert data.exists() is False
    store2 = open_existing(proj, cfg)
    store2.save_snapshot(snap, raws, cache_key=key)
    assert (proj / "data" / "public_search" / "muse" / "raw" / raw_id).is_file()
    store2.close()


def test_symlink_raw_rejected(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj20"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-link-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    raw_id = list(raws.keys())[0]
    target = proj / "data" / "public_search" / "muse" / "raw" / raw_id
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    target.unlink()
    try:
        target.symlink_to(outside)
        linked = True
    except Exception:
        linked = False
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    if linked:
        with pytest.raises(StoreError):
            store.load_cache(key, now=now)
        with pytest.raises(StoreError):
            store.read_snapshot("snap-link-1")
    else:
        assert target.exists() is False
    store.close()


def test_interrupted_transaction_leaves_no_dangling(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj21"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-crash-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    snap2, raws2, key2 = build_snapshot(cfg, "snap-crash-2", "success")
    raw_dir = proj / "data" / "public_search" / "muse" / "raw"
    for rid, payload in raws2.items():
        (raw_dir / rid).write_bytes(payload)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    assert key2 == key
    assert store.load_cache(key2, now=now).snapshot_id == "snap-crash-1"
    with pytest.raises(StoreError):
        store.read_snapshot("snap-crash-2")
    assert store.load_cache(key, now=now).snapshot_id == "snap-crash-1"
    orphans = list(raw_dir.iterdir())
    assert len(orphans) >= 2
    store.close()


def test_concurrent_read_write(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj22"
    proj.mkdir()
    seed = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-conc-0", "success")
    seed.save_snapshot(snap, raws, cache_key=key)
    seed.close()
    def writer(idx: int):
        local = open_existing(proj, cfg)
        try:
            s, r, k = build_snapshot(cfg, "snap-conc-" + str(idx + 1), "success")
            local.save_snapshot(s, r, cache_key=k)
        finally:
            local.close()
        return idx
    def reader():
        local = open_existing(proj, cfg)
        try:
            now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
            local.list_library(offset=0, limit=10)
            local.load_cache(key, now=now)
        finally:
            local.close()
        return True
    with ThreadPoolExecutor(max_workers=4) as pool:
        writes = [pool.submit(writer, i) for i in range(4)]
        reads = [pool.submit(reader) for _ in range(4)]
        assert [f.result() for f in writes] == [0, 1, 2, 3]
        assert all(f.result() for f in reads)
    check = open_existing(proj, cfg)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    assert check.load_cache(key, now=now) is not None
    check.close()


def test_close_handles(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj23"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    store.close()
    store.close()
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(StoreError):
        store.list_library(offset=0, limit=1)
    with pytest.raises(StoreError):
        store.load_cache("a" * 64, now=now)


def test_no_fallback_get_in_store():
    src = (ROOT / "src" / "scholargraph" / "public_search" / "store.py").read_text(encoding="utf-8")
    assert ".get(" not in src
    assert "model_construct" not in src


def test_export_roundtrip_library(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "proj24"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-exp-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    store.save_paper("snap-exp-1", "synthetic:W1", now=now)
    raw_json = store.export_library("json")
    payload = json.loads(raw_json.decode("utf-8"))
    assert len(payload) == 1 and payload[0]["canonical_id"] == "synthetic:W1"
    raw_bib = store.export_library("bibtex")
    assert b"@misc" in raw_bib and b"synthetic:W1" in raw_bib
    store.close()


def test_boundary_cli_valid_and_invalid(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projcli"
    proj.mkdir()
    cfg_file = tmp_path / "used_cfg.json"
    cfg_file.write_text(cfg.model_dump_json(), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    base_cmd = [sys.executable, "-m", "scholargraph.public_search.store", "--check-storage", "--config", str(cfg_file), "--project-root", str(proj)]
    missing = subprocess.run(base_cmd, cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert missing.returncode == 1 and "FAIL" in missing.stderr
    store = initialize_store(proj, cfg)
    store.close()
    valid = subprocess.run(base_cmd, cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert valid.returncode == 0 and "VALID" in valid.stdout
    (proj / "data" / "public_search" / "muse" / "library.sqlite3").write_bytes(b"bad")
    corrupt = subprocess.run(base_cmd, cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert corrupt.returncode == 1 and "FAIL" in corrupt.stderr
    noflag = subprocess.run([sys.executable, "-m", "scholargraph.public_search.store", "--config", str(cfg_file)], cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert noflag.returncode == 1


def _single_snapshot_for_tz(config, snapshot_id, canonical_id, sid):
    req = make_request()
    now0 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    body = ("{\"synthetic-tz\": \"" + snapshot_id + "\"}").encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    rid = "openalex-" + sha
    raws = {rid: body}
    rec = paper_for("openalex", sid, sha)
    results = [SourceResult(source="openalex", status="success", records=[rec], error=None, source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[RawReference(raw_id=rid, sha256=sha, byte_count=len(body))]), SourceResult(source="arxiv", status="empty", records=[], error=None, source_total=None, elapsed_seconds=0.1, filter_coverage="server", truncated=False, raw_references=[])]
    hit = RankedHit(canonical_id=canonical_id, rank=1, score=1.0 / 61.0, display=rec, source_records=[rec], source_ranks={"openalex": 1}, conflicts={})
    counts = FusionCounts(raw=1, valid=1, invalid=0, excluded_by_year=0, eligible=1, groups=1, duplicate_excess=0, returned=1)
    fusion = FusionResult(hits=[hit], counts=counts)
    adapter = {s: ADAPTER_SHA for s in req.sources}
    snap = SearchSnapshot(schema_version=1, contract_version="1.0.0", snapshot_id=snapshot_id, request=req, config_sha256=digest(config), adapter_sha256=adapter, source_results=results, fusion=fusion, overall="success", fetched_at=now0, expires_at=now0 + timedelta(days=1))
    key = cache_key(req, config, adapter)
    return snap, raws, key


def test_load_cache_rejects_failed_and_partial_overall(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projF1R2"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    good, good_raw, key = build_snapshot(cfg, "snap-f1r2-good", "success")
    store.save_snapshot(good, good_raw, cache_key=key)
    bad, bad_raw, _ = build_snapshot(cfg, "snap-f1r2-failed", "failed")
    store.save_snapshot(bad, bad_raw, cache_key=key)
    part, part_raw, _ = build_snapshot(cfg, "snap-f1r2-partial", "partial")
    store.save_snapshot(part, part_raw, cache_key=key)
    now = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
    assert store.load_cache(key, now=now).snapshot_id == "snap-f1r2-good"
    store.close()
    import sqlite3
    db = proj / "data" / "public_search" / "muse" / "library.sqlite3"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("UPDATE cache SET snapshot_id = ? WHERE cache_key = ?", ("snap-f1r2-failed", key))
        conn.commit()
    finally:
        conn.close()
    reopened = open_existing(proj, cfg)
    with pytest.raises(StoreError) as exc1:
        reopened.load_cache(key, now=now)
    assert exc1.value.error.kind == "storage"
    reopened.close()
    conn2 = sqlite3.connect(str(db))
    try:
        conn2.execute("UPDATE cache SET snapshot_id = ? WHERE cache_key = ?", ("snap-f1r2-partial", key))
        conn2.commit()
    finally:
        conn2.close()
    reopened2 = open_existing(proj, cfg)
    with pytest.raises(StoreError) as exc2:
        reopened2.load_cache(key, now=now)
    assert exc2.value.error.kind == "storage"
    reopened2.close()
    conn3 = sqlite3.connect(str(db))
    try:
        conn3.execute("INSERT OR REPLACE INTO cache (cache_key, snapshot_id, cached_at) VALUES (?, ?, ?)", ("e" * 64, "snap-f1r2-failed", now.isoformat()))
        conn3.commit()
    finally:
        conn3.close()
    reopened3 = open_existing(proj, cfg)
    with pytest.raises(StoreError) as exc3:
        reopened3.load_cache("e" * 64, now=now)
    assert exc3.value.error.kind == "storage"
    reopened3.close()


def test_library_mixed_timezone_chronological_order(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projF2R2"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap_a, raw_a, key_a = _single_snapshot_for_tz(cfg, "snap-f2r2-A", "synthetic:TZ-A", "W-TZ-A")
    snap_b, raw_b, key_b = _single_snapshot_for_tz(cfg, "snap-f2r2-B", "synthetic:TZ-B", "W-TZ-B")
    store.save_snapshot(snap_a, raw_a, cache_key=key_a)
    store.save_snapshot(snap_b, raw_b, cache_key=key_b)
    t_a = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    tz7 = timezone(timedelta(hours=7))
    t_b = datetime(2026, 9, 30, 20, 0, 0, tzinfo=tz7)
    assert t_b < t_a
    assert t_a.isoformat() < t_b.isoformat()
    e_a = store.save_paper("snap-f2r2-A", "synthetic:TZ-A", now=t_a)
    e_b = store.save_paper("snap-f2r2-B", "synthetic:TZ-B", now=t_b)
    assert e_a.saved_at == t_a
    assert e_b.saved_at == t_b
    page = store.list_library(offset=0, limit=10)
    assert [e.canonical_id for e in page] == ["synthetic:TZ-B", "synthetic:TZ-A"]
    assert store.list_library(offset=0, limit=1)[0].canonical_id == "synthetic:TZ-B"
    assert store.list_library(offset=1, limit=1)[0].canonical_id == "synthetic:TZ-A"
    raw = store.export_library("json")
    payload = json.loads(raw.decode("utf-8"))
    assert [r["canonical_id"] for r in payload] == ["synthetic:TZ-B", "synthetic:TZ-A"]
    store.close()


def test_library_equivalent_instants_tie_break(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projF2R2tie"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap_a, raw_a, key_a = _single_snapshot_for_tz(cfg, "snap-f2r2-tie-A", "synthetic:TIE-A", "W-TIE-A")
    snap_b, raw_b, key_b = _single_snapshot_for_tz(cfg, "snap-f2r2-tie-B", "synthetic:TIE-B", "W-TIE-B")
    store.save_snapshot(snap_a, raw_a, cache_key=key_a)
    store.save_snapshot(snap_b, raw_b, cache_key=key_b)
    t1 = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 30, 21, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    assert t1 == t2
    assert t1.isoformat() != t2.isoformat()
    store.save_paper("snap-f2r2-tie-B", "synthetic:TIE-B", now=t2)
    store.save_paper("snap-f2r2-tie-A", "synthetic:TIE-A", now=t1)
    page = store.list_library(offset=0, limit=10)
    assert [e.canonical_id for e in page] == ["synthetic:TIE-A", "synthetic:TIE-B"]
    assert page[0].saved_at == t1
    assert page[1].saved_at == t2
    store.close()


def test_close_concurrent_bounded(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projF3R2"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-f3r2-1", "success")
    store.save_snapshot(snap, raws, cache_key=key)
    store.save_paper("snap-f3r2-1", "synthetic:W1", now=datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc))
    barrier = threading.Barrier(5)
    outcomes: list[str] = []
    guard = threading.Lock()
    def reader():
        try:
            barrier.wait(timeout=5)
        except Exception:
            with guard:
                outcomes.append("barrier-fail")
            return None
        try:
            store.list_library(offset=0, limit=10)
            with guard:
                outcomes.append("ok")
        except StoreError as exc:
            assert exc.error.kind == "storage"
            with guard:
                outcomes.append("closed")
        except Exception:
            with guard:
                outcomes.append("unexpected")
        return None
    def closer():
        try:
            barrier.wait(timeout=5)
        except Exception:
            with guard:
                outcomes.append("barrier-fail")
            return None
        try:
            store.close()
            with guard:
                outcomes.append("close-ok")
        except Exception:
            with guard:
                outcomes.append("close-fail")
        return None
    threads = [threading.Thread(target=reader) for _ in range(4)]
    threads.append(threading.Thread(target=closer))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert all(not t.is_alive() for t in threads)
    assert "close-ok" in outcomes
    assert all(o in ("ok", "closed", "close-ok") for o in outcomes)
    with pytest.raises(StoreError):
        store.list_library(offset=0, limit=1)
    store.close()


def test_close_fault_structured_failure_and_retry(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projR3close"
    proj.mkdir()
    store = initialize_store(proj, cfg)
    real_conn = store._conn
    class BrokenClose:
        def close(self):
            raise OSError("synthetic close fault")
    store._conn = BrokenClose()
    with pytest.raises(StoreError) as exc:
        store.close()
    assert exc.value.error.kind == "storage"
    assert store._closed is False
    store._conn = real_conn
    store.close()
    assert store._closed is True
    store.close()
    with pytest.raises(StoreError):
        store.list_library(offset=0, limit=1)


def test_check_storage_close_fault_cli_exit1(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projR3cli"
    proj.mkdir()
    seed = initialize_store(proj, cfg)
    seed.close()
    cfg_file = tmp_path / "used_r3.json"
    cfg_file.write_text(cfg.model_dump_json(), encoding="utf-8")
    boot = tmp_path / "boot_r3.py"
    boot.write_text("from scholargraph.public_search import store as s\nclass BrokenStore:\n def list_library(self, **kw):\n  return []\n def close(self):\n  raise OSError('synthetic close fault')\ns.open_existing=lambda *a, **k: BrokenStore()\nraise SystemExit(s.main())\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    cmd = [sys.executable, str(boot), "--check-storage", "--config", str(cfg_file), "--project-root", str(proj)]
    proc = subprocess.run(cmd, cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "FAIL" in proc.stderr
    assert "VALID" not in proc.stdout


def test_has_evidence_enumeration_fault_fails_loud(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projR3ev"
    proj.mkdir()
    data_dir = proj / "data" / "public_search" / "muse"
    data_dir.mkdir(parents=True)
    sentinel = data_dir / "sentinel.bin"
    sentinel.write_bytes(b"sentinel-bytes-r3")
    before = sentinel.read_bytes()
    original = Path.iterdir
    def fault(self):
        if self == data_dir:
            raise OSError("synthetic evidence enumeration fault")
        return original(self)
    Path.iterdir = fault
    try:
        with pytest.raises(StoreError) as exc:
            initialize_store(proj, cfg)
        assert exc.value.error.kind == "storage"
    finally:
        Path.iterdir = original
    assert sentinel.read_bytes() == before
    assert not (data_dir / "store.json").exists()
    assert not (data_dir / "library.sqlite3").exists()


def test_metadata_close_interleaving_controlled(tmp_path):
    cfg = muse_config(tmp_path)
    proj = tmp_path / "projR4race"
    proj.mkdir()
    seed = initialize_store(proj, cfg)
    snap, raws, key = build_snapshot(cfg, "snap-r4-race", "success")
    seed.save_snapshot(snap, raws, cache_key=key)
    seed.close()
    cfg_file = tmp_path / "used_r4.json"
    cfg_file.write_text(cfg.model_dump_json(), encoding="utf-8")
    child = tmp_path / "race_r4_child.py"
    child.write_text("import sys, json, threading\nfrom pathlib import Path\nfrom datetime import datetime, timezone\nfrom scholargraph.public_search.store import open_existing, StoreError\nfrom scholargraph.public_search.contracts import load_config\ncfg_file = Path(sys.argv[1])\nproj = Path(sys.argv[2])\ncfg = load_config(cfg_file)\nstore = open_existing(proj, cfg)\nbarrier = threading.Barrier(3)\nouts = []\nguard = threading.Lock()\n\ndef reader():\n try:\n  barrier.wait(timeout=5)\n except Exception:\n  with guard:\n   outs.append('barrier-fail')\n  return\n try:\n  store.list_library(offset=0, limit=1)\n  with guard:\n   outs.append('ok')\n except StoreError as e:\n  assert e.error.kind == 'storage'\n  with guard:\n   outs.append('closed')\n except Exception:\n  with guard:\n   outs.append('unexpected')\n\ndef closer():\n try:\n  barrier.wait(timeout=5)\n except Exception:\n  with guard:\n   outs.append('barrier-fail')\n  return\n try:\n  store.close()\n  with guard:\n   outs.append('close-ok')\n except StoreError:\n  with guard:\n   outs.append('close-structured')\n except Exception:\n  with guard:\n   outs.append('close-unexpected')\nthreads = [threading.Thread(target=reader) for _ in range(2)]\nthreads.append(threading.Thread(target=closer))\nfor t in threads:\n t.start()\nfor t in threads:\n t.join(timeout=5)\nhung = [t.is_alive() for t in threads]\nprint(json.dumps({'outs': outs, 'hung': hung, 'closed': store._closed}))\nraise SystemExit(0 if (not any(hung) and ('close-ok' in outs or 'close-structured' in outs) and all(o in ('ok', 'closed', 'close-ok', 'close-structured') for o in outs)) else 1)\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run([sys.executable, str(child), str(cfg_file), str(proj)], cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.returncode != -1073741819
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["hung"] == [False, False, False]
    assert "close-ok" in payload["outs"] or "close-structured" in payload["outs"]
    assert all(o in ("ok", "closed", "close-ok", "close-structured") for o in payload["outs"])
