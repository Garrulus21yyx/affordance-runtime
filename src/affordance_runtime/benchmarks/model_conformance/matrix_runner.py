"""One-attempt-per-cell live runner for the compact decision behavior matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.model_boundary.failures import ModelFailure
from affordance_runtime.model_policy.contracts import ModelDecisionRequest
from affordance_runtime.model_policy.grounding import DecisionGroundingVariant
from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS
from affordance_runtime.model_policy.spec import SCHEMA_VERSION, decision_response_schema
from affordance_runtime.model_port import ModelConfig, ModelPort, OllamaModelPort

from .contracts import ModelProfileIdentity
from .decision_matrix import (
    DecisionMatrixCase,
    build_destination_case,
    build_multi_action_case,
    build_seven_decision_cases,
)
from .profile_identity import identity_from_ollama_inventory, ollama_inventory
from .scenario import build_live_dom_scenario


@dataclass(frozen=True)
class DecisionMatrixAttempt:
    case_id: str
    expected_variant: str
    actual_variant: str
    success: bool
    failure_stage: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    selected_first_action: bool
    provider_attempts: int


@dataclass(frozen=True)
class DecisionMatrixResult:
    schema_version: str
    identity: ModelProfileIdentity
    repetitions: int
    attempts: tuple[DecisionMatrixAttempt, ...]
    success_count: int
    first_action_selection_count: int
    nonfirst_case_first_action_count: int
    nonfirst_case_count: int
    retry_count: int
    fallback_count: int


async def run_decision_matrix(
    identity: ModelProfileIdentity,
    port_factory,
    *,
    repetitions: int,
    output_dir: Path,
) -> DecisionMatrixResult:
    if not 1 <= repetitions <= 5:
        raise ValueError("decision matrix repetitions must be in [1, 5]")
    scenario = await build_live_dom_scenario()
    cases = (
        *build_seven_decision_cases(scenario.serialized_context),
        build_multi_action_case(scenario.serialized_context, action_count=8, correct_index=7),
        build_multi_action_case(scenario.serialized_context, action_count=16, correct_index=7),
        build_multi_action_case(scenario.serialized_context, action_count=8, correct_index=4),
        build_destination_case(scenario.serialized_context, destinations=0),
        build_destination_case(scenario.serialized_context, destinations=1),
        build_destination_case(scenario.serialized_context, destinations=2, correct_index=1),
        build_destination_case(
            scenario.serialized_context, destinations=2, correct_index=1, similar_ids=True,
        ),
    )
    attempts = []
    for case in cases:
        for _ in range(repetitions):
            attempts.append(await _attempt(case, port_factory()))
    result = DecisionMatrixResult(
        "compact-decision-matrix.v1",
        identity,
        repetitions,
        tuple(attempts),
        sum(item.success for item in attempts),
        sum(item.selected_first_action for item in attempts),
        sum(
            item.selected_first_action
            for case, item in _case_attempt_pairs(cases, attempts, repetitions)
            if case.correct_action_index not in {None, 0}
        ),
        sum(
            1
            for case, _ in _case_attempt_pairs(cases, attempts, repetitions)
            if case.correct_action_index not in {None, 0}
        ),
        0,
        0,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "matrix.json").write_text(
        json.dumps(asdict(result), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


async def _attempt(case: DecisionMatrixCase, port: ModelPort) -> DecisionMatrixAttempt:
    adapter = ModelPortDecisionAdapter(
        port,
        ModelConfig(
            timeout_s=89,
            rate_limit_retries=0,
            transient_retries=0,
            prompt_version="p5-m1.1",
        ),
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT,
    )
    request = ModelDecisionRequest(
        f"matrix:{case.case_id}",
        case.serialized_context,
        SCHEMA_VERSION,
        MODEL_POLICY_INSTRUCTIONS,
        decision_response_schema(),
    )
    outcome = await adapter.generate(request)
    record = port.last_call
    if isinstance(outcome, ModelFailure):
        return _result(case, "", False, outcome.kind.value, record)
    decision = parse_agent_decision(
        outcome.raw_payload,
        json.loads(case.serialized_context)["context_id"],
    )
    if isinstance(decision, ModelFailure | PolicyFailure):
        return _result(case, "", False, "parser", record)
    actual = _variant(decision)
    success = actual == case.expected_variant and _matches_oracle(decision, case)
    stage = "" if success else "wrong_decision_or_domain"
    return _result(case, actual, success, stage, record, decision=decision)


def _result(case, actual, success, stage, record, *, decision=None) -> DecisionMatrixAttempt:
    first = False
    if decision is not None and hasattr(decision, "action_id"):
        options = json.loads(case.serialized_context)["actions"]["options"]
        first = bool(options) and decision.action_id == options[0]["action_id"]
    return DecisionMatrixAttempt(
        case.case_id,
        case.expected_variant,
        actual,
        success,
        stage,
        record.prompt_tokens if record else 0,
        record.completion_tokens if record else 0,
        record.latency_ms if record else 0.0,
        first,
        1,
    )


def _matches_oracle(decision, case: DecisionMatrixCase) -> bool:
    expected = case.expected_payload
    if case.expected_variant == "select_action":
        return (
            decision.action_id == expected["action_id"]
            and decision.destination_id == expected["destination_id"]
        )
    return True


def _variant(decision) -> str:
    names = {
        "SelectAction": "select_action",
        "RequestObservation": "request_observation",
        "RequestActionPage": "request_action_page",
        "AskUser": "ask_user",
        "ProposeDone": "propose_done",
        "Wait": "wait",
        "Abort": "abort",
    }
    return names.get(type(decision).__name__, "")


def _case_attempt_pairs(cases, attempts, repetitions):
    return tuple(
        (case, attempts[index * repetitions + offset])
        for index, case in enumerate(cases)
        for offset in range(repetitions)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--execution-profile", default="")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    version, models = ollama_inventory(args.ollama_base_url)
    identity = identity_from_ollama_inventory(
        args.model,
        runtime_version=version,
        models=models,
        grounding_variant="compact-contract",
        execution_profile=args.execution_profile,
    )
    asyncio.run(run_decision_matrix(
        identity,
        lambda: OllamaModelPort(model=args.model, base_url=args.ollama_base_url),
        repetitions=args.repetitions,
        output_dir=Path(args.output_dir),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
