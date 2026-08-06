"""Bind an accepted semantic selection to one current execution route."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.action_contract_authority import rebuild_contract_authority
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.choice_contracts import ActionSelection
from affordance_runtime.collection_window import (
    resolve_global_ordinal_constraint,
    snapshot_collection_affordances,
)
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    GestureBindingError,
    GestureContractBinder,
    RuntimeErrorCode,
)
from affordance_runtime.grounding import GroundingCandidate
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    ProposalRejected,
    ProposalRejectionCode,
    UnifiedTargetResolution,
    UnifiedTargetResolver,
    _action_compatible,
    _canonical_active_value_transfer_source_target,
    _contract_parameters,
    _exact_transfer_source_value,
    _max_risk,
    _operation_risk,
)
from affordance_runtime.routing import CostAwareRouter
from affordance_runtime.scope_authorization import (
    ProposalScopeDecision,
    ProposalScopeEvaluator,
    ScopeRejectionKind,
    ScopeRejectionReason,
    authorize_observed_value_transfer,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec, task_semantic_scope_terms
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.visual_contracts import VisualContractBinder


@dataclass
class ActionContractMaterializer:
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
        snapshot: BrowserSnapshot | PerceptionCapture,
        observation: UnifiedObservation | None = None,
    ) -> ActionContract:
        canonical = observation or CanonicalObservationBuilder().build(
            PerceptionCapture.from_browser_snapshot(snapshot) if isinstance(snapshot, BrowserSnapshot) else snapshot
        )
        if proposal.based_on_task_revision != task_spec.revision:
            raise ProposalRejected(ProposalRejectionCode.STALE_TASK_REVISION)
        if proposal.based_on_state_version != state.version:
            raise ProposalRejected(ProposalRejectionCode.STALE_STATE_VERSION)
        if proposal.snapshot_id != canonical.epoch_id:
            raise ProposalRejected(ProposalRejectionCode.STALE_SNAPSHOT)
        source_resolution = self._resolve_unified_target(
            proposal.target_affordance_id,
            action=proposal.action_kind,
            proposal=proposal,
            task_spec=task_spec,
            snapshot=snapshot,
            observation=canonical,
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
                observation=canonical,
                available_executors=(frozenset({selected_executor}) if selected_executor else None),
                excluded_candidate_ids=state.excluded_candidates_for(proposal.destination_affordance_id),
                verifier_kinds=self._route_verifier_kinds(
                    proposal.target_affordance_id,
                    canonical,
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
            self.requirements.get(affordance.id, self.requirements.get("*", ContractRequirements())),
        )
        required_capabilities = tuple(
            dict.fromkeys(
                [
                    *contract_requirements.required_capabilities,
                    *task_spec.capability_ceiling,
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
            authority_refs = tuple(
                getattr(proposal, "effect_authorization_refs", ()) or getattr(proposal, "requirement_refs", ())
            )
            requirement_by_id = {item.requirement_id: item for item in task_spec.requirements}
            scope_terms = tuple(
                value
                for requirement_id in authority_refs
                if requirement_id in requirement_by_id
                for value in (
                    requirement_by_id[requirement_id].payload.subject,
                    requirement_by_id[requirement_id].payload.value,
                )
                if value.strip()
            ) or task_semantic_scope_terms(task_spec)
            ordinal_constraint = resolve_global_ordinal_constraint(
                objective="",
                targets=scope_terms,
                affordances=snapshot_collection_affordances(snapshot),
            )
            scope_decision = self._value_transfer_scope_decision(
                proposal,
                state,
                canonical,
                contract.grounding_candidate,
            )
            if scope_decision is None and isinstance(proposal, _SelectedSemanticAction):
                scope_decision = ProposalScopeDecision(True)
            if scope_decision is None:
                scope_decision = ProposalScopeEvaluator().evaluate(
                    action_kind=proposal.action_kind.value,
                    target_id=proposal.target_affordance_id,
                    target_label=source_resolution.target.label,
                    target_role=source_resolution.target.role,
                    parameters=proposal.parameters,
                    objective="",
                    targets=scope_terms,
                    unified_affordances=tuple(canonical.targets),
                    observation=canonical,
                    bindings=canonical.bindings,
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
                    reason_code=(scope_decision.reason.value if scope_decision.reason is not None else ""),
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
        snapshot: UnifiedObservation,
        destination_candidate: GroundingCandidate,
    ) -> ProposalScopeDecision | None:
        source_target_id = _canonical_active_value_transfer_source_target(
            state,
            snapshot,
            proposal.target_affordance_id,
        )
        if source_target_id is None:
            return None
        source_target = next(
            (item for item in snapshot.targets if item.target_id == source_target_id),
            None,
        )
        safe_sources: list[tuple[GroundingCandidate, str]] = []
        if source_target is not None:
            for candidate in snapshot.bindings:
                if candidate.semantic_target_id != source_target.target_id:
                    continue
                value = _exact_transfer_source_value(source_target.state)
                if candidate.is_current(snapshot) and value is not None:
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
            observation=snapshot,
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
        snapshot: BrowserSnapshot | PerceptionCapture,
        observation: UnifiedObservation,
        available_executors: frozenset[str] | None = None,
        verifier_kinds: tuple[str, ...] | None = None,
        excluded_candidate_ids: frozenset[str] = frozenset(),
    ) -> UnifiedTargetResolution | None:
        if not any(item.target_id == semantic_target_id for item in observation.targets):
            return None
        try:
            return self.unified_resolver.resolve(
                semantic_target_id,
                action=action,
                task_spec=task_spec,
                subgoal=proposal.subgoal,
                snapshot=snapshot,
                observation=observation,
                available_executors=(
                    available_executors if available_executors is not None else self._available_executors(observation)
                ),
                verifier_kinds=(
                    verifier_kinds
                    if verifier_kinds is not None
                    else self._route_verifier_kinds(semantic_target_id, observation)
                ),
                excluded_candidate_ids=excluded_candidate_ids,
            )
        except ValueError as exc:
            detail = str(exc)
            code = (
                ProposalRejectionCode.UNSUPPORTED_ACTION
                if "action_unsupported" in detail
                else ProposalRejectionCode.NO_BACKEND
            )
            raise ProposalRejected(code, detail) from exc

    def _available_executors(self, snapshot: UnifiedObservation) -> frozenset[str]:
        return frozenset(candidate.compatible_executor for candidate in snapshot.bindings)

    def _route_verifier_kinds(
        self,
        semantic_target_id: str,
        snapshot: UnifiedObservation,
    ) -> tuple[str, ...]:
        requirements = self.requirements.get(semantic_target_id)
        if requirements is None:
            target = next(
                (item for item in snapshot.targets if item.target_id == semantic_target_id),
                None,
            )
            source_ids = (
                tuple(
                    candidate.source_affordance_id
                    for candidate in snapshot.bindings
                    if candidate.semantic_target_id == target.target_id
                )
                if target is not None
                else ()
            )
            requirements = next(
                (self.requirements[item] for item in source_ids if item in self.requirements),
                self.requirements.get("*", ContractRequirements()),
            )
        return tuple(spec.kind for spec in requirements.verifier_plan)

    @staticmethod
    def _legacy_affordance(
        affordance_id: str,
        snapshot: BrowserSnapshot | PerceptionCapture,
    ) -> Affordance | None:
        return next(
            (item for item in snapshot.affordance_model.affordances if item.id == affordance_id),
            None,
        )


@dataclass(frozen=True)
class _SelectedSemanticAction:
    selection_id: str
    based_on_task_revision: int
    based_on_state_version: int
    snapshot_id: str
    subgoal: str
    action_kind: PlannerActionKind
    target_affordance_id: str
    destination_affordance_id: str
    parameters: dict[str, Any]
    requirement_refs: tuple[str, ...]
    effect_authorization_refs: tuple[str, ...]
    choice_role: str


@dataclass
class ActionContractBuilder:
    """Canonical contract owner.

    Selection/catalog/observation identities are checked before route
    materialization. The selected backend is a deterministic Runtime route over
    all current canonical candidates; no presentation field is consulted.
    """

    materializer: ActionContractMaterializer = field(
        default_factory=ActionContractMaterializer,
        repr=False,
    )

    @property
    def requirements(self):
        return self.materializer.requirements

    @property
    def unified_resolver(self):
        return self.materializer.unified_resolver

    def build(
        self,
        selection: ActionSelection,
        catalog: ActionChoiceCatalog,
        task_spec: TaskSpec,
        state: StateKernel,
        capture: PerceptionCapture,
        observation: UnifiedObservation,
    ) -> ActionContract:
        if selection.catalog_ref != catalog.ref:
            raise ValueError("selection does not bind the current Catalog")
        if selection.observation_ref != observation.epoch_id:
            raise ValueError("selection does not bind the current observation")
        if catalog.observation_ref != observation.epoch_id:
            raise ValueError("Catalog does not bind the current observation")
        if selection.task_revision != task_spec.revision or selection.state_version != state.version:
            raise ValueError("stale action selection authority")
        choice = catalog.get(selection.choice_id)
        if choice is None:
            raise ValueError("selected choice is not a Catalog member")
        semantic_action = _SelectedSemanticAction(
            selection_id=selection.choice_id,
            based_on_task_revision=selection.task_revision,
            based_on_state_version=selection.state_version,
            snapshot_id=selection.observation_ref,
            subgoal=selection.active_step_id,
            action_kind=choice.action_kind,
            target_affordance_id=choice.target_id,
            destination_affordance_id=choice.destination_id,
            parameters=dict(choice.parameters),
            requirement_refs=choice.requirement_refs,
            effect_authorization_refs=choice.effect_refs,
            choice_role=choice.role.value,
        )
        contract = self.materializer.build(
            semantic_action,
            task_spec,
            state,
            capture,
            observation,
        )
        candidate = contract.grounding_candidate
        route_reason = (
            f"canonical_candidate:{candidate.candidate_id}"
            if candidate is not None
            else f"canonical_backend:{contract.backend}"
        )
        runtime_signature, proof = rebuild_contract_authority(choice, task_spec, observation, contract)
        return replace(
            contract,
            choice_catalog_id=catalog.catalog_id,
            choice_catalog_digest=catalog.catalog_digest,
            selected_choice_id=selection.choice_id,
            observation_ref=observation.epoch_id,
            requirement_refs=choice.requirement_refs,
            effect_authorization_refs=choice.effect_refs,
            choice_role=choice.role.value,
            action_authority_proof=proof,
            runtime_effect_signature=runtime_signature,
            risk=proof.risk,
            route_reason=route_reason,
            contract_hash="",
        )
