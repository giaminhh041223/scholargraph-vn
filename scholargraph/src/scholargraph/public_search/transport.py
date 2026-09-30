"""Bounded HTTP transport; no raw exception text, secrets or implicit auth fallback."""
from __future__ import annotations
import hashlib
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping
import httpx
from .contracts import PublicSearchConfig, SearchError, Source

class TransportError(RuntimeError):
    def __init__(self, error: SearchError):
        self.error = error
        super().__init__(error.message)

@dataclass(frozen=True)
class TransportResponse:
    body: bytes
    sha256: str
    content_type: str
    elapsed_seconds: float
    attempts: int

@dataclass
class RateState:
    """Service reuses this process-local state across request-scoped transports."""
    locks: dict = field(default_factory=lambda: {s: threading.Lock() for s in ("openalex", "arxiv")})
    next_times: dict = field(default_factory=lambda: {s: None for s in ("openalex", "arxiv")})

class Transport:
    def __init__(self, config: PublicSearchConfig, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 environ: Mapping[str, str] | None = None, rate_state: RateState | None = None):
        self.config = config
        self.client = client if client is not None else httpx.Client(follow_redirects=False, trust_env=False)
        self._owns_client = client is None
        self.clock, self.sleeper, self.wall_clock = clock, sleeper, wall_clock
        self.environ = os.environ if environ is None else environ
        state = RateState() if rate_state is None else rate_state
        self._locks, self._next = state.locks, state.next_times
        self._deadline = self.clock() + config.deadline_seconds

    def close(self):
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def deadline(self) -> float:
        return self._deadline

    def _fail(self, source, kind, message, retry=None):
        raise TransportError(SearchError(kind=kind, message=message, source=source,
                                        retry_after_seconds=retry, record_index=None))

    def _wait(self, source, delay, deadline, kind="timeout"):
        if delay >= deadline-self.clock():
            self._fail(source, kind, "required wait exceeds request deadline", delay)
        if delay > 0:
            self.sleeper(delay)
        if self.clock() >= deadline:
            self._fail(source, kind, "request deadline exhausted", delay)

    def _retry_after(self, source, response):
        values=response.headers.get_list("retry-after")
        if not values:
            return None
        if len(values) != 1:
            self._fail(source, "schema", "duplicate Retry-After")
        value=values[0].strip()
        if value.isascii() and value.isdigit():
            try:
                delay=float(value)
            except ValueError:
                self._fail(source, "schema", "invalid Retry-After")
            if not math.isfinite(delay):
                self._fail(source, "schema", "invalid Retry-After")
            return delay
        try:
            parsed=parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                raise ValueError()
            return max(0.0,(parsed-self.wall_clock()).total_seconds())
        except (ValueError, TypeError, OverflowError):
            self._fail(source, "schema", "invalid Retry-After")

    def get(self, source: Source, params: Mapping[str, str | int], *, deadline: float) -> TransportResponse:
        if source not in self.config.sources:
            raise ValueError("unknown source")
        policy=self.config.sources[source]
        if not policy.source_policy_verified:
            self._fail(source, "policy", "source policy not verified; EXT-01B audit required")
        if type(deadline) not in {int, float} or not math.isfinite(deadline):
            self._fail(source, "config", "invalid deadline")
        deadline = min(deadline, self._deadline)
        forbidden={"api_key", "apikey", "key", "token", "authorization", "access_token"}
        if any(k.casefold() in forbidden for k in params):
            self._fail(source, "config", "secret parameters forbidden")
        if any(type(k) is not str or type(v) not in {str, int} for k,v in params.items()):
            self._fail(source, "request", "invalid transport parameters")
        headers={"Accept": ", ".join(policy.content_types), "User-Agent": "ScholarGraph-public-search/1.0.0"}
        if policy.auth_mode == "bearer":
            if policy.key_env not in self.environ or not self.environ[policy.key_env].strip():
                self._fail(source, "auth", "required bearer credential missing")
            key=self.environ[policy.key_env]
            if any(ord(c)<33 or ord(c)>126 for c in key):
                self._fail(source, "auth", "invalid bearer credential")
            headers["Authorization"]="Bearer " + key
        start=self.clock()
        remaining=deadline-self.clock()
        if remaining <= 0 or not self._locks[source].acquire(timeout=remaining):
            self._fail(source, "timeout", "deadline waiting for source lock")
        try:
            for attempt in range(policy.max_retries+1):
                next_time=self._next[source]
                if next_time is not None:
                    self._wait(source,max(0.0,next_time-self.clock()),deadline)
                remaining=deadline-self.clock()
                if remaining <= 0:
                    self._fail(source, "timeout", "request deadline exhausted")
                self._next[source]=self.clock()+policy.interval_seconds
                retry_delay=None
                kind="upstream"
                try:
                    with self.client.stream("GET", policy.endpoint, params=params, headers=headers,
                                            timeout=min(policy.timeout_seconds,remaining), follow_redirects=False) as response:
                        if self.clock() >= deadline:
                            self._fail(source,"timeout","response exceeded request deadline")
                        status=response.status_code
                        if status in {401,403}:
                            self._fail(source,"auth","upstream authentication rejected")
                        if status == 429 or status in {500,502,503,504}:
                            kind="quota" if status == 429 else "upstream"
                            retry_delay=self._retry_after(source,response)
                            if retry_delay is None:
                                retry_delay=policy.backoff_seconds * 2**attempt
                        elif status != 200:
                            self._fail(source,"upstream",f"upstream HTTP {status}")
                        else:
                            content_types=response.headers.get_list("content-type")
                            if len(content_types) != 1:
                                self._fail(source,"schema","missing/duplicate Content-Type")
                            content_type=content_types[0].split(";",1)[0].strip().lower()
                            if content_type not in policy.content_types:
                                self._fail(source,"schema","unexpected Content-Type")
                            lengths=response.headers.get_list("content-length")
                            if lengths:
                                if len(lengths)!=1 or len(lengths[0])>20 or not lengths[0].isascii() or not lengths[0].isdigit():
                                    self._fail(source,"schema","invalid Content-Length")
                                if int(lengths[0]) > policy.max_body_bytes:
                                    self._fail(source,"schema","body exceeds byte cap")
                            chunks=[]; size=0
                            for chunk in response.iter_bytes():
                                size+=len(chunk)
                                if size>policy.max_body_bytes:
                                    self._fail(source,"schema","body exceeds byte cap")
                                if self.clock()>=deadline:
                                    self._fail(source,"timeout","body exceeded request deadline")
                                chunks.append(chunk)
                            body=b"".join(chunks)
                            if not body:
                                self._fail(source,"schema","empty response body")
                            return TransportResponse(body,hashlib.sha256(body).hexdigest(),content_type,self.clock()-start,attempt+1)
                except httpx.TimeoutException:
                    kind="timeout"; retry_delay=policy.backoff_seconds * 2**attempt
                except httpx.RequestError:
                    kind="upstream"; retry_delay=policy.backoff_seconds * 2**attempt
                # Retain upstream cooldown even when this request cannot wait/retry.
                self._next[source]=max(self._next[source], self.clock()+retry_delay)
                if attempt == policy.max_retries:
                    self._fail(source,kind,"upstream retries exhausted",retry_delay)
                self._wait(source,retry_delay,deadline,kind)
        finally:
            self._locks[source].release()
