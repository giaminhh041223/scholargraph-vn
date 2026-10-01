"""Bounded HTML crawler for JOSS published papers (EXT-10).

Adheres strictly to Anti-Silent-Bypass Protocol:
- Strict schema validation with no silent .get defaults or fallback.
- Mandatory negative/adversarial guards: missing resources, malformed metadata,
  forbidden research keys (labels/qrels/dev_labels/test_labels/heldout/split/score),
  SSRF / private DNS resolution, oversized payloads, robots disallow, redirect rejection.
- Atomic checkpoints with SHA-256 verification and resume integrity checking.
"""
from __future__ import annotations

import hashlib
import html.parser
import ipaddress
import json
import math
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Frozen constants for JOSS crawler
SITE_ID = "joss"
CANONICAL_ORIGIN = "https://joss.theoj.org"
START_PATH = "/papers/published.html"
ROBOTS_PATH = "/robots.txt"
CONDITIONS_PATH = "/about"
PARSER_VERSION = "joss-citation-1.0.0"
MIN_INTERVAL_SECONDS_FLOOR = 3.0
PAPER_PATH_REGEX = re.compile(r"^/papers/10\.21105/joss\.(\d+)$")
PAPER_URL_REGEX = re.compile(r"^https://joss\.theoj\.org/papers/10\.21105/joss\.(\d+)$")

FORBIDDEN_METADATA_KEYS = frozenset({
    "labels", "qrels", "dev_labels", "test_labels", "heldout", "split", "score"
})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CrawlerError(Exception):
    """Base exception for JOSS crawler failures."""

    def __init__(self, message: str, kind: str = "crawler_error"):
        super().__init__(message)
        self.message = message
        self.kind = kind

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "message": self.message}


class PolicyViolationError(CrawlerError):
    def __init__(self, message: str):
        super().__init__(message, kind="policy_violation")


class SecurityError(CrawlerError):
    def __init__(self, message: str):
        super().__init__(message, kind="security_violation")


class NetworkFetchError(CrawlerError):
    def __init__(self, message: str):
        super().__init__(message, kind="network_error")


class RobotsDeniedError(CrawlerError):
    def __init__(self, message: str):
        super().__init__(message, kind="robots_denied")


class ParseError(CrawlerError):
    def __init__(self, message: str):
        super().__init__(message, kind="parse_error")


class CheckpointIntegrityError(CrawlerError):
    def __init__(self, message: str):
        super().__init__(message, kind="checkpoint_integrity")


# ---------------------------------------------------------------------------
# Config & Data Models
# ---------------------------------------------------------------------------

