from __future__ import annotations

import asyncio
import inspect
import json
import os
import threading

import pytest

from affordance_runtime.actions import ActionBinder, ActionSpaceBuilder
from affordance_runtime.execution import ActionError, DispatchStatus
from affordance_runtime.surfaces.browsergym.binding import BrowserGymElementBinding
from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessReason,
    BrowserGymCurrentnessStatus,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import open_surface, request_for

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIWOB_URL"),
    reason="fixed MiniWoB source is unavailable",
)

_UNCHANGED_TASKS = (
    "click-tab",
    "click-tab-2",
    "click-tab-2-hard",
    "click-tab-2-easy",
    "book-flight",
    "choose-list",
)


def test_pinned_currentness_uses_actual_read_only_and_frame_safe_helpers() -> None:
    from browsergym.core.action.utils import get_elem_by_bid
    from browsergym.core.env import BrowserEnv

    assert callable(BrowserEnv._get_obs)  # noqa: SLF001 - pinned private API conformance
    assert tuple(inspect.signature(get_elem_by_bid).parameters) == (
        "page", "bid", "scroll_into_view",
    )


@pytest.mark.parametrize("slug", _UNCHANGED_TASKS)
def test_real_unchanged_ax_world_is_current_without_capture_side_effects(slug: str) -> None:
    async def scenario() -> None:
        task_id = f"browsergym/miniwob.{slug}"
        environment, task = open_surface(task_id, 7)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            world = initial.observation
            binding = next(
                item
                for item in world.bindings
                if isinstance(environment.bindings.get(item.binding_id), BrowserGymElementBinding)
            )
            schema = binding.parameter_schema
            properties = schema.get("properties", {})
            parameters = {
                name: (
                    field["enum"][0]
                    if field.get("enum")
                    else "focused-currentness-witness"
                    if field.get("type") == "string"
                    else field.get("minimum", 0)
                    if field.get("type") in {"integer", "number"}
                    else False
                )
                for name in schema.get("required", ())
                if (field := properties[name])
            }
            option = next(
                item
                for item in ActionSpaceBuilder().build(task, world).options
                if binding.binding_id in item.eligible_binding_ids
            )
            selection = ActionSpaceBuilder().admit(option, parameters)
            request = ActionBinder().bind(selection, world, "context:test")
            private = environment.bindings.get(request.binding.binding_id)
            assert private is not None
            before = (
                environment._observation_serial,  # noqa: SLF001 - side-effect conformance
                environment.bindings.count,
                environment.current_task_state,
                environment.full_observation_count,
                environment.capture_calls,
                environment.step_calls,
                environment.reset_calls,
            )

            error, count = environment._probe_currentness(request, private)  # noqa: SLF001

            after = (
                environment._observation_serial,  # noqa: SLF001
                environment.bindings.count,
                environment.current_task_state,
                environment.full_observation_count,
                environment.capture_calls,
                environment.step_calls,
                environment.reset_calls,
            )
            backend = environment.gym_environment
            assert error is None and count == 1
            assert environment.last_currentness_decision is not None
            assert environment.last_currentness_decision.status is BrowserGymCurrentnessStatus.CURRENT
            assert after == before
            assert environment.probe_calls == backend.currentness_probe_calls == 1  # type: ignore[attr-defined]
            assert len(environment.currentness_probe_latencies_ms) == 1
            assert backend.owner_thread_ident == backend.last_currentness_probe_thread_ident  # type: ignore[attr-defined]
            assert backend.owner_thread_ident != threading.get_ident()  # type: ignore[attr-defined]
            assert not hasattr(backend, "page")
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_real_login_user_popup_terminal_reentry_is_stale_and_zero_step() -> None:
    async def scenario() -> None:
        task_id = "browsergym/miniwob.login-user-popup"
        environment, task = open_surface(task_id, 7)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            world = initial.observation
            request = request_for(world, task, "activate")
            private = environment.bindings.get(request.binding.binding_id)
            assert private is not None
            # Test-only terminal injection through the real owner thread. Clicking
            # the login button without credentials deterministically ends at -1.
            environment.gym_environment.step(
                f"click({json.dumps(private.private_element_id)})",
                may_navigate=False,
            )
            assert environment.step_calls == 0

            outcome = await environment.execute(request)

            assert (outcome.result.dispatch_status, outcome.result.error) == (
                DispatchStatus.NOT_SENT,
                ActionError.STALE_BINDING,
            )
            assert environment.last_currentness_decision is not None
            assert environment.last_currentness_decision.reason is BrowserGymCurrentnessReason.TASK_DONE
            assert environment.step_calls == 0
            backend = environment.gym_environment
            assert environment.probe_calls == backend.currentness_probe_calls == 1  # type: ignore[attr-defined]
        finally:
            await environment.close()

    asyncio.run(scenario())
