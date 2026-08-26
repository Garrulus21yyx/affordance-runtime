"""Immutable expensive context derivations owned by one fresh observation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.acquisition_projection import ObservationCapabilityView
from affordance_runtime.agent.context.actor_world_snapshot import ActorWorldSnapshot
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.contracts import AgentActionSpaceView
from affordance_runtime.agent.context.grounding_projection import GroundingProjectionResult
from affordance_runtime.agent.context.world_projection import ModelWorldView
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class ObservationContextProjection:
    """One disposable, non-authoritative projection reused within one World generation.

    A policy turn may change history, progress, candidate ranking, and Context identity
    without changing these observation-owned values.  A fresh observation or a changed
    ActionSpace must produce a new instance.
    """

    observation_id: str
    action_space_id: str
    canonical_projection_lineage: str
    observation_capabilities: tuple[ObservationCapabilityView, ...]
    runtime_controls: tuple[str, ...]
    model_world: ModelWorldView
    grounding: GroundingProjectionResult
    actor_world: ActorWorldSnapshot
    evidence_index: WorldEvidenceIndex
    complete_actions: AgentActionSpaceView
    target_labels: Mapping[str, str] = field(repr=False, compare=False)
    tool_catalog_digest: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not self.observation_id.strip()
            or not self.action_space_id.strip()
            or not self.canonical_projection_lineage.startswith("projection:")
            or re.fullmatch(r"[0-9a-f]{64}", self.tool_catalog_digest) is None
        ):
            raise ValueError("observation context projection identity is invalid")
        object.__setattr__(self, "observation_capabilities", tuple(self.observation_capabilities))
        object.__setattr__(self, "runtime_controls", tuple(self.runtime_controls))
        object.__setattr__(self, "target_labels", freeze_json(dict(self.target_labels)))
        if self.evidence_index.observation_id != self.observation_id:
            raise ValueError("observation context evidence belongs to another World")

    def assert_current(
        self,
        observation: WorldObservation,
        action_space: ActionSpace,
        canonical_world: CanonicalPublicWorldProjection,
        observation_capabilities: tuple[ObservationCapabilityView, ...],
        runtime_controls: tuple[str, ...],
    ) -> None:
        if (
            self.observation_id != observation.observation_id
            or self.action_space_id != action_space.action_space_id
            or self.canonical_projection_lineage != canonical_world.projection_lineage
            or self.observation_capabilities != tuple(observation_capabilities)
            or self.runtime_controls != tuple(runtime_controls)
        ):
            raise ValueError("observation context projection inputs are not current")
        if set(self.target_labels) != {item.target_id for item in observation.targets}:
            raise ValueError("observation context projection target inventory is incomplete")
        if set(self.grounding.index.target_refs) != set(self.target_labels):
            raise ValueError("observation context grounding inventory is incomplete")
        if set(self.grounding.index.target_refs.items()) != set(canonical_world.target_refs.items()):
            raise ValueError("observation context grounding disagrees with canonical public refs")
        if {item.action_id for item in self.complete_actions.options} != {
            item.action_id for item in action_space.options
        }:
            raise ValueError("observation context ActionSpace inventory is incomplete")
