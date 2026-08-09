"""Shared wording for writes Canvas accepted but did not visibly perform,
plus the two-step confirmation-token guard for destructive tools.

Canvas frequently answers 200 while doing less than asked: rubric
associations it silently ignored (#180/#181/#190), announcements downgraded
to plain discussions for tokens without permission (#220), and module-item
"done" PUTs that no-op when the item has no must_mark_done requirement
(#221). The house rule is: never report success for a state the user cannot
see in Canvas. Centralising the wording keeps that failure legible and
identical across tools instead of drifting per call site.

``ConfirmationGuard`` generalises the preview→token→confirm pattern that
``tools/student_write.py`` established for assignment submission, so
educator-side destructive tools can require the same explicit two-step. The
threat it addresses (issue 239) is a prompt-injected model chaining a read of
student-authored content straight into a write: a required, single-use,
content-bound token forces a human-visible preview between "decided to send"
and "sent".
"""

import hashlib
import hmac
import secrets
import time
from typing import Any

from .credentials import get_request_credentials


def unconfirmed_write_warning(what: str, facts: dict[str, Any], remedy: str) -> str:
    """Format the 'Canvas accepted this but created nothing' warning."""
    lines = [f"⚠️  Could not confirm {what}.\n"]
    lines += [f"{label}: {value}\n" for label, value in facts.items() if value is not None]
    lines.append(f"{remedy}\n")
    return "".join(lines)


class ConfirmationGuard:
    """Single-use, content-bound confirmation tokens for one destructive tool.

    Each guard instance owns a per-process signing secret and its own redeemed
    set. Tokens commit to a fingerprint the caller derives from everything the
    preview displayed (target, exact payload, caller identity), so a token
    cannot authorize different content, a different target, or a different
    caller than the preview showed.

    Deliberately per-process, like the student_write original: sharing the
    secret between replicas would let one token verify everywhere while the
    single-use claim stays process-local, so two workers could both accept it.
    A hosted deployment should use session affinity; without it, a rejected
    confirmation just means previewing again.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._secret = secrets.token_bytes(32)
        # token nonce -> when its claim can be forgotten. Keyed by nonce, not
        # fingerprint, so redeeming one token does not block a *fresh* preview
        # of identical content — each preview mints its own single-use token.
        self._redeemed: dict[str, float] = {}

    def reset(self) -> None:
        """Discard redeemed-token state (used by tests)."""
        self._redeemed.clear()

    def caller_identity(self) -> str:
        """A stable, non-reversible handle for whoever is calling.

        Hosted deployments pass a per-user Canvas token on every request; in
        stdio mode there is a single user and the constant is fine.
        """
        credentials = get_request_credentials()
        if credentials is None:
            return "stdio"
        return hmac.new(
            self._secret, credentials.api_token.encode(), hashlib.sha256
        ).hexdigest()

    def fingerprint(self, *parts: str) -> str:
        """Bind a confirmation to the caller plus the exact previewed request.

        Parts are length-prefixed before hashing so adjacent fields cannot be
        reassembled into a colliding split ("ab","c" vs "a","bc").
        """
        hasher = hashlib.sha256()
        hasher.update(self.caller_identity().encode())
        for part in parts:
            chunk = part.encode()
            hasher.update(len(chunk).to_bytes(8, "big"))
            hasher.update(chunk)
        return hasher.hexdigest()

    def issue(self, fingerprint: str, now: float | None = None) -> str:
        """Mint a token committing to ``fingerprint`` until it expires."""
        expiry = int((now if now is not None else time.time()) + self._ttl)
        nonce = secrets.token_hex(8)
        mac = hmac.new(
            self._secret, f"{expiry}|{nonce}|{fingerprint}".encode(), hashlib.sha256
        ).hexdigest()[:32]
        return f"{expiry}.{nonce}.{mac}"

    @staticmethod
    def _parse(token: str) -> tuple[int, str, str] | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        try:
            expiry = int(parts[0])
        except ValueError:
            return None
        return expiry, parts[1], parts[2]

    def check(self, token: str, fingerprint: str) -> str | None:
        """Verify a token against the current request. Returns an error, or None."""
        parsed = self._parse(token)
        if parsed is None:
            return "❌ That confirmation token is malformed. Run the preview again."
        expiry, nonce, mac = parsed

        expected = hmac.new(
            self._secret, f"{expiry}|{nonce}|{fingerprint}".encode(), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(mac, expected):
            return (
                "❌ This confirmation does not match. Either the request changed "
                "since the preview, or the preview was handled by a different "
                "server process. Nothing was sent. Preview again and confirm "
                "the new token."
            )
        if expiry < time.time():
            return "❌ That confirmation expired. Run the preview again."

        self._purge()
        if nonce in self._redeemed:
            return (
                "❌ That confirmation was already used. Nothing was sent. "
                "Run the preview again."
            )
        return None

    def reserve(self, token: str) -> bool:
        """Atomically claim a token. False if it was already claimed.

        No ``await`` between the membership test and the write, which is what
        makes this atomic on the event loop. Call ``check`` first — reserve
        only tracks single-use; it does not verify the signature.
        """
        parsed = self._parse(token)
        if parsed is None:
            return False
        _, nonce, _ = parsed
        self._purge()
        if nonce in self._redeemed:
            return False
        self._redeemed[nonce] = time.time() + self._ttl
        return True

    def release(self, token: str) -> None:
        """Give a claim back after a path that ended without writing."""
        parsed = self._parse(token)
        if parsed is not None:
            self._redeemed.pop(parsed[1], None)

    def _purge(self) -> None:
        """Forget claims whose tokens have expired anyway."""
        now = time.time()
        for fingerprint in [f for f, expiry in self._redeemed.items() if expiry < now]:
            self._redeemed.pop(fingerprint, None)
