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

    # A token is ``expiry.nonce.authmac.fpmac`` — all fixed-width hex/int, so a
    # legitimate token is well under this. Anything longer is rejected before
    # any hashing (cheap flood defense).
    _MAX_TOKEN_LEN = 256

    def __init__(self, ttl_seconds: int = 300, nothing_done: str = "Nothing was sent.") -> None:
        self._ttl = ttl_seconds
        # Wording for "the guarded action did not happen" — "sent" for the
        # messaging tools, "deleted" for the delete tools (#318).
        self.nothing_done = nothing_done
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

    def _auth_mac(self, expiry: int, nonce: str) -> str:
        """Fingerprint-INDEPENDENT authenticator: proves this process issued
        the token, so ``reserve`` can authenticate a token whose fingerprint no
        longer matches (the burn-on-mismatch path) without being forgeable."""
        return hmac.new(
            self._secret, f"auth|{expiry}|{nonce}".encode(), hashlib.sha256
        ).hexdigest()[:32]

    def _fp_mac(self, expiry: int, nonce: str, fingerprint: str) -> str:
        """Content binding: ties the token to the exact previewed request."""
        return hmac.new(
            self._secret, f"{expiry}|{nonce}|{fingerprint}".encode(), hashlib.sha256
        ).hexdigest()[:32]

    def issue(self, fingerprint: str, now: float | None = None) -> str:
        """Mint a token committing to ``fingerprint`` until it expires."""
        expiry = int((now if now is not None else time.time()) + self._ttl)
        nonce = secrets.token_hex(8)
        return (
            f"{expiry}.{nonce}."
            f"{self._auth_mac(expiry, nonce)}.{self._fp_mac(expiry, nonce, fingerprint)}"
        )

    def _parse(self, token: object) -> tuple[int, str, str, str] | None:
        if not isinstance(token, str) or len(token) > self._MAX_TOKEN_LEN:
            return None
        parts = token.split(".")
        if len(parts) != 4:
            return None
        try:
            expiry = int(parts[0])
        except ValueError:
            return None
        return expiry, parts[1], parts[2], parts[3]

    def _authenticate(self, token: object) -> tuple[int, str] | None:
        """Return (expiry, nonce) if the token was genuinely issued by THIS
        process and has not expired; else None. Never touches the fingerprint,
        so it works on the burn-on-mismatch path — but a forged/unsigned token
        fails here and is never recorded (closes the token-store DoS)."""
        parsed = self._parse(token)
        if parsed is None:
            return None
        expiry, nonce, authmac, _ = parsed
        if not hmac.compare_digest(authmac, self._auth_mac(expiry, nonce)):
            return None
        if expiry < time.time():
            return None
        return expiry, nonce

    def check(self, token: str, fingerprint: str) -> str | None:
        """Verify a token against the current request. Returns an error, or None."""
        parsed = self._parse(token)
        if parsed is None:
            return "❌ That confirmation token is malformed. Run the preview again."
        expiry, nonce, authmac, fpmac = parsed

        # Authenticator first: proves we issued it (and is what reserve checks).
        if not hmac.compare_digest(authmac, self._auth_mac(expiry, nonce)):
            return "❌ That confirmation token is malformed. Run the preview again."
        if not hmac.compare_digest(fpmac, self._fp_mac(expiry, nonce, fingerprint)):
            return (
                "❌ This confirmation does not match. Either the request changed "
                "since the preview, or the preview was handled by a different "
                f"server process. {self.nothing_done} Preview again and confirm "
                "the new token."
            )
        if expiry < time.time():
            return "❌ That confirmation expired. Run the preview again."

        self._purge()
        if nonce in self._redeemed:
            return (
                f"❌ That confirmation was already used. {self.nothing_done} "
                "Run the preview again."
            )
        return None

    def reserve(self, token: str) -> bool:
        """Mark an authenticated token's nonce spent. Serves BOTH callers:

        - a fresh confirmation claiming its nonce (prevents double-submit), and
        - the burn-on-mismatch path invalidating a genuine token whose
          fingerprint no longer matches (prevents revert-replay).

        Both must ALWAYS record for an authenticated, unexpired token — a burn
        that failed to record would let the mismatched token become reusable
        once an unrelated older claim expired, reopening revert-replay. There
        is therefore NO capacity cap and NO eviction here (either would drop a
        burn or resurrect a used nonce). It is safe because only authenticated,
        unexpired tokens reach this point (round-9): forged/unsigned/expired
        tokens are rejected by ``_authenticate`` and never recorded, so the map
        holds at most the genuinely-issued unexpired tokens — itself bounded by
        issuance-rate × TTL, and each entry self-drains on its own expiry.

        The nonce is retained until the token's OWN signed expiry (not now+TTL),
        which is exactly its remaining valid lifetime. No ``await`` between the
        membership test and the write keeps it atomic on the event loop.
        """
        authed = self._authenticate(token)
        if authed is None:
            return False
        expiry, nonce = authed
        self._purge()
        if nonce in self._redeemed:
            return False
        self._redeemed[nonce] = float(expiry)
        return True

    def release(self, token: str) -> None:
        """Give a claim back after a path that ended without writing."""
        parsed = self._parse(token)
        if parsed is not None:
            self._redeemed.pop(parsed[1], None)

    def _purge(self) -> None:
        """Forget claims whose tokens have expired anyway."""
        now = time.time()
        for nonce in [n for n, expiry in self._redeemed.items() if expiry < now]:
            self._redeemed.pop(nonce, None)


def preview_with_token(
    guard: ConfirmationGuard, fingerprint: str, tool_name: str, preview: str
) -> str:
    """Render a destructive-tool preview that ends with a fresh single-use token.

    Used by every delete tool (#318): the preview must show exactly what the
    token authorizes, and the fingerprint must be derived from that same
    content so a changed target stops matching.
    """
    return (
        "PREVIEW — Nothing deleted.\n\n"
        f"{preview.rstrip()}\n\n"
        f"Confirmation token: {guard.issue(fingerprint)}\n"
        f"Show this preview to the user. To delete, call {tool_name} again with "
        "this confirmation_token and identical arguments. The token is "
        "single-use, expires in 5 minutes, and stops matching if the target "
        "changes in the meantime."
    )


def redeem_confirmation(guard: ConfirmationGuard, token: str, fingerprint: str) -> str | None:
    """Verify and reserve a token for the current request.

    Returns an error message (and the guarded action must NOT run) or None
    once the token's nonce is claimed. A mismatching genuine token is burned
    so a swapped-then-reverted argument set cannot replay it within its TTL —
    the same rule the messaging tools apply.
    """
    error = guard.check(token, fingerprint)
    if error:
        guard.reserve(token)
        return error
    if not guard.reserve(token):
        return (
            f"❌ That confirmation was already used. {guard.nothing_done} "
            "Run the preview again."
        )
    return None
