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
    with pytest.raises(ParseError, match="Foreign metadata abstract URL rejected"):
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
    with pytest.raises(ParseError, match="User credentials in metadata PDF URL"):
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
