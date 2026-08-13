import asyncio
from dataclasses import dataclass, replace

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _world

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    RequestActionPage,
    SelectAction,
)
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
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


@dataclass(frozen=True)
class _Objective:
    direct_target_ids: tuple[str, ...] = ()
    direct_effects: tuple[str, ...] = ()
    enabling_target_ids: tuple[str, ...] = ()
    enabling_action_hints: tuple[str, ...] = ()


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
    objective = _Objective(direct_target_ids=("target:00",))

    default = pager.page(space, objective)
    other = pager.page(space, objective, relevance_role=ActionRelevanceRole.OTHER)

    assert default.visible_action_ids[0] == "action:00"
    assert len(default.visible_action_ids) == 8
    assert default.total_count == 40 and default.has_more
    assert "action:39" not in default.visible_action_ids
    assert "action:39" in other.visible_action_ids or other.has_more
    assert other.page_id != default.page_id


def test_cursor_pager_traverses_every_action_without_overlap() -> None:
    space = ActionSpace("obs:1", tuple(_option(index) for index in range(20)))
    pager = ActionPager(page_size=6)
    pages = []
    cursor = ""

    while True:
        page = pager.page(space, cursor=cursor)
        pages.append(page)
        if not page.has_more:
            break
        assert page.next_cursor
        cursor = page.next_cursor

    flattened = tuple(action_id for page in pages for action_id in page.visible_action_ids)
    assert flattened == tuple(option.action_id for option in space.options)
    assert len(flattened) == len(set(flattened))
    assert pages[-1].next_cursor == ""


def test_filtered_page_can_continue_and_cursor_is_filter_bound() -> None:
    options = tuple(_option(index, action="read", effect="") for index in range(12))
    space = ActionSpace("obs:1", options)
    pager = ActionPager(page_size=5)

    first = pager.page(space, relevance_role=ActionRelevanceRole.INFORMATION)
    second = pager.page(
        space,
        relevance_role=ActionRelevanceRole.INFORMATION,
        cursor=first.next_cursor,
    )

    assert first.visible_action_ids != second.visible_action_ids
    assert second.cursor == first.next_cursor
    with pytest.raises(ValueError, match="cursor"):
        pager.page(space, query="different", cursor=first.next_cursor)


def test_single_oversized_option_fails_closed_instead_of_bypassing_byte_budget() -> None:
    option = replace(_option(0), description="x" * 1_000)

    with pytest.raises(ValueError, match="byte budget"):
        ActionPager(max_projected_bytes=100).page(ActionSpace("obs:1", (option,)))


def test_page_weight_counts_only_model_visible_destination_slice() -> None:
    destinations = tuple(f"destination:{index:04}" for index in range(500))
    option = replace(
        _option(0),
        destination_required=True,
        eligible_destination_ids=destinations,
    )

    page = ActionPager(max_projected_bytes=600).page(
        ActionSpace("obs:1", (option,)),
        max_destinations_per_option=1,
    )

    assert page.visible_action_ids == (option.action_id,)
    assert page.visible_destination_ids(option.action_id) == (destinations[0],)


def test_empty_filtered_page_is_not_a_truncated_page() -> None:
    page = ActionPager(page_size=1).page(
        ActionSpace("obs:1", (_option(0),)),
        target_id="target:missing",
    )

    assert page.visible_action_ids == ()
    assert page.total_count == 0
    assert not page.has_more and not page.next_cursor


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
        replace(
            target_page,
            visible_action_ids=("action:00",),
            visible_destinations=(("action:00", ()),),
        )


