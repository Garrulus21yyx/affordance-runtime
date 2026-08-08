"""Harness-only counters that forward without changing Runtime semantics."""

from dataclasses import dataclass


@dataclass
class CounterState:
    policy_calls: int = 0
    action_evaluator_calls: int = 0
    task_evaluator_calls: int = 0
    semantic_judge_calls: int = 0
    provider_attempts: int = 0


@dataclass
class CountingPolicy:
    wrapped: object
    counters: CounterState

    async def decide(self, context):
        self.counters.policy_calls += 1
        return await self.wrapped.decide(context)


@dataclass
class CountingActionEvaluator:
    wrapped: object
    counters: CounterState

    async def evaluate(self, task, before, request, result, after):
        self.counters.action_evaluator_calls += 1
        return await self.wrapped.evaluate(task, before, request, result, after)


@dataclass
class CountingTaskEvaluator:
    wrapped: object
    counters: CounterState

    async def evaluate(self, task, observation):
        self.counters.task_evaluator_calls += 1
        return await self.wrapped.evaluate(task, observation)
