"""Semantic planner proposals and deterministic ActionContract binding."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.collection_window import (
    resolve_global_ordinal_constraint,
    snapshot_collection_affordances,
)
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    Condition,
    GestureBindingError,
    GestureContractBinder,
    ProgressEvidenceScope,
    RiskLevel,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.grounding import GroundingCandidate, RoutePlan, UnifiedAffordance
from affordance_runtime.interaction_grounding import (
    GroundingStatus,
    GroundingTarget,
    InteractionGrounder,
)
from affordance_runtime.perception import derive_perception_requirements, route_perception_requirements
from affordance_runtime.routing import CostAwareRouter
from affordance_runtime.scope_authorization import (
    ProposalScopeDecision,
    ProposalScopeEvaluator,
    ScopeRejectionKind,
    ScopeRejectionReason,
    authorize_observed_value_transfer,
)
from affordance_runtime.simplified_runtime_contracts import RelationIntent, StepActivityStatus
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.unified_grounding import UnifiedRoutePlanner, source_affordance_for_candidate
from affordance_runtime.visual_contracts import VisualContractBinder


class PlannerActionKind(StrEnum):
    ACTIVATE = "activate"
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
    RUNTIME_TERMINAL = "runtime_terminal"


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
    active_step_id = state.task_progress.active_subgoal_id
    if not active_step_id:
        return None
    subgoal = next(
        (item for item in state.task_plan.subgoals if item.subgoal_id == active_step_id),
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
    if (
        isinstance(subgoal.interaction, RelationIntent)
        and subgoal.interaction.relation == "value_transfer"
    ):
        permitted_targets = grounding.destinations
    return ActiveStepScope(
        task_revision=state.task_plan.task_revision,
        evaluated_at_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        activity_status=StepActivityStatus.ACTIVE,
        active_step_id=active_step_id,
        permitted_target_ids=tuple(item.target_id for item in permitted_targets),
        permitted_destination_ids=tuple(
            item.target_id for item in grounding.destinations
        ),
        permitted_action_kinds=((subgoal.action_family.value,) if subgoal.action_family is not None else ()),
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


def _active_value_transfer_source_target(
    state: StateKernel,
    snapshot: BrowserSnapshot,
    destination_target_id: str,
) -> str | None:
    if state.task_plan is None or state.task_progress is None:
        return None
    active = next(
        (
            item
            for item in state.task_plan.subgoals
            if item.subgoal_id == state.task_progress.active_subgoal_id
        ),
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
        or tuple(item.target_id for item in grounding.destinations)
        != (destination_target_id,)
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
        snapshot: BrowserSnapshot,
    ) -> None:
        if provenance is None:
            raise ProposalRejected(ProposalRejectionCode.MISSING_PROVENANCE)
        if proposal.based_on_task_revision != task_spec.revision:
            raise ProposalRejected(ProposalRejectionCode.STALE_TASK_REVISION)
        if proposal.based_on_state_version != state.version:
            raise ProposalRejected(ProposalRejectionCode.STALE_STATE_VERSION)
        if proposal.snapshot_id != snapshot.observation.snapshot_id:
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
        snapshot: BrowserSnapshot,
    ) -> bool:
        scope = _active_step_scope(state, snapshot)
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
        snapshot: BrowserSnapshot,
    ) -> None:
        """Reject current but unauthorized semantic targets before binding."""

        label, role = _semantic_target_label_role(proposal.target_affordance_id, snapshot)
        ordinal_constraint = resolve_global_ordinal_constraint(
            objective=task_spec.objective,
            targets=task_spec.targets,
            affordances=snapshot_collection_affordances(snapshot),
        )
        decision = ProposalScopeEvaluator().evaluate(
            action_kind=proposal.action_kind.value,
            target_id=proposal.target_affordance_id,
            target_label=label,
            target_role=role,
            parameters=proposal.parameters,
            objective=task_spec.objective,
            targets=task_spec.targets,
            unified_affordances=snapshot.unified_affordances,
            observation=snapshot.observation,
            ordinal_constraint=ordinal_constraint,
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
        snapshot: BrowserSnapshot,
        *,
        destination: bool = False,
    ) -> None:
        unified = next(
            (item for item in snapshot.unified_affordances if item.semantic_target_id == semantic_target_id),
            None,
        )
        if unified is not None:
            if (
                destination
                or action.value in unified.supported_actions
                or any(_action_compatible(action, item) for item in unified.supported_actions)
            ):
                return
            raise ProposalRejected(
                ProposalRejectionCode.UNSUPPORTED_ACTION,
                f"{action.value} cannot bind {semantic_target_id}",
            )
        affordance = next(
            (item for item in snapshot.affordance_model.affordances if item.id == semantic_target_id),
            None,
        )
        if affordance is None:
            raise ProposalRejected(ProposalRejectionCode.MISSING_TARGET, semantic_target_id)
        if not destination and not _action_compatible(action, affordance.action):
            raise ProposalRejected(
                ProposalRejectionCode.UNSUPPORTED_ACTION,
                f"{action.value} cannot bind {affordance.action}",
            )


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
    """Runtime-owned target for binding verifier evidence to a TaskPlan subgoal."""

    plan_id: str
    plan_version: int
    subgoal_id: str
    based_on_state_version: int


@dataclass(frozen=True)
class SubgoalEvidenceBinder:
    """Validate explicit verifier-to-subgoal links without inferring by timing."""

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
        active_id = (
            progress_target.subgoal_id
            if progress_target is not None
            else state.task_progress.active_subgoal_id
        )
        subgoal = next(
            (item for item in state.task_plan.subgoals if item.subgoal_id == active_id),
            None,
        )
        if subgoal is None:
            return verifier_plan
        if progress_target is not None and not set(subgoal.depends_on).issubset(
            state.task_progress.completed_subgoal_ids
        ):
            return verifier_plan
        criterion_prefix = f"subgoal:{subgoal.subgoal_id}:criterion:"
        requirement_prefix = f"subgoal:{subgoal.subgoal_id}:evidence-requirement:"
        allowed_criteria = {
            f"{criterion_prefix}{index}"
            for index, _description in enumerate(subgoal.success_criteria)
        }
        allowed_requirements = {
            f"{requirement_prefix}{index}"
            for index, _description in enumerate(subgoal.evidence_requirements)
        }
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
        subgoal_criteria = {
            value for value in spec.criterion_ids if value.startswith("subgoal:")
        }
        subgoal_requirements = {
            value for value in spec.requirement_ids if value.startswith("subgoal:")
        }
        if not subgoal_criteria and not subgoal_requirements:
            if spec.progress_scope == ProgressEvidenceScope.NONE:
                return spec
            progress_scope = (
                ProgressEvidenceScope.ACTIVE_SUBGOAL
                if materialize_as_active
                else spec.progress_scope
            )
            return replace(
                spec,
                criterion_ids=tuple((*spec.criterion_ids, *sorted(allowed_criteria))),
                requirement_ids=tuple(
                    (*spec.requirement_ids, *sorted(allowed_requirements))
                ),
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
            criterion_ids=tuple(
                value for value in spec.criterion_ids if not value.startswith("subgoal:")
            ),
            requirement_ids=tuple(
                value for value in spec.requirement_ids if not value.startswith("subgoal:")
            ),
        )

    @staticmethod
    def _strip_subgoal_links(spec: VerifierSpec) -> VerifierSpec:
        return replace(
            spec,
            criterion_ids=tuple(
                value for value in spec.criterion_ids if not value.startswith("subgoal:")
            ),
            requirement_ids=tuple(
                value for value in spec.requirement_ids if not value.startswith("subgoal:")
            ),
        )


def _progress_target_current(
    progress_target: TaskPlanProgressTarget | None,
    state: StateKernel,
) -> bool:
    if (
        progress_target is None
        or state.task_plan is None
        or state.task_progress is None
    ):
        return False
    return (
        progress_target.plan_id == state.task_plan.plan_id
        and progress_target.plan_version == state.task_plan.plan_version
        and progress_target.based_on_state_version == state.version
        and progress_target.subgoal_id
        not in set(state.task_progress.completed_subgoal_ids)
        | set(state.task_progress.failed_subgoal_ids)
    )


def bind_active_subgoal_verifiers(
    verifier_plan: tuple[VerifierSpec, ...],
    state: StateKernel,
    *,
    progress_target: TaskPlanProgressTarget | None = None,
) -> tuple[VerifierSpec, ...]:
    """Compatibility entrypoint for explicit subgoal evidence validation."""

    return SubgoalEvidenceBinder().bind(
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
        subgoal_id=scope.active_step_id or "",
        based_on_state_version=state.version,
    )


@dataclass(frozen=True)
class UnifiedTargetResolution:
    target: UnifiedAffordance
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
        snapshot: BrowserSnapshot,
        available_executors: frozenset[str],
        verifier_kinds: tuple[str, ...],
        excluded_candidate_ids: frozenset[str] = frozenset(),
    ) -> UnifiedTargetResolution:
        target = next(
            (item for item in snapshot.unified_affordances if item.semantic_target_id == semantic_target_id),
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
                    evidence for candidate in target.grounding_candidates for evidence in candidate.evidence_kinds
                ),
            ),
            observation=snapshot.observation,
            available_executors=available_executors,
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


@dataclass
class ContractBuilder:
    router: CostAwareRouter = field(default_factory=CostAwareRouter)
    gesture_binder: GestureContractBinder = field(default_factory=GestureContractBinder)
    visual_binder: VisualContractBinder = field(default_factory=VisualContractBinder)
    unified_resolver: UnifiedTargetResolver = field(default_factory=UnifiedTargetResolver)
    requirements: Mapping[str, ContractRequirements] = field(default_factory=dict)

    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        if proposal.based_on_task_revision != task_spec.revision:
            raise ProposalRejected(ProposalRejectionCode.STALE_TASK_REVISION)
        if proposal.based_on_state_version != state.version:
            raise ProposalRejected(ProposalRejectionCode.STALE_STATE_VERSION)
        if proposal.snapshot_id != snapshot.observation.snapshot_id:
            raise ProposalRejected(ProposalRejectionCode.STALE_SNAPSHOT)
        source_resolution = self._resolve_unified_target(
            proposal.target_affordance_id,
            action=proposal.action_kind,
            proposal=proposal,
            task_spec=task_spec,
            snapshot=snapshot,
            excluded_candidate_ids=state.excluded_candidates_for(proposal.target_affordance_id),
        )
        affordance = (
            source_resolution.source_affordance
            if source_resolution is not None
            else self._legacy_affordance(proposal.target_affordance_id, snapshot)
        )
        if affordance is None:
            raise ProposalRejected(
                ProposalRejectionCode.MISSING_TARGET,
                proposal.target_affordance_id,
            )
        if not _action_compatible(proposal.action_kind, affordance.action):
            raise ProposalRejected(
                ProposalRejectionCode.UNSUPPORTED_ACTION,
                f"{proposal.action_kind.value} cannot bind {affordance.action}",
            )
        destination: Affordance | None = None
        destination_resolution: UnifiedTargetResolution | None = None
        gesture_binding = None
        if proposal.action_kind == PlannerActionKind.DRAG:
            selected_executor = (
                source_resolution.route.selected_candidate.compatible_executor if source_resolution is not None else ""
            )
            destination_resolution = self._resolve_unified_target(
                proposal.destination_affordance_id,
                action=proposal.action_kind,
                proposal=proposal,
                task_spec=task_spec,
                snapshot=snapshot,
                available_executors=(frozenset({selected_executor}) if selected_executor else None),
                excluded_candidate_ids=state.excluded_candidates_for(proposal.destination_affordance_id),
                verifier_kinds=self._route_verifier_kinds(
                    proposal.target_affordance_id,
                    snapshot,
                ),
            )
            destination = (
                destination_resolution.source_affordance
                if destination_resolution is not None
                else self._legacy_affordance(proposal.destination_affordance_id, snapshot)
            )
            if destination is None:
                raise ProposalRejected(ProposalRejectionCode.MISSING_TARGET, proposal.destination_affordance_id)
        if source_resolution is not None:
            selected_backend = source_resolution.route.selected_candidate.compatible_executor
        else:
            backend_names = set(affordance.backend_candidates)
            if destination is not None:
                backend_names.intersection_update(destination.backend_candidates)
            candidates = {name: affordance for name in affordance.backend_candidates if name in backend_names}
            route = self.router.route(candidates)
            if route.selected_backend is None:
                raise ProposalRejected(ProposalRejectionCode.NO_BACKEND, affordance.id)
            selected_backend = route.selected_backend

        contract_requirements = self.requirements.get(
            proposal.target_affordance_id,
            self.requirements.get(affordance.id, ContractRequirements()),
        )
        required_capabilities = tuple(
            dict.fromkeys(
                [
                    *contract_requirements.required_capabilities,
                    *(
                        task_spec.requested_capabilities
                        if task_spec.operation_class
                        in {
                            OperationClass.REVERSIBLE_WRITE,
                            OperationClass.EXTERNAL_SIDE_EFFECT,
                            OperationClass.IRREVERSIBLE,
                        }
                        else ()
                    ),
                ]
            )
        )
        parameters = _contract_parameters(proposal)
        if source_resolution is not None and proposal.action_kind == PlannerActionKind.POINT_ACTIVATE:
            candidate = source_resolution.route.selected_candidate
            lineage = state.fallback_lineage_for(source_resolution.target.semantic_target_id)
            try:
                contract = self.visual_binder.bind_point_activate(
                    source_resolution.route,
                    snapshot.observation,
                    intent=proposal.subgoal or task_spec.objective,
                    verifier_plan=contract_requirements.verifier_plan,
                    required_capabilities=required_capabilities,
                    supersedes_contract_id=lineage.get("supersedes_contract_id", ""),
                    source_contract_id=lineage.get("source_contract_id", ""),
                    fallback_reason=lineage.get("fallback_reason", ""),
                )
            except ValueError as exc:
                raise ProposalRejected(
                    ProposalRejectionCode.STALE_SNAPSHOT,
                    str(exc),
                ) from exc
            contract = replace(
                contract,
                expected_effects=list(contract_requirements.expected_effects),
                contract_hash="",
            )
        else:
            contract = ActionContract.from_affordance(
                affordance,
                intent=proposal.subgoal or task_spec.objective,
                backend=selected_backend,
                expected_effects=list(contract_requirements.expected_effects),
                verifier_plan=list(contract_requirements.verifier_plan),
                required_capabilities=list(required_capabilities),
                parameters=parameters,
            )
            if source_resolution is not None:
                candidate = source_resolution.route.selected_candidate
                lineage = state.fallback_lineage_for(source_resolution.target.semantic_target_id)
                contract = replace(
                    contract,
                    id=(f"contract_{candidate.candidate_id.replace(':', '_')}_{candidate.observation_epoch_id}"),
                    affordance_id=source_resolution.target.semantic_target_id,
                    backend=candidate.compatible_executor,
                    grounding_candidate=candidate,
                    route_plan=source_resolution.route,
                    snapshot_id=candidate.observation_epoch_id,
                    page_revision=candidate.page_revision,
                    target_fingerprint=candidate.target_fingerprint,
                    target_fingerprint_key=candidate.fingerprint_key or candidate.candidate_id,
                    expires_at_s=candidate.expires_at_s,
                    supersedes_contract_id=lineage.get("supersedes_contract_id", ""),
                    source_contract_id=lineage.get("source_contract_id", ""),
                    fallback_reason=lineage.get("fallback_reason", ""),
                    contract_hash="",
                )
        if destination is not None:
            try:
                source_candidate = source_resolution.route.selected_candidate if source_resolution is not None else None
                destination_candidate = (
                    destination_resolution.route.selected_candidate if destination_resolution is not None else None
                )
                gesture_binding = self.gesture_binder.bind(
                    replace(affordance, backend_candidates=[selected_backend]),
                    replace(destination, backend_candidates=[selected_backend]),
                    selected_route=selected_backend,
                    observation=snapshot.observation,
                    source_semantic_target_id=(
                        source_resolution.target.semantic_target_id if source_resolution is not None else affordance.id
                    ),
                    source_candidate_id=(
                        source_candidate.candidate_id if source_candidate is not None else affordance.id
                    ),
                    source_fingerprint_key=(
                        source_candidate.fingerprint_key or source_candidate.candidate_id
                        if source_candidate is not None
                        else affordance.id
                    ),
                    destination_semantic_target_id=(
                        destination_resolution.target.semantic_target_id
                        if destination_resolution is not None
                        else destination.id
                    ),
                    destination_candidate_id=(
                        destination_candidate.candidate_id if destination_candidate is not None else destination.id
                    ),
                    destination_fingerprint_key=(
                        destination_candidate.fingerprint_key or destination_candidate.candidate_id
                        if destination_candidate is not None
                        else destination.id
                    ),
                )
            except GestureBindingError as exc:
                rejection_code = (
                    ProposalRejectionCode.NO_BACKEND
                    if exc.code == RuntimeErrorCode.BACKEND_UNAVAILABLE
                    else ProposalRejectionCode.STALE_SNAPSHOT
                    if exc.code
                    in {
                        RuntimeErrorCode.STALE_OBSERVATION,
                        RuntimeErrorCode.STALE_PAGE_REVISION,
                        RuntimeErrorCode.SNAPSHOT_MISMATCH,
                        RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
                        RuntimeErrorCode.LEASE_EXPIRED,
                    }
                    else ProposalRejectionCode.UNSUPPORTED_ACTION
                )
                raise ProposalRejected(rejection_code, exc.detail) from exc
            contract = replace(contract, gesture_binding=gesture_binding, contract_hash="")
        risk = contract_requirements.risk or _max_risk(
            _max_risk(affordance.risk, destination.risk) if destination is not None else affordance.risk,
            _operation_risk(task_spec.operation_class),
        )
        idempotency_key = contract_requirements.idempotency_key
        if not idempotency_key and proposal.action_kind in {
            PlannerActionKind.TYPE_TEXT,
            PlannerActionKind.SELECT_OPTION,
        }:
            idempotency_key = (
                f"task:{task_spec.task_id}:revision:{task_spec.revision}:"
                f"target:{affordance.id}:parameters:{sorted(parameters.items())}"
            )
        scope_authorization = None
        if contract.grounding_candidate is not None and source_resolution is not None:
            ordinal_constraint = resolve_global_ordinal_constraint(
                objective=task_spec.objective,
                targets=task_spec.targets,
                affordances=snapshot_collection_affordances(snapshot),
            )
            scope_decision = self._value_transfer_scope_decision(
                proposal,
                state,
                snapshot,
                contract.grounding_candidate,
            )
            if scope_decision is None:
                scope_decision = ProposalScopeEvaluator().evaluate(
                    action_kind=proposal.action_kind.value,
                    target_id=proposal.target_affordance_id,
                    target_label=source_resolution.target.label,
                    target_role=source_resolution.target.role,
                    parameters=proposal.parameters,
                    objective=task_spec.objective,
                    targets=task_spec.targets,
                    unified_affordances=snapshot.unified_affordances,
                    observation=snapshot.observation,
                    selected_candidate=contract.grounding_candidate,
                    ordinal_constraint=ordinal_constraint,
                )
            if not scope_decision.authorized:
                rejection = (
                    ProposalRejectionCode.UNREQUESTED_EFFECT
                    if scope_decision.rejection == ScopeRejectionKind.UNREQUESTED_EFFECT
                    else ProposalRejectionCode.TARGET_OUT_OF_SCOPE
                )
                raise ProposalRejected(
                    rejection,
                    scope_decision.detail,
                    reason_code=(
                        scope_decision.reason.value
                        if scope_decision.reason is not None
                        else ""
                    ),
                )
            scope_authorization = scope_decision.authorization
        return replace(
            contract,
            scope_authorization=scope_authorization,
            risk=risk,
            idempotency_key=idempotency_key,
            compensation=contract_requirements.compensation,
            timeout_ms=contract_requirements.timeout_ms,
            contract_hash="",
        )

    @staticmethod
    def _value_transfer_scope_decision(
        proposal: PlannerProposal,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        destination_candidate: GroundingCandidate,
    ) -> ProposalScopeDecision | None:
        source_target_id = _active_value_transfer_source_target(
            state,
            snapshot,
            proposal.target_affordance_id,
        )
        if source_target_id is None:
            return None
        source_target = next(
            (
                item
                for item in snapshot.unified_affordances
                if item.semantic_target_id == source_target_id
            ),
            None,
        )
        source_by_id = {
            item.id: item for item in snapshot.affordance_model.affordances
        }
        safe_sources: list[tuple[GroundingCandidate, str]] = []
        if source_target is not None:
            for candidate in source_target.grounding_candidates:
                affordance = source_by_id.get(candidate.source_affordance_id)
                value = _exact_transfer_source_value(
                    affordance.state if affordance is not None else {}
                )
                if candidate.is_current(snapshot.observation) and value is not None:
                    safe_sources.append((candidate, value))
        if not safe_sources:
            return ProposalScopeDecision(
                False,
                ScopeRejectionKind.TARGET_OUT_OF_SCOPE,
                proposal.target_affordance_id,
                ScopeRejectionReason.SEMANTIC_VALUE_NOT_AUTHORIZED,
            )
        source_candidate, observed_value = min(
            safe_sources,
            key=lambda item: item[0].candidate_id,
        )
        return authorize_observed_value_transfer(
            source_candidate=source_candidate,
            destination_candidate=destination_candidate,
            observation=snapshot.observation,
            observed_value=observed_value,
            parameter_value=proposal.parameters.get("text"),
        )

    def _resolve_unified_target(
        self,
        semantic_target_id: str,
        *,
        action: PlannerActionKind,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        snapshot: BrowserSnapshot,
        available_executors: frozenset[str] | None = None,
        verifier_kinds: tuple[str, ...] | None = None,
        excluded_candidate_ids: frozenset[str] = frozenset(),
    ) -> UnifiedTargetResolution | None:
        if not any(item.semantic_target_id == semantic_target_id for item in snapshot.unified_affordances):
            return None
        try:
            return self.unified_resolver.resolve(
                semantic_target_id,
                action=action,
                task_spec=task_spec,
                subgoal=proposal.subgoal,
                snapshot=snapshot,
                available_executors=(
                    available_executors if available_executors is not None else self._available_executors(snapshot)
                ),
                verifier_kinds=(
                    verifier_kinds
                    if verifier_kinds is not None
                    else self._route_verifier_kinds(semantic_target_id, snapshot)
                ),
                excluded_candidate_ids=excluded_candidate_ids,
            )
        except ValueError as exc:
            raise ProposalRejected(ProposalRejectionCode.NO_BACKEND, str(exc)) from exc

    def _available_executors(self, snapshot: BrowserSnapshot) -> frozenset[str]:
        return frozenset(
            candidate.compatible_executor
            for target in snapshot.unified_affordances
            for candidate in target.grounding_candidates
        )

    def _route_verifier_kinds(
        self,
        semantic_target_id: str,
        snapshot: BrowserSnapshot,
    ) -> tuple[str, ...]:
        requirements = self.requirements.get(semantic_target_id)
        if requirements is None:
            target = next(
                (
                    item
                    for item in snapshot.unified_affordances
                    if item.semantic_target_id == semantic_target_id
                ),
                None,
            )
            source_ids = (
                tuple(
                    candidate.source_affordance_id
                    for candidate in target.grounding_candidates
                )
                if target is not None
                else ()
            )
            requirements = next(
                (self.requirements[item] for item in source_ids if item in self.requirements),
                ContractRequirements(),
            )
        return tuple(spec.kind for spec in requirements.verifier_plan)

    @staticmethod
    def _legacy_affordance(
        affordance_id: str,
        snapshot: BrowserSnapshot,
    ) -> Affordance | None:
        return next(
            (item for item in snapshot.affordance_model.affordances if item.id == affordance_id),
            None,
        )


def _action_compatible(kind: PlannerActionKind, affordance_action: str) -> bool:
    return (
        affordance_action
        in {
            PlannerActionKind.ACTIVATE: {"activate", "click", "download", "invoke", "write_property"},
            PlannerActionKind.POINT_ACTIVATE: {"point_activate"},
            PlannerActionKind.TYPE_TEXT: {"fill", "type"},
            PlannerActionKind.SELECT_OPTION: {"select", "select_option"},
            PlannerActionKind.PRESS_KEY: {"press"},
            PlannerActionKind.DRAG: {"drag"},
            PlannerActionKind.NAVIGATE: {"navigate"},
            PlannerActionKind.SCROLL: {"scroll"},
            PlannerActionKind.WAIT: {"wait"},
            PlannerActionKind.ASK_USER: set(),
            PlannerActionKind.FINISH: set(),
        }[kind]
    )


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
