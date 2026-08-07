"""Semantic planner proposals and deterministic ActionContract binding."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from affordance_runtime.action_semantics import action_compatible
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    Affordance,
    Condition,
    ProgressEvidenceScope,
    RiskLevel,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.grounding import RoutePlan
from affordance_runtime.interaction_grounding import (
    GroundingStatus,
    GroundingTarget,
    InteractionGrounder,
)
from affordance_runtime.perception import derive_perception_requirements, route_perception_requirements
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.scope_authorization import (
    ProposalScopeEvaluator,
    ScopeRejectionKind,
)
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    ElementOperationKind,
    RegionIntent,
    RelationIntent,
    StepActivityStatus,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec, task_semantic_scope_terms
from affordance_runtime.unified_grounding import UnifiedRoutePlanner, source_affordance_for_candidate
from affordance_runtime.unified_observation import CanonicalTarget, UnifiedObservation


class PlannerActionKind(StrEnum):
    ACTIVATE = "activate"
    FOCUS = "focus"
    POINT_ACTIVATE = "point_activate"
    TYPE_TEXT = "type_text"
    SELECT_OPTION = "select_option"
    PRESS_KEY = "press_key"
    DRAG = "drag"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    WAIT = "wait"
    ASK_USER = "ask_user"
    FINISH = "finish"


class PlannerProposalSource(StrEnum):
    """Runtime-declared origin of a semantic proposal, never model-authored."""

    MODEL = "model"
    DETERMINISTIC_RULE = "deterministic_rule"
    PARENT_AGENT = "parent_agent"
    ACCEPTED_SKILL = "accepted_skill"
    RECOVERY = "recovery"
    EXTERNAL_POLICY = "external_policy"


class PlannerProposalProvenance(BaseModel):
    """Immutable audit identity attached outside the semantic proposal schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: PlannerProposalSource
    producer_id: str = Field(min_length=1)
    profile_id: str = ""
    version: str = ""
    evidence_refs: tuple[str, ...] = ()


_TARGET_ACTIONS = {
    PlannerActionKind.ACTIVATE,
    PlannerActionKind.FOCUS,
    PlannerActionKind.POINT_ACTIVATE,
    PlannerActionKind.TYPE_TEXT,
    PlannerActionKind.SELECT_OPTION,
    PlannerActionKind.PRESS_KEY,
    PlannerActionKind.DRAG,
}
_FORBIDDEN_PARAMETER_KEYS = {
    "approval",
    "approval_token",
    "backend",
    "bbox",
    "capability",
    "capabilities",
    "coordinates",
    "css",
    "href",
    "locator",
    "selector",
    "wot_form",
    "x",
    "y",
}
_ACTION_PARAMETERS = {
    PlannerActionKind.ACTIVATE: set(),
    PlannerActionKind.FOCUS: set(),
    PlannerActionKind.POINT_ACTIVATE: set(),
    PlannerActionKind.TYPE_TEXT: {"text"},
    PlannerActionKind.SELECT_OPTION: {"option"},
    PlannerActionKind.PRESS_KEY: {"key"},
    PlannerActionKind.DRAG: set(),
    PlannerActionKind.NAVIGATE: {"destination"},
    PlannerActionKind.SCROLL: {"direction", "amount"},
    PlannerActionKind.WAIT: {"duration_ms"},
    PlannerActionKind.ASK_USER: set(),
    PlannerActionKind.FINISH: set(),
}


class PlannerProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=1)
    based_on_task_revision: int = Field(ge=1)
    based_on_state_version: int = Field(ge=0)
    snapshot_id: str = Field(min_length=1)
    subgoal: str = ""
    action_kind: PlannerActionKind
    target_affordance_id: str = ""
    destination_affordance_id: str = ""
    parameters: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)
    expected_effects: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_clarification: bool = False
    done: bool = False
    result: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    @model_validator(mode="after")
    def validate_semantic_boundary(self) -> "PlannerProposal":
        if self.action_kind in _TARGET_ACTIONS and not self.target_affordance_id:
            raise PydanticCustomError(
                "proposal_target_required",
                "target action requires target_affordance_id",
            )
        if self.action_kind == PlannerActionKind.NAVIGATE and not self.parameters.get("destination"):
            raise PydanticCustomError(
                "proposal_navigation_destination_required",
                "navigate requires a semantic destination",
            )
        if self.action_kind == PlannerActionKind.DRAG and not self.destination_affordance_id:
            raise PydanticCustomError(
                "proposal_drag_destination_required",
                "drag requires destination_affordance_id",
            )
        if self.done and self.action_kind != PlannerActionKind.FINISH:
            raise PydanticCustomError("proposal_done_kind", "done requires action_kind=finish")
        if self.action_kind == PlannerActionKind.FINISH:
            object.__setattr__(self, "done", True)
        if self.requires_clarification and self.action_kind != PlannerActionKind.ASK_USER:
            raise PydanticCustomError(
                "proposal_clarification_kind",
                "requires_clarification requires action_kind=ask_user",
            )
        if self.action_kind == PlannerActionKind.ASK_USER:
            object.__setattr__(self, "requires_clarification", True)
        forbidden = sorted(_FORBIDDEN_PARAMETER_KEYS.intersection(self.parameters))
        if forbidden:
            raise PydanticCustomError(
                "proposal_forbidden_parameters",
                "surface or authority parameters are forbidden",
            )
        unknown = sorted(set(self.parameters) - _ACTION_PARAMETERS[self.action_kind])
        if unknown:
            raise PydanticCustomError(
                "proposal_unsupported_parameters",
                "unsupported semantic parameters",
            )
        required_parameter = {
            PlannerActionKind.TYPE_TEXT: "text",
            PlannerActionKind.SELECT_OPTION: "option",
            PlannerActionKind.PRESS_KEY: "key",
        }.get(self.action_kind)
        if required_parameter and required_parameter not in self.parameters:
            raise PydanticCustomError(
                "proposal_action_parameter_required",
                f"{self.action_kind.value} requires {required_parameter}",
            )
        return self


class ProposalRejectionCode(StrEnum):
    MISSING_PROVENANCE = "missing_provenance"
    STALE_TASK_REVISION = "stale_task_revision"
    STALE_STATE_VERSION = "stale_state_version"
    STALE_SNAPSHOT = "stale_snapshot"
    MISSING_TARGET = "missing_target"
    UNEXPECTED_TARGET = "unexpected_target"
    IDENTICAL_DRAG_TARGETS = "identical_drag_targets"
    UNSUPPORTED_ACTION = "unsupported_action"
    NO_BACKEND = "no_backend"
    TARGET_OUT_OF_SCOPE = "target_out_of_scope"
    UNREQUESTED_EFFECT = "unrequested_effect"


def proposal_error_code(code: ProposalRejectionCode) -> RuntimeErrorCode:
    """Map proposal validation failures to their Runtime protocol code."""

    if code == ProposalRejectionCode.STALE_TASK_REVISION:
        return RuntimeErrorCode.STALE_TASK_REVISION
    if code == ProposalRejectionCode.STALE_STATE_VERSION:
        return RuntimeErrorCode.STALE_STATE_VERSION
    if code == ProposalRejectionCode.STALE_SNAPSHOT:
        return RuntimeErrorCode.SNAPSHOT_MISMATCH
    return RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED


def proposal_record(
    proposal: PlannerProposal,
    provenance: PlannerProposalProvenance,
) -> dict[str, Any]:
    """Serialize a proposal together with its Runtime-attached provenance."""

    return {
        **proposal.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
    }


class ProposalRejected(ValueError):
    def __init__(
        self,
        code: ProposalRejectionCode,
        detail: str = "",
        *,
        reason_code: str = "",
    ) -> None:
        self.code = code
        self.detail = detail
        self.reason_code = reason_code
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


