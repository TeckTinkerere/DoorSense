"""Bounded original analyses; signed IDs identify expired runs without tombstones."""

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import secrets
from threading import RLock
import time
from typing import Any, Callable
import uuid


class AnalysisMissing(Exception):
    def __init__(self, expired: bool):
        self.expired = expired


@dataclass(frozen=True)
class Analysis:
    id: str
    expires_at: float
    model: Any
    cycles: tuple
    response_json: bytes
    csv_bytes: bytes
    zip_bytes: bytes


class AnalysisStore:
    """At most max_count runs, with fixed TTL and oldest-created eviction.

    A process-local signature recognises previously issued IDs after expiry or
    eviction, so a growing tombstone table is unnecessary. Restarting the process
    clears all runs and its signing key. Reads do not extend the retention time.
    """

    def __init__(self, max_count: int = 3, ttl_seconds: float = 1800,
                 clock: Callable[[], float] = time.time):
        import math

        if max_count <= 0 or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("Store count and lifetime must be positive and finite.")
        self.max_count = max_count
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._runs: OrderedDict[str, Analysis] = OrderedDict()
        self._key = secrets.token_bytes(32)
        self._lock = RLock()

    def new_id(self) -> str:
        nonce = uuid.uuid4().hex
        signature = hmac.new(self._key, nonce.encode("ascii"), hashlib.sha256).hexdigest()[:32]
        return f"{nonce}.{signature}"

    def _issued(self, identifier: str) -> bool:
        parts = identifier.split(".")
        if len(parts) != 2 or len(parts[0]) != 32 or len(parts[1]) != 32:
            return False
        try:
            expected = hmac.new(self._key, parts[0].encode("ascii"), hashlib.sha256).hexdigest()[:32]
            return hmac.compare_digest(parts[1].encode("ascii"), expected.encode("ascii"))
        except UnicodeEncodeError:
            return False

    def _purge(self):
        now = self.clock()
        for identifier in [key for key, value in self._runs.items() if value.expires_at <= now]:
            del self._runs[identifier]

    def put(self, analysis: Analysis):
        with self._lock:
            self._purge()
            while len(self._runs) >= self.max_count:
                self._runs.popitem(last=False)
            self._runs[analysis.id] = analysis

    def get(self, identifier: str) -> Analysis:
        with self._lock:
            self._purge()
            try:
                return self._runs[identifier]
            except KeyError:
                raise AnalysisMissing(expired=self._issued(identifier)) from None

    def delete(self, identifier: str):
        with self._lock:
            self.get(identifier)
            del self._runs[identifier]

    def __len__(self):
        with self._lock:
            self._purge()
            return len(self._runs)
