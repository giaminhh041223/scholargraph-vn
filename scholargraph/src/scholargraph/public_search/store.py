"""SQLite cache snapshot library store for EXT-04A, boundary only CLI."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Literal

from .contracts import LibraryEntry
from .contracts import PublicSearchConfig
from .contracts import SearchError
from .contracts import SearchSnapshot
from .contracts import digest
from .contracts import load_config
from .contracts import read_json
from .export import export_bibtex
from .export import export_json

MARKER_NAME = "store.json"
DB_NAME = "library.sqlite3"
RAW_DIR_NAME = "raw"
RAW_ID_PATTERN = re.compile(r"^(openalex|arxiv)-[0-9a-f]{64}$")
CACHE_KEY_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HEX64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class StoreError(RuntimeError):
    """Structured storage failure for future service mapping, never silent."""
    def __init__(self, error: SearchError):
        self.error = error
        super().__init__(error.message)


def _fail(kind: str, message: str) -> None:
    if type(message) is not str or not message.strip():
        message = "storage failure"
    if kind not in ("request", "config", "policy", "auth", "quota", "timeout", "upstream", "schema", "storage"):
        kind = "storage"
    err = SearchError(kind=kind, message=message, source=None, retry_after_seconds=None, record_index=None)
    raise StoreError(err)


def _require_aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime):
        _fail("request", label + " must be datetime")
    tz = value.tzinfo
    if tz is None or value.utcoffset() is None:
        _fail("request", label + " must include timezone")
    return value


def _revalidate_config(config: PublicSearchConfig) -> PublicSearchConfig:
    if not isinstance(config, PublicSearchConfig):
        _fail("config", "config must be PublicSearchConfig")
    raw = config.model_dump_json().encode("utf-8")
    try:
        return PublicSearchConfig.model_validate_json(raw)
    except Exception:
        _fail("config", "config revalidation failed")


def _config_digest(config: PublicSearchConfig) -> str:
    cfg = _revalidate_config(config)
    return digest(cfg)


def _resolve_data_root(project_root: Path, config: PublicSearchConfig) -> Path:
    if not isinstance(project_root, Path):
        _fail("storage", "project root must be Path")
    cfg = _revalidate_config(config)
    data_root_str = cfg.data_root
    if type(data_root_str) is not str:
        _fail("storage", "data root must be str")
    rel = Path(data_root_str)
    if rel.is_absolute():
        _fail("storage", "data root must stay under data public_search")
    parts = rel.parts
    if ".." in parts:
        _fail("storage", "data root must stay under data public_search")
    if len(parts) < 2 or parts[0] != "data" or parts[1] != "public_search":
        _fail("storage", "data root must stay under data public_search")
    try:
        project_resolved = project_root.resolve()
    except Exception:
        _fail("storage", "project root resolve failed")
    if not project_resolved.is_dir():
        _fail("storage", "project root must be directory")
    expected_base = project_resolved / "data" / "public_search"
    candidate = project_resolved.joinpath(data_root_str)
    try:
        data_resolved = candidate.resolve()
    except Exception:
        _fail("storage", "data root resolve failed")
    try:
        data_resolved.relative_to(expected_base)
    except Exception:
        _fail("storage", "data root escapes public_search")
    return data_resolved


def _marker_path(data_root: Path) -> Path:
    return data_root / MARKER_NAME

def _db_path(data_root: Path) -> Path:
    return data_root / DB_NAME


def _raw_dir(data_root: Path) -> Path:
    return data_root / RAW_DIR_NAME


def _read_marker(marker_file: Path, expected_digest: str) -> dict:
    if not marker_file.is_file() or marker_file.is_symlink():
        _fail("storage", "marker missing")
    try:
        data = read_json(marker_file)
    except Exception:
        _fail("storage", "marker corrupt")
    if type(data) is not dict:
        _fail("storage", "marker corrupt")
    keys = set(data.keys())
    if keys != {"schema_version", "contract_version", "config_sha256"}:
        _fail("storage", "marker schema mismatch")
    schema_version = data["schema_version"]
    contract_version = data["contract_version"]
    config_sha256 = data["config_sha256"]
    if type(schema_version) is not int or schema_version != 1:
        _fail("storage", "marker version mismatch")
    if contract_version != "1.0.0":
        _fail("storage", "marker contract mismatch")
    if type(config_sha256) is not str or HEX64_PATTERN.fullmatch(config_sha256) is None:
        _fail("storage", "marker hash mismatch")
    if config_sha256 != expected_digest:
        _fail("config", "config digest mismatch marker")
    return data


def _write_marker_atomic(marker_file: Path, config_digest: str) -> None:
    parent = marker_file.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        _fail("storage", "marker directory create failed")
    payload = {"config_sha256": config_digest, "contract_version": "1.0.0", "schema_version": 1}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix="store-", suffix=".tmp")
        tmp = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(str(tmp), str(marker_file))
    except Exception:
        try:
            if tmp is not None and tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        _fail("storage", "marker write failed")


def _connect_db(db_file: Path) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(str(db_file), timeout=30.0, check_same_thread=False, isolation_level=None)
    except Exception:
        _fail("storage", "db connect failed")
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        _fail("storage", "db pragma failed")
    return conn


def _init_schema(conn: sqlite3.Connection, config_digest: str) -> None:
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS snapshots (snapshot_id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, overall TEXT NOT NULL, fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL, config_sha256 TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS cache (cache_key TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, cached_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS library (canonical_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, saved_at TEXT NOT NULL, entry_json TEXT NOT NULL)")
        conn.execute("DELETE FROM metadata")
        conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("schema_version", "1"))
        conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("contract_version", "1.0.0"))
        conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", ("config_sha256", config_digest))
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        _fail("storage", "db schema init failed")


def _verify_metadata(conn: sqlite3.Connection, expected_digest: str) -> None:
    try:
        rows = list(conn.execute("SELECT key, value FROM metadata"))
    except Exception:
        _fail("storage", "db schema mismatch")
    if len(rows) != 3:
        _fail("storage", "db metadata mismatch")
    mapping: dict[str, str] = {}
    for k, v in rows:
        if type(k) is not str or type(v) is not str:
            _fail("storage", "db metadata mismatch")
        if k in mapping:
            _fail("storage", "db metadata mismatch")
        mapping[k] = v
    keys = set(mapping.keys())
    if keys != {"schema_version", "contract_version", "config_sha256"}:
        _fail("storage", "db metadata mismatch")
    if mapping["schema_version"] != "1":
        _fail("storage", "db version mismatch")
    if mapping["contract_version"] != "1.0.0":
        _fail("storage", "db contract mismatch")
    if HEX64_PATTERN.fullmatch(mapping["config_sha256"]) is None:
        _fail("storage", "db hash mismatch")
    if mapping["config_sha256"] != expected_digest:
        _fail("config", "config digest mismatch db")


def _verify_store(data_root: Path, conn: sqlite3.Connection, expected_digest: str) -> None:
    marker_file = _marker_path(data_root)
    _read_marker(marker_file, expected_digest)
    _verify_metadata(conn, expected_digest)
    raw_dir = _raw_dir(data_root)
    if raw_dir.is_symlink():
        _fail("storage", "raw symlink escape")
    if not raw_dir.is_dir():
        _fail("storage", "raw directory missing")


def _validate_raw_id(raw_id: str) -> None:
    if type(raw_id) is not str:
        _fail("storage", "raw id must be str")
    if RAW_ID_PATTERN.fullmatch(raw_id) is None:
        _fail("storage", "raw id unsafe")


def _raw_path_for(raw_dir: Path, raw_id: str) -> Path:
    _validate_raw_id(raw_id)
    candidate = raw_dir / raw_id
    try:
        base = raw_dir.resolve()
        target = candidate.resolve()
    except Exception:
        _fail("storage", "raw resolve failed")
    try:
        target.relative_to(base)
    except Exception:
        _fail("storage", "raw traversal escape")
    if candidate.is_symlink():
        _fail("storage", "raw symlink escape")
    return candidate


def _write_raw_atomic(raw_dir: Path, raw_id: str, payload: bytes) -> None:
    if type(payload) is not bytes:
        _fail("storage", "raw payload must be bytes")
    dest = _raw_path_for(raw_dir, raw_id)
    if dest.exists():
        if dest.is_symlink() or not dest.is_file():
            _fail("storage", "raw path conflict")
        try:
            existing = dest.read_bytes()
        except Exception:
            _fail("storage", "raw read failed")
        if existing != payload:
            _fail("storage", "raw id immutable different bytes")
        return None
    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(raw_dir), prefix="raw-", suffix=".tmp")
        tmp = Path(tmp_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(str(tmp), str(dest))
    except StoreError:
        raise
    except Exception:
        try:
            if tmp is not None and tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        _fail("storage", "raw write failed")


def _read_raw_checked(raw_dir: Path, raw_id: str, expected_sha: str, expected_count: int) -> bytes:
    _validate_raw_id(raw_id)
    if type(expected_sha) is not str or HEX64_PATTERN.fullmatch(expected_sha) is None:
        _fail("storage", "raw hash mismatch")
    if type(expected_count) is not int or isinstance(expected_count, bool) or expected_count < 0:
        _fail("storage", "raw byte count mismatch")
    dest = _raw_path_for(raw_dir, raw_id)
    if not dest.is_file() or dest.is_symlink():
        _fail("storage", "referenced raw missing")
    try:
        data = dest.read_bytes()
    except Exception:
        _fail("storage", "raw read failed")
    if len(data) != expected_count:
        _fail("storage", "raw byte count mismatch")
    if hashlib.sha256(data).hexdigest() != expected_sha:
        _fail("storage", "raw hash mismatch")
    return data


def _revalidate_snapshot(snapshot: SearchSnapshot) -> SearchSnapshot:
    if not isinstance(snapshot, SearchSnapshot):
        _fail("storage", "snapshot must be SearchSnapshot")
    raw = snapshot.model_dump_json().encode("utf-8")
    try:
        return SearchSnapshot.model_validate_json(raw)
    except Exception:
        _fail("storage", "snapshot revalidation failed")


def _collect_raw_refs(snapshot: SearchSnapshot) -> dict:
    refs: dict[str, tuple[str, int]] = {}
    for result in snapshot.source_results:
        for ref in result.raw_references:
            _validate_raw_id(ref.raw_id)
            if ref.raw_id in refs:
                prev = refs[ref.raw_id]
                if prev[0] != ref.sha256 or prev[1] != ref.byte_count:
                    _fail("storage", "raw reference conflict")
                continue
            refs[ref.raw_id] = (ref.sha256, ref.byte_count)
    return refs


class SQLiteStore:
    """SQLite implementation of PublicStore protocol."""
    def __init__(self, project_root: Path, config: PublicSearchConfig, data_root: Path, conn: sqlite3.Connection, config_digest: str):
        self._project_root = project_root
        self._config = _revalidate_config(config)
        self._data_root = data_root
        self._conn = conn
        self._digest = config_digest
        self._closed = False
        self._lock = threading.Lock()

    def _ensure_open(self) -> None:
        if self._closed:
            _fail("storage", "store closed")

    def load_cache(self, cache_key: str, *, now: datetime) -> SearchSnapshot | None:
        self._ensure_open()
        if type(cache_key) is not str or CACHE_KEY_PATTERN.fullmatch(cache_key) is None:
            _fail("request", "invalid cache key")
        _require_aware(now, "now")
        _verify_store(self._data_root, self._conn, self._digest)
        with self._lock:
            try:
                row = self._conn.execute("SELECT snapshot_id FROM cache WHERE cache_key = ?", (cache_key,)).fetchone()
            except Exception:
                _fail("storage", "cache lookup failed")
            if row is None:
                return None
            snapshot_id = row[0]
            try:
                srow = self._conn.execute("SELECT snapshot_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
            except Exception:
                _fail("storage", "snapshot lookup failed")
            if srow is None:
                _fail("storage", "referenced snapshot missing")
            snapshot_json = srow[0]
        try:
            if isinstance(snapshot_json, str):
                snapshot = SearchSnapshot.model_validate_json(snapshot_json.encode("utf-8"))
            else:
                snapshot = SearchSnapshot.model_validate_json(snapshot_json)
        except Exception:
            _fail("storage", "cached snapshot corrupt")
        if snapshot.config_sha256 != self._digest:
            _fail("storage", "cached snapshot config mismatch")
        if snapshot.overall not in ("success", "empty"):
            _fail("storage", "cached snapshot invalid overall")
        refs = _collect_raw_refs(snapshot)
        raw_dir = _raw_dir(self._data_root)
        for raw_id in refs:
            sha, count = refs[raw_id]
            _read_raw_checked(raw_dir, raw_id, sha, count)
        if now >= snapshot.expires_at:
            return None
        return snapshot

    def save_snapshot(self, snapshot: SearchSnapshot, raw_payloads: dict[str, bytes], *, cache_key: str) -> None:
        self._ensure_open()
        if type(cache_key) is not str or CACHE_KEY_PATTERN.fullmatch(cache_key) is None:
            _fail("request", "invalid cache key")
        if type(raw_payloads) is not dict:
            _fail("storage", "raw payloads must be dict")
        snap = _revalidate_snapshot(snapshot)
        if snap.config_sha256 != self._digest:
            _fail("config", "snapshot config mismatch")
        refs = _collect_raw_refs(snap)
        if set(raw_payloads.keys()) != set(refs.keys()):
            _fail("storage", "raw keyset mismatch")
        for raw_id in refs:
            if raw_id not in raw_payloads:
                _fail("storage", "raw keyset mismatch")
            payload = raw_payloads[raw_id]
            if type(payload) is not bytes:
                _fail("storage", "raw payload must be bytes")
            sha, count = refs[raw_id]
            if len(payload) != count:
                _fail("storage", "raw byte count mismatch")
            if hashlib.sha256(payload).hexdigest() != sha:
                _fail("storage", "raw hash mismatch")
        _verify_store(self._data_root, self._conn, self._digest)
        raw_dir = _raw_dir(self._data_root)
        for raw_id in refs:
            payload = raw_payloads[raw_id]
            _write_raw_atomic(raw_dir, raw_id, payload)
        snapshot_json = snap.model_dump_json()
        overall = snap.overall
        fetched = snap.fetched_at.isoformat()
        expires = snap.expires_at.isoformat()
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                existing = self._conn.execute("SELECT snapshot_json FROM snapshots WHERE snapshot_id = ?", (snap.snapshot_id,)).fetchone()
                if existing is not None:
                    if existing[0] != snapshot_json:
                        self._conn.execute("ROLLBACK")
                        _fail("storage", "snapshot id immutable different bytes")
                else:
                    self._conn.execute("INSERT INTO snapshots (snapshot_id, snapshot_json, overall, fetched_at, expires_at, config_sha256) VALUES (?, ?, ?, ?, ?, ?)", (snap.snapshot_id, snapshot_json, overall, fetched, expires, snap.config_sha256))
                if overall == "success" or overall == "empty":
                    self._conn.execute("INSERT OR REPLACE INTO cache (cache_key, snapshot_id, cached_at) VALUES (?, ?, ?)", (cache_key, snap.snapshot_id, fetched))
                self._conn.execute("COMMIT")
            except StoreError:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                _fail("storage", "snapshot persist failed")
        return None

    def read_snapshot(self, snapshot_id: str) -> SearchSnapshot:
        self._ensure_open()
        if type(snapshot_id) is not str or not snapshot_id.strip():
            _fail("request", "invalid snapshot id")
        _verify_store(self._data_root, self._conn, self._digest)
        with self._lock:
            try:
                row = self._conn.execute("SELECT snapshot_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
            except Exception:
                _fail("storage", "snapshot lookup failed")
            if row is None:
                _fail("request", "unknown snapshot id")
            snapshot_json = row[0]
        try:
            if isinstance(snapshot_json, str):
                snapshot = SearchSnapshot.model_validate_json(snapshot_json.encode("utf-8"))
            else:
                snapshot = SearchSnapshot.model_validate_json(snapshot_json)
        except Exception:
            _fail("storage", "snapshot corrupt")
        if snapshot.config_sha256 != self._digest:
            _fail("storage", "snapshot config mismatch")
        refs = _collect_raw_refs(snapshot)
        raw_dir = _raw_dir(self._data_root)
        for raw_id in refs:
            sha, count = refs[raw_id]
            _read_raw_checked(raw_dir, raw_id, sha, count)
        return snapshot

    def save_paper(self, snapshot_id: str, canonical_id: str, *, now: datetime) -> LibraryEntry:
        self._ensure_open()
        if type(snapshot_id) is not str or not snapshot_id.strip():
            _fail("request", "invalid snapshot id")
        if type(canonical_id) is not str or not canonical_id.strip():
            _fail("request", "invalid canonical id")
        _require_aware(now, "now")
        snapshot = self.read_snapshot(snapshot_id)
        hit = None
        for candidate in snapshot.fusion.hits:
            if candidate.canonical_id == canonical_id:
                hit = candidate
                break
        if hit is None:
            _fail("request", "unknown hit")
        if snapshot.overall == "partial_failure":
            incomplete = True
        else:
            incomplete = False
        with self._lock:
            try:
                existing = self._conn.execute("SELECT entry_json FROM library WHERE canonical_id = ?", (canonical_id,)).fetchone()
            except Exception:
                _fail("storage", "library lookup failed")
            if existing is not None:
                try:
                    if isinstance(existing[0], str):
                        entry = LibraryEntry.model_validate_json(existing[0].encode("utf-8"))
                    else:
                        entry = LibraryEntry.model_validate_json(existing[0])
                except Exception:
                    _fail("storage", "library entry corrupt")
                return entry
            try:
                fresh = LibraryEntry(canonical_id=canonical_id, snapshot_id=snapshot_id, saved_at=now, hit=hit, incomplete_sources=incomplete)
                fresh_json = fresh.model_dump_json()
                fresh_valid = LibraryEntry.model_validate_json(fresh_json.encode("utf-8"))
            except Exception:
                _fail("request", "library entry invalid")
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                double = self._conn.execute("SELECT entry_json FROM library WHERE canonical_id = ?", (canonical_id,)).fetchone()
                if double is not None:
                    self._conn.execute("ROLLBACK")
                    try:
                        if isinstance(double[0], str):
                            entry = LibraryEntry.model_validate_json(double[0].encode("utf-8"))
                        else:
                            entry = LibraryEntry.model_validate_json(double[0])
                    except Exception:
                        _fail("storage", "library entry corrupt")
                    return entry
                self._conn.execute("INSERT INTO library (canonical_id, snapshot_id, saved_at, entry_json) VALUES (?, ?, ?, ?)", (canonical_id, snapshot_id, now.astimezone(timezone.utc).isoformat(), fresh_json))
                self._conn.execute("COMMIT")
            except StoreError:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                _fail("storage", "library persist failed")
            return fresh_valid

    def list_library(self, *, offset: int, limit: int) -> list[LibraryEntry]:
        self._ensure_open()
        if type(offset) is not int or isinstance(offset, bool):
            _fail("request", "invalid paging")
        if type(limit) is not int or isinstance(limit, bool):
            _fail("request", "invalid paging")
        if offset < 0 or limit < 1 or limit > 100:
            _fail("request", "invalid paging")
        _verify_store(self._data_root, self._conn, self._digest)
        with self._lock:
            try:
                rows = list(self._conn.execute("SELECT entry_json FROM library ORDER BY saved_at ASC, canonical_id ASC LIMIT ? OFFSET ?", (limit, offset)).fetchall())
            except Exception:
                _fail("storage", "library list failed")
        out: list[LibraryEntry] = []
        for row in rows:
            try:
                if isinstance(row[0], str):
                    entry = LibraryEntry.model_validate_json(row[0].encode("utf-8"))
                else:
                    entry = LibraryEntry.model_validate_json(row[0])
            except Exception:
                _fail("storage", "library entry corrupt")
            snap = self.read_snapshot(entry.snapshot_id)
            found = False
            for candidate in snap.fusion.hits:
                if candidate.canonical_id == entry.canonical_id:
                    found = True
                    break
            if not found:
                _fail("storage", "library hit missing")
            out.append(entry)
        return out

    def export_library(self, format: Literal["json", "bibtex"]) -> bytes:
        self._ensure_open()
        if format != "json" and format != "bibtex":
            _fail("request", "unknown export format")
        full: list[LibraryEntry] = []
        offset = 0
        while True:
            page = self.list_library(offset=offset, limit=100)
            if len(page) == 0:
                break
            for item in page:
                full.append(item)
            if len(page) < 100:
                break
            offset += 100
            if offset > 100000:
                _fail("storage", "library too large")
        if format == "json":
            return export_json(full)
        return export_bibtex(full)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return None
            try:
                self._conn.close()
            except Exception:
                _fail("storage", "store close failed")
            self._closed = True
            return None


def _has_evidence(data_root: Path) -> bool:
    try:
        items = list(data_root.iterdir())
    except Exception:
        _fail("storage", "evidence check failed")
    return len(items) > 0


def initialize_store(project_root: Path, config: PublicSearchConfig) -> SQLiteStore:
    cfg = _revalidate_config(config)
    config_digest = digest(cfg)
    data_root = _resolve_data_root(project_root, cfg)
    if data_root.exists():
        try:
            looks_dir = data_root.is_dir()
        except Exception:
            _fail("storage", "data root check failed")
        if not looks_dir:
            _fail("storage", "data root not directory")
        if _has_evidence(data_root):
            marker_file = _marker_path(data_root)
            db_file = _db_path(data_root)
            if not marker_file.is_file() or not db_file.is_file():
                _fail("storage", "existing evidence without db marker refusing rebuild")
            _read_marker(marker_file, config_digest)
            conn = _connect_db(db_file)
            try:
                _verify_store(data_root, conn, config_digest)
            except StoreError:
                try:
                    conn.close()
                except Exception:
                    pass
                raise
            return SQLiteStore(project_root, cfg, data_root, conn, config_digest)
    else:
        try:
            data_root.mkdir(parents=True, exist_ok=False)
        except Exception:
            _fail("storage", "data root create failed")
    raw_dir = _raw_dir(data_root)
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        _fail("storage", "raw directory create failed")
    db_file = _db_path(data_root)
    marker_file = _marker_path(data_root)
    if db_file.exists() or marker_file.exists():
        _fail("storage", "unexpected existing store files")
    conn = _connect_db(db_file)
    try:
        _init_schema(conn, config_digest)
    except StoreError:
        try:
            conn.close()
        except Exception:
            pass
        raise
    try:
        _write_marker_atomic(marker_file, config_digest)
    except StoreError:
        try:
            conn.close()
        except Exception:
            pass
        raise
    try:
        _verify_store(data_root, conn, config_digest)
    except StoreError:
        try:
            conn.close()
        except Exception:
            pass
        raise
    return SQLiteStore(project_root, cfg, data_root, conn, config_digest)


def open_existing(project_root: Path, config: PublicSearchConfig) -> SQLiteStore:
    cfg = _revalidate_config(config)
    config_digest = digest(cfg)
    data_root = _resolve_data_root(project_root, cfg)
    if not data_root.is_dir():
        _fail("storage", "store not initialized")
    if data_root.is_symlink():
        _fail("storage", "data root symlink escape")
    marker_file = _marker_path(data_root)
    db_file = _db_path(data_root)
    if not marker_file.is_file() or marker_file.is_symlink():
        _fail("storage", "marker missing")
    if not db_file.is_file() or db_file.is_symlink():
        _fail("storage", "db missing")
    _read_marker(marker_file, config_digest)
    conn = _connect_db(db_file)
    try:
        _verify_store(data_root, conn, config_digest)
    except StoreError:
        try:
            conn.close()
        except Exception:
            pass
        raise
    return SQLiteStore(project_root, cfg, data_root, conn, config_digest)


def _check_storage(config_path: Path, project_path: Path) -> int:
    try:
        cfg = load_config(config_path)
    except Exception:
        print("FAIL: invalid or missing config", file=sys.stderr)
        return 1
    try:
        store = open_existing(project_path, cfg)
    except Exception:
        print("FAIL: storage check failed", file=sys.stderr)
        return 1
    try:
        store.list_library(offset=0, limit=1)
    except Exception:
        try:
            store.close()
        except Exception:
            pass
        print("FAIL: storage check failed", file=sys.stderr)
        return 1
    try:
        store.close()
    except Exception:
        print("FAIL: storage check failed", file=sys.stderr)
        return 1
    print("VALID storage")
    return 0


def main() -> int:
    """Boundary-only storage check, not production search CLI."""
    parser = argparse.ArgumentParser(description="Boundary-only storage check, not production search CLI")
    parser.add_argument("--check-storage", action="store_true", required=False, default=False)
    parser.add_argument("--config", required=False, default=None)
    parser.add_argument("--project-root", required=False, default=None)
    args = parser.parse_args()
    if not args.check_storage:
        print("FAIL: boundary-only check requires --check-storage", file=sys.stderr)
        return 1
    if args.config is None or args.project_root is None:
        print("FAIL: missing required --config or --project-root", file=sys.stderr)
        return 1
    if type(args.config) is not str or type(args.project_root) is not str:
        print("FAIL: invalid paths", file=sys.stderr)
        return 1
    return _check_storage(Path(args.config), Path(args.project_root))


if __name__ == "__main__":
    sys.exit(main())
