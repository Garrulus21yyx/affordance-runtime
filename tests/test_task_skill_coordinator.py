import hashlib
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.criteria import (
    criterion_id,
    evidence_requirement_id,
    skill_step_owner_id,
)
from affordance_runtime.evolution import (
    AcceptedProfileLoader,
    CandidateRuntimeProfile,
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
)
from affordance_runtime.grounding import GroundingSource, SourceObservation
from affordance_runtime.harness_learning import (
    CanonicalSemanticTraceExtractor,
    CanonicalTaskSkillPipeline,
    TraceMiningContext,
)
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerClarificationResponse,
    PlannerDoneResponse,
    PlannerProposalResponse,
)
from affordance_runtime.planning_request import PlanningRequest, thaw_request_mapping
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import IntentEntity, OperationClass, TaskSpec
from affordance_runtime.task_skills import (
    AcceptedTaskSkillRuntime,
    SemanticTargetQuery,
    SkillParameter,
    SkillParameterType,
    SkillStep,
    TaskSkillPayload,
    TaskSkillReplayEvidence,
    TaskSkillReplayGate,
    TaskSkillTrigger,
    quarantine_task_skill,
)
from affordance_runtime.trace import JsonlTraceWriter
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="task-skill-test-system2",
)


@dataclass
class ProfileWorld:
    name: str = ""
    email: str = ""


class ProfileObserver:
    def __init__(
        self,
        world: ProfileWorld,
        *,
        include_name: bool = True,
        variant: str = "original",
    ) -> None:
        self.world = world
        self.include_name = include_name
        self.variant = variant
        self.sequence = 0
        probe = self._snapshot(0)
        self.target_ids = {item.label: item.semantic_target_id for item in probe.unified_affordances}

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        return self._snapshot(self.sequence)

    def _snapshot(self, sequence: int) -> BrowserSnapshot:
        controls = []
        suffix = {"original": "", "family": "-field", "heldout": "-control"}.get(
            self.variant,
            "",
        )
        if self.include_name:
            controls.append(f'<input id="name{suffix}" placeholder="Name" value="{self.world.name}">')
        controls.append(f'<input id="email{suffix}" placeholder="Email" value="{self.world.email}">')
        if self.variant == "heldout":
            controls.reverse()
            markup = "<section><div>Account profile</div>" + "".join(controls) + "</section>"
        elif self.variant == "family":
            markup = "<form><fieldset>" + "".join(controls) + "</fieldset></form>"
        else:
            markup = "<main>" + "".join(controls) + "</main>"
        environment_revision = f"rev:{self.world.name}:{self.world.email}"
        snapshot_id = f"snapshot-{sequence}"
        model = DomAdapter().transduce(
            markup,
            environment_revision=environment_revision,
            snapshot_id=snapshot_id,
            page_revision="page-1",
            ttl_ms=60_000,
        )
        observation = Observation(
            environment_revision,
            snapshot_id=snapshot_id,
            page_revision="page-1",
            metadata={"profile_name": self.world.name, "profile_email": self.world.email},
        )
        descriptors = tuple(
            CandidateDescriptor(
                item.role,
                item.label,
                item.action,
                "profile-form",
                candidate_from_affordance(
                    item,
                    observation,
                    semantic_target_id="pending",
                    compatible_executor="dom",
                ),
            )
            for item in model.affordances
        )
        targets = SemanticEntityResolver().resolve(descriptors)
        observation = replace(
            observation,
            target_fingerprints={
                **{item.id: item.target_fingerprint for item in model.affordances},
                **candidate_fingerprints(targets),
            },
        )
        return BrowserSnapshot(
            observation,
            model,
            source_observations=(
                SourceObservation(
                    GroundingSource.DOM,
                    "dom-adapter",
                    snapshot_id,
                    environment_revision,
                    "page-1",
                ),
            ),
            grounding_candidates=tuple(candidate for target in targets for candidate in target.grounding_candidates),
            unified_affordances=targets,
        )


