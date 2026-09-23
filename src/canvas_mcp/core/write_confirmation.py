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
from dataclasses import dataclass
from typing import Any

from .credentials import get_request_credentials
from .write_outcome import WriteOutcome


def unconfirmed_write_warning(what: str, facts: dict[str, Any], remedy: str) -> str:
    """Format the 'Canvas accepted this but created nothing' warning."""
    lines = [f"⚠️  Could not confirm {what}.\n"]
    lines += [f"{label}: {value}\n" for label, value in facts.items() if value is not None]
    lines.append(f"{remedy}\n")
    return "".join(lines)


@dataclass(frozen=True, eq=False)
class ConfirmationClaim:
    """One reservation's identity; finishing it cannot release a later owner."""

    _guard: "ConfirmationGuard"
    _nonce: str

    def finish(self, outcome: WriteOutcome) -> bool:
        """Consume this handle; return whether a proven no-write claim was freed."""
        return self._guard._finish_claim(self, outcome)


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
        # A mismatch is terminal, including when another request owns the
        # reservation and later releases it after a definite rejection.
        self._burned: set[str] = set()
        # None marks a finished, spent owning claim; legacy release cannot free it.
        self._claims: dict[str, ConfirmationClaim | None] = {}
        self._last_now = float("-inf")
        self._last_monotonic = time.monotonic()

    def reset(self) -> None:
        """Discard redeemed-token state (used by tests)."""
        self._redeemed.clear()
        self._burned.clear()
        self._claims.clear()

    def _now(self) -> float:
        """An epoch clock that cannot roll back or freeze token lifetimes."""
        monotonic = time.monotonic()
        elapsed = max(0.0, monotonic - self._last_monotonic)
        self._last_monotonic = monotonic
        self._last_now = max(self._last_now + elapsed, time.time())
        return self._last_now

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
        expiry = int((now if now is not None else self._now()) + self._ttl)
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

    def _authenticate(self, token: object, now: float) -> tuple[int, str] | None:
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
        if expiry < now:
            return None
        return expiry, nonce

    def check(self, token: str, fingerprint: str) -> str | None:
        """Verify a token; burn authentic mismatches. Return an error, or None."""
        parsed = self._parse(token)
        if parsed is None:
            return "❌ That confirmation token is malformed. Run the preview again."
        expiry, nonce, authmac, fpmac = parsed

        # Authenticator first: proves we issued it (and is what reserve checks).
        if not hmac.compare_digest(authmac, self._auth_mac(expiry, nonce)):
            return "❌ That confirmation token is malformed. Run the preview again."
        now = self._now()
        if not hmac.compare_digest(fpmac, self._fp_mac(expiry, nonce, fingerprint)):
            if expiry >= now:
                self._purge(now)
                self._redeemed[nonce] = float(expiry)
                self._burned.add(nonce)
            return (
                "❌ This confirmation does not match. Either the request changed "
                "since the preview, or the preview was handled by a different "
                f"server process. {self.nothing_done} Preview again and confirm "
                "the new token."
            )
        if expiry < now:
            return "❌ That confirmation expired. Run the preview again."

        self._purge(now)
        if nonce in self._redeemed:
            return (
                f"❌ That confirmation was already used. {self.nothing_done} "
                "Run the preview again."
            )
        return None

    def reserve(self, token: str) -> bool:
        """Claim an authenticated, unexpired nonce if not already spent.

        This is fingerprint-independent; callers must first ``check`` the
        request binding. ``check`` makes genuine mismatches terminal even if
        another request already holds the nonce. Legacy error paths may still
        call ``reserve`` to consume an otherwise unused token.

        There is no capacity eviction: dropping an unexpired claim would
        resurrect the token. Only authenticated tokens enter the map; expired
        entries are removed on subsequent guard activity, not by a timer.

        The nonce is retained until the token's OWN signed expiry (not now+TTL),
        which is exactly its remaining valid lifetime. No ``await`` between the
        membership test and the write keeps it atomic on the event loop.
        """
        # Authentication and cleanup must use one sample: a second sample
        # could expire and remove an existing claim AFTER authentication.
        now = self._now()
        authed = self._authenticate(token, now)
        if authed is None:
            return False
        expiry, nonce = authed
        self._purge(now)
        if nonce in self._redeemed:
            return False
        self._redeemed[nonce] = float(expiry)
        return True

    def claim(self, token: str, fingerprint: str) -> ConfirmationClaim | str:
        """Validate binding and reserve synchronously, with no intervening await."""
        error = self.check(token, fingerprint)
        if error:
            return error
        if not self.reserve(token):
            return (f"❌ That confirmation was already used. {self.nothing_done} "
                    "Run the preview again.")
        parsed = self._parse(token)
        assert parsed is not None  # reserve authenticated this same token
        claim = ConfirmationClaim(self, parsed[1])
        self._claims[parsed[1]] = claim
        return claim

    def _finish_claim(self, claim: ConfirmationClaim, outcome: WriteOutcome) -> bool:
        if self._claims.get(claim._nonce) is not claim:
            return False
        # Finishing is single-use even when the outcome is uncertain or burned.
        self._claims[claim._nonce] = None
        if (claim._nonce in self._burned or
                outcome not in (WriteOutcome.NOT_DISPATCHED, WriteOutcome.REJECTED)):
            return False
        del self._claims[claim._nonce]
        return self._redeemed.pop(claim._nonce, None) is not None

    def release(self, token: str) -> None:
        """Owner-only: release after proven no write, unless a mismatch burned it."""
        parsed = self._parse(token)
        if (parsed is not None and parsed[1] not in self._burned
                and parsed[1] not in self._claims):
            self._redeemed.pop(parsed[1], None)

    def _purge(self, now: float | None = None) -> None:
        """Forget claims whose tokens have expired anyway."""
        if now is None:
            now = self._now()
        for nonce in [n for n, expiry in self._redeemed.items() if expiry < now]:
            self._redeemed.pop(nonce, None)
            self._burned.discard(nonce)
            self._claims.pop(nonce, None)