def _active_step_scope(
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> ActiveStepScope | None:
    if state.task_plan is None or state.task_progress is None:
        return None
    active_step_id = state.task_progress.active_step_id
    if not active_step_id:
        return None
    subgoal = next(
        (item for item in state.task_plan.steps if item.step_id == active_step_id),
        None,
    )
    if subgoal is None:
        return None
    grounding = InteractionGrounder().ground(
        subgoal.interaction,
        _snapshot_grounding_targets(snapshot),
    )
    if grounding.status != GroundingStatus.RESOLVED:
        return None
    permitted_targets = grounding.targets
    if isinstance(subgoal.interaction, RelationIntent) and subgoal.interaction.relation == "value_transfer":
        permitted_targets = grounding.destinations
    return ActiveStepScope(
        task_revision=state.task_plan.task_revision,
        evaluated_at_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        activity_status=StepActivityStatus.ACTIVE,
        active_step_id=active_step_id,
        permitted_target_ids=tuple(item.target_id for item in permitted_targets),
        permitted_destination_ids=tuple(item.target_id for item in grounding.destinations),
        permitted_action_kinds=_step_action_kinds(subgoal),
    )


def _snapshot_grounding_targets(
    snapshot: BrowserSnapshot,
) -> tuple[GroundingTarget, ...]:
    source_by_id = {item.id: item for item in snapshot.affordance_model.affordances}
    if snapshot.unified_affordances:
        views: list[GroundingTarget] = []
        for item in snapshot.unified_affordances:
            state: Mapping[str, Any] = {}
            source = next(
                (
                    source_by_id[candidate.source_affordance_id]
                    for candidate in item.grounding_candidates
                    if candidate.source_affordance_id in source_by_id
                ),
                None,
            )
            if source is not None:
                state = source.state
            views.append(
                GroundingTarget(
                    target_id=item.semantic_target_id,
                    role=item.role,
                    label=item.label,
                    supported_actions=tuple(sorted(item.supported_actions)),
                    state=state,
                )
            )
        return tuple(views)
    return tuple(
        GroundingTarget(
            target_id=item.id,
            role=item.role,
            label=item.label,
            supported_actions=(item.action,),
            state=item.state,
        )
        for item in snapshot.affordance_model.affordances
    )


def _canonical_active_step_scope(
    state: StateKernel,
    observation: UnifiedObservation,
) -> ActiveStepScope | None:
    if state.task_plan is None or state.task_progress is None:
        return None
    active_step_id = state.task_progress.active_step_id
    if not active_step_id:
        return None
    subgoal = next(
        (item for item in state.task_plan.steps if item.step_id == active_step_id),
        None,
    )
    if subgoal is None:
        return None
    grounding = InteractionGrounder().ground(
        subgoal.interaction,
        tuple(
            GroundingTarget(
                target_id=item.target_id,
                role=item.role,
                label=item.label,
                supported_actions=item.supported_actions,
                state=item.state,
            )
            for item in observation.targets
        ),
    )
    if grounding.status != GroundingStatus.RESOLVED:
        return None
    permitted_targets = grounding.targets
    if isinstance(subgoal.interaction, RelationIntent) and subgoal.interaction.relation == "value_transfer":
        permitted_targets = grounding.destinations
    return ActiveStepScope(
        task_revision=state.task_plan.task_revision,
        evaluated_at_state_version=state.version,
        snapshot_id=observation.epoch_id,
        activity_status=StepActivityStatus.ACTIVE,
        active_step_id=active_step_id,
        permitted_target_ids=tuple(item.target_id for item in permitted_targets),
        permitted_destination_ids=tuple(item.target_id for item in grounding.destinations),
        permitted_action_kinds=_step_action_kinds(subgoal),
    )


def _step_action_kinds(step: StepSpec) -> tuple[str, ...]:
    interaction = step.interaction
    if isinstance(interaction, RegionIntent):
        return (PlannerActionKind.POINT_ACTIVATE.value,)
    if isinstance(interaction, CollectionIntent):
        return (PlannerActionKind.SELECT_OPTION.value,)
    if isinstance(interaction, RelationIntent):
        return (PlannerActionKind.DRAG.value,)
    if isinstance(interaction, ElementIntent):
        return {
            ElementOperationKind.FOCUS: (PlannerActionKind.FOCUS.value,),
            ElementOperationKind.SCROLL_FORWARD: (PlannerActionKind.SCROLL.value,),
            ElementOperationKind.SCROLL_BACKWARD: (PlannerActionKind.SCROLL.value,),
        }.get(interaction.operation, ())
    return ()


def _canonical_active_value_transfer_source_target(
    state: StateKernel,
    observation: UnifiedObservation,
    destination_target_id: str,
) -> str | None:
    if state.task_plan is None or state.task_progress is None:
        return None
    active = next(
        (item for item in state.task_plan.steps if item.step_id == state.task_progress.active_step_id),
        None,
    )
    if (
        active is None
        or not isinstance(active.interaction, RelationIntent)
        or active.interaction.relation != "value_transfer"
    ):
        return None
    grounding = InteractionGrounder().ground(
        active.interaction,
        tuple(
            GroundingTarget(
                target_id=item.target_id,
                role=item.role,
                label=item.label,
                supported_actions=item.supported_actions,
                state=item.state,
            )
            for item in observation.targets
        ),
    )
    if (
        grounding.status != GroundingStatus.RESOLVED
        or len(grounding.targets) != 1
        or tuple(item.target_id for item in grounding.destinations) != (destination_target_id,)
    ):
        return None
    return grounding.targets[0].target_id


def _active_value_transfer_source_target(
    state: StateKernel,
    snapshot: BrowserSnapshot,
    destination_target_id: str,
) -> str | None:
    if state.task_plan is None or state.task_progress is None:
        return None
    active = next(
        (item for item in state.task_plan.steps if item.step_id == state.task_progress.active_step_id),
        None,
    )
    if (
        active is None
        or not isinstance(active.interaction, RelationIntent)
        or active.interaction.relation != "value_transfer"
    ):
        return None
    grounding = InteractionGrounder().ground(
        active.interaction,
        _snapshot_grounding_targets(snapshot),
    )
    if (
        grounding.status != GroundingStatus.RESOLVED
        or len(grounding.targets) != 1
        or tuple(item.target_id for item in grounding.destinations) != (destination_target_id,)
    ):
        return None
    return grounding.targets[0].target_id


def _exact_transfer_source_value(state: Mapping[str, Any]) -> str | None:
    if str(state.get("input_type") or "").casefold() == "password":
        return None
    if "control_value_prefix" in state or "control_value_suffix" in state:
        return None
    value = state.get("control_value")
    if not isinstance(value, str) or not value or len(value) > 240:
        return None
    return value


@dataclass(frozen=True)
class PlannerProposalValidator:
    """One source-neutral semantic proposal gate before contract binding."""

    def validate(
        self,
        proposal: PlannerProposal,
        provenance: PlannerProposalProvenance | None,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
    ) -> None:
        if provenance is None:
            raise ProposalRejected(ProposalRejectionCode.MISSING_PROVENANCE)
        if proposal.based_on_task_revision != task_spec.revision:
            raise ProposalRejected(ProposalRejectionCode.STALE_TASK_REVISION)
        if proposal.based_on_state_version != state.version:
            raise ProposalRejected(ProposalRejectionCode.STALE_STATE_VERSION)
        if proposal.snapshot_id != snapshot.epoch_id:
            raise ProposalRejected(ProposalRejectionCode.STALE_SNAPSHOT)

        if proposal.action_kind not in _TARGET_ACTIONS:
            if proposal.target_affordance_id or proposal.destination_affordance_id:
                raise ProposalRejected(
                    ProposalRejectionCode.UNEXPECTED_TARGET,
                    proposal.action_kind.value,
                )
            return

        if (
            proposal.action_kind == PlannerActionKind.DRAG
            and proposal.target_affordance_id == proposal.destination_affordance_id
        ):
            raise ProposalRejected(
                ProposalRejectionCode.IDENTICAL_DRAG_TARGETS,
                proposal.target_affordance_id,
            )
        self._validate_target(proposal.target_affordance_id, proposal.action_kind, snapshot)
        if not self._validate_active_step_scope(proposal, state, snapshot):
            self._validate_task_scope(proposal, task_spec, snapshot)
        if proposal.action_kind != PlannerActionKind.DRAG:
            if proposal.destination_affordance_id:
                raise ProposalRejected(
                    ProposalRejectionCode.UNEXPECTED_TARGET,
                    proposal.destination_affordance_id,
                )
            return
        self._validate_target(
            proposal.destination_affordance_id,
            PlannerActionKind.DRAG,
            snapshot,
            destination=True,
        )

    @staticmethod
    def _validate_active_step_scope(
        proposal: PlannerProposal,
        state: StateKernel,
        snapshot: UnifiedObservation,
    ) -> bool:
        scope = _canonical_active_step_scope(state, snapshot)
        if scope is None:
            return False
        decision = scope.evaluate(proposal)
        if decision.allowed:
            return True
        raise ProposalRejected(
            ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
            decision.reason_code,
            reason_code=decision.reason_code,
        )

    @staticmethod
    def _validate_task_scope(
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        snapshot: UnifiedObservation,
    ) -> None:
        """Reject current but unauthorized semantic targets before binding."""

        label, role = _canonical_target_label_role(proposal.target_affordance_id, snapshot)
        scope_terms = task_semantic_scope_terms(task_spec)
        decision = ProposalScopeEvaluator().evaluate(
            action_kind=proposal.action_kind.value,
            target_id=proposal.target_affordance_id,
            target_label=label,
            target_role=role,
            parameters=proposal.parameters,
            objective="",
            targets=scope_terms,
            unified_affordances=tuple(snapshot.targets),
            observation=snapshot,
            bindings=snapshot.bindings,
        )
        if decision.authorized:
            return
        rejection = (
            ProposalRejectionCode.UNREQUESTED_EFFECT
            if decision.rejection == ScopeRejectionKind.UNREQUESTED_EFFECT
            else ProposalRejectionCode.TARGET_OUT_OF_SCOPE
        )
        raise ProposalRejected(
            rejection,
            decision.detail,
            reason_code=decision.reason.value if decision.reason is not None else "",
        )

    @staticmethod
    def _validate_target(
        semantic_target_id: str,
        action: PlannerActionKind,
        snapshot: UnifiedObservation,
        *,
        destination: bool = False,
    ) -> None:
        unified = next(
            (item for item in snapshot.targets if item.target_id == semantic_target_id),
            None,
        )
        if unified is not None:
            if (
                destination
                or action.value in unified.supported_actions
                or any(action_compatible(action, item) for item in unified.supported_actions)
            ):
                return
            raise ProposalRejected(
                ProposalRejectionCode.UNSUPPORTED_ACTION,
                f"{action.value} cannot bind {semantic_target_id}",
            )
        raise ProposalRejected(ProposalRejectionCode.MISSING_TARGET, semantic_target_id)


def _semantic_target_label_role(
    semantic_target_id: str,
    snapshot: BrowserSnapshot,
) -> tuple[str, str]:
    unified = next(
        (item for item in snapshot.unified_affordances if item.semantic_target_id == semantic_target_id),
        None,
    )
    if unified is not None:
        return unified.label, unified.role
    affordance = next(
        (item for item in snapshot.affordance_model.affordances if item.id == semantic_target_id),
        None,
    )
    return (affordance.label, affordance.role) if affordance is not None else ("", "")


def _canonical_target_label_role(
    semantic_target_id: str,
    observation: UnifiedObservation,
) -> tuple[str, str]:
    target = next(
        (item for item in observation.targets if item.target_id == semantic_target_id),
        None,
    )
    return (target.label, target.role) if target is not None else ("", "")


@dataclass(frozen=True)
class ContractRequirements:
    expected_effects: tuple[Condition, ...] = ()
    verifier_plan: tuple[VerifierSpec, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    risk: RiskLevel | None = None
    idempotency_key: str = ""
    compensation: str | None = None
    timeout_ms: int = 5_000


@dataclass(frozen=True)
class TaskPlanProgressTarget:
    """Runtime-owned target for binding verifier evidence to a TaskPlan step."""

    plan_id: str
    plan_version: int
    step_id: str
    based_on_state_version: int


@dataclass(frozen=True)
class StepEvidenceBinder:
    """Validate explicit verifier-to-step links without inferring by timing."""

    def bind(
        self,
        verifier_plan: tuple[VerifierSpec, ...],
        state: StateKernel,
        *,
        progress_target: TaskPlanProgressTarget | None = None,
    ) -> tuple[VerifierSpec, ...]:
        if state.task_plan is None or state.task_progress is None:
            return verifier_plan
        if progress_target is not None and not _progress_target_current(
            progress_target,
            state,
        ):
            return tuple(self._strip_subgoal_links(item) for item in verifier_plan)
        active_id = progress_target.step_id if progress_target is not None else state.task_progress.active_step_id
        step = next(
            (item for item in state.task_plan.steps if item.step_id == active_id),
            None,
        )
        if step is None:
            return verifier_plan
        if progress_target is not None and not set(step.depends_on).issubset(state.task_progress.completed_step_ids):
            return verifier_plan
        from affordance_runtime.criteria import criterion_ids

        allowed_criteria = set(criterion_ids(step.completion_criteria))
        allowed_requirements = {item.source_unit_id for item in step.source_refs}
        return tuple(
            self._validate_spec(
                item,
                allowed_criteria,
                allowed_requirements,
                materialize_as_active=progress_target is not None,
            )
            for item in verifier_plan
        )

    @staticmethod
    def _validate_spec(
        spec: VerifierSpec,
        allowed_criteria: set[str],
        allowed_requirements: set[str],
        *,
        materialize_as_active: bool = False,
    ) -> VerifierSpec:
        subgoal_criteria = {value for value in spec.criterion_ids if value.startswith("subgoal:")}
        subgoal_requirements = {value for value in spec.requirement_ids if value.startswith("subgoal:")}
        if not subgoal_criteria and not subgoal_requirements:
            if spec.progress_scope == ProgressEvidenceScope.NONE:
                return spec
            progress_scope = ProgressEvidenceScope.ACTIVE_SUBGOAL if materialize_as_active else spec.progress_scope
            return replace(
                spec,
                criterion_ids=tuple((*spec.criterion_ids, *sorted(allowed_criteria))),
                requirement_ids=tuple((*spec.requirement_ids, *sorted(allowed_requirements))),
                progress_scope=progress_scope,
            )
        if (
            subgoal_criteria
            and subgoal_requirements
            and subgoal_criteria.issubset(allowed_criteria)
            and subgoal_requirements.issubset(allowed_requirements)
        ):
            return spec
        return replace(
            spec,
            criterion_ids=tuple(value for value in spec.criterion_ids if not value.startswith("subgoal:")),
            requirement_ids=tuple(value for value in spec.requirement_ids if not value.startswith("subgoal:")),
        )

    @staticmethod
    def _strip_subgoal_links(spec: VerifierSpec) -> VerifierSpec:
        return replace(
            spec,
            criterion_ids=tuple(value for value in spec.criterion_ids if not value.startswith("subgoal:")),
            requirement_ids=tuple(value for value in spec.requirement_ids if not value.startswith("subgoal:")),
        )


def _progress_target_current(
    progress_target: TaskPlanProgressTarget | None,
    state: StateKernel,
) -> bool:
    if progress_target is None or state.task_plan is None or state.task_progress is None:
        return False
    return (
        progress_target.plan_id == state.task_plan.plan_id
        and progress_target.plan_version == state.task_plan.plan_version
        and progress_target.based_on_state_version == state.version
        and progress_target.step_id
        not in set(state.task_progress.completed_step_ids) | set(state.task_progress.failed_step_ids)
    )


def bind_active_step_verifiers(
    verifier_plan: tuple[VerifierSpec, ...],
    state: StateKernel,
    *,
    progress_target: TaskPlanProgressTarget | None = None,
) -> tuple[VerifierSpec, ...]:
    """Bind explicit verifier evidence to the current canonical step."""

    return StepEvidenceBinder().bind(
        verifier_plan,
        state,
        progress_target=progress_target,
    )


def resolve_task_plan_progress_target(
    proposal: PlannerProposal,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> TaskPlanProgressTarget | None:
    """Resolve a Runtime-owned verifier progress target for a semantic action."""

    if (
        proposal.action_kind not in _TARGET_ACTIONS
        or state.task_plan is None
        or state.task_progress is None
        or proposal.based_on_state_version != state.version
        or proposal.snapshot_id != snapshot.observation.snapshot_id
    ):
        return None
    scope = _active_step_scope(state, snapshot)
    if scope is None or not scope.evaluate(proposal).allowed:
        return None
    return TaskPlanProgressTarget(
        plan_id=state.task_plan.plan_id,
        plan_version=state.task_plan.plan_version,
        step_id=scope.active_step_id or "",
        based_on_state_version=state.version,
    )


@dataclass(frozen=True)
class UnifiedTargetResolution:
    target: CanonicalTarget
    route: RoutePlan
    source_affordance: Affordance


@dataclass
class UnifiedTargetResolver:
    """Resolve semantic planner targets through deterministic route hard gates."""

    router: UnifiedRoutePlanner = field(default_factory=UnifiedRoutePlanner)

    def resolve(
        self,
        semantic_target_id: str,
        *,
        action: PlannerActionKind,
        task_spec: TaskSpec,
        subgoal: str,
        snapshot: BrowserSnapshot | PerceptionCapture,
        observation: UnifiedObservation,
        available_executors: frozenset[str],
        verifier_kinds: tuple[str, ...],
        excluded_candidate_ids: frozenset[str] = frozenset(),
    ) -> UnifiedTargetResolution:
        target = next(
            (item for item in observation.targets if item.target_id == semantic_target_id),
            None,
        )
        if target is None:
            raise ProposalRejected(ProposalRejectionCode.MISSING_TARGET, semantic_target_id)
        base_requirements = snapshot.perception_requirements or derive_perception_requirements(
            task_spec, active_subgoal=subgoal
        )
        route = self.router.plan(
            target,
            action=action.value,
            requirements=route_perception_requirements(
                base_requirements,
                action=action.value,
                target_role=target.role,
                target_label=target.label,
                target_context=subgoal,
                target_evidence=frozenset(
                    evidence
                    for candidate in observation.bindings
                    if candidate.semantic_target_id == target.target_id
                    for evidence in candidate.evidence_kinds
                ),
            ),
            observation=observation,
            available_executors=available_executors,
            bindings=observation.bindings,
            verifier_kinds=verifier_kinds,
            excluded_candidate_ids=excluded_candidate_ids,
            environment_scope=str(
                snapshot.observation.metadata.get("environment_family")
                or snapshot.observation.metadata.get("environment_profile_id")
                or "generic"
            ),
        )
        source = source_affordance_for_candidate(
            route.selected_candidate,
            snapshot.affordance_model.affordances,
        )
        return UnifiedTargetResolution(target, route, source)


def _contract_parameters(proposal: PlannerProposal) -> dict[str, Any]:
    values = dict(proposal.parameters)
    if proposal.action_kind == PlannerActionKind.TYPE_TEXT:
        if "text" not in values:
            raise ProposalRejected(ProposalRejectionCode.UNSUPPORTED_ACTION, "type_text requires text")
        return {"value": values["text"]}
    if proposal.action_kind == PlannerActionKind.SELECT_OPTION:
        if "option" not in values:
            raise ProposalRejected(ProposalRejectionCode.UNSUPPORTED_ACTION, "select_option requires option")
        return {"value": values["option"]}
    if proposal.action_kind == PlannerActionKind.PRESS_KEY:
        if "key" not in values:
            raise ProposalRejected(ProposalRejectionCode.UNSUPPORTED_ACTION, "press_key requires key")
        return {"key": values["key"]}
    return values


def _operation_risk(operation: OperationClass) -> RiskLevel:
    return {
        OperationClass.READ_ONLY: RiskLevel.LOW,
        OperationClass.NAVIGATION: RiskLevel.LOW,
        OperationClass.REVERSIBLE_WRITE: RiskLevel.MEDIUM,
        OperationClass.EXTERNAL_SIDE_EFFECT: RiskLevel.HIGH,
        OperationClass.IRREVERSIBLE: RiskLevel.IRREVERSIBLE,
    }[operation]


def _max_risk(first: RiskLevel, second: RiskLevel) -> RiskLevel:
    rank = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.IRREVERSIBLE: 3,
    }
    return max((first, second), key=rank.__getitem__)
