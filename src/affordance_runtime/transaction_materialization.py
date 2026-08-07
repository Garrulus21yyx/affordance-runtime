"""Canonical committed-observation transaction materialization.

This module intentionally has no dependency on proposal-based contract
materializers.  Compatibility edges may project route-owner configuration into
this owner, never a partially built ActionContract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as dataclass_fields
from typing import Any, Mapping, Protocol

from affordance_runtime.action_choice_authority import authorize_runtime_signature
from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.action_contract_authority import rebuild_contract_authority
from affordance_runtime.action_effect_classifier import classify_action
from affordance_runtime.action_semantics import action_compatible
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.choice_contracts import ActionSelection
from affordance_runtime.contracts import ActionContract, GestureContractBinder, VerifierSpec
from affordance_runtime.effect_authority_contracts import AuthorityStatus
from affordance_runtime.execution_context import (
    RouteBinding,
    RunProvenanceManifest,
    deterministic_application_payload,
    digest_payload,
    ensure_secret_free,
)
from affordance_runtime.high_risk_effect_policy import policy_for_effect
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    ProposalRejected,
    ProposalRejectionCode,
    TaskPlanProgressTarget,
    UnifiedTargetResolver,
    bind_active_step_verifiers,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation


@dataclass(frozen=True)
class ActionContractDraft:
    """A complete but deliberately non-executable transaction draft."""

    contract: ActionContract
    route_binding: RouteBinding
    executable: bool = False


class CanonicalRouteEncoder(Protocol):
    """Edge-owned deterministic encoder; it carries no proposal materializer authority."""

    def encode_canonical_choice(
        self,
        choice: Any,
        task_spec: TaskSpec,
        state: StateKernel,
        capture: PerceptionCapture,
        affordance: Any,
    ) -> tuple[str, dict[str, Any], tuple[Any, ...]]: ...

    def verifier_kinds(self, target_id: str, observation: UnifiedObservation) -> tuple[str, ...]: ...


@dataclass
class ActionTransactionMaterializer:
    """Build and seal one transaction solely from the exact committed O1."""

    requirements: Mapping[str, ContractRequirements] = field(default_factory=dict)
    unified_resolver: UnifiedTargetResolver = field(default_factory=UnifiedTargetResolver)
    gesture_binder: GestureContractBinder = field(default_factory=GestureContractBinder)
    route_encoder: CanonicalRouteEncoder | None = field(default=None, repr=False)
    provenance_manifest: RunProvenanceManifest | None = None
    artifacts: ArtifactStore | None = field(default=None, repr=False)

    def build(
        self,
        selection: ActionSelection,
        catalog: ActionChoiceCatalog,
        task_spec: TaskSpec,
        state: StateKernel,
        capture: PerceptionCapture,
        observation: UnifiedObservation,
    ) -> ActionContract:
        committed = getattr(state, "current_observation_ref", None)
        if committed is None or committed.epoch_id != observation.epoch_id or committed.digest != observation.digest:
            raise ValueError("transaction materialization requires the exact committed observation")
        if (
            capture.observation.snapshot_id != observation.epoch_id
            or capture.observation.page_revision != observation.page_revision
            or capture.observation.environment_revision != observation.environment_revision
        ):
            raise ValueError("transaction materialization capture does not match the committed observation")
        surface = observation.live_surface_binding
        coordinate = observation.coordinate_binding
        descriptor = observation.capability_descriptor
        manifest = self.provenance_manifest
        if surface is None or coordinate is None or descriptor is None or manifest is None:
            raise ValueError("transaction materialization requires bound context, coordinate, capability, and provenance")
        if not surface.lease.current(surface):
            raise ValueError("transaction materialization requires a current SurfaceLease")
        if not coordinate.current_for(surface):
            raise ValueError("transaction coordinate binding is stale")
        if selection.catalog_ref != catalog.ref:
            raise ValueError("selection does not bind the current Catalog")
        if selection.observation_ref != observation.epoch_id or catalog.observation_ref != observation.epoch_id:
            raise ValueError("selection and Catalog must bind the committed observation")
        if selection.task_revision != task_spec.revision or selection.state_version != state.version:
            raise ValueError("stale action selection authority")
        choice = catalog.get(selection.choice_id)
        if choice is None:
            raise ValueError("selected choice is not a Catalog member")

        source_requirement_keys = tuple(
            item.source_affordance_id
            for item in observation.bindings
            if item.semantic_target_id == choice.target_id and item.source_affordance_id
        )
        requirements = self.requirements.get(choice.target_id)
        if requirements is None:
            requirements = next(
                (self.requirements[key] for key in source_requirement_keys if key in self.requirements),
                self.requirements.get("*", ContractRequirements()),
            )
        available_executors = frozenset(item.compatible_executor for item in observation.bindings)
        verifier_kinds = tuple(item.kind for item in requirements.verifier_plan)
        if self.route_encoder is not None:
            verifier_kinds = self.route_encoder.verifier_kinds(choice.target_id, observation)
        source_resolution = self.unified_resolver.resolve(
            choice.target_id,
            action=choice.action_kind,
            task_spec=task_spec,
            subgoal=selection.active_step_id,
            snapshot=capture,
            observation=observation,
            available_executors=available_executors,
            verifier_kinds=verifier_kinds,
            excluded_candidate_ids=state.excluded_candidates_for(choice.target_id),
        )
        source = source_resolution.route.selected_candidate
        source_affordance = source_resolution.source_affordance
        if not action_compatible(choice.action_kind, source_affordance.action):
            raise ProposalRejected(ProposalRejectionCode.UNSUPPORTED_ACTION, choice.action_kind.value)

        destination_resolution = None
        destination = None
        gesture_binding = None
        if choice.destination_id:
            destination_resolution = self.unified_resolver.resolve(
                choice.destination_id,
                action=choice.action_kind,
                task_spec=task_spec,
                subgoal=selection.active_step_id,
                snapshot=capture,
                observation=observation,
                available_executors=frozenset({source.compatible_executor}),
                verifier_kinds=verifier_kinds,
                excluded_candidate_ids=state.excluded_candidates_for(choice.destination_id),
            )
            destination = destination_resolution.route.selected_candidate
            if destination.compatible_executor != source.compatible_executor:
                raise ProposalRejected(ProposalRejectionCode.NO_BACKEND, "gesture endpoints do not share a route")
            gesture_binding = self.gesture_binder.bind(
                source_affordance,
                destination_resolution.source_affordance,
                selected_route=source.compatible_executor,
                observation=capture.observation,
                source_semantic_target_id=choice.target_id,
                source_candidate_id=source.candidate_id,
                source_fingerprint_key=source.fingerprint_key or source.candidate_id,
                destination_semantic_target_id=choice.destination_id,
                destination_candidate_id=destination.candidate_id,
                destination_fingerprint_key=destination.fingerprint_key or destination.candidate_id,
            )

        progress_target = None
        if (
            state.task_plan is not None
            and state.task_progress is not None
            and state.task_progress.active_step_id == selection.active_step_id
        ):
            progress_target = TaskPlanProgressTarget(
                state.task_plan.plan_id,
                state.task_plan.plan_version,
                selection.active_step_id,
                selection.state_version,
            )
        encoded_action = (
            source_affordance.action
            if source_affordance.action in descriptor.actions_for(source.compatible_executor)
            else "point_activate"
            if source.compatible_executor == "visual"
            and choice.action_kind == PlannerActionKind.ACTIVATE
            else choice.action_kind.value
        )
        encoded_parameters: dict[str, Any] | None = None
        encoded_verifiers = tuple(requirements.verifier_plan)
        if self.route_encoder is not None:
            encoded_action, encoded_parameters, encoded_verifiers = self.route_encoder.encode_canonical_choice(
                choice, task_spec, state, capture, source_affordance
            )
        verifier_plan = bind_active_step_verifiers(encoded_verifiers, state, progress_target=progress_target)
        if source.compatible_executor not in descriptor.supported_backends:
            raise ValueError("selected backend is not supported by the pinned executor descriptor")
        if encoded_action not in descriptor.actions_for(source.compatible_executor):
            raise ValueError("selected action is not supported by provider and adapter")
        if not action_compatible(choice.action_kind, encoded_action):
            raise ValueError("encoded action changes the authorized semantic action family")

        named_parameters = dict(choice.parameters)
        ensure_secret_free(named_parameters)
        parameters = encoded_parameters if encoded_parameters is not None else dict(choice.parameters)
        if encoded_parameters is None and choice.action_kind == PlannerActionKind.TYPE_TEXT:
            if "text" not in parameters:
                raise ProposalRejected(ProposalRejectionCode.UNREQUESTED_EFFECT, "type_text requires text")
            parameters = {"value": parameters["text"]}
        elif encoded_parameters is None and choice.action_kind == PlannerActionKind.SELECT_OPTION:
            parameters = {"value": parameters["option"]}
        elif encoded_parameters is None and choice.action_kind == PlannerActionKind.PRESS_KEY:
            parameters = {"key": parameters["key"]}
        if encoded_action == "download" and not parameters.get("destination_dir"):
            if self.artifacts is None:
                raise ValueError("download transaction materialization requires an ArtifactStore")
            parameters["destination_dir"] = str(
                self.artifacts.run_dir(task_spec.task_id) / "downloads"
            )
        ensure_secret_free(source_affordance.locator)
        ensure_secret_free(parameters)
        runtime_signature = classify_action(
            observation,
            target_id=choice.target_id,
            destination_id=choice.destination_id,
            action_kind=choice.action_kind.value,
            parameters=named_parameters,
            candidate=source,
            destination_candidate=destination,
        )
        proof = authorize_runtime_signature(
            task_spec=task_spec,
            step=None,
            signature=runtime_signature,
            requirement_refs=choice.requirement_refs,
            choice_role=choice.role,
        )
        if proof.status != AuthorityStatus.ALLOW:
            raise ValueError(f"encoded action binding is not authorized: {proof.reason_code}")
        catalog_proof = choice.action_authority_proof
        if catalog_proof is None or catalog_proof.authorization_scope_digest != proof.authorization_scope_digest:
            raise ValueError("encoded action authority scope differs from Catalog authority proof")
        high_risk_policy = policy_for_effect(runtime_signature.effect_class, runtime_signature.operation_ref)
        if high_risk_policy is not None:
            verifier_plan = (
                *verifier_plan,
                *(
                    VerifierSpec(kind, runtime_signature.operation_ref or "", "clear")
                    for kind in high_risk_policy.required_collateral_verifiers
                    if not any(item.kind == kind for item in verifier_plan)
                ),
            )
        actual_target = source.candidate_id
        actual_destination = destination.candidate_id if destination is not None else ""
        route_named_parameters = parameters
        application_payload = deterministic_application_payload(
            action=encoded_action,
            target_id=actual_target,
            destination_id=actual_destination,
            named_parameters=route_named_parameters,
        )
        ensure_secret_free(application_payload)
        input_refs = tuple(
            sorted(
                item.binding_id
                for item in task_spec.inputs
                if item.field in named_parameters and named_parameters[item.field] == item.value
            )
        )
        route_binding = RouteBinding(
            backend=source.compatible_executor,
            provider_id=descriptor.provider_id,
            tool_schema_digest=descriptor.tool_schema_digest,
            adapter_id=descriptor.adapter_id,
            adapter_version=descriptor.adapter_version,
            encoder_id=f"{source.compatible_executor}:canonical-action-encoder",
            encoder_version="p4-c3@v1",
            route_policy_digest=digest_payload(
                {"requirements": choice.requirement_refs, "effects": choice.effect_refs, "scope": proof.authorization_scope_digest}
            ),
            action=encoded_action,
            target_id=actual_target,
            destination_id=actual_destination,
            target_locator_ref=digest_payload(source_affordance.locator),
            destination_locator_ref=(
                digest_payload(destination_resolution.source_affordance.locator)
                if destination_resolution is not None
                else ""
            ),
            input_binding_refs=input_refs,
            named_parameters=route_named_parameters,
            application_payload=application_payload,
            payload_digest=digest_payload(application_payload),
            observation_digest=observation.digest,
            surface_binding_digest=surface.digest,
            coordinate_transform_digest=coordinate.transform_digest,
            provenance_digest=manifest.digest,
        )
        required_capabilities = tuple(dict.fromkeys((*requirements.required_capabilities, *task_spec.capability_ceiling)))
        idempotency_key = requirements.idempotency_key
        if not idempotency_key and choice.action_kind in {PlannerActionKind.TYPE_TEXT, PlannerActionKind.SELECT_OPTION}:
            idempotency_key = (
                f"task:{task_spec.task_id}:revision:{task_spec.revision}:"
                f"target:{choice.target_id}:parameters:{sorted(named_parameters.items())}"
            )
        contract = ActionContract(
            id=f"contract_{source.candidate_id.replace(':', '_')}_{observation.epoch_id}",
            intent=selection.active_step_id or task_spec.objective,
            affordance_id=choice.target_id,
            action=encoded_action,
            backend=source.compatible_executor,
            environment_revision=observation.environment_revision,
            locator=dict(source_affordance.locator),
            choice_catalog_id=catalog.catalog_id,
            choice_catalog_digest=catalog.catalog_digest,
            selected_choice_id=choice.choice_id,
            observation_ref=observation.epoch_id,
            requirement_refs=choice.requirement_refs,
            effect_authorization_refs=choice.effect_refs,
            choice_role=choice.role.value,
            action_authority_proof=proof,
            runtime_effect_signature=runtime_signature,
            route_reason=f"canonical_candidate:{source.candidate_id}",
            grounding_candidate=source,
            route_plan=source_resolution.route,
            gesture_binding=gesture_binding,
            parameters=parameters,
            expected_effects=list(requirements.expected_effects),
            verifier_plan=list(verifier_plan),
            required_capabilities=list(required_capabilities),
            risk=proof.risk,
            idempotency_key=idempotency_key,
            compensation=requirements.compensation,
            timeout_ms=requirements.timeout_ms,
            run_id=task_spec.task_id,
            snapshot_id=observation.epoch_id,
            page_revision=observation.page_revision,
            target_fingerprint=source.target_fingerprint,
            target_fingerprint_key=source.fingerprint_key or source.candidate_id,
            observed_at_s=source_affordance.lease.issued_at_s,
            expires_at_s=source.expires_at_s or source_affordance.lease.expires_at_s,
        )
        draft = ActionContractDraft(contract, route_binding)
        if draft.executable:
            raise AssertionError("ActionContractDraft must never be executable")
        sealed = ActionContract(
            **{
                item.name: getattr(draft.contract, item.name)
                for item in dataclass_fields(ActionContract)
                if item.name
                not in {
                    "contract_hash",
                    "transaction_seal",
                    "route_binding",
                    "live_surface_binding",
                    "coordinate_binding",
                    "provenance_manifest",
                }
            },
            route_binding=draft.route_binding,
            live_surface_binding=surface,
            coordinate_binding=coordinate,
            provenance_manifest=manifest,
        )
        rebuilt_signature, rebuilt_proof = rebuild_contract_authority(choice, task_spec, observation, sealed)
        if rebuilt_proof != sealed.action_authority_proof or rebuilt_signature != sealed.runtime_effect_signature:
            raise ValueError("sealed transaction authority drift")
        return sealed
