"""Disposable model-facing AgentContext and opaque Runtime identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.context.contracts import (
    AgentActionOptionView,
    AgentActionPageView,
    AgentTaskView,
)
from affordance_runtime.agent.workspace import AgentWorkspace
from affordance_runtime.goals.plan import AgentGoalPlanView
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.finalization import FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

if TYPE_CHECKING:
    from affordance_runtime.agent.context.action_candidate_projection import (
        ActionCandidateProjection,
        ActionDeliveryPlan,
    )
    from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot
    from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
    from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
    from affordance_runtime.agent.run_state import StepResult
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


@dataclass(frozen=True)
class AgentImageMark:
    ref: str
    bbox: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        if (
            not PublicRefCodec.accepts(self.ref)
            or self.ref[:1] not in {PublicRefKind.EXECUTABLE.value, PublicRefKind.NODE.value}
            or len(self.bbox) != 4
            or any(type(value) is not int for value in self.bbox)
        ):
            raise ValueError("agent image mark is invalid")
        object.__setattr__(self, "bbox", tuple(self.bbox))


@dataclass(frozen=True)
class VisualEvidenceFragment:
    """Exact model-visible image evidence with actual marks and no action authority."""

    evidence_ref: str
    mime_type: str
    data: bytes = field(repr=False)
    sha256: str = ""
    coordinate_space_id: str = ""
    marks: tuple[AgentImageMark, ...] = ()

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
            or (self.mime_type == "image/png" and not self.data.startswith(b"\x89PNG\r\n\x1a\n"))
            or (self.mime_type == "image/jpeg" and not self.data.startswith(b"\xff\xd8\xff"))
        ):
            raise ValueError("visual evidence fragment is invalid")
        marks = tuple(self.marks)
        if any(not isinstance(mark, AgentImageMark) for mark in marks):
            raise ValueError("agent image marks must be typed")
        if len({mark.ref for mark in marks}) != len(marks):
            raise ValueError("agent image marks must be unique")
        object.__setattr__(self, "marks", marks)


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
    image_inputs: tuple[VisualEvidenceFragment, ...] = ()
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
    action_delivery_plan: ActionDeliveryPlan | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    last_step: StepResult | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    final_response_guidance: str = field(
        default="",
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )

    def __post_init__(self) -> None:
        if not self.context_id.startswith("context:"):
            raise ValueError("AgentContext requires opaque context identity")
        if self.last_step is not None and type(self.last_step).__name__ != "StepResult":
            raise TypeError("AgentContext last step must be committed Runtime truth")
        guidance = " ".join(self.final_response_guidance.split())
        if len(guidance) > FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS:
            raise ValueError("AgentContext final response guidance exceeds its bound")
        object.__setattr__(self, "final_response_guidance", guidance)
        object.__setattr__(self, "image_inputs", tuple(self.image_inputs))
        if len(self.image_inputs) > 2 or any(
            not isinstance(item, VisualEvidenceFragment) for item in self.image_inputs
        ):
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
            not isinstance(item, str) or not item.strip() or len(item) > 64 for item in controls
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
            ActionRouteFragment,
        )
        from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot
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
                and self.action_candidates.world_observation_id != self.current_observation.observation_id
            ):
                raise ValueError("AgentContext candidates belong to another World")
            current_candidates = {(item.action_id, item.target_ref, item.operation) for item in complete_actions}
            if any(
                (item.action_id, item.target_ref, item.operation) not in current_candidates
                for item in self.action_candidates.candidates
            ):
                raise ValueError("AgentContext candidates are outside the complete current actions")
            current_by_target: dict[str, list[AgentActionOptionView]] = {}
            current_by_action = {item.action_id: item for item in complete_actions}
            for current in complete_actions:
                current_by_target.setdefault(current.target_ref, []).append(current)
            if any(
                not set(destination.target_ref for destination in item.destinations).issubset(
                    {
                        destination.grounding_ref
                        for current in current_by_target[item.target_ref]
                        for destination in current.destinations.items
                    }
                )
                or (item.destination_required and not item.destinations)
                or item.destination_required
                != any(current.destination_required for current in current_by_target[item.target_ref])
                for item in self.action_candidates.candidates
            ):
                raise ValueError("AgentContext candidate destinations are outside current actions")
            if any(
                not isinstance(fragment, ActionRouteFragment)
                or (
                    fragment.candidate.action_id,
                    fragment.candidate.target_ref,
                    fragment.candidate.operation,
                )
                not in current_candidates
                or not {destination.target_ref for destination in fragment.candidate.destinations}.issubset(
                    {
                        destination.grounding_ref
                        for destination in current_by_action[fragment.candidate.action_id].destinations.items
                    }
                )
                for fragment in self.action_candidates.route_fragments
            ):
                raise ValueError("AgentContext candidate routes are outside complete current actions")
        if self.action_delivery_plan is not None:
            if not isinstance(self.action_delivery_plan, ActionDeliveryPlan):
                raise TypeError("AgentContext action delivery plan must be typed")
            if self.action_delivery_plan.action_space_id != self.action_space_id:
                raise ValueError("AgentContext action delivery plan belongs to another ActionSpace")
            if (
                self.current_observation is not None
                and self.action_delivery_plan.world_observation_id != self.current_observation.observation_id
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
