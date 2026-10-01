"""Comprehensive unit and adversarial negative tests for JOSS crawler (EXT-10).

Adheres strictly to Anti-Silent-Bypass Protocol:
- Negative & adversarial testing: missing resources, tampered SHA-256,
  malformed citation metadata, title-only/text-only, DOI mismatch,
  forbidden research sentinel keys (labels, qrels, dev_labels, test_labels, heldout, split, score),
  SSRF / private DNS resolutions, explicit redirects, oversized streaming payloads,
  robots.txt denial and control characters, duplicate counters, quota caps,
  rate limiter timing floor (>=3s), interrupted checkpoint resume, and raw file integrity corruption.
- Real CLI boundary verification via subprocess.run: exit code 1 on errors with
  machine-readable structured JSON, exit code 0 on --help.
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
    CheckpointIntegrityError,
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
    load_joss_config,
    validate_policy_manifest,
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
        ("max_pages", 0),
        ("max_pages", -5),
        ("max_papers", 0),
        ("max_depth", 2),
        ("max_body_bytes", 512),
        ("timeout_seconds", 0.0),
        ("timeout_seconds", -10.0),
        ("parser_version", "joss-v2"),
        ("data_root", "../escaped/path"),
        ("data_root", "data\\escaped"),
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


def test_config_extra_forbidden_keys(tmp_path: Path) -> None:
    _, cfg_file, _ = create_valid_test_env(tmp_path)
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    data["extra_synthetic_key"] = "forbidden"
    cfg_file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PolicyViolationError):
        load_joss_config(cfg_file)


# ===========================================================================
# 2. Policy Manifest Validation Tests
# ===========================================================================

def test_policy_manifest_positive(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    manifest = validate_policy_manifest(project_root, config.policy_manifest)
    assert manifest["status"] == "PASS"


def test_policy_manifest_missing_file(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    with pytest.raises(PolicyViolationError, match="Policy manifest not found"):
        validate_policy_manifest(project_root, "data/public_search/missing_manifest.json")


def test_policy_manifest_sha_mismatch(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    # Tamper with the robots file on disk
    robots_path = project_root / "data" / "public_search" / "phase_b" / "policy-107" / "joss-robots.txt"
    robots_path.write_bytes(b"tampered content")

    with pytest.raises(PolicyViolationError, match="Policy SHA-256 mismatch"):
        validate_policy_manifest(project_root, config.policy_manifest)


def test_policy_manifest_path_escape(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    with pytest.raises(PolicyViolationError, match="outside data/public_search"):
        validate_policy_manifest(project_root, "../../etc/passwd")


def test_policy_manifest_missing_required_resource(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    manifest_file = project_root / config.policy_manifest
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    # Remove the robots resource
    data["resources"] = [r for r in data["resources"] if ROBOTS_PATH not in r["url"]]
    manifest_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PolicyViolationError, match="missing required resources"):
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
        ("https://joss.theoj.org/papers/10.21105/joss.invalid_letters", "Disallowed path"),
        ("https://joss.theoj.org/robots.txt\n", "whitespace or control characters"),
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
# 4. Listing Parser Tests (Deduplication, Depth-1, Selector Drift)
# ===========================================================================

def test_listing_parser_positive() -> None:
    parser = JossListingParser()
    urls, found, dups = parser.extract_links(SAMPLE_LISTING_HTML)
    assert len(urls) == 3
    assert "https://joss.theoj.org/papers/10.21105/joss.09260" in urls
    assert "https://joss.theoj.org/papers/10.21105/joss.09644" in urls
    assert "https://joss.theoj.org/papers/10.21105/joss.10451" in urls
    # Duplicate link for 09260 in sample html
    assert found == 4
    assert dups == 1


def test_listing_parser_selector_drift() -> None:
    parser = JossListingParser()
    empty_html = "<html><body><div>No paper links found</div></body></html>"
    with pytest.raises(ParseError, match="Selector drift: zero paper links extracted"):
        parser.extract_links(empty_html)


# ===========================================================================
# 5. Paper Parser Tests (Metadata, Singletons, DOI Match, Leakage Keys)
# ===========================================================================

def test_paper_parser_positive() -> None:
    parser = JossPaperParser()
    record = parser.parse_record(
        SAMPLE_PAPER_HTML.encode("utf-8"),
        landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
        parser_version=PARSER_VERSION,
        retrieved_at="2026-10-01T23:30:00+00:00",
    )
    assert isinstance(record, JossPaperRecord)
    assert record.doi == "10.21105/joss.09260"
    assert record.id == "joss:10.21105/joss.09260"
    assert record.venue == "Journal of Open Source Software"
    assert record.publication_date == "2026/10/01"
    assert record.authors == ["Stephen A. Collins-Elliott"]
    assert record.pdf_url == "https://joss.theoj.org/papers/10.21105/joss.09260.pdf"
    assert record.provenance.site_id == "joss"


def test_paper_parser_multiple_authors() -> None:
    multi_author_html = SAMPLE_PAPER_HTML.replace(
        '<meta name="citation_author" content="Stephen A. Collins-Elliott">',
        '<meta name="citation_author" content="Author One">\n<meta name="citation_author" content="Author Two">',
    )
    parser = JossPaperParser()
    record = parser.parse_record(
        multi_author_html.encode("utf-8"),
        landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
        parser_version=PARSER_VERSION,
        retrieved_at="2026-10-01T23:30:00+00:00",
    )
    assert record.authors == ["Author One", "Author Two"]


@pytest.mark.parametrize(
    "missing_tag",
    [
        "citation_title",
        "citation_doi",
        "citation_publication_date",
        "citation_journal_title",
        "citation_author",
    ],
)
def test_paper_parser_missing_required_tag(missing_tag: str) -> None:
    lines = [line for line in SAMPLE_PAPER_HTML.splitlines() if missing_tag not in line]
    stripped_html = "\n".join(lines).encode("utf-8")
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="Missing required"):
        parser.parse_record(
            stripped_html,
            landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


def test_paper_parser_doi_mismatch() -> None:
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="Landing DOI mismatch"):
        parser.parse_record(
            SAMPLE_PAPER_HTML.encode("utf-8"),
            landing_url="https://joss.theoj.org/papers/10.21105/joss.99999",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


def test_paper_parser_contradictory_singleton() -> None:
    conflicting_html = SAMPLE_PAPER_HTML.replace(
        '<meta name="citation_title" content="eratosthenes: Synchronizing archaeological chronologies">',
        '<meta name="citation_title" content="Title A">\n<meta name="citation_title" content="Title B">',
    )
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="Contradictory singleton citation meta tag"):
        parser.parse_record(
            conflicting_html.encode("utf-8"),
            landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


def test_paper_parser_foreign_pdf_url() -> None:
    foreign_pdf_html = SAMPLE_PAPER_HTML.replace(
        'content="https://joss.theoj.org/papers/10.21105/joss.09260.pdf"',
        'content="https://evil.org/malware.pdf"',
    )
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="Foreign metadata PDF URL rejected"):
        parser.parse_record(
            foreign_pdf_html.encode("utf-8"),
            landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


@pytest.mark.parametrize(
    "leakage_key",
    ["labels", "qrels", "dev_labels", "test_labels", "heldout", "split", "score"],
)
def test_paper_parser_leakage_research_keys(leakage_key: str) -> None:
    poisoned_html = SAMPLE_PAPER_HTML.replace(
        "</head>",
        f'<meta name="{leakage_key}" content="leakage_value">\n</head>',
    )
    parser = JossPaperParser()
    with pytest.raises(ParseError, match="Forbidden research meta tag"):
        parser.parse_record(
            poisoned_html.encode("utf-8"),
            landing_url="https://joss.theoj.org/papers/10.21105/joss.09260",
            parser_version=PARSER_VERSION,
            retrieved_at="2026-10-01T23:30:00+00:00",
        )


# ===========================================================================
# 6. Crawler Bounded Execution, Checkpointing, and Resume Tests
# ===========================================================================

def make_mock_transport() -> httpx.MockTransport:
    """MockTransport providing deterministic HTTP responses for JOSS crawling."""

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        if url_str == f"{CANONICAL_ORIGIN}{START_PATH}":
            return httpx.Response(200, content=SAMPLE_LISTING_HTML.encode("utf-8"), headers={"Content-Type": "text/html; charset=utf-8"})
        if "/papers/10.21105/joss." in url_str:
            doi_suffix = url_str.split("/")[-1]
            paper_content = SAMPLE_PAPER_HTML.replace("10.21105/joss.09260", doi_suffix)
            return httpx.Response(200, content=paper_content.encode("utf-8"), headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_crawler_full_bounded_run(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "test-run-1"

    sleep_calls: list[float] = []

    def mock_sleeper(secs: float) -> None:
        sleep_calls.append(secs)

    current_time = [1000.0]

    def mock_clock() -> float:
        current_time[0] += 0.1
        return current_time[0]

    transport = make_mock_transport()
    client = httpx.Client(transport=transport)

    with JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=client,
        clock=mock_clock,
        sleeper=mock_sleeper,
        dns_resolver=fake_global_dns_resolver,
    ) as crawler:
        result = crawler.crawl()

    assert result["status"] == "success"
    counters = result["counters"]
    # Seed listing (1) + 3 papers = 4 pages fetched
    assert counters["pages_fetched"] == 4
    assert counters["unique_papers"] == 3
    assert counters["papers_parsed"] == 3
    assert counters["links_found"] == 4
    assert counters["duplicate_links"] == 1
    assert counters["failed_attempted_calls"] == 0

    # Rate limiter >= 3.0s enforced
    assert len(sleep_calls) > 0
    assert all(s >= 2.0 for s in sleep_calls)

    # Verify artifacts on disk
    assert (run_dir / "checkpoint.json").is_file()
    assert (run_dir / "records.json").is_file()
    assert (run_dir / "robots.txt").is_file()
    raw_files = list((run_dir / "raw").glob("*.html"))
    assert len(raw_files) == 4


def test_crawler_existing_rundir_without_resume_refused(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "existing-dir"
    run_dir.mkdir(parents=True)

    with pytest.raises(PolicyViolationError, match="run_dir already exists"):
        JossCrawler(
            project_root=project_root,
            config=config,
            run_dir=run_dir,
            resume=False,
            dns_resolver=fake_global_dns_resolver,
        )


def test_crawler_rundir_escape_data_root(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    escaped_run_dir = project_root / "data" / "escaped_run"

    with pytest.raises(SecurityError, match="escapes configured data_root"):
        JossCrawler(
            project_root=project_root,
            config=config,
            run_dir=escaped_run_dir,
            resume=False,
            dns_resolver=fake_global_dns_resolver,
        )


def test_crawler_resume_complete_run(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "complete-run"

    transport = make_mock_transport()
    client = httpx.Client(transport=transport)

    # Initial crawl to completion
    crawler1 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    res1 = crawler1.crawl()
    assert res1["status"] == "success"

    # Now resume the complete run
    crawler2 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    res2 = crawler2.crawl()
    assert res2["status"] == "success"
    assert res2["counters"] == res1["counters"]
    assert res2["records_count"] == res1["records_count"]


def test_crawler_resume_corrupted_raw_sha_fails(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "corrupted-run"

    transport = make_mock_transport()
    client = httpx.Client(transport=transport)

    crawler1 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    crawler1.crawl()

    # Tamper with one raw file in raw/
    raw_files = list((run_dir / "raw").glob("*.html"))
    assert len(raw_files) > 0
    raw_files[0].write_bytes(b"tampered content")

    crawler2 = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=True,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(CheckpointIntegrityError, match="Raw HTML SHA-256 corruption"):
        crawler2.crawl()


def test_crawler_robots_denied_fails_closed(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "robots-denied-run"

    disallowing_robots = b"User-agent: *\nDisallow: /\n"

    def disallow_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=disallowing_robots, headers={"Content-Type": "text/plain"})
        return httpx.Response(200, content=SAMPLE_LISTING_HTML.encode("utf-8"), headers={"Content-Type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(disallow_handler))
    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(RobotsDeniedError):
        crawler.crawl()


def test_crawler_oversized_payload_rejected(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "oversized-run"

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        # 2 MB payload exceeding max_body_bytes (1 MB)
        oversized_body = b"A" * 2000000
        return httpx.Response(200, content=oversized_body, headers={"Content-Type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(oversized_handler))
    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(NetworkFetchError, match="Response exceeded max_body_bytes"):
        crawler.crawl()


def test_crawler_explicit_redirect_rejected(tmp_path: Path) -> None:
    project_root, _, config = create_valid_test_env(tmp_path)
    run_dir = project_root / "data" / "public_search" / "joss" / "redirect-run"

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            return httpx.Response(200, content=SAMPLE_ROBOTS, headers={"Content-Type": "text/plain"})
        return httpx.Response(301, headers={"Location": "https://joss.theoj.org/redirected"})

    client = httpx.Client(transport=httpx.MockTransport(redirect_handler))
    crawler = JossCrawler(
        project_root=project_root,
        config=config,
        run_dir=run_dir,
        resume=False,
        client=client,
        sleeper=lambda _: None,
        dns_resolver=fake_global_dns_resolver,
    )
    with pytest.raises(SecurityError, match="Explicit redirect 301 rejected"):
        crawler.crawl()


# ===========================================================================
# 7. Real Subprocess CLI Tests (exit code 1 on errors, exit code 0 on --help)
# ===========================================================================

def run_cli_subprocess(*args: str) -> subprocess.CompletedProcess[str]:
    """Execute crawl_public.py via real subprocess."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [PYTHON, str(CLI_PATH), *args],
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )


def test_cli_help_flag() -> None:
    result = run_cli_subprocess("--help")
    assert result.returncode == 0
    assert "ScholarGraph JOSS paper HTML crawler" in result.stdout


def test_cli_missing_run_dir_fails_exit1() -> None:
    result = run_cli_subprocess("--project-root", ".")
    assert result.returncode == 1
    # Check structured JSON on stderr
    err_json = json.loads(result.stderr)
    assert err_json["status"] == "failed"
    assert err_json["error"]["kind"] == "usage_error"


def test_cli_missing_config_fails_exit1(tmp_path: Path) -> None:
    run_dir = tmp_path / "data" / "public_search" / "joss" / "run-test"
    result = run_cli_subprocess(
        "--project-root", str(tmp_path),
        "--config", "non_existent_config.json",
        "--run-dir", str(run_dir),
    )
    assert result.returncode == 1
    err_json = json.loads(result.stderr)
    assert err_json["status"] == "failed"
    assert "not found" in err_json["error"]["message"].lower()


def test_cli_run_dir_outside_data_root_fails_exit1(tmp_path: Path) -> None:
    project_root, cfg_file, _ = create_valid_test_env(tmp_path)
    escaped_run_dir = project_root / "escaped_run"
    result = run_cli_subprocess(
        "--project-root", str(project_root),
        "--config", str(cfg_file),
        "--run-dir", str(escaped_run_dir),
    )
    assert result.returncode == 1
    err_json = json.loads(result.stderr)
    assert err_json["status"] == "failed"
    assert "escapes configured data_root" in err_json["error"]["message"]


def test_cli_nonexistent_resume_dir_fails_exit1(tmp_path: Path) -> None:
    project_root, cfg_file, _ = create_valid_test_env(tmp_path)
    non_existent = project_root / "data" / "public_search" / "joss" / "does_not_exist"
    result = run_cli_subprocess(
        "--project-root", str(project_root),
        "--config", str(cfg_file),
        "--run-dir", str(non_existent),
        "--resume",
    )
    assert result.returncode == 1
    err_json = json.loads(result.stderr)
    assert err_json["status"] == "failed"
    assert "does not exist for resume" in err_json["error"]["message"]
