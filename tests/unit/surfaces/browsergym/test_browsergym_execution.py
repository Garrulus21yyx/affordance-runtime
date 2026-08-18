import asyncio
import copy
from dataclasses import replace

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.execution import ActionError, DispatchStatus
from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessReason,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
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


def test_scroll_dispatches_viewport_browsergym_scroll_without_element_route() -> None:
    fake, environment, task, world = _fixture()
    request = _request_for_role(world, task, "scroll", "viewport", {"direction": "down", "extent": "small"})

    outcome = asyncio.run(environment.execute(request))

    assert outcome.result.dispatch_status is DispatchStatus.SENT
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

    focused_outcome = asyncio.run(environment.execute(focused_request))

    assert focused_outcome.result.dispatch_status is DispatchStatus.SENT
    assert fake.actions == ['keyboard_press("Escape")']
    assert environment.keyboard_press_calls == 1
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
    assert len(fake.actions) == 1 and environment.step_calls == 1
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
