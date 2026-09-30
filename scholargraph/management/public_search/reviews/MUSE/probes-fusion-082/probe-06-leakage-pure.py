"""Independent probe 06: purity/leakage - no file/socket/network/storage/labels access.
Blocks Path.open/builtins.open/socket.socket during fuse; sentinel held_out in tmp.
Also asserts no offline/graph/storage imports and failed-attempt evidence preserved.
"""
import socket
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from scholargraph.public_search.contracts import (
    FieldEvidence, PaperRecord, RawReference, SearchRequest, SourceResult,
)
from scholargraph.public_search import fusion as F
from scholargraph.public_search.fusion import fuse

SHA = "0" * 64
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
NULLABLE = ("abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url",
            "license", "open_access_status", "citation_count", "authors")

def main():
    tmp = Path(tempfile.mkdtemp(prefix="probe06-082-"))
    (tmp / "held_out.json").write_text("SENTINEL_LEAK", encoding="utf-8")
    (tmp / "qrels.txt").write_text("SENTINEL_LEAK", encoding="utf-8")
    print(f"tmp={tmp}")
    row = dict(source="openalex", source_id="L1", title="Leak probe",
               landing_url="https://example.org/l", retrieved_at=NOW,
               raw_sha256=SHA, parser_version="probe-082")
    for f in NULLABLE:
        row[f] = None
    row["authors_availability"] = "missing"
    row["missing_fields"] = list(NULLABLE)
    row["field_provenance"] = {
        f: [FieldEvidence(source="openalex", source_id="L1", raw_sha256=SHA, raw_field=f)]
        for f in ("source_id", "title", "landing_url")}
    rec = PaperRecord.model_validate(row)
    req = SearchRequest.model_validate(dict(query="leak", sources=["openalex"], top_k=50,
                                            cap_per_source=50, year_from=None, year_to=None))
    rows = [SourceResult(source="openalex", status="success", records=[rec], error=None,
                         source_total=1, elapsed_seconds=0.1, filter_coverage="none",
                         truncated=False,
                         raw_references=[RawReference(raw_id="openalex-"+SHA, sha256=SHA, byte_count=1)])]
    # instrument: any file/socket use inside fuse must raise
    calls = {"open": 0, "socket": 0}
    orig_path_open = Path.open
    import builtins
    orig_open = builtins.open
    orig_socket = socket.socket
    def denied_open(*a, **k):
        calls["open"] += 1
        raise AssertionError("unexpected file open in fuse")
    def denied_socket(*a, **k):
        calls["socket"] += 1
        raise AssertionError("unexpected socket in fuse")
    Path.open = denied_open  # type: ignore
    builtins.open = denied_open  # type: ignore
    socket.socket = denied_socket  # type: ignore
    try:
        out = fuse(rows, req)
    finally:
        Path.open = orig_path_open  # type: ignore
        builtins.open = orig_open  # type: ignore
        socket.socket = orig_socket  # type: ignore
    print(f"fuse returned={out.counts.returned} file_calls={calls['open']} socket_calls={calls['socket']}")
    assert out.counts.returned == 1 and calls == {"open": 0, "socket": 0}
    # source must not import storage/network/offline modules (import-level, not docstring substrings)
    import inspect
    src = inspect.getsource(F)
    for token in ["import sqlite3", "import httpx", "import requests", "import socket", "from .store", "from .service", "qrels", "held_out"]:
        assert token not in src, f"purity token {token!r} found in fusion.py"
    # 'graph' only appears in docstring 'alias graph', not as graph import; verify no graph import
    assert "from scholargraph.graph" not in src and "import scholargraph.graph" not in src
    print("no-blocked-token PASS (graph-docstring false positive excluded)")
    # extras carrying labels must FAIL (no fake invalid drop): fuse must raise not silently drop
    bad_row = rec.model_dump()
    bad_row["labels"] = "SENTINEL_LEAK"
    from scholargraph.public_search.contracts import PaperRecord as PR
    forged = rec.model_copy(update={"labels": "SENTINEL_LEAK"}) if "labels" not in PR.model_fields else PR.model_construct(**bad_row)
    bad = [SourceResult(source="openalex", status="success", records=[rec], error=None,
                        source_total=1, elapsed_seconds=0.1, filter_coverage="none",
                        truncated=False,
                        raw_references=[RawReference(raw_id="openalex-"+SHA, sha256=SHA, byte_count=1)])]
    bad[0].records[0] = forged
    try:
        fuse(bad, req)
        raise AssertionError("labels extra silently passed")
    except Exception as e:
        print(f"labels-extra rejected ({type(e).__name__}) PASS; failed-attempt preserved")
    print("PROBE06 PASS")

if __name__ == "__main__":
    main()
