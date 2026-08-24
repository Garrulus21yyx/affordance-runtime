import asyncio
import copy
import threading
import time
from dataclasses import replace

import pytest

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.execution import ActionError, DispatchStatus, ExecutionDiagnosticPhase
from affordance_runtime.surfaces.browsergym import backend as browsergym_backend
from affordance_runtime.surfaces.browsergym import environment as browsergym_environment
from affordance_runtime.surfaces.browsergym.backend import _with_stable_private_control_properties
from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessReason,
)
from affordance_runtime.surfaces.browsergym.environment import BrowserGymSurfaceAdapter
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.surfaces.browsergym.transition import BrowserGymStabilityStatus
from affordance_runtime.world import AcquisitionStatus, ObservationRequestKind, WorldObservationRequest
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
    request_for,
    start_environment,
)


def _request_for_role(world, task, semantic_action, target_role, parameters=None):
    builder = ActionSpaceBuilder()
    target = next(item for item in world.targets if item.role == target_role)
    option = next(
        item
        for item in builder.build(task, world).options
        if item.semantic_action == semantic_action and item.target_id == target.target_id
    )
    selection = builder.admit(option, parameters or {})
    return ActionBinder().bind(selection, world, "context:test")


def _fixture(*, fail_step=False, fail_probe=False):
    raw = raw_observation(
        ax_node("1", "button", "okay"),
        ax_node("2", "textbox", "", properties=(("required", False),)),
        ax_node("3", "combobox", "", value="A", properties=(("expanded", False),)),
        ax_node("4", "option", "A"),
        ax_node("5", "option", "B"),
    )
    fake = FakeBrowserGym(raw, raw, fail_step=fail_step, fail_probe=fail_probe)
    environment, task = open_fake(fake)
    return fake, environment, task, start_environment(environment, task)


class _StablePage:
    def __init__(self):
        self.visible = False
        self.wait_count = 0
        self.batch_sizes = []

    def evaluate(self, script, bids):
        assert script == browsergym_backend._BULK_PHYSICAL_PROPERTIES_SCRIPT  # noqa: SLF001
        self.batch_sizes.append(len(bids))
        return {
            bid: {
                "attached": True,
                "visible": self.visible,
                "enabled": True,
                "readonly": False,
                "active": False,
                "focusable": True,
                "focused": False,
                "editable": False,
                "bbox": [10, 10, 80, 20],
                "options": [],
            }
            for bid in bids
        }

    def wait_for_timeout(self, delay_ms):
        del delay_ms
        self.wait_count += 1
        self.visible = True


def test_thread_bound_capture_batches_large_stable_executable_inventory() -> None:
    page = _StablePage()
    raw = raw_observation(*(
        ax_node(f"link-{index}", "link", f"Result {index}")
        for index in range(2_000)
    ))

    enriched = _with_stable_private_control_properties(page, lambda: raw, raw)

    assert page.wait_count == 2
    assert page.batch_sizes == [2_000, 2_000, 2_000]
    assert len(enriched[PRIVATE_CONTROL_PROPERTIES_KEY]) == 2_000
    assert enriched[PRIVATE_CONTROL_PROPERTIES_KEY]["link-1999"]["visible"] is True


def test_browsergym_physical_calls_do_not_block_the_asyncio_watchdog() -> None:
    class BlockingProbe(FakeBrowserGym):
        def __init__(self, raw):
            super().__init__(raw, raw)
            self.release = threading.Event()
            self.order = []

        def currentness_probe(self, bid):
            self.order.append("probe_started")
            self.release.wait(timeout=1)
            self.order.append("probe_finished")
            return super().currentness_probe(bid)

    raw = raw_observation(ax_node("1", "button", "okay"))
    fake = BlockingProbe(raw)
    environment, task = open_fake(fake)
    world = start_environment(environment, task)
    request = request_for(world, task, "activate")

    async def scenario() -> None:
        timer = threading.Timer(0.2, fake.release.set)
        timer.start()
        try:
            execution = asyncio.create_task(environment.execute(request))

            async def watchdog_tick() -> None:
                await asyncio.sleep(0)
                fake.order.append("watchdog_tick")

            await asyncio.gather(execution, watchdog_tick())
        finally:
            timer.cancel()
        assert fake.order.index("watchdog_tick") < fake.order.index("probe_finished")
        await environment.close()

    asyncio.run(scenario())


