"""Sealed model-facing boundary for selecting a displayed semantic choice."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from affordance_runtime.choice_contracts import ChoicePlanningRequest, SelectChoice


class DisplayedChoiceCandidate(BaseModel):
    """The only model-authored value accepted at the strict choice boundary."""

    model_config = {"extra": "forbid", "frozen": True}
    choice_id: str = Field(min_length=1)


class StepChoicePlanner(Protocol):
    async def select(self, request: ChoicePlanningRequest) -> SelectChoice: ...
