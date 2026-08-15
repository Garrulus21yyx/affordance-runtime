from __future__ import annotations

import asyncio
from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from affordance_runtime.agent import (
    Abort,
    AgentLoop,
    AgentLoopStatus,
    RequestActionPage,
    RequestObservation,
    SelectAction,
)
from affordance_runtime.agent.control_feedback import ControlFeedbackKind
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from tests.integration.agent.test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world
from tests.support.agent.static_environment import StaticEnvironment


def test_invalid_parameters_reach_next_normal_policy_context_once_then_correct() -> None:
    class Policy:
        contexts = []

        async def decide(self, context):
            self.contexts.append(context)
            option = context.actions.options[0]
            if len(self.contexts) == 1:
                return SelectAction(context.context_id, option.action_id, {"unknown": "private-value"})
            return SelectAction(context.context_id, option.action_id, {})

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            [_world("before", False), _world("after", True)],
            [_sent(DispatchStatus.SENT, True)],
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.DONE
        assert environment.execute_calls == 1
        assert len(policy.contexts) == 2
        assert policy.contexts[0].control_feedback is None
        feedback = policy.contexts[1].control_feedback
        assert feedback is not None
        assert feedback.kind == ControlFeedbackKind.REPAIRABLE_REJECTION.value
        assert feedback.public_field_paths == ("parameters.unknown",)
        assert feedback.violation is not None
        assert feedback.violation.contract_owner == "current_action_space"
        assert feedback.recovery is not None
        assert feedback.recovery.must_change_fields == ("parameters.unknown",)
        assert "private-value" not in repr(feedback)
        first = result.control_transitions[0]
        assert first.control_feedback is not None
        assert not first.execution_attempts and not first.acquisition_attempts

    asyncio.run(scenario())


def test_same_issue_with_different_invalid_values_terminates_without_execution() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            option = context.actions.options[0]
            return SelectAction(
                context.context_id,
                option.action_id,
                {"unknown": f"bad-{self.calls}"},
            )

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls == 2
        assert environment.execute_calls == 0
        assert result.runtime_failure is not None
        assert result.runtime_failure.code == "no_progress_control_repetition"

    asyncio.run(scenario())


