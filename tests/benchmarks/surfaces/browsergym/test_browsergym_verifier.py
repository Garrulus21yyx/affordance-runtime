import asyncio

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.external_smoke.case_environment import (
    BrowserGymCaseEnvironment,
    ExternalEnvironmentTaskEvaluator,
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.benchmarks.external_smoke.verifier_policy import (
    classify_browsergym_verifier,
    verifier_snapshot,
)
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.evaluation import (
    ProductionActionEvaluator,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
)
from tests.integration.agent.test_agent_loop import ScriptedPolicy
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
    request_for,
    start_environment,
)


def _open_fake_case(fake: FakeBrowserGym):
    surface, task = open_fake(fake)
    return BrowserGymCaseEnvironment(surface.task_id, surface.surface, surface.world), task


def test_official_verifier_status_mapping_is_strict() -> None:
    common = dict(task_run_id="run:1", observation_id="obs:1", source_observation_id="obs:1")
    success = verifier_snapshot(
        **common,
        source=VerifierFactSource.POST_ACTION,
        reward=1.0,
        terminated=True,
        truncated=False,
        task_info={"RAW_REWARD_GLOBAL": 1, "DONE_GLOBAL": True, "TASK_READY": True},
    )
    incomplete = verifier_snapshot(
        **common,
        source=VerifierFactSource.POST_ACTION,
        reward=0.0,
        terminated=False,
        truncated=False,
        task_info={"RAW_REWARD_GLOBAL": 0, "DONE_GLOBAL": False, "TASK_READY": True},
    )
    unavailable = verifier_snapshot(
        **common,
        source=VerifierFactSource.POST_ACTION,
        reward=1.0,
        terminated=False,
        truncated=False,
        task_info={"RAW_REWARD_GLOBAL": 1, "DONE_GLOBAL": False, "TASK_READY": True},
    )
    failure = verifier_snapshot(
        **common,
        source=VerifierFactSource.POST_ACTION,
        reward=0.0,
        terminated=True,
        truncated=False,
        task_info={"RAW_REWARD_GLOBAL": -1, "DONE_GLOBAL": True, "TASK_READY": True},
    )
    assert success.status is ExternalVerifierStatus.SUCCESS and success.evidence_refs[0].startswith("artifact:")
    assert incomplete.status is ExternalVerifierStatus.INCOMPLETE and not incomplete.evidence_refs
    assert unavailable.status is ExternalVerifierStatus.UNAVAILABLE
    assert failure.status is ExternalVerifierStatus.TERMINAL_TASK_FAILURE
    assert failure.evidence_refs[0].endswith(f":{BROWSERGYM_TASK_STATE_EVIDENCE_KEY}")


_ARBITRARY = st.one_of(
    st.sampled_from(tuple(VerifierFactSource)),
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=8),
    st.lists(st.integers(), max_size=2),
    st.dictionaries(st.text(max_size=4), st.integers(), max_size=2),
)


@given(
    source=_ARBITRARY,
    reward=_ARBITRARY,
    raw_reward=_ARBITRARY,
    terminated=_ARBITRARY,
    truncated=_ARBITRARY,
    done=_ARBITRARY,
    ready=_ARBITRARY,
)
def test_verifier_classifier_is_total_for_arbitrary_python_shapes(
    source,
    reward,
    raw_reward,
    terminated,
    truncated,
    done,
    ready,
) -> None:
    result = classify_browsergym_verifier(
        source,
        reward=reward,
        raw_reward=raw_reward,
        terminated=terminated,
        truncated=truncated,
        done=done,
        ready=ready,
    )
    assert isinstance(result.status, ExternalVerifierStatus)
    assert isinstance(result.reason, ExternalVerifierReason)


@given(
    exponent=st.integers(min_value=309, max_value=2000),
    field=st.sampled_from(("reward", "raw_reward")),
    sign=st.sampled_from((-1, 1)),
)
def test_arbitrarily_large_exact_ints_remain_inside_typed_algebra(
    exponent,
    field,
    sign,
) -> None:
    values = dict(reward=0, raw_reward=0)
    values[field] = sign * 10**exponent
    result = classify_browsergym_verifier(
        VerifierFactSource.POST_ACTION,
        terminated=False,
        truncated=False,
        done=False,
        ready=True,
        **values,
    )
    assert isinstance(result.status, ExternalVerifierStatus)
    assert isinstance(result.reason, ExternalVerifierReason)