@dataclass
class ProfileExecutor:
    world: ProfileWorld
    fail_email_effect: bool = False
    backend: str = "dom"

    def execute(self, contract: Any, observation: Observation) -> ExecutionReceipt:
        value = str(contract.parameters.get("value") or "")
        selector = str(contract.locator.get("selector") or "")
        if selector.startswith("#name"):
            self.world.name = value
        elif selector.startswith("#email") and not self.fail_email_effect:
            self.world.email = value
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"action": "fill", "selector": selector},
        )


class CountingSystem2Planner:
    def __init__(self, *, ask_on_call: bool = False) -> None:
        self.calls = 0
        self.ask_on_call = ask_on_call

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerClarificationResponse | PlannerDoneResponse:
        self.calls += 1
        if self.ask_on_call:
            return PlannerClarificationResponse(
                question="TaskSkill failed; request safe user guidance",
                reason="TaskSkill postcondition failed after verified prior progress",
            )
        return PlannerDoneResponse(result={"system2": True})


class ProfileTrainingPlanner:
    """Generic System 2 proposal source used only to produce verified traces."""

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        summary = thaw_request_mapping(request.task.task_summary)
        entities = summary.get("entities", [])
        value = next(
            str(item["value"])
            for item in entities
            if isinstance(item, dict) and item.get("name") == "text"
        )
        if any(
            outcome.verification_status == "passed"
            for outcome in request.recent_outcomes
        ):
            return PlannerDoneResponse(result={"profile_name": value})
        target = next(
            item for item in request.observation.affordances if item.label == "Name"
        )
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=PlannerProposal(
                proposal_id=f"system2-profile-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="update the requested profile field",
                action_kind=PlannerActionKind.TYPE_TEXT,
                target_affordance_id=target.target_id,
                parameters={"text": value},
                expected_effects=("profile name changed",),
                evidence_requirements=("independent profile state",),
            ),
        )


def _payload(*, two_steps: bool = False) -> TaskSkillPayload:
    parameters = () if two_steps else (SkillParameter("step_1_text", SkillParameterType.STRING),)
    steps = [
        SkillStep(
            "step-1",
            "type profile name",
            "type_text",
            SemanticTargetQuery("textbox", "Name", "type_text"),
            parameter_bindings=(() if two_steps else (("text", "step_1_text"),)),
            constant_parameters=(("text", "Ada"),) if two_steps else (),
            postconditions=("profile name changed",),
            evidence_requirements=("independent profile state",),
            required_capabilities=("settings.write",),
            risk="medium",
        )
    ]
    if two_steps:
        steps.append(
            SkillStep(
                "step-2",
                "type profile email",
                "type_text",
                SemanticTargetQuery("textbox", "Email", "type_text"),
                constant_parameters=(("text", "ada@example.test"),),
                postconditions=("profile email changed",),
                evidence_requirements=("independent profile state",),
                required_capabilities=("settings.write",),
                risk="medium",
            )
        )
    payload = TaskSkillPayload(
        "1.0",
        "task_skill",
        "profile.update-fields",
        "1.0.0",
        TaskSkillTrigger("profile update", ("profile", "update")),
        parameters,
        tuple(steps),
        ("layout-a", "layout-b"),
        ("trace-1", "trace-2", "trace-3"),
        ("layout-a", "layout-b", "layout-a"),
        heldout_suite="profile-heldout-v1",
    )
    payload.validate()
    return payload


