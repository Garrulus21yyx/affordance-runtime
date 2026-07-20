"""Semantic planner proposals and deterministic ActionContract binding."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, Condition, RiskLevel, VerifierSpec
from affordance_runtime.routing import CostAwareRouter
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


class PlannerActionKind(StrEnum):
    ACTIVATE = "activate"
    TYPE_TEXT = "type_text"
    SELECT_OPTION = "select_option"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    WAIT = "wait"
    ASK_USER = "ask_user"
    FINISH = "finish"


_TARGET_ACTIONS = {
    PlannerActionKind.ACTIVATE,
    PlannerActionKind.TYPE_TEXT,
    PlannerActionKind.SELECT_OPTION,
}
_FORBIDDEN_PARAMETER_KEYS = {
    "approval",
    "approval_token",
    "backend",
    "bbox",
    "bid",
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
    PlannerActionKind.TYPE_TEXT: {"text"},
    PlannerActionKind.SELECT_OPTION: {"option"},
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
        return self


class ProposalRejectionCode(StrEnum):
    STALE_TASK_REVISION = "stale_task_revision"
    STALE_STATE_VERSION = "stale_state_version"
    STALE_SNAPSHOT = "stale_snapshot"
    MISSING_TARGET = "missing_target"
    UNSUPPORTED_ACTION = "unsupported_action"
    NO_BACKEND = "no_backend"


class ProposalRejected(ValueError):
    def __init__(self, code: ProposalRejectionCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


@dataclass(frozen=True)
class ContractRequirements:
    expected_effects: tuple[Condition, ...] = ()
    verifier_plan: tuple[VerifierSpec, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    risk: RiskLevel | None = None
    idempotency_key: str = ""
    compensation: str | None = None
    timeout_ms: int = 5_000


@dataclass
class ContractBuilder:
    router: CostAwareRouter = field(default_factory=CostAwareRouter)
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
        affordance = next(
            (
                item
                for item in snapshot.affordance_model.affordances
                if item.id == proposal.target_affordance_id
            ),
            None,
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
        candidates = {name: affordance for name in affordance.backend_candidates}
        route = self.router.route(candidates)
        if route.selected_backend is None:
            raise ProposalRejected(ProposalRejectionCode.NO_BACKEND, affordance.id)

        contract_requirements = self.requirements.get(affordance.id, ContractRequirements())
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
        contract = ActionContract.from_affordance(
            affordance,
            intent=proposal.subgoal or task_spec.objective,
            backend=route.selected_backend,
            expected_effects=list(contract_requirements.expected_effects),
            verifier_plan=list(contract_requirements.verifier_plan),
            required_capabilities=list(required_capabilities),
            parameters=parameters,
        )
        risk = contract_requirements.risk or _max_risk(
            affordance.risk,
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
        return replace(
            contract,
            risk=risk,
            idempotency_key=idempotency_key,
            compensation=contract_requirements.compensation,
            timeout_ms=contract_requirements.timeout_ms,
            contract_hash="",
        )


def _action_compatible(kind: PlannerActionKind, affordance_action: str) -> bool:
    return affordance_action in {
        PlannerActionKind.ACTIVATE: {"activate", "click", "download", "invoke", "write_property"},
        PlannerActionKind.TYPE_TEXT: {"fill", "type"},
        PlannerActionKind.SELECT_OPTION: {"select", "select_option"},
        PlannerActionKind.NAVIGATE: {"navigate"},
        PlannerActionKind.SCROLL: {"scroll"},
        PlannerActionKind.WAIT: {"wait"},
        PlannerActionKind.ASK_USER: set(),
        PlannerActionKind.FINISH: set(),
    }[kind]


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