@given(raw_reward=st.floats(max_value=0, allow_nan=False, allow_infinity=False))
def test_terminal_failure_is_magnitude_invariant_within_nonpositive_sign(raw_reward) -> None:
    result = classify_browsergym_verifier(
        VerifierFactSource.POST_ACTION,
        reward=0.0,
        raw_reward=raw_reward,
        terminated=True,
        truncated=False,
        done=True,
        ready=True,
    )
    assert result.status is ExternalVerifierStatus.TERMINAL_TASK_FAILURE


@given(
    reward=st.floats(allow_nan=True, allow_infinity=True),
    raw_reward=st.floats(allow_nan=True, allow_infinity=True),
    terminated=st.booleans(),
    truncated=st.booleans(),
    done=st.booleans(),
    ready=st.booleans(),
)
def test_reset_never_proves_terminal_outcome(
    reward,
    raw_reward,
    terminated,
    truncated,
    done,
    ready,
) -> None:
    result = classify_browsergym_verifier(
        VerifierFactSource.RESET,
        reward=reward,
        raw_reward=raw_reward,
        terminated=terminated,
        truncated=truncated,
        done=done,
        ready=ready,
    )
    assert result.status not in {
        ExternalVerifierStatus.SUCCESS,
        ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
    }


def test_bool_nonfinite_truncated_and_probe_without_reward_fail_closed() -> None:
    common = dict(terminated=True, truncated=False, done=True, ready=True)
    assert (
        classify_browsergym_verifier(
            VerifierFactSource.POST_ACTION,
            reward=True,
            raw_reward=1,
            **common,
        ).reason
        is ExternalVerifierReason.INVALID_FACTS
    )
    assert (
        classify_browsergym_verifier(
            VerifierFactSource.POST_ACTION,
            reward=1.0,
            raw_reward=float("nan"),
            **common,
        ).reason
        is ExternalVerifierReason.NON_FINITE_FACTS
    )
    assert (
        classify_browsergym_verifier(
            VerifierFactSource.POST_ACTION,
            reward=0.0,
            raw_reward=0.0,
            terminated=True,
            truncated=True,
            done=True,
            ready=True,
        ).reason
        is ExternalVerifierReason.UNSUPPORTED_STATE
    )
    assert (
        classify_browsergym_verifier(
            VerifierFactSource.READ_ONLY_PROBE,
            done=True,
            ready=True,
        ).reason
        is ExternalVerifierReason.MISSING_FACTS
    )

    class HostileInt(int):
        def __float__(self):
            raise RuntimeError("must not be called")

    hostile = classify_browsergym_verifier(
        VerifierFactSource.POST_ACTION,
        reward=HostileInt(1),
        raw_reward=1,
        **common,
    )
    assert hostile.reason is ExternalVerifierReason.INVALID_FACTS


def test_unrelated_task_info_fields_and_mapping_order_do_not_change_assessment() -> None:
    common = dict(
        task_run_id="run:1",
        observation_id="obs:1",
        source_observation_id="obs:1",
        source=VerifierFactSource.POST_ACTION,
        reward=0.0,
        terminated=True,
        truncated=False,
    )
    first = verifier_snapshot(
        **common,
        task_info={
            "RAW_REWARD_GLOBAL": -1,
            "DONE_GLOBAL": True,
            "TASK_READY": True,
            "unrelated": {"task": "identity"},
        },
    )
    second = verifier_snapshot(
        **common,
        task_info={
            "TASK_READY": True,
            "DONE_GLOBAL": True,
            "RAW_REWARD_GLOBAL": -9,
            "another": "ignored",
        },
    )
    assert (
        (first.status, first.reason)
        == (second.status, second.reason)
        == (
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
            ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE,
        )
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"reward": 1.0, "raw_reward": 1.0, "terminated": False, "done": False},
        {"reward": 0.0, "raw_reward": 0.0, "terminated": True, "done": False},
        {"reward": 0.0, "raw_reward": 1.0, "terminated": True, "done": True},
    ),
)
def test_well_typed_post_action_disagreements_are_unavailable(changes) -> None:
    result = classify_browsergym_verifier(
        VerifierFactSource.POST_ACTION,
        truncated=False,
        ready=True,
        **changes,
    )
    assert result.status is ExternalVerifierStatus.UNAVAILABLE
    assert result.reason is ExternalVerifierReason.INCONSISTENT_FACTS


