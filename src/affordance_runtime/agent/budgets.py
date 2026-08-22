"""Typed execution budget for the single continuous agent run."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StandaloneRunBudget:
    """Task-owned budget for one CoreLoop run."""

    turns: int

    def __post_init__(self) -> None:
        if type(self.turns) is not int or self.turns < 1:
            raise ValueError("standalone run turns must be positive")
