"""EXT09 synthetic/mocked adversarial checks; all writes stay in tmp_path."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx
import pytest

from scholargraph.public_search import crossref as cr
from scholargraph.public_search.contracts import PaperRecord, Source

ROOT = Path(__file__).resolve().parents[2]
DOI = "10.1234/synthetic"
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def payload():
    return {"status": "ok", "message-type": "work", "message-version": "1.0.0",
            "message": {"source": "Crossref", "DOI": DOI, "title": ["Tiêu đề synthetic"],
                        "type": "journal-article", "author": [{"given": "Ada", "family": "Example"}],
                        "published": {"date-parts": [[2024, 2, 29]]}, "container-title": ["Synthetic Venue"],
                        "publisher": "Synthetic Publisher", "URL": "https://doi.org/" + DOI,
                        "is-referenced-by-count": 0, "score": 1.0}}


def body(row):
    return json.dumps(row, ensure_ascii=False).encode()


def parse(raw=None, **kwargs):
    return cr.parse_payload(body(payload()) if raw is None else raw, DOI, raw_path="raw.json",
                            synthetic=True, retrieved_at=None, **kwargs)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "_NEXT", 0.0)
    root = tmp_path / "project"
    public = root / "data/public_search"
    public.mkdir(parents=True)
    (root / "configs").mkdir()
    raw_policy = b"synthetic verified policy fixture, not a real policy snapshot"
    (public / "policy.txt").write_bytes(raw_policy)
    config = json.loads((ROOT / "configs/public_crossref.json").read_text())
    config["policy_evidence_path"] = "data/public_search/policy.txt"
    config["policy_evidence_sha256"] = hashlib.sha256(raw_policy).hexdigest()
    path = root / "configs/public_crossref.json"
    path.write_bytes(body(config))
    (public / "payload.json").write_bytes(body(payload()))
    return root, path, public


def original():
    sha = "a" * 64
    fields = {"title": "Original title", "source_id": "W1234", "landing_url": "https://example.org/paper", "doi": DOI}
    nullable = ("abstract", "publication_year", "arxiv_id", "venue", "pdf_url", "license", "open_access_status", "citation_count", "authors")
    row = dict(source="openalex", retrieved_at=NOW, raw_sha256=sha, parser_version="openalex-1.0.0", **fields)
    row.update({key: None for key in nullable})
    row.update(authors_availability="missing", missing_fields=list(nullable),
               field_provenance={key: [{"source": "openalex", "source_id": "W1234", "raw_sha256": sha, "raw_field": key}] for key in fields})
    return PaperRecord.model_validate(row)


def cli(root, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, str(ROOT / "scripts/enrich_public.py"), "--project-root", str(root), *args],
                          env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_mapping_availability_and_frozen_contract():
    parsed = parse()
    assert Source.__args__ == ("openalex", "arxiv")
    assert parsed.metadata.title == "Tiêu đề synthetic"
    assert parsed.metadata.authors == ["Ada Example"]
    assert parsed.metadata.publication_year == 2024 and parsed.metadata.citation_count == 0
    assert parsed.metadata.abstract is None and parsed.unavailable_fields == ["abstract"]
    assert parsed.field_provenance["publication_year"].raw_field == "message.published.date-parts"
    assert parsed.field_provenance["abstract"].availability == "unavailable"
    assert parsed.field_provenance["title"].raw_sha256 == hashlib.sha256(body(payload())).hexdigest()


def test_optional_absence_is_null():
    row = payload()
    for key in ("author", "published", "container-title", "publisher", "URL", "is-referenced-by-count"):
        del row["message"][key]
    parsed = parse(body(row))
    assert set(parsed.unavailable_fields) == {"authors", "publication_year", "venue", "publisher", "landing_url", "citation_count", "abstract"}
    assert all(parsed.field_provenance[key].availability == "unavailable" for key in parsed.unavailable_fields)


def test_original_conflict_preserved():
    record = original()
    before = record.model_dump_json()
    parsed = parse(original=record)
    assert record.model_dump_json() == before and parsed.original == record
    assert parsed.original.title == "Original title" and parsed.metadata.title == "Tiêu đề synthetic"
    conflict = parsed.conflicts["title"]
    assert conflict.original_value == "Original title" and conflict.crossref_value == parsed.metadata.title
    assert conflict.original_evidence == record.model_dump(mode="json")["field_provenance"]["title"]
    assert conflict.crossref_evidence == parsed.field_provenance["title"]


@pytest.mark.parametrize("key", ["source", "DOI", "title", "type"])
def test_required_message_fields_missing(key):
    row = payload(); del row["message"][key]
    with pytest.raises(cr.CrossrefError):
        parse(body(row))


@pytest.mark.parametrize("row", [{"text": "only"}, {"title": "only"}, [], "text", {"status": "ok"}])
def test_text_title_only_and_bad_envelope(row):
    with pytest.raises(cr.CrossrefError):
        parse(body(row))


@pytest.mark.parametrize("field,value", [
    ("source", "Other"), ("DOI", "10.1234/wrong"), ("DOI", "bad"), ("title", []), ("title", "text"),
    ("title", [""]), ("type", 3), ("type", ""), ("abstract", None), ("publisher", 8),
    ("URL", "javascript:alert(1)"), ("container-title", "wrong"), ("author", "wrong"),
    ("author", [{}]), ("author", [{"family": 2}]), ("is-referenced-by-count", -1),
    ("is-referenced-by-count", True), ("score", -1), ("score", float("inf")), ("score", "1"), ("score", True),
    ("published", {"date-parts": [[2024, 2, 30]]}), ("published", {"date-parts": [[2024, 13]]}),
    ("published", {"date-parts": [[True]]}), ("published", {"date-parts": [[2200]]}),
    ("published", {}), ("published", {"date-parts": []}),
])
def test_malformed_used_metadata(field, value):
    row = payload(); row["message"][field] = value
    with pytest.raises(cr.CrossrefError):
        parse(body(row))


@pytest.mark.parametrize("key", ["labels", "split", "qrels", "Held_Out", "relevance-score", "test", "test_labels", "datasetSplit", "split_id", "QRELS_PATH"])
def test_recursive_poison_label_split_rejected(key):
    row = payload(); row["message"]["unknown-public-field"] = [{"nested": {key: 1}}]
    with pytest.raises(cr.CrossrefError, match="forbidden"):
        parse(body(row))


def test_duplicate_keys_and_invalid_utf8():
    for raw in (b'{"status":"ok","status":"ok"}', b"\xff"):
        with pytest.raises(cr.CrossrefError):
            parse(raw)


@pytest.mark.parametrize("field,value", [("pool", "polite"), ("auth_mode", "bearer"), ("interval_seconds", 0.2),
                                         ("concurrency", 2), ("concurrency", True), ("max_retries", 1), ("mailto", "invented@example.org")])
def test_invalid_policy(sandbox, field, value):
    root, cfg, _ = sandbox
    row = json.loads(cfg.read_bytes()); row[field] = value; cfg.write_bytes(body(row))
    with pytest.raises(ValueError):
        cr.load_config(root, cfg)


def test_missing_policy_and_hash_mismatch(sandbox):
    root, cfg, public = sandbox
    (public / "policy.txt").write_bytes(b"corrupted")
    with pytest.raises(cr.CrossrefError, match="hash"):
        cr.load_config(root, cfg)
    (public / "policy.txt").unlink()
    with pytest.raises(OSError):
        cr.load_config(root, cfg)


def test_encoded_exact_lookup_and_headers(sandbox):
    root, cfg, _ = sandbox
    seen = []
    def handler(req):
        seen.append(req)
        return httpx.Response(200, headers={"content-type": "application/json", "x-rate-limit-limit": "5", "x-rate-limit-interval": "1s", "x-concurrency-limit": "1"}, content=body(payload()))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = cr.CrossrefTransport(cr.load_config(root, cfg), client=client)
        assert transport.get("https://doi.org/10.1234/SYNTHETIC") == body(payload())
    assert len(seen) == 1 and seen[0].url.raw_path == b"/works/10.1234%2Fsynthetic"
    assert not seen[0].url.query and "authorization" not in seen[0].headers
    assert seen[0].headers["accept-encoding"] == "identity"
    assert "@" not in seen[0].headers["user-agent"]
    assert transport.audit["headers"]["x-concurrency-limit"] == ["1"]


@pytest.mark.parametrize("status,kind", [(404, "not_found"), (429, "quota"), (403, "auth"), (301, "redirect"), (503, "upstream")])
def test_http_failures_retained_no_retry(sandbox, status, kind):
    root, cfg, public = sandbox
    count = []
    def handler(req):
        count.append(req)
        return httpx.Response(status, headers={"content-type": "application/json", "retry-after": "2"}, content=b'{"error":"synthetic failure"}')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = cr.enrich(root, cfg, public / "run", doi=DOI, client=client)
    assert result["status"] == "failed" and result["error"]["kind"] == kind and len(count) == 1
    assert result["request"]["status_code"] == status
    assert (public / "run/raw.json").read_bytes() == b'{"error":"synthetic failure"}'
    assert result["raw"]["sha256"] == hashlib.sha256((public / "run/raw.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("headers", [
    {"content-type": "text/html"}, {}, {"content-type": "application/json", "x-concurrency-limit": "0"},
    {"content-type": "application/json", "x-rate-limit-limit": "5"},
    {"content-type": "application/json", "x-rate-limit-limit": "0", "x-rate-limit-interval": "1s"},
    {"content-type": "application/json", "x-rate-limit-limit": "5", "x-rate-limit-interval": "nans"},
    {"content-type": "application/json", "content-length": "999999999"},
    {"content-type": "application/json", "retry-after": "invalid"},
    [("content-type", "application/json"), ("content-type", "application/json")],
    {"content-type": "application/json", "content-encoding": "gzip"},
])
def test_invalid_transport_headers(sandbox, headers):
    root, cfg, _ = sandbox
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, headers=headers, content=body(payload())))) as client:
        transport = cr.CrossrefTransport(cr.load_config(root, cfg), client=client)
        with pytest.raises(cr.CrossrefError):
            transport.get(DOI)


def test_streaming_body_cap(sandbox):
    root, cfg, public = sandbox
    row = json.loads(cfg.read_bytes()); row["max_body_bytes"] = 10; cfg.write_bytes(body(row))
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"0123456789"
            yield b"0123456789"
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, headers={"content-type": "application/json"}, stream=Stream()))) as client:
        result = cr.enrich(root, cfg, public / "run", doi=DOI, client=client)
    assert result["status"] == "failed" and result["request"]["complete_body"] is False
    assert len((public / "run/raw.json").read_bytes()) == 10


@pytest.mark.parametrize("exc,kind", [(httpx.ReadTimeout("secret"), "timeout"), (httpx.ConnectError("secret"), "upstream")])
def test_network_failure_redacted(sandbox, exc, kind):
    root, cfg, public = sandbox
    def handler(req):
        raise exc
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = cr.enrich(root, cfg, public / "run", doi=DOI, client=client)
    assert result["error"]["kind"] == kind and "secret" not in json.dumps(result)
    assert result["request"]["attempted"] is True and result["raw"] is None


def test_one_process_concurrency_and_interval(sandbox):
    root, cfg, _ = sandbox
    config = cr.load_config(root, cfg)
    guard = threading.Lock(); active = 0; maximum = 0; starts = []
    def handler(req):
        nonlocal active, maximum
        with guard:
            active += 1; maximum = max(maximum, active); starts.append(time.monotonic())
        time.sleep(0.03)
        with guard:
            active -= 1
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body(payload()))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, ThreadPoolExecutor(max_workers=2) as pool:
        transports = [cr.CrossrefTransport(config, client=client) for _ in range(2)]
        results = list(pool.map(lambda transport: transport.get(DOI), transports))
    assert results == [body(payload()), body(payload())]
    assert maximum == 1 and starts[1] - starts[0] >= 0.99


def test_synthetic_run_atomic_integrity_overwrite_and_no_benchmark(sandbox, monkeypatch):
    root, cfg, public = sandbox
    original_open = Path.open
    def checked(path, *args, **kwargs):
        assert not any(word in str(path).lower() for word in ("benchmark", "qrels", "splits"))
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", checked)
    result = cr.enrich(root, cfg, public / "run", doi=DOI, payload_path=public / "payload.json")
    assert result["status"] == "success" and result["synthetic"] is True
    assert result["enrichment"]["retrieved_at"] is None and result["request"]["attempted"] is False
    assert result["raw"]["sha256"] == hashlib.sha256((public / "run/raw.json").read_bytes()).hexdigest()
    before = (public / "run/result.json").read_bytes()
    with pytest.raises(FileExistsError):
        cr.enrich(root, cfg, public / "run", doi=DOI, payload_path=public / "payload.json")
    assert (public / "run/result.json").read_bytes() == before
    assert not list((public / "run").glob("*.tmp"))


@pytest.mark.parametrize("mode", ["missing_config", "missing_policy", "missing_payload", "bad_doi", "malformed", "labels", "quota_fixture", "wrong_doi", "score", "missing_doi", "extra_argument"])
def test_cli_failures_exit_one(sandbox, mode):
    root, cfg, public = sandbox
    args = ["--doi", DOI, "--output-dir", "data/public_search/run", "--payload", "data/public_search/payload.json"]
    row = payload()
    if mode == "missing_config": cfg.unlink()
    elif mode == "missing_policy": (public / "policy.txt").unlink()
    elif mode == "missing_payload": (public / "payload.json").unlink()
    elif mode == "bad_doi": args[1] = "bad"
    elif mode == "missing_doi": args = args[2:]
    elif mode == "extra_argument": args += ["--wrong"]
    elif mode == "malformed": (public / "payload.json").write_bytes(b"title-only")
    else:
        if mode == "labels": row["message"]["extra"] = {"split": "test"}
        elif mode == "quota_fixture": row = {"status": "error", "message": "quota exceeded"}
        elif mode == "wrong_doi": row["message"]["DOI"] = "10.1234/other"
        elif mode == "score": row["message"]["score"] = -1
        (public / "payload.json").write_bytes(body(row))
    proc = cli(root, *args)
    assert proc.returncode == 1, proc.stderr
    assert json.loads(proc.stdout)["status"] == "failed"


def test_cli_record_and_help_success(sandbox):
    root, cfg, public = sandbox
    record = original(); path = public / "original.json"; path.write_text(record.model_dump_json(), encoding="utf-8")
    before = path.read_bytes()
    proc = cli(root, "--record-json", "data/public_search/original.json", "--output-dir", "data/public_search/run", "--payload", "data/public_search/payload.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["enrichment"]["original"] == record.model_dump(mode="json") and path.read_bytes() == before
    assert "title" in result["enrichment"]["conflicts"]
    assert cli(root, "--help").returncode == 0
    assert cli(root, "--doi", DOI, "--output-dir", "data/public_search/run", "--payload", "data/public_search/payload.json").returncode == 1


def test_cli_standalone_without_pythonpath(sandbox):
    root, cfg, public = sandbox
    env = dict(os.environ); env.pop("PYTHONPATH", None)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/enrich_public.py"), "--project-root", str(root),
                           "--doi", DOI, "--output-dir", "data/public_search/standalone", "--payload", "data/public_search/payload.json"],
                          env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0 and json.loads(proc.stdout)["status"] == "success"


@pytest.mark.parametrize("status", [404, 429, 403, 302])
def test_cli_mocked_http_subprocess_exit_one(sandbox, status):
    root, cfg, public = sandbox
    # Run the actual script/main in a new interpreter with an injected HTTP transport.
    code = """
