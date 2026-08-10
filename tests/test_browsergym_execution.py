import asyncio

from browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
    request_for,
    start_environment,
)

from affordance_runtime.execution import ActionError, DispatchStatus


def _fixture(*, fail_step=False, fail_probe=False):
    raw = raw_observation(
        ax_node("1", "button", "okay"),
        ax_node("2", "textbox", "", properties=(("required", False),)),
        ax_node("3", "combobox", "", value="A", properties=(("expanded", False),)),
        ax_node("4", "option", "A"),
        ax_node("5", "option", "B"),
    )
    fake = FakeBrowserGym(raw, raw, fail_step=fail_step, fail_probe=fail_probe)
    common = {"exists": True, "url": raw["url"], "episode": "0", "ready": True, "done": False}
    fake.probes = {
        "1": {**common, "role": "button", "label": "okay", "state": {}},
        "2": {**common, "role": "textbox", "label": "", "state": {
            "value": "", "required": False,
        }},
        "3": {**common, "role": "combobox", "label": "", "state": {
            "value": "A", "expanded": False, "option_count": 2,
        }},
    }
    environment, task = open_fake(fake)
    return fake, environment, task, start_environment(environment, task)


def test_activate_fill_and_select_each_dispatch_one_official_action() -> None:
    expected = (
        ("activate", {}, "click("),
        ("fill", {"value": "hello"}, "fill("),
        ("select", {"value": "B"}, "select_option("),
    )
    for semantic, parameters, prefix in expected:
        fake, environment, task, world = _fixture()
        request = request_for(world, task, semantic, parameters)
        result = asyncio.run(environment.execute(request))
        assert result.dispatch_status is DispatchStatus.SENT
        assert len(fake.actions) == 1 and fake.actions[0].startswith(prefix)
        assert environment.probe_calls == 1 and environment.step_calls == 1
        asyncio.run(environment.close())


def test_stale_or_unavailable_currentness_is_not_sent_and_zero_step() -> None:
    fake, environment, task, world = _fixture()
    request = request_for(world, task, "activate")
    fake.probes["1"]["label"] = "changed"
    result = asyncio.run(environment.execute(request))
    assert (result.dispatch_status, result.error) == (DispatchStatus.NOT_SENT, ActionError.STALE_BINDING)
    assert fake.actions == [] and environment.step_calls == 0 and environment.probe_calls == 1
    asyncio.run(environment.close())

    fake, environment, task, world = _fixture(fail_probe=True)
    result = asyncio.run(environment.execute(request_for(world, task, "activate")))
    assert (result.dispatch_status, result.error) == (
        DispatchStatus.NOT_SENT, ActionError.CURRENTNESS_UNAVAILABLE,
    )
    assert fake.actions == [] and environment.step_calls == 0 and environment.probe_calls == 1
    asyncio.run(environment.close())


def test_step_exception_after_dispatch_is_sent_unknown_without_retry() -> None:
    fake, environment, task, world = _fixture(fail_step=True)
    result = asyncio.run(environment.execute(request_for(world, task, "activate")))
    assert result.dispatch_status is DispatchStatus.SENT_UNKNOWN
    assert result.error is ActionError.EXECUTION_FAILED
    assert len(fake.actions) == 1 and environment.step_calls == 1
    asyncio.run(environment.close())


def test_post_step_observation_cache_is_consumed_without_second_step() -> None:
    fake, environment, task, world = _fixture()
    result = asyncio.run(environment.execute(request_for(world, task, "activate")))
    assert result.dispatch_status is DispatchStatus.SENT
    after = asyncio.run(environment.observe("post action"))
    assert after.observation_id != world.observation_id
    assert len(fake.actions) == 1 and environment.full_observation_count == 2
    try:
        asyncio.run(environment.observe("duplicate"))
    except RuntimeError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("post-step cache was not consumed")
    asyncio.run(environment.close())