def test_owner_timeout_poisoning_rejects_queued_fallback_immediately() -> None:
    owner = object.__new__(browsergym_backend.ThreadBoundBrowserGym)
    owner._closed = False  # noqa: SLF001 - owner timeout contract gate
    owner._commands = browsergym_backend.queue.Queue()  # noqa: SLF001
    owner._command_timed_out = threading.Event()  # noqa: SLF001

    with pytest.raises(TimeoutError, match="owner command 'causal_step'"):
        owner._call("causal_step", "click('1')", True, wait_timeout_s=0.01)  # noqa: SLF001

    started = time.perf_counter()
    with pytest.raises(RuntimeError, match="unavailable after a command timeout"):
        owner._call("capture_current", wait_timeout_s=1)  # noqa: SLF001
    assert time.perf_counter() - started < 0.1
    assert owner._commands.qsize() == 1  # noqa: SLF001


def test_completed_command_timeout_does_not_poison_owner() -> None:
    owner = object.__new__(browsergym_backend.ThreadBoundBrowserGym)
    owner._closed = False  # noqa: SLF001 - owner timeout contract gate
    owner._commands = browsergym_backend.queue.Queue()  # noqa: SLF001
    owner._command_timed_out = threading.Event()  # noqa: SLF001

    def complete_command() -> None:
        _name, _args, _kwargs, outcome = owner._commands.get(timeout=1)  # noqa: SLF001
        outcome.set_exception(TimeoutError("operation-owned timeout"))

    worker = threading.Thread(target=complete_command)
    worker.start()
    with pytest.raises(TimeoutError, match="operation-owned timeout"):
        owner._call("currentness_probe", "1", wait_timeout_s=1)  # noqa: SLF001
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert owner._command_timed_out.is_set() is False  # noqa: SLF001


def _drag_fixture():
    raw = raw_observation(
        ax_node("source", "generic", "Card"),
        ax_node("destination", "generic", "Done column"),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["source"].update({
        "gesture_role": "draggable",
        "gesture_group": "board",
        "gesture_kind": "move",
        "bbox": [10, 10, 40, 20],
    })
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["destination"].update({
        "gesture_role": "drop_target",
        "gesture_group": "board",
        "bbox": [80, 10, 60, 40],
    })
    fake = FakeBrowserGym(raw, raw)
    environment, task = open_fake(fake)
    return fake, environment, task, start_environment(environment, task)


def test_reset_offer_is_independent_from_optional_independent_capture_capability() -> None:
    raw = raw_observation(ax_node("1", "button", "okay"))
    fake = FakeBrowserGym(raw, raw)
    fake.supports_capture_current = False
    environment, task = open_fake(fake)

    initial = asyncio.run(environment.reset(task))
    capture = asyncio.run(
        environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "explicit refresh",
            )
        )
    )

    assert initial.status is AcquisitionStatus.ACQUIRED
    assert capture.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
    assert capture.reason_code == "independent_capture_unsupported"
    asyncio.run(environment.close())


def test_activate_fill_and_select_each_dispatch_one_official_action() -> None:
    expected = (
        ("activate", {}, "click("),
        ("type_text", {"text": "hello"}, "fill("),
        ("select_option", {"value": "B"}, "select_option("),
    )
    for semantic, parameters, prefix in expected:
        fake, environment, task, world = _fixture()
        request = request_for(world, task, semantic, parameters)
        outcome = asyncio.run(environment.execute(request))
        result = outcome.result
        assert result.dispatch_status is DispatchStatus.SENT
        assert len(fake.actions) == 1 and fake.actions[0].startswith(prefix)
        assert environment.probe_calls == 1 and environment.step_calls == 1
        asyncio.run(environment.close())