def test_success_evidence_is_current_opaque_and_resolves() -> None:
    raw = raw_observation(ax_node("1", "button", "okay"))
    fake = FakeBrowserGym(raw, raw)
    fake.probes["1"] = {
        "exists": True,
        "url": raw["url"],
        "episode": "0",
        "ready": True,
        "done": False,
        "role": "button",
        "label": "okay",
        "state": {},
    }
    environment, task = _open_fake_case(fake)
    before = start_environment(environment, task)
    outcome = asyncio.run(environment.execute(request_for(before, task, "activate")))
    after = outcome.post_acquisition.observation
    assert after is not None
    evaluator = ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment)
    evaluation = asyncio.run(evaluator.evaluate(task, after))
    assert evaluation.status is TaskEvaluationStatus.COMPLETE
    ref = evaluation.completion_evidence_refs[0]
    assert WorldEvidenceIndex.from_observation(after).resolve(ref)
    for forbidden in ("reward", environment.benchmark_task_id, "expected", "hidden"):
        assert forbidden not in ref
    asyncio.run(environment.close())
    asyncio.run(environment.close())
    assert fake.close_count == 1


def test_independent_capture_does_not_relabel_old_success_verifier_evidence() -> None:
    raw = raw_observation(ax_node("1", "button", "okay"))
    fake = FakeBrowserGym(raw, raw)
    fake.probes["1"] = {
        "exists": True,
        "url": raw["url"],
        "episode": "0",
        "ready": True,
        "done": False,
        "role": "button",
        "label": "okay",
        "state": {},
    }
    environment, task = _open_fake_case(fake)
    before = start_environment(environment, task)
    sent = asyncio.run(environment.execute(request_for(before, task, "activate")))
    assert sent.post_acquisition.observation is not None
    assert environment.current_result(environment.benchmark_task_id).status is ExternalVerifierStatus.SUCCESS

    from affordance_runtime.world import ObservationRequestKind, WorldObservationRequest

    refreshed = asyncio.run(
        environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "refresh current verifier",
            )
        )
    )
    assert refreshed.observation is not None
    assert environment.current_result(environment.benchmark_task_id).status is ExternalVerifierStatus.INCOMPLETE
    asyncio.run(environment.close())


def test_negative_terminal_flows_once_without_synthetic_runtime_failure() -> None:
    async def scenario() -> None:
        raw = raw_observation(ax_node("1", "button", "Login"))
        fake = FakeBrowserGym(raw, raw)
        fake.step_reward = 0.0
        fake.step_raw_reward = 0
        fake.step_done = True
        environment, task = _open_fake_case(fake)
        policy = ScriptedPolicy(["first"])
        loop = AgentLoop(
            policy,
            ProductionActionEvaluator(),
            ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
        )
        session = await (loop).start(environment, task)
        first = await session.run_until_pause()
        second = await session.run_until_pause()

        assert first is second
        assert first.status is AgentLoopStatus.BLOCKED
        assert first.runtime_failure is None
        assert first.task_outcome is not None
        assert first.task_outcome.kind.value == "terminal_failure"
        assert first.control_transitions[0].execution is not None
        assert first.control_transitions[0].execution.result.dispatch_status is DispatchStatus.SENT
        assert fake.actions and len(fake.actions) == environment.step_calls == 1
        task_evaluation = first.control_transitions[0].task_evaluation
        assert task_evaluation is not None
        assert task_evaluation.status is TaskEvaluationStatus.BLOCKED
        assert task_evaluation.completion_evidence_refs == ()
        assert WorldEvidenceIndex.from_observation(first.final_observation).resolve(first.task_outcome.evidence_refs[0])
        projected = project_case_result(
            "negative-terminal",
            first,
            BenchmarkInstrumentation(),
            1.0,
            "",
        )
        classified = classify_case(projected)
        assert classified.outcome is MiniWobTaskOutcome.TASK_FAILED
        assert classified.source == "canonical_task_outcome"
        assert not policy.decisions
        await environment.close()

    asyncio.run(scenario())
