"""Bounded HTML crawler for JOSS published papers (EXT-10).

Adheres strictly to Anti-Silent-Bypass Protocol and R1 Review Findings:
- Strict schema validation with no silent .get defaults or fallback.
- Mandatory negative/adversarial guards: missing resources, malformed metadata,
  forbidden research keys (labels/qrels/dev_labels/test_labels/heldout/split/score),
  SSRF / private DNS resolution, oversized payloads, robots disallow, redirect rejection.
- Atomic checkpoints with SHA-256 verification and resume integrity checking.
- Reparsing of raw HTML on resume to prevent metadata tampering.
- Strict data_root confinement to public JOSS namespace and symlink escape guarding.
- Strict robots parser rejecting unparseable garbage directives and honoring Crawl-delay.
- Monotonic rate limiting floor (>=3.0s).
- Bounded overall request streaming deadlines and exact Content-Type media matching.
"""
from __future__ import annotations

import copy
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
DATA_ROOT_CANONICAL = "data/public_search/joss"

PAPER_PATH_REGEX = re.compile(r"^/papers/10\.21105/joss\.(\d+)$")
PAPER_URL_REGEX = re.compile(r"^https://joss\.theoj\.org/papers/10\.21105/joss\.(\d+)$")
DOI_REGEX = re.compile(r"^10\.21105/joss\.(\d+)$")

FORBIDDEN_METADATA_KEYS = frozenset({
    "labels", "qrels", "dev_labels", "test_labels", "heldout", "split", "score"
})

