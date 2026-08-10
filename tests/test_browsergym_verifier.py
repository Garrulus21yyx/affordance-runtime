import asyncio

from browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
    request_for,
    start_environment,
)

from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import verifier_snapshot
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalEnvironmentTaskEvaluator,
    ExternalVerifierStatus,
)
from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex


def test_official_verifier_status_mapping_is_strict() -> None:
    common = dict(task_run_id="run:1", observation_id="obs:1", source_observation_id="obs:1")
    success = verifier_snapshot(
        **common, reward=1.0, terminated=True, truncated=False,
        task_info={"RAW_REWARD_GLOBAL": 1, "DONE_GLOBAL": True},
    )
    incomplete = verifier_snapshot(
        **common, reward=0.0, terminated=False, truncated=False,
        task_info={"RAW_REWARD_GLOBAL": 0, "DONE_GLOBAL": False},
    )
    unavailable = verifier_snapshot(
        **common, reward=1.0, terminated=False, truncated=False,
        task_info={"RAW_REWARD_GLOBAL": 1, "DONE_GLOBAL": False},
    )
    assert success.status is ExternalVerifierStatus.SUCCESS and success.evidence_ref.startswith("artifact:")
    assert incomplete.status is ExternalVerifierStatus.INCOMPLETE and not incomplete.evidence_ref
    assert unavailable.status is ExternalVerifierStatus.UNAVAILABLE


def test_success_evidence_is_current_opaque_and_resolves() -> None:
    raw = raw_observation(ax_node("1", "button", "okay"))
    fake = FakeBrowserGym(raw, raw)
    fake.probes["1"] = {
        "exists": True, "url": raw["url"], "episode": "0", "ready": True,
        "done": False, "role": "button", "label": "okay", "state": {},
    }
    environment, task = open_fake(fake)
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
        "exists": True, "url": raw["url"], "episode": "0", "ready": True,
        "done": False, "role": "button", "label": "okay", "state": {},
    }
    environment, task = open_fake(fake)
    before = start_environment(environment, task)
    sent = asyncio.run(environment.execute(request_for(before, task, "activate")))
    assert sent.post_acquisition.observation is not None
    assert environment.current_result(environment.benchmark_task_id).status is ExternalVerifierStatus.SUCCESS

    from affordance_runtime.world import ObservationRequestKind, WorldObservationRequest

    refreshed = asyncio.run(environment.capture(WorldObservationRequest(
        ObservationRequestKind.CURRENTNESS_REFRESH, "refresh current verifier",
    )))
    assert refreshed.observation is not None
    assert environment.current_result(environment.benchmark_task_id).status is ExternalVerifierStatus.INCOMPLETE
    asyncio.run(environment.close())