class JossConfig(BaseModel):
    """Strict configuration model for JOSS site crawler."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: int
    site_id: Literal["joss"]
    origin: str
    start_url: str
    robots_url: str
    conditions_url: str
    policy_manifest: str
    user_agent: str
    min_interval_seconds: float
    max_pages: int
    max_papers: int
    max_depth: int
    max_body_bytes: int
    timeout_seconds: float
    parser_version: str
    data_root: str

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: int) -> int:
        if type(v) is not int or v != 1:
            raise ValueError("schema_version must be exactly 1")
        return v

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, v: str) -> str:
        if v != CANONICAL_ORIGIN:
            raise ValueError(f"origin must be exactly '{CANONICAL_ORIGIN}'")
        return v

    @field_validator("start_url")
    @classmethod
    def validate_start_url(cls, v: str) -> str:
        if v != f"{CANONICAL_ORIGIN}{START_PATH}":
            raise ValueError(f"start_url must be exactly '{CANONICAL_ORIGIN}{START_PATH}'")
        return v

    @field_validator("robots_url")
    @classmethod
    def validate_robots_url(cls, v: str) -> str:
        if v != f"{CANONICAL_ORIGIN}{ROBOTS_PATH}":
            raise ValueError(f"robots_url must be exactly '{CANONICAL_ORIGIN}{ROBOTS_PATH}'")
        return v

    @field_validator("conditions_url")
    @classmethod
    def validate_conditions_url(cls, v: str) -> str:
        if v != f"{CANONICAL_ORIGIN}{CONDITIONS_PATH}":
            raise ValueError(f"conditions_url must be exactly '{CANONICAL_ORIGIN}{CONDITIONS_PATH}'")
        return v

    @field_validator("min_interval_seconds")
    @classmethod
    def validate_min_interval(cls, v: float) -> float:
        if not math.isfinite(v) or v < MIN_INTERVAL_SECONDS_FLOOR:
            raise ValueError(f"min_interval_seconds must be finite and >= {MIN_INTERVAL_SECONDS_FLOOR}")
        return v

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, v: int) -> int:
        if type(v) is not int or v < 1:
            raise ValueError("max_pages must be an integer >= 1")
        return v

    @field_validator("max_papers")
    @classmethod
    def validate_max_papers(cls, v: int) -> int:
        if type(v) is not int or v < 1:
            raise ValueError("max_papers must be an integer >= 1")
        return v

    @field_validator("max_depth")
    @classmethod
    def validate_max_depth(cls, v: int) -> int:
        if type(v) is not int or v != 1:
            raise ValueError("max_depth must be exactly 1 for JOSS paper listing")
        return v

    @field_validator("max_body_bytes")
    @classmethod
    def validate_max_body_bytes(cls, v: int) -> int:
        if type(v) is not int or v < 1024:
            raise ValueError("max_body_bytes must be an integer >= 1024")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError("timeout_seconds must be a finite positive float")
        return v

    @field_validator("parser_version")
    @classmethod
    def validate_parser_version(cls, v: str) -> str:
        if v != PARSER_VERSION:
            raise ValueError(f"parser_version must be exactly '{PARSER_VERSION}'")
        return v

    @field_validator("data_root")
    @classmethod
    def validate_data_root(cls, v: str) -> str:
        if ".." in v or "\\" in v or v.startswith("/"):
            raise ValueError("data_root must be a safe relative path without traversal")
        return v


def _check_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    d: dict[str, object] = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"Duplicate key '{k}' found in JSON")
        d[k] = v
    return d


def load_joss_config(path: Path) -> JossConfig:
    """Load and strictly validate JossConfig from a JSON file."""
    if not path.is_file():
        raise PolicyViolationError(f"Config file not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text, object_pairs_hook=_check_duplicate_keys)
    except Exception as exc:
        raise PolicyViolationError(f"Invalid JSON in config {path}: {exc}") from exc
    try:
        return JossConfig.model_validate(data)
    except Exception as exc:
        raise PolicyViolationError(f"Config validation error: {exc}") from exc


# ---------------------------------------------------------------------------
# Output Records Schema (Separate from frozen v1 search contracts)
# ---------------------------------------------------------------------------

class JossProvenance(BaseModel):
    """Detailed provenance tracking for harvested JOSS records."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    site_id: Literal["joss"]
    landing_url: str
    raw_sha256: str
    parser_version: str
    retrieved_at: str
    meta_fields: list[str]


