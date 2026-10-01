"""Optional drift and fragment guards for the body-writing tools (issue 419).

``edit_page_content``, ``update_assignment``, ``update_discussion_topic`` and
``update_syllabus`` replace a whole HTML body with what the caller sends. To
change one sentence an agent reads the object, rebuilds the body and writes it
back, and anything another editor changed in between is silently reverted
(a stale copy once overwrote a live page for about 25 minutes).

The guards here add refusals, never new writes:

- Drift. Pages and assignments carry ``updated_at``: ``expect_updated_at``
  refuses unless the freshly fetched value is the same instant the caller read,
  compared as timestamps (the same instant arrives as ``...Z`` from Canvas and
  as ``...-05:00`` from ``format_date`` when ``TIMEZONE`` is set). Discussion
  topics and the syllabus have NO ``updated_at`` (measured live: a topic GET's
  only timestamps are created_at, delayed_post_at, last_reply_at, lock_at and
  posted_at), so they use ``expect_body_sha256``, a SHA-256 of the fetched body.
- ``find``/``replace``: substitute one fragment of the freshly fetched body
  instead of sending a full body. ``find`` must occur exactly once.
- ``require``: substrings that must already be present in the fetched body.

After a guarded write the tool reads the object back. It reports the write as
confirmed only when the read-back proves it: ``updated_at`` advanced (where the
object has one), the stored body equals the body the write should have produced, compared
after whitespace normalization only (so attribute changes and unrelated
content loss both count), and every other requested
field reads back with the value sent. Anything it cannot establish, including
HTML that Canvas rewrote, is reported through ``unconfirmed_write_warning``,
never as success.

Omitting every guard parameter must leave each tool's behaviour unchanged, so
callers only enter this module when :attr:`BodyGuard.active` is true.
"""

import datetime
import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .untrusted_content import FENCE_LEAK_ERROR, contains_fence_markers
from .write_confirmation import unconfirmed_write_warning

NOTHING_WRITTEN = "Nothing was written."

_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class BodyGuard:
    """The guard arguments one tool call supplied."""

    expect_updated_at: str | None = None
    find: str | None = None
    replace: str | None = None
    require: list[str] | None = None
    expect_body_sha256: str | None = None

    @property
    def active(self) -> bool:
        """True when any guard parameter was supplied."""
        return (
            self.expect_updated_at is not None
            or self.find is not None
            or self.replace is not None
            or self.require is not None
            or self.expect_body_sha256 is not None
        )

    @property
    def fragment(self) -> bool:
        """True when the caller asked for a find/replace edit."""
        return self.find is not None or self.replace is not None


def body_sha256(body: str | None) -> str:
    """Hex SHA-256 of a body exactly as Canvas returned it (None counts as '')."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def normalize_html(html: str | None) -> str:
    """HTML with whitespace normalized and nothing else changed.

    Attributes and markup are kept, so an href-only edit is still visible;
    only runs of whitespace collapse, and whitespace between tags is dropped.
    """
    text = " ".join((html or "").split())
    return re.sub(r">\s+<", "><", text)


def parse_timestamp(value: str | None) -> datetime.datetime | None:
    """Parse an ISO 8601 instant; a missing offset is read as UTC.

    Truncated to whole seconds: Canvas reports ``updated_at`` at second
    precision and ``format_date`` (what read tools show) drops fractions, so a
    caller copying a value from tool output must still match.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed.replace(microsecond=0)


def validate_guard(guard: BodyGuard, body_param: str, body: str | None) -> str | None:
    """Reject inconsistent guard arguments before any Canvas call.

    Returns an error string, or None when the arguments are usable.
    """
    if guard.fragment:
        if guard.find is None or guard.replace is None:
            return "❌ find and replace must be supplied together. " + NOTHING_WRITTEN
        if not guard.find.strip():
            return "❌ find must contain non-whitespace text. " + NOTHING_WRITTEN
        if body is not None:
            return (
                f"❌ Supply either {body_param} (the full body) or find/replace "
                f"(one fragment), not both. {NOTHING_WRITTEN}"
            )
        # Backstop for issue 239, as for full bodies.
        if contains_fence_markers(guard.replace):
            return FENCE_LEAK_ERROR
    if guard.require is not None:
        for item in guard.require:
            if not isinstance(item, str) or item == "":
                return "❌ require entries must be non-empty strings. " + NOTHING_WRITTEN
    if guard.expect_updated_at is not None and parse_timestamp(guard.expect_updated_at) is None:
        return (
            f"❌ expect_updated_at '{guard.expect_updated_at}' is not an ISO 8601 "
            f"timestamp (e.g. '2026-09-09T14:00:00Z'). {NOTHING_WRITTEN}"
        )
    if guard.expect_body_sha256 is not None and not _SHA256_HEX.fullmatch(
        guard.expect_body_sha256.strip()
    ):
        return (
            "❌ expect_body_sha256 must be a 64-character hex SHA-256 of the body "
            f"as Canvas returned it. {NOTHING_WRITTEN}"
        )
    return None


