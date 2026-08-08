import asyncio
from dataclasses import replace

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _world

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    RequestActionPage,
    SelectAction,
)
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.task import LocalObjective, LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionOption,
    ActionPager,
    ActionRelevanceRole,
    ActionRisk,
    ActionSpace,
    ActionSpaceBuilder,
    SemanticTarget,
)


def _option(index: int, *, action: str = "activate", effect: str = "changed") -> ActionOption:
    return ActionOption(
        f"action:{index:02}",
        "obs:1",
        action,
        f"target:{index:02}",
        "observation" if action == "read" else "local_reversible",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:1",
        (f"binding:{index:02}",),
        f"{action} public target {index:02}",
        () if action == "read" else (effect,),
        ActionRisk.LOW,
    )


def test_action_page_is_bounded_truthful_and_other_remains_retrievable() -> None:
    options = tuple(_option(index) for index in range(40))
    space = ActionSpace("obs:1", options)
    pager = ActionPager(page_size=8)
    objective = LocalObjective({"changed": True}, direct_target_ids=("target:00",))

    default = pager.page(space, objective)
    other = pager.page(space, objective, relevance_role=ActionRelevanceRole.OTHER)

    assert default.visible_action_ids[0] == "action:00"
    assert len(default.visible_action_ids) == 8
    assert default.total_count == 40 and default.has_more
    assert "action:39" not in default.visible_action_ids
    assert "action:39" in other.visible_action_ids or other.has_more
    assert other.page_id != default.page_id


def test_action_page_filters_are_exact_and_page_identity_binds_visible_membership() -> None:
    options = (_option(0), _option(1, action="read", effect=""), _option(2))
    space = ActionSpace("obs:1", options)
    pager = ActionPager(page_size=8)

    target_page = pager.page(space, target_id="target:02")
    query_page = pager.page(space, query="PUBLIC TARGET 01")
    info_page = pager.page(space, relevance_role=ActionRelevanceRole.INFORMATION)

    assert target_page.visible_action_ids == ("action:02",)
    assert query_page.visible_action_ids == ("action:01",)
    assert info_page.visible_action_ids == ("action:01",)
    assert len({target_page.page_id, query_page.page_id, info_page.page_id}) == 3
    with pytest.raises(ValueError, match="identity"):
        replace(target_page, visible_action_ids=("action:00",))


def test_default_page_ranks_direct_enabling_information_then_other() -> None:
    options = (
        _option(0),
        _option(1),
        _option(2, action="read", effect=""),
        _option(3),
    )
    objective = LocalObjective(
        {"changed": True},
        direct_target_ids=("target:00",),
        enabling_target_ids=("target:01",),
    )

    page = ActionPager(page_size=8).page(ActionSpace("obs:1", options), objective)

    assert page.visible_action_ids == ("action:00", "action:01", "action:02", "action:03")
    assert tuple(item.role for _, item in page.relevance) == (
        ActionRelevanceRole.DIRECT,
        ActionRelevanceRole.ENABLING,
        ActionRelevanceRole.INFORMATION,
        ActionRelevanceRole.OTHER,
    )


def _two_action_world(identity: str, enabled: bool):
    base = _world(identity, enabled)
    second_target = SemanticTarget("z-other-toggle", "button", "Other toggle", {"enabled": enabled})
    second_binding = replace(
        base.bindings[0],
        binding_id=f"binding:{identity}:other",
        target_id=second_target.target_id,
        source_target_id=second_target.target_id,
        target_fingerprint=f"fingerprint:{identity}:other",
    )
    return replace(base, targets=(*base.targets, second_target), bindings=(*base.bindings, second_binding))


def _paging_task() -> TaskGoal:
    return TaskGoal(
        "paging",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
        risk_profile=RiskProfile.LOW,
        loop_budget=LoopBudget(3, 5),
    )


def test_hidden_page_action_id_is_rejected_with_zero_execution() -> None:
    before = _two_action_world("before", False)
    space = ActionSpaceBuilder().build(_paging_task(), before)
    hidden_id = space.options[1].action_id

    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, hidden_id)

    async def scenario() -> None:
        environment = StaticEnvironment([before])
        result = await AgentEpisodeRunner(
            AgentLoop(
                Policy(),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                context_builder=ContextBuilder(pager=ActionPager(page_size=1)),
            )
        ).run(environment, _paging_task())

        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_page_request_changes_context_and_old_page_decision_is_stale_zero_call() -> None:
    before = _two_action_world("before", False)

    class Policy:
        calls = 0
        old_context_id = ""

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                self.old_context_id = context.context_id
                return RequestActionPage(context.context_id, target_id="z-other-toggle")
            if self.calls == 2:
                assert context.context_id != self.old_context_id
                return SelectAction(self.old_context_id, context.actions.options[0].action_id)
            return Abort(context.context_id, "stale page rejected", "policy")

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([before])
        result = await AgentEpisodeRunner(
            AgentLoop(
                policy,
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                context_builder=ContextBuilder(pager=ActionPager(page_size=1)),
            )
        ).run(environment, _paging_task())

        assert result.status == AgentLoopStatus.FAILED
        assert policy.calls == 3
        assert result.execution_count == 0
        assert result.observation_count == 1
        assert environment.executed_requests == []

    asyncio.run(scenario())