def _accepted_runtime(payload: TaskSkillPayload) -> AcceptedTaskSkillRuntime:
    artifact = EvolutionArtifact(
        payload.skill_id,
        EvolutionArtifactType.TASK_SKILL.value,
        "accepted profile skill",
        {"task_family": payload.trigger.task_family},
        list(payload.source_traces),
        status=EvolutionStatus.ACCEPTED,
        version=payload.version,
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    profile = CandidateRuntimeProfile()
    profile.load(artifact)
    return AcceptedTaskSkillRuntime.from_profile(profile)


def _step_verifier(
    payload: TaskSkillPayload,
    step_id: str,
    target: str,
    expected: Any,
) -> VerifierSpec:
    owner_id = skill_step_owner_id(payload.skill_id, payload.version, step_id)
    return VerifierSpec(
        "observation_metadata",
        target,
        expected,
        criterion_ids=(criterion_id("skill-step", owner_id, 0),),
        requirement_ids=(evidence_requirement_id("skill-step", owner_id, 0),),
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )


def _task(*, with_entity: bool) -> TaskSpec:
    return TaskSpec(
        task_id="profile-task",
        revision=1,
        objective="profile update Name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Name", "Email"),
        entities=((IntentEntity(name="text", value="Margaret", source_ref="user"),) if with_entity else ()),
        success_criteria=("profile fields changed",),
        evidence_requirements=("independent profile state",),
        requested_capabilities=("settings.write",),
        source_request_ref="test",
    )


def test_coordinator_system1_completes_accepted_skill_without_system2_planner_call() -> None:
    world = ProfileWorld()
    observer = ProfileObserver(world)
    planner = CountingSystem2Planner()
    payload = _payload()
    builder = ContractBuilder(
        requirements={
            observer.target_ids["Name"]: ContractRequirements(
                verifier_plan=(_step_verifier(payload, "step-1", "profile_name", "Margaret"),),
                idempotency_key="profile:name:v1",
            )
        }
    )

    runtime = _accepted_runtime(payload)
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world),
        contract_builder=builder,
        task_skill_runtime=runtime,
    ).run_sync(RunRequest(task_spec=_task(with_entity=True), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert world.name == "Margaret"
    assert planner.calls == 0
    progress = runtime.progress_for(result.state)
    assert progress is not None
    assert progress.completed_step_ids == ["step-1"]
    events = [node.kind for node in result.trace.nodes]
    assert "TaskSkillActivated" in events
    assert "TaskSkillStepExposed" in events
    validated = next(node for node in result.trace.nodes if node.kind == "PlannerProposalValidated")
    assert validated.payload["source"] == "accepted_skill"
    assert validated.payload["provenance"]["producer_id"] == payload.skill_id
    assert validated.payload["provenance"]["version"] == payload.version
    assert "ContractBuilt" in events
    assert "RouteSelected" in events
    assert "TaskSkillStepCompleted" in events
    assert "TaskSkillCompleted" in events


def test_passed_but_unbound_verifier_cannot_checkpoint_task_skill() -> None:
    world = ProfileWorld()
    observer = ProfileObserver(world)
    planner = CountingSystem2Planner()
    payload = _payload()
    builder = ContractBuilder(
        requirements={
            observer.target_ids["Name"]: ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "observation_metadata",
                        "profile_name",
                        "Margaret",
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                ),
                idempotency_key="profile:name:unbound",
            )
        }
    )

    runtime = _accepted_runtime(payload)
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world),
        contract_builder=builder,
        task_skill_runtime=runtime,
    ).run_sync(
        RunRequest(
            task_spec=_task(with_entity=True),
            capabilities=["settings.write"],
        )
    )

    assert result.status == RuntimeStep.DONE
    assert world.name == "Margaret"
    assert planner.calls == 1
    progress = runtime.progress_for(result.state)
    assert progress is not None
    assert progress.completed_step_ids == []
    events = [node.kind for node in result.trace.nodes]
    assert "PostActionEvaluated" in events
    assert "TaskSkillStepEvidenceRejected" in events
    assert "TaskSkillFellThrough" in events


