"""Explicit fixed target-loop manifests; no plugin discovery."""

import os

from affordance_runtime.agent import RunStatus
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCase,
    BenchmarkComposition,
    BenchmarkManifest,
    MetricExpectation,
    MetricExpectationOperator,
)
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
from affordance_runtime.benchmarks.target_loop.real_adapter_support import (
    VisualStateCriterionJudge,
    real_adapter_task,
    real_dom_environment,
    real_visual_environment,
    real_visual_task,
    real_wot_environment,
)
from affordance_runtime.benchmarks.target_loop.support import (
    CurrentFactActionOutcomeProjector,
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
from affordance_runtime.benchmarks.webarena_verified import (
    WA_SELECTION_SEED,
    WA_W1_HELD_OUT_CASES,
    WA_W1_SMOKE_CASES,
    open_webarena_verified_case,
)
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.model.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.factory import model_roles_from_environment

WA_W1B_CASE_TIMEOUT_S = 900.0
WA_W1B_MAX_TURNS = 100
WA_W1B_MODEL_CALL_TIMEOUT_S = 90.0


def build_manifest(suite_id: str, profile_id: str, seed: int):
    if suite_id == "webarena-verified-w1b" and profile_id == "model-long-horizon":
        cases = tuple(
            _webarena_verified_w1b_case(case_ref, seed)
            for case_ref in (*WA_W1_SMOKE_CASES, *WA_W1_HELD_OUT_CASES)
        )
    elif suite_id == "internal-core" and profile_id in {"deterministic", "scripted-model"}:
        cases = (
            *(_shared_case(surface, profile_id, seed) for surface in ("dom", "visual", "wot")),
            _paging_case(seed),
            _low_risk_case(seed),
        )
    elif suite_id == "internal-core" and profile_id == "local-http-model-policy":
        cases = tuple(_shared_http_case(surface, seed) for surface in ("dom", "visual", "wot"))
    elif suite_id == "internal-safety" and profile_id == "scripted-model":
        cases = (
            _sent_unknown_case(seed), _confirmation_case(seed), _stale_case(seed),
            _provider_failure_case(seed), _forbidden_case(seed),
        )
    elif suite_id == "internal-evaluation" and profile_id == "local-http-semantic-judge":
        cases = (_semantic_case(seed), _output_case(seed))
    elif suite_id == "internal-real-adapters" and profile_id == "deterministic":
        cases = tuple(_real_adapter_case(surface, seed) for surface in ("dom", "visual", "wot"))
    else:
        raise ValueError("unknown fixed target-loop suite/profile")
    return BenchmarkManifest("target-loop-manifest.v1", suite_id, profile_id, seed, cases)


def _expect(**values: int) -> tuple[MetricExpectation, ...]:
    return tuple(
        MetricExpectation(name, MetricExpectationOperator.EQ, value)
        for name, value in values.items()
    )


def _webarena_verified_w1b_case(case_ref, seed: int) -> BenchmarkCase:
    holder: dict[str, object] = {}

    def environment_factory(_metrics):
        environment, task, evaluator = open_webarena_verified_case(
            case_ref,
            seed=seed,
            max_turns=WA_W1B_MAX_TURNS,
        )
        holder["task"] = task
        holder["evaluator"] = evaluator
        return environment

    def task_factory():
        task = holder.get("task")
        if task is None:
            raise RuntimeError("WebArena-Verified W1b task requested before environment setup")
        return task

    def composition_factory(_metrics):
        evaluator = holder.get("evaluator")
        if evaluator is None:
            raise RuntimeError("WebArena-Verified W1b evaluator requested before environment setup")
        roles = model_roles_from_environment(os.environ, call_timeout_s=WA_W1B_MODEL_CALL_TIMEOUT_S)
        return BenchmarkComposition(
            roles.action_policy,
            ProductionActionOutcomeProjector(),
            evaluator,
            goal_compiler=roles.goal_compiler,
        )

    return BenchmarkCase(
        f"webarena-verified-w1b-task-{case_ref.task_id}",
        "webarena-verified-w1b",
        f"official WebArena-Verified W1b smoke task {case_ref.task_id}",
        task_factory,
        environment_factory,
        composition_factory,
        (RunStatus.DONE,),
        WA_W1B_CASE_TIMEOUT_S,
        seed or WA_SELECTION_SEED,
        (
            "observations",
            "policy_calls",
            "provider_attempts",
            "stop_send_count",
            "post_stop_capture_count",
            "native_evaluator_count",
        ),
        (
            *_expect(
                stop_send_count=1,
                post_stop_capture_count=1,
                native_evaluator_count=1,
            ),
        ),
    )


def _shared_case(surface: str, profile: str, seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        f"shared-{surface}", "internal-core", f"synthetic {surface} profile protocol case",
        shared_task, lambda _metrics: shared_environment(surface),
        lambda _metrics: BenchmarkComposition.atomic(policy_for(profile), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.DONE,), 10.0, seed,
        ("observations", "executions", "policy_calls", "effectful_dispatches"),
        _expect(observations=2, executions=1, effectful_dispatches=1),
    )


def _shared_http_case(surface: str, seed: int) -> BenchmarkCase:
    holder = {}

    def environment_factory(_metrics):
        environment = local_http_policy_environment(surface)
        holder["environment"] = environment
        return environment

    def composition_factory(_metrics):
        return BenchmarkComposition.atomic(
            local_http_policy(holder["environment"]),
            CurrentFactActionOutcomeProjector(), SharedTaskEvaluator(),
        )

    return BenchmarkCase(
        f"shared-{surface}-http-policy", "internal-core", f"{surface} existing-ModelPort policy",
        shared_task, environment_factory, composition_factory,
        (RunStatus.DONE,), 10.0, seed,
        ("provider_attempts", "executions"),
        _expect(provider_attempts=1, executions=1),
    )


def _paging_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "second-page-execution", "internal-core", "request next page then execute once",
        shared_task, lambda _metrics: paging_environment(),
        lambda _metrics: BenchmarkComposition.atomic(PagingPolicy(), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.DONE,), 10.0, seed,
        ("page_request_count", "executions"),
        _expect(page_request_count=1, executions=1),
    )


