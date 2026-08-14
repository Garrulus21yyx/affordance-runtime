"""Single owner for grounded-agent prompts and model-message binding."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Mapping

import yaml

from affordance_runtime.agent.working_memory import AgentWorkingMemory
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_policy.contracts import ModelDecisionRequest
from affordance_runtime.model_policy.grounded_tool_contracts import ToolPolicyView
from affordance_runtime.model_policy.model_port_bridge import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model_port import ModelImageURLPart, ModelMessage, ModelTextPart


@dataclass(frozen=True)
class GroundedAgentPrompts:
    version: str
    task_state_updater: str
    actor: str
    objective_proposer: str

    def __post_init__(self) -> None:
        if not self.version or any(
            not value.strip()
            for value in (self.task_state_updater, self.actor, self.objective_proposer)
        ):
            raise ValueError("grounded-agent prompt bundle is incomplete")


@lru_cache(maxsize=1)
def load_grounded_agent_prompts() -> GroundedAgentPrompts:
    resource = files("affordance_runtime.model_policy").joinpath("prompts/grounded_agent.yaml")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {
        "version",
        "task_state_updater",
        "actor",
        "objective_proposer",
    }:
        raise ValueError("grounded-agent prompt bundle has an invalid shape")
    return GroundedAgentPrompts(
        str(raw["version"]),
        str(raw["task_state_updater"]),
        str(raw["actor"]),
        str(raw["objective_proposer"]),
    )


@dataclass(frozen=True)
class GroundedPolicyContextBinder:
    """Bind internal policy state to one explicit provider message boundary."""

    prompts: GroundedAgentPrompts = field(default_factory=load_grounded_agent_prompts)

    def task_state_messages(
        self,
        view: ToolPolicyView,
        request: ModelDecisionRequest,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
    ) -> tuple[ModelMessage, ...]:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        public = {
            "task_goal": to_json_compatible(view.task_brief),
            "current_unified_world": self._world(view, include_images),
            "world_transition": {
                "initial_observation": not bool(view.world_transition),
                "latest": to_json_compatible(view.world_transition),
            },
            "previous_agent_task_state": to_json_compatible(view.agent_task_state),
        }
        return self._messages(self.prompts.task_state_updater, public, request, include_images)

    def actor_messages(
        self,
        view: ToolPolicyView,
        request: ModelDecisionRequest,
        task_state: AgentWorkingMemory,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> tuple[ModelMessage, ...]:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        public: dict[str, object] = {
            "task_goal": to_json_compatible(view.task_brief),
            "current_unified_world": self._world(view, include_images),
            "world_transition": {
                "initial_observation": not bool(view.world_transition),
                "latest": to_json_compatible(view.world_transition),
            },
            "agent_task_state": task_state_to_public(task_state),
        }
        if include_tool_menu:
            public["tool_menu"] = tuple(
                {
                    "op": item.name,
                    "description": item.description,
                    "arguments": to_json_compatible(item.input_schema),
                }
                for item in view.tools
            )
        return self._messages(self.prompts.actor, public, request, include_images)

    def objective_messages(
        self,
        view: ToolPolicyView,
        request: ModelDecisionRequest,
        *,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        include_tool_menu: bool,
    ) -> tuple[ModelMessage, ...]:
        include_images = self._include_images(request, supports_multimodal, perception_profile)
        public: dict[str, object] = {
            "task_goal": to_json_compatible(view.task_brief),
            "current_unified_world": self._world(view, include_images),
            "world_transition": {
                "initial_observation": not bool(view.world_transition),
                "latest": to_json_compatible(view.world_transition),
            },
        }
        if include_tool_menu:
            public["tool_menu"] = tuple(
                {
                    "op": item.name,
                    "description": item.description,
                    "arguments": to_json_compatible(item.input_schema),
                }
                for item in view.tools
            )
        return self._messages(self.prompts.objective_proposer, public, request, include_images)

    @staticmethod
    def _world(view: ToolPolicyView, include_images: bool) -> dict[str, object]:
        entities = tuple(
            dict(item) if include_images else {**dict(item), "marked": False}
            for item in view.grounding_index
        )
        return {
            "entities": to_json_compatible(entities),
            "runtime_state": to_json_compatible(view.current_world),
        }

    @staticmethod
    def _include_images(
        request: ModelDecisionRequest,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
    ) -> bool:
        include_images = perception_uses_images(request, perception_profile)
        if include_images and (not supports_multimodal or not request.image_inputs):
            raise ValueError("selected grounded perception requires a current image input")
        return include_images

    @staticmethod
    def _messages(
        system_prompt: str,
        public: Mapping[str, object],
        request: ModelDecisionRequest,
        include_images: bool,
    ) -> tuple[ModelMessage, ...]:
        text = json.dumps(public, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if not include_images:
            return (
                ModelMessage(role="system", content=system_prompt),
                ModelMessage(role="user", content=text),
            )
        parts: list[ModelTextPart | ModelImageURLPart] = [ModelTextPart(text=text)]
        for image in request.image_inputs:
            encoded = base64.b64encode(image.data).decode("ascii")
            parts.append(ModelImageURLPart(image_url=f"data:{image.mime_type};base64,{encoded}"))
        return (
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=tuple(parts)),
        )


def task_state_to_public(memory: AgentWorkingMemory) -> dict[str, object]:
    return {
        "authority": "advisory_agent_belief",
        "goal": memory.goal,
        "items": tuple(
            {"description": item.description, "status": item.status.value}
            for item in memory.items
        ),
        "derived_facts": memory.derived_facts,
        "next_step": memory.next_step,
        "ready_to_finalize": memory.ready_to_finalize,
        "blockers": memory.blockers,
    }
