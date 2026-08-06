import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence, TypeVar, cast

import pytest
from pydantic import BaseModel

import affordance_runtime.benchmarks.browsergym as browsergym_module
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.benchmarks.browsergym import (
    BROWSERGYM_MINIWOB_COMMIT,
    BROWSERGYM_PLANNER_MAX_TOKENS,
    BROWSERGYM_VERSION,
    NIGHTLY_ACTION_FAMILIES,
    NIGHTLY_MANIFEST_VERSION,
    PR_SMOKE_TASKS,
    BrowserGymAction,
    BrowserGymEpisodeResult,
    BrowserGymEpisodeState,
    BrowserGymExecutor,
    BrowserGymGeneralistPlanner,
    BrowserGymGestureEncoder,
    BrowserGymObserver,
    BrowserGymPointEncoder,
    BrowserGymPolicyRequest,
    GeneralistBrowserGymContractBuilder,
    _accessibility_tree_text,
    _browsergym_planning_stats,
    _close_quietly,
    _fuse_visual_candidates,
    _intent_compiler_checkpoint_identity,
    _load_browsergym_checkpoints,
    _prepare_browsergym_checkpoint_metadata,
    _require_frozen_profile_identity,
    _runtime_source_sha256,
    _validate_browsergym_time_budgets,
    _visual_fallback_affordance,
    _write_browsergym_checkpoint,
    browsergym_batch_circuit_breaker,
    browsergym_episode_schedule,
    browsergym_failure_envelope,
    browsergym_profile,
    cluster_browsergym_failure_envelopes,
    run_browsergym_generalist_episode,
    update_browsergym_batch_circuit_state,
    write_browsergym_report,
)
from affordance_runtime.benchmarks.browsergym_dom import (
    browsergym_dom_adapter,
    browsergym_svg_observer,
)
from affordance_runtime.benchmarks.browsergym_episode_runner import (
    BrowserGymPlanner,
    _browsergym_failure_stats,
    _browsergym_model_stats,
)
from affordance_runtime.benchmarks.browsergym_matrix import checkpoint_filename
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    ExecutionReceipt,
    GestureBinding,
    Observation,
    ProgressEvidenceScope,
    Surface,
    VerifierSpec,
)
from affordance_runtime.generalist_planner import PlannerLimits
from affordance_runtime.grounding import (
    EvidenceKind,
    GroundingSource,
    PerceptionRequirements,
    SourceObservation,
)
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderFailureKind,
    ProviderModelError,
    StructuredOutputError,
)
from affordance_runtime.perception import GenericPerceptionOrchestrator
from affordance_runtime.planning import PlannerActionKind, PlannerProposal
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import legacy_run_request
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification.contracts import SuccessExpression
from affordance_runtime.verification.mechanical import VerifierLadder
from affordance_runtime.visual_grounding import VisualGroundingPoint, VisualRegion
from runtime_test_support import canonical_observation, remember_observation

T = TypeVar("T", bound=BaseModel)


def _task_success(*requirement_refs: str) -> SuccessExpression:
    return SuccessExpression(
        expression_id="success:test-task",
        operator="criterion",
        criterion_id="criterion:test-task",
        requirement_refs=requirement_refs,
    )


def test_browsergym_projects_runtime_owned_failure_event_without_reclassification() -> None:
    trace = TraceDag("run")
    trace.add(
        "FailureDetected",
        {
            "failure": {
                "phase": "fusion",
                "failure_class": "source_conflict",
                "error_code": "precondition_failed",
                "effect_status": "not_dispatched",
                "message": "required spatial evidence is absent",
                "evidence_refs": ["artifact:source"],
            }
        },
    )

    projected = _browsergym_failure_stats(trace.nodes)["runtime_failure"]

    assert projected is not None
    assert projected.phase == "fusion"
    assert projected.failure_class == "source_conflict"
    assert projected.error_code == "precondition_failed"
    assert projected.message == "required spatial evidence is absent"
    assert projected.evidence_refs == ["artifact:source"]


def test_browsergym_preserves_proposal_validator_detail_code() -> None:
    trace = TraceDag("run")
    trace.add(
        "PlannerProposalRejected",
        {
            "error_code": "planner_proposal_rejected",
            "rejection_code": "target_out_of_scope",
            "reason": "semantic:target",
        },
    )
    trace.add(
        "FailureDetected",
        {
            "failure": {
                "phase": "proposal_validation",
                "failure_class": "validation",
                "error_code": "planner_proposal_rejected",
                "effect_status": "not_dispatched",
                "message": "semantic:target",
                "evidence_refs": [],
            }
        },
    )

    projected = _browsergym_failure_stats(trace.nodes)["runtime_failure"]

    assert projected is not None
    assert projected.detail_code == "target_out_of_scope"


def test_browsergym_preserves_task_replan_validator_detail_code() -> None:
    trace = TraceDag("run")
    trace.add(
        "TaskReplanRejected",
        {
            "error_code": "planner_proposal_rejected",
            "validation": "repairable",
            "issues": [
                {
                    "code": "entry_outcome_state_unsupported",
                    "detail": "search",
                }
            ],
        },
    )
    trace.add(
        "FailureDetected",
        {
            "failure": {
                "phase": "task_planning",
                "failure_class": "validation",
                "error_code": "planner_proposal_rejected",
                "effect_status": "not_dispatched",
                "message": "task plan validation: repairable",
                "evidence_refs": [],
            }
        },
    )

    projected = _browsergym_failure_stats(trace.nodes)["runtime_failure"]

    assert projected is not None
    assert projected.detail_code == "entry_outcome_state_unsupported"


def test_browsergym_preserves_failed_verifier_kind_as_detail_code() -> None:
    trace = TraceDag("run")
    trace.add(
        "PostActionEvaluated",
        {
            "reason": "verifier failed: control_state:slider",
            "action_effect_status": "failed",
            "evidence": [
                {
                    "verifier_kind": "evidence",
                    "passed": True,
                },
                {
                    "verifier_kind": "control_state",
                    "passed": False,
                },
            ],
        },
    )
    trace.add(
        "FailureDetected",
        {
            "failure": {
                "phase": "verification",
                "failure_class": "verification",
                "error_code": "verification_failed",
                "effect_status": "may_have_occurred",
                "message": "verifier failed: control_state:slider",
                "evidence_refs": ["artifact:verification"],
            }
        },
    )

    projected = _browsergym_failure_stats(trace.nodes)["runtime_failure"]

    assert projected is not None
    assert projected.detail_code == "control_state"
    assert projected.evidence_refs == ["artifact:verification"]


def test_browsergym_projects_approval_pause_without_fabricating_recovery() -> None:
    trace = TraceDag("run")
    trace.add("HumanApprovalRequested", {"state": "waiting_approval"})

    projected = _browsergym_failure_stats(trace.nodes)["runtime_failure"]

    assert projected is not None
    assert projected.phase == "preflight"
    assert projected.failure_class == "authority"
    assert projected.error_code == "approval_required"


def _browsergym_session(page: Any, **kwargs: Any) -> BrowserSession:
    return BrowserSession(
        page,
        dom_adapter=browsergym_dom_adapter(),
        svg_observer=browsergym_svg_observer(),
        **kwargs,
    )


class FakeBrowserGymPage:
    url = "http://miniwob/click-button.html"

    def __init__(self) -> None:
        self.done = False
        self.default_timeout_ms: int | None = None

    def content(self) -> str:
        status = "done" if self.done else "pending"
        return f'<html><body><button bid="target">Target</button><p>{status}</p></body></html>'

    def screenshot(self, **kwargs: Any) -> bytes:
        payload = b"fake-png"
        if kwargs.get("path"):
            Path(kwargs["path"]).write_bytes(payload)
        return payload

    def wait_for_load_state(self, state: str = "load", **kwargs: Any) -> None:
        del state, kwargs

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.default_timeout_ms = timeout_ms