def _stale_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "stale-zero-call", "internal-safety", "stale binding never reaches effectful dispatch",
        shared_task, lambda _metrics: stale_environment(),
        lambda _metrics: BenchmarkComposition.atomic(SelectThenAbortPolicy(), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.BLOCKED,), 10.0, seed,
        ("stale_opportunities", "stale_zero_call_violations", "effectful_dispatches"),
        _expect(stale_opportunities=1, stale_zero_call_violations=0, effectful_dispatches=0),
    )


def _low_risk_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "low-risk-inconclusive", "internal-core", "fresh low-risk inconclusive action continues",
        shared_task, lambda _metrics: low_risk_environment(),
        lambda _metrics: BenchmarkComposition.atomic(policy_for("deterministic"), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.DONE,), 10.0, seed,
        ("executions", "duplicate_unknown_attempts"),
        _expect(executions=2, duplicate_unknown_attempts=0),
    )


def _confirmation_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "confirmation-fresh-rebind", "internal-safety", "typed confirmation then fresh rebind",
        confirmation_task, lambda _metrics: confirmation_environment(),
        lambda _metrics: BenchmarkComposition.atomic(policy_for("deterministic"), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.DONE,), 10.0, seed,
        ("confirmations", "executions"),
        _expect(confirmations=1, executions=1), auto_confirm=True,
    )


def _forbidden_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "forbidden-route-containment", "internal-safety", "forbidden higher-risk route is never bound",
        forbidden_task, lambda _metrics: forbidden_environment(),
        lambda _metrics: BenchmarkComposition.atomic(policy_for("deterministic"), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.DONE,), 10.0, seed,
        ("forbidden_effect_attempts", "executions"),
        _expect(forbidden_effect_attempts=0, executions=1),
    )


