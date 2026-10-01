"""Machine-readable date blocks for the ``raw_dates`` option (issue 418).

The formatted read tools keep one date and drop the rest, so an agent cannot
tell "no due date" from "the date lives in a field the summary does not show".
These helpers copy date fields exactly as Canvas returned them: ISO 8601
strings, with null kept as JSON ``null``.

Field names were measured against a live checkpointed discussion on
2026-10-01 (fixture: ``tests/fixtures/canvas_raw_dates.json``):

* ``has_sub_assignments`` and ``checkpoints`` appear on the assignments list
  and single-assignment endpoints only with ``include[]=checkpoints``.
* Each checkpoint carries ``tag`` (``reply_to_topic`` / ``reply_to_entry``),
  ``due_at``, ``unlock_at``, ``lock_at``, ``only_visible_to_overrides``,
  ``overrides``, ``name`` and ``points_possible``.
* The single-assignment endpoint returns ``all_dates`` only with the boolean
  query parameter ``all_dates=true``; ``include[]=all_dates`` is ignored there.
* A discussion topic's embedded ``assignment`` already carries
  ``has_sub_assignments`` and ``checkpoints`` but never ``all_dates``.

The block is metadata only. It is built from an explicit allowlist, so the
``submission`` object that ``list_assignments`` requests, grading counts and
any user field never reach it. Author-controlled text (checkpoint ``name``,
the section or group ``title`` in ``all_dates``) is left out too, so nothing
in the block needs an untrusted-content fence.
"""

from __future__ import annotations

import json
from typing import Any

ASSIGNMENT_DATE_FIELDS: tuple[str, ...] = ("due_at", "unlock_at", "lock_at", "updated_at")
_ALL_DATES_ENTRY_FIELDS: tuple[str, ...] = (
    "id", "base", "set_type", "set_id", "due_at", "unlock_at", "lock_at",
)
_CHECKPOINT_FIELDS: tuple[str, ...] = (
    "tag", "due_at", "unlock_at", "lock_at", "only_visible_to_overrides",
)
# Every checkpoint in the live capture had ``overrides: []``, so the override
# shape is doc-derived, unverified. The allowlist keeps dates and the target
# ids, and drops ``student_ids`` and any override title.
_CHECKPOINT_OVERRIDE_FIELDS: tuple[str, ...] = (
    "id", "set_type", "set_id", "course_section_id", "group_id",
    "due_at", "unlock_at", "lock_at",
)
_TOPIC_DATE_FIELDS: tuple[str, ...] = ("delayed_post_at", "lock_at", "todo_date")

CHECKPOINTED_NOTE = (
    "Checkpointed discussion: the parent due_at is null by design. "
    "The due dates are on the checkpoints."
)
TOPIC_ALL_DATES_NOTE = (
    "The discussion-topic endpoint does not return all_dates. For section and "
    "override dates call get_assignment_details with raw_dates=True."
)


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy only the listed keys Canvas actually returned (absent stays absent)."""
    return {key: source[key] for key in fields if key in source}


def assignment_raw_dates(assignment: dict[str, Any]) -> dict[str, Any]:
    """Date metadata for one assignment, values exactly as Canvas returned them."""
    block: dict[str, Any] = {"assignment_id": assignment.get("id")}
    for field in ASSIGNMENT_DATE_FIELDS:
        # These four are always present on Canvas assignment objects; a
        # missing one is reported as null rather than dropped.
        block[field] = assignment.get(field)

    all_dates = assignment.get("all_dates")
    if isinstance(all_dates, list):
        block["all_dates"] = [
            _pick(entry, _ALL_DATES_ENTRY_FIELDS)
            for entry in all_dates
            if isinstance(entry, dict)
        ]

    if "has_sub_assignments" in assignment:
        block["has_sub_assignments"] = assignment["has_sub_assignments"]

    checkpoints = assignment.get("checkpoints")
    if isinstance(checkpoints, list):
        block["checkpoints"] = []
        for checkpoint in checkpoints:
            if not isinstance(checkpoint, dict):
                continue
            entry = _pick(checkpoint, _CHECKPOINT_FIELDS)
            overrides = checkpoint.get("overrides")
            if isinstance(overrides, list):
                entry["overrides"] = [
                    _pick(override, _CHECKPOINT_OVERRIDE_FIELDS)
                    for override in overrides
                    if isinstance(override, dict)
                ]
            block["checkpoints"].append(entry)

    if assignment.get("has_sub_assignments") is True and assignment.get("due_at") is None:
        block["note"] = CHECKPOINTED_NOTE
    return block


def topic_raw_dates(topic: dict[str, Any], topic_id: str | int) -> dict[str, Any]:
    """Date metadata for a discussion topic and, if graded, its assignment."""
    block: dict[str, Any] = {"topic_id": topic.get("id", topic_id)}
    block.update(_pick(topic, _TOPIC_DATE_FIELDS))
    if "is_checkpointed" in topic:
        block["is_checkpointed"] = topic["is_checkpointed"]

    assignment = topic.get("assignment")
    assignment_id = topic.get("assignment_id")
    if isinstance(assignment, dict):
        block["assignment"] = assignment_raw_dates(assignment)
        block["notes"] = [TOPIC_ALL_DATES_NOTE]
    elif assignment_id is not None:
        block["assignment"] = None
        block["notes"] = [
            f"Graded topic (assignment_id {assignment_id}), but Canvas did not "
            "embed the assignment in this response. Call get_assignment_details "
            "with raw_dates=True for its dates."
        ]
    else:
        block["assignment"] = None
        block["notes"] = ["Ungraded topic: there is no assignment, so no assignment dates."]
    return block


def render_raw_dates(payload: dict[str, Any]) -> str:
    """Render the block appended to a tool's text output."""
    return (
        "\n\nRaw dates (JSON, values exactly as Canvas returned them; "
        "null means Canvas returned null):\n"
        + json.dumps(payload, indent=2)
    )