class FakeBrowserGymEnvironment:
    def __init__(self) -> None:
        self.page = FakeBrowserGymPage()
        self.closed = False

    @property
    def unwrapped(self) -> "FakeBrowserGymEnvironment":
        return self

    def reset(self, *, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
        assert seed == 4
        return {"goal": "Click the target", "last_action_error": ""}, {}

    def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        assert action == "click('target')"
        self.page.done = True
        return (
            {"goal": "Click the target", "last_action_error": ""},
            1.0,
            True,
            False,
            {"task_info": {"RAW_REWARD_GLOBAL": 1}},
        )

    def close(self) -> None:
        self.closed = True


class OneClickPolicy:
    def __init__(self) -> None:
        self.closed = False

    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction | None:
        assert request.goal == "Click the target"
        assert request.affordances[0]["locator"]["selector"] == "[bid='target']"
        assert request.affordances[0]["locator"]["bid"] == "target"
        return BrowserGymAction("click", {"bid": "target"})

    def close(self) -> None:
        self.closed = True


def test_browsergym_policy_planner_projects_request_without_changing_policy_request() -> None:
    revision = "browsergym-request-v1"
    model = DomAdapter().transduce(
        '<button bid="target">Target</button>',
        environment_revision=revision,
        snapshot_id="browsergym-request-snapshot",
    )
    observation = Observation(
        revision,
        snapshot_id="browsergym-request-snapshot",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("browsergym-request", "Click the target")
    state.transition("observing")
    remember_observation(state, observation)
    state.transition("planning")
    task = TaskSpec(
        task_id="browsergym-request",
        revision=1,
        objective="Click the target",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("target",), OperationClass.REVERSIBLE_WRITE, "browsergym-request-source", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("target",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="browsergym-request-source",
    )

    class RecordingPolicy(OneClickPolicy):
        seen: BrowserGymPolicyRequest | None = None

        def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction | None:
            self.seen = request
            return BrowserGymAction("click", {"bid": "target"})

    policy = RecordingPolicy()
    episode = BrowserGymEpisodeState(
        task_id="click-button",
        seed=4,
        goal="Click the target",
        observation={"text": "Target"},
        info={},
    )

    planning_request = PlanningRequestBuilder().build(
        legacy_run_request(task_spec=task),
        state,
        canonical_observation(BrowserSnapshot(observation, model)),
    )
    decision = BrowserGymPlanner(policy, episode, {}).propose(planning_request)

    assert planning_request.identity.snapshot_id == observation.snapshot_id
    assert policy.seen is not None
    assert policy.seen.task_id == "click-button"
    assert policy.seen.seed == 4
    assert policy.seen.affordances[0]["id"] == "dom_button_1"
    assert decision.proposal is not None


@dataclass
class GeneralistClickModel:
    provider: str = "fixed"
    model: str = "fixed-generalist"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0
    first_target_id: str = ""
    planner_calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del config
        if output_schema.__name__ == "LLMMinimalIntentProposal":
            request = json.loads(messages[-1].content)
            source_ref = request["source_envelope"]["anchors"][0]["anchor_id"]
            self.calls += 1
            return output_schema.model_validate(
                {
                    "objective": request["raw_text"],
                    "requested_effects": [
                        {
                            "operation_class": "reversible_write",
                            "target": "target",
                            "source_ref": source_ref,
                        }
                    ],
                    "success": {
                        "expression_id": "success:target-activated",
                        "operator": "criterion",
                        "criterion_id": "criterion:target-activated",
                        "requirement_refs": ["requirement:effect:1"],
                    },
                    "task_structure": "flat",
                }
            )
        context = json.loads(messages[-1].content)
        if output_schema.__name__ == "TaskPlanProviderResponse":
            task_spec = context["task_spec"]
            requirement_ref = task_spec["allowed_effect_refs"][0]
            target = context["planning"]["environment"]["affordances"][0]
            self.first_target_id = target["semantic_target_id"]
            payload = {
                "steps": [
                    {
                        "step_id": "step:click-target",
                        "objective": "activate the admitted target",
                        "subject": target["label"],
                        "relation": "is_completed",
                        "requirement_refs": [requirement_ref],
                        "effect_authorization_refs": [requirement_ref],
                        "effectful": True,
                    }
                ]
            }
        elif output_schema.__name__ == "DisplayedChoiceCandidate":
            payload = {"choice_id": context["choices"][0]["choice_id"]}
        else:
            raise AssertionError(f"unexpected schema: {output_schema.__name__}")
        self.calls += 1
        self.planner_calls += 1
        return output_schema.model_validate(payload)


class RepairingGeneralistClickModel(GeneralistClickModel):
    intake_drafts: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        if output_schema.__name__ == "LLMMinimalIntentProposal":
            self.intake_drafts += 1
            if self.intake_drafts == 1:
                self.calls += 1
                raise StructuredOutputError("invalid proposal schema")
            messages = (messages[0], messages[1])
        return await super().generate_structured(messages, output_schema, config)


class InvalidIntentModel:
    provider = "fixed"
    model = "invalid-intent"
    endpoint_class = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        return output_schema.model_validate({})


class UnsupportedPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        del request
        return BrowserGymAction("page.evaluate", {"code": "danger"})


class UnsupportedSemanticPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        del request
        return BrowserGymAction("scroll", {"delta_x": 0, "delta_y": 10})


def test_typed_browsergym_action_rejects_code_and_unknown_arguments() -> None:
    assert BrowserGymAction("fill", {"bid": "field", "value": "hello"}).render() == "fill('field', 'hello')"
    with pytest.raises(ValueError, match="unsupported BrowserGym action"):
        BrowserGymAction("page.evaluate", {"code": "danger"}).render()
    with pytest.raises(ValueError, match="unsupported arguments"):
        BrowserGymAction("click", {"bid": "target", "code": "danger"}).render()
    with pytest.raises(ValueError, match="expected string"):
        BrowserGymAction("press", {"bid": "target", "key_comb": ["ArrowDown"]}).render()
    with pytest.raises(ValueError, match="expected number"):
        BrowserGymAction("scroll", {"delta_x": "0", "delta_y": 10}).render()


def test_accessibility_tree_fallback_preserves_role_name_and_bid() -> None:
    text = _accessibility_tree_text(
        {
            "axtree_object": {
                "nodes": [
                    {
                        "nodeId": "1",
                        "ignored": False,
                        "role": {"value": "checkbox"},
                        "name": {"value": "Third choice"},
                        "browsergym_id": "23",
                    }
                ]
            }
        }
    )
    assert "checkbox" in text
    assert "Third choice" in text
    assert "23" in text


def test_disabling_browsergym_observation_profile_preserves_declared_runtime_actions() -> None:
    html = (
        '<span bid="benchmark-only" browsergym_set_of_marks="1">Profile control</span>'
        '<div id="portable-drag" draggable="true">Portable drag</div>'
        '<button id="native">Native</button>'
    )

    enabled = browsergym_dom_adapter().transduce(html, environment_revision="rev-enabled")
    disabled = DomAdapter().transduce(html, environment_revision="rev-disabled")

    assert any(item.label == "Profile control" for item in enabled.affordances)
    assert all(item.label != "Profile control" for item in disabled.affordances)
    assert {(item.label, item.action) for item in disabled.affordances} == {
        ("Portable drag", "drag"),
        ("Native", "click"),
    }


def test_browsergym_marks_do_not_promote_native_labels_over_their_controls() -> None:
    model = browsergym_dom_adapter().transduce(
        '<p><label bid="label-1" browsergym_set_of_marks="1">Password</label>'
        '<input id="password" bid="input-1" browsergym_set_of_marks="1" type="password"></p>'
        '<p><label bid="label-2" browsergym_set_of_marks="1">Verify password</label>'
        '<input id="verify" bid="input-2" browsergym_set_of_marks="1" type="password"></p>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action, item.locator.get("backend_handle")) for item in model.affordances] == [
        ("Password", "type", "input-1"),
        ("Verify password", "type", "input-2"),
    ]


def test_strict_task_and_choice_planners_run_browsergym_without_external_policy(tmp_path: Path) -> None:
    environment = FakeBrowserGymEnvironment()
    model = GeneralistClickModel()

    result = run_browsergym_generalist_episode(
        environment,
        model,
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )

    assert result.runtime_status != "done"
    assert result.official_success is True
    assert result.official_success is True
    assert result.action_families == ["click"]
    assert model.calls == 2
    assert model.planner_calls == 1
    assert result.model_call_count == 2
    assert environment.page.default_timeout_ms == 1_500
    trace_rows = [json.loads(line) for line in Path(result.trace_path).read_text().splitlines()]
    events = [row["event_type"] for row in trace_rows]
    assert "SourceEnvelopeBuilt" in events
    assert "MinimalIntentProposalProduced" in events
    assert "TaskSpecAdmissionDecided" in events
    assert "TaskPlanProposed" in events
    assert "ActionChoiceCatalogBuilt" in events
    assert "ActionChoiceSelected" in events
    assert "ContractBuilt" in events
    route = next(row["payload"] for row in trace_rows if row["event_type"] == "RouteSelected")
    assert model.first_target_id.startswith("semantic:")
    assert route["candidate_id"].startswith("candidate:dom:")
    task_plan_context = next(
        row["payload"]["planning_context"] for row in trace_rows if row["event_type"] == "TaskPlanProposed"
    )
    assert task_plan_context["task_spec"]["operation_class"] == "reversible_write"
    assert task_plan_context["task_spec"]["requirements"][0]["payload"]["subject"] == "target"
    assert "task_structure" not in task_plan_context["task_spec"]
    assert "task_id" not in task_plan_context["task_spec"]
    assert task_plan_context["task_spec"]["source_envelope_ref"].startswith("sha256:")
    assert "official_reward" not in json.dumps(task_plan_context)
    assert route["semantic_target_id"].startswith("semantic:")
    assert route["semantic_target_id"] != "dom_button_1"
    assert route["hard_gates"] and route["hard_gates"][0]["passed"] is True
    assert route["scores"] and route["decision_reason"]


def test_generalist_intent_rejection_preserves_trace_and_model_attempt(tmp_path: Path) -> None:
    result = run_browsergym_generalist_episode(
        FakeBrowserGymEnvironment(),
        InvalidIntentModel(),
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )

    assert result.runtime_status == "failed"
    assert result.runtime_error.startswith("ValidationError:")
    assert result.model_call_count == 1
    assert result.trace_path
    events = [json.loads(line)["event_type"] for line in Path(result.trace_path).read_text().splitlines()]
    assert events[-2:] == ["MinimalIntentProposalRejected", "BrowserGymEpisodeFailed"]


def test_browsergym_episode_report_counts_successful_intent_repair(tmp_path: Path) -> None:
    model = RepairingGeneralistClickModel()

    result = run_browsergym_generalist_episode(
        FakeBrowserGymEnvironment(),
        model,
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )

    assert result.runtime_status != "done"
    assert result.official_success is True
    assert model.calls == 3
    assert model.planner_calls == 1
    assert result.model_call_count == 3


def test_browsergym_model_stats_counts_repair_model_call_record() -> None:
    nodes = (SimpleNamespace(kind="MinimalIntentProposalProduced", payload={"model_call": {"latency_ms": 3}}),)

    stats = _browsergym_model_stats(nodes, attempted_calls=3)

    assert stats["model_call_count"] == 3
    assert stats["model_call_latency_ms"] == 3.0


def test_generalist_browsergym_adapter_binds_native_option_activation_as_select() -> None:
    model = browsergym_dom_adapter().transduce(
        '<select bid="select-bid"><option bid="option-bid" value="earth">Earth</option></select>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Choose Earth")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Choose Earth",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("select",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("select",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="option",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_option_1",
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))

    assert contract.action == "select_option"
    assert contract.parameters["action"] == {
        "name": "select_option",
        "arguments": {"bid": "select-bid", "options": "earth"},
    }
    assert contract.verifier_plan[-1] == VerifierSpec(
        "control_state",
        "select-bid",
        {"field": "selected_options", "value": ["earth"]},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )


def test_generalist_browsergym_adapter_uses_navigation_safe_hash_link_click() -> None:
    model = browsergym_dom_adapter().transduce(
        '<a bid="result" href="#">Result</a>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Open Result")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Open Result",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("result",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("result",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="open",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_a_1",
    )

    contract = GeneralistBrowserGymContractBuilder().build(
        proposal,
        task,
        state,
        BrowserSnapshot(observation, model),
    )

    assert contract.parameters["action"] == {
        "name": "click_no_navigation",
        "arguments": {"bid": "result"},
    }


def test_generalist_browsergym_adapter_uses_current_dom_click_for_collection_control() -> None:
    model = browsergym_dom_adapter().transduce(
        """
        <div class="media" data-result="0">
          <span class="username">@owner</span>
          <div class="controls">
            <span><span bid="more-bid" class="more"></span><ul class="hide"></ul></span>
          </div>
        </div>
        """,
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    affordance = next(item for item in model.affordances if item.label == "More")
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Open More for @owner")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Open More for @owner",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("@owner", "More"), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("@owner", "More")),
        success=_task_success("requirement:effect:1", "requirement:effect:2"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="open-more",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )

    contract = GeneralistBrowserGymContractBuilder().build(
        proposal,
        task,
        state,
        BrowserSnapshot(observation, model),
    )

    assert contract.parameters["action"] == {
        "name": "click_no_navigation",
        "arguments": {"bid": "more-bid"},
    }


def test_generalist_browsergym_adapter_binds_semantic_drag_to_two_bids() -> None:
    class SortablePage:
        url = "http://fixture/sortable"

        def content(self) -> str:
            return (
                '<li bid="source" class="ui-sortable-handle">Source</li>'
                '<li bid="destination" class="ui-sortable-handle">Destination</li>'
            )

    snapshot = _browsergym_session(
        cast(Any, SortablePage()),
        lease_ttl_ms=60_000,
        dom_executor="browsergym",
    ).capture()
    source = next(item for item in snapshot.unified_affordances if item.label == "Source")
    destination = next(item for item in snapshot.unified_affordances if item.label == "Destination")
    state = StateKernel("task-1", "Drag Source to Destination")
    remember_observation(state, snapshot.observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Drag Source to Destination",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("Source", "Destination"), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("Source", "Destination")),
        success=_task_success("requirement:effect:1", "requirement:effect:2"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="drag",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id=source.semantic_target_id,
        destination_affordance_id=destination.semantic_target_id,
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, snapshot)

    assert contract.action == "drag_and_drop"
    assert contract.affordance_id == source.semantic_target_id
    assert contract.grounding_candidate == source.grounding_candidates[0]
    assert contract.route_plan is not None
    assert contract.route_plan.selected_candidate == source.grounding_candidates[0]
    assert contract.gesture_binding is not None
    assert contract.gesture_binding.source.semantic_target_id == source.semantic_target_id
    assert contract.gesture_binding.destination.semantic_target_id == destination.semantic_target_id
    assert contract.gesture_binding.source.candidate_id == source.grounding_candidates[0].candidate_id
    assert contract.gesture_binding.destination.candidate_id == destination.grounding_candidates[0].candidate_id
    assert contract.gesture_binding.source.target_fingerprint_key == source.grounding_candidates[0].fingerprint_key
    assert (
        contract.gesture_binding.destination.target_fingerprint_key
        == destination.grounding_candidates[0].fingerprint_key
    )
    assert contract.gesture_binding.source.snapshot_id == contract.gesture_binding.destination.snapshot_id
    assert contract.parameters["action"] == {
        "name": "drag_and_drop",
        "arguments": {"from_bid": "source", "to_bid": "destination"},
    }


def test_browsergym_point_encoder_uses_current_svg_viewport_box() -> None:
    point = Affordance(
        "svg_circle_1",
        Surface.SVG,
        "point",
        "(-1,0)",
        "point_activate",
        {"bbox": [120.0, 240.0, 8.0, 8.0], "coordinate_space": "viewport_pixels"},
        AffordanceLease.issue(environment_revision="rev-1"),
        backend_candidates=["visual"],
    )

    action = BrowserGymPointEncoder().encode(point)

    assert action == BrowserGymAction("mouse_click", {"x": 124.0, "y": 244.0})


def test_browsergym_sortable_list_drag_uses_insertion_geometry() -> None:
    model = browsergym_dom_adapter().transduce(
        '<li bid="source" class="ui-sortable-handle">Source</li>'
        '<li bid="destination" class="ui-sortable-handle">Destination</li>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    source, destination = model.affordances
    source = replace(source, locator={**source.locator, "bbox": [10, 100, 120, 24]})
    destination = replace(destination, locator={**destination.locator, "bbox": [10, 130, 120, 24]})
    binding = GestureBinding(source=source, destination=destination)

    action = BrowserGymGestureEncoder().encode(binding)

    assert action.name == "mouse_drag_and_drop"
    assert action.arguments == {"from_x": 70.0, "from_y": 112.0, "to_x": 70.0, "to_y": 148.0}


def test_browsergym_size_relation_drag_uses_observed_geometry_over_dom_shortcut() -> None:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    source = Affordance(
        "source",
        Surface.DOM,
        "generic",
        "source",
        "drag",
        {
            "backend_handle": "source",
            "bbox": [10, 20, 20, 20],
            "relation_geometry": "relative_size",
        },
        lease,
        state={"relative_size": "smallest"},
    )
    destination = Affordance(
        "destination",
        Surface.DOM,
        "generic",
        "destination",
        "drag",
        {
            "backend_handle": "destination",
            "bbox": [100, 80, 80, 60],
            "relation_geometry": "relative_size",
        },
        lease,
        state={"relative_size": "largest"},
    )

    action = BrowserGymGestureEncoder().encode(GestureBinding(source=source, destination=destination))

    assert action == BrowserGymAction(
        "mouse_drag_and_drop",
        {"from_x": 20.0, "from_y": 30.0, "to_x": 140.0, "to_y": 110.0},
    )


def test_browsergym_visual_drag_falls_back_to_viewport_geometry() -> None:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    source = Affordance(
        "visual-source",
        Surface.VISUAL,
        "region",
        "small box",
        "drag",
        {"bbox": [10, 20, 20, 20]},
        lease,
    )
    destination = Affordance(
        "visual-destination",
        Surface.VISUAL,
        "region",
        "large box",
        "drag",
        {"bbox": [100, 80, 80, 60]},
        lease,
    )

    action = BrowserGymGestureEncoder().encode(GestureBinding(source=source, destination=destination))

    assert action.name == "mouse_drag_and_drop"
    assert action.arguments == {
        "from_x": 20.0,
        "from_y": 30.0,
        "to_x": 140.0,
        "to_y": 110.0,
    }


def test_browsergym_single_calendar_slot_uses_distinct_boundary_pointer_motion() -> None:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    source = Affordance(
        "slot-start",
        Surface.DOM,
        "time_slot",
        "8:00am calendar slot",
        "drag",
        {
            "backend_handle": "slot-16",
            "bbox": [10, 20, 100, 20],
            "calendar_endpoint": "start",
        },
        lease,
    )
    destination = Affordance(
        "slot-end",
        Surface.DOM,
        "time_slot_end",
        "8:00am calendar slot end boundary",
        "drop",
        {
            "backend_handle": "slot-16",
            "bbox": [10, 20, 100, 20],
            "calendar_endpoint": "end",
        },
        lease,
        state={"accepts_drop": True},
    )

    action = BrowserGymGestureEncoder().encode(GestureBinding(source=source, destination=destination))

    assert action == BrowserGymAction(
        "mouse_drag_and_drop",
        {
            "from_x": 60.0,
            "from_y": 25.0,
            "to_x": 60.0,
            "to_y": 35.0,
            "from_bid": "slot-16",
            "to_bid": "slot-16",
        },
    )


def test_browsergym_sortable_drag_uses_trailing_half_of_a_lower_target() -> None:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    source = Affordance(
        "dom_li_3",
        Surface.DOM,
        "listitem",
        "Lyssa",
        "drag",
        {"bid": "source", "bbox": [10, 100, 120, 24]},
        lease,
    )
    anchor = Affordance(
        "dom_li_5",
        Surface.DOM,
        "listitem",
        "Carissa",
        "drag",
        {"bid": "anchor", "bbox": [10, 160, 120, 24]},
        lease,
    )

    action = BrowserGymGestureEncoder().encode(GestureBinding(source=source, destination=anchor))

    assert action.arguments == {
        "from_x": 70.0,
        "from_y": 112.0,
        "to_x": 70.0,
        "to_y": 178.0,
    }


def test_browsergym_sortable_drag_uses_trailing_half_for_bottom_position() -> None:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    source = Affordance(
        "dom_li_2",
        Surface.DOM,
        "listitem",
        "Audry",
        "drag",
        {"bid": "source", "bbox": [10, 70, 120, 24], "sortable_index": 2, "sortable_count": 5},
        lease,
    )
    last = Affordance(
        "dom_li_5",
        Surface.DOM,
        "listitem",
        "Jane",
        "drag",
        {"bid": "last", "bbox": [10, 160, 120, 24], "sortable_index": 5, "sortable_count": 5},
        lease,
    )

    action = BrowserGymGestureEncoder().encode(GestureBinding(source=source, destination=last))

    assert action.arguments["to_y"] == 178.0


class FakeVisualGrounder:
    provider = "test"
    model = "test-vision"
    prompt_version = "test-v1"

    def ground(self, request: Any) -> VisualGroundingPoint:
        assert request.image_size == (200, 100)
        return VisualGroundingPoint((0.25, 0.5), normalized=True)


class FakeVisualRegionProposer:
    provider = "test"
    model = "test-vision"
    prompt_version = "test-region-v1"

    def propose(self, request: Any) -> list[VisualRegion]:
        assert "smaller box" in request.instruction
        return [
            VisualRegion((0.1, 0.2, 0.2, 0.2), "smaller box", 0.9),
            VisualRegion((0.5, 0.1, 0.4, 0.6), "larger box", 0.9),
        ]


class RateLimitedVisualRegionProposer:
    provider = "test"
    model = "test-vision"
    prompt_version = "test-region-v1"

    def propose(self, request: Any) -> list[VisualRegion]:
        del request
        raise ProviderModelError(ProviderFailureKind.RATE_LIMIT_TRANSIENT, retry_after_s=30.0)


def test_browsergym_observer_fuses_visual_drag_regions_with_mixed_dom(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (200).to_bytes(4, "big") + (100).to_bytes(4, "big")

    class MixedPage:
        url = "http://fixture/drag-box"

        def content(self) -> str:
            return '<canvas></canvas><button bid="submit">Submit</button>'

        def screenshot(self, **kwargs: Any) -> bytes:
            if kwargs.get("path"):
                Path(kwargs["path"]).write_bytes(png)
            return png

    requirements = PerceptionRequirements(
        required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
        acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.VISUAL}),
        model_call_budget=1,
    )
    fused = _browsergym_session(
        cast(Any, MixedPage()),
        dom_executor="browsergym",
        visual_executor="browsergym",
        lease_ttl_ms=60_000,
        perception_orchestrator=GenericPerceptionOrchestrator(FakeVisualRegionProposer()),
    ).capture(
        screenshot_path=str(tmp_path / "drag-box.png"),
        perception_requirements=requirements,
        task_terms=("drag", "smaller", "box", "larger"),
        task_instruction="Drag the smaller box completely inside the larger box",
    )

    assert [(item.label, item.action) for item in fused.affordance_model.affordances] == [
        ("Submit", "click"),
        ("smaller box", "drag"),
        ("larger box", "drag"),
    ]
    assert {item.label for item in fused.unified_affordances} == {
        "Submit",
        "smaller box",
        "larger box",
    }
    assert all(item.is_current(fused.observation) for item in fused.grounding_candidates)


def test_browsergym_observer_preserves_typed_visual_provider_failure(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (200).to_bytes(4, "big") + (100).to_bytes(4, "big")

    class CanvasPage:
        url = "http://fixture/drag-box"

        def content(self) -> str:
            return "<canvas></canvas>"

        def screenshot(self, **kwargs: Any) -> bytes:
            if kwargs.get("path"):
                Path(kwargs["path"]).write_bytes(png)
            return png

    session = _browsergym_session(
        cast(Any, CanvasPage()),
        dom_executor="browsergym",
        visual_executor="browsergym",
        lease_ttl_ms=60_000,
        perception_orchestrator=GenericPerceptionOrchestrator(RateLimitedVisualRegionProposer()),
    )

    with pytest.raises(ProviderModelError, match="rate_limit_transient"):
        session.capture(
            screenshot_path=str(tmp_path / "drag-box-429.png"),
            perception_requirements=PerceptionRequirements(
                required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
                acceptable_evidence=frozenset({GroundingSource.VISUAL}),
                model_call_budget=1,
            ),
            task_terms=("drag", "smaller", "inside", "larger"),
        )


def test_browsergym_observer_materializes_visual_grounding_before_contract_binding(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (200).to_bytes(4, "big") + (100).to_bytes(4, "big")

    class CanvasPage:
        url = "http://fixture/visual"

        def content(self) -> str:
            return "<main><canvas></canvas></main>"

        def screenshot(self, **kwargs: Any) -> bytes:
            if kwargs.get("path"):
                Path(kwargs["path"]).write_bytes(png)
            return png

    grounded = _browsergym_session(
        cast(Any, CanvasPage()),
        dom_executor="browsergym",
        visual_executor="browsergym",
        perception_orchestrator=GenericPerceptionOrchestrator(point_grounder=FakeVisualGrounder()),
    ).capture(
        screenshot_path=str(tmp_path / "view.png"),
        perception_requirements=PerceptionRequirements(
            required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
            acceptable_evidence=frozenset({GroundingSource.VISUAL}),
            model_call_budget=1,
        ),
        task_instruction="Click the target",
    )

    assert grounded.affordance_model.affordances[0].action == "point_activate"
    assert grounded.grounding_candidates[0].payload.point_xy == (50.0, 50.0)
    assert grounded.grounding_candidates[0].is_current(grounded.observation)


def test_browsergym_observer_retries_one_transient_coherent_epoch_drift(tmp_path: Path) -> None:
    model = browsergym_dom_adapter().transduce(
        "<button bid='target'>Target</button>", environment_revision="rev-1", snapshot_id="snap-1"
    )
    snapshot = BrowserSnapshot(
        Observation("rev-1", snapshot_id="snap-1", page_revision=model.page_revision),
        model,
    )

    class DriftThenSnapshotSession:
        calls = 0

        def capture(self, **kwargs: Any) -> BrowserSnapshot:
            del kwargs
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("coherent observation epoch drifted during multi-source capture")
            return snapshot

        def bounding_boxes_for_selectors(
            self, bindings: dict[str, str]
        ) -> dict[str, tuple[float, float, float, float]]:
            del bindings
            return {}

    session = DriftThenSnapshotSession()
    observer = BrowserGymObserver(session, BrowserGymEpisodeState("retry", 0, "Click target", {}, {}), tmp_path)

    observed = observer.capture()

    assert session.calls == 2
    assert observed.observation.metadata["browsergym"]["capture_attempt"] == 2


def test_browsergym_drag_geometry_refreshes_dom_grounding_candidate(tmp_path: Path) -> None:
    model = browsergym_dom_adapter().transduce(
        '<li bid="source" class="ui-sortable-handle">Source</li>'
        '<li bid="renamed" class="ui-sortable-handle">Renamed</li>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )

    class GeometrySession:
        def bounding_boxes_for_selectors(
            self, bindings: dict[str, str]
        ) -> dict[str, tuple[float, float, float, float]]:
            assert bindings == {
                "source": "[bid='source']",
                "renamed": "[bid='renamed']",
            }
            return {
                "source": (10.0, 20.0, 100.0, 24.0),
                "renamed": (10.0, 50.0, 100.0, 24.0),
            }

    observer = BrowserGymObserver(GeometrySession(), BrowserGymEpisodeState("drag", 0, "Drag source", {}, {}), tmp_path)
    enriched = observer._attach_drag_geometry(BrowserSnapshot(observation, model))

    affordance = enriched.affordance_model.affordances[0]
    assert affordance.locator["bbox"] == [10.0, 20.0, 100.0, 24.0]
    assert [item.state["collection_position"] for item in enriched.affordance_model.affordances] == [1, 2]
    assert [item.state["collection_cardinality"] for item in enriched.affordance_model.affordances] == [2, 2]
    assert enriched.grounding_candidates[0].target_fingerprint == affordance.target_fingerprint
    assert enriched.grounding_candidates[0].is_current(enriched.observation)
    assert (
        enriched.observation.target_fingerprints[enriched.grounding_candidates[0].fingerprint_key]
        == affordance.target_fingerprint
    )


def test_browsergym_drag_geometry_adds_semantic_relative_size_without_coordinates(tmp_path: Path) -> None:
    model = browsergym_dom_adapter().transduce(
        '<div bid="small" class="ui-draggable-handle">s</div><div bid="large" class="ui-draggable-handle">L</div>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )

    class GeometrySession:
        def bounding_boxes_for_selectors(
            self, bindings: dict[str, str]
        ) -> dict[str, tuple[float, float, float, float]]:
            assert bindings == {"small": "[bid='small']", "large": "[bid='large']"}
            return {
                "small": (10.0, 20.0, 20.0, 20.0),
                "large": (0.0, 0.0, 80.0, 80.0),
            }

    observer = BrowserGymObserver(
        GeometrySession(), BrowserGymEpisodeState("drag", 0, "Drag smaller inside larger", {}, {}), tmp_path
    )
    enriched = observer._attach_drag_geometry(BrowserSnapshot(observation, model))

    assert [item.state["relative_size"] for item in enriched.affordance_model.affordances] == [
        "smallest",
        "largest",
    ]
    assert enriched.affordance_model.affordances[0].state["inside_largest"] is True


def test_generalist_browsergym_adapter_binds_screenshot_only_target_without_exposing_coordinates(
    tmp_path: Path,
) -> None:
    screenshot = tmp_path / "view.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (200).to_bytes(4, "big") + (100).to_bytes(4, "big"))
    model = browsergym_dom_adapter().transduce(
        "<main>canvas</main>", environment_revision="rev-1", snapshot_id="snap-1"
    )
    observation = Observation(
        "rev-1", screenshot_ref=str(screenshot), snapshot_id="snap-1", page_revision=model.page_revision
    )
    visual = _visual_fallback_affordance(BrowserSnapshot(observation, model))

    assert visual is not None
    assert "x" not in visual.locator and "y" not in visual.locator
    visual = replace(
        visual,
        locator={**visual.locator, "center": [50.0, 50.0]},
        confidence=1.0,
        lease=replace(visual.lease, confidence=1.0),
    )
    snapshot = _fuse_visual_candidates(
        BrowserSnapshot(
            replace(observation, target_fingerprints={visual.id: visual.target_fingerprint}),
            model,
            source_observations=(
                SourceObservation(GroundingSource.DOM, "dom", "snap-1", "rev-1", model.page_revision),
                SourceObservation(GroundingSource.VISUAL, "screenshot", "snap-1", "rev-1", model.page_revision),
            ),
        ),
        [visual],
        (200, 100),
    )
    state = StateKernel("task-1", "Click the visual target")
    remember_observation(state, snapshot.observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click the visual target",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(
            ("Current screenshot visual target",), OperationClass.READ_ONLY, "test", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("Current screenshot visual target",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="visual",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.POINT_ACTIVATE,
        target_affordance_id=snapshot.unified_affordances[0].semantic_target_id,
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, snapshot)

    assert contract.parameters["action"] == {"name": "mouse_click", "arguments": {"x": 50.0, "y": 50.0}}
    assert contract.grounding_candidate is not None


def test_visual_fallback_fingerprint_tracks_pixels_not_observation_filename(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (20).to_bytes(4, "big") + (10).to_bytes(4, "big")
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    first.write_bytes(png)
    second.write_bytes(png)
    model = browsergym_dom_adapter().transduce("<main>canvas</main>", environment_revision="rev-1")
    first_target = _visual_fallback_affordance(
        BrowserSnapshot(Observation("rev-1", screenshot_ref=str(first), page_revision=model.page_revision), model)
    )
    second_target = _visual_fallback_affordance(
        BrowserSnapshot(Observation("rev-1", screenshot_ref=str(second), page_revision=model.page_revision), model)
    )

    assert first_target is not None and second_target is not None
    assert first_target.target_fingerprint == second_target.target_fingerprint


def test_browsergym_select_collapses_a_transient_overlay_after_success() -> None:
    class Keyboard:
        pressed: list[str] = []

        def press(self, key: str) -> None:
            self.pressed.append(key)

    class Page:
        keyboard = Keyboard()

    class SelectEnvironment:
        page = Page()

        @property
        def unwrapped(self) -> "SelectEnvironment":
            return self

        def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
            assert action == "select_option('select-bid', 'earth')"
            return {"last_action_error": ""}, 0.0, False, False, {}

    environment = SelectEnvironment()
    episode = BrowserGymEpisodeState("choose-list", 0, "Choose Earth", {}, {})
    contract = ActionContract(
        "contract-select",
        "Choose Earth",
        "dom_select_1",
        "select_option",
        "browsergym",
        "rev-1",
        {},
        parameters={
            "action": {
                "name": "select_option",
                "arguments": {"bid": "select-bid", "options": "earth"},
            }
        },
    )

    receipt = BrowserGymExecutor(environment, episode).execute(contract, Observation("rev-1"))

    assert receipt.success is True
    assert receipt.evidence["select_overlay_cleanup"] is True
    assert environment.page.keyboard.pressed == ["Escape"]


def test_browsergym_click_scrolls_current_bid_before_standard_dispatch() -> None:
    class Page:
        evaluations: list[tuple[str, str]] = []

        def evaluate(self, expression: str, bid: str) -> bool:
            self.evaluations.append((expression, bid))
            return True

    class ClickEnvironment:
        page = Page()

        @property
        def unwrapped(self) -> "ClickEnvironment":
            return self

        def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
            assert action == "click('target-bid')"
            return {"last_action_error": ""}, 0.0, False, False, {}

    environment = ClickEnvironment()
    episode = BrowserGymEpisodeState("collection", 0, "Click current item", {}, {})
    contract = ActionContract(
        "contract-click",
        "Click current item",
        "semantic:item",
        "activate",
        "browsergym",
        "rev-1",
        {},
        parameters={"action": {"name": "click", "arguments": {"bid": "target-bid"}}},
    )

    receipt = BrowserGymExecutor(environment, episode).execute(contract, Observation("rev-1"))

    assert receipt.success is True
    assert environment.page.evaluations[0][1] == "target-bid"
    assert "scrollIntoView" in environment.page.evaluations[0][0]
    assert receipt.evidence["direct_dispatch"] == {"scrolled": True}


def test_browsergym_mouse_click_uses_direct_pointer_lifecycle() -> None:
    class Mouse:
        clicks: list[tuple[float, float, str]] = []

        def click(self, x: float, y: float, *, button: str) -> None:
            self.clicks.append((x, y, button))

    class Page:
        mouse = Mouse()

    class PointerEnvironment:
        page = Page()
        last_action = ""

        @property
        def unwrapped(self) -> "PointerEnvironment":
            return self

        def pre_step(self) -> tuple[dict[str, Any], None, None]:
            return {}, None, None

        def post_step(self, info: dict[str, Any]) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
            return {"last_action_error": ""}, 1.0, True, False, info

    environment = PointerEnvironment()
    episode = BrowserGymEpisodeState("grid-coordinate", 0, "Click a point", {}, {})
    contract = ActionContract(
        "contract-point",
        "Click a point",
        "svg_circle_1",
        "point_activate",
        "browsergym",
        "rev-1",
        {},
        parameters={"action": {"name": "mouse_click", "arguments": {"x": 124.0, "y": 244.0}}},
    )

    receipt = BrowserGymExecutor(environment, episode).execute(contract, Observation("rev-1"))

    assert receipt.success is True
    assert receipt.evidence["browsergym_action"] == ["direct_pointer_click"]
    assert environment.page.mouse.clicks == [(124.0, 244.0, "left")]
    assert environment.last_action == "direct_pointer_click"


def test_browsergym_bid_bound_range_drag_dispatches_current_dom_event_lifecycle() -> None:
    class Mouse:
        calls: list[str] = []

        def move(self, *_args: Any, **_kwargs: Any) -> None:
            self.calls.append("move")

        def down(self, **_kwargs: Any) -> None:
            self.calls.append("down")

        def up(self, **_kwargs: Any) -> None:
            self.calls.append("up")

    class Page:
        mouse = Mouse()
        evaluations: list[tuple[str, dict[str, str]]] = []

        def evaluate(self, expression: str, payload: dict[str, str]) -> bool:
            self.evaluations.append((expression, payload))
            return True

    class RangeEnvironment:
        page = Page()
        last_action = ""

        @property
        def unwrapped(self) -> "RangeEnvironment":
            return self

        def pre_step(self) -> tuple[dict[str, Any], None, None]:
            return {}, None, None

        def post_step(self, info: dict[str, Any]) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
            return {"last_action_error": ""}, 0.0, False, False, info

    environment = RangeEnvironment()
    episode = BrowserGymEpisodeState("daily-calendar", 0, "Create event", {}, {})
    contract = ActionContract(
        "contract-range",
        "Create event",
        "slot-start",
        "drag",
        "browsergym",
        "rev-1",
        {},
        parameters={
            "action": {
                "name": "mouse_drag_and_drop",
                "arguments": {
                    "from_x": 10.0,
                    "from_y": 20.0,
                    "to_x": 10.0,
                    "to_y": 40.0,
                    "from_bid": "slot-24",
                    "to_bid": "slot-26",
                },
            }
        },
    )

    receipt = BrowserGymExecutor(environment, episode).execute(contract, Observation("rev-1"))

    assert receipt.success is True
    assert environment.page.evaluations[0][1] == {"fromBid": "slot-24", "toBid": "slot-26"}
    assert environment.page.mouse.calls == []
    assert environment.last_action == "direct_pointer_drag"


def test_browsergym_navigation_safe_click_uses_direct_lifecycle() -> None:
    class Page:
        calls: list[tuple[str, str]] = []
        mouse = object()

        def evaluate(self, expression: str, bid: str) -> None:
            self.calls.append((expression, bid))

    class LinkEnvironment:
        page = Page()
        last_action = ""

        @property
        def unwrapped(self) -> "LinkEnvironment":
            return self

        def pre_step(self) -> tuple[dict[str, Any], None, None]:
            return {}, None, None

        def post_step(self, info: dict[str, Any]) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
            return {"last_action_error": ""}, 1.0, True, False, info

    environment = LinkEnvironment()
    episode = BrowserGymEpisodeState("search-engine", 0, "Open result", {}, {})
    contract = ActionContract(
        "contract-link",
        "Open result",
        "result",
        "activate",
        "browsergym",
        "rev-1",
        {},
        parameters={"action": {"name": "click_no_navigation", "arguments": {"bid": "28"}}},
    )

    receipt = BrowserGymExecutor(environment, episode).execute(contract, Observation("rev-1"))

    assert receipt.success is True
    assert receipt.evidence["browsergym_action"] == ["direct_click_no_navigation"]
    assert environment.page.calls[0][1] == "28"
    assert environment.last_action == "direct_click_no_navigation"


def test_generalist_browsergym_adapter_binds_semantic_key_press() -> None:
    model = browsergym_dom_adapter().transduce(
        '<span bid="slider" class="ui-slider-handle" tabindex="0"></span>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        metadata={"control_states": {"slider": {"aria_valuenow": "1"}}},
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Increase slider")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Increase slider",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("slider",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("slider",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="press",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id="dom_span_1",
        parameters={"key": "ArrowRight"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))

    assert contract.action == "press"
    assert contract.parameters["action"] == {"name": "press", "arguments": {"bid": "slider", "key_comb": "ArrowRight"}}
    receipt = ExecutionReceipt(
        "contract", "browsergym", True, "rev-1", "rev-2", 1.0, evidence={"last_action_error": ""}
    )
    report = VerifierLadder().verify_report(
        contract.verifier_plan,
        receipt,
        Observation("rev-2", metadata={"control_states": {"slider": {"aria_valuenow": "2"}}}),
    )

    assert contract.verifier_plan[-1] == VerifierSpec(
        "control_state",
        "slider",
        {"field": "aria_valuenow", "changed_from": "1"},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )
    assert report.passed is True


def test_generalist_browsergym_scroll_press_verifies_scroll_top_delta() -> None:
    model = browsergym_dom_adapter().transduce(
        '<textarea bid="source">Long text</textarea>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    source = model.affordances[0]
    scroll_region = replace(source, id=f"{source.id}_scroll", role="scroll_region", action="press")
    model = replace(model, affordances=[source, scroll_region])
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        metadata={"control_states": {"source": {"scroll_top": 120, "scroll_height": 300, "client_height": 100}}},
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Scroll to top")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Scroll to top",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements((scroll_region.label,), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs((scroll_region.label,)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="press-scroll",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id="dom_textarea_1_scroll",
        parameters={"key": "Control+Home"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))
    receipt = ExecutionReceipt(
        "contract", "browsergym", True, "rev-1", "rev-2", 1.0, evidence={"last_action_error": ""}
    )
    report = VerifierLadder().verify_report(
        contract.verifier_plan,
        receipt,
        Observation(
            "rev-2",
            metadata={"control_states": {"source": {"scroll_top": 0, "scroll_height": 300, "client_height": 100}}},
        ),
    )

    assert contract.parameters["action"] == {
        "name": "press",
        "arguments": {"bid": "source", "key_comb": "Control+Home"},
    }
    assert contract.verifier_plan[-1] == VerifierSpec(
        "control_state",
        "source",
        {"field": "scroll_top", "changed_from": 120},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )
    assert report.passed is True


def test_generalist_browsergym_text_contract_verifies_post_observation_value() -> None:
    model = browsergym_dom_adapter().transduce(
        '<input bid="text-bid" value="">',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Enter Myron")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter Myron",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("text",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("text",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="type",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="dom_input_1",
        parameters={"text": "Myron"},
    )
    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))
    receipt = ExecutionReceipt(
        "contract", "browsergym", True, "rev-1", "rev-2", 1.0, evidence={"last_action_error": ""}
    )

    passed = VerifierLadder().verify_report(
        contract.verifier_plan, receipt, Observation("rev-2", metadata={"html": '<input bid="text-bid" value="Myron">'})
    )
    failed = VerifierLadder().verify_report(
        contract.verifier_plan, receipt, Observation("rev-2", metadata={"html": '<input bid="text-bid" value="">'})
    )

    assert passed.passed is True
    assert failed.passed is False


def test_generalist_browsergym_search_contract_uses_keyboard_events() -> None:
    model = browsergym_dom_adapter().transduce(
        '<input bid="search-bid" placeholder="Search" value="">',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    model = replace(
        model,
        affordances=[replace(model.affordances[0], state={**model.affordances[0].state, "focused": True})],
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Search for Ryann")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Search for Ryann",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("search",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("search",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="type",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="dom_input_1",
        parameters={"text": "Ryann"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))

    assert contract.parameters["action"] == {
        "name": "type_text_with_events",
        "arguments": {"bid": "search-bid", "text": "Ryann"},
    }


def test_generalist_browsergym_date_contract_uses_native_iso_value() -> None:
    model = browsergym_dom_adapter().transduce(
        '<input bid="date-bid" type="date">',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Enter 02/04/2012 as the date")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter 02/04/2012 as the date",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("date",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("date",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="date",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="dom_input_1",
        parameters={"text": "02/04/2012"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))

    assert contract.parameters["action"] == {
        "name": "fill",
        "arguments": {"bid": "date-bid", "value": "2012-02-04"},
    }
    assert contract.verifier_plan[-1] == VerifierSpec(
        "dom_attribute",
        "date-bid",
        {"target_attribute": "bid", "attribute": "value", "value": "2012-02-04"},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )


def test_generalist_browsergym_time_contract_uses_native_24_hour_value() -> None:
    model = browsergym_dom_adapter().transduce(
        '<input bid="time-bid" type="time">',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Enter 11:10 AM as the time")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter 11:10 AM as the time",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("time",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("time",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="time",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="dom_input_1",
        parameters={"text": "11:10 AM"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(
        proposal,
        task,
        state,
        BrowserSnapshot(observation, model),
    )

    assert contract.parameters["action"] == {
        "name": "fill",
        "arguments": {"bid": "time-bid", "value": "11:10"},
    }
    assert contract.verifier_plan[-1] == VerifierSpec(
        "dom_attribute",
        "time-bid",
        {"target_attribute": "bid", "attribute": "value", "value": "11:10"},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )


def test_generalist_browsergym_click_requires_state_delta_or_positive_terminal_oracle() -> None:
    model = browsergym_dom_adapter().transduce(
        '<button bid="target">Target</button>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Click target")
    remember_observation(state, observation)
    task = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click target",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("target",), OperationClass.READ_ONLY, "test", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("target",)),
        success=_task_success("requirement:effect:1"),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="click",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snap-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_button_1",
    )
    contract = GeneralistBrowserGymContractBuilder().build(proposal, task, state, BrowserSnapshot(observation, model))
    unchanged = ExecutionReceipt(
        "contract",
        "browsergym",
        True,
        "rev-1",
        "rev-1",
        1.0,
        evidence={"last_action_error": "", "terminated": False, "official_reward": 0.0},
    )
    terminal = ExecutionReceipt(
        "contract",
        "browsergym",
        True,
        "rev-1",
        "rev-1",
        1.0,
        evidence={
            "last_action_error": "",
            "terminated": True,
            "truncated": False,
            "official_reward": 1.0,
            "terminal_success": True,
        },
    )

    assert contract.verifier_plan[-1].kind == "state_delta_or_terminal"
    assert VerifierLadder().verify_report(contract.verifier_plan, unchanged, Observation("rev-1")).passed is False
    assert VerifierLadder().verify_report(contract.verifier_plan, unchanged, Observation("rev-2")).passed is True
    assert VerifierLadder().verify_report(contract.verifier_plan, terminal, Observation("rev-1")).passed is True


def test_browsergym_generalist_context_uses_the_episode_action_budget() -> None:
    limits = PlannerLimits(max_steps=50, max_observations=153, max_recoveries=3, max_effectful_actions=51)
    planner = BrowserGymGeneralistPlanner(
        model=cast(ModelPort, object()),
        episode=BrowserGymEpisodeState("form-sequence", 0, "Set a slider", {}, {}),
        config=ModelConfig(),
        limits=limits,
    )

    assert planner._planner.limits == limits
    assert planner._planner.allow_finish is False


def test_browsergym_profiles_and_report_expose_coverage_without_silent_omission(tmp_path: Path) -> None:
    tasks = tuple(f"task-{index:02d}" for index in range(35))
    nightly_tasks, nightly_seeds = browsergym_profile(tasks, "nightly")
    expected_nightly_tasks = tuple(task for family in NIGHTLY_ACTION_FAMILIES.values() for task in family)
    assert nightly_tasks == expected_nightly_tasks
    assert len(nightly_tasks) == 30
    assert len(NIGHTLY_ACTION_FAMILIES) == 10
    assert {len(tasks) for tasks in NIGHTLY_ACTION_FAMILIES.values()} == {3}
    assert nightly_seeds == tuple(range(10))
    release_tasks, release_seeds = browsergym_profile(tasks, "release")
    assert release_tasks == tasks
    assert release_seeds == tuple(range(5))

    report = write_browsergym_report(
        tmp_path,
        profile="nightly",
        registered_tasks=tasks,
        selected_tasks=nightly_tasks,
        seeds=(0,),
        episodes=[],
    )
    assert report["browsergym_version"] == BROWSERGYM_VERSION
    assert report["run_protocol_version"] == "three-layer-breadth-first-audit-v2"
    assert report["miniwob_commit"] == BROWSERGYM_MINIWOB_COMMIT
    assert report["nightly_manifest_version"] == NIGHTLY_MANIFEST_VERSION
    assert report["nightly_action_families"] == {
        family: list(family_tasks) for family, family_tasks in NIGHTLY_ACTION_FAMILIES.items()
    }
    assert report["task_manifest_version"] == NIGHTLY_MANIFEST_VERSION
    assert report["task_action_families"] == report["nightly_action_families"]
    assert BROWSERGYM_PLANNER_MAX_TOKENS == 384
    assert report["expected_episode_count"] == 30
    assert report["execution_order"][:3] == [
        "click-button:seed-0",
        "click-checkboxes:seed-0",
        "click-dialog:seed-0",
    ]
    assert report["failure_envelopes"] == []
    assert report["failure_clusters"] == []
    assert report["missing_episode_count"] == 30
    assert len(report["missing_episode_ids"]) == 30
    assert report["acceptance_errors"] == ["missing episodes: 30"]
    assert report["runtime_error_counts"] == {}
    assert report["official_track"] is True
    assert report["fault_injection"] is False


def test_browsergym_smoke_profile_is_the_six_pr_tasks_at_one_seed() -> None:
    tasks, seeds = browsergym_profile(PR_SMOKE_TASKS, "smoke")

    assert tasks == PR_SMOKE_TASKS
    assert seeds == (0,)


def test_browsergym_diagnostic_and_nightly_schedule_are_breadth_first() -> None:
    diagnostic_tasks, diagnostic_seeds = browsergym_profile(PR_SMOKE_TASKS, "diagnostic")

    assert diagnostic_tasks == tuple(task for tasks in NIGHTLY_ACTION_FAMILIES.values() for task in tasks)
    assert diagnostic_seeds == (0, 1)
    assert browsergym_episode_schedule(("a", "b", "c"), (0, 1)) == (
        ("a", 0),
        ("b", 0),
        ("c", 0),
        ("a", 1),
        ("b", 1),
        ("c", 1),
    )


def test_failure_envelopes_cluster_ordinary_failures_without_circuit_breaking() -> None:
    first = BrowserGymEpisodeResult(
        "enter-text", 0, "done", False, 0.0, True, False, 2, ["fill"], [], "", False, "trace-a"
    )
    second = BrowserGymEpisodeResult(
        "enter-text", 1, "done", False, 0.0, True, False, 2, ["fill"], [], "", False, "trace-b"
    )
    envelopes = [
        browsergym_failure_envelope(first, task_family_map={"enter-text": "text_entry"}),
        browsergym_failure_envelope(second, task_family_map={"enter-text": "text_entry"}),
    ]
    concrete = [item for item in envelopes if item is not None]

    assert concrete[0]["root_layer"] == "EXECUTION"
    assert concrete[0]["required_evidence_present"] is True
    assert concrete[0]["artifact_refs"] == ["trace-a"]
    assert browsergym_batch_circuit_breaker(concrete) == ""
    assert cluster_browsergym_failure_envelopes(concrete) == [
        {
            "root_layer": "EXECUTION",
            "failure_signature": "official_reward_zero",
            "family": "text_entry",
            "episode_count": 2,
            "episode_ids": ["enter-text:seed-0", "enter-text:seed-1"],
        }
    ]


def test_failure_envelope_allows_only_batch_wide_circuit_breakers() -> None:
    provider = BrowserGymEpisodeResult(
        "click-button",
        0,
        "failed",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "provider failure: quota_exhausted",
        False,
        "",
        provider_failures=["quota_exhausted"],
    )
    source = BrowserGymEpisodeResult(
        "click-button", 1, "failed", False, 0.0, False, False, 0, [], [], "NamespaceNotFound", False, ""
    )
    provider_envelope = browsergym_failure_envelope(provider)
    source_envelope = browsergym_failure_envelope(source)

    assert provider_envelope is not None
    assert source_envelope is not None
    assert browsergym_batch_circuit_breaker([provider_envelope]) == ""
    assert (
        browsergym_batch_circuit_breaker([provider_envelope, provider_envelope])
        == "provider_unavailable_or_continuous_rate_limit"
    )
    assert browsergym_batch_circuit_breaker([source_envelope]) == "source_or_oracle_unavailable"


def test_successful_episode_prevents_later_task_local_schema_circuit_break() -> None:
    success = BrowserGymEpisodeResult(
        "click-button", 0, "done", True, 1.0, True, False, 1, ["click"], [], "", False, ""
    )
    local_schema_failure = BrowserGymEpisodeResult(
        "scroll-text",
        0,
        "failed",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "StructuredModelError: proposal_done_kind:type_text",
        False,
        "",
    )
    envelope = browsergym_failure_envelope(local_schema_failure)
    assert envelope is not None
    consecutive: list[dict[str, object]] = []

    compatible, reason = update_browsergym_batch_circuit_state(
        consecutive,
        success,
        None,
        schema_compatible_episode_observed=False,
    )
    compatible, first_reason = update_browsergym_batch_circuit_state(
        consecutive,
        local_schema_failure,
        envelope,
        schema_compatible_episode_observed=compatible,
    )
    compatible, second_reason = update_browsergym_batch_circuit_state(
        consecutive,
        local_schema_failure,
        envelope,
        schema_compatible_episode_observed=compatible,
    )

    assert compatible is True
    assert reason == first_reason == second_reason == ""
    assert consecutive == []


def test_task_local_schema_failure_breaks_provider_failure_consecutiveness() -> None:
    provider = BrowserGymEpisodeResult(
        "case-a",
        0,
        "failed",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "provider failure: 429",
        False,
        "",
        provider_failures=["rate_limit"],
    )
    local_schema = BrowserGymEpisodeResult(
        "case-b",
        0,
        "failed",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "StructuredModelError: task-local proposal validation",
        False,
        "",
    )
    provider_envelope = browsergym_failure_envelope(provider)
    schema_envelope = browsergym_failure_envelope(local_schema)
    assert provider_envelope is not None and schema_envelope is not None
    consecutive: list[dict[str, object]] = []

    compatible, _ = update_browsergym_batch_circuit_state(
        consecutive,
        provider,
        provider_envelope,
        schema_compatible_episode_observed=True,
    )
    compatible, _ = update_browsergym_batch_circuit_state(
        consecutive,
        local_schema,
        schema_envelope,
        schema_compatible_episode_observed=compatible,
    )
    _, reason = update_browsergym_batch_circuit_state(
        consecutive,
        provider,
        provider_envelope,
        schema_compatible_episode_observed=compatible,
    )

    assert reason == ""
    assert [item["failure_signature"] for item in consecutive] == ["provider_failure"]


def test_browsergym_planning_stats_project_canonical_planning_turn() -> None:
    stats = _browsergym_planning_stats(
        [
            SimpleNamespace(
                kind="PlanningTurnEvaluated",
                payload={
                    "model_stage": "action_choice_selection",
                    "grounded_target_count": 3,
                    "action_choice_count": 2,
                    "selection_source": "model_choice_id",
                },
            )
        ]
    )

    assert stats == {
        "planning_turn_count": 1,
        "model_stage": "action_choice_selection",
        "grounded_target_count": 3,
        "action_choice_count": 2,
        "selection_source": "model_choice_id",
    }


def test_browsergym_planning_stats_keep_latest_diagnostic_turn_before_terminal_done() -> None:
    stats = _browsergym_planning_stats(
        [
            SimpleNamespace(
                kind="PlanningTurnEvaluated",
                payload={
                    "model_stage": "action_choice_build",
                    "grounded_target_count": 1,
                    "action_choice_count": 1,
                    "selection_source": "runtime_unique_choice",
                    "response_status": "proposal",
                },
            ),
            SimpleNamespace(
                kind="PlanningTurnEvaluated",
                payload={
                    "model_stage": "unknown",
                    "grounded_target_count": 0,
                    "action_choice_count": 0,
                    "selection_source": "none",
                    "response_status": "done",
                },
            ),
        ]
    )

    assert stats == {
        "planning_turn_count": 2,
        "model_stage": "action_choice_build",
        "grounded_target_count": 1,
        "action_choice_count": 1,
        "selection_source": "runtime_unique_choice",
    }


def test_browsergym_planning_stats_do_not_fabricate_zero_counts_without_event() -> None:
    stats = _browsergym_planning_stats([])

    assert stats["grounded_target_count"] is None
    assert stats["action_choice_count"] is None
    assert stats["model_stage"] == "unknown"


def test_failure_envelope_classifies_planner_waiting_and_verification_separately() -> None:
    waiting = BrowserGymEpisodeResult(
        "click-link",
        0,
        "waiting_clarification",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "",
        False,
        "",
        model_stage="action_choice_selection",
        action_choice_count=2,
    )
    verification = BrowserGymEpisodeResult(
        "use-slider", 0, "failed", False, 0.0, True, False, 3, ["press"], [], "verification_failed", False, ""
    )

    waiting_envelope = browsergym_failure_envelope(waiting)
    verification_envelope = browsergym_failure_envelope(verification)

    assert waiting_envelope is not None
    assert waiting_envelope["root_layer"] == "INTENT / PLANNING"
    assert verification_envelope is not None
    assert verification_envelope["root_layer"] == "VERIFICATION"

    observation = BrowserGymEpisodeResult(
        "grid-coordinate",
        0,
        "waiting_clarification",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "",
        False,
        "",
        model_stage="observation",
    )
    observation_envelope = browsergym_failure_envelope(observation)
    assert observation_envelope is not None
    assert observation_envelope["root_layer"] == "OBSERVATION / CONTEXT"

    visual_grounding = BrowserGymEpisodeResult(
        "grid-coordinate",
        0,
        "waiting_clarification",
        False,
        0.0,
        False,
        False,
        1,
        ["mouse_click"],
        [],
        "",
        False,
        "",
        model_stage="action_choice_selection",
        action_choice_count=1,
    )
    visual_envelope = browsergym_failure_envelope(visual_grounding)
    assert visual_envelope is not None
    assert visual_envelope["failure_signature"] == "grounding_unverified"
    assert visual_envelope["root_layer"] == "GROUNDING / ROUTING"


def test_failure_envelope_does_not_misclassify_model_budget_as_schema_failure() -> None:
    exhausted = BrowserGymEpisodeResult(
        "form-sequence",
        4,
        "failed",
        False,
        0.0,
        False,
        False,
        15,
        ["press"],
        [],
        "StructuredModelError: model call budget exhausted",
        False,
        "trace-budget",
    )

    envelope = browsergym_failure_envelope(exhausted)

    assert envelope is not None
    assert envelope["failure_signature"] == "model_call_budget_exhausted"
    assert envelope["root_layer"] == "INTENT / PLANNING"
    assert browsergym_batch_circuit_breaker([envelope, envelope]) == ""


def test_browsergym_time_budgets_are_explicit_and_reserve_execution_time() -> None:
    _validate_browsergym_time_budgets(
        episode_timeout_s=150,
        model_call_timeout_s=10,
        max_model_calls=13,
        execution_reserve_s=15,
    )
    with pytest.raises(ValueError, match="exceeds episode timeout"):
        _validate_browsergym_time_budgets(
            episode_timeout_s=150,
            model_call_timeout_s=10,
            max_model_calls=14,
            execution_reserve_s=15,
        )


class StoppedPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> None:
        del request
        return None


def test_browsergym_generalist_episode_checkpoints_are_atomic_and_reject_foreign_cases(tmp_path: Path) -> None:
    assert checkpoint_filename("task/name", 0) != checkpoint_filename("task_name", 0)
    episode = BrowserGymEpisodeResult(
        task_id="click-button",
        seed=4,
        runtime_status="done",
        official_success=True,
        official_reward=1.0,
        terminated=True,
        truncated=False,
        action_count=1,
        action_families=["click"],
        unsupported_actions=[],
        runtime_error="",
        policy_stopped=False,
        trace_path="artifact/events.jsonl",
    )
    _write_browsergym_checkpoint(tmp_path, episode)
    ignored = BrowserGymEpisodeResult(
        task_id="other",
        seed=0,
        runtime_status="done",
        official_success=True,
        official_reward=1.0,
        terminated=True,
        truncated=False,
        action_count=1,
        action_families=["click"],
        unsupported_actions=[],
        runtime_error="",
        policy_stopped=False,
        trace_path="artifact/ignored.jsonl",
    )
    _write_browsergym_checkpoint(tmp_path, ignored)

    with pytest.raises(ValueError, match="outside the requested matrix"):
        _load_browsergym_checkpoints(tmp_path, {("click-button", 4)})
    ignored_path = tmp_path / checkpoint_filename(ignored.task_id, ignored.seed)
    ignored_path.unlink()
    checkpoints = _load_browsergym_checkpoints(tmp_path, {("click-button", 4)})
    assert checkpoints == {("click-button", 4): episode}
    assert not list(tmp_path.glob("*.tmp"))


def test_browsergym_checkpoint_metadata_rejects_mismatched_resume(tmp_path: Path) -> None:
    first = {"schema_version": "v1", "model": "first"}
    _prepare_browsergym_checkpoint_metadata(tmp_path, first, resume=False)
    _prepare_browsergym_checkpoint_metadata(tmp_path, first, resume=True)

    with pytest.raises(ValueError, match="metadata does not match"):
        _prepare_browsergym_checkpoint_metadata(tmp_path, {"schema_version": "v1", "model": "second"}, resume=True)
    with pytest.raises(ValueError, match="new output directory"):
        _prepare_browsergym_checkpoint_metadata(tmp_path, first, resume=False)


def test_browsergym_checkpoint_metadata_binds_selected_matrix(tmp_path: Path) -> None:
    first = {
        "schema_version": "browsergym-generalist-checkpoint-v5",
        "selected_task_ids": ["click-link", "navigate-tree"],
        "seeds": [0, 1],
    }
    _prepare_browsergym_checkpoint_metadata(tmp_path, first, resume=False)

    with pytest.raises(ValueError, match="metadata does not match"):
        _prepare_browsergym_checkpoint_metadata(
            tmp_path,
            {**first, "seeds": [0, 1, 2]},
            resume=True,
        )


def test_browsergym_checkpoint_identity_binds_distinct_intent_repair_prompt() -> None:
    identity = _intent_compiler_checkpoint_identity()

    assert identity["intent_compiler_model_config"]["prompt_version"] == "minimal-intent-proposal-v1"
    assert identity["intent_draft_repair_model_config"]["prompt_version"] == "minimal-intent-proposal-repair-v1"
    assert identity["intent_compiler_schema_sha256"] == identity["intent_draft_repair_schema_sha256"]


def test_browsergym_runtime_source_digest_changes_only_with_runtime_inputs(tmp_path: Path) -> None:
    source = tmp_path / "src" / "affordance_runtime"
    source.mkdir(parents=True)
    runtime_file = source / "runtime.py"
    runtime_file.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=first\n", encoding="utf-8")
    first = _runtime_source_sha256(tmp_path)

    (tmp_path / ".env").write_text("SECRET=second\n", encoding="utf-8")
    assert _runtime_source_sha256(tmp_path) == first

    runtime_file.write_text("VALUE = 2\n", encoding="utf-8")
    assert _runtime_source_sha256(tmp_path) != first


@pytest.mark.parametrize("profile", ["nightly", "release"])
def test_browsergym_frozen_profiles_reject_dirty_worktrees(profile: str) -> None:
    with pytest.raises(ValueError, match=f"Frozen {profile} requires a clean committed worktree"):
        _require_frozen_profile_identity(
            cast(Any, profile),
            {
                "git_sha": "abc",
                "working_tree_clean": False,
                "source_tree_sha256": "sha256:runtime",
            },
        )


def test_browsergym_diagnostic_profile_allows_source_bound_dirty_worktree() -> None:
    _require_frozen_profile_identity(
        "diagnostic",
        {
            "git_sha": "abc",
            "working_tree_clean": False,
            "source_tree_sha256": "sha256:runtime",
        },
    )


def test_browsergym_dirty_frozen_profile_fails_before_source_server_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        browsergym_module,
        "_frozen_run_identity",
        lambda: {
            "git_sha": "abc",
            "working_tree_clean": False,
            "source_tree_sha256": "sha256:runtime",
        },
    )

    def fail_if_called(_path: Path) -> Path:
        raise AssertionError("source preparation must not run")

    monkeypatch.setattr(browsergym_module, "ensure_browsergym_miniwob", fail_if_called)

    with pytest.raises(ValueError, match="Frozen nightly requires a clean committed worktree"):
        browsergym_module.run_browsergym_miniwob_generalist_suite(
            tmp_path,
            profile="nightly",
            model=cast(Any, object()),
        )


def test_browsergym_checkpoint_loader_ignores_matrix_metadata(tmp_path: Path) -> None:
    _prepare_browsergym_checkpoint_metadata(tmp_path, {"schema_version": "v1"}, resume=False)

    assert _load_browsergym_checkpoints(tmp_path, {("click-button", 0)}) == {}


def test_browsergym_cleanup_does_not_replace_a_prior_failure() -> None:
    class BrokenClose:
        def close(self) -> None:
            raise RuntimeError("already disposed")

    _close_quietly(BrokenClose())