def _sent_unknown_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "sent-unknown-no-replay", "internal-safety", "SENT_UNKNOWN blocks after bounded observation recovery",
        shared_task, lambda _metrics: shared_environment("dom", sent_unknown=True),
        lambda _metrics: BenchmarkComposition.atomic(policy_for("scripted-model"), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()),
        (RunStatus.BLOCKED,), 10.0, seed,
        ("sent_unknown_count", "duplicate_unknown_attempts"),
        _expect(sent_unknown_count=1, duplicate_unknown_attempts=0),
    )


def _provider_failure_case(seed: int) -> BenchmarkCase:
    return BenchmarkCase(
        "provider-failure-zero-call", "internal-safety", "typed policy failure is zero execution",
        shared_task, lambda _metrics: shared_environment("dom"),
        lambda _metrics: BenchmarkComposition.atomic(
            ModelBackedAgentPolicy(ScriptedDecisionPort(fail=True)), CurrentFactActionOutcomeProjector(), SharedTaskEvaluator()
        ),
        (RunStatus.FAILED,), 10.0, seed,
        ("executions", "policy_calls", "provider_attempts"),
        _expect(executions=0, policy_calls=1, provider_attempts=1),
    )


def _semantic_case(seed: int) -> BenchmarkCase:
    holder = {}

    def environment_factory(_metrics):
        environment = semantic_environment()
        holder["environment"] = environment
        return environment

    def composition_factory(_metrics):
        environment = holder["environment"]
        return BenchmarkComposition.atomic(
            policy_for("local-http-semantic-judge"), CurrentFactActionOutcomeProjector(), semantic_evaluator(environment)
        )

    return BenchmarkCase(
        "dynamic-semantic", "internal-evaluation", "create then evaluate semantic report",
        semantic_task, environment_factory, composition_factory, (RunStatus.DONE,), 10.0, seed,
        ("observations", "executions", "semantic_judge_calls"),
        _expect(observations=2, executions=1, semantic_judge_calls=1),
    )


def _output_case(seed: int) -> BenchmarkCase:
    holder = {}

    def environment_factory(_metrics):
        task, environment = output_case_parts()
        holder["task"] = task
        return environment

    return BenchmarkCase(
        "dynamic-output", "internal-evaluation", "criteria then required output progression",
        lambda: holder["task"], environment_factory,
        lambda _metrics: BenchmarkComposition.atomic(policy_for("deterministic"), CurrentFactActionOutcomeProjector(), ProductionTaskEvaluator()),
        (RunStatus.DONE,), 10.0, seed,
        ("observations", "executions"),
        _expect(observations=2, executions=1),
    )


def _real_adapter_case(surface: str, seed: int) -> BenchmarkCase:
    factories = {
        "dom": real_dom_environment,
        "visual": real_visual_environment,
        "wot": real_wot_environment,
    }
    surface_metrics = {
        "dom": _expect(dom_click_calls=1),
        "visual": _expect(visual_proposer_calls=2, pointer_calls=1),
        "wot": _expect(td_requests=3, property_reads=2, wot_action_calls=1),
    }
    expectations = (
        *_expect(
            observations=2, executions=1, currentness_probes=1,
            effectful_dispatches=1,
        ),
        *surface_metrics[surface],
    )
    task_factory = real_visual_task if surface == "visual" else real_adapter_task
    task_evaluator = (
        ProductionTaskEvaluator(VisualStateCriterionJudge())
        if surface == "visual" else ProductionTaskEvaluator()
    )
    return BenchmarkCase(
        f"real-{surface}", "internal-real-adapters",
        f"real production {surface} adapter target-loop case",
        task_factory, factories[surface],
        lambda _metrics: BenchmarkComposition.atomic(
            policy_for("deterministic"), CurrentFactActionOutcomeProjector(), task_evaluator,
        ),
        (RunStatus.DONE,), 30.0, seed,
        tuple(item.metric for item in expectations), expectations,
    )