def test_navigation_lease_is_mechanical_and_non_navigation_button_keeps_fast_path() -> None:
    fake, environment, task, world = _fixture()
    asyncio.run(environment.execute(request_for(world, task, "activate")))
    assert fake.navigation_expectations == [False]
    asyncio.run(environment.close())

    raw = raw_observation(ax_node("link", "link", "Open result"))
    fake = FakeBrowserGym(raw, raw)
    environment, task = open_fake(fake)
    world = start_environment(environment, task)
    asyncio.run(environment.execute(request_for(world, task, "activate")))
    assert fake.navigation_expectations == [True]
    asyncio.run(environment.close())

    fake = FakeBrowserGym(raw, raw)
    environment, task = open_fake(fake)
    world = start_environment(environment, task)
    asyncio.run(
        environment.execute(
            request_for(world, task, "press_key", {"key": "Enter"})
        )
    )
    assert fake.navigation_expectations == [True]
    asyncio.run(environment.close())


@pytest.mark.parametrize(
    "status",
    (
        BrowserGymStabilityStatus.NAVIGATION_PENDING,
        BrowserGymStabilityStatus.ACQUISITION_UNSTABLE,
    ),
)
def test_unstable_causal_post_state_is_typed_and_not_admitted(status) -> None:
    fake, environment, task, world = _fixture()
    fake.step_stability_status = status

    outcome = asyncio.run(environment.execute(request_for(world, task, "activate")))

    assert outcome.result.dispatch_status is DispatchStatus.SENT
    assert outcome.result.adapter_evidence["browsergym_transition"]["stability_status"] == status.value
    assert outcome.post_acquisition is not None
    assert outcome.post_acquisition.status is AcquisitionStatus.FAILED
    assert any(
        source.reason_code == status.value
        for source in outcome.post_acquisition.source_results
    )
    asyncio.run(environment.close())


def test_unstable_post_state_allows_one_read_only_recovery() -> None:
    fake, environment, task, world = _fixture()
    fake.step_stability_status = BrowserGymStabilityStatus.ACQUISITION_UNSTABLE
    request = request_for(world, task, "activate")

    outcome = asyncio.run(environment.execute(request))
    recovery = asyncio.run(
        environment.world.recover_execution_observation(
            request,
            WorldObservationRequest(
                ObservationRequestKind.POST_ACTION_FALLBACK,
                "recover unstable post state",
                request.verification_needs,
            ),
        )
    )

    assert outcome.post_acquisition is not None
    assert outcome.post_acquisition.status is AcquisitionStatus.FAILED
    assert recovery.acquisition.status is AcquisitionStatus.ACQUIRED
    assert recovery.acquisition.observation is not None
    assert fake.capture_count == environment.capture_calls == 1
    assert len(fake.actions) == environment.step_calls == 1
    asyncio.run(environment.close())


def test_post_action_projection_failure_keeps_owner_diagnostic(monkeypatch) -> None:
    fake, environment, task, world = _fixture()
    request = request_for(world, task, "activate")

    def fail_projection(*args, **kwargs):
        del args, kwargs
        raise ValueError("projection witness")

    monkeypatch.setattr(
        browsergym_environment,
        "project_browsergym_observation",
        fail_projection,
    )

    outcome = asyncio.run(environment.execute(request))

    assert outcome.post_acquisition is not None
    assert outcome.post_acquisition.status is AcquisitionStatus.FAILED
    assert any(
        source.reason_code == "post_action_projection_failed"
        for source in outcome.post_acquisition.source_results
    )
    assert outcome.result.diagnostics[-1].exception_type == "ValueError"
    assert outcome.result.diagnostics[-1].safe_message == "projection witness"
    assert outcome.result.diagnostics[-1].traceback_ref.startswith("traceback:sha256:")
    asyncio.run(environment.close())


