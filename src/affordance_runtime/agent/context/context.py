"""Disposable model-facing AgentContext and opaque Runtime identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.agent.context.contracts import (
    AgentActionOptionView,
    AgentActionPageView,
    AgentTaskView,
)
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.goals.plan import AgentGoalPlanView
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

if TYPE_CHECKING:
    from affordance_runtime.agent.context.action_candidate_projection import (
        ActionCandidateProjection,
        ActionDeliveryPlan,
    )
    from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot
    from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
    from affordance_runtime.agent.context.observation_delivery import ObservationDelivery
    from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
    from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
    from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class ContextIdentity:
    task_revision: int
    observation_id: str
    action_space_id: str
    action_page_id: str
    context_generation: int = 0
    goal_plan_disposition: str = "unavailable"
    goal_plan_version: int | None = None
    goal_plan_digest: str = ""
    tool_catalog_digest: str = ""

    def __post_init__(self) -> None:
        if self.task_revision <= 0 or self.context_generation < 0:
            raise ValueError("context revisions are invalid")
        if not all(value.strip() for value in (self.observation_id, self.action_space_id, self.action_page_id)):
            raise ValueError("context identity requires current observation, action space, and page")
        if self.goal_plan_disposition not in {"ready", "not_required", "unavailable"}:
            raise ValueError("context identity goal disposition is invalid")
        if self.goal_plan_disposition == "ready":
            if self.goal_plan_version is None or self.goal_plan_version < 1:
                raise ValueError("ready context identity requires a goal plan version")
            if re.fullmatch(r"[0-9a-f]{64}", self.goal_plan_digest) is None:
                raise ValueError("ready context identity requires a goal plan digest")
        elif self.goal_plan_version is not None or self.goal_plan_digest:
            raise ValueError("empty goal guidance cannot invent plan identity")
        if re.fullmatch(r"[0-9a-f]{64}", self.tool_catalog_digest) is None:
            raise ValueError("context identity requires a current tool catalog digest")

    @property
    def context_id(self) -> str:
        payload = (
            self.task_revision,
            self.observation_id,
            self.action_space_id,
            self.action_page_id,
            self.context_generation,
            self.goal_plan_disposition,
            self.goal_plan_version,
            self.goal_plan_digest,
            self.tool_catalog_digest,
        )
        digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        return f"context:{digest}"


class AgentImageOperandRole(StrEnum):
    SOURCE = "source"
    DESTINATION = "destination"


@dataclass(frozen=True)
class AgentImageActionRoute:
    operation: str
    source_ref: str
    destination_ref: str = ""
    private_action_id: str = field(
        default="", repr=False, compare=False, metadata={"serialize": False}
    )
    private_option: object | None = field(
        default=None, repr=False, compare=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        if (
            not self.operation.strip()
            or not PublicRefCodec.accepts(self.source_ref, expected=PublicRefKind.EXECUTABLE)
            or not self.private_action_id.strip()
            or self.private_option is None
        ):
            raise ValueError("agent image route requires exact public and private lineage")
        if self.destination_ref and not PublicRefCodec.accepts(
            self.destination_ref, expected=PublicRefKind.EXECUTABLE
        ):
            raise ValueError("agent image route destination is invalid")


@dataclass(frozen=True)
class AgentImageMark:
    ref: str
    bbox: tuple[int, int, int, int]
    operand_roles: tuple[AgentImageOperandRole, ...] = ()

    def __post_init__(self) -> None:
        roles = tuple(AgentImageOperandRole(item) for item in self.operand_roles)
        if (
            not PublicRefCodec.accepts(self.ref, expected=PublicRefKind.EXECUTABLE)
            or len(self.bbox) != 4
            or any(type(value) is not int for value in self.bbox)
            or len(roles) != len(set(roles))
        ):
            raise ValueError("agent image mark is invalid")
        object.__setattr__(self, "bbox", tuple(self.bbox))
        object.__setattr__(self, "operand_roles", roles)


@dataclass(frozen=True)
class AgentImageInput:
    evidence_ref: str
    mime_type: str
    data: bytes = field(repr=False)
    sha256: str = ""
    coordinate_space_id: str = ""
    marks: tuple[AgentImageMark, ...] = ()
    route_deltas: tuple[AgentImageActionRoute, ...] = field(
        default=(), repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if (
            not self.evidence_ref.startswith("artifact:")
            or self.mime_type not in {"image/png", "image/jpeg"}
            or not isinstance(self.data, bytes)
            or not self.data
            or len(self.data) > 5 * 1024 * 1024
            or len(self.sha256) != 64
            or hashlib.sha256(self.data).hexdigest() != self.sha256
            or not self.coordinate_space_id.strip()
            or (
                self.mime_type == "image/png"
                and not self.data.startswith(b"\x89PNG\r\n\x1a\n")
            )
            or (
                self.mime_type == "image/jpeg"
                and not self.data.startswith(b"\xff\xd8\xff")
            )
        ):
            raise ValueError("agent image input is invalid")
        marks = tuple(self.marks)
        routes = tuple(self.route_deltas)
        if any(not isinstance(mark, AgentImageMark) for mark in marks) or any(
            not isinstance(route, AgentImageActionRoute) for route in routes
        ):
            raise ValueError("agent image relation must be typed")
        if len({mark.ref for mark in marks}) != len(marks) or len(routes) != len(set(routes)):
            raise ValueError("agent image relation must be unique")
        role_map = {mark.ref: frozenset(mark.operand_roles) for mark in marks}
        for route in routes:
            if not (
                AgentImageOperandRole.SOURCE in role_map.get(route.source_ref, frozenset())
                or (
                    route.destination_ref
                    and AgentImageOperandRole.DESTINATION
                    in role_map.get(route.destination_ref, frozenset())
                )
            ):
                raise ValueError("agent image route lacks an actual typed operand mark")
        for mark in marks:
            expected = {
                role
                for route in routes
                for role, operand in (
                    (AgentImageOperandRole.SOURCE, route.source_ref),
                    (AgentImageOperandRole.DESTINATION, route.destination_ref),
                )
                if operand == mark.ref
            }
            if set(mark.operand_roles) != expected:
                raise ValueError("agent image mark roles differ from exact route deltas")
        object.__setattr__(self, "marks", marks)
        object.__setattr__(self, "route_deltas", routes)


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
        if not PublicRefCodec.accepts(self.ref):
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
    goal_plan: AgentGoalPlanView
    actions: AgentActionPageView
    workspace: AgentWorkspace
    actor_world: ActorWorldSnapshot
    image_inputs: tuple[AgentImageInput, ...] = ()
    grounding: AgentGroundingIndexView = field(default_factory=AgentGroundingIndexView)
    private_fact_bindings: Mapping[str, str] = field(
        default_factory=dict,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    evidence_index: WorldEvidenceIndex | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    current_observation: WorldObservation | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    region_index: WorldDeliveryIndex | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    canonical_world: CanonicalPublicWorldProjection | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    current_step_index: int = field(default=0, repr=False, compare=False)
    runtime_controls: tuple[str, ...] = ()
    control_feedback: Mapping[str, object] = field(default_factory=dict)
    complete_actions: tuple[AgentActionOptionView, ...] = field(
        default_factory=tuple,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    action_space_id: str = field(default="", repr=False, compare=False)
    action_candidates: ActionCandidateProjection | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    observation_delivery: ObservationDelivery | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    action_delivery_plan: ActionDeliveryPlan | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    delivery_store: object | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )

    def __post_init__(self) -> None:
        if not self.context_id.startswith("context:"):
            raise ValueError("AgentContext requires opaque context identity")
        object.__setattr__(self, "image_inputs", tuple(self.image_inputs))
        if len(self.image_inputs) > 2 or any(not isinstance(item, AgentImageInput) for item in self.image_inputs):
            raise TypeError("AgentContext image inputs must be bounded and typed")
        if not isinstance(self.grounding, AgentGroundingIndexView):
            raise TypeError("AgentContext grounding index must be typed")
        if not isinstance(self.workspace, AgentWorkspace):
            raise TypeError("AgentContext workspace must be typed")
        if self.canonical_world is None:
            raise TypeError("AgentContext requires the current canonical public World projection")
        bindings = dict(self.private_fact_bindings)
        if any(
            not PublicRefCodec.accepts(ref, expected=PublicRefKind.FACT)
            or not isinstance(canonical, str)
            or not canonical.startswith("fact:")
            for ref, canonical in bindings.items()
        ):
            raise ValueError("AgentContext fact bindings must be current public fact refs")
        object.__setattr__(self, "private_fact_bindings", freeze_json(bindings))
        if self.current_step_index < 0:
            raise ValueError("AgentContext episode bounds are invalid")
        controls = tuple(self.runtime_controls)
        if len(set(controls)) != len(controls) or any(
            not isinstance(item, str) or not item.strip() or len(item) > 64
            for item in controls
        ):
            raise ValueError("AgentContext runtime controls must be bounded and unique")
        object.__setattr__(self, "runtime_controls", controls)
        object.__setattr__(self, "control_feedback", freeze_json(dict(self.control_feedback)))
        complete_actions = tuple(self.complete_actions) or tuple(self.actions.options)
        if len({item.action_id for item in complete_actions}) != len(complete_actions):
            raise ValueError("AgentContext complete action index must be unique")
        object.__setattr__(self, "complete_actions", complete_actions)
        if not self.action_space_id.strip():
            raise ValueError("AgentContext requires current ActionSpace identity")
        from affordance_runtime.agent.context.action_candidate_projection import (
            ActionCandidateProjection,
            ActionDeliveryPlan,
        )
        from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot
        from affordance_runtime.agent.context.observation_delivery import ObservationDelivery

        if self.observation_delivery is not None:
            if not isinstance(self.observation_delivery, ObservationDelivery):
                raise TypeError("AgentContext observation delivery must be typed")
            if (
                self.current_observation is not None
                and self.observation_delivery.world_observation_id
                != self.current_observation.observation_id
            ):
                raise ValueError("AgentContext observation delivery belongs to another World")
        from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
        from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
        from affordance_runtime.world.contracts import WorldObservation

        if not isinstance(self.actor_world, ActorWorldSnapshot):
            raise TypeError("AgentContext actor world must be a typed snapshot")
        if self.evidence_index is not None and not isinstance(self.evidence_index, WorldEvidenceIndex):
            raise TypeError("AgentContext evidence index must be typed")
        if self.current_observation is not None and not isinstance(self.current_observation, WorldObservation):
            raise TypeError("AgentContext current observation must be typed")
        if self.action_candidates is not None:
            if not isinstance(self.action_candidates, ActionCandidateProjection):
                raise TypeError("AgentContext action candidates must be a typed projection")
            if self.action_candidates.action_space_id != self.action_space_id:
                raise ValueError("AgentContext candidates belong to another ActionSpace")
            if (
                self.current_observation is not None
                and self.action_candidates.world_observation_id
                != self.current_observation.observation_id
            ):
                raise ValueError("AgentContext candidates belong to another World")
            current_candidates = {
                (item.action_id, item.target_ref, item.operation)
                for item in complete_actions
            }
            if any(
                (item.action_id, item.target_ref, item.operation) not in current_candidates
                for item in self.action_candidates.candidates
            ):
                raise ValueError("AgentContext candidates are outside the complete current actions")
            current_by_action = {item.action_id: item for item in complete_actions}
            if any(
                not set(destination.target_ref for destination in item.destinations).issubset(
                    {
                        destination.grounding_ref
                        for destination in current_by_action[item.action_id].destinations.items
                    }
                )
                or (item.destination_required and not item.destinations)
                or item.destination_required
                != current_by_action[item.action_id].destination_required
                for item in self.action_candidates.candidates
            ):
                raise ValueError("AgentContext candidate destinations are outside current actions")
        if self.action_delivery_plan is not None:
            if not isinstance(self.action_delivery_plan, ActionDeliveryPlan):
                raise TypeError("AgentContext action delivery plan must be typed")
            if self.action_delivery_plan.action_space_id != self.action_space_id:
                raise ValueError("AgentContext action delivery plan belongs to another ActionSpace")
            if (
                self.current_observation is not None
                and self.action_delivery_plan.world_observation_id
                != self.current_observation.observation_id
            ):
                raise ValueError("AgentContext action delivery plan belongs to another World")
        if self.region_index is not None:
            if not isinstance(self.region_index, WorldDeliveryIndex):
                raise TypeError("AgentContext region index must be typed")
            if (
                self.current_observation is not None
                and self.region_index.world_observation_id != self.current_observation.observation_id
            ):
                raise ValueError("AgentContext region index must belong to current observation")
        if self.evidence_index is not None and any(
            self.evidence_index.resolve(canonical) is False for canonical in bindings.values()
        ):
            raise ValueError("AgentContext fact bindings must resolve in the current evidence index")
