"""Frozen model-workspace contracts; production migration is a later stage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.context.world_transition import PublicWorldDelta
from affordance_runtime.agent.working_facts import WorkingFact, validate_working_fact_collection
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import CoverageState


@dataclass(frozen=True)
class CurrentFinding:
    evidence_ref: str
    predicate: str
    exact_value: object
    source_context: str
    coverage: CoverageState

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.evidence_ref, self.predicate, self.source_context)):
            raise ValueError("current finding requires public evidence identity and context")
        if not isinstance(self.coverage, CoverageState):
            raise TypeError("current finding coverage must be typed")
        object.__setattr__(self, "exact_value", freeze_json(self.exact_value))


class SemanticEventKind(StrEnum):
    GUI_EFFECT = "gui_effect"
    PUBLIC_RESULT = "public_result"
    WORKING_FACT = "working_fact"
    TYPED_FAILURE = "typed_failure"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class SemanticEvent:
    step_index: int
    kind: SemanticEventKind
    summary: str
    exact_public_values: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("semantic event step index must be non-negative")
        if not isinstance(self.kind, SemanticEventKind) or not self.summary.strip():
            raise TypeError("semantic event requires typed kind and summary")
        values = tuple(freeze_json(dict(item)) for item in self.exact_public_values)
        object.__setattr__(self, "exact_public_values", values)


class ActivityFamily(StrEnum):
    READ_REGION = "read_region"
    SEARCH_PAGE_CONTENT = "search_page_content"
    FIND_CONTROLS = "find_controls"
    WAIT = "wait"
    NO_EFFECT = "no_effect"


@dataclass(frozen=True)
class ActivitySummary:
    family: ActivityFamily
    world_digest: str
    attempt_count: int
    new_finding_count: int
    last_outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.family, ActivityFamily):
            raise TypeError("activity family must be typed")
        if not self.world_digest.strip() or not self.last_outcome.strip():
            raise ValueError("activity summary requires digest and outcome")
        if (
            type(self.attempt_count) is not int
            or self.attempt_count < 1
            or type(self.new_finding_count) is not int
            or self.new_finding_count < 0
        ):
            raise ValueError("activity counts are invalid")


@dataclass(frozen=True)
class AgentWorkspace:
    recent_steps: tuple[AgentTurnView, ...] = ()
    semantic_events: tuple[SemanticEvent, ...] = ()
    activities: tuple[ActivitySummary, ...] = ()
    working_facts: tuple[WorkingFact, ...] = ()

    def __post_init__(self) -> None:
        recent = tuple(self.recent_steps)
        events = tuple(self.semantic_events)
        activities = tuple(self.activities)
        if len(recent) > 4 or any(not isinstance(item, AgentTurnView) for item in recent):
            raise ValueError("workspace retains at most four typed detailed steps")
        if any(not isinstance(item, SemanticEvent) for item in events):
            raise TypeError("workspace semantic events must be typed")
        if any(not isinstance(item, ActivitySummary) for item in activities):
            raise TypeError("workspace activities must be typed")
        object.__setattr__(self, "recent_steps", recent)
        object.__setattr__(self, "semantic_events", events)
        object.__setattr__(self, "activities", activities)
        object.__setattr__(self, "working_facts", validate_working_fact_collection(self.working_facts))


class WorkspaceReducer(Protocol):
    """Stage-4 implementation port; its transition input is already frozen."""

    def reduce(
        self,
        previous: AgentWorkspace,
        step: object,
        current_findings: tuple[CurrentFinding, ...],
        public_world_delta: PublicWorldDelta,
        allocation_bytes: int,
    ) -> AgentWorkspace: ...
