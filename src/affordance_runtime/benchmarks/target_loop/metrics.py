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
        before = getattr(getattr(self.wrapped, "port", None), "calls", None)
        outcome = await self.wrapped.decide(context)
        after = getattr(getattr(self.wrapped, "port", None), "calls", None)
        if isinstance(before, int) and isinstance(after, int):
            self.counters.provider_attempts += max(0, after - before)
        elif getattr(self.wrapped, "last_metadata", None) is not None:
            self.counters.provider_attempts += 1
        return outcome


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
        outcome = await self.wrapped.evaluate(task, observation)
        judge = getattr(self.wrapped, "semantic_judge", None)
        if judge is not None and getattr(judge, "last_metadata", None) is not None:
            self.counters.semantic_judge_calls += 1
            self.counters.provider_attempts += 1
        return outcome
