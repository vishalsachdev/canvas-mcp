"""Internal write evidence; error dictionaries retain their public JSON shape."""
from enum import Enum


class WriteOutcome(Enum):
    NOT_DISPATCHED = 'not_dispatched'
    REJECTED = 'rejected'
    MAY_HAVE_WRITTEN = 'may_have_written'


# Existing messaging policy: timeout, conflict, rate limit and 5xx are uncertain.
NO_WRITE_STATUSES = frozenset({400, 401, 403, 404, 422})


class RequestFailure(dict[str, str]):
    """Carry transport evidence in an attribute, never a new wire field.

    Plain dictionaries and errors reconstructed from presentation text have no
    evidence and must be treated as uncertain by confirmation callers.
    """

    def __init__(self, message: str, outcome: WriteOutcome) -> None:
        super().__init__(error=message)
        self.outcome = outcome
