"""Comprehensive unit and adversarial negative tests for JOSS crawler (EXT-10).

Adheres strictly to Anti-Silent-Bypass Protocol and R1 Review Regressions:
- Checkpoint poison rejection: missing counters, negative counters, missing schema/status/frontier,
  altered title (reparsed from raw), research leakage sentinels (score, test_labels, qrels),
  missing/corrupted records.json on complete resume.
- Selector drift and parse failures on resume: cached listing re-parsed; cached paper failures
  re-evaluated, never silently bypassed or completed with 0 records.
- Path confinement and symlinks: rejection of data_root=data/benchmarks, absolute paths,
  traversal escaping, and symlink detection.
- Robots parser boundary: rejection of non-robots HTML; Crawl-delay strictly honored.
- Content-Type strictness: rejection of text/htmlbad and missing headers.
- Metadata URL security: foreign abstract URLs and userinfo PDF URLs rejected.
- Standalone CLI execution without PYTHONPATH: --help exits 0, invalid args/missing config exits 1.
- Network interruption resume: recovery without duplicate records or duplicate pages.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

import httpx
import pytest

from scholargraph.public_search.site_crawler import (
    CANONICAL_ORIGIN,
    PARSER_VERSION,
    ROBOTS_PATH,
    START_PATH,
    CheckpointCounters,
    CheckpointIntegrityError,
    CheckpointModel,
    CheckpointVisitedEntry,
    CrawlerError,
    JossConfig,
    JossCrawler,
    JossListingParser,
    JossPaperParser,
    JossPaperRecord,
    NetworkFetchError,
    ParseError,
    PolicyViolationError,
    RateLimiter,
    RobotsDeniedError,
    SecurityError,
    guard_confinement_and_symlinks,
    load_joss_config,
    validate_policy_manifest,
    validate_robots_directives,
    validate_url_and_dns,
)

ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts" / "crawl_public.py"
PYTHON = sys.executable

# Standard test fixtures
SAMPLE_ROBOTS = b"# See https://www.robotstxt.org/robotstxt.html\nUser-agent: *\nDisallow:\n"

SAMPLE_LISTING_HTML = """<!DOCTYPE html>
<html>
<body>
  <div class="paper-card">
    <h2><a href="https://joss.theoj.org/papers/10.21105/joss.09260">Paper 9260</a></h2>
    <div class="doi"><a href="/papers/10.21105/joss.09260#comments">10.21105/joss.09260</a></div>
  </div>
  <div class="paper-card">
    <h2><a href="/papers/10.21105/joss.09644">Paper 9644</a></h2>
  </div>
  <div class="paper-card">
    <h2><a href="https://joss.theoj.org/papers/10.21105/joss.10451">Paper 10451</a></h2>
  </div>
  <div class="other">
    <a href="/about">About</a>
    <a href="https://external.org/other">External</a>
  </div>
</body>
</html>
"""

SAMPLE_PAPER_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>JOSS: eratosthenes</title>
  <meta name="citation_title" content="eratosthenes: Synchronizing archaeological chronologies">
  <meta name="citation_author" content="Stephen A. Collins-Elliott">
  <meta name="citation_publication_date" content="2026/10/01">
  <meta name="citation_journal_title" content="Journal of Open Source Software">
  <meta name="citation_doi" content="10.21105/joss.09260">
  <meta name="citation_issn" content="2475-9066">
  <meta name="citation_volume" content="11">
  <meta name="citation_issue" content="126">
  <meta name="citation_pdf_url" content="https://joss.theoj.org/papers/10.21105/joss.09260.pdf">
  <meta name="citation_abstract_html_url" content="https://joss.theoj.org/papers/10.21105/joss.09260">
</head>
<body>
  <h1>eratosthenes</h1>
</body>
</html>
"""


def fake_global_dns_resolver(hostname: str) -> list[str]:
    """Mock DNS resolver returning a valid public global IPv4 address."""
    return ["93.184.216.34"]


def fake_private_dns_resolver(hostname: str) -> list[str]:
    """Mock DNS resolver returning private/loopback IPs."""
    return ["127.0.0.1", "10.0.0.5"]