import httpx, runpy, sys
from scholargraph.public_search import crossref as cr
original = cr.CrossrefTransport
status = int(sys.argv[1])
client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, headers={'content-type':'application/json','retry-after':'1'}, content=b'{"error":"synthetic"}')))
cr.CrossrefTransport = lambda config, **kwargs: original(config, client=client)
script, root = sys.argv[2:4]
sys.argv = [script, '--project-root', root, '--doi', '10.1234/synthetic', '--output-dir', 'data/public_search/http-cli']
runpy.run_path(script, run_name='__main__')
"""
    env = dict(os.environ); env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run([sys.executable, "-c", code, str(status), str(ROOT / "scripts/enrich_public.py"), str(root)],
                          env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 1, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "failed" and result["request"]["status_code"] == status
    assert (public / "http-cli/raw.json").exists()


def test_cli_bad_record_missing_doi_and_recursive_label(sandbox):
    root, cfg, public = sandbox
    for index, row in enumerate(({"title": "only"}, original().model_dump(mode="json"))):
        if index == 1:
            row["field_provenance"]["title"][0]["labels"] = [1]
        (public / "record.json").write_bytes(body(row))
        proc = cli(root, "--record-json", "data/public_search/record.json", "--output-dir", f"data/public_search/run-{index}", "--payload", "data/public_search/payload.json")
        assert proc.returncode == 1


def test_paths_outside_public_and_config_missing_fields(sandbox):
    root, cfg, public = sandbox
    with pytest.raises(cr.CrossrefError):
        cr.enrich(root, cfg, root / "forbidden", doi=DOI, payload_path=public / "payload.json")
    row = json.loads(cfg.read_bytes()); del row["policy_evidence_sha256"]; cfg.write_bytes(body(row))
    proc = cli(root, "--doi", DOI, "--output-dir", "data/public_search/run", "--payload", "data/public_search/payload.json")
    assert proc.returncode == 1
