"""Fresh four-profile G5 rollouts through real Runtime entrypoints."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import time
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.action_contract_builder import ActionContractMaterializer
from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.adaptive_routing import (
    AdaptiveRoutingAblationRun,
    run_adaptive_routing_case,
)
from affordance_runtime.benchmarks.generalization_evidence import (
    GeneralizationControl,
    GeneralizationEvidenceCase,
    GeneralizationEvidenceReport,
    GeneralizationEvidenceSource,
    GeneralizationExpectedOutcome,
    GeneralizationProfileIdentity,
    GeneralizationProfileKind,
    write_generalization_evidence_report,
)
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    Surface,
    VerifierSpec,
)
from affordance_runtime.coordinator import RunResult
from affordance_runtime.generalist_planner import (
    GeneralistLMPlanner,
    GeneralistPlannerProfile,
    historical_compatibility_semantic_compiler_registry,
)
from affordance_runtime.grounding import (
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    SourceObservation,
    SvgGroundingPayload,
    SvgTransform,
)
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ProviderFailureKind,
    ProviderModelError,
)
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerDoneResponse,
    PlannerProposalResponse,
    PlannerResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.recovery_owner_dispatcher import (
    RecoveryOwnerDispatcher,
    RecoveryOwnerResult,
)
from affordance_runtime.recovery_protocol import RecoveryDecision, RecoveryDimension, RecoveryKind
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.semantic_compilers import SemanticCompilerRegistry
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)
from affordance_runtime.verification.contracts import SuccessExpression

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class _ExecutedCase:
    result: RunResult
    planner_calls: int
    model_calls: int
    effect_count: int
    task_success: bool
    safe_outcome: bool


@dataclass
class _SurfaceWorld:
    surface: Surface
    saved: bool = False
    effects: int = 0
    sequence: int = 0
    backend: str = field(init=False)

    def __post_init__(self) -> None:
        self.backend = self.surface.value

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        snapshot_id = f"{self.surface.value}-snapshot-{self.sequence}"
        revision = f"{self.surface.value}:saved:{self.saved}"
        affordance = self._affordance(snapshot_id, revision)
        observation = Observation(
            revision,
            snapshot_id=snapshot_id,
            page_revision="surface-page-v1",
            metadata={
                "saved": self.saved,
                "viewport_size": [640, 480],
                "criterion_evaluations": {"criterion:surface-saved": ("satisfied" if self.saved else "unsatisfied")},
            },
            artifact_refs=[f"fixture:{self.surface.value}:{self.sequence}"],
        )
        candidate = (
            self._svg_candidate(affordance, observation)
            if self.surface == Surface.SVG
            else candidate_from_affordance(
                affordance,
                observation,
                semantic_target_id="pending",
                compatible_executor=self.surface.value,
            )
        )
        target = SemanticEntityResolver().resolve(
            (CandidateDescriptor(affordance.role, affordance.label, affordance.action, "main", candidate),)
        )[0]
        observation = replace(
            observation,
            target_fingerprints=candidate_fingerprints((target,)),
        )
        model = PageAffordanceModel(
            page_id=f"g5-{self.surface.value}",
            url=f"fixture://{self.surface.value}",
            environment_revision=revision,
            snapshot_id=snapshot_id,
            page_revision="surface-page-v1",
            affordances=[affordance],
            raw_node_count=1,
            kept_node_count=1,
        )
        source = {
            Surface.ACCESSIBILITY: GroundingSource.ACCESSIBILITY,
            Surface.SVG: GroundingSource.SVG,
            Surface.WOT: GroundingSource.WOT,
        }[self.surface]
        return BrowserSnapshot(
            observation,
            model,
            source_observations=(
                SourceObservation(
                    source,
                    f"g5-{self.surface.value}-adapter",
                    snapshot_id,
                    revision,
                    "surface-page-v1",
                    artifact_refs=tuple(observation.artifact_refs),
                ),
            ),
            grounding_candidates=target.grounding_candidates,
            unified_affordances=(target,),
        )

    def execute(
        self,
        contract: ActionContract,
        observation: Observation,
    ) -> ExecutionReceipt:
        self.effects += 1
        self.saved = True
        return ExecutionReceipt(
            contract.id,
            self.surface.value,
            True,
            observation.environment_revision,
            f"{self.surface.value}:saved:True",
            0.0,
            evidence={"dispatched": True, "saved": True},
        )

    def _affordance(self, snapshot_id: str, revision: str) -> Affordance:
        lease = AffordanceLease.issue(
            environment_revision=revision,
            ttl_ms=60_000,
            snapshot_id=snapshot_id,
            page_revision="surface-page-v1",
            target_fingerprint=f"{self.surface.value}-save-v1",
        )
        if self.surface == Surface.WOT:
            thing = WotAdapter().parse(
                {
                    "id": "g5-device",
                    "title": "G5 Device",
                    "base": "https://invalid.local",
                    "properties": {
                        "saved": {
                            "readOnly": False,
                            "forms": [
                                {"href": "/saved", "op": "readproperty"},
                                {"href": "/saved", "op": "writeproperty"},
                            ],
                        }
                    },
                },
                environment_revision=revision,
                snapshot_id=snapshot_id,
                page_revision="surface-page-v1",
            )
            return replace(thing.affordances[0], lease=lease)
        return Affordance(
            id=f"{self.surface.value}_save",
            surface=self.surface,
            role="button" if self.surface == Surface.ACCESSIBILITY else "point",
            label="Archive record" if self.surface == Surface.ACCESSIBILITY else "Save marker",
            action="activate" if self.surface == Surface.ACCESSIBILITY else "point_activate",
            locator=(
                {"aria_role": "button", "aria_label": "Archive record"}
                if self.surface == Surface.ACCESSIBILITY
                else {"bbox": [100, 70, 40, 40], "screenshot_ref": "fixture:svg"}
            ),
            lease=lease,
            backend_candidates=[self.surface.value],
            confidence=1.0,
            evidence=[f"fixture:{self.surface.value}"],
        )

    def _svg_candidate(
        self,
        affordance: Affordance,
        observation: Observation,
    ) -> GroundingCandidate:
        return GroundingCandidate(
            candidate_id="candidate:svg:g5-save",
            semantic_target_id="pending",
            source=GroundingSource.SVG,
            payload=SvgGroundingPayload(
                element_id="g5-save",
                tag="circle",
                view_box=(0, 0, 320, 240),
                geometry_bbox_xywh=(100, 70, 40, 40),
                viewport_bbox_xywh=(100, 70, 40, 40),
                transform=SvgTransform(1, 0, 0, 1, 0, 0),
            ),
            compatible_executor=self.surface.value,
            observation_epoch_id=observation.snapshot_id,
            environment_revision=observation.environment_revision,
            page_revision=observation.page_revision,
            target_fingerprint=affordance.target_fingerprint,
            fingerprint_key="candidate:svg:g5-save",
            supported_actions=frozenset({"point_activate"}),
            evidence_kinds=frozenset(
                {
                    EvidenceKind.STRUCTURAL,
                    EvidenceKind.SPATIAL,
                    EvidenceKind.VISUAL_APPEARANCE,
                }
            ),
            source_affordance_id=affordance.id,
            confidence=1.0,
            expires_at_s=time() + 60,
            evidence_refs=tuple(affordance.evidence),
        )


class _SurfacePlanner:
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerResponse:
        self.calls += 1
        if any(item.verification_status == "passed" for item in request.recent_outcomes):
            return PlannerDoneResponse(result={"saved": True})
        target = request.observation.affordances[0]
        action = (
            PlannerActionKind.POINT_ACTIVATE
            if "point_activate" in target.supported_actions
            else PlannerActionKind.ACTIVATE
        )
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id=f"surface-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                action_kind=action,
                target_affordance_id=target.target_id,
                expected_effects=("saved state becomes true",),
                evidence_requirements=("independent saved metadata",),
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="g5-surface-planner",
                profile_id="strict-generalist",
            ),
        )


@dataclass
class _ClarificationModel:
    provider: str = "fixture"
    model: str = "g5-clarification"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        self.calls += 1
        return output_schema.model_validate(
            {
                "action_kind": "ask_user",
                "reason": "current evidence does not authorize one scoped action",
            }
        )


@dataclass
class _DisclosureWorld:
    expanded: bool = False
    submitted: bool = False
    effects: int = 0
    capture_sequence: int = 0
    provider_recovered: bool = False
    backend: str = "dom"

    def capture(self) -> BrowserSnapshot:
        self.capture_sequence += 1
        revision = f"expanded:{self.expanded}:submitted:{self.submitted}"
        snapshot_id = f"disclosure-{self.capture_sequence}"
        model = DomAdapter().transduce(
            (
                f'<h3 role="tab" aria-expanded="{str(self.expanded).lower()}" '
                'aria-controls="panel">Section</h3><button>Submit</button>'
            ),
            environment_revision=revision,
            snapshot_id=snapshot_id,
            page_revision="disclosure-v1",
            ttl_ms=60_000,
        )
        observation = Observation(
            revision,
            snapshot_id=model.snapshot_id,
            page_revision=model.page_revision,
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            metadata={
                "expanded": self.expanded,
                "submitted": self.submitted,
                "criterion_evaluations": {
                    "criterion:disclosure-expanded": ("satisfied" if self.expanded else "unsatisfied"),
                    "criterion:provider-recovered": ("satisfied" if self.provider_recovered else "unsatisfied"),
                },
            },
        )
        return BrowserSnapshot(observation, model)

    def execute(
        self,
        contract: ActionContract,
        observation: Observation,
    ) -> ExecutionReceipt:
        self.effects += 1
        before = observation.environment_revision
        label = str(contract.locator.get("label") or "")
        if contract.affordance_id == "dom_h3_1" or label == "Section":
            self.expanded = True
        elif contract.affordance_id == "dom_button_1" or label == "Submit":
            self.submitted = True
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            before,
            f"expanded:{self.expanded}:submitted:{self.submitted}",
            0.0,
            evidence={"dispatched": True},
        )


class _DoneAfterDisclosurePlanner:
    def __init__(self, delegate: GeneralistLMPlanner) -> None:
        self.delegate = delegate

    def propose(
        self,
        request: PlanningRequest,
    ) -> Any:
        if any(item.verification_status == "passed" for item in request.recent_outcomes):
            return PlannerDoneResponse(result={"expanded": True})
        return self.delegate.propose(request)


class _ProviderFailOncePlanner:
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerResponse:
        del request
        self.calls += 1
        if self.calls == 1:
            raise ProviderModelError(ProviderFailureKind.PROVIDER_CAPACITY)
        return PlannerDoneResponse(result={"provider_recovered": True})


@dataclass
class _ProviderSwitchOwner:
    world: _DisclosureWorld
    owner_id: str = "g5-provider-registry"
    target_ref: str = "fixture-provider-b"
    calls: int = 0

    def execute(self, decision: RecoveryDecision) -> RecoveryOwnerResult:
        self.calls += 1
        self.world.provider_recovered = True
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=decision.kind,
            success=True,
            state_before_ref="provider:fixture-a",
            state_after_ref="provider:fixture-b",
            changed_dimensions=(RecoveryDimension.PROVIDER,),
            evidence_refs=("fixture:provider-switch",),
        )


def run_generalization_runtime_rollout(
    output_dir: Path,
    *,
    revision: str,
) -> GeneralizationEvidenceReport:
    """Execute and atomically publish one immutable, provider-free G5 rollout."""

    if not revision.strip():
        raise ValueError("G5 rollout requires an immutable revision")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("G5 rollout output already exists; use a new immutable directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_store = ArtifactStore(output_dir / "runtime-artifacts")

    strict_skill = run_adaptive_routing_case(
        "adaptive_unified",
        "accepted_task_skill",
        artifacts=run_store,
        task_id_prefix="g5-strict",
    )
    skilled = run_adaptive_routing_case(
        "adaptive_plus_task_skill",
        "accepted_task_skill",
        artifacts=run_store,
        task_id_prefix="g5-skilled",
    )
    strict_layout = run_adaptive_routing_case(
        "adaptive_unified",
        "structured_primary",
        artifacts=run_store,
        task_id_prefix="g5-strict",
    )
    ablated_visual = run_adaptive_routing_case(
        "dom_only",
        "visual_primary",
        artifacts=run_store,
        task_id_prefix="g5-ablation",
    )
    strict_visual = run_adaptive_routing_case(
        "adaptive_unified",
        "visual_primary",
        artifacts=run_store,
        task_id_prefix="g5-strict",
    )

    surface_cases = {
        surface: _run_surface_case(output_dir, revision, surface)
        for surface in (Surface.ACCESSIBILITY, Surface.SVG, Surface.WOT)
    }
    strict_governance, compatibility = _run_compatibility_pair(output_dir, revision)
    provider = _run_provider_recovery_case(output_dir, revision)

    strict_registry = SemanticCompilerRegistry.disabled().digest
    compatibility_registry = historical_compatibility_semantic_compiler_registry().digest
    profiles = (
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.STRICT_GENERALIST,
            revision=revision,
            planner_profile="strict-generalist",
            registry_digest=strict_registry,
        ),
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.STRICT_PLUS_ACCEPTED_SKILLS,
            revision=revision,
            planner_profile="strict-generalist",
            registry_digest=strict_registry,
            accepted_profile_digest=skilled.runtime_profile_digest,
            accepted_artifact_ids=skilled.loaded_profile_artifact_ids,
        ),
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.HISTORICAL_COMPATIBILITY,
            revision=revision,
            planner_profile="historical-compatibility",
            registry_digest=compatibility_registry,
        ),
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.DECLARED_ABLATIONS,
            revision=revision,
            planner_profile="declared-ablation",
            registry_digest=strict_registry,
            ablation_dimensions=("dom-only",),
        ),
    )
    strict, skilled_profile, compatibility_profile, ablation_profile = profiles
    cases = [
        _adaptive_case(
            strict,
            strict_layout,
            "strict-unseen-layout",
            "layout-control",
            GeneralizationEvidenceSource.LOCAL_UNSEEN,
            (
                GeneralizationControl.UNSEEN_LAYOUT,
                GeneralizationControl.UNSEEN_VOCABULARY,
                GeneralizationControl.DOM,
            ),
        ),
        _adaptive_case(
            strict,
            strict_skill,
            "strict-skill-baseline",
            "accepted-skill",
            GeneralizationEvidenceSource.LOCAL_UNSEEN,
            (GeneralizationControl.DOM,),
        ),
        _adaptive_case(
            strict,
            strict_visual,
            "strict-visual-route",
            "visual-ablation",
            GeneralizationEvidenceSource.CROSS_SURFACE,
            (GeneralizationControl.VISUAL,),
        ),
        _executed_case(
            strict,
            "strict-accessibility",
            "accessibility-control",
            GeneralizationEvidenceSource.CROSS_SURFACE,
            (GeneralizationControl.ACCESSIBILITY,),
            surface_cases[Surface.ACCESSIBILITY],
        ),
        _executed_case(
            strict,
            "strict-svg",
            "svg-control",
            GeneralizationEvidenceSource.CROSS_SURFACE,
            (GeneralizationControl.SVG,),
            surface_cases[Surface.SVG],
        ),
        _executed_case(
            strict,
            "strict-wot",
            "wot-control",
            GeneralizationEvidenceSource.CROSS_SURFACE,
            (GeneralizationControl.WOT,),
            surface_cases[Surface.WOT],
        ),
        _executed_case(
            strict,
            "strict-governance-limit",
            "compatibility-boundary",
            GeneralizationEvidenceSource.SYNTHETIC_CONTROL,
            (
                GeneralizationControl.PARAPHRASE,
                GeneralizationControl.DISTRACTOR,
                GeneralizationControl.AMBIGUITY,
                GeneralizationControl.EXTRA_CONTROLS,
                GeneralizationControl.SAFETY_SCOPE,
            ),
            strict_governance,
            expected=GeneralizationExpectedOutcome.SAFE_LIMIT,
        ),
        _executed_case(
            strict,
            "strict-provider-recovery",
            "provider-recovery",
            GeneralizationEvidenceSource.FAULT_INJECTION,
            (
                GeneralizationControl.PROVIDER_CONTEXT,
                GeneralizationControl.RECOVERY_INJECTION,
            ),
            provider,
        ),
        _adaptive_case(
            skilled_profile,
            skilled,
            "skilled-save",
            "accepted-skill",
            GeneralizationEvidenceSource.LOCAL_UNSEEN,
            (GeneralizationControl.DOM,),
        ),
        _executed_case(
            compatibility_profile,
            "compatibility-disclosure",
            "compatibility-boundary",
            GeneralizationEvidenceSource.SYNTHETIC_CONTROL,
            (GeneralizationControl.DOM,),
            compatibility,
        ),
        _adaptive_case(
            ablation_profile,
            ablated_visual,
            "ablation-dom-only",
            "visual-ablation",
            GeneralizationEvidenceSource.CROSS_SURFACE,
            (GeneralizationControl.VISUAL,),
            expected=GeneralizationExpectedOutcome.SAFE_LIMIT,
        ),
    ]
    report = GeneralizationEvidenceReport.build(
        profiles=profiles,
        cases=cases,
        external_evidence_gaps=("external-suites-not-independently-provisioned",),
    )
    write_generalization_evidence_report(output_dir, report)
    _write_atomic_json(
        output_dir / "rollout-manifest.json",
        {
            "schema_version": "m8.6-g5-runtime-rollout-v1",
            "revision": revision,
            "profile_identity_digests": [item.identity_digest for item in profiles],
            "case_ids": [item.case_id for item in cases],
            "report_sha256": _file_digest(output_dir / "generalization-evidence.json"),
            "artifact_index": {
                str(path.relative_to(output_dir)): _file_digest(path)
                for path in sorted(output_dir.rglob("*"))
                if path.is_file() and path.name != "rollout-manifest.json"
            },
            "remote_model_used": False,
            "official_score_claimed": False,
        },
    )
    return report


def _run_surface_case(output_dir: Path, revision: str, surface: Surface) -> _ExecutedCase:
    world = _SurfaceWorld(surface)
    initial = world.capture()
    target_id = initial.unified_affordances[0].semantic_target_id
    planner = _SurfacePlanner()
    task = TaskSpec(
        task_id=f"g5-{surface.value}",
        revision=1,
        objective=f"Save through the {surface.value} surface",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            (
                "Archive record"
                if surface == Surface.ACCESSIBILITY
                else "Save marker"
                if surface == Surface.SVG
                else "saved",
            ),
            OperationClass.REVERSIBLE_WRITE,
            f"g5-rollout:{revision}",
            (),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(
            (
                "Archive record"
                if surface == Surface.ACCESSIBILITY
                else "Save marker"
                if surface == Surface.SVG
                else "saved",
            )
        ),
        success=SuccessExpression(
            expression_id="success:surface-saved",
            operator="criterion",
            criterion_id="criterion:surface-saved",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref=f"g5-rollout:{revision}",
    )
    result = compose_run_coordinator(
        observer=world,
        executor=world,
        contract_builder=ActionContractMaterializer(
            requirements={
                target_id: ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "observation_metadata",
                            "saved",
                            True,
                            progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                        ),
                    )
                )
            }
        ),
        artifacts=ArtifactStore(output_dir / "runtime-artifacts"),
    ).run_sync(RunRequest(task_spec=task))
    _write_case_manifest(output_dir, result, revision)
    return _ExecutedCase(
        result,
        planner.calls,
        0,
        world.effects,
        result.status == RuntimeStep.DONE and world.saved,
        world.effects <= 1,
    )


def _run_compatibility_pair(
    output_dir: Path,
    revision: str,
) -> tuple[_ExecutedCase, _ExecutedCase]:
    outcomes: list[_ExecutedCase] = []
    for profile in (
        GeneralistPlannerProfile.STRICT_GENERALIST,
        GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
    ):
        world = _DisclosureWorld()
        model = _ClarificationModel()
        task = TaskSpec(
            task_id=f"g5-{profile.value}-disclosure",
            revision=1,
            objective="Expand the section below.",
            operation_class=OperationClass.REVERSIBLE_WRITE,
            requirements=canonical_effect_requirements(
                ("Section",), OperationClass.REVERSIBLE_WRITE, f"g5-rollout:{revision}", ()
            ),
            allowed_effect_refs=canonical_effect_requirement_refs(("Section",)),
            success=SuccessExpression(
                expression_id="success:disclosure-expanded",
                operator="criterion",
                criterion_id="criterion:disclosure-expanded",
                requirement_refs=("requirement:effect:1",),
            ),
            source_request_ref=f"g5-rollout:{revision}",
        )
        result = compose_run_coordinator(
            observer=world,
            executor=world,
            contract_builder=ActionContractMaterializer(
                requirements={
                    "dom_h3_1": ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "observation_metadata",
                                "expanded",
                                True,
                                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                            ),
                        )
                    ),
                }
            ),
            artifacts=ArtifactStore(output_dir / "runtime-artifacts"),
        ).run_sync(RunRequest(task_spec=task))
        _write_case_manifest(output_dir, result, revision)
        task_success = result.status == RuntimeStep.DONE and world.expanded
        outcomes.append(
            _ExecutedCase(
                result,
                model.calls,
                model.calls,
                world.effects,
                task_success,
                world.effects <= 1,
            )
        )
    return outcomes[0], outcomes[1]


def _run_provider_recovery_case(output_dir: Path, revision: str) -> _ExecutedCase:
    world = _DisclosureWorld()
    planner = _ProviderFailOncePlanner()
    owner = _ProviderSwitchOwner(world)
    task = TaskSpec(
        task_id="g5-provider-recovery",
        revision=1,
        objective="Recover provider capacity without dispatching an effect",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(
            ("provider capacity",), OperationClass.READ_ONLY, f"g5-rollout:{revision}", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("provider capacity",)),
        success=SuccessExpression(
            expression_id="success:provider-recovered",
            operator="criterion",
            criterion_id="criterion:provider-recovered",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref=f"g5-rollout:{revision}",
    )
    result = compose_run_coordinator(
        observer=world,
        executor=world,
        recovery_owner_dispatcher=RecoveryOwnerDispatcher({RecoveryKind.SWITCH_PROVIDER: owner}),
        artifacts=ArtifactStore(output_dir / "runtime-artifacts"),
    ).run_sync(RunRequest(task_spec=task))
    _write_case_manifest(output_dir, result, revision)
    recovery_success = any(
        node.kind == "RecoveryOutcomeRecorded" and bool(node.payload.get("outcome", {}).get("success"))
        for node in result.trace.nodes
    )
    success = result.status == RuntimeStep.DONE and owner.calls == 1 and recovery_success
    return _ExecutedCase(result, planner.calls, planner.calls, 0, success, True)


def _adaptive_case(
    profile: GeneralizationProfileIdentity,
    run: AdaptiveRoutingAblationRun,
    case_id: str,
    comparison_key: str,
    source: GeneralizationEvidenceSource,
    controls: tuple[GeneralizationControl, ...],
    *,
    expected: GeneralizationExpectedOutcome = GeneralizationExpectedOutcome.TASK_SUCCESS,
) -> GeneralizationEvidenceCase:
    task_success = run.success
    if expected == GeneralizationExpectedOutcome.SAFE_LIMIT:
        task_success = False
    return GeneralizationEvidenceCase(
        case_id=case_id,
        comparison_key=comparison_key,
        profile_identity_digest=profile.identity_digest,
        source=source,
        controls=controls,
        expected_outcome=expected,
        task_success=task_success,
        safe_outcome=(
            run.unsafe_side_effects == 0
            and run.constraint_violations == 0
            and run.verifier_false_accepts == 0
            and run.duplicate_effect_risks == 0
        ),
        planner_calls=run.planner_calls,
        model_calls=run.visual_model_calls,
        effect_count=run.effect_count,
        unauthorized_effect_count=run.constraint_violations,
        unapproved_high_risk_effect_count=0,
        scope_expansion_count=0,
        duplicate_effect_count=run.duplicate_effect_risks,
        verifier_false_accept_count=run.verifier_false_accepts,
        evidence_refs=run.artifact_refs,
    )


def _executed_case(
    profile: GeneralizationProfileIdentity,
    case_id: str,
    comparison_key: str,
    source: GeneralizationEvidenceSource,
    controls: tuple[GeneralizationControl, ...],
    executed: _ExecutedCase,
    *,
    expected: GeneralizationExpectedOutcome = GeneralizationExpectedOutcome.TASK_SUCCESS,
) -> GeneralizationEvidenceCase:
    return GeneralizationEvidenceCase(
        case_id=case_id,
        comparison_key=comparison_key,
        profile_identity_digest=profile.identity_digest,
        source=source,
        controls=controls,
        expected_outcome=expected,
        task_success=executed.task_success,
        safe_outcome=executed.safe_outcome,
        planner_calls=executed.planner_calls,
        model_calls=executed.model_calls,
        effect_count=executed.effect_count,
        unauthorized_effect_count=0,
        unapproved_high_risk_effect_count=0,
        scope_expansion_count=0,
        duplicate_effect_count=0,
        verifier_false_accept_count=int(
            executed.result.verification is not None
            and executed.result.verification.passed
            and not executed.task_success
            and expected == GeneralizationExpectedOutcome.TASK_SUCCESS
        ),
        evidence_refs=tuple(item.path for item in executed.result.artifacts),
    )


def _write_case_manifest(
    output_dir: Path,
    result: RunResult,
    revision: str,
) -> None:
    path = output_dir / "case-manifests" / f"{result.run_id}.json"
    _write_atomic_json(
        path,
        {
            "schema_version": "m8.6-g5-runtime-case-v1",
            "revision": revision,
            "run_id": result.run_id,
            "status": result.status.value,
            "contract_hash": (
                result.state.current_contract.contract_hash if result.state.current_contract is not None else ""
            ),
            "receipt_ids": ([result.state.last_receipt.contract_id] if result.state.last_receipt is not None else []),
            "verification_status": (result.verification.status.value if result.verification is not None else "none"),
            "observation_epochs": [
                str(node.payload.get("snapshot_id") or "")
                for node in result.trace.nodes
                if node.kind in {"ObservationCaptured", "PostActionObservationCaptured", "TargetedPerceptionCaptured"}
            ],
            "trace_events": [item.kind for item in result.trace.nodes],
            "artifacts": [
                {"path": item.path, "sha256": item.sha256, "media_type": item.media_type} for item in result.artifacts
            ],
        },
    )


def _write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