def test_navigation_pending_cannot_be_admitted_by_current_page_recovery() -> None:
    fake, environment, task, world = _fixture()
    fake.step_stability_status = BrowserGymStabilityStatus.NAVIGATION_PENDING
    request = request_for(world, task, "activate")

    outcome = asyncio.run(environment.execute(request))
    recovery = asyncio.run(
        environment.world.recover_execution_observation(
            request,
            WorldObservationRequest(
                ObservationRequestKind.POST_ACTION_FALLBACK,
                "do not snapshot an uncommitted navigation",
                request.verification_needs,
            ),
        )
    )

    assert outcome.post_acquisition is not None
    assert outcome.post_acquisition.status is AcquisitionStatus.FAILED
    assert recovery.acquisition.status is AcquisitionStatus.FAILED
    assert fake.capture_count == environment.capture_calls == 0
    assert len(fake.actions) == environment.step_calls == 1
    asyncio.run(environment.close())


def test_missing_native_task_globals_use_lifecycle_fallback_for_element_dispatch() -> None:
    fake, environment, task, world = _fixture()
    fake.probe_task = {}

    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

    assert result.dispatch_status is DispatchStatus.SENT
    assert result.adapter_evidence["currentness_status"] == "current"
    assert result.adapter_evidence["currentness_reason"] == "current"
    assert result.adapter_evidence["currentness_task_state_source"] == "lifecycle_fallback"
    assert result.adapter_evidence["currentness_episode_source"] == "lifecycle_fallback"
    assert result.adapter_evidence["effectful_dispatch_count"] == 1
    assert environment.step_calls == fake.currentness_probe_count == 1
    asyncio.run(environment.close())


def test_native_task_facts_take_precedence_over_lifecycle_fallback() -> None:
    fake, environment, task, world = _fixture()
    fake.probe_task["ready"] = False

    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.STALE_BINDING,
    )
    assert result.adapter_evidence["currentness_reason"] == "task_not_ready"
    assert result.adapter_evidence["currentness_task_state_source"] == "native"
    assert environment.step_calls == 0
    asyncio.run(environment.close())

    fake, environment, task, world = _fixture()
    fake.probe_task["episode"] = "changed"

    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.STALE_BINDING,
    )
    assert result.adapter_evidence["currentness_reason"] == "episode_changed"
    assert result.adapter_evidence["currentness_episode_source"] == "native"
    assert environment.step_calls == 0
    asyncio.run(environment.close())


def test_missing_and_malformed_native_task_facts_are_distinct() -> None:
    fake, environment, task, world = _fixture()
    fake.probe_task = {"episode": "0"}

    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

    assert result.dispatch_status is DispatchStatus.SENT
    assert result.adapter_evidence["currentness_task_state_source"] == "lifecycle_fallback"
    assert result.adapter_evidence["currentness_episode_source"] == "native"
    asyncio.run(environment.close())

    for malformed_task in ({"ready": "yes"}, {"episode": {}}):
        fake, environment, task, world = _fixture()
        fake.probe_override = {
            "raw": fake.post,
            "task": {**malformed_task, "url": fake.post["url"]},
            "latency_ms": 0.1,
        }

        result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

        assert (result.dispatch_status, result.error) == (
            DispatchStatus.NOT_SENT,
            ActionError.CURRENTNESS_UNAVAILABLE,
        )
        assert result.adapter_evidence["currentness_status"] == "unavailable"
        assert result.adapter_evidence["currentness_reason"] == "probe_unavailable"
        assert result.adapter_evidence["effectful_dispatch_count"] == 0
        assert environment.step_calls == 0
        asyncio.run(environment.close())


