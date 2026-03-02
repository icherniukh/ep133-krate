"""Slot selection strategies for the TUI.

Architecture
------------
SlotSelector (ABC)
    └── RangeSelector  — numeric ranges / lists: "200", "201-210", "101,201-210"

To add a new selection mechanic:
  1. Subclass SlotSelector and implement resolve(slots).
  2. Extend parse_selector() to detect and dispatch to the new class.

Possible future selectors:
  WildcardSelector("*kick*")  — match sample names against a glob pattern
  EmptySelector()             — all slots where row.exists is False
  InverseSelector(inner)      — complement of another selector's result
  TagSelector("drum")         — once a sample database is in place
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .state import SlotRow


class SlotSelector(ABC):
    """Resolves a selection expression to a set of matching slot numbers."""

    @abstractmethod
    def resolve(self, slots: dict[int, SlotRow]) -> set[int]:
        """Return the subset of slot numbers from `slots` that match."""
        ...


class RangeSelector(SlotSelector):
    """Selects slots by explicit numbers and/or inclusive ranges.

    Expression syntax: comma-separated tokens; each token is either a
    single slot number or a "lo-hi" inclusive range.

    Examples
    --------
    "200"           → {200}
    "201,202"       → {201, 202}
    "200-299"       → {200, 201, ..., 299}
    "101,201-210"   → {101, 201, 202, ..., 210}

    Slot numbers absent from the available set are silently skipped.
    Raises ValueError on non-integer tokens.
    """

    def __init__(self, expr: str) -> None:
        self._expr = expr

    def resolve(self, slots: dict[int, SlotRow]) -> set[int]:
        result: set[int] = set()
        for token in self._expr.replace(" ", "").split(","):
            if not token:
                continue
            if "-" in token:
                lo_str, hi_str = token.split("-", 1)
                lo, hi = int(lo_str), int(hi_str)
                result.update(s for s in range(lo, hi + 1) if s in slots)
            else:
                s = int(token)
                if s in slots:
                    result.add(s)
        return result


def parse_selector(expr: str) -> SlotSelector:
    """Parse a selector expression and return the appropriate SlotSelector.

    Currently only handles numeric range expressions (RangeSelector).
    Extend this function to dispatch on expression syntax for new types —
    e.g. detect a leading '*' for WildcardSelector, reserved words like
    'empty' or 'stereo', regex patterns prefixed with '/', etc.
    """
    return RangeSelector(expr)
