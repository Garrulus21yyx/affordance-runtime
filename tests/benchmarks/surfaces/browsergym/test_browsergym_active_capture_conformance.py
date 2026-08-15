from __future__ import annotations

import asyncio
import os
import threading

import pytest

from affordance_runtime.benchmarks.external_smoke.case_environment import (
    ExternalVerifierStatus,
    open_browsergym_case,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BrowserGymTaskStateSource,
    task_state_from_transition,
)
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ObservationRequestKind,
    WorldObservationRequest,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIWOB_URL"),
    reason="fixed MiniWoB source is unavailable",
)


def test_real_backend_active_capture_is_fresh_read_only_and_thread_owned() -> None:
    async def scenario() -> None:
        environment, task = open_browsergym_case(
            "browsergym/miniwob.click-button",
            7,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            assert environment.observation_capabilities.independent_capture
            captured = await environment.capture(WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "real active capture conformance",
            ))
            assert captured.status is AcquisitionStatus.ACQUIRED
            assert captured.origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
            assert captured.observation is not None
            assert captured.observation.observation_id != initial.observation.observation_id
            assert environment.backend_reset_calls == environment.logical_reset_calls == 1
            assert environment.capture_calls == 1
            assert environment.step_calls == 0
            backend = environment.gym_environment
            assert backend.owner_thread_ident == backend.last_capture_thread_ident  # type: ignore[attr-defined]
            assert backend.owner_thread_ident != threading.get_ident()  # type: ignore[attr-defined]
            assert not hasattr(backend, "page")
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_real_active_capture_does_not_copy_old_success_or_dispatch_again() -> None:
    async def scenario() -> None:
        environment, task = open_browsergym_case(
            "browsergym/miniwob.click-button",
            7,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            environment.surface._task_state = task_state_from_transition(  # noqa: SLF001
                task_run_id=environment.task_run_id,
                observation_id=initial.observation.observation_id,
                source_observation_id=initial.observation.observation_id,
                source=BrowserGymTaskStateSource.POST_ACTION,
                reward=1.0,
                terminated=True,
                truncated=False,
                task_info={
                    "RAW_REWARD_GLOBAL": 1,
                    "DONE_GLOBAL": True,
                    "TASK_READY": True,
                },
            )
            assert environment.current_result(environment.benchmark_task_id).status is ExternalVerifierStatus.SUCCESS
            steps = environment.step_calls
            refreshed = await environment.capture(WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "refresh verifier after success",
            ))
            assert refreshed.status is AcquisitionStatus.ACQUIRED
            assert refreshed.origin is AcquisitionOrigin.INDEPENDENT_CAPTURE
            assert refreshed.observation is not None
            assert refreshed.observation.observation_id != initial.observation.observation_id
            assert environment.step_calls == steps == 0
            assert environment.backend_reset_calls == environment.logical_reset_calls == 1
            assert environment.current_result(environment.benchmark_task_id).status is not ExternalVerifierStatus.SUCCESS
        finally:
            await environment.close()

    asyncio.run(scenario())
