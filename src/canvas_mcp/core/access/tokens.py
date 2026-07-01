"""Signed, single-use approval tokens (stdlib only — no I/O, no Azure)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenClaims:
    oid: str
    jti: str
    exp: int  # unix seconds


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64u(sig)


def mint_token(*, oid: str, jti: str, exp: int, secret: str) -> str:
    payload = _b64u(json.dumps({"oid": oid, "jti": jti, "exp": exp}).encode())
    return f"{payload}.{_sign(payload, secret)}"


def verify_token(token: str, *, secret: str, now: int) -> TokenClaims | None:
    """Return claims if the token is well-formed, untampered, and unexpired."""
    try:
        payload_b64, sig = token.split(".", 1)
        expected = _sign(payload_b64, secret)
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64u_decode(payload_b64))
        exp = int(data["exp"])
        if exp <= now:
            return None
        return TokenClaims(oid=str(data["oid"]), jti=str(data["jti"]), exp=exp)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
