"""Risk levels used by the permission system."""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    """How dangerous an action is.

    LOW     - read-only or trivially reversible (open an app, read a permitted
              file, search the web). Runs automatically.
    MEDIUM  - modifies state in a limited, recoverable way (edit a file, run a
              dev command, download). Needs confirmation unless the user has
              granted "Always Allow" for that exact tool + scope.
    HIGH    - destructive, costly or externally visible (delete files, install
              software, change settings, send messages, financial actions).
              Always needs explicit confirmation; "Always Allow" is never
              offered.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}[self.value]

    def __ge__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank >= other.rank

    def __gt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank > other.rank

    def __le__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank <= other.rank

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank < other.rank
