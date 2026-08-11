"""Disposable model-facing AgentContext and opaque Runtime identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.contracts import AgentActionPageView, AgentPlanView, AgentTaskView, AgentTurnView
from affordance_runtime.model_boundary.control_feedback_projection import AgentControlFeedbackView
from affordance_runtime.model_boundary.world_projection import ModelWorldView, PublicFactView


class DecisionMode(StrEnum):
    ACT = "act"
    RECOVER = "recover"


@dataclass(frozen=True)
class ContextIdentity:
    task_revision: int
    observation_id: str
    action_space_id: str
    action_page_id: str
    progress_revision: int
    pending_revision: int
    context_generation: int = 0

    def __post_init__(self) -> None:
        if (
            self.task_revision <= 0
            or self.progress_revision < 0
            or self.pending_revision < 0
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
            self.progress_revision,
            self.pending_revision,
            self.context_generation,
        )
        digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        return f"context:{digest}"


@dataclass(frozen=True)
class IntentExcerptView:
    text: str
    source_kind: str
    source_ref: str
    digest: str


@dataclass(frozen=True)
class IntentContextView:
    excerpts: BoundedSection[IntentExcerptView]
    authority: str = "context_only"


@dataclass(frozen=True)
class AgentProgressEventView:
    event_type: str
    semantic_action: str
    target_id: str
    attempt_key_digest: str
    effect_status: str
    task_status: str
    strategy_transition_required: bool


@dataclass(frozen=True)
class AgentProgressView:
    plan_summary: AgentPlanView | None
    active_objective: str
    validated_task_status: str
    verified_public_facts: tuple[PublicFactView, ...]
    unresolved_criteria: BoundedSection[str]
    unresolved_outputs: BoundedSection[str]
    events: BoundedSection[AgentProgressEventView]
    truncated: bool = False


@dataclass(frozen=True)
class AgentPendingView:
    waiting_user_summary: str = ""
    waiting_confirmation_summary: str = ""
    uncertain_effect_summary: str = ""


@dataclass(frozen=True)
class AgentBudgetView:
    remaining_turns: int
    remaining_observations: int
    remaining_wait_ms: int
    section_truncation: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_truncation", freeze_json(self.section_truncation))


@dataclass(frozen=True)
class AgentContext:
    context_id: str
    task: AgentTaskView
    intent: IntentContextView
    progress: AgentProgressView
    world: ModelWorldView
    actions: AgentActionPageView
    history: BoundedSection[AgentTurnView]
    pending: AgentPendingView
    budgets: AgentBudgetView
    decision_mode: DecisionMode
    control_feedback: AgentControlFeedbackView | None = None

    def __post_init__(self) -> None:
        if not self.context_id.startswith("context:"):
            raise ValueError("AgentContext requires opaque context identity")
