"""Reproducer probe for EXT-04A MUSE storage review findings.

Executed by coordinator in isolated temp directory.
Zero mutations to project repository or core data.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

MUSE_SRC = Path("D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph/src")
if MUSE_SRC.exists() and str(MUSE_SRC) not in sys.path:
    sys.path.insert(0, str(MUSE_SRC))

try:
    from scholargraph.public_search.contracts import (
        FusionCounts,
        FusionResult,
        LibraryEntry,
        PaperRecord,
        RankedHit,
        RawReference,
        SearchError,
        SearchRequest,
        SearchSnapshot,
        SourceResult,
        digest,
        load_config,
    )
    from scholargraph.public_search.export import export_json
    from scholargraph.public_search.store import (
        StoreError,
        _validate_raw_id,
        initialize_store,
        open_existing,
    )
    IMPORTS_OK = True
except Exception as e:
    IMPORTS_OK = False
    IMPORT_ERR = str(e)


def run_probe() -> dict:
    if not IMPORTS_OK:
        return {"status": "IMPORT_FAIL", "error": IMPORT_ERR, "passed": 0, "failed": 1}

    results = []

    # 1. Probe Timezone string sorting in export_json (Finding F1)
    # Entry A: 14:00 UTC
    # Entry B: 20:00 UTC+7 (which is 13:00 UTC, chronologically earlier than A)
    try:
        t_a = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)
        tz_plus7 = timezone(timedelta(hours=7))
        t_b = datetime(2026, 9, 30, 20, 0, 0, tzinfo=tz_plus7)

        sha = "a" * 64
        nullable = ["abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url", "license", "open_access_status", "citation_count", "authors"]
        row = {
            "source": "openalex", "source_id": "W1", "title": "Paper A", "landing_url": "https://example.org/a",
            "retrieved_at": t_a, "raw_sha256": sha, "parser_version": "syn-1", "authors_availability": "missing",
            "missing_fields": nullable, "field_provenance": {k: [{"source": "openalex", "source_id": "W1", "raw_sha256": sha, "raw_field": k}] for k in ["title", "source_id", "landing_url"]}
        }
        row.update({n: None for n in nullable})
        rec_a = PaperRecord.model_validate(row)
        hit_a = RankedHit(canonical_id="paper:A", rank=1, score=0.5, display=rec_a, source_records=[rec_a], source_ranks={"openalex": 1}, conflicts={})
        entry_a = LibraryEntry(canonical_id="paper:A", snapshot_id="s1", saved_at=t_a, hit=hit_a, incomplete_sources=False)

        row_b = dict(row)
        row_b["title"] = "Paper B"
        rec_b = PaperRecord.model_validate(row_b)
        hit_b = RankedHit(canonical_id="paper:B", rank=1, score=0.5, display=rec_b, source_records=[rec_b], source_ranks={"openalex": 1}, conflicts={})
        entry_b = LibraryEntry(canonical_id="paper:B", snapshot_id="s1", saved_at=t_b, hit=hit_b, incomplete_sources=False)

        out_bytes = export_json([entry_a, entry_b])
        exported = json.loads(out_bytes.decode("utf-8"))
        is_inverted = (exported[0]["canonical_id"] == "paper:A")
        results.append({
            "probe": "export_timezone_string_sorting",
            "reproduced": is_inverted,
            "description": "export_json sorts by isoformat string reversing chronological order for mixed timezones"
        })
    except Exception as ex:
        results.append({"probe": "export_timezone_string_sorting", "error": str(ex)})

    # 2. Probe Cache entry with non-success/empty overall (Finding F2)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        try:
            root_cfg_path = Path("D:/Web_mining_20261/scholargraph/configs/public_search.json")
            cfg_dict = json.loads(root_cfg_path.read_text(encoding="utf-8"))
            cfg_dict["data_root"] = "data/public_search/muse"
            local_cfg = tmppath / "cfg.json"
            local_cfg.write_text(json.dumps(cfg_dict), encoding="utf-8")
            config = load_config(local_cfg)

            proj = tmppath / "proj"
            proj.mkdir()
            store = initialize_store(proj, config)

            req = SearchRequest(query="test", sources=["openalex", "arxiv"], top_k=10, cap_per_source=10, year_from=None, year_to=None, refresh=False)
            now_dt = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
            snap = SearchSnapshot(
                schema_version=1,
                contract_version="1.0.0",
                snapshot_id="snap-corrupt-cache",
                request=req,
                config_sha256=digest(config),
                adapter_sha256={"openalex": "b" * 64, "arxiv": "b" * 64},
                source_results=[
                    SourceResult(source="openalex", status="failed", records=[], error=SearchError(kind="timeout", message="err", source="openalex", retry_after_seconds=None, record_index=None), source_total=None, elapsed_seconds=0.1, filter_coverage="none", truncated=False, raw_references=[]),
                    SourceResult(source="arxiv", status="failed", records=[], error=SearchError(kind="timeout", message="err", source="arxiv", retry_after_seconds=None, record_index=None), source_total=None, elapsed_seconds=0.1, filter_coverage="none", truncated=False, raw_references=[]),
                ],
                fusion=FusionResult(hits=[], counts=FusionCounts(raw=0, valid=0, invalid=0, excluded_by_year=0, eligible=0, groups=0, duplicate_excess=0, returned=0)),
                overall="failed",
                fetched_at=now_dt,
                expires_at=now_dt + timedelta(days=1),
            )
            db_path = proj / "data" / "public_search" / "muse" / "library.sqlite3"
            conn = sqlite3.connect(str(db_path))
            c_key = "e" * 64
            conn.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?)", (snap.snapshot_id, snap.model_dump_json(), snap.overall, snap.fetched_at.isoformat(), snap.expires_at.isoformat(), snap.config_sha256))
            conn.execute("INSERT INTO cache VALUES (?, ?, ?)", (c_key, snap.snapshot_id, now_dt.isoformat()))
            conn.commit()
            conn.close()

            loaded = store.load_cache(c_key, now=now_dt + timedelta(minutes=1))
            store.close()

            returned_failed_as_hit = (loaded is not None and loaded.overall == "failed")
            results.append({
                "probe": "cache_accepts_corrupt_failed_overall",
                "reproduced": returned_failed_as_hit,
                "description": "load_cache does not verify overall in ('success', 'empty') before returning hit"
            })
        except Exception as ex:
            results.append({"probe": "cache_accepts_corrupt_failed_overall", "error": str(ex)})

    # 3. Probe RAW_ID_PATTERN convention check (Finding F3)
    try:
        valid_openalex = "openalex-" + "a" * 64
        valid_arxiv = "arxiv-" + "b" * 64
        future_crossref = "crossref-" + "c" * 64

        _validate_raw_id(valid_openalex)
        _validate_raw_id(valid_arxiv)
        crossref_rejected = False
        try:
            _validate_raw_id(future_crossref)
        except StoreError:
            crossref_rejected = True

        results.append({
            "probe": "raw_id_pattern_sources",
            "reproduced": crossref_rejected,
            "description": "RAW_ID_PATTERN strictly limits to openalex/arxiv (safe for W1, requires expansion for EXT-09)"
        })
    except Exception as ex:
        results.append({"probe": "raw_id_pattern_sources", "error": str(ex)})

    return {
        "status": "DIAGNOSTIC_COMPLETE",
        "probe_count": len(results),
        "results": results
    }


if __name__ == "__main__":
    out = run_probe()
    print(json.dumps(out, indent=2))
    sys.exit(0)
