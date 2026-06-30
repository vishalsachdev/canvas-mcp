"""Runtime-mutable overlay allowlist on a Table backend.

The Azure Table client is wrapped behind a tiny backend protocol so this
module (and its tests) never import azure directly. The real backend lives in
``factory.py`` and is built lazily only when the feature is enabled.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

GRANT_PK = "grant"
PENDING_PK = "pending"


class ConcurrencyConflict(Exception):
    """An ETag-guarded replace lost a race (someone else updated the row)."""


@dataclass(frozen=True)
class Requester:
    oid: str
    upn: str
    display_name: str


@dataclass(frozen=True)
class Grant:
    oid: str
    upn: str
    display_name: str
    granted_utc: str


class InMemoryBackend:
    """Reference + test backend. Dict keyed by (PartitionKey, RowKey)."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict] = {}
        self._etag = 0

    def _bump(self) -> str:
        self._etag += 1
        return f"etag-{self._etag}"

    def get(self, pk: str, rk: str) -> dict | None:
        row = self._rows.get((pk, rk))
        return dict(row) if row else None

    def upsert(self, entity: dict) -> None:
        entity = dict(entity)
        entity["etag"] = self._bump()
        self._rows[(entity["PartitionKey"], entity["RowKey"])] = entity

    def replace_if_unmodified(self, entity: dict, etag: str) -> None:
        key = (entity["PartitionKey"], entity["RowKey"])
        current = self._rows.get(key)
        if current is None or current.get("etag") != etag:
            raise ConcurrencyConflict("etag mismatch")
        entity = dict(entity)
        entity["etag"] = self._bump()
        self._rows[key] = entity

    def query(self, pk: str) -> list[dict]:
        return [dict(r) for (p, _), r in self._rows.items() if p == pk]

    def delete(self, pk: str, rk: str) -> None:
        self._rows.pop((pk, rk), None)


class AccessStore:
    def __init__(self, backend, *, cache_ttl_seconds: int = 30, clock=time.time) -> None:
        self._backend = backend
        self._ttl = cache_ttl_seconds
        self._clock = clock
        self._cache: dict[str, bool] = {}
        self._cache_at: dict[str, float] = {}

    # --- authorization read path (hot) ---
    def is_granted(self, oid: str) -> bool:
        now = self._clock()
        if self._ttl and oid in self._cache and now - self._cache_at[oid] < self._ttl:
            return self._cache[oid]
        granted = self._backend.get(GRANT_PK, oid) is not None
        self._cache[oid] = granted
        self._cache_at[oid] = now
        return granted

    def grant(self, req: Requester, *, jti: str) -> None:
        self._backend.upsert({
            "PartitionKey": GRANT_PK, "RowKey": req.oid,
            "upn": req.upn, "displayName": req.display_name,
            "grantedUtc": _utcnow_iso(self._clock), "tokenJti": jti,
            "source": "self-service",
        })
        self._cache.pop(req.oid, None)

    def revoke(self, oid: str) -> bool:
        if self._backend.get(GRANT_PK, oid) is None:
            return False
        self._backend.delete(GRANT_PK, oid)
        self._cache.pop(oid, None)
        return True

    def list_grants(self) -> list[Grant]:
        return [
            Grant(oid=r["RowKey"], upn=r.get("upn", ""),
                  display_name=r.get("displayName", ""),
                  granted_utc=r.get("grantedUtc", ""))
            for r in self._backend.query(GRANT_PK)
        ]

    # --- request/dedup + single-use consume ---
    def note_request(self, req: Requester, *, jti: str, exp: int,
                     now_iso: str, cooldown_hours: int) -> bool:
        existing = self._backend.get(PENDING_PK, req.oid)
        if existing and existing.get("status") == "pending":
            last = existing.get("lastNotifiedUtc", "")
            if _within_cooldown(last, now_iso, cooldown_hours):
                return False  # suppress duplicate notify
        self._backend.upsert({
            "PartitionKey": PENDING_PK, "RowKey": req.oid,
            "upn": req.upn, "displayName": req.display_name,
            "firstSeenUtc": existing.get("firstSeenUtc", now_iso) if existing else now_iso,
            "lastNotifiedUtc": now_iso,
            "notifyCount": (existing.get("notifyCount", 0) if existing else 0) + 1,
            "status": "pending", "tokenJti": jti, "tokenExp": exp,
        })
        return True

    def get_pending(self, oid: str) -> dict | None:
        return self._backend.get(PENDING_PK, oid)

    def consume_pending(self, oid: str, jti: str) -> bool:
        row = self._backend.get(PENDING_PK, oid)
        if not row or row.get("status") != "pending" or row.get("tokenJti") != jti:
            return False
        row["status"] = "granted"
        try:
            self._backend.replace_if_unmodified(row, row["etag"])
        except ConcurrencyConflict:
            return False
        return True


def _utcnow_iso(clock) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))


def _within_cooldown(last_iso: str, now_iso: str, hours: int) -> bool:
    if not last_iso:
        return False
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        last = time.mktime(time.strptime(last_iso, fmt))
        now = time.mktime(time.strptime(now_iso, fmt))
    except (ValueError, TypeError):
        return False
    return (now - last) < hours * 3600