def check_updated_at(current: dict[str, Any], expected: str, what: str) -> str | None:
    """Refuse unless ``current['updated_at']`` is the instant the caller expected."""
    actual_raw = current.get("updated_at")
    actual = parse_timestamp(actual_raw)
    if actual is None:
        return (
            f"❌ Cannot check for changes: Canvas returned no usable updated_at for "
            f"this {what} (got {actual_raw!r}). {NOTHING_WRITTEN}"
        )
    if actual != parse_timestamp(expected):
        return (
            f"❌ The {what} changed since it was read. {NOTHING_WRITTEN}\n"
            f"  Expected updated_at: {expected}\n"
            f"  Current updated_at:  {actual_raw}\n"
            f"Read it again, re-apply the edit to the current content, and retry "
            f"with the new updated_at."
        )
    return None


def check_body_hash(current_body: str | None, expected: str, what: str) -> str | None:
    """Refuse unless the fetched body hashes to ``expected``."""
    actual = body_sha256(current_body)
    if actual != expected.strip().lower():
        return (
            f"❌ The {what} changed since it was read. {NOTHING_WRITTEN}\n"
            f"  Expected body SHA-256: {expected}\n"
            f"  Current body SHA-256:  {actual}\n"
            f"Read it again, re-apply the edit to the current content, and retry "
            f"with the new hash."
        )
    return None


def check_require(body: str, require: list[str] | None, what: str) -> str | None:
    """Refuse when a required substring is missing from the fetched body."""
    missing = [item for item in (require or []) if item not in body]
    if missing:
        listed = "\n".join(f"  - {item!r}" for item in missing)
        return (
            f"❌ The current {what} is missing {len(missing)} required "
            f"string(s). {NOTHING_WRITTEN}\n{listed}"
        )
    return None


def apply_find_replace(body: str, find: str, replace: str, what: str) -> tuple[str | None, str | None]:
    """Substitute the single occurrence of ``find``; return (new_body, error)."""
    count = body.count(find)
    if count != 1:
        hint = (
            "Check the exact text, including HTML markup and entities."
            if count == 0 else
            "Extend find with surrounding text until it matches exactly once."
        )
        return None, (
            f"❌ find must match exactly once in the current {what}, but it "
            f"matched {count} times. {NOTHING_WRITTEN} {hint}"
        )
    return body.replace(find, replace, 1), None


def prepare_body(
    guard: BodyGuard,
    current: dict[str, Any],
    body_field: str,
    full_body: str | None,
    what: str,
) -> tuple[str | None, str | None]:
    """Run the pre-write checks against a freshly fetched object.

    Returns ``(body_to_write, error)``. ``body_to_write`` is None when the call
    does not touch the body (e.g. ``update_assignment`` changing only a date
    under ``expect_updated_at``).
    """
    current_body = current.get(body_field) or ""
    if guard.expect_updated_at is not None:
        error = check_updated_at(current, guard.expect_updated_at, what)
        if error:
            return None, error
    if guard.expect_body_sha256 is not None:
        error = check_body_hash(current.get(body_field), guard.expect_body_sha256, what)
        if error:
            return None, error
    error = check_require(current_body, guard.require, what)
    if error:
        return None, error
    if guard.fragment:
        assert guard.find is not None and guard.replace is not None
        return apply_find_replace(current_body, guard.find, guard.replace, what)
    return full_body, None


BODY_MISMATCH = (
    "the stored body is not the expected body (compared after whitespace "
    "normalization only): Canvas dropped or rewrote content, so the edit "
    "cannot be confirmed"
)


def body_readback_failure(expected_body: str, stored_body: str | None) -> str | None:
    """Does the stored body equal the body this write should have produced?

    ``expected_body`` is the whole body sent: for find/replace, the fetched
    body with the one substitution applied. Equality after whitespace-only
    normalization is the proof. Checking just the edited fragment is not:
    a read-back that lost unrelated content would still pass. None = proven.
    """
    if stored_body is None:
        return "the read-back has no body"
    if normalize_html(stored_body) != normalize_html(expected_body):
        return BODY_MISMATCH
    return None