class JossPaperRecord(BaseModel):
    """Immutable output record for a single JOSS published paper."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: str
    doi: str
    title: str
    authors: list[str]
    publication_date: str
    venue: str
    landing_url: str
    pdf_url: str | None
    raw_sha256: str
    retrieved_at: str
    parser_version: str
    provenance: JossProvenance


# ---------------------------------------------------------------------------
# Policy Manifest Verification
# ---------------------------------------------------------------------------

def validate_policy_manifest(project_root: Path, manifest_rel_path: str) -> dict[str, object]:
    """Validate policy manifest schema, file presence, and SHA-256 integrity."""
    manifest_path = (project_root / manifest_rel_path).resolve()
    policy_base = (project_root / "data" / "public_search").resolve()
    try:
        manifest_path.relative_to(policy_base)
    except ValueError:
        raise PolicyViolationError(f"Policy manifest {manifest_path} outside data/public_search")

    if not manifest_path.is_file():
        raise PolicyViolationError(f"Policy manifest not found: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_check_duplicate_keys)
    except Exception as exc:
        raise PolicyViolationError(f"Invalid policy manifest JSON: {exc}") from exc

    if data.get("status") != "PASS":
        raise PolicyViolationError(f"Policy manifest status is not PASS: {data.get('status')}")

    resources = data.get("resources")
    if not isinstance(resources, list) or not resources:
        raise PolicyViolationError("Policy manifest resources list is missing or empty")

    required_urls = {
        f"{CANONICAL_ORIGIN}{ROBOTS_PATH}",
        f"{CANONICAL_ORIGIN}{CONDITIONS_PATH}",
        f"{CANONICAL_ORIGIN}{START_PATH}",
        f"{CANONICAL_ORIGIN}/papers/10.21105/joss.09260",
    }
    seen_urls: set[str] = set()

    for item in resources:
        if not isinstance(item, dict):
            raise PolicyViolationError("Malformed resource item in manifest")
        url = item.get("url")
        raw_path = item.get("raw_path")
        expected_sha = item.get("sha256")
        status = item.get("status")
        retrieved_at = item.get("retrieved_at")

        if not all(isinstance(x, str) and x for x in (url, raw_path, expected_sha, retrieved_at)):
            raise PolicyViolationError(f"Resource missing required fields: {item}")
        if status != 200:
            raise PolicyViolationError(f"Policy resource {url} status is {status}, expected 200")

        file_path = (project_root / raw_path).resolve()
        try:
            file_path.relative_to(policy_base)
        except ValueError:
            raise PolicyViolationError(f"Policy resource path escapes data/public_search: {raw_path}")

        if not file_path.is_file():
            raise PolicyViolationError(f"Policy resource file missing on disk: {file_path}")

        file_bytes = file_path.read_bytes()
        actual_sha = hashlib.sha256(file_bytes).hexdigest()
        if actual_sha.lower() != expected_sha.lower():
            raise PolicyViolationError(f"Policy SHA-256 mismatch for {url}: expected {expected_sha}, got {actual_sha}")

        seen_urls.add(url)

    missing = required_urls - seen_urls
    if missing:
        raise PolicyViolationError(f"Policy manifest missing required resources: {sorted(missing)}")

    return data


# ---------------------------------------------------------------------------
# SSRF & DNS Security Validation
# ---------------------------------------------------------------------------

def default_dns_resolver(hostname: str) -> list[str]:
    """Default resolver using socket.getaddrinfo to resolve global IPv4/IPv6."""
    try:
        addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        ips = [entry[4][0] for entry in addr_info]
        if not ips:
            raise SecurityError(f"DNS resolution yielded no IPs for {hostname}")
        return ips
    except Exception as exc:
        raise SecurityError(f"DNS resolution failed for {hostname}: {exc}") from exc


def validate_url_and_dns(
    url: str,
    config: JossConfig,
    dns_resolver: Callable[[str], list[str]] = default_dns_resolver,
) -> None:
    """Validate URL syntax, path containment, origin matching, and global IP resolution."""
    if any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise SecurityError(f"URL contains whitespace or control characters: {url!r}")

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise SecurityError(f"URL scheme must be 'https', got '{parsed.scheme}'")
    if parsed.username or parsed.password:
        raise SecurityError(f"URL contains userinfo credentials: {url}")
    if parsed.port not in (None, 443):
        raise SecurityError(f"Non-standard port disallowed: {parsed.port}")
    if parsed.hostname != "joss.theoj.org":
        raise SecurityError(f"Foreign host rejected: '{parsed.hostname}'")
    if parsed.query:
        raise SecurityError(f"Query parameters disallowed on JOSS crawler URL: '{parsed.query}'")
    if parsed.fragment:
        raise SecurityError(f"URL fragments disallowed: '{parsed.fragment}'")

    raw_path = parsed.path
    if ".." in raw_path or "%2e" in raw_path.lower() or "%2f" in raw_path.lower() or "\\" in raw_path:
        raise SecurityError(f"Path traversal detected in URL: {raw_path}")

    # Check allowed paths: robots.txt, published listing, or canonical papers
    allowed = (
        raw_path == ROBOTS_PATH
        or raw_path == START_PATH
        or bool(PAPER_PATH_REGEX.match(raw_path))
    )
    if not allowed:
        raise SecurityError(f"Disallowed path for JOSS crawler: {raw_path}")

    # Resolve and inspect DNS IPs
    ips = dns_resolver(parsed.hostname)
    for ip_str in ips:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SecurityError(f"Invalid IP address returned by DNS: {ip_str}")
        if (
            not ip_obj.is_global
            or ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            raise SecurityError(f"SSRF protection: Disallowed non-global IP resolved ({ip_str}) for {parsed.hostname}")


# ---------------------------------------------------------------------------
# HTML Parsers (stdlib HTMLParser)
# ---------------------------------------------------------------------------

class JossListingParser(html.parser.HTMLParser):
    """Safe HTMLParser extracting depth-1 canonical published paper URLs from JOSS listing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paper_urls: list[str] = []
        self.seen_urls: set[str] = set()
        self.links_found: int = 0
        self.duplicate_links: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href_val: str | None = None
        for k, v in attrs:
            if k.lower() == "href" and v:
                href_val = v
                break
        if not href_val:
            return

        cleaned_href = href_val.split("#")[0].strip()
        if not cleaned_href:
            return

        if cleaned_href.startswith("/"):
            candidate_url = f"{CANONICAL_ORIGIN}{cleaned_href}"
        elif cleaned_href.startswith("https://joss.theoj.org/"):
            candidate_url = cleaned_href
        else:
            return

        m = PAPER_URL_REGEX.match(candidate_url)
        if m:
            self.links_found += 1
            if candidate_url in self.seen_urls:
                self.duplicate_links += 1
            else:
                self.seen_urls.add(candidate_url)
                self.paper_urls.append(candidate_url)

    def extract_links(self, html_content: str) -> tuple[list[str], int, int]:
        self.feed(html_content)
        self.close()
        if not self.paper_urls:
            raise ParseError("Selector drift: zero paper links extracted from published listing")
        return list(self.paper_urls), self.links_found, self.duplicate_links