def test_task_skill_target_mismatch_falls_through_to_system2_before_action() -> None:
    world = ProfileWorld()
    observer = ProfileObserver(world, include_name=False)
    planner = CountingSystem2Planner()

    runtime = _accepted_runtime(_payload())
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world),
        contract_builder=ContractBuilder(),
        task_skill_runtime=runtime,
        task_planner=None,
    ).run_sync(RunRequest(task_spec=_task(with_entity=True), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert planner.calls == 1
    assert result.state.last_receipt is None
    progress = runtime.progress_for(result.state)
    assert progress is not None
    assert "matched 0" in progress.fallthrough_reason
    assert "TaskSkillFellThrough" in [node.kind for node in result.trace.nodes]


def test_task_skill_cannot_extend_task_capability_authority() -> None:
    world = ProfileWorld()
    observer = ProfileObserver(world)
    planner = CountingSystem2Planner()
    task = _task(with_entity=True).model_copy(update={"requested_capabilities": ()})

    runtime = _accepted_runtime(_payload())
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world),
        contract_builder=ContractBuilder(),
        task_skill_runtime=runtime,
        task_planner=None,
    ).run_sync(RunRequest(task_spec=task))

    assert result.status == RuntimeStep.DONE
    assert planner.calls == 1
    assert result.state.last_receipt is None
    progress = runtime.progress_for(result.state)
    assert progress is not None
    assert "cannot extend task capability authority" in progress.fallthrough_reason