def _same_value(field: str, sent: Any, got: Any) -> bool:
    """Whether a read-back value matches what was sent for ``field``."""
    if got is None:
        return False
    if isinstance(sent, bool):
        return got is sent
    if isinstance(sent, (int, float)):
        try:
            return float(got) == float(sent)
        except (TypeError, ValueError):
            return False
    if isinstance(sent, list):
        return isinstance(got, list) and sorted(map(str, sent)) == sorted(map(str, got))
    if field.endswith("_at"):
        sent_ts = parse_timestamp(str(sent))
        return sent_ts is not None and sent_ts == parse_timestamp(str(got))
    return str(sent) == str(got)


def readback_failure(
    *,
    guard: BodyGuard,
    before: dict[str, Any],
    after: Any,
    body_field: str,
    written_body: str | None,
    requested: dict[str, Any],
    has_updated_at: bool,
) -> str | None:
    """Check a post-write read-back. Return why it is unconfirmed, or None."""
    if not isinstance(after, dict) or "error" in after:
        detail = after.get("error") if isinstance(after, dict) else type(after).__name__
        return f"the read-back after the write failed ({detail})"
    if has_updated_at:
        old_ts = parse_timestamp(before.get("updated_at"))
        new_raw = after.get("updated_at")
        new_ts = parse_timestamp(new_raw)
        if new_ts is None:
            return f"Canvas returned no usable updated_at on read-back (got {new_raw!r})"
        if old_ts is not None and new_ts <= old_ts:
            return "updated_at did not advance, so Canvas may not have saved the change"

    if written_body is not None:
        reason = body_readback_failure(written_body, after.get(body_field))
        if reason:
            return reason

    mismatched = [
        field for field, sent in requested.items()
        if field != body_field and not _same_value(field, sent, after.get(field))
    ]
    if mismatched:
        return (
            "these requested fields did not read back with the value sent: "
            + ", ".join(mismatched)
        )
    return None


def _failed(response: Any) -> str | None:
    """The error text of a failed make_canvas_request result, else None."""
    if not isinstance(response, dict):
        return f"unexpected response type {type(response).__name__}"
    if "error" in response:
        return str(response["error"])
    return None


async def run_guarded_write(
    guard: BodyGuard,
    *,
    what: str,
    body_field: str,
    full_body: str | None,
    fetch: Callable[[], Awaitable[Any]],
    write: Callable[[str | None], Awaitable[Any]],
    refetch: Callable[[Any], Awaitable[Any]],
    requested: dict[str, Any],
    facts: dict[str, Any],
    has_updated_at: bool = True,
) -> str:
    """Fetch, check, write once, read back, and report (pages/assignments/topics).

    ``write`` receives the body to send (None leaves the body untouched) and
    performs exactly one PUT. Every refusal returns before ``write`` is called.
    ``refetch`` receives the PUT response so it can follow a renamed page slug.
    ``requested`` holds every non-body field the caller asked to change, as
    sent; each must read back unchanged for the write to count as confirmed.
    ``has_updated_at`` is False for objects Canvas gives no ``updated_at``
    (discussion topics); their drift and read-back signal is the body hash.
    """
    current = await fetch()
    error = _failed(current)
    if error:
        return f"Error fetching {what} before the guarded edit: {error}. {NOTHING_WRITTEN}"

    body, error = prepare_body(guard, current, body_field, full_body, what)
    if error:
        return error

    response = await write(body)
    error = _failed(response)
    if error:
        return f"Error updating {what}: {error}"

    after = await refetch(response)
    reason = readback_failure(
        guard=guard, before=current, after=after, body_field=body_field,
        written_body=body, requested=requested, has_updated_at=has_updated_at,
    )
    after_dict = after if isinstance(after, dict) and "error" not in after else {}
    if has_updated_at:
        report_facts = {
            **facts,
            "Previous updated_at": current.get("updated_at"),
            "New updated_at": after_dict.get("updated_at"),
        }
    else:
        report_facts = {
            **facts,
            "Previous body SHA-256": body_sha256(current.get(body_field)),
            "New body SHA-256": (
                body_sha256(after_dict.get(body_field)) if after_dict else None
            ),
        }
    if reason:
        return unconfirmed_write_warning(
            f"the {what} update",
            {"Reason": reason, **report_facts},
            f"Canvas accepted the request but the change could not be confirmed. "
            f"Open the {what} in Canvas and check it before retrying.",
        )

    lines = [f"✅ Updated the {what} (guarded edit)."]
    lines += [f"  {label}: {value}" for label, value in report_facts.items() if value is not None]
    changed = [field for field in requested if field != body_field]
    if body is not None:
        changed.insert(0, body_field)
    if changed:
        lines.append(f"  Updated fields: {', '.join(changed)}")
    lines.append(f"  Verified by reading the {what} back from Canvas")
    return "\n".join(lines)