def create_valid_test_env(tmp_path: Path) -> tuple[Path, Path, JossConfig]:
    """Create a self-contained valid test directory structure with mock policy files."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)

    policy_dir = project_root / "data" / "public_search" / "phase_b" / "policy-107"
    policy_dir.mkdir(parents=True)

    robots_file = policy_dir / "joss-robots.txt"
    robots_file.write_bytes(SAMPLE_ROBOTS)

    about_file = policy_dir / "joss-about.txt"
    about_file.write_text("About JOSS", encoding="utf-8")

    list_file = policy_dir / "joss-list.txt"
    list_file.write_text(SAMPLE_LISTING_HTML, encoding="utf-8")

    paper_file = policy_dir / "joss-paper.txt"
    paper_file.write_text(SAMPLE_PAPER_HTML, encoding="utf-8")

    manifest = {
        "status": "PASS",
        "resources": [
            {
                "url": f"{CANONICAL_ORIGIN}{ROBOTS_PATH}",
                "status": 200,
                "raw_path": "data/public_search/phase_b/policy-107/joss-robots.txt",
                "sha256": hashlib.sha256(robots_file.read_bytes()).hexdigest(),
                "retrieved_at": "2026-10-01T23:30:30+07:00",
            },
            {
                "url": f"{CANONICAL_ORIGIN}/about",
                "status": 200,
                "raw_path": "data/public_search/phase_b/policy-107/joss-about.txt",
                "sha256": hashlib.sha256(about_file.read_bytes()).hexdigest(),
                "retrieved_at": "2026-10-01T23:30:30+07:00",
            },
            {
                "url": f"{CANONICAL_ORIGIN}{START_PATH}",
                "status": 200,
                "raw_path": "data/public_search/phase_b/policy-107/joss-list.txt",
                "sha256": hashlib.sha256(list_file.read_bytes()).hexdigest(),
                "retrieved_at": "2026-10-01T23:30:30+07:00",
            },
            {
                "url": f"{CANONICAL_ORIGIN}/papers/10.21105/joss.09260",
                "status": 200,
                "raw_path": "data/public_search/phase_b/policy-107/joss-paper.txt",
                "sha256": hashlib.sha256(paper_file.read_bytes()).hexdigest(),
                "retrieved_at": "2026-10-01T23:30:30+07:00",
            },
        ],
    }
    manifest_file = policy_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    cfg_dict = {
        "schema_version": 1,
        "site_id": "joss",
        "origin": CANONICAL_ORIGIN,
        "start_url": f"{CANONICAL_ORIGIN}{START_PATH}",
        "robots_url": f"{CANONICAL_ORIGIN}{ROBOTS_PATH}",
        "conditions_url": f"{CANONICAL_ORIGIN}/about",
        "policy_manifest": "data/public_search/phase_b/policy-107/manifest.json",
        "user_agent": "ScholarGraphPublicCrawler/1.0",
        "min_interval_seconds": 3.0,
        "max_pages": 5,
        "max_papers": 3,
        "max_depth": 1,
        "max_body_bytes": 1048576,
        "timeout_seconds": 30.0,
        "parser_version": PARSER_VERSION,
        "data_root": "data/public_search/joss",
    }
    cfg_file = project_root / "config.json"
    cfg_file.write_text(json.dumps(cfg_dict, indent=2), encoding="utf-8")

    config = JossConfig.model_validate(cfg_dict)
    return project_root, cfg_file, config


def make_mock_transport() -> httpx.MockTransport:
    """MockTransport providing deterministic HTTP responses for JOSS crawling with strict DOI replacement."""

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        if url_str == f"{CANONICAL_ORIGIN}{START_PATH}":
            return httpx.Response(200, content=SAMPLE_LISTING_HTML.encode("utf-8"), headers={"Content-Type": "text/html; charset=utf-8"})
        if "/papers/10.21105/joss." in url_str:
            doi = url_str.split("/papers/")[-1].split("#")[0].split("?")[0]
            paper_content = SAMPLE_PAPER_HTML.replace("10.21105/joss.09260", doi)
            return httpx.Response(200, content=paper_content.encode("utf-8"), headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


# ===========================================================================
# 1. Config Validation Tests (Positive and Adversarial Negative)
# ===========================================================================

def test_config_positive(tmp_path: Path) -> None:
    _, cfg_file, _ = create_valid_test_env(tmp_path)
    loaded = load_joss_config(cfg_file)
    assert loaded.site_id == "joss"
    assert loaded.min_interval_seconds == 3.0
    assert loaded.max_papers == 3


@pytest.mark.parametrize(
    "corrupt_field, bad_val",
    [
        ("schema_version", 2),
        ("schema_version", "1"),
        ("site_id", "arxiv"),
        ("origin", "http://joss.theoj.org"),
        ("start_url", "https://joss.theoj.org/all_papers"),
        ("robots_url", "https://joss.theoj.org/robots.html"),
        ("conditions_url", "https://joss.theoj.org/terms"),
        ("min_interval_seconds", 2.99),
        ("min_interval_seconds", -1.0),
        ("min_interval_seconds", 65.0),
        ("max_pages", 0),
        ("max_pages", 101),
        ("max_papers", 0),
        ("max_papers", 51),
        ("max_depth", 2),
        ("max_body_bytes", 512),
        ("max_body_bytes", 20000000),
        ("timeout_seconds", 0.0),
        ("timeout_seconds", -10.0),
        ("timeout_seconds", 200.0),
        ("parser_version", "joss-v2"),
        ("data_root", "data/benchmarks"),
        ("data_root", "D:/Web_mining_20261/external"),
        ("data_root", "../escaped/path"),
        ("data_root", "data\\escaped"),
        ("user_agent", "   "),
        ("user_agent", "Bad\nAgent"),
    ],
)
def test_config_negative_adversarial(tmp_path: Path, corrupt_field: str, bad_val: object) -> None:
    _, cfg_file, _ = create_valid_test_env(tmp_path)
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    data[corrupt_field] = bad_val
    cfg_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PolicyViolationError):
        load_joss_config(cfg_file)


def test_config_duplicate_json_keys(tmp_path: Path) -> None:
    bad_json = '{"schema_version": 1, "schema_version": 1, "site_id": "joss"}'
    cfg_file = tmp_path / "dup.json"
    cfg_file.write_text(bad_json, encoding="utf-8")
    with pytest.raises(PolicyViolationError, match="Duplicate key"):
        load_joss_config(cfg_file)


# ===========================================================================
# 2. Policy Manifest Validation Tests
# ===========================================================================

def test_policy_manifest_positive(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    manifest = validate_policy_manifest(project_root, config.policy_manifest)
    assert manifest["status"] == "PASS"


def test_policy_manifest_sha_mismatch(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    robots_path = project_root / "data" / "public_search" / "phase_b" / "policy-107" / "joss-robots.txt"
    robots_path.write_bytes(b"tampered content")

    with pytest.raises(PolicyViolationError, match="Policy SHA-256 mismatch"):
        validate_policy_manifest(project_root, config.policy_manifest)


# ===========================================================================
# 3. SSRF & URL Security Tests
# ===========================================================================

def test_url_and_dns_positive(tmp_path: Path) -> None:
    _, _, config = create_valid_test_env(tmp_path)
    validate_url_and_dns("https://joss.theoj.org/robots.txt", config, dns_resolver=fake_global_dns_resolver)
    validate_url_and_dns("https://joss.theoj.org/papers/published.html", config, dns_resolver=fake_global_dns_resolver)
    validate_url_and_dns("https://joss.theoj.org/papers/10.21105/joss.09260", config, dns_resolver=fake_global_dns_resolver)


@pytest.mark.parametrize(
    "bad_url, exc_pattern",
    [
        ("http://joss.theoj.org/robots.txt", "scheme must be 'https'"),
        ("https://user:pass@joss.theoj.org/robots.txt", "userinfo credentials"),
        ("https://joss.theoj.org:8080/robots.txt", "Non-standard port"),
        ("https://foreign.org/papers/published.html", "Foreign host rejected"),
        ("https://joss.theoj.org/papers/published.html?page=2", "Query parameters disallowed"),
        ("https://joss.theoj.org/papers/published.html#section", "URL fragments disallowed"),
        ("https://joss.theoj.org/papers/../admin", "Path traversal"),
        ("https://joss.theoj.org/papers/%2e%2e/admin", "Path traversal"),
        ("https://joss.theoj.org/admin/dashboard", "Disallowed path"),
    ],
)
def test_url_validation_negative(tmp_path: Path, bad_url: str, exc_pattern: str) -> None:
    _, _, config = create_valid_test_env(tmp_path)
    with pytest.raises(SecurityError, match=exc_pattern):
        validate_url_and_dns(bad_url, config, dns_resolver=fake_global_dns_resolver)


def test_ssrf_private_dns_rejection(tmp_path: Path) -> None:
    _, _, config = create_valid_test_env(tmp_path)
    with pytest.raises(SecurityError, match="SSRF protection: Disallowed non-global IP"):
        validate_url_and_dns("https://joss.theoj.org/robots.txt", config, dns_resolver=fake_private_dns_resolver)


# ===========================================================================
# 4. Strict Robots Parser Boundary & Rate Limiting
# ===========================================================================

def test_robots_malformed_html_rejected() -> None:
    garbage_robots = "<html><head><title>404</title></head><body>Not robots</body></html>"
    with pytest.raises(RobotsDeniedError, match="Malformed robots.txt directive"):
        validate_robots_directives(garbage_robots)


def test_robots_unrecognized_directive_rejected() -> None:
    bad_directive_robots = "User-agent: *\nUnknown-Directive: True\nDisallow: /admin"
    with pytest.raises(RobotsDeniedError, match="unrecognized directive 'unknown-directive'"):
        validate_robots_directives(bad_directive_robots)


def test_robots_crawl_delay_stricter(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "delay-run"

    robots_with_delay = b"User-agent: *\nCrawl-delay: 10\nDisallow:\n"

    def delay_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=robots_with_delay, headers={"Content-Type": "text/plain"})
        if url_str == f"{CANONICAL_ORIGIN}{START_PATH}":
            return httpx.Response(200, content=SAMPLE_LISTING_HTML.encode("utf-8"), headers={"Content-Type": "text/html"})
        doi = url_str.split("/papers/")[-1]
        content = SAMPLE_PAPER_HTML.replace("10.21105/joss.09260", doi)
        return httpx.Response(200, content=content.encode("utf-8"), headers={"Content-Type": "text/html"})

    sleep_calls: list[float] = []
    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=httpx.MockTransport(delay_handler)),
        sleeper=lambda s: sleep_calls.append(s),
        dns_resolver=fake_global_dns_resolver,
    )
    crawler.crawl()
    # Crawl-delay of 10s should be honored
    assert any(s >= 9.9 for s in sleep_calls)


# ===========================================================================
# 5. Paper Parser Tests (Metadata, DOI, Sentinels, Foreign URLs)
# ===========================================================================

def test_paper_parser_positive() -> None:
    parser = JossPaperParser()
    record = parser.parse_record(
        SAMPLE_PAPER_HTML.encode("utf-8"),
        landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
        parser_version=PARSER_VERSION,
        retrieved_at="2026-10-01T23:30:00+00:00",
    )
    assert record.doi == "10.21105/joss.09260"
    assert record.title == "eratosthenes: Synchronizing archaeological chronologies"


def test_paper_parser_foreign_abstract_url_fails() -> None:
    foreign_abs_html = SAMPLE_PAPER_HTML.replace(
        '<meta name="citation_abstract_html_url" content="https://joss.theoj.org/papers/10.21105/joss.09260">',
        '<meta name="citation_abstract_html_url" content="https://external.org/papers/10.21105/joss.09260">',
    )
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="Foreign metadata URL rejected"):
        parser.parse_record(
            foreign_abs_html.encode("utf-8"),
            landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


def test_paper_parser_pdf_userinfo_fails() -> None:
    bad_pdf_html = SAMPLE_PAPER_HTML.replace(
        'content="https://joss.theoj.org/papers/10.21105/joss.09260.pdf"',
        'content="https://user:pass@joss.theoj.org/papers/10.21105/joss.09260.pdf"',
    )
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="User credentials in metadata URL"):
        parser.parse_record(
            bad_pdf_html.encode("utf-8"),
            landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


def test_strict_content_type_rejects_bad_media_type(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "bad-ct-run"

    def bad_ct_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        # Return invalid media type text/htmlbad
        return httpx.Response(200, content=SAMPLE_LISTING_HTML.encode("utf-8"), headers={"Content-Type": "text/htmlbad"})

    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=httpx.MockTransport(bad_ct_handler)),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(NetworkFetchError, match="does not match expected"):
        crawler.crawl()


# ===========================================================================
# 6. Checkpoint Poison & Resume Reparsing Regressions (R1-01)
# ===========================================================================

def test_crawler_full_bounded_run_and_complete_resume(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "test-run-1"

    crawler1 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    res1 = crawler1.crawl()
    assert res1["status"] == "success"
    assert res1["counters"]["pages_fetched"] == 4
    assert res1["counters"]["unique_papers"] == 3

    # Resume complete run verifies integrity and returns records
    crawler2 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    res2 = crawler2.crawl()
    assert res2["status"] == "success"
    assert res2["records_count"] == 3


def test_checkpoint_poison_missing_counters(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "poison-counters"

    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    crawler.crawl()

    chk_file = run_dir / "checkpoint.json"
    chk_data = json.loads(chk_file.read_text(encoding="utf-8"))
    del chk_data["counters"]
    chk_file.write_text(json.dumps(chk_data), encoding="utf-8")

    resume_crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(CheckpointIntegrityError, match="Checkpoint schema validation failed"):
        resume_crawler.crawl()


def test_checkpoint_poison_negative_counter(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "poison-neg"

    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    crawler.crawl()

    chk_file = run_dir / "checkpoint.json"
    chk_data = json.loads(chk_file.read_text(encoding="utf-8"))
    chk_data["counters"]["pages_fetched"] = -99
    chk_file.write_text(json.dumps(chk_data), encoding="utf-8")

    resume_crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(CheckpointIntegrityError):
        resume_crawler.crawl()


def test_checkpoint_poison_altered_title_raw_unchanged(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "poison-title"

    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    crawler.crawl()

    # Alter title in checkpoint without changing raw file
    chk_file = run_dir / "checkpoint.json"
    chk_data = json.loads(chk_file.read_text(encoding="utf-8"))
    chk_data["records"][0]["title"] = "Tampered Poisoned Title"
    chk_file.write_text(json.dumps(chk_data), encoding="utf-8")
    (run_dir / "records.json").write_text(json.dumps(chk_data["records"]), encoding="utf-8")

    resume_crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(CheckpointIntegrityError, match="Discrepancy detected between raw HTML and checkpoint record"):
        resume_crawler.crawl()


def test_checkpoint_poison_sentinel_keys(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "poison-sentinel"

    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    crawler.crawl()

    chk_file = run_dir / "checkpoint.json"
    chk_data = json.loads(chk_file.read_text(encoding="utf-8"))
    chk_data["records"][0]["score"] = 0.99
    chk_file.write_text(json.dumps(chk_data), encoding="utf-8")

    resume_crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(CheckpointIntegrityError, match="Checkpoint schema validation failed"):
        resume_crawler.crawl()


def test_checkpoint_missing_records_json_fails(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "missing-records"

    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    crawler.crawl()

    (run_dir / "records.json").unlink()

    resume_crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=make_mock_transport()),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(CheckpointIntegrityError, match="records.json missing on complete checkpoint"):
        resume_crawler.crawl()


# ===========================================================================
# 7. Selector Drift and Quota Cap Resume Regressions (R1-02)
# ===========================================================================

def test_selector_drift_resume_reparses_cached_listing(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "selector-drift-resume"

    drift_listing = "<html><body><div>Zero paper links here</div></body></html>"

    def drift_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        return httpx.Response(200, content=drift_listing.encode("utf-8"), headers={"Content-Type": "text/html"})

    # Run 1 fails with ParseError on selector drift
    crawler1 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=httpx.MockTransport(drift_handler)),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(ParseError, match="Selector drift"):
        crawler1.crawl()

    # Resume must reparse cached listing and FAIL again, never complete 0!
    crawler2 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=httpx.MockTransport(drift_handler)),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(ParseError, match="Selector drift"):
        crawler2.crawl()


def test_malformed_paper_at_budget_resume(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "budget-fail-resume"

    # Set max_pages to 2 (1 listing + 1 paper)
    config = config.model_copy(update={"max_pages": 2})

    malformed_paper = "<html><head><title>No Citation Tags</title></head><body>Title Only</body></html>"

    def fail_paper_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        if url_str == f"{CANONICAL_ORIGIN}{START_PATH}":
            return httpx.Response(200, content=SAMPLE_LISTING_HTML.encode("utf-8"), headers={"Content-Type": "text/html"})
        return httpx.Response(200, content=malformed_paper.encode("utf-8"), headers={"Content-Type": "text/html"})

    crawler1 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=httpx.Client(transport=httpx.MockTransport(fail_paper_handler)),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(ParseError):
        crawler1.crawl()

    # Resume must re-evaluate and fail, not silently mark complete with 0 records
    crawler2 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=httpx.Client(transport=httpx.MockTransport(fail_paper_handler)),
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(ParseError):
        crawler2.crawl()


# ===========================================================================
# 8. Real Subprocess CLI Tests (Clean Env without PYTHONPATH)
# ===========================================================================

def test_cli_standalone_clean_env_no_pythonpath() -> None:
    """Ensure scripts/crawl_public.py boots in clean environment without PYTHONPATH."""
    clean_env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PATH": os.environ.get("PATH", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }
    result = subprocess.run(
        [PYTHON, str(CLI_PATH), "--help"],
        text=True,
        capture_output=True,
        env=clean_env,
        timeout=30,
    )
    assert result.returncode == 0
    assert "ScholarGraph JOSS paper HTML crawler" in result.stdout


def test_cli_missing_config_clean_env(tmp_path: Path) -> None:
    clean_env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PATH": os.environ.get("PATH", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }
    result = subprocess.run(
        [
            PYTHON, str(CLI_PATH),
            "--project-root", str(tmp_path),
            "--config", "nonexistent_cfg.json",
            "--run-dir", str(tmp_path / "data" / "public_search" / "joss" / "r1"),
        ],
        text=True,
        capture_output=True,
        env=clean_env,
        timeout=30,
    )
    assert result.returncode == 1
    err_json = json.loads(result.stderr)
    assert err_json["status"] == "failed"
    assert err_json["counters"] is None


def test_cli_empty_query_fails_before_network(tmp_path: Path) -> None:
    project_root, cfg_file, _ = create_valid_test_env(tmp_path)
    result = subprocess.run(
        [
            PYTHON, str(CLI_PATH),
            "--project-root", str(project_root),
            "--config", str(cfg_file),
            "--run-dir", str(project_root / "data" / "public_search" / "joss" / "r-query"),
            "--query", "   ",
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1
    err_json = json.loads(result.stderr)
    assert err_json["status"] == "failed"
    assert "cannot be empty" in err_json["error"]["message"].lower()
    assert err_json["counters"] is None


# R3 reproductions: all temporary fixtures are synthetic, never live data.
class AdvancingClock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


def offline_crawler(root, config, run_dir, *, resume=False, handler=None, dns=fake_global_dns_resolver, clock=None):
    tick = clock if clock is not None else AdvancingClock()
    return JossCrawler(root, config, run_dir, resume=resume,
                       client=httpx.Client(transport=httpx.MockTransport(handler) if handler is not None else make_mock_transport()),
                       clock=tick, sleeper=tick.sleep, dns_resolver=dns)


def checkpoint(run_dir):
    return json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("mode", ["schema", "timestamp", "time_order", "hash", "parser", "visited_time", "visited_hash", "visited_url",
                                   "provenance", "meta_fields", "links", "duplicate", "frontier", "premature_complete", "records_corrupt", "raw_missing", "raw_corrupt", "labels"])
def test_r3_semantic_poison_before_http(tmp_path, mode):
    root, _, config = create_valid_test_env(tmp_path)
    run_dir = root / config.data_root / "run"
    offline_crawler(root, config, run_dir).crawl()
    cp = checkpoint(run_dir)
    if mode == "schema": cp["schema_version"] = 42
    elif mode == "timestamp": cp["created_at"] = "INVALID"
    elif mode == "time_order": cp["created_at"] = "2099-01-01T00:00:00+00:00"
    elif mode == "hash": cp["config_hash"] = "not-a-hash"
    elif mode == "parser": cp["records"][0]["parser_version"] = "evil"
    elif mode == "visited_time": cp["visited"][1]["retrieved_at"] = "1900-01-01T00:00:00+00:00"
    elif mode == "visited_hash": cp["visited"][1]["config_hash"] = "0" * 64
    elif mode == "visited_url": cp["visited"][1]["url"] = "https://foreign.org/paper"
    elif mode == "provenance": cp["records"][0]["provenance"]["raw_sha256"] = "0" * 64
    elif mode == "meta_fields": cp["records"][0]["provenance"]["meta_fields"] = ["citation_fake"]
    elif mode == "links": cp["counters"].update(links_found=0, duplicate_links=100)
    elif mode == "duplicate":
        cp["records"].append(copy.deepcopy(cp["records"][0])); cp["visited"].append(copy.deepcopy(cp["visited"][1]))
        cp["counters"].update(pages_fetched=5, papers_parsed=4, unique_papers=4)
    elif mode == "frontier": cp["frontier"] = ["https://foreign.org/paper"]
    elif mode == "premature_complete":
        cp["records"] = cp["records"][:1]; cp["visited"] = cp["visited"][:2]
        cp["fetch_attempts"] = cp["fetch_attempts"][:3]
        cp["frontier"] = [CANONICAL_ORIGIN + "/papers/10.21105/joss.09644", CANONICAL_ORIGIN + "/papers/10.21105/joss.10451"]
        cp["counters"].update(pages_fetched=2, papers_parsed=1, unique_papers=1)
    elif mode == "raw_missing": (run_dir / "raw" / (cp["visited"][1]["raw_sha256"] + ".html")).unlink()
    elif mode == "raw_corrupt": (run_dir / "raw" / (cp["visited"][1]["raw_sha256"] + ".html")).write_bytes(b"POISON")
    elif mode == "labels": cp["records"][0]["provenance"]["meta_fields"] = ["test_labels"]
    (run_dir / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
    (run_dir / "records.json").write_text("POISON" if mode == "records_corrupt" else json.dumps(cp["records"]), encoding="utf-8")
    calls = []
    def no_http(request):
        calls.append(str(request.url))
        raise AssertionError("poison must fail before HTTP")
    with pytest.raises(CheckpointIntegrityError):
        offline_crawler(root, config, run_dir, resume=True, handler=no_http).crawl()
    assert calls == []


@pytest.mark.parametrize("max_pages", [2, 5])
def test_r3_cached_unparsed_paper_never_refetched_or_completed(tmp_path, max_pages):
    root, _, config = create_valid_test_env(tmp_path)
    config = JossConfig.model_validate({**config.model_dump(), "max_pages": max_pages})
    run = root / config.data_root / "run"
    calls = []
    normal = make_mock_transport()
    def handler(req):
        calls.append(str(req.url))
        if req.url.path not in (ROBOTS_PATH, START_PATH):
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<title>title-only</title>")
        return normal.handle_request(req)
    with pytest.raises(ParseError):
        offline_crawler(root, config, run, handler=handler).crawl()
    before = checkpoint(run)
    assert before["status"] == "failed" and before["counters"]["pages_fetched"] == 2
    assert before["counters"]["failed_attempted_calls"] == 0
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(ParseError):
        offline_crawler(root, config, run, resume=True, handler=handler).crawl()
    assert calls == [] and checkpoint(run) == before


def test_r3_network_interruption_resume_exact_counts(tmp_path):
    root, _, config = create_valid_test_env(tmp_path)
    run = root / config.data_root / "run"
    calls = []
    normal = make_mock_transport()
    failed = False
    def handler(req):
        nonlocal failed
        calls.append(str(req.url))
        if str(req.url).endswith("joss.09644") and not failed:
            failed = True
            raise httpx.ConnectError("synthetic interruption")
        return normal.handle_request(req)
    with pytest.raises(NetworkFetchError):
        offline_crawler(root, config, run, handler=handler).crawl()
    initial = checkpoint(run)
    assert initial["counters"]["pages_fetched"] == 2 and initial["counters"]["failed_attempted_calls"] == 1
    result = offline_crawler(root, config, run, resume=True, handler=handler).crawl()
    assert result["http_attempts"] == 7 and result["http_successes"] == 6
    assert result["counters"] == dict(pages_fetched=4, links_found=4, duplicate_links=1, papers_parsed=3, unique_papers=3, failed_attempted_calls=1)
    assert calls.count(CANONICAL_ORIGIN + "/papers/10.21105/joss.09260") == 1
    assert calls.count(CANONICAL_ORIGIN + START_PATH) == 1
    assert calls.count(CANONICAL_ORIGIN + ROBOTS_PATH) == 2
    assert checkpoint(run)["created_at"] == initial["created_at"]


@pytest.mark.parametrize("robots", [b"<html>garbage</html>", b"User-agent: *\nCrawl-delay: nan\n", b"User-agent: *\nCrawl-delay: inf\n",
                                    b"User-agent: *\nRequest-rate: broken\n", b"User-agent: *\nRequest-rate: 0/3\n", b"\xff", b"User-agent: *\nDisallow: /\n"])
def test_r3_robots_failure_retains_bytes_and_checkpoint(tmp_path, robots):
    root, _, config = create_valid_test_env(tmp_path)
    run = root / config.data_root / "run"
    def handler(req):
        assert req.url.path == ROBOTS_PATH
        return httpx.Response(200, content=robots, headers={"content-type": "text/plain"})
    with pytest.raises(RobotsDeniedError):
        offline_crawler(root, config, run, handler=handler).crawl()
    cp = checkpoint(run)
    assert cp["status"] == "failed" and cp["counters"]["failed_attempted_calls"] == 0
    attempts = cp["fetch_attempts"]
    assert len(attempts) == 1 and attempts[0]["attempted"] and attempts[0]["success"]
    assert (run / attempts[0]["raw_path"]).read_bytes() == robots
    assert attempts[0]["raw_sha256"] == hashlib.sha256(robots).hexdigest()


def test_r3_request_rate_conservative_and_robots_history_unique(tmp_path):
    root, _, config = create_valid_test_env(tmp_path)
    run = root / config.data_root / "run"
    tick = AdvancingClock(); starts = []
    normal = make_mock_transport()
    def handler(req):
        starts.append(tick())
        if req.url.path == ROBOTS_PATH:
            return httpx.Response(200, content=b"User-agent: *\nRequest-rate: 2/20\nDisallow:\n", headers={"content-type":"text/plain"})
        return normal.handle_request(req)
    offline_crawler(root, config, run, handler=handler, clock=tick).crawl()
    assert all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    offline_crawler(root, config, run, resume=True, handler=handler, clock=tick).crawl()
    files = list((run / "robots").glob("*.txt"))
    assert len(files) == 2 and files[0].name != files[1].name


def test_r3_dns_preflight_zero_http_attempts(tmp_path):
    root, _, config = create_valid_test_env(tmp_path)
    run = root / config.data_root / "run"
    calls = []
    def forbidden(req):
        calls.append(req); raise AssertionError("must not send")
    with pytest.raises(SecurityError):
        offline_crawler(root, config, run, dns=fake_private_dns_resolver, handler=forbidden).crawl()
    cp = checkpoint(run)
    assert calls == [] and cp["counters"]["failed_attempted_calls"] == 0
    assert cp["fetch_attempts"][0]["attempted"] is False and cp["fetch_attempts"][0]["raw_path"] is None


@pytest.mark.parametrize("tag", ["citation_title", "citation_doi", "citation_author", "citation_journal_title", "citation_publication_date"])
def test_r3_each_required_citation_missing(tmp_path, tag):
    import re
    raw = re.sub(r'\s*<meta name="' + tag + r'"[^>]+>', "", SAMPLE_PAPER_HTML).encode()
    with pytest.raises(ParseError):
        JossPaperParser().parse_record(raw, CANONICAL_ORIGIN + "/papers/10.21105/joss.09260", PARSER_VERSION, "2026-10-01T23:30:00+07:00")


@pytest.mark.parametrize("mode", ["doi", "calendar", "singleton", "mixed_blank_author", "label", "timestamp", "parser"])
def test_r3_parser_adversarial_metadata(mode):
    raw = SAMPLE_PAPER_HTML; timestamp = "2026-10-01T23:30:00+07:00"; version = PARSER_VERSION
    if mode == "doi": raw = raw.replace('name="citation_doi" content="10.21105/joss.09260"', 'name="citation_doi" content="10.21105/joss.99999"')
    elif mode == "calendar": raw = raw.replace("2026/10/01", "2026/02/30")
    elif mode == "singleton": raw += '<meta name="citation_title" content="CONFLICT">'
    elif mode == "mixed_blank_author": raw += '<meta name="citation_author" content=" ">'
    elif mode == "label": raw += '<meta name="test_labels" content="1">'
    elif mode == "timestamp": timestamp = "INVALID"
    elif mode == "parser": version = "evil"
    with pytest.raises(ParseError):
        JossPaperParser().parse_record(raw.encode(), CANONICAL_ORIGIN + "/papers/10.21105/joss.09260", version, timestamp)


@pytest.mark.parametrize("mode", ["bodycap", "redirect", "duplicate_header", "deadline"])
def test_r3_transport_bounds(tmp_path, mode):
    from scholargraph.public_search.site_crawler import stream_bounded_fetch
    root, _, config = create_valid_test_env(tmp_path)
    tick = AdvancingClock(); audit = {}
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            if mode == "deadline": tick.now += config.timeout_seconds + 1
            yield b"x" * (config.max_body_bytes + 1 if mode == "bodycap" else 20)
    headers = [("content-type", "text/plain")]
    if mode == "duplicate_header": headers.append(("content-type", "text/plain"))
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(302 if mode == "redirect" else 200, headers=headers, stream=Body()))) as client:
        with pytest.raises((NetworkFetchError, SecurityError)):
            stream_bounded_fetch(client, config.robots_url, config, RateLimiter(3.0, clock=tick, sleeper=tick.sleep), "text/plain",
                                 dns_resolver=fake_global_dns_resolver, clock=tick, attempt_audit=audit)
    assert audit["attempted"] is True
    if mode == "bodycap": assert len(audit["body"]) == config.max_body_bytes and audit["complete_body"] is False


@pytest.mark.parametrize("resource", ["joss-robots.txt", "joss-about.txt", "joss-list.txt", "joss-paper.txt"])
def test_r3_missing_policy_raw_failed_checkpoint(tmp_path, resource):
    root, _, config = create_valid_test_env(tmp_path)
    (root / config.policy_manifest).parent.joinpath(resource).unlink()
    run = root / config.data_root / "run"
    with pytest.raises(PolicyViolationError):
        offline_crawler(root, config, run).crawl()
    cp = checkpoint(run)
    assert cp["status"] == "failed" and cp["fetch_attempts"] == [] and cp["counters"]["failed_attempted_calls"] == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows native junction required")
@pytest.mark.parametrize("location", ["base", "raw", "robots", "ancestor"])
def test_r3_native_windows_junction_rejected(tmp_path, location):
    root, _, config = create_valid_test_env(tmp_path)
    target = tmp_path / "outside-project"; target.mkdir(); (target / "sentinel").write_bytes(b"unchanged")
    base = root / config.data_root
    run = base / "run"
    if location in {"raw", "robots"}:
        run.mkdir(parents=True); junction = run / location
    elif location == "ancestor":
        base.mkdir(parents=True); junction = base / "linked"; run = junction / "run"
    else: junction = base
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    command = "New-Item -ItemType Junction -Path " + quote(junction) + " -Target " + quote(target) + " | Out-Null"
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert junction.is_junction() and not junction.is_symlink()
    with pytest.raises(SecurityError):
        offline_crawler(root, config, run, resume=location in {"raw", "robots"})
    assert (target / "sentinel").read_bytes() == b"unchanged" and not (target / "run").exists()


def test_r3_real_cli_subprocess_poison_and_cached_parse(tmp_path):
    root, cfg, config = create_valid_test_env(tmp_path)
    run = root / config.data_root / "run"
    normal = make_mock_transport()
    def bad(req):
        if req.url.path not in {ROBOTS_PATH, START_PATH}:
            return httpx.Response(200, headers={"content-type":"text/html"}, content=b"<title>only</title>")
        return normal.handle_request(req)
    with pytest.raises(ParseError): offline_crawler(root, config, run, handler=bad).crawl()
    code = '''import httpx,runpy,sys
from scholargraph.public_search import site_crawler as m
original=m.JossCrawler
class Offline(original):
 def __init__(self, **kw):
  def forbid(req): raise AssertionError("Cached parse/poison must fail before HTTP")
  super().__init__(**kw, client=httpx.Client(transport=httpx.MockTransport(forbid)), dns_resolver=lambda _: ["93.184.216.34"], sleeper=lambda _:None)
m.JossCrawler=Offline
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name="__main__")
'''
    env = dict(os.environ); env["PYTHONPATH"] = str(ROOT / "src")
    args = [PYTHON, "-c", code, str(CLI_PATH), "--project-root", str(root), "--config", str(cfg), "--run-dir", str(run), "--resume"]
    proc = subprocess.run(args, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 1
    result = json.loads(proc.stderr); assert result["error"]["kind"] == "parse_error" and result["counters"]["pages_fetched"] == 2
    cp = checkpoint(run); cp["schema_version"] = 42; (run / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
    proc = subprocess.run(args, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 1 and json.loads(proc.stderr)["counters"] is None
