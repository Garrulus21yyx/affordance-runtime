"""Verified-success semantic TaskSkill schemas, mining, and incremental exposure."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, Observation, RiskLevel
from affordance_runtime.criteria import (
    CriteriaEvidenceMatcher,
    SkillStepVerificationReport,
    criteria_from_descriptions,
    evidence_requirements_from_descriptions,
    skill_step_owner_id,
)
from affordance_runtime.planning import PlannerActionKind, PlannerProposal
from affordance_runtime.state_kernel import StateKernel, TaskSkillRunState
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.verification import VerificationReport

_FORBIDDEN_HANDLE_PATTERNS = (
    r"\bxpath\b",
    r"\bcss\s*=",
    r"\bnth-(?:child|of-type)\b",
    r"\bbackend_handle\s*[:=]",
    r"\b(?:selector|mark_id|screenshot_ref|browser_handle|approval_token)\b",
    r"\b(?:x|y)\s*[:=]\s*-?\d",
    r"://",
)
_FORBIDDEN_HANDLE_RE = re.compile("|".join(_FORBIDDEN_HANDLE_PATTERNS), re.IGNORECASE)


class SkillParameterType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class SkillParameter:
    name: str
    value_type: SkillParameterType
    required: bool = True
    enum_values: tuple[str, ...] = ()

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.name):
            raise ValueError(f"invalid TaskSkill parameter name: {self.name}")
        if self.enum_values and self.value_type != SkillParameterType.STRING:
            raise ValueError("TaskSkill enum values require a string parameter")
        _assert_semantic(self.enum_values)


@dataclass(frozen=True)
class SemanticTargetQuery:
    role: str
    label_template: str
    action: str

    def validate(self) -> None:
        if not self.role or not self.label_template or not self.action:
            raise ValueError("semantic target query fields must be non-empty")
        _assert_semantic((self.role, self.label_template, self.action))


@dataclass(frozen=True)
class SkillStep:
    step_id: str
    objective_template: str
    action_kind: str
    target_query: SemanticTargetQuery
    destination_query: SemanticTargetQuery | None = None
    parameter_bindings: tuple[tuple[str, str], ...] = ()
    constant_parameters: tuple[tuple[str, Any], ...] = ()
    preconditions: tuple[str, ...] = ()
    invalidation_rules: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    risk: str = RiskLevel.LOW.value
    requires_approval: bool = False

    def validate(self, parameter_names: frozenset[str]) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.step_id):
            raise ValueError(f"invalid TaskSkill step id: {self.step_id}")
        try:
            action = PlannerActionKind(self.action_kind)
            RiskLevel(self.risk)
        except ValueError as exc:
            raise ValueError(f"invalid TaskSkill step enum: {exc}") from exc
        self.target_query.validate()
        if action == PlannerActionKind.DRAG:
            if self.destination_query is None:
                raise ValueError("TaskSkill drag step requires a semantic destination query")
            self.destination_query.validate()
        elif self.destination_query is not None:
            raise ValueError("only a TaskSkill drag step may declare a destination query")
        bound_names = [name for _, name in self.parameter_bindings]
        if any(name not in parameter_names for name in bound_names):
            raise ValueError("TaskSkill step references an undeclared parameter")
        if len({name for name, _ in self.parameter_bindings}) != len(self.parameter_bindings):
            raise ValueError("TaskSkill step parameter destinations must be unique")
        if len({name for name, _ in self.constant_parameters}) != len(self.constant_parameters):
            raise ValueError("TaskSkill step constant parameter names must be unique")
        if set(name for name, _ in self.parameter_bindings).intersection(name for name, _ in self.constant_parameters):
            raise ValueError("TaskSkill parameter cannot be both bound and constant")
        if not self.postconditions or not self.evidence_requirements:
            raise ValueError("every TaskSkill step requires postconditions and independent evidence")
        _assert_semantic(asdict(self))


@dataclass(frozen=True)
class TaskSkillTrigger:
    task_family: str
    objective_terms: tuple[str, ...]

    def validate(self) -> None:
        if not self.task_family or not self.objective_terms:
            raise ValueError("TaskSkill trigger requires task family and objective terms")
        _assert_semantic(asdict(self))


@dataclass(frozen=True)
class TaskSkillPayload:
    schema_version: str
    patch_kind: str
    skill_id: str
    version: str
    trigger: TaskSkillTrigger
    parameters: tuple[SkillParameter, ...]
    steps: tuple[SkillStep, ...]
    applicability: tuple[str, ...]
    source_traces: tuple[str, ...]
    source_variants: tuple[str, ...]
    negative_examples: tuple[str, ...] = ()
    heldout_suite: str = ""

    def validate(self) -> None:
        if self.schema_version != "1.0" or self.patch_kind != "task_skill":
            raise ValueError("unsupported TaskSkill payload schema or kind")
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,127}", self.skill_id):
            raise ValueError("invalid TaskSkill id")
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ValueError("TaskSkill version must use semantic versioning")
        self.trigger.validate()
        if len(self.source_traces) < 3 or len(set(self.source_variants)) < 2:
            raise ValueError("TaskSkill requires at least three traces across two variants")
        if not self.steps or not self.applicability or not self.heldout_suite:
            raise ValueError("TaskSkill requires steps, applicability, and a held-out suite")
        names = [item.name for item in self.parameters]
        if len(set(names)) != len(names):
            raise ValueError("TaskSkill parameter names must be unique")
        for parameter in self.parameters:
            parameter.validate()
        for step in self.steps:
            step.validate(frozenset(names))
        if len({item.step_id for item in self.steps}) != len(self.steps):
            raise ValueError("TaskSkill step ids must be unique")
        _assert_semantic(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def digest(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TaskSkillPayload":
        trigger_value = _mapping(value.get("trigger"), "trigger")
        parameters = tuple(
            SkillParameter(
                name=str(item.get("name", "")),
                value_type=SkillParameterType(str(item.get("value_type", ""))),
                required=bool(item.get("required", True)),
                enum_values=tuple(_string_list(item.get("enum_values", []), "enum_values")),
            )
            for item in _mapping_list(value.get("parameters", []), "parameters")
        )
        steps = tuple(_step_from_dict(item) for item in _mapping_list(value.get("steps"), "steps"))
        payload = cls(
            schema_version=str(value.get("schema_version", "")),
            patch_kind=str(value.get("patch_kind", "")),
            skill_id=str(value.get("skill_id", "")),
            version=str(value.get("version", "")),
            trigger=TaskSkillTrigger(
                str(trigger_value.get("task_family", "")),
                tuple(_string_list(trigger_value.get("objective_terms"), "objective_terms")),
            ),
            parameters=parameters,
            steps=steps,
            applicability=tuple(_string_list(value.get("applicability"), "applicability")),
            source_traces=tuple(_string_list(value.get("source_traces"), "source_traces")),
            source_variants=tuple(_string_list(value.get("source_variants"), "source_variants")),
            negative_examples=tuple(_string_list(value.get("negative_examples", []), "negative_examples")),
            heldout_suite=str(value.get("heldout_suite", "")),
        )
        payload.validate()
        return payload


@dataclass(frozen=True)
class VerifiedSemanticStep:
    action_kind: str
    target_role: str
    target_label: str
    parameters: tuple[tuple[str, Any], ...] = ()
    destination_role: str = ""
    destination_label: str = ""
    postconditions: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifiedSemanticTrace:
    trace_id: str
    task_family: str
    variant: str
    objective: str
    steps: tuple[VerifiedSemanticStep, ...]
    independently_verified: bool = True
    policy_violations: int = 0
    verifier_false_accepts: int = 0


@dataclass(frozen=True)
class SemanticTraceNormalizer:
    def normalize(self, trace: VerifiedSemanticTrace) -> VerifiedSemanticTrace:
        if (
            not trace.trace_id
            or not trace.task_family
            or not trace.variant
            or not trace.steps
            or not trace.independently_verified
            or trace.policy_violations
            or trace.verifier_false_accepts
        ):
            raise ValueError("TaskSkill source trace is not independently safe and verified")
        steps = tuple(
            VerifiedSemanticStep(
                action_kind=PlannerActionKind(step.action_kind).value,
                target_role=_normalize(step.target_role),
                target_label=" ".join(step.target_label.split()),
                parameters=tuple(sorted(step.parameters)),
                destination_role=_normalize(step.destination_role),
                destination_label=" ".join(step.destination_label.split()),
                postconditions=tuple(_normalize(item) for item in step.postconditions),
                evidence_requirements=tuple(_normalize(item) for item in step.evidence_requirements),
            )
            for step in trace.steps
        )
        if any(not step.postconditions or not step.evidence_requirements for step in steps):
            raise ValueError("every verified semantic step needs postcondition evidence")
        normalized = VerifiedSemanticTrace(
            trace.trace_id,
            _normalize(trace.task_family),
            _normalize(trace.variant),
            " ".join(trace.objective.split()),
            steps,
        )
        _assert_semantic(asdict(normalized))
        return normalized


@dataclass(frozen=True)
class TaskSkillMiner:
    minimum_traces: int = 3
    minimum_variants: int = 2
    normalizer: SemanticTraceNormalizer = SemanticTraceNormalizer()

    def mine(
        self,
        traces: Iterable[VerifiedSemanticTrace],
        *,
        skill_id: str,
        heldout_suite: str,
    ) -> TaskSkillPayload:
        normalized = tuple(self.normalizer.normalize(item) for item in traces)
        if len(normalized) < self.minimum_traces:
            raise ValueError("insufficient independently verified traces for TaskSkill")
        families = {item.task_family for item in normalized}
        variants = {item.variant for item in normalized}
        if len(families) != 1 or len(variants) < self.minimum_variants:
            raise ValueError("TaskSkill traces must share one family across two variants")
        step_count = len(normalized[0].steps)
        if any(len(item.steps) != step_count for item in normalized):
            raise ValueError("TaskSkill traces do not share one semantic step shape")

        parameters: list[SkillParameter] = []
        steps: list[SkillStep] = []
        for index in range(step_count):
            source_steps = tuple(item.steps[index] for item in normalized)
            action_kinds = {item.action_kind for item in source_steps}
            roles = {item.target_role for item in source_steps}
            destination_roles = {item.destination_role for item in source_steps}
            if len(action_kinds) != 1 or len(roles) != 1 or len(destination_roles) != 1:
                raise ValueError("TaskSkill traces differ in action or semantic role")
            target_template = self._template_slot(
                parameters,
                f"step_{index + 1}_target_label",
                tuple(item.target_label for item in source_steps),
            )
            destination_template = self._template_slot(
                parameters,
                f"step_{index + 1}_destination_label",
                tuple(item.destination_label for item in source_steps),
            )
            parameter_maps = [dict(item.parameters) for item in source_steps]
            if any(set(item) != set(parameter_maps[0]) for item in parameter_maps):
                raise ValueError("TaskSkill trace parameters do not share one schema")
            bindings: list[tuple[str, str]] = []
            constants: list[tuple[str, Any]] = []
            for name in sorted(parameter_maps[0]):
                values = tuple(item[name] for item in parameter_maps)
                if len({_json_value(item) for item in values}) == 1:
                    constants.append((name, values[0]))
                else:
                    slot = f"step_{index + 1}_{_normalize_slot(name)}"
                    parameters.append(SkillParameter(slot, _parameter_type(values)))
                    bindings.append((name, slot))
            first = source_steps[0]
            action = next(iter(action_kinds))
            destination_query = (
                SemanticTargetQuery(next(iter(destination_roles)), destination_template, "drag")
                if action == PlannerActionKind.DRAG.value
                else None
            )
            steps.append(
                SkillStep(
                    step_id=f"step-{index + 1}",
                    objective_template=f"{action} {target_template}",
                    action_kind=action,
                    target_query=SemanticTargetQuery(next(iter(roles)), target_template, action),
                    destination_query=destination_query,
                    parameter_bindings=tuple(bindings),
                    constant_parameters=tuple(constants),
                    postconditions=first.postconditions,
                    evidence_requirements=first.evidence_requirements,
                )
            )
        objective_terms = tuple(
            dict.fromkeys(term for item in normalized for term in re.findall(r"[a-z0-9_-]+", item.objective.casefold()))
        )[:16]
        payload = TaskSkillPayload(
            "1.0",
            "task_skill",
            skill_id,
            "1.0.0",
            TaskSkillTrigger(next(iter(families)), objective_terms),
            tuple(parameters),
            tuple(steps),
            tuple(sorted(variants)),
            tuple(item.trace_id for item in normalized),
            tuple(item.variant for item in normalized),
            heldout_suite=heldout_suite,
        )
        payload.validate()
        return payload

    @staticmethod
    def _template_slot(
        parameters: list[SkillParameter],
        name: str,
        values: tuple[str, ...],
    ) -> str:
        if len(set(values)) == 1:
            return values[0]
        if not all(values):
            raise ValueError("TaskSkill semantic target labels cannot be partially absent")
        parameters.append(SkillParameter(name, SkillParameterType.STRING))
        return "{{" + name + "}}"


TaskSkillProgress = TaskSkillRunState


@dataclass(frozen=True)
class SkillStepExposure:
    proposal: PlannerProposal | None
    step_id: str = ""
    fallthrough: bool = False
    reason: str = ""


@dataclass(frozen=True)
class IncrementalTaskSkillExecutor:
    def expose_next(
        self,
        payload: TaskSkillPayload,
        bindings: Mapping[str, Any],
        task: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        progress: TaskSkillProgress,
    ) -> SkillStepExposure:
        payload.validate()
        if progress.skill_id != payload.skill_id or progress.version != payload.version:
            raise ValueError("TaskSkill progress identity mismatch")
        if progress.next_step_index >= len(payload.steps):
            return SkillStepExposure(None, reason="TaskSkill completed")
        step = payload.steps[progress.next_step_index]
        _validate_bindings(
            payload.parameters,
            bindings,
            required_names=_step_binding_names(step),
        )
        target_label = _render(step.target_query.label_template, bindings)
        targets = [
            item
            for item in snapshot.unified_affordances
            if _normalize(item.role) == _normalize(step.target_query.role)
            and _normalize(item.label) == _normalize(target_label)
            and step.action_kind in item.supported_actions
        ]
        if len(targets) != 1:
            reason = f"semantic target query matched {len(targets)} candidates"
            progress.fallthrough_reason = reason
            return SkillStepExposure(None, step.step_id, True, reason)
        destination_id = ""
        if step.destination_query is not None:
            destination_label = _render(step.destination_query.label_template, bindings)
            destinations = [
                item
                for item in snapshot.unified_affordances
                if _normalize(item.role) == _normalize(step.destination_query.role)
                and _normalize(item.label) == _normalize(destination_label)
                and PlannerActionKind.DRAG.value in item.supported_actions
            ]
            if len(destinations) != 1 or destinations[0].semantic_target_id == targets[0].semantic_target_id:
                reason = "semantic destination query is missing, ambiguous, or identical"
                progress.fallthrough_reason = reason
                return SkillStepExposure(None, step.step_id, True, reason)
            destination_id = destinations[0].semantic_target_id
        parameters = dict(step.constant_parameters)
        parameters.update({name: bindings[slot] for name, slot in step.parameter_bindings})
        proposal = PlannerProposal(
            proposal_id=f"skill-{payload.skill_id}-{step.step_id}-{state.version}",
            based_on_task_revision=task.revision,
            based_on_state_version=state.version,
            snapshot_id=snapshot.observation.snapshot_id,
            subgoal=_render(step.objective_template, bindings),
            action_kind=PlannerActionKind(step.action_kind),
            target_affordance_id=targets[0].semantic_target_id,
            destination_affordance_id=destination_id,
            parameters=parameters,
            expected_effects=step.postconditions,
            evidence_requirements=step.evidence_requirements,
        )
        return SkillStepExposure(proposal, step.step_id)

    def checkpoint_verified(
        self,
        payload: TaskSkillPayload,
        progress: TaskSkillProgress,
        *,
        step_id: str,
        verified: bool,
        evidence: Iterable[str] = (),
    ) -> None:
        expected = payload.steps[progress.next_step_index]
        if expected.step_id != step_id:
            raise ValueError("TaskSkill checkpoint is not the active step")
        if not verified:
            progress.fallthrough_reason = f"verification failed for {step_id}"
            return
        progress.completed_step_ids.append(step_id)
        progress.evidence.extend(item for item in evidence if item not in progress.evidence)
        progress.next_step_index += 1
        progress.fallthrough_reason = ""


TaskSkillBindingResolver = Callable[
    [TaskSkillPayload, TaskSpec, BrowserSnapshot, TaskSkillRunState | None],
    Mapping[str, Any] | None,
]


@dataclass(frozen=True)
class TaskSkillRuntimeDecision:
    payload: TaskSkillPayload | None = None
    exposure: SkillStepExposure | None = None
    newly_activated: bool = False
    attempted: bool = False
    reason: str = ""


@dataclass(frozen=True)
class AcceptedTaskSkillRuntime:
    """System 1 selector over payloads already accepted by the registry."""

    payloads: tuple[TaskSkillPayload, ...]
    accepted_payload_digests: frozenset[str]
    binding_resolver: TaskSkillBindingResolver | None = None
    executor: IncrementalTaskSkillExecutor = IncrementalTaskSkillExecutor()
    criteria_matcher: CriteriaEvidenceMatcher = CriteriaEvidenceMatcher()

    def __post_init__(self) -> None:
        digests = frozenset(item.digest() for item in self.payloads)
        if digests != self.accepted_payload_digests:
            raise ValueError("TaskSkill runtime requires digest-validated loaded payloads")

    @classmethod
    def from_profile(
        cls,
        profile: Any,
        *,
        binding_resolver: TaskSkillBindingResolver | None = None,
    ) -> "AcceptedTaskSkillRuntime":
        payloads = tuple(item for item in profile.loaded.values() if isinstance(item, TaskSkillPayload))
        return cls(
            payloads,
            frozenset(item.digest() for item in payloads),
            binding_resolver,
        )

    def expose(
        self,
        task: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> TaskSkillRuntimeDecision:
        active = state.task_skill
        if active is not None:
            if not active.active:
                return TaskSkillRuntimeDecision(reason=active.fallthrough_reason)
            payload = next(
                (item for item in self.payloads if item.skill_id == active.skill_id and item.version == active.version),
                None,
            )
            if payload is None:
                state.fall_through_task_skill("accepted TaskSkill payload is no longer loaded")
                return TaskSkillRuntimeDecision(
                    attempted=True,
                    reason="accepted TaskSkill payload is no longer loaded",
                )
            bindings = self._bindings(payload, task, snapshot, active)
            if bindings is not None:
                state.update_task_skill_bindings(dict(bindings))
            return self._expose_payload(payload, task, state, snapshot, newly_activated=False)

        candidates: list[tuple[TaskSkillPayload, Mapping[str, Any]]] = []
        for payload in self.payloads:
            if not self._trigger_matches(payload, task):
                continue
            bindings = self._bindings(payload, task, snapshot, None)
            if bindings is not None:
                candidates.append((payload, bindings))
        if not candidates:
            return TaskSkillRuntimeDecision(reason="no accepted TaskSkill matched")
        if len(candidates) > 1:
            return TaskSkillRuntimeDecision(
                attempted=True,
                reason="multiple accepted TaskSkills matched; use System 2",
            )
        payload, bindings = candidates[0]
        state.activate_task_skill(payload.skill_id, payload.version, dict(bindings))
        return self._expose_payload(payload, task, state, snapshot, newly_activated=True)

    def verify_active_step(
        self,
        state: StateKernel,
        *,
        step_id: str,
        verification: VerificationReport,
        observation: Observation,
    ) -> SkillStepVerificationReport:
        active = state.task_skill
        if active is None:
            raise ValueError("no TaskSkill progress to checkpoint")
        payload = next(
            item for item in self.payloads if item.skill_id == active.skill_id and item.version == active.version
        )
        if active.next_step_index >= len(payload.steps):
            raise ValueError("TaskSkill has no active step to verify")
        step = payload.steps[active.next_step_index]
        if step.step_id != step_id:
            raise ValueError("TaskSkill verification does not match the active step")
        owner_id = skill_step_owner_id(payload.skill_id, payload.version, step.step_id)
        match = self.criteria_matcher.match(
            criteria=criteria_from_descriptions("skill-step", owner_id, step.postconditions),
            requirements=evidence_requirements_from_descriptions("skill-step", owner_id, step.evidence_requirements),
            verification=verification,
            observation=observation,
        )
        return SkillStepVerificationReport(
            payload.skill_id,
            payload.version,
            step.step_id,
            match,
        )

    def checkpoint_verified(
        self,
        state: StateKernel,
        *,
        report: SkillStepVerificationReport,
        artifact_refs: Iterable[str] = (),
    ) -> bool:
        if not report.passed:
            raise ValueError("TaskSkill progress requires a passed criteria match report")
        active = state.task_skill
        if active is None:
            raise ValueError("no TaskSkill progress to checkpoint")
        payload = next(
            item for item in self.payloads if item.skill_id == active.skill_id and item.version == active.version
        )
        if report.skill_id != payload.skill_id or report.skill_version != payload.version:
            raise ValueError("TaskSkill criteria report identity mismatch")
        evidence = [*report.match.evidence_ids, *artifact_refs]
        state.checkpoint_task_skill_step(report.step_id, evidence)
        return state.task_skill is not None and state.task_skill.next_step_index >= len(payload.steps)

    def contract_requirement_error(
        self,
        state: StateKernel,
        contract: ActionContract,
        *,
        approval_required_risks: frozenset[RiskLevel],
        approval_required_capabilities: frozenset[str],
    ) -> str:
        """Fail closed when a skill is stricter than the fresh normal contract.

        TaskSkill requirements constrain reuse; they never add capability or
        approval authority to a contract.
        """

        active = state.task_skill
        if active is None:
            return "TaskSkill progress is missing"
        payload = next(
            (item for item in self.payloads if item.skill_id == active.skill_id and item.version == active.version),
            None,
        )
        if payload is None or active.next_step_index >= len(payload.steps):
            return "accepted TaskSkill step is no longer available"
        step = payload.steps[active.next_step_index]
        missing = sorted(set(step.required_capabilities) - set(contract.required_capabilities))
        if missing:
            return f"TaskSkill contract lacks required capabilities: {', '.join(missing)}"
        if _risk_rank(contract.risk) < _risk_rank(RiskLevel(step.risk)):
            return (
                "TaskSkill contract risk is weaker than the accepted step requirement: "
                f"{contract.risk.value} < {step.risk}"
            )
        approval_enforced = contract.risk in approval_required_risks or bool(
            set(contract.required_capabilities) & approval_required_capabilities
        )
        if step.requires_approval and not approval_enforced:
            return "TaskSkill step requires approval but the normal contract gate does not"
        return ""

    @staticmethod
    def fallthrough(state: StateKernel, reason: str) -> None:
        state.fall_through_task_skill(reason)

    def _expose_payload(
        self,
        payload: TaskSkillPayload,
        task: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        *,
        newly_activated: bool,
    ) -> TaskSkillRuntimeDecision:
        active = state.task_skill
        if active is None:
            raise ValueError("TaskSkill activation state is missing")
        if active.next_step_index >= len(payload.steps):
            return TaskSkillRuntimeDecision(
                payload,
                SkillStepExposure(None, reason="TaskSkill completed"),
                newly_activated,
                True,
                "TaskSkill completed",
            )
        step = payload.steps[active.next_step_index]
        missing_capabilities = sorted(set(step.required_capabilities) - set(task.requested_capabilities))
        if missing_capabilities:
            reason = "TaskSkill cannot extend task capability authority: " + ", ".join(missing_capabilities)
            state.fall_through_task_skill(reason)
            return TaskSkillRuntimeDecision(
                payload,
                SkillStepExposure(None, step.step_id, True, reason),
                newly_activated,
                True,
                reason,
            )
        state.expose_task_skill_step(step.step_id)
        try:
            exposure = self.executor.expose_next(
                payload,
                active.bindings,
                task,
                state,
                snapshot,
                active,
            )
        except ValueError as exc:
            exposure = SkillStepExposure(None, step.step_id, True, str(exc))
        if exposure.fallthrough:
            state.fall_through_task_skill(exposure.reason)
        return TaskSkillRuntimeDecision(
            payload,
            exposure,
            newly_activated,
            True,
            exposure.reason,
        )

    def _bindings(
        self,
        payload: TaskSkillPayload,
        task: TaskSpec,
        snapshot: BrowserSnapshot,
        progress: TaskSkillRunState | None,
    ) -> Mapping[str, Any] | None:
        if self.binding_resolver is not None:
            return self.binding_resolver(payload, task, snapshot, progress)
        return _default_skill_bindings(payload, task, snapshot, progress)

    @staticmethod
    def _trigger_matches(payload: TaskSkillPayload, task: TaskSpec) -> bool:
        text = " ".join((task.objective, *task.targets)).casefold()
        terms = set(re.findall(r"[a-z0-9_-]+", text))
        family_terms = set(re.findall(r"[a-z0-9_-]+", payload.trigger.task_family))
        return bool(family_terms) and family_terms.issubset(terms)


def _risk_rank(risk: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.IRREVERSIBLE: 3,
    }[risk]


@dataclass(frozen=True)
class TaskSkillReplayEvidence:
    category: str
    trace_id: str
    variant: str
    success: bool
    independently_verified: bool
    activated: bool
    applicable: bool
    model_calls: int
    latency_ms: float
    policy_violations: int = 0
    verifier_false_accepts: int = 0
    duplicate_effect_risks: int = 0
    fell_through: bool = False


@dataclass(frozen=True)
class TaskSkillReplayDecision:
    status: str
    reason: str
    metrics: dict[str, float]


@dataclass(frozen=True)
class TaskSkillReplayGate:
    mandatory_categories: frozenset[str] = frozenset(
        {"original", "task_family", "heldout", "global_smoke", "safety_smoke"}
    )

    def evaluate(
        self,
        registry: Any,
        artifact_id: str,
        evidence: Iterable[TaskSkillReplayEvidence],
        *,
        baseline_model_calls: float,
        baseline_latency_ms: float,
    ) -> TaskSkillReplayDecision:
        from affordance_runtime.evolution import (
            EvolutionStatus,
            MetricDirection,
            RegressionRule,
        )

        artifact = registry.artifacts[artifact_id]
        runs = tuple(evidence)
        categories = {item.category for item in runs if item.success and item.independently_verified}
        activated = [item for item in runs if item.activated]
        correct_activations = [item for item in activated if item.applicable]
        metrics = {
            "task_success_rate": sum(item.success for item in runs) / len(runs) if runs else 0.0,
            "unsafe_side_effect_rate": (sum(item.policy_violations for item in runs) / len(runs) if runs else 1.0),
            "verifier_false_accept_rate": (
                sum(item.verifier_false_accepts for item in runs) / len(runs) if runs else 1.0
            ),
            "duplicate_effect_risk_rate": (
                sum(item.duplicate_effect_risks for item in runs) / len(runs) if runs else 1.0
            ),
            "skill_activation_precision": (len(correct_activations) / len(activated) if activated else 0.0),
            "skill_fallthrough_rate": (sum(item.fell_through for item in runs) / len(runs) if runs else 1.0),
            "mean_model_calls": (sum(item.model_calls for item in runs) / len(runs) if runs else float("inf")),
            "mean_latency_ms": (sum(item.latency_ms for item in runs) / len(runs) if runs else float("inf")),
        }
        metrics["model_call_reduction"] = baseline_model_calls - metrics["mean_model_calls"]
        metrics["latency_reduction_ms"] = baseline_latency_ms - metrics["mean_latency_ms"]
        artifact.regression_results = metrics
        missing = sorted(self.mandatory_categories - categories)
        efficiency_improved = metrics["model_call_reduction"] > 0 or metrics["latency_reduction_ms"] > 0
        if missing or not runs or not efficiency_improved:
            artifact.status = EvolutionStatus.QUARANTINED
            reasons = []
            if missing:
                reasons.append(f"missing successful replay categories: {', '.join(missing)}")
            if not runs:
                reasons.append("no fresh replay evidence")
            if not efficiency_improved:
                reasons.append("TaskSkill did not reduce model calls or latency")
            artifact.decision_reason = "; ".join(reasons)
            return TaskSkillReplayDecision(
                artifact.status.value,
                artifact.decision_reason,
                metrics,
            )
        status = registry.accept_if_regression_passes(
            artifact_id,
            rules=[
                RegressionRule("task_success_rate", MetricDirection.HIGHER_IS_BETTER, 1.0),
                RegressionRule("unsafe_side_effect_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("verifier_false_accept_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("duplicate_effect_risk_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("skill_activation_precision", MetricDirection.HIGHER_IS_BETTER, 1.0),
            ],
        )
        return TaskSkillReplayDecision(status.value, artifact.decision_reason, metrics)


def quarantine_task_skill(payload: TaskSkillPayload, registry: Any) -> Any:
    """Persist every mined TaskSkill as quarantined before any replay."""

    from affordance_runtime.evolution import (
        EvolutionArtifact,
        EvolutionArtifactType,
        EvolutionStatus,
    )

    payload.validate()
    artifact = EvolutionArtifact(
        id=payload.skill_id,
        artifact_type=EvolutionArtifactType.TASK_SKILL.value,
        summary=f"Verified-success TaskSkill for {payload.trigger.task_family}",
        applicability={"task_family": payload.trigger.task_family},
        source_traces=list(payload.source_traces),
        negative_examples=list(payload.negative_examples),
        status=EvolutionStatus.QUARANTINED,
        version=payload.version,
        target_suite_versions=[payload.heldout_suite],
        rollback_artifact="system-2-planner",
        decision_reason="quarantined pending mandatory held-out replay",
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    registry.propose(artifact)
    return artifact


def _step_from_dict(value: dict[str, Any]) -> SkillStep:
    target = _mapping(value.get("target_query"), "target_query")
    raw_destination = value.get("destination_query")
    destination = None
    if raw_destination is not None:
        destination_value = _mapping(raw_destination, "destination_query")
        destination = SemanticTargetQuery(
            str(destination_value.get("role", "")),
            str(destination_value.get("label_template", "")),
            str(destination_value.get("action", "")),
        )
    return SkillStep(
        step_id=str(value.get("step_id", "")),
        objective_template=str(value.get("objective_template", "")),
        action_kind=str(value.get("action_kind", "")),
        target_query=SemanticTargetQuery(
            str(target.get("role", "")),
            str(target.get("label_template", "")),
            str(target.get("action", "")),
        ),
        destination_query=destination,
        parameter_bindings=tuple(_pair_list(value.get("parameter_bindings", []), "parameter_bindings")),
        constant_parameters=tuple(_pair_list(value.get("constant_parameters", []), "constant_parameters")),
        preconditions=tuple(_string_list(value.get("preconditions", []), "preconditions")),
        invalidation_rules=tuple(_string_list(value.get("invalidation_rules", []), "invalidation_rules")),
        postconditions=tuple(_string_list(value.get("postconditions"), "postconditions")),
        evidence_requirements=tuple(_string_list(value.get("evidence_requirements"), "evidence_requirements")),
        required_capabilities=tuple(_string_list(value.get("required_capabilities", []), "required_capabilities")),
        risk=str(value.get("risk", RiskLevel.LOW.value)),
        requires_approval=bool(value.get("requires_approval", False)),
    )


def _validate_bindings(
    parameters: tuple[SkillParameter, ...],
    bindings: Mapping[str, Any],
    *,
    required_names: frozenset[str] | None = None,
) -> None:
    declared = {item.name: item for item in parameters}
    required = (
        required_names if required_names is not None else frozenset(item.name for item in parameters if item.required)
    )
    missing = sorted(name for name in required if name not in bindings)
    unknown = sorted(set(bindings) - set(declared))
    if missing or unknown:
        raise ValueError(f"TaskSkill binding mismatch; missing={missing}, unknown={unknown}")
    for name, value in bindings.items():
        expected = declared[name]
        if expected.value_type == SkillParameterType.STRING and not isinstance(value, str):
            raise ValueError(f"TaskSkill parameter {name} requires string")
        if expected.value_type == SkillParameterType.BOOLEAN and not isinstance(value, bool):
            raise ValueError(f"TaskSkill parameter {name} requires boolean")
        if expected.value_type == SkillParameterType.NUMBER and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            raise ValueError(f"TaskSkill parameter {name} requires number")
        if expected.enum_values and value not in expected.enum_values:
            raise ValueError(f"TaskSkill parameter {name} is outside its enum")
    _assert_semantic(dict(bindings))


def _step_binding_names(step: SkillStep) -> frozenset[str]:
    templates = [step.objective_template, step.target_query.label_template]
    if step.destination_query is not None:
        templates.append(step.destination_query.label_template)
    names = {name for _, name in step.parameter_bindings}
    for template in templates:
        names.update(re.findall(r"\{\{([a-z][a-z0-9_]*)\}\}", template))
    return frozenset(names)


def _default_skill_bindings(
    payload: TaskSkillPayload,
    task: TaskSpec,
    snapshot: BrowserSnapshot,
    progress: TaskSkillRunState | None,
) -> Mapping[str, Any] | None:
    bindings = dict(progress.bindings) if progress is not None else {}
    entities = {_normalize(item.name): item.value for item in task.entities}
    for parameter in payload.parameters:
        if parameter.name in bindings:
            continue
        if parameter.name.endswith("_target_label"):
            step_index = _slot_step_index(parameter.name)
            query = payload.steps[step_index].target_query if step_index is not None else None
            label = _semantic_label_binding(task, snapshot, query, destination=False)
            if label is not None:
                bindings[parameter.name] = label
            continue
        if parameter.name.endswith("_destination_label"):
            step_index = _slot_step_index(parameter.name)
            query = payload.steps[step_index].destination_query if step_index is not None else None
            label = _semantic_label_binding(task, snapshot, query, destination=True)
            if label is not None:
                bindings[parameter.name] = label
            continue
        semantic_name = re.sub(r"^step_\d+_", "", parameter.name)
        if semantic_name in entities:
            bindings[parameter.name] = entities[semantic_name]
        elif len(entities) == 1:
            bindings[parameter.name] = next(iter(entities.values()))
    return bindings


def _slot_step_index(name: str) -> int | None:
    match = re.match(r"step_(\d+)_", name)
    if match is None:
        return None
    return int(match.group(1)) - 1


def _semantic_label_binding(
    task: TaskSpec,
    snapshot: BrowserSnapshot,
    query: SemanticTargetQuery | None,
    *,
    destination: bool,
) -> str | None:
    if query is None:
        return None
    candidates = [
        item.label
        for item in snapshot.unified_affordances
        if _normalize(item.role) == _normalize(query.role) and query.action in item.supported_actions
    ]
    target_matches = [
        label for label in candidates if any(_normalize(label) == _normalize(target) for target in task.targets)
    ]
    if len(target_matches) == 1:
        return target_matches[0]
    if len(candidates) == 1 and not destination:
        return candidates[0]
    return None


def _render(template: str, bindings: Mapping[str, Any]) -> str:
    rendered = template
    for name, value in bindings.items():
        rendered = rendered.replace("{{" + name + "}}", str(value))
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("TaskSkill template has an unbound parameter")
    return rendered


def _parameter_type(values: tuple[Any, ...]) -> SkillParameterType:
    if all(isinstance(item, bool) for item in values):
        return SkillParameterType.BOOLEAN
    if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in values):
        return SkillParameterType.NUMBER
    if all(isinstance(item, str) for item in values):
        return SkillParameterType.STRING
    raise ValueError("TaskSkill parameter values do not share one supported type")


def _assert_semantic(value: Any) -> None:
    encoded = json.dumps(value, sort_keys=True, default=str)
    if _FORBIDDEN_HANDLE_RE.search(encoded):
        raise ValueError("TaskSkill payload contains a forbidden raw handle or coordinate")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_slot(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "value"


def _json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _mapping_list(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{name} must be a list of mappings")
    return list(value)


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return list(value)


def _pair_list(value: Any, name: str) -> list[tuple[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of pairs")
    pairs: list[tuple[str, Any]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not isinstance(item[0], str):
            raise ValueError(f"{name} must contain string-key pairs")
        pairs.append((item[0], item[1]))
    return pairs
