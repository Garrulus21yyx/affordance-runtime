"""Secret-free policy view projected from the full runtime observation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class AgentTargetView:
    target_id: str
    role: str
    label: str
    state: dict[str, Any] = field(default_factory=dict)
    supported_actions: tuple[str, ...] = ()
    relations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "supported_actions", tuple(self.supported_actions))
        object.__setattr__(self, "relations", freeze_json(self.relations))


@dataclass(frozen=True)
class AgentWorldView:
    observation_id: str
    targets: tuple[AgentTargetView, ...]
    facts: tuple[dict[str, Any], ...]
    coverage: dict[str, Any]
    conflict_summaries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "facts", tuple(freeze_json(fact) for fact in self.facts))
        object.__setattr__(self, "coverage", freeze_json(self.coverage))
        object.__setattr__(self, "conflict_summaries", tuple(self.conflict_summaries))


def build_agent_world_view(observation: WorldObservation) -> AgentWorldView:
    supported: dict[str, set[str]] = {}
    for binding in observation.bindings:
        supported.setdefault(binding.target_id, set()).update(binding.supported_actions)
    return AgentWorldView(
        observation_id=observation.observation_id,
        targets=tuple(
            AgentTargetView(
                target.target_id,
                target.role,
                target.label,
                target.state,
                tuple(sorted(supported.get(target.target_id, set()))),
                target.relations,
            )
            for target in observation.targets
        ),
        facts=tuple(
            {
                "fact_id": fact.fact_id,
                "subject_id": fact.subject_id,
                "predicate": fact.predicate,
                "value": fact.value,
            }
            for fact in observation.facts
        ),
        coverage={
            item.source_observation_id: item.coverage
            for item in observation.source_manifest
        },
        conflict_summaries=tuple(conflict.summary for conflict in observation.conflicts),
    )
