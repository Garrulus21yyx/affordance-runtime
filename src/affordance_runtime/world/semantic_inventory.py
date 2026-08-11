"""Profile-relative semantic inventory truth for one observation source."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_SEMANTIC_INVENTORY_COUNT = 1_000_000
UNASSESSED_SEMANTIC_INVENTORY_PROFILE = "unassessed"


class SemanticInventoryStatus(StrEnum):
    UNASSESSED = "unassessed"
    EMPTY = "empty"
    REPRESENTED = "represented"
    PARTIAL = "partial"


@dataclass(frozen=True)
class SemanticInventorySummary:
    """Conserved counts relative only to the named semantic inventory profile."""

    profile_id: str = UNASSESSED_SEMANTIC_INVENTORY_PROFILE
    status: SemanticInventoryStatus = SemanticInventoryStatus.UNASSESSED
    recognized_target_count: int = 0
    projected_target_count: int = 0
    actionable_target_count: int = 0
    non_executable_target_count: int = 0
    omitted_target_count: int = 0
    informational_target_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("semantic inventory requires a profile identity")
        if len(self.profile_id) > 96:
            raise ValueError("semantic inventory profile identity is too long")
        if not isinstance(self.status, SemanticInventoryStatus):
            raise TypeError("semantic inventory status must be typed")
        counts = (
            self.recognized_target_count,
            self.projected_target_count,
            self.actionable_target_count,
            self.non_executable_target_count,
            self.omitted_target_count,
            self.informational_target_count,
        )
        if any(type(value) is not int for value in counts):
            raise TypeError("semantic inventory counts must be exact integers")
        if any(value < 0 or value > MAX_SEMANTIC_INVENTORY_COUNT for value in counts):
            raise ValueError("semantic inventory count is outside the bounded range")
        if self.recognized_target_count != (
            self.projected_target_count + self.omitted_target_count
        ):
            raise ValueError("semantic inventory recognized-count conservation failed")
        if self.projected_target_count != (
            self.actionable_target_count + self.non_executable_target_count
        ):
            raise ValueError("semantic inventory projected-count conservation failed")
        if self.informational_target_count > self.non_executable_target_count:
            raise ValueError("informational targets must be a non-executable subset")
        if self.status is SemanticInventoryStatus.UNASSESSED:
            if any(counts):
                raise ValueError("unassessed semantic inventory cannot carry counts")
        elif self.status is SemanticInventoryStatus.EMPTY:
            if any(counts):
                raise ValueError("empty semantic inventory requires all counts to be zero")
        elif self.status is SemanticInventoryStatus.REPRESENTED:
            if (
                self.recognized_target_count == 0
                or self.recognized_target_count != self.projected_target_count
                or self.omitted_target_count != 0
            ):
                raise ValueError("represented semantic inventory requires full non-empty projection")
        elif (
            self.recognized_target_count == 0
            or self.omitted_target_count == 0
        ):
            raise ValueError("partial semantic inventory requires recognized omission")

    @classmethod
    def unassessed(
        cls,
        profile_id: str = UNASSESSED_SEMANTIC_INVENTORY_PROFILE,
    ) -> SemanticInventorySummary:
        return cls(profile_id, SemanticInventoryStatus.UNASSESSED)

    @classmethod
    def assessed(
        cls,
        profile_id: str,
        *,
        recognized_target_count: int,
        projected_target_count: int,
        actionable_target_count: int,
        non_executable_target_count: int,
        omitted_target_count: int,
        informational_target_count: int,
    ) -> SemanticInventorySummary:
        status = (
            SemanticInventoryStatus.EMPTY
            if recognized_target_count == 0
            else SemanticInventoryStatus.REPRESENTED
            if omitted_target_count == 0
            else SemanticInventoryStatus.PARTIAL
        )
        return cls(
            profile_id,
            status,
            recognized_target_count,
            projected_target_count,
            actionable_target_count,
            non_executable_target_count,
            omitted_target_count,
            informational_target_count,
        )