def test_scroll_dispatches_viewport_browsergym_scroll_without_element_route() -> None:
    fake, environment, task, world = _fixture()
    request = _request_for_role(world, task, "scroll", "viewport", {"direction": "down", "extent": "small"})
    fake.probe_task = {}

    outcome = asyncio.run(environment.execute(request))

    assert outcome.result.dispatch_status is DispatchStatus.SENT
    assert outcome.result.adapter_evidence["currentness_task_state_source"] == "lifecycle_fallback"
    assert fake.actions == ["scroll(0.0, 150.0)"]
    assert environment.scroll_calls == 1
    assert environment.keyboard_press_calls == environment.press_calls == 0
    assert environment.step_calls == 1
    asyncio.run(environment.close())


def test_press_key_dispatches_entity_press_and_focused_keyboard_press() -> None:
    fake, environment, task, world = _fixture()
    entity_request = _request_for_role(world, task, "press_key", "button", {"key": "Enter"})

    entity_outcome = asyncio.run(environment.execute(entity_request))

    assert entity_outcome.result.dispatch_status is DispatchStatus.SENT
    assert fake.actions == ['press("1", "Enter")']
    assert environment.press_calls == 1
    asyncio.run(environment.close())

    fake, environment, task, world = _fixture()
    focused_request = _request_for_role(world, task, "press_key", "focused_context", {"key": "Escape"})
    fake.probe_task = {}

    focused_outcome = asyncio.run(environment.execute(focused_request))

    assert focused_outcome.result.dispatch_status is DispatchStatus.SENT
    assert focused_outcome.result.adapter_evidence["currentness_task_state_source"] == "lifecycle_fallback"
    assert fake.actions == ['keyboard_press("Escape")']
    assert environment.keyboard_press_calls == 1
    asyncio.run(environment.close())


def test_focused_context_fallback_uses_dispatch_time_focus_without_invented_bid_identity() -> None:
    initial = raw_observation(ax_node("status", "status", "Ready"))
    initial[PRIVATE_CONTROL_PROPERTIES_KEY]["status"]["focused"] = True
    changed = copy.deepcopy(initial)
    changed[PRIVATE_CONTROL_PROPERTIES_KEY]["status"]["focused"] = False
    fake = FakeBrowserGym(initial, changed)
    environment, task = open_fake(fake)
    world = start_environment(environment, task)
    request = _request_for_role(
        world,
        task,
        "press_key",
        "focused_context",
        {"key": "Enter"},
    )

    result = asyncio.run(environment.execute(request)).result

    assert (result.dispatch_status, result.error) == (DispatchStatus.SENT, None)
    assert fake.actions == ['keyboard_press("Enter")']
    assert environment.keyboard_press_calls == environment.step_calls == 1
    asyncio.run(environment.close())


def test_press_key_rejects_keys_outside_current_closed_enum_before_dispatch() -> None:
    fake, environment, task, world = _fixture()
    builder = ActionSpaceBuilder()
    target = next(item for item in world.targets if item.role == "button")
    option = next(
        item
        for item in builder.build(task, world).options
        if item.semantic_action == "press_key" and item.target_id == target.target_id
    )

    result = builder.try_admit(option, {"key": 'Enter"); scroll(0, 9999); //'})

    assert result.admitted is None
    assert result.issue is not None
    assert fake.actions == []
    asyncio.run(environment.close())


def test_drag_dispatches_one_official_action_with_two_private_current_endpoints() -> None:
    fake, environment, task, world = _drag_fixture()
    option = next(
        item for item in ActionSpaceBuilder().build(task, world).options
        if item.semantic_action == "drag_to"
    )
    request = request_for(
        world,
        task,
        "drag_to",
        destination_id=option.eligible_destination_ids[0],
    )

    outcome = asyncio.run(environment.execute(request))

    assert outcome.result.dispatch_status is DispatchStatus.SENT
    assert fake.actions == ['drag_and_drop("source", "destination")']
    assert environment.probe_calls == environment.step_calls == 1
    assert outcome.post_acquisition is not None
    asyncio.run(environment.close())