def preview_with_token(
    guard: ConfirmationGuard,
    fingerprint: str,
    tool_name: str,
    preview: str,
    action: str = "delete",
) -> str:
    """Render a destructive-tool preview that ends with a fresh single-use token.

    Used by every delete tool (#318): the preview must show exactly what the
    token authorizes, and the fingerprint must be derived from that same
    content so a changed target stops matching.

    ``action`` names the verb for tools whose irreversible write is not a
    deletion -- ``update_syllabus`` replaces a body Canvas keeps no history
    for. Telling the user a replace would "delete" something, or that nothing
    was deleted when content was about to be overwritten, describes the wrong
    risk. Defaults to "delete" so every existing call site reads unchanged.
    """
    nothing_done = "Nothing deleted." if action == "delete" else guard.nothing_done
    return (
        f"PREVIEW — {nothing_done}\n\n"
        f"{preview.rstrip()}\n\n"
        f"Confirmation token: {guard.issue(fingerprint)}\n"
        f"Show this preview to the user. To {action}, call {tool_name} again "
        "with this confirmation_token and identical arguments. The token is "
        "single-use, expires in 5 minutes, and stops matching if the target "
        "changes in the meantime."
    )


def redeem_confirmation(guard: ConfirmationGuard, token: str, fingerprint: str) -> str | None:
    """Verify and reserve a token for the current request.

    Returns an error message (and the guarded action must NOT run) or None
    once the token's nonce is claimed. A mismatching genuine token is burned
    so a swapped-then-reverted argument set cannot replay it within its TTL —
    the same rule the messaging tools apply.

    Deliberately NO ``release()`` path for the delete tools: the messaging
    tools hand a claim back on a provable rejection so a send can be retried,
    but a failed DELETE is cheap to re-preview and a fresh preview re-checks
    the target. Spending the token on any confirm attempt is the safe side.
    """
    error = guard.check(token, fingerprint)
    if error:
        return error
    if not guard.reserve(token):
        return (
            f"❌ That confirmation was already used. {guard.nothing_done} "
            "Run the preview again."
        )
    return None