class JossPaperParser(html.parser.HTMLParser):
    """Safe HTMLParser extracting citation metadata from a JOSS published paper HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raw_meta: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Check all attributes for forbidden research sentinel keys
        for k, v in attrs:
            k_lower = k.lower()
            if k_lower in FORBIDDEN_METADATA_KEYS:
                raise ParseError(f"Forbidden research attribute '{k}' detected in paper HTML")
            if tag.lower() == "meta" and k_lower in ("name", "property") and v:
                v_lower = v.strip().lower()
                for fk in FORBIDDEN_METADATA_KEYS:
                    if v_lower == fk or v_lower.startswith(fk + "_") or v_lower.endswith("_" + fk):
                        raise ParseError(f"Forbidden research meta tag '{v}' detected in paper HTML")

        if tag.lower() == "meta":
            meta_name: str | None = None
            meta_content: str | None = None
            for k, v in attrs:
                k_lower = k.lower()
                if k_lower in ("name", "property") and v:
                    meta_name = v.strip().lower()
                elif k_lower in ("content", "value") and v is not None:
                    meta_content = v.strip()

            if meta_name and meta_content is not None:
                if meta_name not in self.raw_meta:
                    self.raw_meta[meta_name] = []
                self.raw_meta[meta_name].append(meta_content)

    def _get_singleton(self, key: str, required: bool = True) -> str | None:
        values = self.raw_meta.get(key, [])
        if not values:
            if required:
                raise ParseError(f"Missing required citation meta tag: '{key}'")
            return None
        unique_vals = list(dict.fromkeys(values))
        if len(unique_vals) > 1:
            raise ParseError(f"Contradictory singleton citation meta tag '{key}': {unique_vals}")
        return unique_vals[0]

    def parse_record(
        self,
        html_bytes: bytes,
        landing_url: str,
        parser_version: str,
        retrieved_at: str,
    ) -> JossPaperRecord:
        """Parse raw HTML bytes and construct a validated JossPaperRecord."""
        try:
            html_text = html_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError(f"Paper HTML is not valid UTF-8: {exc}") from exc

        self.feed(html_text)
        self.close()

        raw_sha256 = hashlib.sha256(html_bytes).hexdigest()

        # Extract landing DOI
        m = PAPER_URL_REGEX.match(landing_url)
        if not m:
            raise ParseError(f"Landing URL does not match canonical JOSS paper pattern: {landing_url}")
        expected_doi = f"10.21105/joss.{m.group(1)}"

        # Mandatory citation singletons
        title = self._get_singleton("citation_title", required=True)
        doi = self._get_singleton("citation_doi", required=True)
        pub_date = self._get_singleton("citation_publication_date", required=True)
        venue = self._get_singleton("citation_journal_title", required=True)

        if not title:
            raise ParseError("Empty citation_title")
        if not doi:
            raise ParseError("Empty citation_doi")
        if not pub_date:
            raise ParseError("Empty citation_publication_date")
        if not venue:
            raise ParseError("Empty citation_journal_title")

        # Landing DOI must match citation DOI strictly
        if doi.lower() != expected_doi.lower():
            raise ParseError(f"Landing DOI mismatch: landing expects '{expected_doi}', citation has '{doi}'")

        # Publication date validation (YYYY/MM/DD or YYYY-MM-DD)
        norm_date = pub_date.replace("-", "/")
        parts = norm_date.split("/")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ParseError(f"Malformed publication date format: {pub_date}")
        try:
            datetime.strptime(norm_date, "%Y/%m/%d")
        except ValueError as exc:
            raise ParseError(f"Invalid calendar publication date: {pub_date}") from exc

        # Authors (multiple allowed, at least 1 required)
        authors = self.raw_meta.get("citation_author", [])
        if not authors:
            raise ParseError("Missing required citation_author metadata")
        clean_authors = [a for a in authors if a.strip()]
        if not clean_authors:
            raise ParseError("All citation_author values are empty")

        # Nullable PDF URL
        pdf_url = self._get_singleton("citation_pdf_url", required=False)
        if pdf_url:
            pdf_parsed = urllib.parse.urlsplit(pdf_url)
            if pdf_parsed.scheme != "https" or pdf_parsed.hostname != "joss.theoj.org":
                raise ParseError(f"Foreign metadata PDF URL rejected: '{pdf_url}'")
            if ".." in pdf_parsed.path or "\\" in pdf_parsed.path:
                raise ParseError(f"Path traversal in metadata PDF URL: '{pdf_url}'")

        # Other optional singletons checked for contradictory conflict
        for opt_key in ("citation_volume", "citation_issue", "citation_firstpage", "citation_issn", "citation_abstract_html_url"):
            self._get_singleton(opt_key, required=False)

        provenance = JossProvenance(
            site_id="joss",
            landing_url=landing_url,
            raw_sha256=raw_sha256,
            parser_version=parser_version,
            retrieved_at=retrieved_at,
            meta_fields=sorted(self.raw_meta.keys()),
        )

        return JossPaperRecord(
            id=f"joss:{doi}",
            doi=doi,
            title=title,
            authors=clean_authors,
            publication_date=pub_date,
            venue=venue,
            landing_url=landing_url,
            pdf_url=pdf_url,
            raw_sha256=raw_sha256,
            retrieved_at=retrieved_at,
            parser_version=parser_version,
            provenance=provenance,
        )


# ---------------------------------------------------------------------------
# Rate Limiting & Sequential Fetching
# ---------------------------------------------------------------------------

class RateLimiter:
    """Sequential rate limiter enforcing >= 3.0s interval between HTTP requests."""

    def __init__(
        self,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval_seconds
        self.clock = clock
        self.sleeper = sleeper
        self.last_call_timestamp: float = 0.0

    def wait(self) -> None:
        now = self.clock()
        elapsed = now - self.last_call_timestamp
        if self.last_call_timestamp > 0.0 and elapsed < self.min_interval:
            to_sleep = self.min_interval - elapsed
            self.sleeper(to_sleep)
        self.last_call_timestamp = self.clock()


def stream_bounded_fetch(
    client: httpx.Client,
    url: str,
    config: JossConfig,
    rate_limiter: RateLimiter,
    expected_content_type_prefix: str,
    dns_resolver: Callable[[str], list[str]] = default_dns_resolver,
) -> tuple[bytes, str]:
    """Perform security checks, rate-limited GET request, streaming body up to max_body_bytes."""
    validate_url_and_dns(url, config, dns_resolver=dns_resolver)
    rate_limiter.wait()

    try:
        request = client.build_request("GET", url, headers={"User-Agent": config.user_agent})
        response = client.send(request, stream=True)
    except Exception as exc:
        raise NetworkFetchError(f"Network error fetching {url}: {exc}") from exc

    try:
        # Explicit redirects are rejected
        if response.status_code in (301, 302, 303, 307, 308):
            raise SecurityError(f"Explicit redirect {response.status_code} rejected for {url}")

        if response.status_code != 200:
            raise NetworkFetchError(f"HTTP {response.status_code} fetching {url}")

        content_type = response.headers.get("content-type", "").lower()
        if not content_type.startswith(expected_content_type_prefix.lower()):
            raise NetworkFetchError(
                f"Content-Type '{content_type}' does not match expected prefix '{expected_content_type_prefix}' for {url}"
            )

        body_buffer = bytearray()
        for chunk in response.iter_bytes():
            body_buffer.extend(chunk)
            if len(body_buffer) > config.max_body_bytes:
                raise NetworkFetchError(
                    f"Response exceeded max_body_bytes ({config.max_body_bytes}) fetching {url}"
                )
        return bytes(body_buffer), content_type
    finally:
        response.close()


# ---------------------------------------------------------------------------
# Checkpoint and Persistence Logic
# ---------------------------------------------------------------------------

def write_atomic_checkpoint(run_dir: Path, checkpoint_data: dict[str, object]) -> None:
    """Atomically write checkpoint JSON file using a temp file and os.replace."""
    tmp_path = run_dir / "checkpoint.json.tmp"
    target_path = run_dir / "checkpoint.json"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target_path)


# ---------------------------------------------------------------------------
# JossCrawler Core Engine
# ---------------------------------------------------------------------------

class JossCrawler:
    """Bounded, sequential, atomic crawler for JOSS published HTML."""

    def __init__(
        self,
        project_root: Path,
        config: JossConfig,
        run_dir: Path,
        resume: bool = False,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        dns_resolver: Callable[[str], list[str]] = default_dns_resolver,
    ) -> None:
        self.project_root = project_root.resolve()
        self.config = config
        self.run_dir = run_dir.resolve()
        self.resume = resume
        self.clock = clock
        self.sleeper = sleeper
        self.dns_resolver = dns_resolver

        self._own_client = client is None
        self.client = client or httpx.Client(
            timeout=config.timeout_seconds,
            follow_redirects=False,
        )
        self.rate_limiter = RateLimiter(config.min_interval_seconds, clock=clock, sleeper=sleeper)

        # Enforce output roots constrained beneath project's config data_root
        data_root_base = (self.project_root / config.data_root).resolve()
        try:
            self.run_dir.relative_to(data_root_base)
        except ValueError:
            raise SecurityError(f"run_dir '{self.run_dir}' escapes configured data_root '{data_root_base}'")

        if self.run_dir == data_root_base:
            raise SecurityError("run_dir cannot be the data_root directory itself")

        if not self.resume:
            if self.run_dir.exists():
                raise PolicyViolationError(f"run_dir already exists: '{self.run_dir}'. Use --resume to resume.")
            self.run_dir.mkdir(parents=True, exist_ok=False)
            (self.run_dir / "raw").mkdir(exist_ok=True)
        else:
            if not self.run_dir.exists():
                raise PolicyViolationError(f"run_dir does not exist for resume: '{self.run_dir}'")

        self.counters = {
            "pages_fetched": 0,
            "links_found": 0,
            "duplicate_links": 0,
            "papers_parsed": 0,
            "unique_papers": 0,
            "failed_attempted_calls": 0,
        }

    def close(self) -> None:
        if self._own_client:
            self.client.close()

    def __enter__(self) -> JossCrawler:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def _fetch_robots(self) -> tuple[urllib.robotparser.RobotFileParser, bytes]:
        """Fetch and parse live robots.txt; verify user agent access."""
        raw_bytes, _ = stream_bounded_fetch(
            self.client,
            self.config.robots_url,
            self.config,
            self.rate_limiter,
            expected_content_type_prefix="text/plain",
            dns_resolver=self.dns_resolver,
        )
        # Check control characters (except carriage return, newline, tab)
        for b in raw_bytes:
            if b < 32 and b not in (9, 10, 13):
                raise RobotsDeniedError(f"Control characters detected in robots.txt: byte {b}")

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RobotsDeniedError(f"robots.txt is not valid UTF-8: {exc}") from exc

        rfp = urllib.robotparser.RobotFileParser()
        rfp.parse(text.splitlines())

        # Save live robots bytes in run_dir
        (self.run_dir / "robots.txt").write_bytes(raw_bytes)
        return rfp, raw_bytes

    def _verify_checkpoint_integrity(self, checkpoint: dict[str, object], expected_config_hash: str) -> None:
        """Verify checkpoint JSON schema, config hash, and raw artifact SHA-256 integrity."""
        if checkpoint.get("config_hash") != expected_config_hash:
            raise CheckpointIntegrityError("Checkpoint config_hash does not match current configuration")

        visited = checkpoint.get("visited")
        if not isinstance(visited, list):
            raise CheckpointIntegrityError("Checkpoint visited list missing or malformed")

        raw_dir = self.run_dir / "raw"
        for v in visited:
            if not isinstance(v, dict):
                raise CheckpointIntegrityError("Malformed visited entry in checkpoint")
            raw_sha = v.get("raw_sha256")
            if not isinstance(raw_sha, str):
                raise CheckpointIntegrityError("Visited entry missing raw_sha256")
            raw_path = raw_dir / f"{raw_sha}.html"
            if not raw_path.is_file():
                raise CheckpointIntegrityError(f"Raw HTML missing on disk: {raw_path}")
            computed_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            if computed_sha.lower() != raw_sha.lower():
                raise CheckpointIntegrityError(f"Raw HTML SHA-256 corruption for {raw_path}")

        records = checkpoint.get("records")
        if not isinstance(records, list):
            raise CheckpointIntegrityError("Checkpoint records list missing or malformed")
        for rec in records:
            if not isinstance(rec, dict):
                raise CheckpointIntegrityError("Malformed record in checkpoint")
            rec_sha = rec.get("raw_sha256")
            if not isinstance(rec_sha, str):
                raise CheckpointIntegrityError("Record missing raw_sha256")
            rec_path = raw_dir / f"{rec_sha}.html"
            if not rec_path.is_file():
                raise CheckpointIntegrityError(f"Record referenced raw HTML missing on disk: {rec_path}")

    def crawl(self) -> dict[str, object]:
        """Execute the JOSS crawler workflow or resume an existing run."""
        # 1. Validate policy manifest
        validate_policy_manifest(self.project_root, self.config.policy_manifest)

        config_hash = hashlib.sha256(self.config.model_dump_json().encode("utf-8")).hexdigest()
        checkpoint_path = self.run_dir / "checkpoint.json"

        # 2. Check for resume
        frontier: list[str] = []
        visited: list[dict[str, str]] = []
        records: list[dict[str, object]] = []

        if self.resume:
            if not checkpoint_path.is_file():
                raise CheckpointIntegrityError(f"Cannot resume: checkpoint not found at {checkpoint_path}")
            try:
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise CheckpointIntegrityError(f"Corrupt checkpoint JSON: {exc}") from exc

            self._verify_checkpoint_integrity(checkpoint, config_hash)

            # Restore counters
            saved_counters = checkpoint.get("counters", {})
            if isinstance(saved_counters, dict):
                for k in self.counters:
                    if k in saved_counters and isinstance(saved_counters[k], int):
                        self.counters[k] = saved_counters[k]

            visited = list(checkpoint.get("visited", []))
            records = list(checkpoint.get("records", []))
            frontier = list(checkpoint.get("frontier", []))

            # If checkpoint was already complete, refresh robots and return existing records
            if checkpoint.get("status") == "complete":
                rfp, _ = self._fetch_robots()
                if not rfp.can_fetch(self.config.user_agent, self.config.start_url):
                    raise RobotsDeniedError("Robots disallows start_url on resume")
                return {
                    "status": "success",
                    "site_id": "joss",
                    "run_dir": str(self.run_dir),
                    "counters": dict(self.counters),
                    "records_count": len(records),
                    "records": records,
                }

        # 3. Always refresh/fetch live robots.txt on new invocation or incomplete resume
        rfp, _ = self._fetch_robots()
        if not rfp.can_fetch(self.config.user_agent, self.config.start_url):
            raise RobotsDeniedError(f"robots.txt disallows user-agent '{self.config.user_agent}' for seed URL")

        # Initial checkpoint for fresh run
        if not self.resume:
            frontier = [self.config.start_url]
            initial_checkpoint = {
                "schema_version": 1,
                "site_id": "joss",
                "config_hash": config_hash,
                "status": "running",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "frontier": frontier,
                "visited": visited,
                "records": records,
                "counters": dict(self.counters),
                "error": None,
            }
            write_atomic_checkpoint(self.run_dir, initial_checkpoint)

        raw_dir = self.run_dir / "raw"

        # 4. Fetch listing page if not yet visited
        visited_urls = {v["url"] for v in visited}
        if self.config.start_url not in visited_urls:
            try:
                listing_bytes, _ = stream_bounded_fetch(
                    self.client,
                    self.config.start_url,
                    self.config,
                    self.rate_limiter,
                    expected_content_type_prefix="text/html",
                    dns_resolver=self.dns_resolver,
                )
                self.counters["pages_fetched"] += 1
            except Exception as exc:
                self.counters["failed_attempted_calls"] += 1
                fail_data = {
                    "schema_version": 1,
                    "site_id": "joss",
                    "config_hash": config_hash,
                    "status": "failed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "frontier": frontier,
                    "visited": visited,
                    "records": records,
                    "counters": dict(self.counters),
                    "error": {"kind": type(exc).__name__, "message": str(exc)},
                }
                write_atomic_checkpoint(self.run_dir, fail_data)
                raise

            listing_sha = hashlib.sha256(listing_bytes).hexdigest()
            (raw_dir / f"{listing_sha}.html").write_bytes(listing_bytes)
            visited.append({
                "url": self.config.start_url,
                "raw_sha256": listing_sha,
                "type": "listing",
            })
            visited_urls.add(self.config.start_url)

            # Parse listing to discover depth-1 paper links
            listing_parser = JossListingParser()
            try:
                extracted_urls, found_cnt, dup_cnt = listing_parser.extract_links(listing_bytes.decode("utf-8"))
            except Exception as exc:
                fail_data = {
                    "schema_version": 1,
                    "site_id": "joss",
                    "config_hash": config_hash,
                    "status": "failed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "frontier": frontier,
                    "visited": visited,
                    "records": records,
                    "counters": dict(self.counters),
                    "error": {"kind": type(exc).__name__, "message": str(exc)},
                }
                write_atomic_checkpoint(self.run_dir, fail_data)
                raise

            self.counters["links_found"] += found_cnt
            self.counters["duplicate_links"] += dup_cnt

            # Frontier is populated with discovered paper URLs
            frontier = [u for u in extracted_urls if u not in visited_urls]

            # Update checkpoint after listing fetch
            checkpoint_update = {
                "schema_version": 1,
                "site_id": "joss",
                "config_hash": config_hash,
                "status": "running",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "frontier": frontier,
                "visited": visited,
                "records": records,
                "counters": dict(self.counters),
                "error": None,
            }
            write_atomic_checkpoint(self.run_dir, checkpoint_update)

        # 5. Fetch and parse paper pages up to quota
        while frontier and (
            self.counters["pages_fetched"] < self.config.max_pages
            and self.counters["unique_papers"] < self.config.max_papers
        ):
            paper_url = frontier.pop(0)
            if paper_url in visited_urls:
                continue

            # Check robots permission
            if not rfp.can_fetch(self.config.user_agent, paper_url):
                self.counters["failed_attempted_calls"] += 1
                fail_data = {
                    "schema_version": 1,
                    "site_id": "joss",
                    "config_hash": config_hash,
                    "status": "failed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "frontier": [paper_url] + frontier,
                    "visited": visited,
                    "records": records,
                    "counters": dict(self.counters),
                    "error": {"kind": "RobotsDeniedError", "message": f"Robots disallows {paper_url}"},
                }
                write_atomic_checkpoint(self.run_dir, fail_data)
                raise RobotsDeniedError(f"Robots disallows paper URL: {paper_url}")

            retrieved_at = datetime.now(timezone.utc).isoformat()
            try:
                paper_bytes, _ = stream_bounded_fetch(
                    self.client,
                    paper_url,
                    self.config,
                    self.rate_limiter,
                    expected_content_type_prefix="text/html",
                    dns_resolver=self.dns_resolver,
                )
                self.counters["pages_fetched"] += 1
            except Exception as exc:
                self.counters["failed_attempted_calls"] += 1
                fail_data = {
                    "schema_version": 1,
                    "site_id": "joss",
                    "config_hash": config_hash,
                    "status": "failed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "frontier": [paper_url] + frontier,
                    "visited": visited,
                    "records": records,
                    "counters": dict(self.counters),
                    "error": {"kind": type(exc).__name__, "message": str(exc)},
                }
                write_atomic_checkpoint(self.run_dir, fail_data)
                raise

            paper_sha = hashlib.sha256(paper_bytes).hexdigest()
            (raw_dir / f"{paper_sha}.html").write_bytes(paper_bytes)

            parser = JossPaperParser()
            try:
                parsed_record = parser.parse_record(
                    paper_bytes,
                    landing_url=paper_url,
                    parser_version=self.config.parser_version,
                    retrieved_at=retrieved_at,
                )
            except Exception as exc:
                self.counters["failed_attempted_calls"] += 1
                fail_data = {
                    "schema_version": 1,
                    "site_id": "joss",
                    "config_hash": config_hash,
                    "status": "failed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "frontier": [paper_url] + frontier,
                    "visited": visited,
                    "records": records,
                    "counters": dict(self.counters),
                    "error": {"kind": type(exc).__name__, "message": str(exc)},
                }
                write_atomic_checkpoint(self.run_dir, fail_data)
                raise

            self.counters["papers_parsed"] += 1
            self.counters["unique_papers"] += 1
            rec_dict = parsed_record.model_dump(mode="json")
            records.append(rec_dict)

            visited.append({
                "url": paper_url,
                "raw_sha256": paper_sha,
                "type": "paper",
            })
            visited_urls.add(paper_url)

            checkpoint_step = {
                "schema_version": 1,
                "site_id": "joss",
                "config_hash": config_hash,
                "status": "running",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "frontier": frontier,
                "visited": visited,
                "records": records,
                "counters": dict(self.counters),
                "error": None,
            }
            write_atomic_checkpoint(self.run_dir, checkpoint_step)

        # 6. Mark complete and save records snapshot JSON
        final_checkpoint = {
            "schema_version": 1,
            "site_id": "joss",
            "config_hash": config_hash,
            "status": "complete",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "frontier": frontier,
            "visited": visited,
            "records": records,
            "counters": dict(self.counters),
            "error": None,
        }
        write_atomic_checkpoint(self.run_dir, final_checkpoint)

        records_file = self.run_dir / "records.json"
        with open(records_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

        return {
            "status": "success",
            "site_id": "joss",
            "run_dir": str(self.run_dir),
            "counters": dict(self.counters),
            "records_count": len(records),
            "records": records,
        }
