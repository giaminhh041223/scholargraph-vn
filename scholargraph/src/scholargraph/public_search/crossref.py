"""Exact DOI enrichment sidecar; public-search Source v1 remains frozen."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from pydantic import Field, field_validator, model_validator

from .contracts import Hash, PaperRecord, StrictModel, Text, aware, read_json, safe_url, unique_object
from .fusion import normalize_doi

PARSER_VERSION = "crossref-1.0.0"
_LOCK = threading.Lock()
_NEXT = 0.0
_FORBIDDEN = {"label", "labels", "qrels", "split", "splits", "train", "dev", "test",
              "heldout", "held-out", "relevance", "relevance_score", "benchmark"}
_FORBIDDEN_NORMALIZED = {re.sub(r"[^a-z0-9]", "", key) for key in _FORBIDDEN}


class CrossrefError(ValueError):
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


def reject_research(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
            tokens = re.sub(r"([a-z])([A-Z])", r"\1_\2", key).casefold()
            tokens = set(re.split(r"[^a-z0-9]+", tokens))
            if (normalized in _FORBIDDEN_NORMALIZED or tokens & _FORBIDDEN_NORMALIZED
                    or any(word in normalized for word in ("label", "split", "qrels", "heldout", "benchmark", "relevance"))):
                raise CrossrefError("schema", "research labels/splits forbidden")
            reject_research(child)
    elif isinstance(value, list):
        for child in value:
            reject_research(child)


class CrossrefConfig(StrictModel):
    schema_version: Literal[1]
    endpoint: Literal["https://api.crossref.org/works"]
    pool: Literal["public"]
    auth_mode: Literal["anonymous"]
    policy_url: Literal["https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/"]
    policy_retrieved_at: datetime
    policy_evidence_path: Text
    policy_evidence_sha256: Hash
    interval_seconds: Annotated[float, Field(ge=1, le=60)]
    concurrency: Literal[1]
    timeout_seconds: Annotated[float, Field(gt=0, le=60)]
    deadline_seconds: Annotated[float, Field(gt=0, le=120)]
    max_retries: Literal[0]
    max_body_bytes: Annotated[int, Field(gt=0, le=10000000)]

    @field_validator("policy_retrieved_at")
    @classmethod
    def timestamp(cls, value):
        return aware(value)

    @field_validator("concurrency", "max_retries", mode="before")
    @classmethod
    def integer(cls, value):
        if type(value) is not int:
            raise ValueError("integer required")
        return value


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise CrossrefError("storage", "path outside permitted project directory")
    return resolved


def load_config(root: Path, path: Path) -> CrossrefConfig:
    row = read_json(_inside(root, path))
    reject_research(row)
    config = CrossrefConfig.model_validate_json(json.dumps(row, allow_nan=False))
    policy = _inside(root / "data/public_search", root / config.policy_evidence_path)
    if hashlib.sha256(policy.read_bytes()).hexdigest() != config.policy_evidence_sha256:
        raise CrossrefError("policy", "policy evidence hash mismatch")
    return config


class Evidence(StrictModel):
    source: Literal["crossref"]
    raw_path: Text
    raw_sha256: Hash
    raw_field: Text
    parser_version: Literal["crossref-1.0.0"]
    availability: Literal["present", "unavailable"]


class CrossrefMetadata(StrictModel):
    doi: Text
    title: Text
    type: Text
    authors: list[Text] | None
    publication_year: Annotated[int, Field(ge=1800, le=2100)] | None
    abstract: Text | None
    venue: Text | None
    publisher: Text | None
    landing_url: Text | None
    citation_count: Annotated[int, Field(ge=0)] | None

    @field_validator("landing_url")
    @classmethod
    def url(cls, value):
        return safe_url(value) if value is not None else None


class Conflict(StrictModel):
    original_value: object
    crossref_value: object
    original_evidence: list[dict]
    crossref_evidence: Evidence


class Enrichment(StrictModel):
    schema_version: Literal[1]
    parser_version: Literal["crossref-1.0.0"]
    synthetic: bool
    requested_doi: Text
    retrieved_at: datetime | None
    metadata: CrossrefMetadata
    field_provenance: dict[str, Evidence]
    unavailable_fields: list[str]
    original: PaperRecord | None
    conflicts: dict[str, Conflict]

    @model_validator(mode="after")
    def coherent(self):
        if self.synthetic != (self.retrieved_at is None):
            raise ValueError("synthetic cannot claim live retrieval")
        if self.retrieved_at is not None:
            aware(self.retrieved_at)
        if normalize_doi(self.requested_doi) != self.metadata.doi:
            raise ValueError("DOI mismatch")
        fields = self.metadata.model_dump()
        missing = {key for key, value in fields.items() if value is None}
        if set(self.field_provenance) != set(fields) or set(self.unavailable_fields) != missing:
            raise ValueError("field evidence/availability mismatch")
        if any((entry.availability == "unavailable") != (key in missing)
               for key, entry in self.field_provenance.items()):
            raise ValueError("evidence availability mismatch")
        return self


def _text(value):
    if type(value) is not str or not value.strip():
        raise CrossrefError("schema", "invalid text metadata")
    return value.strip()


def parse_payload(raw: bytes, doi: str, *, raw_path: str, synthetic: bool,
                  retrieved_at: datetime | None, original: PaperRecord | None = None) -> Enrichment:
    try:
        row = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        reject_research(row)
        if type(row) is not dict or set(row) != {"status", "message-type", "message-version", "message"}:
            raise CrossrefError("schema", "invalid Crossref envelope")
        if row["status"] != "ok" or row["message-type"] != "work" or row["message-version"] != "1.0.0":
            raise CrossrefError("schema", "invalid Crossref envelope status/version/type")
        msg = row["message"]
        if type(msg) is not dict or msg["source"] != "Crossref":
            raise CrossrefError("schema", "invalid Crossref source")
        requested = normalize_doi(doi)
        returned = normalize_doi(_text(msg["DOI"]))
        if returned != requested or (original is not None and original.doi is not None and normalize_doi(original.doi) != requested):
            raise CrossrefError("schema", "returned/original DOI differs from requested DOI")
        if "score" in msg and (type(msg["score"]) not in {int, float} or not math.isfinite(msg["score"]) or msg["score"] < 0):
            raise CrossrefError("schema", "invalid Crossref score")
        title = msg["title"]
        if type(title) is not list or not title:
            raise CrossrefError("schema", "required title list missing/empty")
        titles = [_text(part) for part in title]
        values = {"doi": returned, "title": " ".join(titles), "type": _text(msg["type"])}
        paths = {"doi": "message.DOI", "title": "message.title", "type": "message.type"}
        for field, source in (("abstract", "abstract"), ("publisher", "publisher"), ("landing_url", "URL")):
            values[field] = _text(msg[source]) if source in msg else None
            paths[field] = "message." + source
        values["venue"] = None
        paths["venue"] = "message.container-title"
        if "container-title" in msg:
            if type(msg["container-title"]) is not list:
                raise CrossrefError("schema", "invalid container-title")
            if msg["container-title"]:
                values["venue"] = " ".join(_text(v) for v in msg["container-title"])
        values["authors"] = None
        paths["authors"] = "message.author"
        if "author" in msg:
            if type(msg["author"]) is not list:
                raise CrossrefError("schema", "invalid author list")
            names = []
            for author in msg["author"]:
                if type(author) is not dict:
                    raise CrossrefError("schema", "invalid author")
                if "name" in author:
                    names.append(_text(author["name"]))
                elif "family" in author:
                    names.append(((_text(author["given"]) + " ") if "given" in author else "") + _text(author["family"]))
                else:
                    raise CrossrefError("schema", "author lacks name")
            values["authors"] = names if names else None
        values["publication_year"] = None
        paths["publication_year"] = "message.published.date-parts"
        for source in ("published", "published-print", "published-online", "issued"):
            if source not in msg:
                continue
            info = msg[source]
            if type(info) is not dict or "date-parts" not in info:
                raise CrossrefError("schema", "invalid publication date")
            parts = info["date-parts"]
            if type(parts) is not list or len(parts) != 1 or type(parts[0]) is not list or not 1 <= len(parts[0]) <= 3 or any(type(v) is not int for v in parts[0]):
                raise CrossrefError("schema", "invalid date-parts")
            year = parts[0][0]
            date(year, parts[0][1] if len(parts[0]) >= 2 else 1, parts[0][2] if len(parts[0]) == 3 else 1)
            if not 1800 <= year <= 2100:
                raise CrossrefError("schema", "publication year outside bounds")
            if values["publication_year"] is None:
                values["publication_year"] = year
                paths["publication_year"] = f"message.{source}.date-parts"
        values["citation_count"] = None
        paths["citation_count"] = "message.is-referenced-by-count"
        if "is-referenced-by-count" in msg:
            count = msg["is-referenced-by-count"]
            if type(count) is not int or count < 0:
                raise CrossrefError("schema", "invalid citation count")
            values["citation_count"] = count
        metadata = CrossrefMetadata.model_validate(values)
        sha = hashlib.sha256(raw).hexdigest()
        evidence = {key: Evidence(source="crossref", raw_path=raw_path, raw_sha256=sha, raw_field=paths[key],
                                 parser_version=PARSER_VERSION, availability="unavailable" if value is None else "present")
                    for key, value in values.items()}
        conflicts = {}
        if original is not None:
            original_values = original.model_dump(mode="json")
            for field, value in values.items():
                if field in original_values and value is not None and original_values[field] is not None:
                    old = normalize_doi(original.doi) if field == "doi" else original_values[field]
                    if old != value:
                        conflicts[field] = Conflict(original_value=original_values[field], crossref_value=value,
                                                    original_evidence=original_values["field_provenance"][field],
                                                    crossref_evidence=evidence[field])
        return Enrichment(schema_version=1, parser_version=PARSER_VERSION, synthetic=synthetic,
                          requested_doi=requested, retrieved_at=retrieved_at, metadata=metadata,
                          field_provenance=evidence, unavailable_fields=sorted(key for key, value in values.items() if value is None),
                          original=original, conflicts=conflicts)
    except CrossrefError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        raise CrossrefError("schema", "malformed Crossref work metadata") from None


class CrossrefTransport:
    def __init__(self, config: CrossrefConfig, *, client=None, clock=time.monotonic, sleeper=time.sleep):
        self.config = config
        self.client = client if client is not None else httpx.Client(trust_env=False, follow_redirects=False)
        self._owns_client = client is None
        self.clock, self.sleeper = clock, sleeper
        self.body = b""
        self.audit = {"attempted": False, "status_code": None, "headers": {}, "complete_body": False}

    def close(self):
        if self._owns_client:
            self.client.close()

    def get(self, doi: str) -> bytes:
        global _NEXT
        url = self.config.endpoint + "/" + quote(normalize_doi(doi), safe="")
        deadline = self.clock() + self.config.deadline_seconds
        if not _LOCK.acquire(timeout=self.config.deadline_seconds):
            raise CrossrefError("timeout", "waiting for process concurrency lock")
        try:
            self.body = b""
            self.audit = {"attempted": False, "status_code": None, "headers": {}, "complete_body": False}
            delay = max(0.0, _NEXT - self.clock())
            if delay >= deadline - self.clock():
                raise CrossrefError("quota", "cooldown exceeds deadline; retry later")
            if delay:
                self.sleeper(delay)
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise CrossrefError("timeout", "request deadline exhausted")
            _NEXT = self.clock() + self.config.interval_seconds
            self.audit["attempted"] = True
            self.audit["url"] = url
            with self.client.stream("GET", url, headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "ScholarGraph-Crossref/1.0.0"},
                                    timeout=min(self.config.timeout_seconds, remaining), follow_redirects=False) as response:
                self.audit["status_code"] = response.status_code
                cooldown = self.config.interval_seconds
                selected = ("x-rate-limit-limit", "x-rate-limit-interval", "x-concurrency-limit", "retry-after", "content-type", "content-length", "content-encoding")
                for key in selected:
                    headers = response.headers.get_list(key)
                    if headers:
                        self.audit["headers"][key] = headers
                        if len(headers) != 1:
                            raise CrossrefError("schema", "duplicate policy/content header")
                recorded = self.audit["headers"]
                if self.clock() >= deadline:
                    raise CrossrefError("timeout", "response exceeded request deadline")
                if "content-encoding" in recorded and recorded["content-encoding"][0].lower().strip() != "identity":
                    raise CrossrefError("schema", "compressed response unsupported; byte cap requires identity")
                if ("x-rate-limit-limit" in recorded) != ("x-rate-limit-interval" in recorded):
                    raise CrossrefError("schema", "incomplete rate headers")
                if "x-rate-limit-limit" in recorded:
                    limit = recorded["x-rate-limit-limit"][0]
                    interval = recorded["x-rate-limit-interval"][0]
                    if not re.fullmatch(r"[1-9]\d{0,8}", limit) or not re.fullmatch(r"(?:\d+(?:\.\d+)?)s", interval):
                        raise CrossrefError("schema", "invalid rate headers")
                    seconds = float(interval[:-1])
                    if not math.isfinite(seconds) or seconds <= 0:
                        raise CrossrefError("schema", "invalid rate interval")
                    cooldown = max(cooldown, seconds / int(limit))
                if "x-concurrency-limit" in recorded and not re.fullmatch(r"[1-9]\d{0,8}", recorded["x-concurrency-limit"][0]):
                    raise CrossrefError("schema", "invalid concurrency header")
                if "retry-after" in recorded:
                    retry = recorded["retry-after"][0]
                    if not re.fullmatch(r"\d{1,8}", retry):
                        raise CrossrefError("schema", "unsupported Retry-After; retry manually later")
                    cooldown = max(cooldown, float(retry))
                _NEXT = max(_NEXT, self.clock() + cooldown)
                if "content-length" in recorded:
                    length = recorded["content-length"][0]
                    if not re.fullmatch(r"\d{1,12}", length) or int(length) > self.config.max_body_bytes:
                        raise CrossrefError("schema", "invalid/oversized Content-Length")
                chunks = []
                size = 0
                for chunk in response.iter_bytes(chunk_size=min(65536, self.config.max_body_bytes + 1)):
                    available = self.config.max_body_bytes - size
                    chunks.append(chunk[:available])
                    size += len(chunk)
                    self.body = b"".join(chunks)
                    if size > self.config.max_body_bytes:
                        raise CrossrefError("schema", "body exceeds byte cap; retained body is partial")
                    if self.clock() >= deadline:
                        raise CrossrefError("timeout", "body exceeded deadline")
                self.audit["complete_body"] = True
                status = response.status_code
                if status != 200:
                    kind = "quota" if status == 429 else "auth" if status in {401, 403} else "not_found" if status == 404 else "redirect" if 300 <= status < 400 else "upstream"
                    raise CrossrefError(kind, f"Crossref HTTP {status}; no automatic retry")
                if "content-type" not in recorded or recorded["content-type"][0].split(";", 1)[0].strip().lower() != "application/json":
                    raise CrossrefError("schema", "expected application/json Content-Type")
                if not self.body:
                    raise CrossrefError("schema", "empty body")
                return self.body
        except httpx.TimeoutException:
            raise CrossrefError("timeout", "Crossref request timed out; no automatic retry") from None
        except httpx.RequestError:
            raise CrossrefError("upstream", "Crossref network failure; no automatic retry") from None
        finally:
            _LOCK.release()


def atomic_write(path: Path, data: bytes):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def enrich(root: Path, config_path: Path, output_dir: Path, *, doi: str | None = None,
           record_path: Path | None = None, payload_path: Path | None = None, client=None) -> dict:
    """One immutable run directory. Exceptions become explicit failed result artifacts."""
    root = root.resolve()
    output = _inside(root / "data/public_search", output_dir)
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "status": "failed", "synthetic": payload_path is not None,
              "config_sha256": None, "parser_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "enrichment": None, "error": None, "request": None, "raw": None, "record_sha256": None}
    transport = None
    raw = None
    try:
        config = load_config(root, config_path)
        result["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
        original = None
        if (doi is None) == (record_path is None):
            raise CrossrefError("request", "require exactly one DOI or original record")
        if record_path is not None:
            record_raw = _inside(root / "data/public_search", record_path).read_bytes()
            row = json.loads(record_raw, object_pairs_hook=unique_object)
            reject_research(row)
            original = PaperRecord.model_validate_json(json.dumps(row, allow_nan=False))
            result["record_sha256"] = hashlib.sha256(record_raw).hexdigest()
            if original.doi is None:
                raise CrossrefError("request", "original record DOI unavailable")
            doi = original.doi
        normalized = normalize_doi(doi)
        if payload_path is not None:
            path = _inside(root / "data/public_search", payload_path)
            with path.open("rb") as stream:
                raw = stream.read(config.max_body_bytes + 1)
            if len(raw) > config.max_body_bytes:
                raw = raw[:config.max_body_bytes]
                result["request"] = {"attempted": False, "complete_body": False}
                raise CrossrefError("schema", "synthetic payload exceeds byte cap")
            result["request"] = {"attempted": False, "complete_body": True}
        else:
            transport = CrossrefTransport(config, client=client)
            raw = transport.get(normalized)
            result["request"] = transport.audit
        parsed = parse_payload(raw, normalized, raw_path="raw.json", synthetic=payload_path is not None,
                               retrieved_at=None if payload_path is not None else datetime.now(timezone.utc), original=original)
        result["enrichment"] = parsed.model_dump(mode="json")
        result["status"] = "success"
    except CrossrefError as exc:
        result["error"] = {"kind": exc.kind, "message": str(exc)}
    except (OSError, ValueError, TypeError, KeyError):
        result["error"] = {"kind": "request", "message": "invalid or missing required config/input/resource"}
    finally:
        if transport is not None:
            result["request"] = transport.audit
            raw = transport.body if transport.body else raw
            transport.close()
    if raw is not None:
        atomic_write(output / "raw.json", raw)
        result["raw"] = {"path": "raw.json", "sha256": hashlib.sha256(raw).hexdigest(), "byte_count": len(raw)}
    atomic_write(output / "result.json", json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return result