VALID_ROBOTS_DIRECTIVES = frozenset({
    "user-agent", "allow", "disallow", "crawl-delay", "request-rate", "sitemap", "host"
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
    """Strict configuration model for JOSS site crawler with finite sane upper bounds."""
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

    @field_validator("user_agent")
    @classmethod
    def validate_user_agent(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_agent must be non-blank")
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("user_agent cannot contain control characters or newlines")
        return v

    @field_validator("min_interval_seconds")
    @classmethod
    def validate_min_interval(cls, v: float) -> float:
        if not math.isfinite(v) or v < MIN_INTERVAL_SECONDS_FLOOR or v > 60.0:
            raise ValueError(f"min_interval_seconds must be finite between {MIN_INTERVAL_SECONDS_FLOOR} and 60.0")
        return v

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, v: int) -> int:
        if type(v) is not int or v < 1 or v > 100:
            raise ValueError("max_pages must be an integer between 1 and 100")
        return v

    @field_validator("max_papers")
    @classmethod
    def validate_max_papers(cls, v: int) -> int:
        if type(v) is not int or v < 1 or v > 50:
            raise ValueError("max_papers must be an integer between 1 and 50")
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
        if type(v) is not int or v < 1024 or v > 10485760:
            raise ValueError("max_body_bytes must be an integer between 1024 and 10485760 (10 MB)")
        return v

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0.5 or v > 120.0:
            raise ValueError("timeout_seconds must be a finite float between 0.5 and 120.0")
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
        norm = v.strip()
        if "\\" in norm or ":" in norm or norm.startswith("/") or ".." in norm or "%2e" in norm.lower():
            raise ValueError("data_root must be a clean relative path without drive letters, backslashes, or traversal")
        if norm != DATA_ROOT_CANONICAL and not norm.startswith(f"{DATA_ROOT_CANONICAL}/"):
            raise ValueError(f"data_root must be '{DATA_ROOT_CANONICAL}' or a descendant within that public namespace")
        return norm


def check_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
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
        data = json.loads(raw_text, object_pairs_hook=check_duplicate_keys)
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

    @field_validator("raw_sha256")
    @classmethod
    def validate_sha(cls, v: str) -> str:
        if not re.match(r"^[0-9a-f]{64}$", v):
            raise ValueError("raw_sha256 must be a valid 64-character lowercase hex string")
        return v

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at(cls, v: str) -> str:
        try:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                raise ValueError("retrieved_at must be an aware datetime with timezone")
        except Exception as exc:
            raise ValueError(f"Invalid ISO-8601 retrieved_at: {v}") from exc
        return v


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

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str) -> str:
        if not DOI_REGEX.match(v):
            raise ValueError(f"Malformed DOI: {v}")
        return v

    @field_validator("title", "venue")
    @classmethod
    def validate_non_empty_str(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[str]) -> list[str]:
        if not v or not any(a.strip() for a in v):
            raise ValueError("authors cannot be empty")
        return v


# ---------------------------------------------------------------------------
# Strict Checkpoint Models
# ---------------------------------------------------------------------------

class CheckpointVisitedEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    url: str
    raw_sha256: str
    type: Literal["listing", "paper", "robots"]
    retrieved_at: str
    parser_version: str
    config_hash: str


class CheckpointCounters(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    pages_fetched: int
    links_found: int
    duplicate_links: int
    papers_parsed: int
    unique_papers: int
    failed_attempted_calls: int

    @field_validator("pages_fetched", "links_found", "duplicate_links", "papers_parsed", "unique_papers", "failed_attempted_calls")
    @classmethod
    def check_non_negative(cls, v: int) -> int:
        if type(v) is not int or v < 0:
            raise ValueError("counter must be a non-negative integer")
        return v


class CheckpointModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: int
    site_id: Literal["joss"]
    config_hash: str
    status: Literal["running", "failed", "complete"]
    created_at: str
    updated_at: str
    frontier: list[str]
    visited: list[CheckpointVisitedEntry]
    records: list[JossPaperRecord]
    counters: CheckpointCounters
    error: dict[str, str] | None


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
        data = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=check_duplicate_keys)
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
    if not ips:
        raise SecurityError(f"DNS resolver returned no IP addresses for {parsed.hostname}")

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
# Strict Robots Parser Boundary
# ---------------------------------------------------------------------------

def validate_robots_directives(robots_text: str) -> tuple[float | None, list[str]]:
    """Validate robots.txt syntax strictly; accept comments, reject unparseable directives."""
    crawl_delay: float | None = None
    clean_lines: list[str] = []

    for line_idx, line in enumerate(robots_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            clean_lines.append(stripped)
            continue
        if ":" not in stripped:
            raise RobotsDeniedError(f"Malformed robots.txt directive at line {line_idx}: missing ':' in '{stripped}'")
        prefix, _, val = stripped.partition(":")
        directive = prefix.strip().lower()
        if directive not in VALID_ROBOTS_DIRECTIVES:
            raise RobotsDeniedError(f"Malformed robots.txt directive at line {line_idx}: unrecognized directive '{directive}'")
        clean_val = val.strip()
        if directive == "crawl-delay":
            try:
                cd = float(clean_val)
                if cd < 0:
                    raise ValueError
                crawl_delay = cd if crawl_delay is None else max(crawl_delay, cd)
            except ValueError:
                raise RobotsDeniedError(f"Malformed Crawl-delay numeric value: '{clean_val}'") from None
        clean_lines.append(f"{directive}: {clean_val}")

    return crawl_delay, clean_lines


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

        # Nullable PDF URL with strict URL validation
        pdf_url = self._get_singleton("citation_pdf_url", required=False)
        if pdf_url:
            pdf_parsed = urllib.parse.urlsplit(pdf_url)
            if pdf_parsed.scheme != "https" or pdf_parsed.hostname != "joss.theoj.org":
                raise ParseError(f"Foreign metadata PDF URL rejected: '{pdf_url}'")
            if pdf_parsed.username or pdf_parsed.password:
                raise ParseError(f"User credentials in metadata PDF URL: '{pdf_url}'")
            if pdf_parsed.port not in (None, 443):
                raise ParseError(f"Non-standard port in metadata PDF URL: '{pdf_url}'")
            if ".." in pdf_parsed.path or "\\" in pdf_parsed.path:
                raise ParseError(f"Path traversal in metadata PDF URL: '{pdf_url}'")

        # citation_abstract_html_url checked for foreign host
        abs_url = self._get_singleton("citation_abstract_html_url", required=False)
        if abs_url:
            abs_parsed = urllib.parse.urlsplit(abs_url)
            if abs_parsed.scheme != "https" or abs_parsed.hostname != "joss.theoj.org":
                raise ParseError(f"Foreign metadata abstract URL rejected: '{abs_url}'")
            if abs_parsed.username or abs_parsed.password:
                raise ParseError(f"User credentials in metadata abstract URL: '{abs_url}'")
            if abs_parsed.port not in (None, 443):
                raise ParseError(f"Non-standard port in metadata abstract URL: '{abs_url}'")
            if ".." in abs_parsed.path or "\\" in abs_parsed.path:
                raise ParseError(f"Path traversal in metadata abstract URL: '{abs_url}'")

        # Other optional singletons checked for contradictory conflict
        for opt_key in ("citation_volume", "citation_issue", "citation_firstpage", "citation_issn"):
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
# Rate Limiting & Sequential Fetching with Monotonic Clock
# ---------------------------------------------------------------------------

class RateLimiter:
    """Sequential rate limiter enforcing >= 3.0s (or stricter robots Crawl-delay) using monotonic clock."""

    def __init__(
        self,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_interval = min_interval_seconds
        self.effective_interval = min_interval_seconds
        self.clock = clock
        self.sleeper = sleeper
        self.last_call_timestamp: float = 0.0

    def set_crawl_delay(self, crawl_delay: float | None) -> None:
        if crawl_delay is not None and crawl_delay > self.effective_interval:
            self.effective_interval = crawl_delay

    def wait(self) -> None:
        now = self.clock()
        elapsed = now - self.last_call_timestamp
        if self.last_call_timestamp > 0.0 and elapsed < self.effective_interval:
            to_sleep = self.effective_interval - elapsed
            self.sleeper(to_sleep)
        self.last_call_timestamp = self.clock()


def stream_bounded_fetch(
    client: httpx.Client,
    url: str,
    config: JossConfig,
    rate_limiter: RateLimiter,
    expected_content_type: str,
    dns_resolver: Callable[[str], list[str]] = default_dns_resolver,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[bytes, str]:
    """Perform security checks, rate-limited GET request, streaming body up to max_body_bytes within deadline."""
    validate_url_and_dns(url, config, dns_resolver=dns_resolver)
    rate_limiter.wait()

    start_monotonic = clock()
    deadline = start_monotonic + config.timeout_seconds

    try:
        # Strictly enforce follow_redirects=False on every request
        request = client.build_request("GET", url, headers={"User-Agent": config.user_agent})
        response = client.send(request, stream=True, follow_redirects=False)
    except Exception as exc:
        raise NetworkFetchError(f"Network error fetching {url}: {exc}") from exc

    try:
        if response.status_code in (301, 302, 303, 307, 308):
            raise SecurityError(f"Explicit redirect {response.status_code} rejected for {url}")

        if response.status_code != 200:
            raise NetworkFetchError(f"HTTP {response.status_code} fetching {url}")

        raw_ct = response.headers.get("content-type")
        if raw_ct is None:
            raise NetworkFetchError(f"Missing Content-Type header fetching {url}")
        base_media_type = raw_ct.split(";")[0].strip().lower()
        if base_media_type != expected_content_type.lower():
            raise NetworkFetchError(
                f"Content-Type '{base_media_type}' does not match expected '{expected_content_type}' for {url}"
            )

        content_length_header = response.headers.get("content-length")
        if content_length_header is not None:
            if not content_length_header.strip().isdigit():
                raise NetworkFetchError(f"Malformed Content-Length header: '{content_length_header}'")
            if int(content_length_header.strip()) > config.max_body_bytes:
                raise NetworkFetchError(
                    f"Content-Length ({content_length_header}) exceeds max_body_bytes ({config.max_body_bytes}) for {url}"
                )

        body_buffer = bytearray()
        for chunk in response.iter_bytes():
            if clock() > deadline:
                raise NetworkFetchError(f"Total response deadline ({config.timeout_seconds}s) exceeded while fetching {url}")
            body_buffer.extend(chunk)
            if len(body_buffer) > config.max_body_bytes:
                raise NetworkFetchError(
                    f"Response exceeded max_body_bytes ({config.max_body_bytes}) fetching {url}"
                )
        return bytes(body_buffer), base_media_type
    finally:
        response.close()


# ---------------------------------------------------------------------------
# Path Confinement & Atomic Checkpoint
# ---------------------------------------------------------------------------

def guard_confinement_and_symlinks(project_root: Path, run_dir: Path, config: JossConfig) -> tuple[Path, Path]:
    """Verify paths are strictly within permitted public namespace and contain no symlinks."""
    proj_resolved = project_root.resolve()
    permitted_public = (proj_resolved / DATA_ROOT_CANONICAL).resolve()
    target_data_root = (proj_resolved / config.data_root).resolve()

    try:
        target_data_root.relative_to(permitted_public)
    except ValueError:
        raise SecurityError(f"data_root '{config.data_root}' escapes permitted public root '{permitted_public}'")

    run_resolved = run_dir.resolve()
    try:
        run_resolved.relative_to(target_data_root)
    except ValueError:
        raise SecurityError(f"run_dir '{run_dir}' escapes configured data_root '{target_data_root}'")

    if run_resolved == target_data_root or run_resolved == permitted_public:
        raise SecurityError("run_dir cannot be the data_root or public namespace itself")

    # Guard against symlinks in critical paths
    for p in (run_dir, run_dir / "raw", run_dir / "checkpoint.json", run_dir / "records.json"):
        if p.is_symlink():
            raise SecurityError(f"Symlink detected at '{p}'")

    return proj_resolved, run_resolved


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
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        dns_resolver: Callable[[str], list[str]] = default_dns_resolver,
    ) -> None:
        self.project_root, self.run_dir = guard_confinement_and_symlinks(project_root, run_dir, config)
        self.config = config
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
        self.config_hash = hashlib.sha256(self.config.model_dump_json().encode("utf-8")).hexdigest()

        if not self.resume:
            if self.run_dir.exists():
                raise PolicyViolationError(f"run_dir already exists: '{self.run_dir}'. Use --resume to resume.")
            self.run_dir.mkdir(parents=True, exist_ok=False)
            (self.run_dir / "raw").mkdir(exist_ok=True)
            (self.run_dir / "robots").mkdir(exist_ok=True)
            self.created_at = datetime.now(timezone.utc).isoformat()
        else:
            if not self.run_dir.exists():
                raise PolicyViolationError(f"run_dir does not exist for resume: '{self.run_dir}'")
            self.created_at = ""

        self.counters = CheckpointCounters(
            pages_fetched=0,
            links_found=0,
            duplicate_links=0,
            papers_parsed=0,
            unique_papers=0,
            failed_attempted_calls=0,
        )
        self.frontier: list[str] = []
        self.visited: list[CheckpointVisitedEntry] = []
        self.records: list[JossPaperRecord] = []

    def close(self) -> None:
        if self._own_client:
            self.client.close()

    def __enter__(self) -> JossCrawler:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def _save_checkpoint(
        self,
        status: Literal["running", "failed", "complete"],
        error: dict[str, str] | None = None,
    ) -> None:
        """Centralized helper to save atomic checkpoint with consistent invariant counters."""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "schema_version": 1,
            "site_id": "joss",
            "config_hash": self.config_hash,
            "status": status,
            "created_at": self.created_at,
            "updated_at": now,
            "frontier": list(self.frontier),
            "visited": [v.model_dump() for v in self.visited],
            "records": [r.model_dump() for r in self.records],
            "counters": self.counters.model_dump(),
            "error": error,
        }
        write_atomic_checkpoint(self.run_dir, data)

    def _fetch_robots(self) -> tuple[urllib.robotparser.RobotFileParser, bytes]:
        """Fetch live robots.txt, parse directives strictly, honor Crawl-delay, and save attempt."""
        try:
            raw_bytes, _ = stream_bounded_fetch(
                self.client,
                self.config.robots_url,
                self.config,
                self.rate_limiter,
                expected_content_type="text/plain",
                dns_resolver=self.dns_resolver,
                clock=self.clock,
            )
        except Exception as exc:
            self.counters = self.counters.model_copy(
                update={"failed_attempted_calls": self.counters.failed_attempted_calls + 1}
            )
            self._save_checkpoint("failed", error={"kind": type(exc).__name__, "message": str(exc)})
            raise

        for b in raw_bytes:
            if b < 32 and b not in (9, 10, 13):
                raise RobotsDeniedError(f"Control characters detected in robots.txt: byte {b}")

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RobotsDeniedError(f"robots.txt is not valid UTF-8: {exc}") from exc

        crawl_delay, clean_lines = validate_robots_directives(text)
        self.rate_limiter.set_crawl_delay(crawl_delay)

        rfp = urllib.robotparser.RobotFileParser()
        rfp.parse(clean_lines)

        # Save latest and immutable historical attempt
        robots_sha = hashlib.sha256(raw_bytes).hexdigest()
        (self.run_dir / "robots.txt").write_bytes(raw_bytes)
        robots_dir = self.run_dir / "robots"
        robots_dir.mkdir(exist_ok=True)
        timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (robots_dir / f"robots_{robots_sha[:16]}_{timestamp_slug}.txt").write_bytes(raw_bytes)

        return rfp, raw_bytes

    def _verify_checkpoint_integrity(self) -> CheckpointModel:
        """Strictly validate checkpoint JSON, counters invariants, and reparse raw HTML to guard against tampering."""
        chk_path = self.run_dir / "checkpoint.json"
        if not chk_path.is_file():
            raise CheckpointIntegrityError(f"Cannot resume: checkpoint not found at {chk_path}")

        try:
            raw_data = json.loads(chk_path.read_text(encoding="utf-8"), object_pairs_hook=check_duplicate_keys)
        except Exception as exc:
            raise CheckpointIntegrityError(f"Corrupt checkpoint JSON: {exc}") from exc

        try:
            chk = CheckpointModel.model_validate(raw_data)
        except Exception as exc:
            raise CheckpointIntegrityError(f"Checkpoint schema validation failed: {exc}") from exc

        if chk.config_hash != self.config_hash:
            raise CheckpointIntegrityError("Checkpoint config_hash does not match current configuration")

        # Verify counter invariants
        expected_pages_fetched = len([v for v in chk.visited if v.type in ("listing", "paper")])
        if chk.counters.pages_fetched != expected_pages_fetched:
            raise CheckpointIntegrityError(
                f"Counter invariant failed: pages_fetched ({chk.counters.pages_fetched}) != visited HTML ({expected_pages_fetched})"
            )
        if chk.counters.unique_papers != len(chk.records) or chk.counters.papers_parsed != len(chk.records):
            raise CheckpointIntegrityError("Counter invariant failed: unique_papers/papers_parsed != records count")

        # Verify raw HTML existence, SHA-256 match, and reparse metadata
        raw_dir = self.run_dir / "raw"
        for v in chk.visited:
            if v.type == "robots":
                continue
            raw_file = raw_dir / f"{v.raw_sha256}.html"
            if not raw_file.is_file():
                raise CheckpointIntegrityError(f"Referenced raw HTML missing on disk: {raw_file}")
            actual_sha = hashlib.sha256(raw_file.read_bytes()).hexdigest()
            if actual_sha.lower() != v.raw_sha256.lower():
                raise CheckpointIntegrityError(f"Raw HTML SHA-256 corruption detected for {raw_file}")

        for rec in chk.records:
            raw_file = raw_dir / f"{rec.raw_sha256}.html"
            if not raw_file.is_file():
                raise CheckpointIntegrityError(f"Record raw file missing on disk: {raw_file}")
            raw_bytes = raw_file.read_bytes()
            # Reparse to ensure no metadata was altered in checkpoint
            parser = JossPaperParser()
            try:
                reparsed = parser.parse_record(
                    raw_bytes,
                    landing_url=rec.landing_url,
                    parser_version=rec.parser_version,
                    retrieved_at=rec.retrieved_at,
                )
            except Exception as exc:
                raise CheckpointIntegrityError(f"Reparsing raw HTML for record {rec.doi} failed: {exc}") from exc

            if (
                reparsed.id != rec.id
                or reparsed.doi != rec.doi
                or reparsed.title != rec.title
                or reparsed.authors != rec.authors
                or reparsed.publication_date != rec.publication_date
                or reparsed.venue != rec.venue
                or reparsed.pdf_url != rec.pdf_url
            ):
                raise CheckpointIntegrityError(f"Discrepancy detected between raw HTML and checkpoint record for {rec.doi}")

        if chk.status == "complete":
            records_file = self.run_dir / "records.json"
            if not records_file.is_file():
                raise CheckpointIntegrityError("records.json missing on complete checkpoint")
            try:
                rec_json = json.loads(records_file.read_text(encoding="utf-8"), object_pairs_hook=check_duplicate_keys)
                if not isinstance(rec_json, list):
                    raise ValueError
                file_records = [JossPaperRecord.model_validate(r) for r in rec_json]
            except Exception as exc:
                raise CheckpointIntegrityError(f"records.json malformed or invalid: {exc}") from exc
            if file_records != chk.records:
                raise CheckpointIntegrityError("records.json does not match checkpoint records")

        return chk

    def crawl(self) -> dict[str, object]:
        """Execute the JOSS crawler workflow or resume an existing run."""
        # 1. Validate policy manifest
        validate_policy_manifest(self.project_root, self.config.policy_manifest)

        # 2. Handle resume or fresh initialization
        if self.resume:
            chk = self._verify_checkpoint_integrity()
            self.created_at = chk.created_at
            self.counters = chk.counters
            self.visited = list(chk.visited)
            self.records = list(chk.records)
            self.frontier = list(chk.frontier)

            # If checkpoint was complete, reload robots and verify access for all items
            if chk.status == "complete":
                rfp, _ = self._fetch_robots()
                if not rfp.can_fetch(self.config.user_agent, self.config.start_url):
                    raise RobotsDeniedError("Robots disallows start_url on complete resume")
                for rec in self.records:
                    if not rfp.can_fetch(self.config.user_agent, rec.landing_url):
                        raise RobotsDeniedError(f"Robots now disallows cached record: {rec.landing_url}")
                return {
                    "status": "success",
                    "site_id": "joss",
                    "run_dir": str(self.run_dir),
                    "counters": self.counters.model_dump(),
                    "records_count": len(self.records),
                    "records": [r.model_dump(mode="json") for r in self.records],
                }

            # If resuming an interrupted or failed run, reparse cached listing to detect selector drift
            listing_entries = [v for v in self.visited if v.type == "listing"]
            if listing_entries:
                listing_file = self.run_dir / "raw" / f"{listing_entries[0].raw_sha256}.html"
                listing_parser = JossListingParser()
                extracted_urls, found_cnt, dup_cnt = listing_parser.extract_links(
                    listing_file.read_bytes().decode("utf-8")
                )
                visited_paper_urls = {v.url for v in self.visited if v.type == "paper"}
                self.frontier = [u for u in extracted_urls if u not in visited_paper_urls]

        # Fetch live robots
        rfp, _ = self._fetch_robots()
        if not rfp.can_fetch(self.config.user_agent, self.config.start_url):
            self._save_checkpoint("failed", error={"kind": "RobotsDeniedError", "message": "Robots disallows start_url"})
            raise RobotsDeniedError(f"robots.txt disallows user-agent '{self.config.user_agent}' for seed URL")

        if not self.resume:
            self.frontier = [self.config.start_url]
            self._save_checkpoint("running")

        raw_dir = self.run_dir / "raw"
        visited_urls = {v.url for v in self.visited}

        # 3. Fetch listing page if not yet visited
        if self.config.start_url not in visited_urls:
            retrieved_at = datetime.now(timezone.utc).isoformat()
            try:
                listing_bytes, _ = stream_bounded_fetch(
                    self.client,
                    self.config.start_url,
                    self.config,
                    self.rate_limiter,
                    expected_content_type="text/html",
                    dns_resolver=self.dns_resolver,
                    clock=self.clock,
                )
            except Exception as exc:
                self.counters = self.counters.model_copy(
                    update={"failed_attempted_calls": self.counters.failed_attempted_calls + 1}
                )
                self._save_checkpoint("failed", error={"kind": type(exc).__name__, "message": str(exc)})
                raise

            listing_sha = hashlib.sha256(listing_bytes).hexdigest()
            (raw_dir / f"{listing_sha}.html").write_bytes(listing_bytes)

            self.visited.append(CheckpointVisitedEntry(
                url=self.config.start_url,
                raw_sha256=listing_sha,
                type="listing",
                retrieved_at=retrieved_at,
                parser_version=self.config.parser_version,
                config_hash=self.config_hash,
            ))
            visited_urls.add(self.config.start_url)
            self.counters = self.counters.model_copy(
                update={"pages_fetched": self.counters.pages_fetched + 1}
            )

            # Parse listing (Selector drift raises ParseError)
            listing_parser = JossListingParser()
            try:
                extracted_urls, found_cnt, dup_cnt = listing_parser.extract_links(listing_bytes.decode("utf-8"))
            except Exception as exc:
                self._save_checkpoint("failed", error={"kind": type(exc).__name__, "message": str(exc)})
                raise

            self.counters = self.counters.model_copy(
                update={
                    "links_found": self.counters.links_found + found_cnt,
                    "duplicate_links": self.counters.duplicate_links + dup_cnt,
                }
            )
            self.frontier = [u for u in extracted_urls if u not in visited_urls]
            self._save_checkpoint("running")

        # 4. Fetch and parse papers up to budget
        while self.frontier and (
            self.counters.pages_fetched < self.config.max_pages
            and self.counters.unique_papers < self.config.max_papers
        ):
            paper_url = self.frontier.pop(0)
            if paper_url in visited_urls:
                continue

            if not rfp.can_fetch(self.config.user_agent, paper_url):
                self.frontier.insert(0, paper_url)
                self._save_checkpoint("failed", error={"kind": "RobotsDeniedError", "message": f"Robots disallows {paper_url}"})
                raise RobotsDeniedError(f"Robots disallows paper URL: {paper_url}")

            retrieved_at = datetime.now(timezone.utc).isoformat()
            try:
                paper_bytes, _ = stream_bounded_fetch(
                    self.client,
                    paper_url,
                    self.config,
                    self.rate_limiter,
                    expected_content_type="text/html",
                    dns_resolver=self.dns_resolver,
                    clock=self.clock,
                )
            except Exception as exc:
                self.counters = self.counters.model_copy(
                    update={"failed_attempted_calls": self.counters.failed_attempted_calls + 1}
                )
                self.frontier.insert(0, paper_url)
                self._save_checkpoint("failed", error={"kind": type(exc).__name__, "message": str(exc)})
                raise

            paper_sha = hashlib.sha256(paper_bytes).hexdigest()
            (raw_dir / f"{paper_sha}.html").write_bytes(paper_bytes)

            self.visited.append(CheckpointVisitedEntry(
                url=paper_url,
                raw_sha256=paper_sha,
                type="paper",
                retrieved_at=retrieved_at,
                parser_version=self.config.parser_version,
                config_hash=self.config_hash,
            ))
            visited_urls.add(paper_url)
            self.counters = self.counters.model_copy(
                update={"pages_fetched": self.counters.pages_fetched + 1}
            )

            # Parse paper
            parser = JossPaperParser()
            try:
                record = parser.parse_record(
                    paper_bytes,
                    landing_url=paper_url,
                    parser_version=self.config.parser_version,
                    retrieved_at=retrieved_at,
                )
            except Exception as exc:
                self._save_checkpoint("failed", error={"kind": type(exc).__name__, "message": str(exc)})
                raise

            self.records.append(record)
            self.counters = self.counters.model_copy(
                update={
                    "papers_parsed": self.counters.papers_parsed + 1,
                    "unique_papers": self.counters.unique_papers + 1,
                }
            )
            self._save_checkpoint("running")

        # 5. Mark complete and save records.json atomically
        records_tmp = self.run_dir / "records.json.tmp"
        records_target = self.run_dir / "records.json"
        with open(records_tmp, "w", encoding="utf-8") as f:
            json.dump([r.model_dump(mode="json") for r in self.records], f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(records_tmp, records_target)

        self._save_checkpoint("complete")

        return {
            "status": "success",
            "site_id": "joss",
            "run_dir": str(self.run_dir),
            "counters": self.counters.model_dump(),
            "records_count": len(self.records),
            "records": [r.model_dump(mode="json") for r in self.records],
        }
