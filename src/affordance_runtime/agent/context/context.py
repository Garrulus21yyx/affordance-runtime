"""Disposable model-facing AgentContext and opaque Runtime identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.contracts import AgentActionPageView, AgentTaskView, AgentTurnView
from affordance_runtime.agent.context.world_projection import PublicFactView
from affordance_runtime.immutable import freeze_json

if TYPE_CHECKING:
    from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot


@dataclass(frozen=True)
class ContextIdentity:
    task_revision: int
    observation_id: str
    action_space_id: str
    action_page_id: str
    context_generation: int = 0

    def __post_init__(self) -> None:
        if (
            self.task_revision <= 0
            or self.context_generation < 0
        ):
            raise ValueError("context revisions are invalid")
        if not all(value.strip() for value in (self.observation_id, self.action_space_id, self.action_page_id)):
            raise ValueError("context identity requires current observation, action space, and page")

    @property
    def context_id(self) -> str:
        payload = (
            self.task_revision,
            self.observation_id,
            self.action_space_id,
            self.action_page_id,
            self.context_generation,
        )
        digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        return f"context:{digest}"


@dataclass(frozen=True)
class AgentProgressView:
    validated_task_status: str
    verified_public_facts: tuple[PublicFactView, ...]
    unresolved_criteria: BoundedSection[str]
    unresolved_outputs: BoundedSection[str]
    truncated: bool = False


@dataclass(frozen=True)
class AgentImageInput:
    evidence_ref: str
    mime_type: str
    data: bytes = field(repr=False)
    sha256: str = ""

    def __post_init__(self) -> None:
        if (
            not self.evidence_ref.startswith("artifact:")
            or self.mime_type not in {"image/png", "image/jpeg"}
            or not isinstance(self.data, bytes)
            or not self.data
            or len(self.data) > 5 * 1024 * 1024
            or len(self.sha256) != 64
        ):
            raise ValueError("agent image input is invalid")


@dataclass(frozen=True)
class AgentGroundingEntityView:
    ref: str
    role: str
    label: str
    state: Mapping[str, object] = field(default_factory=dict)
    relation_hints: tuple[str, ...] = ()
    verbs: tuple[str, ...] = ()
    marked: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"E[1-9][0-9]{0,2}", self.ref):
            raise ValueError("grounding entity requires a bounded call-local ref")
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "relation_hints", tuple(self.relation_hints))
        object.__setattr__(self, "verbs", tuple(self.verbs))


@dataclass(frozen=True)
class AgentGroundingIndexView:
    entities: tuple[AgentGroundingEntityView, ...] = ()
    target_refs: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        entities = tuple(self.entities)
        refs = {item.ref for item in entities}
        if len(refs) != len(entities):
            raise ValueError("grounding refs must be unique")
        mapping = dict(self.target_refs)
        if set(mapping.values()) != refs or len(mapping) != len(entities):
            raise ValueError("grounding target/ref mapping must be bijective")
        object.__setattr__(self, "entities", entities)
        object.__setattr__(self, "target_refs", freeze_json(mapping))

    def private_subject_bindings(self) -> Mapping[str, str]:
        """Return call-local public ref to canonical Runtime subject identity."""

        return freeze_json({ref: target_id for target_id, ref in self.target_refs.items()})


@dataclass(frozen=True)
class AgentContext:
    context_id: str
    task: AgentTaskView
    progress: AgentProgressView
    actions: AgentActionPageView
    recent_steps: BoundedSection[AgentTurnView]
    actor_world: ActorWorldSnapshot
    image_inputs: tuple[AgentImageInput, ...] = ()
    grounding: AgentGroundingIndexView = field(default_factory=AgentGroundingIndexView)

    def __post_init__(self) -> None:
        if not self.context_id.startswith("context:"):
            raise ValueError("AgentContext requires opaque context identity")
        object.__setattr__(self, "image_inputs", tuple(self.image_inputs))
        if len(self.image_inputs) > 2 or any(not isinstance(item, AgentImageInput) for item in self.image_inputs):
            raise TypeError("AgentContext image inputs must be bounded and typed")
        if not isinstance(self.grounding, AgentGroundingIndexView):
            raise TypeError("AgentContext grounding index must be typed")
        from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot

        if not isinstance(self.actor_world, ActorWorldSnapshot):
            raise TypeError("AgentContext actor world must be a typed snapshot")
