"""Typed execution budgets with distinct mission and standalone authority."""

from __future__ import annotations

from dataclasses import dataclass

EPISODE_TURN_HARD_CAP = 15
ORDINARY_EPISODE_TURNS = EPISODE_TURN_HARD_CAP


@dataclass(frozen=True)
class EpisodeBudget:
    """Runtime-owned budget for one Supervisor milestone episode."""

    turns: int

    def __post_init__(self) -> None:
        if type(self.turns) is not int or not 1 <= self.turns <= EPISODE_TURN_HARD_CAP:
            raise ValueError("mission episode turns must be within [1, 15]")

    @classmethod
    def ordinary(cls) -> EpisodeBudget:
        return cls(ORDINARY_EPISODE_TURNS)

    @classmethod
    def explicit(cls, turns: int) -> EpisodeBudget:
        return cls(turns)


@dataclass(frozen=True)
class StandaloneRunBudget:
    """Task-owned budget for a standalone CoreLoop run, outside mission episode policy."""

    turns: int

    def __post_init__(self) -> None:
        if type(self.turns) is not int or self.turns < 1:
            raise ValueError("standalone run turns must be positive")