def test_changed_drag_destination_is_stale_and_never_dispatched() -> None:
    fake, environment, task, world = _drag_fixture()
    option = next(
        item for item in ActionSpaceBuilder().build(task, world).options
        if item.semantic_action == "drag_to"
    )
    request = request_for(
        world,
        task,
        "drag_to",
        destination_id=option.eligible_destination_ids[0],
    )
    changed = copy.deepcopy(fake.post)
    changed["axtree_object"]["nodes"][1]["name"]["value"] = "Changed"
    fake.post = changed

    result = asyncio.run(environment.execute(request)).result

    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.STALE_BINDING,
    )
    assert fake.actions == [] and environment.step_calls == 0
    asyncio.run(environment.close())


def test_stale_or_unavailable_currentness_is_not_sent_and_zero_step() -> None:
    fake, environment, task, world = _fixture()
    request = request_for(world, task, "activate")
    fake.post["axtree_object"]["nodes"][0]["name"]["value"] = "changed"
    result = asyncio.run(environment.execute(request)).result
    assert (result.dispatch_status, result.error) == (DispatchStatus.NOT_SENT, ActionError.STALE_BINDING)
    assert fake.actions == [] and environment.step_calls == 0 and environment.probe_calls == 1
    assert fake.currentness_probe_count == 1
    asyncio.run(environment.close())


def test_page_and_element_drift_stay_stale_when_native_globals_are_missing() -> None:
    fake, environment, task, world = _fixture()
    fake.probe_task = {}
    changed_page = copy.deepcopy(fake.post)
    changed_page["url"] = "http://shopping_admin.example.test/admin/dashboard"
    fake.post = changed_page

    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.STALE_BINDING,
    )
    assert result.adapter_evidence["currentness_reason"] == "page_changed"
    assert result.adapter_evidence["currentness_task_state_source"] == "lifecycle_fallback"
    asyncio.run(environment.close())

    fake, environment, task, world = _fixture()
    fake.probe_task = {}
    detached = copy.deepcopy(fake.post)
    detached["axtree_object"]["nodes"] = [
        node for node in detached["axtree_object"]["nodes"] if node.get("browsergym_id") != "1"
    ]
    fake.post = detached

    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result

    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.STALE_BINDING,
    )
    assert result.adapter_evidence["currentness_reason"] == "element_missing"
    assert environment.step_calls == 0
    asyncio.run(environment.close())


def test_malformed_probe_is_currentness_unavailable_and_zero_step() -> None:
    fake, environment, task, world = _fixture()
    fake.probe_override = {"raw": [], "task": "malformed"}
    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result
    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.CURRENTNESS_UNAVAILABLE,
    )
    assert environment.step_calls == 0
    assert environment.probe_calls == fake.currentness_probe_count == 1
    asyncio.run(environment.close())


def test_capture_then_disabled_readonly_or_detached_is_zero_step_stale() -> None:
    for mutation in ("disabled", "readonly", "detached"):
        fake, environment, task, world = _fixture()
        live = copy.deepcopy(fake.post)
        if mutation == "disabled":
            live[PRIVATE_CONTROL_PROPERTIES_KEY]["2"]["enabled"] = False
        elif mutation == "readonly":
            live[PRIVATE_CONTROL_PROPERTIES_KEY]["2"]["readonly"] = True
        else:
            live["axtree_object"]["nodes"] = [
                node for node in live["axtree_object"]["nodes"] if node.get("browsergym_id") != "2"
            ]
        fake.post = live
        result = asyncio.run(environment.execute(request_for(world, task, "type_text", {"text": "x"}))).result
        assert (result.dispatch_status, result.error) == (
            DispatchStatus.NOT_SENT,
            ActionError.STALE_BINDING,
        )
        assert environment.step_calls == 0
        assert environment.probe_calls == fake.currentness_probe_count == 1
        asyncio.run(environment.close())


