"""Frozen generic no-progress recovery profile."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentLoopProfile:
    max_consecutive_observation_only: int
    max_recovery_retries: int

    def __post_init__(self) -> None:
        values = (
            self.max_consecutive_observation_only,
            self.max_recovery_retries,
        )
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("agent loop profile values must be positive exact integers")


DEFAULT_AGENT_LOOP_PROFILE = AgentLoopProfile(8, 1)
