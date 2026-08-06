"""Sealed provider boundary for choosing from one Runtime-owned ChoicePage."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from affordance_runtime.choice_contracts import ChoicePlannerResponse, ChoicePlanningRequest, SelectChoice
from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.planning_request_serializer import (
    serialize_choice_planning_request,
)

STEP_CHOICE_PROMPT_VERSION = "strict-step-choice-v1"


class DisplayedChoiceCandidate(BaseModel):
    """The only model-authored value accepted at the strict choice boundary."""

    model_config = {"extra": "forbid", "frozen": True}
    choice_id: str = Field(min_length=1)


class StepChoicePlanner(Protocol):
    def select(self, request: ChoicePlanningRequest) -> ChoicePlannerResponse: ...


@dataclass
class StrictStepChoicePlanner:
    """Model adapter that can only return an ID displayed on the supplied page."""

    model: ModelPort
    config: ModelConfig = field(
        default_factory=lambda: ModelConfig(
            temperature=0.0,
            max_tokens=128,
            prompt_version=STEP_CHOICE_PROMPT_VERSION,
        )
    )
    model_call_count: int = field(default=0, init=False)

    async def select(self, request: ChoicePlanningRequest) -> SelectChoice:
        payload = serialize_choice_planning_request(request)
        self.model_call_count += 1
        candidate = await self.model.generate_structured(
            (
                ModelMessage(
                    role="system",
                    content=(
                        "Select exactly one Runtime-provided choice_id from the supplied page. "
                        "Never invent actions, targets, parameters, effects, selectors, "
                        "coordinates, backend handles, locators, approvals, or capabilities."
                    ),
                ),
                ModelMessage(
                    role="user",
                    content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            ),
            DisplayedChoiceCandidate,
            self.config,
        )
        return SelectChoice(candidate.choice_id, "model_selected_presented_choice")