def test_terminal_probe_is_zero_step_stale_and_not_relaxed() -> None:
    fake, environment, task, world = _fixture()
    fake.probe_task["done"] = True
    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result
    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.STALE_BINDING,
    )
    assert environment.last_currentness_decision is not None
    assert environment.last_currentness_decision.reason is BrowserGymCurrentnessReason.TASK_DONE
    assert environment.step_calls == 0
    assert environment.probe_calls == fake.currentness_probe_count == 1
    asyncio.run(environment.close())


def test_currentness_probe_has_no_capture_or_projection_side_effect() -> None:
    fake, environment, task, world = _fixture()
    request = request_for(world, task, "activate")
    private = environment.bindings.get(request.binding.binding_id)
    assert private is not None
    before = (
        environment._observation_serial,  # noqa: SLF001 - currentness side-effect gate
        environment.bindings.count,
        environment._task_state,  # noqa: SLF001
        environment.full_observation_count,
        environment.capture_calls,
        environment.step_calls,
    )

    error, physical_count = environment._probe_currentness(request, private)  # noqa: SLF001

    after = (
        environment._observation_serial,  # noqa: SLF001
        environment.bindings.count,
        environment._task_state,  # noqa: SLF001
        environment.full_observation_count,
        environment.capture_calls,
        environment.step_calls,
    )
    assert error is None and physical_count == 1
    assert after == before
    assert environment.probe_calls == fake.currentness_probe_count == 1
    asyncio.run(environment.close())


def test_binding_epoch_drift_is_zero_step() -> None:
    fake, environment, task, world = _fixture()
    request = request_for(world, task, "activate")
    request = replace(
        request,
        binding=replace(request.binding, source_revision="different"),
    )
    result = asyncio.run(environment.execute(request)).result
    assert result.dispatch_status is DispatchStatus.NOT_SENT
    assert environment.last_currentness_decision is not None
    assert environment.last_currentness_decision.reason is (BrowserGymCurrentnessReason.BINDING_EPOCH_CHANGED)
    assert environment.step_calls == 0
    assert environment.probe_calls == fake.currentness_probe_count == 1
    asyncio.run(environment.close())

    fake, environment, task, world = _fixture(fail_probe=True)
    result = asyncio.run(environment.execute(request_for(world, task, "activate"))).result
    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT,
        ActionError.CURRENTNESS_UNAVAILABLE,
    )
    assert fake.actions == [] and environment.step_calls == 0 and environment.probe_calls == 1
    asyncio.run(environment.close())


def test_step_exception_after_dispatch_is_sent_unknown_without_retry() -> None:
    fake, environment, task, world = _fixture(fail_step=True)
    outcome = asyncio.run(environment.execute(request_for(world, task, "activate")))
    result = outcome.result
    assert result.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert result.error is ActionError.EXECUTION_FAILED
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.phase is ExecutionDiagnosticPhase.DISPATCH_WAIT
    assert diagnostic.exception_type == "RuntimeError"
    assert diagnostic.exception_module == "builtins"
    assert diagnostic.safe_message == "after dispatch"
    assert diagnostic.dispatch_crossed is True
    assert diagnostic.elapsed_ms >= 0
    assert diagnostic.traceback_ref.startswith("traceback:sha256:")
    assert len(fake.actions) == 1 and environment.step_calls == 1
    asyncio.run(environment.close())


def test_open_preserves_reset_failure_when_cleanup_also_fails() -> None:
    class FailingOpenBrowserGym:
        def __init__(self, *_args, **_kwargs):
            pass

        def reset(self, *, seed):
            del seed
            raise ValueError("reset primary")

        def close(self):
            raise TimeoutError("cleanup secondary")

    with pytest.raises(ValueError, match="reset primary") as caught:
        BrowserGymSurfaceAdapter.open(
            "browsergym/test",
            1,
            gym_factory=FailingOpenBrowserGym,
        )

    diagnostic = getattr(caught.value, "__affordance_cleanup_diagnostic__")
    assert diagnostic.phase is ExecutionDiagnosticPhase.CLEANUP
    assert diagnostic.exception_type == "TimeoutError"
    assert diagnostic.safe_message == "cleanup secondary"