def test_task_skill_approval_requirement_must_be_enforced_by_normal_contract_gate() -> None:
    world = ProfileWorld()
    observer = ProfileObserver(world)
    planner = CountingSystem2Planner()
    payload = _payload()
    payload = replace(
        payload,
        steps=(replace(payload.steps[0], requires_approval=True),),
    )

    runtime = _accepted_runtime(payload)
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world),
        contract_builder=ContractBuilder(
            requirements={
                observer.target_ids["Name"]: ContractRequirements(
                    verifier_plan=(_step_verifier(payload, "step-1", "profile_name", "Margaret"),),
                    idempotency_key="profile:name:v1",
                )
            }
        ),
        task_skill_runtime=runtime,
        task_planner=None,
    ).run_sync(RunRequest(task_spec=_task(with_entity=True), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert planner.calls == 1
    assert result.state.last_receipt is None
    progress = runtime.progress_for(result.state)
    assert progress is not None
    assert "requires approval" in progress.fallthrough_reason


def test_failed_later_skill_step_preserves_verified_progress_and_falls_through() -> None:
    world = ProfileWorld()
    observer = ProfileObserver(world)
    planner = CountingSystem2Planner(ask_on_call=True)
    payload = _payload(two_steps=True)
    builder = ContractBuilder(
        requirements={
            observer.target_ids["Name"]: ContractRequirements(
                verifier_plan=(_step_verifier(payload, "step-1", "profile_name", "Ada"),),
                idempotency_key="profile:name:v1",
            ),
            observer.target_ids["Email"]: ContractRequirements(
                verifier_plan=(
                    _step_verifier(
                        payload,
                        "step-2",
                        "profile_email",
                        "ada@example.test",
                    ),
                ),
                idempotency_key="profile:email:v1",
            ),
        }
    )

    runtime = _accepted_runtime(payload)
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world, fail_email_effect=True),
        contract_builder=builder,
        task_skill_runtime=runtime,
    ).run_sync(RunRequest(task_spec=_task(with_entity=False), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert world.name == "Ada"
    assert world.email == ""
    assert planner.calls == 1
    progress = runtime.progress_for(result.state)
    assert progress is not None
    assert progress.completed_step_ids == ["step-1"]
    assert progress.next_step_index == 1
    assert progress.evidence
    assert progress.fallthrough_reason == "TaskSkill step verification failed"
    assert result.state.current_failure is not None
    assert result.state.current_failure.error_code == "verification_failed"
    recovery_outcomes = [
        node.payload["outcome"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    ]
    assert recovery_outcomes
    assert recovery_outcomes[-1]["success"]
    events = [node.kind for node in result.trace.nodes]
    assert events.count("TaskSkillStepCompleted") == 1
    assert "TaskSkillStepFailed" in events
    assert "TaskSkillFellThrough" in events
    assert events.index("TaskSkillFellThrough") < events.index("ClarificationRequested")


def test_canonical_pipeline_mines_three_real_system2_runtime_traces_across_variants(tmp_path) -> None:
    sources = []
    for index, (variant, value) in enumerate(
        (("original", "Margaret"), ("family", "Grace"), ("heldout", "Lin")),
        start=1,
    ):
        world = ProfileWorld()
        observer = ProfileObserver(world, variant=variant)
        task = _task(with_entity=True).model_copy(
            update={
                "task_id": f"profile-training-{index}",
                "entities": (IntentEntity(name="text", value=value, source_ref=f"training:{index}"),),
            }
        )
        result = compose_run_coordinator(
            observer,
            ProfileTrainingPlanner(),
            ProfileExecutor(world),
            contract_builder=ContractBuilder(
                requirements={
                    observer.target_ids["Name"]: ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "observation_metadata",
                                "profile_name",
                                value,
                                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                            ),
                        ),
                        idempotency_key=f"profile:training:{index}",
                    )
                }
            ),
        ).run_sync(RunRequest(task_spec=task, capabilities=["settings.write"]))
        assert result.status == RuntimeStep.DONE
        trace_path = JsonlTraceWriter(tmp_path / f"training-{index}.jsonl").write(result.trace)
        sources.append((trace_path, TraceMiningContext("profile update", variant)))

    registry = EvolutionRegistry()
    proposal = CanonicalTaskSkillPipeline().propose(
        sources,
        registry=registry,
        skill_id="profile.system2-mined",
        heldout_suite="profile-fresh-heldout-v1",
    )

    assert proposal.payload.schema_version == "1.1"
    assert len(set(proposal.payload.source_trace_digests)) == 3
    assert len(set(proposal.payload.source_variants)) == 3
    assert registry.artifacts[proposal.artifact_id].status == EvolutionStatus.QUARANTINED

    replay_evidence: list[TaskSkillReplayEvidence] = []
    for category, variant, value in (
        ("original", "original", "Margaret"),
        ("task_family", "family", "Grace"),
        ("heldout", "heldout", "Lin"),
    ):
        world = ProfileWorld()
        observer = ProfileObserver(world, variant=variant)
        planner = CountingSystem2Planner()
        task = _task(with_entity=True).model_copy(
            update={
                "task_id": f"mined-replay-{category}",
                "entities": (IntentEntity(name="text", value=value, source_ref=f"replay:{category}"),),
            }
        )
        result = compose_run_coordinator(
            observer,
            planner,
            ProfileExecutor(world),
            contract_builder=ContractBuilder(
                requirements={
                    observer.target_ids["Name"]: ContractRequirements(
                        verifier_plan=(
                            _step_verifier(proposal.payload, "step-1", "profile_name", value),
                        ),
                        idempotency_key=f"mined:replay:{category}",
                    )
                }
            ),
            task_skill_runtime=_accepted_runtime(proposal.payload),
        ).run_sync(RunRequest(task_spec=task, capabilities=["settings.write"]))
        kinds = [node.kind for node in result.trace.nodes]
        trace_path = JsonlTraceWriter(tmp_path / f"mined-replay-{category}.jsonl").write(result.trace)
        replay_evidence.append(
            _bind_replay_report(
                TaskSkillReplayEvidence(
                    category,
                    result.run_id,
                    variant,
                    result.status == RuntimeStep.DONE and world.name == value,
                    result.verification is not None and result.verification.status.value == "passed",
                    "TaskSkillActivated" in kinds,
                    True,
                    planner.calls,
                    1.0,
                    fell_through="TaskSkillFellThrough" in kinds,
                    source_trace_digest=_file_digest(trace_path),
                    skill_payload_digest=proposal.payload.digest(),
                )
            )
        )

    for category, operation, capability in (
        ("global_smoke", OperationClass.READ_ONLY, ""),
        ("safety_smoke", OperationClass.IRREVERSIBLE, "account.delete"),
    ):
        world = ProfileWorld()
        observer = ProfileObserver(world)
        planner = CountingSystem2Planner()
        task = TaskSpec(
            task_id=f"mined-non-profile-{category}",
            revision=1,
            objective="inspect account" if category == "global_smoke" else "delete account",
            operation_class=operation,
            targets=("Account",),
            success_criteria=("system 2 completed safely",),
            requested_capabilities=((capability,) if capability else ()),
            source_request_ref=f"replay:{category}",
        )
        result = compose_run_coordinator(
            observer,
            planner,
            ProfileExecutor(world),
            contract_builder=ContractBuilder(),
            task_skill_runtime=_accepted_runtime(proposal.payload),
            task_planner=None,
        ).run_sync(RunRequest(task_spec=task, capabilities=([capability] if capability else [])))
        kinds = [node.kind for node in result.trace.nodes]
        trace_path = JsonlTraceWriter(tmp_path / f"mined-replay-{category}.jsonl").write(result.trace)
        replay_evidence.append(
            _bind_replay_report(
                TaskSkillReplayEvidence(
                    category,
                    result.run_id,
                    "non-profile",
                    result.status == RuntimeStep.DONE and result.state.last_receipt is None,
                    result.state.last_receipt is None,
                    "TaskSkillActivated" in kinds,
                    False,
                    planner.calls,
                    1.0,
                    fell_through="TaskSkillFellThrough" in kinds,
                    source_trace_digest=_file_digest(trace_path),
                    skill_payload_digest=proposal.payload.digest(),
                )
            )
        )

    decision = TaskSkillReplayGate().evaluate(
        registry,
        proposal.artifact_id,
        replay_evidence,
        baseline_model_calls=1.0,
        baseline_latency_ms=2.0,
    )
    assert decision.status == EvolutionStatus.ACCEPTED.value
    assert decision.metrics["mean_model_calls"] < 1.0
    assert decision.metrics["skill_activation_precision"] == 1.0

    registry_path = tmp_path / "accepted-mined-profile.json"
    EvolutionRegistryStore(registry_path).save(registry)
    loaded = AcceptedProfileLoader(registry_path).load()
    world = ProfileWorld()
    observer = ProfileObserver(world, variant="heldout")
    planner = CountingSystem2Planner()
    task = _task(with_entity=True).model_copy(
        update={
            "task_id": "profile-fresh-loaded-heldout",
            "entities": (IntentEntity(name="text", value="Ken", source_ref="heldout:fresh"),),
        }
    )
    result = compose_run_coordinator(
        observer,
        planner,
        ProfileExecutor(world),
        contract_builder=ContractBuilder(
            requirements={
                observer.target_ids["Name"]: ContractRequirements(
                    verifier_plan=(
                        _step_verifier(proposal.payload, "step-1", "profile_name", "Ken"),
                    ),
                    idempotency_key="profile:fresh-loaded-heldout",
                )
            }
        ),
        task_skill_runtime=loaded.task_skill_runtime,
        runtime_profile_digest=loaded.profile_digest,
        loaded_profile_artifact_ids=loaded.artifact_ids,
    ).run_sync(RunRequest(task_spec=task, capabilities=["settings.write"]))
    kinds = [node.kind for node in result.trace.nodes]
    assert result.status == RuntimeStep.DONE
    assert world.name == "Ken"
    assert planner.calls == 0
    assert "TaskSkillSelectionEvaluated" in kinds
    assert "TaskSkillActivated" in kinds
    assert result.trace.nodes[0].payload["runtime_profile_digest"] == loaded.profile_digest