def test_action_page_identity_churn_cannot_bypass_no_gain_repetition() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            return RequestActionPage(context.context_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls == 2
        assert environment.execute_calls == 0
        assert result.control_transitions[0].control_feedback is not None
        assert result.control_transitions[0].control_feedback.kind is ControlFeedbackKind.NO_INFORMATION_GAIN

    asyncio.run(scenario())


def test_casefold_equivalent_page_queries_are_bounded_as_one_no_gain_issue() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            query = "NO-SUCH-ACTION" if self.calls % 2 else "no-such-action"
            return RequestActionPage(context.context_id, query=query)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls == 3
        assert result.control_feedback_delivery_count == 1
        assert result.control_repetition_count == 1
        assert result.execution_count == 0
        assert result.currentness_probe_count == 0
        assert environment.execute_calls == 0
        assert environment.capture_calls == 0
        assert all(
            not transition.execution_attempts
            and not transition.acquisition_attempts
            for transition in result.control_transitions
        )

    asyncio.run(scenario())


def test_distinct_requests_with_same_page_result_are_bounded() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            query = "no-match-alpha" if self.calls % 2 else "no-match-beta"
            return RequestActionPage(context.context_id, query=query)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls <= 4
        assert result.control_feedback_delivery_count >= 1
        assert result.control_repetition_count == 1
        assert result.execution_count == 0
        assert result.currentness_probe_count == 0
        assert environment.execute_calls == 0
        assert environment.capture_calls == 0
        assert result.control_transitions[0].decision_result == "page_changed"
        assert result.control_transitions[0].control_feedback is None

    asyncio.run(scenario())


@given(st.lists(st.one_of(st.none(), st.integers(min_value=0, max_value=5)), min_size=1, max_size=8))
@settings(max_examples=40)
def test_generated_request_view_churn_without_new_facts_is_bounded(
    pattern: list[int | None],
) -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            item = pattern[self.calls % len(pattern)]
            self.calls += 1
            if item is None:
                return RequestObservation(
                    context.context_id,
                    "shared-toggle",
                    "structural",
                    "structural",
                    f"echo-{self.calls}",
                )
            return RequestActionPage(context.context_id, query=f"no-match-{item}")

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            initial_observation=_world("before", False),
            independent_observations=tuple(
                _world(f"fresh-{index}", False) for index in range(5)
            ),
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        # One truly unseen page result may grant gain once; thereafter the
        # shared two-issue budget is absorbing.
        assert policy.calls <= 5
        assert result.control_repetition_count == 1
        assert environment.execute_calls == 0
        assert result.currentness_probe_count == 0

    asyncio.run(scenario())


def test_page_and_unchanged_policy_observation_cannot_reset_each_other() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls % 2:
                return RequestActionPage(context.context_id, query="no-match")
            return RequestObservation(
                context.context_id,
                "shared-toggle",
                "structural",
                "structural",
                f"request view {self.calls}",
            )

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            initial_observation=_world("before", False),
            independent_observations=tuple(
                _world(f"fresh-{index}", False) for index in range(6)
            ),
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls <= 4
        assert result.control_repetition_count == 1
        assert result.execution_count == 0
        assert result.currentness_probe_count == 0
        assert environment.execute_calls == 0
        assert environment.capture_calls <= 2

    asyncio.run(scenario())


def test_policy_observation_fresh_identity_without_semantic_gain_is_bounded() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            return RequestObservation(
                context.context_id,
                "shared-toggle",
                "structural",
                "structural",
                f"free form reason {self.calls}",
            )

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(
                _world("fresh-one", False),
                _world("fresh-two", False),
            ),
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls == 2
        assert environment.capture_calls == 2
        assert environment.execute_calls == 0
        assert result.control_transitions[0].control_feedback is not None
        assert result.control_transitions[0].control_feedback.source.value == "policy_observation"

    asyncio.run(scenario())


def test_policy_observation_task_terminal_precedes_no_gain_feedback() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            return RequestObservation(
                context.context_id,
                "shared-toggle",
                "structural",
                "structural",
                "refresh",
            )

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(_world("terminal", True),),
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.DONE
        assert policy.calls == 1
        assert result.control_transitions[0].control_feedback is None

    asyncio.run(scenario())


def test_three_distinct_admission_page_issues_share_one_budget() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            option = context.actions.options[0]
            if self.calls == 1:
                return SelectAction(context.context_id, option.action_id, {"unknown": "x"})
            if self.calls == 2:
                return SelectAction(context.context_id, "outside-current-page")
            return RequestActionPage(context.context_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.BLOCKED
        assert result.reason_code == "no_progress_control_repetition"
        assert policy.calls == 3
        assert environment.execute_calls == 0
        assert result.control_issue_consumption_count == 2
        assert result.control_feedback_delivery_count == 2

    asyncio.run(scenario())


def test_adapter_invalid_parameters_after_admission_is_not_policy_repair() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            [_world("before", False)],
            [ActionResult(
                "*",
                DispatchStatus.NOT_SENT,
                "dom",
                False,
                ActionError.INVALID_PARAMETERS,
            )],
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.FAILED
        assert result.reason_code == "action_not_dispatched"
        assert policy.calls == 1
        assert environment.execute_calls == 1
        assert result.control_transitions[0].control_feedback is None
        assert result.runtime_failure is not None
        assert result.runtime_failure.stage.value == "execution"

    asyncio.run(scenario())


def test_no_effect_feedback_carries_expected_observed_delta_and_mechanical_recovery() -> None:
    class Policy:
        contexts = []

        async def decide(self, context):
            self.contexts.append(context)
            if len(self.contexts) == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            return Abort(context.context_id, "verified no effect", "no_progress")

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            [_world("before", False), _world("after", False)],
            [_sent(DispatchStatus.SENT, True)],
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        feedback = policy.contexts[1].control_feedback
        assert feedback is not None
        assert feedback.code == "action_no_effect_change_strategy"
        assert feedback.related_decision is not None
        assert feedback.semantic_effect is not None
        assert feedback.semantic_effect.dispatch == "sent"
        assert feedback.semantic_effect.observed_effect == "no_effect_confirmed"
        assert feedback.semantic_effect.expected_effects == ("shared_state_enabled",)
        assert feedback.recovery is not None
        assert feedback.recovery.retry_allowed is False
        assert feedback.recovery.rollback_available is False
        assert feedback.recovery.strategy_change_required is True
        assert result.execution_count == 1

    asyncio.run(scenario())


def test_exact_replay_after_confirmed_no_effect_is_zero_dispatch() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            [_world("before", False), _world("after", False)],
            [_sent(DispatchStatus.SENT, True)],
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.FAILED
        assert result.reason_code == "no_progress_repetition"
        assert policy.calls == 2
        assert environment.execute_calls == 1
        assert result.execution_count == 1

    asyncio.run(scenario())


def test_empty_no_gain_filter_restores_default_recovery_page_without_new_epoch() -> None:
    class Policy:
        contexts = []

        async def decide(self, context):
            self.contexts.append(context)
            if len(self.contexts) <= 2:
                return RequestActionPage(context.context_id, query="no-match")
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            [_world("before", False), _world("after", True)],
            [_sent(DispatchStatus.SENT, True)],
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        recovery = policy.contexts[2]
        assert recovery.control_feedback is not None
        assert recovery.control_feedback.code == "action_page_no_information_gain"
        assert recovery.actions.options
        assert recovery.actions.active_query == ""
        assert recovery.control_feedback.recovery is not None
        assert recovery.control_feedback.recovery.offered_action_ids == tuple(
            option.action_id for option in recovery.actions.options
        )
        assert result.status is AgentLoopStatus.DONE
        assert result.control_repetition_count == 0

    asyncio.run(scenario())


def test_relevant_public_semantic_gain_resets_issue_budget() -> None:
    before = _world("before", False)
    renamed_base = _world("renamed", False)
    renamed_target = replace(renamed_base.targets[0], label="Enable renamed shared state")
    renamed_source = replace(renamed_base.sources[0], targets=(renamed_target,))
    renamed = replace(
        renamed_base,
        targets=(renamed_target,),
        sources=(renamed_source,),
    )

    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            option = context.actions.options[0]
            if self.calls in {1, 3}:
                return SelectAction(context.context_id, option.action_id, {"unknown": "x"})
            if self.calls == 2:
                return RequestObservation(
                    context.context_id,
                    "shared-toggle",
                    "structural",
                    "structural",
                    "refresh semantics",
                )
            return SelectAction(context.context_id, option.action_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment(
            initial_observation=before,
            independent_observations=(renamed,),
            post_observations=(_world("after", True),),
            results=(_sent(DispatchStatus.SENT, True),),
        )
        result = await (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.DONE
        assert policy.calls == 4
        assert environment.capture_calls == 1
        assert environment.execute_calls == 1
        assert result.control_repetition_count == 0
        assert result.control_issue_consumption_count == 2

    asyncio.run(scenario())
