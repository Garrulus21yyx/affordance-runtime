"""Explicit fixed internal target-loop manifests; no plugin discovery."""

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCase, BenchmarkComposition
from affordance_runtime.benchmarks.target_loop.evaluation_support import (
    output_case_parts,
    semantic_environment,
    semantic_evaluator,
    semantic_task,
)
from affordance_runtime.benchmarks.target_loop.model_policy_support import (
    local_http_policy,
    local_http_policy_environment,
)
from affordance_runtime.benchmarks.target_loop.support import (
    CurrentFactActionEvaluator,
    PagingPolicy,
    ScriptedDecisionPort,
    SelectThenAbortPolicy,
    SharedTaskEvaluator,
    confirmation_environment,
    confirmation_task,
    forbidden_environment,
    forbidden_task,
    low_risk_environment,
    paging_environment,
    policy_for,
    shared_environment,
    shared_task,
    stale_environment,
)
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.model_policy import ModelBackedAgentPolicy


def build_manifest(suite_id: str, profile_id: str, seed: int):
    if suite_id == "internal-core" and profile_id in {"deterministic", "scripted-model"}:
        return (
            *(_shared_case(surface, profile_id, seed) for surface in ("dom", "visual", "wot")),
            _paging_case(seed),
            _low_risk_case(seed),
        )
    if suite_id == "internal-core" and profile_id == "local-http-model-policy":
        return tuple(_shared_http_case(surface, seed) for surface in ("dom", "visual", "wot"))
    if suite_id == "internal-safety" and profile_id == "scripted-model":
        return (
            _sent_unknown_case(seed), _confirmation_case(seed), _stale_case(seed),
            _provider_failure_case(seed), _forbidden_case(seed),
        )
    if suite_id == "internal-evaluation" and profile_id == "local-http-semantic-judge":
        return (_semantic_case(seed), _output_case(seed))
    raise ValueError("unknown fixed target-loop suite/profile")


def _shared_case(surface: str, profile: str, seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        f"shared-{surface}", "internal-core", f"{surface} shared-state target loop",
        shared_task, lambda: shared_environment(surface),
        lambda: BenchmarkComposition(policy_for(profile), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("observations", "executions", "policy_calls"), "internal-core",
    )


def _shared_http_case(surface: str, seed: int) -> BenchmarkCase:
    holder = {}

    def environment_factory():
        environment = local_http_policy_environment(surface)
        holder["environment"] = environment
        return environment

    def composition_factory():
        return BenchmarkComposition(
            local_http_policy(holder["environment"]),
            CurrentFactActionEvaluator(), SharedTaskEvaluator(),
        )

    return BenchmarkCase(
        f"shared-{surface}-http-policy", "internal-core", f"{surface} existing-ModelPort policy",
        shared_task, environment_factory, composition_factory,
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("provider_attempts", "executions"), "internal-core",
    )


def _paging_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "second-page-execution", "internal-core", "request next page then execute once",
        shared_task, paging_environment,
        lambda: BenchmarkComposition(PagingPolicy(), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("page_request_count", "executions"), "internal-core",
    )


def _stale_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "stale-zero-call", "internal-safety", "stale binding never reaches effectful dispatch",
        shared_task, stale_environment,
        lambda: BenchmarkComposition(SelectThenAbortPolicy(), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.FAILED,), 10.0, seed,
        ("stale_opportunities", "stale_zero_call_violations"), "internal-safety",
    )


def _low_risk_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "low-risk-inconclusive", "internal-core", "fresh low-risk inconclusive action continues",
        shared_task, low_risk_environment,
        lambda: BenchmarkComposition(policy_for("deterministic"), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("executions", "duplicate_unknown_attempts"), "internal-core",
    )


def _confirmation_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "confirmation-fresh-rebind", "internal-safety", "typed confirmation then fresh rebind",
        confirmation_task, confirmation_environment,
        lambda: BenchmarkComposition(policy_for("deterministic"), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("confirmations", "executions"), "internal-safety", auto_confirm=True,
    )


def _forbidden_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "forbidden-route-containment", "internal-safety", "forbidden higher-risk route is never bound",
        forbidden_task, forbidden_environment,
        lambda: BenchmarkComposition(policy_for("deterministic"), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("forbidden_effect_attempts", "executions"), "internal-safety",
    )


def _sent_unknown_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "sent-unknown-no-replay", "internal-safety", "SENT_UNKNOWN stops without replay",
        shared_task, lambda: shared_environment("dom", sent_unknown=True),
        lambda: BenchmarkComposition(policy_for("scripted-model"), CurrentFactActionEvaluator(), SharedTaskEvaluator()),
        (AgentLoopStatus.WAITING_USER,), 10.0, seed,
        ("sent_unknown_count", "duplicate_unknown_attempts"), "internal-safety",
    )


def _provider_failure_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "provider-failure-zero-call", "internal-safety", "typed policy failure is zero execution",
        shared_task, lambda: shared_environment("dom"),
        lambda: BenchmarkComposition(
            ModelBackedAgentPolicy(ScriptedDecisionPort(fail=True)), CurrentFactActionEvaluator(), SharedTaskEvaluator()
        ),
        (AgentLoopStatus.FAILED,), 10.0, seed, ("executions", "policy_calls"), "internal-safety",
    )


def _semantic_case(seed: int) -> BenchmarkCase:
    holder = {}

    def environment_factory():
        environment = semantic_environment()
        holder["environment"] = environment
        return environment

    def composition_factory():
        environment = holder["environment"]
        return BenchmarkComposition(
            policy_for("local-http-semantic-judge"), CurrentFactActionEvaluator(), semantic_evaluator(environment)
        )

    return BenchmarkCase(
        "dynamic-semantic", "internal-evaluation", "create then evaluate semantic report",
        semantic_task, environment_factory, composition_factory, (AgentLoopStatus.DONE,), 10.0, seed,
        ("observations", "executions", "semantic_judge_calls"), "internal-evaluation",
    )


def _output_case(seed: int) -> BenchmarkCase:
    holder = {}

    def environment_factory():
        task, environment = output_case_parts()
        holder["task"] = task
        return environment

    return BenchmarkCase(
        "dynamic-output", "internal-evaluation", "criteria then required output progression",
        lambda: holder["task"], environment_factory,
        lambda: BenchmarkComposition(policy_for("deterministic"), CurrentFactActionEvaluator(), ProductionTaskEvaluator()),
        (AgentLoopStatus.DONE,), 10.0, seed,
        ("observations", "executions"), "internal-evaluation",
    )
