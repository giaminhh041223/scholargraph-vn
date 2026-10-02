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

import hashlib
import html.parser
import ipaddress
import json
import math
import os
import re
import socket
import uuid
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


def aware_timestamp(value: str) -> str:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return value


def valid_hash(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("SHA-256 must be lowercase hex")
    return value


def fixed_parser(value: str) -> str:
    if value != PARSER_VERSION:
        raise ValueError("parser version mismatch")
    return value


def paper_url(value: str) -> str:
    if PAPER_URL_REGEX.fullmatch(value) is None:
        raise ValueError("paper URL must be canonical JOSS URL")
    return value


def research_key(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    # Field aliases, not substrings: public HTML aria-label/data-label are accessibility/UI fields.
    for prefix in ("citation", "research"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized in {
        "label", "labels", "qrels", "qrelspath", "heldout", "heldoutlabels", "score", "scores",
        "split", "splits", "splitid", "datasetsplit",
        "trainlabel", "trainlabels", "devlabel", "devlabels", "testlabel", "testlabels",
        "trainsplit", "devsplit", "testsplit", "traintestsplit",
    }


def reject_research_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if research_key(key):
                raise ValueError("research labels/splits/scores forbidden")
            reject_research_keys(child)
    elif isinstance(value, list):
        for child in value:
            reject_research_keys(child)


class BoundaryModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def research_boundary(cls, value):
        reject_research_keys(value)
        return value


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

class JossConfig(BoundaryModel):
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

class JossProvenance(BoundaryModel):
    """Detailed provenance tracking for harvested JOSS records."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    site_id: Literal["joss"]
    landing_url: str
    raw_sha256: str
    parser_version: str
    retrieved_at: str
    meta_fields: list[str]

    _landing = field_validator("landing_url")(paper_url)
    _parser = field_validator("parser_version")(fixed_parser)

    @field_validator("meta_fields")
    @classmethod
    def meta_names(cls, value):
        if value != sorted(set(value)) or any(not name or research_key(name) for name in value):
            raise ValueError("meta_fields must be sorted unique public metadata names")
        return value

    @field_validator("raw_sha256")
    @classmethod
    def validate_sha(cls, v: str) -> str:
        return valid_hash(v)

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


class JossPaperRecord(BoundaryModel):
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

    _hash = field_validator("raw_sha256")(valid_hash)
    _timestamp = field_validator("retrieved_at")(aware_timestamp)
    _parser = field_validator("parser_version")(fixed_parser)
    _landing = field_validator("landing_url")(paper_url)

    @model_validator(mode="after")
    def metadata_matches_provenance(self):
        if self.id != "joss:" + self.doi or self.landing_url != CANONICAL_ORIGIN + "/papers/" + self.doi:
            raise ValueError("record identity/DOI/URL mismatch")
        for key in ("landing_url", "raw_sha256", "parser_version", "retrieved_at"):
            if getattr(self, key) != getattr(self.provenance, key):
                raise ValueError("record/provenance mismatch")
        if re.fullmatch(r"\d{4}(/|-)\d{2}\1\d{2}", self.publication_date) is None:
            raise ValueError("invalid publication date")
        datetime.strptime(self.publication_date.replace("-", "/"), "%Y/%m/%d")
        if self.pdf_url is not None:
            metadata_url(self.pdf_url)
        return self

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str) -> str:
        if not DOI_REGEX.fullmatch(v):
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
        if not v or any(not a.strip() for a in v):
            raise ValueError("authors cannot be empty")
        return v


# ---------------------------------------------------------------------------
# Strict Checkpoint Models
# ---------------------------------------------------------------------------

class CheckpointVisitedEntry(BoundaryModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    url: str
    raw_sha256: str
    type: Literal["listing", "paper"]
    retrieved_at: str
    parser_version: str
    config_hash: str

    _hashes = field_validator("raw_sha256", "config_hash")(valid_hash)
    _timestamp = field_validator("retrieved_at")(aware_timestamp)
    _parser = field_validator("parser_version")(fixed_parser)

    @model_validator(mode="after")
    def canonical_url(self):
        if self.type == "listing":
            if self.url != CANONICAL_ORIGIN + START_PATH:
                raise ValueError("listing URL mismatch")
        else:
            paper_url(self.url)
        return self


class CheckpointCounters(BoundaryModel):
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


class FetchAttempt(BoundaryModel):
    attempt_id: str
    url: str
    retrieved_at: str
    attempted: bool
    success: bool
    status_code: int | None = Field(ge=100, le=599)
    raw_path: str | None
    raw_sha256: str | None
    complete_body: bool
    error_kind: str | None

    _timestamp = field_validator("retrieved_at")(aware_timestamp)

    @model_validator(mode="after")
    def coherent(self):
        uuid.UUID(self.attempt_id)
        if self.url not in {CANONICAL_ORIGIN + ROBOTS_PATH, CANONICAL_ORIGIN + START_PATH}:
            paper_url(self.url)
        if (self.raw_sha256 is None) != (self.raw_path is None):
            raise ValueError("raw reference incomplete")
        if self.raw_sha256 is not None:
            valid_hash(self.raw_sha256)
            expected = ("robots/" + self.attempt_id + ".txt") if self.url.endswith(ROBOTS_PATH) else "raw/" + self.raw_sha256 + ".html"
            if self.raw_path != expected:
                raise ValueError("raw path must trace this attempt")
        if self.success:
            if not self.attempted or self.status_code != 200 or not self.complete_body or self.raw_path is None or self.error_kind is not None:
                raise ValueError("success attempt inconsistent")
        elif self.error_kind is None:
            raise ValueError("failed attempt requires error kind")
        if not self.attempted and (self.status_code is not None or self.raw_path is not None or self.complete_body):
            raise ValueError("preflight cannot claim HTTP observations")
        if self.complete_body and (self.raw_path is None or self.status_code is None):
            raise ValueError("complete body needs actual response/raw")
        return self


class CheckpointModel(BoundaryModel):
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
    fetch_attempts: list[FetchAttempt]

    _hash = field_validator("config_hash")(valid_hash)
    _timestamps = field_validator("created_at", "updated_at")(aware_timestamp)

    @field_validator("schema_version")
    @classmethod
    def version_one(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be exactly 1")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if datetime.fromisoformat(self.updated_at) < datetime.fromisoformat(self.created_at):
            raise ValueError("checkpoint timestamp order reversed")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("status/error mismatch")
        if len(self.frontier) != len(set(self.frontier)):
            raise ValueError("duplicate frontier")
        for url in self.frontier:
            if url != CANONICAL_ORIGIN + START_PATH:
                paper_url(url)
        return self


# ---------------------------------------------------------------------------
# Policy Manifest Verification
# ---------------------------------------------------------------------------

def validate_policy_manifest(project_root: Path, manifest_rel_path: str) -> dict[str, object]:
    """Validate policy manifest schema, file presence, and SHA-256 integrity."""
    manifest_path = project_root / manifest_rel_path
    guard_path(project_root, manifest_path)
    manifest_path = manifest_path.resolve()
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

    if type(data) is not dict or "status" not in data or data["status"] != "PASS" or "resources" not in data:
        raise PolicyViolationError("Policy manifest missing required PASS status/resources")
    reject_research_keys(data)
    resources = data["resources"]
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
        if set(item) != {"url", "raw_path", "sha256", "status", "retrieved_at"}:
            raise PolicyViolationError("Resource schema missing/extra fields")
        url = item["url"]
        raw_path = item["raw_path"]
        expected_sha = item["sha256"]
        status = item["status"]
        retrieved_at = item["retrieved_at"]

        if not all(isinstance(x, str) and x for x in (url, raw_path, expected_sha, retrieved_at)):
            raise PolicyViolationError(f"Resource missing required fields: {item}")
        if status != 200:
            raise PolicyViolationError(f"Policy resource {url} status is {status}, expected 200")

        try:
            valid_hash(expected_sha)
            aware_timestamp(retrieved_at)
        except ValueError:
            raise PolicyViolationError("invalid policy hash/timestamp") from None
        if url in seen_urls:
            raise PolicyViolationError("Duplicate policy URL")
        file_path = project_root / raw_path
        guard_path(project_root, file_path)
        file_path = file_path.resolve()
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
    has_agent = False

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
        clean_val = val.split("#", 1)[0].strip()
        if any(ord(c) < 32 and c not in "\t\r\n" for c in stripped):
            raise RobotsDeniedError("Control characters in robots.txt")
        if directive == "user-agent":
            has_agent = True
        elif directive in {"allow", "disallow", "crawl-delay", "request-rate"} and not has_agent:
            raise RobotsDeniedError("Robots rule lacks User-agent group")
        if directive in {"allow", "disallow"} and clean_val and not clean_val.startswith(("/", "*")):
            raise RobotsDeniedError("Malformed robots rule path")
        if directive == "crawl-delay":
            try:
                cd = float(clean_val)
                if not math.isfinite(cd) or cd < 0:
                    raise ValueError
                crawl_delay = cd if crawl_delay is None else max(crawl_delay, cd)
            except ValueError:
                raise RobotsDeniedError(f"Malformed Crawl-delay numeric value: '{clean_val}'") from None
        elif directive == "request-rate":
            match = re.fullmatch(r"([1-9]\d{0,8})/([1-9]\d{0,8})", clean_val)
            if match is None:
                raise RobotsDeniedError("Malformed Request-rate; expected positive requests/seconds")
            interval = int(match[2]) / int(match[1])
            crawl_delay = interval if crawl_delay is None else max(crawl_delay, interval)
        elif directive in {"user-agent", "sitemap", "host"} and not clean_val:
            raise RobotsDeniedError("Empty required robots directive value")
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
            if research_key(k_lower):
                raise ParseError(f"Forbidden research attribute '{k}' detected in paper HTML")
            if tag.lower() == "meta" and k_lower in ("name", "property") and v:
                v_lower = v.strip().lower()
                if research_key(v_lower):
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
        if key not in self.raw_meta or not self.raw_meta[key]:
            if required:
                raise ParseError(f"Missing required citation meta tag: '{key}'")
            return None
        values = self.raw_meta[key]
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
            paper_url(landing_url)
            fixed_parser(parser_version)
            aware_timestamp(retrieved_at)
        except ValueError:
            raise ParseError("Invalid parser API URL/version/aware timestamp") from None
        try:
            html_text = html_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError(f"Paper HTML is not valid UTF-8: {exc}") from exc

        self.raw_meta = {}
        self.reset()
        self.feed(html_text)
        self.close()

        raw_sha256 = hashlib.sha256(html_bytes).hexdigest()

        # Extract landing DOI
        m = PAPER_URL_REGEX.fullmatch(landing_url)
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
        if "citation_author" not in self.raw_meta or not self.raw_meta["citation_author"]:
            raise ParseError("Missing required citation_author metadata")
        authors = self.raw_meta["citation_author"]
        clean_authors = list(authors)
        if any(not a.strip() for a in authors):
            raise ParseError("Empty citation_author value")

        # Nullable PDF URL with strict URL validation
        pdf_url = self._get_singleton("citation_pdf_url", required=False)
        if pdf_url is not None:
            metadata_url(pdf_url)

        # citation_abstract_html_url checked for foreign host
        abs_url = self._get_singleton("citation_abstract_html_url", required=False)
        if abs_url is not None:
            metadata_url(abs_url)

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

def metadata_url(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "joss.theoj.org":
            raise ParseError("Foreign metadata URL rejected")
        if parsed.username or parsed.password:
            raise ParseError("User credentials in metadata URL")
        if parsed.port not in (None, 443) or parsed.query or parsed.fragment or "\\" in value or any(ord(c) <= 32 for c in value):
            raise ParseError("Unsafe metadata URL")
        if any(part in parsed.path.lower() for part in ("..", "%2e", "%2f")):
            raise ParseError("Path traversal in metadata URL")
        return value
    except ValueError:
        raise ParseError("Malformed metadata URL") from None


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
        self.last_call_timestamp: float | None = None

    def set_crawl_delay(self, crawl_delay: float | None) -> None:
        if crawl_delay is not None and crawl_delay > self.effective_interval:
            self.effective_interval = crawl_delay

    def wait(self, max_wait: float | None = None) -> None:
        now = self.clock()
        elapsed = now - self.last_call_timestamp if self.last_call_timestamp is not None else None
        if elapsed is not None and elapsed < self.effective_interval:
            to_sleep = self.effective_interval - elapsed
            if max_wait is not None and to_sleep >= max_wait:
                raise PolicyViolationError("Required robots/rate cooldown exceeds request deadline; retry later")
            self.sleeper(to_sleep)
        self.last_call_timestamp = self.clock()


def stream_bounded_fetch(
    client: httpx.Client, url: str, config: JossConfig, rate_limiter: RateLimiter,
    expected_content_type: str, dns_resolver=default_dns_resolver,
    clock=time.monotonic, attempt_audit: dict | None = None,
) -> tuple[bytes, str]:
    """Bounded identity bytes; audit marks an HTTP attempt only at client.send."""
    audit = attempt_audit if attempt_audit is not None else {}
    audit.update(attempted=False, status_code=None, body=None, complete_body=False)
    validate_url_and_dns(url, config, dns_resolver=dns_resolver)
    deadline = clock() + config.timeout_seconds
    rate_limiter.wait(max_wait=config.timeout_seconds)
    remaining = deadline - clock()
    if remaining <= 0:
        raise NetworkFetchError("Deadline exhausted before HTTP attempt")
    request = client.build_request("GET", url, headers={"User-Agent": config.user_agent, "Accept-Encoding": "identity"},
                                   timeout=remaining)
    response = None
    try:
        audit["attempted"] = True
        response = client.send(request, stream=True, follow_redirects=False)
        audit["status_code"] = response.status_code
        if clock() >= deadline:
            raise NetworkFetchError("Overall response deadline exceeded")
        headers = {}
        for key in ("content-type", "content-length", "content-encoding"):
            values = response.headers.get_list(key)
            if values:
                if len(values) != 1:
                    raise NetworkFetchError("Duplicate content header")
                headers[key] = values[0]
        if "content-encoding" in headers and headers["content-encoding"].strip().lower() != "identity":
            raise NetworkFetchError("Compressed response unsupported for bounded identity bytes")
        if "content-length" in headers:
            length = headers["content-length"]
            if re.fullmatch(r"\d{1,12}", length) is None or int(length) > config.max_body_bytes:
                raise NetworkFetchError("Malformed/oversized Content-Length")
        buffer = bytearray()
        audit["body"] = b""
        for chunk in response.iter_bytes(chunk_size=min(65536, config.max_body_bytes + 1)):
            available = config.max_body_bytes - len(buffer)
            buffer.extend(chunk[:available])
            audit["body"] = bytes(buffer)
            if len(chunk) > available:
                raise NetworkFetchError("Response exceeded max_body_bytes; retained bytes are partial")
            if clock() >= deadline:
                raise NetworkFetchError("Overall response deadline exceeded")
        audit["complete_body"] = True
        if "content-length" in headers and len(buffer) != int(headers["content-length"]):
            raise NetworkFetchError("Content-Length differs from received identity bytes")
        if 300 <= response.status_code < 400:
            raise SecurityError("Explicit redirect rejected")
        if response.status_code != 200:
            raise NetworkFetchError(f"HTTP {response.status_code} fetching allowed URL")
        if "content-type" not in headers:
            raise NetworkFetchError("Missing Content-Type header")
        media = headers["content-type"].split(";", 1)[0].strip().lower()
        if media != expected_content_type:
            raise NetworkFetchError("Content-Type does not match expected media type")
        return bytes(buffer), media
    except CrawlerError:
        raise
    except (httpx.HTTPError, OSError):
        raise NetworkFetchError("Network request/stream failed") from None
    finally:
        if response is not None:
            response.close()


# Filesystem guards apply before resolving or touching any artifact.
def guard_path(project_root: Path, target: Path) -> Path:
    root = Path(os.path.abspath(project_root))
    lexical = Path(os.path.abspath(target))
    if ".." in target.parts or not lexical.is_relative_to(root):
        raise SecurityError("Path outside lexical project root")
    for path in (lexical, *lexical.parents):
        if path.is_symlink() or path.is_junction():
            raise SecurityError("Symlink/junction in artifact path")
    resolved = lexical.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise SecurityError("Path outside resolved project root")
    return resolved


def guard_confinement_and_symlinks(project_root: Path, run_dir: Path, config: JossConfig) -> tuple[Path, Path]:
    root = Path(os.path.abspath(project_root))
    guard_path(root, root)
    public = root / DATA_ROOT_CANONICAL
    base = root / config.data_root
    guard_path(root, public)
    guard_path(root, base)
    run = Path(os.path.abspath(run_dir))
    if not run.is_relative_to(public) or not run.is_relative_to(base) or run in {public, base}:
        raise SecurityError("run_dir must be a descendant of lexical public JOSS data_root")
    guard_path(root, run)
    if not run.resolve().is_relative_to(public.resolve()):
        raise SecurityError("run_dir outside resolved public JOSS namespace")
    # Check each existing descendant before recursion; never walk through a junction.
    def scan(path):
        guard_path(root, path)
        if path.is_dir():
            for child in path.iterdir():
                scan(child)
    if run.exists():
        scan(run)
    for name in ("raw", "robots", "robots.txt", "checkpoint.json", "records.json", "checkpoint.json.tmp", "records.json.tmp"):
        guard_path(root, run / name)
    return root.resolve(), run.resolve()


def atomic_json(root: Path, target: Path, data) -> None:
    guard_path(root, target)
    temporary = target.with_name(target.name + ".tmp")
    guard_path(root, temporary)
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def write_atomic_checkpoint(run_dir: Path, checkpoint_data: dict[str, object]) -> None:
    # Public helper still checks all ancestors; crawler uses its verified project root.
    atomic_json(run_dir, run_dir / "checkpoint.json", checkpoint_data)


class JossCrawler:
    """One sequential crawler/run per process; immutable fetch evidence and strict resume."""
    def __init__(self, project_root: Path, config: JossConfig, run_dir: Path, resume=False,
                 client=None, clock=time.monotonic, sleeper=time.sleep, dns_resolver=default_dns_resolver):
        self.project_root, self.run_dir = guard_confinement_and_symlinks(project_root, run_dir, config)
        self.config, self.resume = config, resume
        self.clock, self.sleeper, self.dns_resolver = clock, sleeper, dns_resolver
        self._own_client = client is None
        self.client = client if client is not None else httpx.Client(timeout=config.timeout_seconds, follow_redirects=False, trust_env=False)
        self.rate_limiter = RateLimiter(config.min_interval_seconds, clock=clock, sleeper=sleeper)
        self.config_hash = hashlib.sha256(config.model_dump_json().encode("utf-8")).hexdigest()
        if resume:
            if not self.run_dir.is_dir():
                raise PolicyViolationError("run_dir missing for resume")
        else:
            if self.run_dir.exists():
                raise PolicyViolationError("run_dir already exists; use --resume")
            self.run_dir.mkdir(parents=True, exist_ok=False)
            (self.run_dir / "raw").mkdir()
            (self.run_dir / "robots").mkdir()
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.counters = CheckpointCounters(pages_fetched=0, links_found=0, duplicate_links=0,
                                           papers_parsed=0, unique_papers=0, failed_attempted_calls=0)
        self.frontier = [config.start_url]
        self.visited = []
        self.records = []
        self.fetch_attempts = []
        self.checkpoint_loaded = not resume

    def close(self):
        if self._own_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _guard(self):
        guard_confinement_and_symlinks(self.project_root, self.run_dir, self.config)

    def _refresh_counters(self):
        self.counters = CheckpointCounters(
            pages_fetched=len(self.visited), links_found=self.counters.links_found,
            duplicate_links=self.counters.duplicate_links, papers_parsed=len(self.records),
            unique_papers=len(self.records), failed_attempted_calls=sum(a.attempted and not a.success for a in self.fetch_attempts))

    def _save_checkpoint(self, status, error=None):
        self._guard()
        self._refresh_counters()
        data = dict(schema_version=1, site_id=SITE_ID, config_hash=self.config_hash, status=status,
                    created_at=self.created_at, updated_at=datetime.now(timezone.utc).isoformat(),
                    frontier=list(self.frontier), visited=[v.model_dump() for v in self.visited],
                    records=[r.model_dump(mode="json") for r in self.records], counters=self.counters.model_dump(),
                    error=error, fetch_attempts=[a.model_dump() for a in self.fetch_attempts])
        # Both artifacts exist at every checkpoint, including policy/parse failures.
        CheckpointModel.model_validate(data)
        atomic_json(self.project_root, self.run_dir / "records.json", data["records"])
        atomic_json(self.project_root, self.run_dir / "checkpoint.json", data)

    def _fetch(self, url, media):
        self._guard()
        audit = {}
        attempt_id = str(uuid.uuid4())
        error = None
        raw = None
        try:
            raw, _ = stream_bounded_fetch(self.client, url, self.config, self.rate_limiter, media,
                                         dns_resolver=self.dns_resolver, clock=self.clock, attempt_audit=audit)
            return raw
        except Exception as exc:
            error = exc.kind if isinstance(exc, CrawlerError) else type(exc).__name__
            raise
        finally:
            retrieved = datetime.now(timezone.utc).isoformat()
            raw = audit["body"] if "body" in audit else raw
            raw_path = None
            sha = None
            if raw is not None:
                sha = hashlib.sha256(raw).hexdigest()
                raw_path = "robots/" + attempt_id + ".txt" if url == self.config.robots_url else "raw/" + sha + ".html"
                target = self.run_dir / raw_path
                guard_path(self.project_root, target)
                if target.exists():
                    if target.read_bytes() != raw:
                        raise CheckpointIntegrityError("existing content-addressed raw differs")
                else:
                    with target.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
            self.fetch_attempts.append(FetchAttempt(attempt_id=attempt_id, url=url, retrieved_at=retrieved,
                attempted=audit["attempted"], success=error is None, status_code=audit["status_code"],
                raw_path=raw_path, raw_sha256=sha, complete_body=audit["complete_body"], error_kind=error))
            self._refresh_counters()

    def _fetch_robots(self):
        raw = self._fetch(self.config.robots_url, "text/plain")
        # Received bytes are already immutable on disk even if any validation below fails.
        try:
            if any(b < 32 and b not in (9, 10, 13) for b in raw):
                raise RobotsDeniedError("Control bytes in robots.txt")
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise RobotsDeniedError("robots.txt invalid UTF-8") from None
        delay, lines = validate_robots_directives(text)
        self.rate_limiter.set_crawl_delay(delay)
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(lines)
        return parser, raw

    def _raw(self, path, sha):
        target = self.run_dir / path
        guard_path(self.project_root, target)
        if not target.is_file():
            raise CheckpointIntegrityError("Referenced raw missing on disk")
        if target.stat().st_size > self.config.max_body_bytes:
            raise CheckpointIntegrityError("Referenced raw exceeds body cap")
        raw = target.read_bytes()
        if len(raw) > self.config.max_body_bytes or hashlib.sha256(raw).hexdigest() != sha:
            raise CheckpointIntegrityError("Raw body SHA-256/size mismatch")
        return raw

    def _verify_checkpoint_integrity(self):
        self._guard()
        def read(path):
            guard_path(self.project_root, path)
            return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=check_duplicate_keys,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        try:
            chk = CheckpointModel.model_validate(read(self.run_dir / "checkpoint.json"))
        except Exception as exc:
            raise CheckpointIntegrityError("Checkpoint schema validation failed") from exc
        if chk.config_hash != self.config_hash:
            raise CheckpointIntegrityError("Checkpoint config_hash mismatch")
        try:
            records_file = self.run_dir / "records.json"
            if not records_file.is_file():
                raise CheckpointIntegrityError("records.json missing on complete checkpoint or unfinished run")
            file_records = [JossPaperRecord.model_validate(row) for row in read(records_file)]
            if [row.model_dump() for row in file_records] != [row.model_dump() for row in chk.records]:
                raise CheckpointIntegrityError("records.json differs from checkpoint")
        except CheckpointIntegrityError:
            raise
        except Exception as exc:
            raise CheckpointIntegrityError("records.json malformed") from exc
        def unique(values):
            items = list(values)
            return len(items) == len(set(items))
        if (not unique(v.url for v in chk.visited) or not unique(r.doi for r in chk.records)
                or not unique(r.id for r in chk.records) or not unique(r.landing_url for r in chk.records)
                or not unique(a.attempt_id for a in chk.fetch_attempts)):
            raise CheckpointIntegrityError("duplicate visited/record/attempt identity")
        if len(chk.visited) > self.config.max_pages or len(chk.records) > self.config.max_papers:
            raise CheckpointIntegrityError("checkpoint exceeds configured caps")
        created, updated = map(datetime.fromisoformat, (chk.created_at, chk.updated_at))
        for entry in [*chk.visited, *chk.records, *chk.fetch_attempts]:
            if not created <= datetime.fromisoformat(entry.retrieved_at) <= updated:
                raise CheckpointIntegrityError("fetch/record time outside run")
        times = [datetime.fromisoformat(attempt.retrieved_at) for attempt in chk.fetch_attempts]
        if times != sorted(times):
            raise CheckpointIntegrityError("fetch timestamps are not ordered")
        for attempt in chk.fetch_attempts:
            if attempt.raw_path is not None:
                self._raw(attempt.raw_path, attempt.raw_sha256)
        successful_html = [a for a in chk.fetch_attempts if a.success and a.url != self.config.robots_url]
        if len(successful_html) != len(chk.visited):
            raise CheckpointIntegrityError("successful HTML attempts/visited mismatch")
        for visited, attempt in zip(chk.visited, successful_html):
            if visited.config_hash != self.config_hash or (visited.url, visited.raw_sha256, visited.retrieved_at) != (attempt.url, attempt.raw_sha256, attempt.retrieved_at):
                raise CheckpointIntegrityError("visited evidence differs from fetch attempt")
        listings = [v for v in chk.visited if v.type == "listing"]
        papers = [v for v in chk.visited if v.type == "paper"]
        if len(listings) > 1 or (papers and (not listings or chk.visited[0] != listings[0])):
            raise CheckpointIntegrityError("invalid listing/paper order")
        urls, found, duplicates = [], 0, 0
        if listings:
            raw = self._raw("raw/" + listings[0].raw_sha256 + ".html", listings[0].raw_sha256)
            urls, found, duplicates = JossListingParser().extract_links(raw.decode("utf-8"))
            if [v.url for v in papers] != urls[:len(papers)]:
                raise CheckpointIntegrityError("visited papers differ from actual ordered listing")
        saved_urls = {r.landing_url for r in chk.records}
        expected_frontier = [url for url in urls if url not in saved_urls] if listings else [self.config.start_url]
        if chk.frontier != expected_frontier:
            raise CheckpointIntegrityError("frontier differs from actual ordered raw listing/parsed records")
        expected = CheckpointCounters(pages_fetched=len(chk.visited), links_found=found, duplicate_links=duplicates,
            papers_parsed=len(chk.records), unique_papers=len(chk.records),
            failed_attempted_calls=sum(a.attempted and not a.success for a in chk.fetch_attempts))
        if chk.counters != expected:
            raise CheckpointIntegrityError("checkpoint counters differ from actual raw/fetch events")
        # A cached parse error still reports verified historical counters rather than fabricated zeros.
        self.created_at, self.counters = chk.created_at, chk.counters
        self.visited, self.records, self.frontier = list(chk.visited), list(chk.records), list(chk.frontier)
        self.fetch_attempts = list(chk.fetch_attempts)
        self.checkpoint_loaded = True
        # Reparse EVERY fetched paper before quota/status/HTTP, including unparsed failures.
        reparsed = []
        for visited in papers:
            raw = self._raw("raw/" + visited.raw_sha256 + ".html", visited.raw_sha256)
            record = JossPaperParser().parse_record(raw, visited.url, self.config.parser_version, visited.retrieved_at)
            reparsed.append(record)
        if len(chk.records) > len(reparsed):
            raise CheckpointIntegrityError("record without fetched paper")
        for record, parsed in zip(chk.records, reparsed):
            if record.model_dump(mode="json") != parsed.model_dump(mode="json"):
                raise CheckpointIntegrityError("Discrepancy detected between raw HTML and checkpoint record")
        if chk.status == "complete" and (not listings or len(reparsed) != len(chk.records)
                or (chk.frontier and len(chk.visited) < self.config.max_pages and len(chk.records) < self.config.max_papers)):
            raise CheckpointIntegrityError("complete checkpoint has unresolved parse/frontier/budget")
        return chk, reparsed

    def _result(self):
        return dict(status="success", site_id=SITE_ID, run_dir=str(self.run_dir), counters=self.counters.model_dump(),
                    records_count=len(self.records), records=[r.model_dump(mode="json") for r in self.records],
                    http_attempts=sum(a.attempted for a in self.fetch_attempts),
                    http_successes=sum(a.success for a in self.fetch_attempts))

    def crawl(self):
        if self.resume:
            chk, reparsed = self._verify_checkpoint_integrity()
            self.created_at, self.counters = chk.created_at, chk.counters
            self.visited, self.records, self.frontier = list(chk.visited), reparsed, list(chk.frontier)
            self.fetch_attempts = list(chk.fetch_attempts)
            parsed_urls = {r.landing_url for r in self.records}
            self.frontier = [url for url in self.frontier if url not in parsed_urls]
            self._refresh_counters()
        else:
            self._save_checkpoint("running")
        try:
            validate_policy_manifest(self.project_root, self.config.policy_manifest)
            robots, _ = self._fetch_robots()
            for url in [self.config.start_url, *(r.landing_url for r in self.records)]:
                if not robots.can_fetch(self.config.user_agent, url):
                    raise RobotsDeniedError("Robots disallows start/cached paper")
            if not self.visited:
                raw = self._fetch(self.config.start_url, "text/html")
                attempt = self.fetch_attempts[-1]
                self.visited.append(CheckpointVisitedEntry(url=attempt.url, raw_sha256=attempt.raw_sha256, type="listing",
                    retrieved_at=attempt.retrieved_at, parser_version=self.config.parser_version, config_hash=self.config_hash))
                self._refresh_counters()
                urls, found, duplicates = JossListingParser().extract_links(raw.decode("utf-8"))
                self.counters = self.counters.model_copy(update={"links_found": found, "duplicate_links": duplicates})
                self.frontier = urls
                self._save_checkpoint("running")
            while self.frontier and len(self.visited) < self.config.max_pages and len(self.records) < self.config.max_papers:
                url = self.frontier[0]
                if not robots.can_fetch(self.config.user_agent, url):
                    raise RobotsDeniedError("Robots disallows next paper")
                raw = self._fetch(url, "text/html")
                attempt = self.fetch_attempts[-1]
                self.visited.append(CheckpointVisitedEntry(url=url, raw_sha256=attempt.raw_sha256, type="paper",
                    retrieved_at=attempt.retrieved_at, parser_version=self.config.parser_version, config_hash=self.config_hash))
                self._refresh_counters()
                record = JossPaperParser().parse_record(raw, url, self.config.parser_version, attempt.retrieved_at)
                self.records.append(record)
                self.frontier.pop(0)
                self._save_checkpoint("running")
            self._save_checkpoint("complete")
            return self._result()
        except Exception as exc:
            kind = exc.kind if isinstance(exc, CrawlerError) else type(exc).__name__
            self._save_checkpoint("failed", error={"kind": kind, "message": str(exc)})
            raise
