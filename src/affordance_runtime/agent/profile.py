"""Frozen generic loop profile; wiring and budget migration are later stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentLoopProfile:
    max_policy_decisions: int
    max_consecutive_observation_only: int
    max_recoveries_per_stall: int

    def __post_init__(self) -> None:
        values = (
            self.max_policy_decisions,
            self.max_consecutive_observation_only,
            self.max_recoveries_per_stall,
        )
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("agent loop profile values must be positive exact integers")


DEFAULT_AGENT_LOOP_PROFILE = AgentLoopProfile(30, 8, 1)