def test_default_page_ranks_direct_enabling_information_then_other() -> None:
    options = (
        _option(0),
        _option(1),
        _option(2, action="read", effect=""),
        _option(3),
    )
    objective = _Objective(
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


def test_page_a_to_b_to_a_never_revalidates_first_page_decision() -> None:
    before = _two_action_world("before", False)

    class Policy:
        calls = 0
        first_page_decision = None
        context_ids = []

        async def decide(self, context):
            self.calls += 1
            self.context_ids.append(context.context_id)
            if self.calls == 1:
                self.first_page_decision = SelectAction(
                    context.context_id, context.actions.options[0].action_id
                )
                return RequestActionPage(context.context_id, target_id="z-other-toggle")
            if self.calls == 2:
                return RequestActionPage(context.context_id)
            if self.calls == 3:
                return self.first_page_decision
            return Abort(context.context_id, "old page decision rejected", "policy")

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
        assert len(set(policy.context_ids)) == 3
        assert result.execution_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_next_page_action_is_selectable_and_model_sees_active_cursor_state() -> None:
    before = _two_action_world("before", False)
    after = _two_action_world("after", True)

    class Policy:
        first_action_id = ""

        async def decide(self, context):
            if not self.first_action_id:
                self.first_action_id = context.actions.options[0].action_id
                assert context.actions.has_more
                assert context.actions.next_cursor
                return RequestActionPage(context.context_id, cursor=context.actions.next_cursor)
            assert context.actions.active_query == ""
            assert context.actions.active_target_filter == ""
            assert context.actions.active_relevance_filter == ""
            assert context.actions.options[0].action_id != self.first_action_id
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        environment = StaticEnvironment([before, after], [_sent()])
        result = await AgentEpisodeRunner(
            AgentLoop(
                Policy(),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                context_builder=ContextBuilder(pager=ActionPager(page_size=1)),
            )
        ).run(environment, _paging_task())

        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ("forged", "filter_change", "previous"))
def test_page_cursor_requires_exact_current_continuation(mode: str) -> None:
    before = _two_action_world("before", False)

    class Policy:
        calls = 0
        first_cursor = ""

        async def decide(self, context):
            self.calls += 1
            cursor = context.actions.next_cursor
            if self.calls == 1:
                self.first_cursor = cursor
                if mode == "forged":
                    return RequestActionPage(context.context_id, cursor=cursor + "forged")
                if mode == "filter_change":
                    return RequestActionPage(context.context_id, query="other", cursor=cursor)
                return RequestActionPage(context.context_id, cursor=cursor)
            return RequestActionPage(context.context_id, cursor=self.first_cursor)

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


def test_previous_page_action_is_rejected_even_with_current_context_id() -> None:
    before = _two_action_world("before", False)

    class Policy:
        previous_action_id = ""

        async def decide(self, context):
            if not self.previous_action_id:
                self.previous_action_id = context.actions.options[0].action_id
                return RequestActionPage(context.context_id, cursor=context.actions.next_cursor)
            return SelectAction(context.context_id, self.previous_action_id)

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


def test_confirmed_hidden_action_gets_a_coherent_private_execution_page() -> None:
    def medium_world(identity: str, enabled: bool):
        world = _two_action_world(identity, enabled)
        return replace(world, bindings=tuple(replace(item, risk=ActionRisk.MEDIUM) for item in world.bindings))

    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return RequestActionPage(context.context_id, target_id="z-other-toggle")
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        task = replace(_paging_task(), risk_profile=RiskProfile.MEDIUM)
        environment = StaticEnvironment(
            [medium_world("before", False), medium_world("fresh", False), medium_world("after", True)],
            [_sent()],
        )
        session = await AgentEpisodeRunner(
            AgentLoop(
                Policy(),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                context_builder=ContextBuilder(pager=ActionPager(page_size=1)),
            )
        ).start(environment, task)
        paused = await session.run_until_pause()
        request = paused.confirmation_request
        assert request is not None

        completed = await session.resolve_confirmation(
            ConfirmationDecision(request.confirmation_id, request.subject_id, ConfirmationDecisionKind.CONFIRM)
        )

        assert completed.status == AgentLoopStatus.DONE
        executed = environment.executed_requests[0]
        assert executed.context_id == session.current_context_snapshot.context_id
        assert executed.selection.action_id in session.current_action_page.visible_action_ids
        assert session.current_action_page.total_count == 1

    asyncio.run(scenario())