def test_browsergym_synchronous_close_runs_off_the_asyncio_event_loop() -> None:
    fake, environment, _task, _world = _fixture()
    original_close = fake.close

    def slow_close() -> None:
        time.sleep(0.1)
        original_close()

    fake.close = slow_close

    async def scenario() -> None:
        closing = asyncio.create_task(environment.close())
        await asyncio.sleep(0.01)
        assert not closing.done()
        await closing

    asyncio.run(scenario())


def test_independent_uncertain_dispatch_recapture_drains_its_own_diagnostic() -> None:
    class FailingCaptures(FakeBrowserGym):
        capture_attempt = 0

        def capture_current(self):
            self.capture_attempt += 1
            raise RuntimeError(f"capture-{self.capture_attempt}-raw")

    raw = raw_observation(ax_node("1", "button", "okay"))
    fake = FailingCaptures(raw, raw, fail_step=True)
    environment, task = open_fake(fake)
    world = start_environment(environment, task)
    request = request_for(world, task, "activate")

    outcome = asyncio.run(environment.execute(request))
    recovery = asyncio.run(
        environment.world.recover_execution_observation(
            request,
            WorldObservationRequest(
                ObservationRequestKind.POST_ACTION_FALLBACK,
                "held-out uncertain recovery",
                request.verification_needs,
            ),
        )
    )

    assert [item.safe_message for item in outcome.result.diagnostics] == [
        "after dispatch",
        "capture-1-raw",
    ]
    assert [item.safe_message for item in recovery.diagnostics] == ["capture-2-raw"]
    assert environment.surface.take_execution_diagnostics() == ()
    asyncio.run(environment.close())


def test_post_step_observation_is_returned_without_capture_or_second_step() -> None:
    fake, environment, task, world = _fixture()
    outcome = asyncio.run(environment.execute(request_for(world, task, "activate")))
    assert outcome.result.dispatch_status is DispatchStatus.SENT
    after = outcome.post_acquisition.observation
    assert after is not None
    assert after.observation_id != world.observation_id
    assert len(fake.actions) == 1 and environment.full_observation_count == 2
    assert environment.capture_calls == 0
    asyncio.run(environment.close())


def test_independent_capture_is_active_fresh_and_does_not_step() -> None:
    fake, environment, task, world = _fixture()
    before_binding = world.bindings[0].binding_id
    before_entities = tuple(item.target_id for item in world.targets)
    acquisition = asyncio.run(
        environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "refresh current browser world",
            )
        )
    )
    after = acquisition.observation
    assert after is not None
    assert after.observation_id != world.observation_id
    assert tuple(item.target_id for item in after.targets) == before_entities
    assert after.bindings[0].binding_id != before_binding
    assert fake.capture_count == 1
    assert fake.actions == [] and environment.step_calls == 0
    assert environment.capture_calls == 1
    asyncio.run(environment.close())


def test_stable_entity_identity_does_not_extend_old_binding_authority() -> None:
    fake, environment, task, world = _fixture()
    old_request = request_for(world, task, "activate")
    acquisition = asyncio.run(
        environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "advance the observation epoch",
            )
        )
    )
    assert acquisition.observation is not None
    assert acquisition.observation.targets[0].target_id == world.targets[0].target_id

    result = asyncio.run(environment.execute(old_request)).result

    assert result.dispatch_status is DispatchStatus.NOT_SENT
    assert fake.actions == [] and environment.step_calls == 0
    asyncio.run(environment.close())


def test_preparation_and_logical_reset_each_happen_exactly_once() -> None:
    fake, environment, task, _world = _fixture()
    assert fake.reset_count == 1
    assert environment.backend_reset_calls == 1
    assert environment.logical_reset_calls == 1
    assert environment.capture_calls == 0
    asyncio.run(environment.close())