def test_fresh_coordinator_replay_accepts_skill_across_mandatory_safe_categories(tmp_path) -> None:
    payload = _payload()
    evidence: list[TaskSkillReplayEvidence] = []
    for category, variant, value in (
        ("original", "original", "Margaret"),
        ("task_family", "family", "Grace"),
        ("heldout", "heldout", "Lin"),
    ):
        world = ProfileWorld()
        observer = ProfileObserver(world, variant=variant)
        planner = CountingSystem2Planner()
        task = _task(with_entity=True).model_copy(
            update={
                "task_id": f"profile-{category}",
                "entities": (IntentEntity(name="text", value=value, source_ref=f"replay:{category}"),),
            }
        )
        started = perf_counter()
        result = compose_run_coordinator(
            observer,
            planner,
            ProfileExecutor(world),
            contract_builder=ContractBuilder(
                requirements={
                    observer.target_ids["Name"]: ContractRequirements(
                        verifier_plan=(
                            _step_verifier(
                                payload,
                                "step-1",
                                "profile_name",
                                value,
                            ),
                        ),
                        idempotency_key=f"profile:name:{category}",
                    )
                }
            ),
            task_skill_runtime=_accepted_runtime(payload),
        ).run_sync(RunRequest(task_spec=task, capabilities=["settings.write"]))
        kinds = [node.kind for node in result.trace.nodes]
        trace_path = JsonlTraceWriter(tmp_path / f"{category}-events.jsonl").write(result.trace)
        if category == "original":
            assert kinds[-1] == "TaskCompleted", kinds[-10:]
            canonical = CanonicalSemanticTraceExtractor().extract(
                trace_path,
                TraceMiningContext("profile update", variant),
            )
            assert canonical.steps[0].target_role == "textbox"
            assert canonical.steps[0].parameters == (("text", value),)
        evidence.append(
            _bind_replay_report(TaskSkillReplayEvidence(
                category,
                result.run_id,
                variant,
                result.status == RuntimeStep.DONE and world.name == value,
                result.verification is not None and result.verification.status.value == "passed",
                "TaskSkillActivated" in kinds,
                True,
                planner.calls,
                (perf_counter() - started) * 1_000,
                fell_through="TaskSkillFellThrough" in kinds,
                source_trace_digest=_file_digest(trace_path),
                skill_payload_digest=payload.digest(),
            ))
        )

    for category, operation, capability in (
        ("global_smoke", OperationClass.READ_ONLY, ""),
        ("safety_smoke", OperationClass.IRREVERSIBLE, "account.delete"),
    ):
        world = ProfileWorld()
        observer = ProfileObserver(world)
        planner = CountingSystem2Planner()
        task = TaskSpec(
            task_id=f"non-profile-{category}",
            revision=1,
            objective="inspect account" if category == "global_smoke" else "delete account",
            operation_class=operation,
            targets=("Account",),
            success_criteria=("planner handled non-profile task",),
            requested_capabilities=((capability,) if capability else ()),
            source_request_ref=f"replay:{category}",
        )
        started = perf_counter()
        result = compose_run_coordinator(
            observer,
            planner,
            ProfileExecutor(world),
            contract_builder=ContractBuilder(),
            task_skill_runtime=_accepted_runtime(payload),
            task_planner=None,
        ).run_sync(RunRequest(task_spec=task, capabilities=([capability] if capability else [])))
        kinds = [node.kind for node in result.trace.nodes]
        no_effect = world == ProfileWorld() and result.state.last_receipt is None
        trace_path = JsonlTraceWriter(tmp_path / f"{category}-events.jsonl").write(result.trace)
        evidence.append(
            _bind_replay_report(TaskSkillReplayEvidence(
                category,
                result.run_id,
                "non-profile",
                result.status == RuntimeStep.DONE and no_effect,
                no_effect,
                "TaskSkillActivated" in kinds,
                False,
                planner.calls,
                (perf_counter() - started) * 1_000,
                fell_through="TaskSkillFellThrough" in kinds,
                source_trace_digest=_file_digest(trace_path),
                skill_payload_digest=payload.digest(),
            ))
        )

    registry = EvolutionRegistry()
    artifact = quarantine_task_skill(payload, registry)
    decision = TaskSkillReplayGate().evaluate(
        registry,
        artifact.id,
        evidence,
        baseline_model_calls=1.0,
        baseline_latency_ms=0.0,
    )

    assert decision.status == EvolutionStatus.ACCEPTED.value
    assert decision.metrics["task_success_rate"] == 1.0
    assert decision.metrics["skill_activation_precision"] == 1.0
    assert decision.metrics["model_call_reduction"] > 0
    assert [item.category for item in evidence] == [
        "original",
        "task_family",
        "heldout",
        "global_smoke",
        "safety_smoke",
    ]


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _bind_replay_report(evidence: TaskSkillReplayEvidence) -> TaskSkillReplayEvidence:
    return replace(evidence, replay_report_digest=evidence.canonical_report_digest())


def _file_digest(path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
