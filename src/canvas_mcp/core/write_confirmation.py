"""Shared wording for writes Canvas accepted but did not visibly perform.

Canvas frequently answers 200 while doing less than asked: rubric
associations it silently ignored (#180/#181/#190), announcements downgraded
to plain discussions for tokens without permission (#220), and module-item
"done" PUTs that no-op when the item has no must_mark_done requirement
(#221). The house rule is: never report success for a state the user cannot
see in Canvas. Centralising the wording keeps that failure legible and
identical across tools instead of drifting per call site.
"""

from typing import Any


def unconfirmed_write_warning(what: str, facts: dict[str, Any], remedy: str) -> str:
    """Format the 'Canvas accepted this but created nothing' warning."""
    lines = [f"⚠️  Could not confirm {what}.\n"]
    lines += [f"{label}: {value}\n" for label, value in facts.items() if value is not None]
    lines.append(f"{remedy}\n")
    return "".join(lines)
