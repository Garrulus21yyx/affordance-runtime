"""Opt-in exact-profile live model-policy attestation on one safe real DOM task."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.external_smoke.pacing import PacedAgentPolicy
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCase,
    BenchmarkComposition,
    BenchmarkManifest,
    MetricExpectation,
    MetricExpectationOperator,
)
from affordance_runtime.benchmarks.target_loop.real_adapter_support import (
    real_adapter_task,
    real_dom_environment,
)
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.benchmarks.target_loop.support import CurrentFactActionEvaluator
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.model.policy import ModelBackedAgentPolicy, model_policy_from_environment
from affordance_runtime.model.policy.contracts import ModelMetadata
from affordance_runtime.model.policy.spec import SCHEMA_VERSION

LIVE_ATTESTATION_SCHEMA_VERSION = "target-loop-live-model-policy.v1"


class LiveModelPolicyStatus(StrEnum):
    ATTESTED = "attested"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class LiveModelPolicyAttestation:
    attestation_schema_version: str
    git_sha: str
    git_dirty: bool
    status: LiveModelPolicyStatus
    provider_id: str = ""
    model_id: str = ""
    endpoint_class: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    task_profile: str = "internal-real-dom-mechanical-v1"
    grounding_profile: str = "format-only.v1"
    minimum_policy_call_interval_s: float = 7.5
    terminal_status: str = ""
    observations: int = 0
    executions: int = 0
    policy_calls: int = 0
    provider_attempts: int = 0
    forbidden_effect_attempts: int = 0
    duplicate_unknown_attempts: int = 0
    stale_zero_call_violations: int = 0
    rate_limit_retry_count: int = 0
    transient_retry_count: int = 0
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    accepted: bool = False
    acceptance_errors: tuple[str, ...] = ()


async def run_live_model_policy_attestation(
    output: Path,
    *,
    environment: Mapping[str, str] | None = None,
    policy_factory: Callable[[Mapping[str, str]], ModelBackedAgentPolicy] = model_policy_from_environment,
    grounding: str = "format-only",
    minimum_policy_call_interval_s: float = 7.5,
    expected_model_id: str = "",
) -> LiveModelPolicyAttestation:
    env = dict(os.environ if environment is None else environment)
    env["LLM_DECISION_GROUNDING"] = grounding
    sha = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--short"))
    if env.get("RUN_LIVE_MODEL_POLICY_ATTESTATION") != "1":
        return _write(output, LiveModelPolicyAttestation(
            LIVE_ATTESTATION_SCHEMA_VERSION, sha, dirty, LiveModelPolicyStatus.UNAVAILABLE,
            acceptance_errors=("live model policy attestation was not enabled",),
        ))
    if dirty:
        return _write(output, LiveModelPolicyAttestation(
            LIVE_ATTESTATION_SCHEMA_VERSION, sha, dirty, LiveModelPolicyStatus.FAILED,
            acceptance_errors=("live model policy attestation requires a clean exact tree",),
        ))
    try:
        model_policy = policy_factory(env)
    except Exception as exc:
        return _failed(output, sha, f"model policy construction failed: {type(exc).__name__}")
    policy = PacedAgentPolicy(model_policy, minimum_policy_call_interval_s)
    holder: dict[str, object] = {"configured_metadata": _configured_metadata(model_policy)}

    def environment_factory(instrumentation):
        holder["instrumentation"] = instrumentation
        return real_dom_environment(instrumentation)

    case = BenchmarkCase(
        "live-real-dom-policy", "live-internal-policy",
        "live existing-ModelPort policy on the safe internal real DOM task",
        real_adapter_task, environment_factory,
        lambda _metrics: BenchmarkComposition(
            policy, CurrentFactActionEvaluator(), ProductionTaskEvaluator(),
        ),
        (AgentLoopStatus.DONE,), 120.0, 7,
        ("observations", "executions", "policy_calls", "provider_attempts"),
        tuple(
            MetricExpectation(name, MetricExpectationOperator.EQ, value)
            for name, value in {
                "observations": 2, "executions": 1, "policy_calls": 1,
                "provider_attempts": 1,
            }.items()
        ),
    )
    try:
        result = await run_suite(BenchmarkManifest(
            "target-loop-manifest.v1", "live-internal-policy", "live-model-policy", 7, (case,),
        ))
    except Exception as exc:
        return _failed(output, sha, f"live target-loop run failed: {type(exc).__name__}")
    return _write(output, evaluate_live_policy_suite(
        sha, result, holder.get("instrumentation"),
        live_origin=policy_factory is model_policy_from_environment,
        configured_metadata=holder["configured_metadata"],
        grounding_profile=f"{grounding}.v1",
        minimum_policy_call_interval_s=minimum_policy_call_interval_s,
        expected_model_id=expected_model_id,
    ))


def evaluate_live_policy_suite(
    sha: str,
    suite,
    instrumentation,
    *,
    live_origin: bool,
    configured_metadata: object = None,
    grounding_profile: str = "format-only.v1",
    minimum_policy_call_interval_s: float = 7.5,
    expected_model_id: str = "",
) -> LiveModelPolicyAttestation:
    case = suite.cases[0]
    metric = lambda name: int(case.measurements[name].value or 0)  # noqa: E731
    metadata = getattr(instrumentation, "model_metadata", None) or configured_metadata
    errors = list(suite.acceptance.acceptance_errors)
    if not live_origin:
        errors.append("injected policy evidence is test-only and cannot attest a live profile")
    if metadata is None:
        errors.append("live provider call did not produce model metadata")
    if grounding_profile != "format-only.v1":
        errors.append("live external admission requires format-only.v1")
    if minimum_policy_call_interval_s != 7.5:
        errors.append("live external admission requires fixed 7.5-second pacing")
    if expected_model_id and getattr(metadata, "model_id", "") != expected_model_id:
        errors.append("live policy model identity does not match the fixed profile")
    if metric("provider_attempts") != metric("policy_calls"):
        errors.append("provider attempts must equal policy calls")
    if any(metric(name) for name in (
        "forbidden_effect_attempts", "duplicate_unknown_attempts", "stale_zero_call_violations",
    )):
        errors.append("live policy run violated a safety metric")
    retries = (
        getattr(metadata, "rate_limit_retry_count", 0),
        getattr(metadata, "transient_retry_count", 0),
    )
    if any(retries):
        errors.append("live policy profile used a provider retry")
    accepted = not errors and case.status == str(AgentLoopStatus.DONE)
    return LiveModelPolicyAttestation(
        LIVE_ATTESTATION_SCHEMA_VERSION, sha, False,
        LiveModelPolicyStatus.ATTESTED if accepted else LiveModelPolicyStatus.FAILED,
        provider_id=getattr(metadata, "provider_id", ""),
        model_id=getattr(metadata, "model_id", ""),
        endpoint_class=getattr(metadata, "endpoint_class", ""),
        prompt_version=getattr(metadata, "prompt_version", ""),
        schema_version=getattr(metadata, "schema_version", ""),
        grounding_profile=grounding_profile,
        minimum_policy_call_interval_s=minimum_policy_call_interval_s,
        terminal_status=case.status,
        observations=metric("observations"), executions=metric("executions"),
        policy_calls=metric("policy_calls"), provider_attempts=metric("provider_attempts"),
        forbidden_effect_attempts=metric("forbidden_effect_attempts"),
        duplicate_unknown_attempts=metric("duplicate_unknown_attempts"),
        stale_zero_call_violations=metric("stale_zero_call_violations"),
        rate_limit_retry_count=retries[0], transient_retry_count=retries[1],
        latency_ms=getattr(metadata, "latency_ms", 0.0),
        prompt_tokens=getattr(metadata, "prompt_tokens", 0),
        completion_tokens=getattr(metadata, "completion_tokens", 0),
        total_tokens=getattr(metadata, "total_tokens", 0),
        accepted=accepted, acceptance_errors=tuple(errors),
    )


def _configured_metadata(policy: ModelBackedAgentPolicy) -> ModelMetadata:
    adapter = policy.port
    transport = getattr(adapter, "port", None)
    config = getattr(adapter, "config", None)
    try:
        return ModelMetadata(
            provider_id=str(getattr(transport, "provider", "")),
            model_id=str(getattr(transport, "model", "")),
            endpoint_class=str(getattr(transport, "endpoint_class", "")),
            prompt_version=str(getattr(config, "prompt_version", "")),
            schema_version=SCHEMA_VERSION,
            grounding_variant=str(getattr(adapter, "grounding_variant", "")),
            grounding_profile_version=str(getattr(adapter, "grounding_profile_version", "")),
        )
    except ValueError:
        return ModelMetadata(schema_version=SCHEMA_VERSION)


def _failed(output: Path, sha: str, reason: str) -> LiveModelPolicyAttestation:
    return _write(output, LiveModelPolicyAttestation(
        LIVE_ATTESTATION_SCHEMA_VERSION, sha, False, LiveModelPolicyStatus.FAILED,
        acceptance_errors=(reason,),
    ))


def _write(output: Path, result: LiveModelPolicyAttestation) -> LiveModelPolicyAttestation:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(result), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def _git(*args: str) -> str:
    result = subprocess.run(("git", *args), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("mistral-format-only",), default="mistral-format-only")
    parser.add_argument("--grounding", choices=("format-only",), default="format-only")
    parser.add_argument("--min-policy-call-interval-s", type=float, default=7.5)
    parser.add_argument("--output")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    import asyncio

    if not args.output and not args.output_dir:
        parser.error("--output or --output-dir is required")
    output = Path(args.output) if args.output else Path(args.output_dir) / "live-policy-attestation.json"
    result = asyncio.run(run_live_model_policy_attestation(
        output,
        grounding=args.grounding,
        minimum_policy_call_interval_s=args.min_policy_call_interval_s,
        expected_model_id="mistral-medium-3-5",
    ))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
