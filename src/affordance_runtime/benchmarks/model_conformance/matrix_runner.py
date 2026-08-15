"""One-attempt-per-cell live runner for the compact decision behavior matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from affordance_runtime.model.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounding import DecisionGroundingVariant
from affordance_runtime.model.policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model.policy.prompt import MODEL_POLICY_INSTRUCTIONS
from affordance_runtime.model.policy.spec import SCHEMA_VERSION, decision_response_schema
from affordance_runtime.model.providers.port import ModelConfig, ModelPort, OllamaModelPort

from .contracts import ModelProfileIdentity
from .critical_cases import build_cross_action_destination_case, build_nonfirst_direct_case
from .decision_matrix import (
    DecisionMatrixCase,
    build_destination_case,
    build_multi_action_case,
    build_seven_decision_cases,
    decision_matches_expectation,
)
from .matrix_progress import write_json_report, write_matrix_progress
from .profile_identity import identity_from_ollama_inventory, ollama_inventory
from .runtime_decision_matrix import (
    ReplayedRuntimeOutcome,
    RuntimeDecisionOutcome,
    replay_runtime_decision,
    run_scripted_runtime_decision_matrix,
    runtime_outcome_matches,
)
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
    runtime_status: str = ""
    execution_count: int = 0
    observation_count: int = 0
    guide_schema_version: str = ""
    guide_digest: str = ""


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
    runtime_control_outcomes: tuple[RuntimeDecisionOutcome, ...]
    runtime_control_success_count: int


async def run_decision_matrix(
    identity: ModelProfileIdentity,
    port_factory,
    *,
    repetitions: int,
    output_dir: Path,
    grounding_variant: DecisionGroundingVariant = DecisionGroundingVariant.COMPACT_CONTRACT,
    case_ids: tuple[str, ...] = (),
    cases_override: tuple[DecisionMatrixCase, ...] = (),
) -> DecisionMatrixResult:
    if not 1 <= repetitions <= 20:
        raise ValueError("decision matrix repetitions must be in [1, 20]")
    scenario = await build_live_dom_scenario()
    cases = cases_override or (
        *build_seven_decision_cases(scenario.serialized_context),
        build_multi_action_case(scenario.serialized_context, action_count=8, correct_index=7),
        build_multi_action_case(scenario.serialized_context, action_count=16, correct_index=7),
        build_nonfirst_direct_case(scenario.serialized_context),
        build_destination_case(scenario.serialized_context, destinations=0),
        build_destination_case(scenario.serialized_context, destinations=1),
        build_destination_case(scenario.serialized_context, destinations=2, correct_index=1),
        build_destination_case(
            scenario.serialized_context, destinations=2, correct_index=1, similar_ids=True,
        ),
        build_cross_action_destination_case(scenario.serialized_context),
    )
    if cases_override and case_ids:
        raise ValueError("decision matrix cannot combine explicit cases with case IDs")
    if case_ids:
        cases = tuple(case for case in cases if case.case_id in case_ids)
        if {case.case_id for case in cases} != set(case_ids):
            raise ValueError("decision matrix case selection contains an unknown case")
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "matrix-progress.json"
    planned_attempt_count = len(cases) * repetitions
    attempts: list[DecisionMatrixAttempt] = []
    write_matrix_progress(
        progress_path, identity=identity, repetitions=repetitions,
        planned_attempt_count=planned_attempt_count, attempts=attempts, complete=False,
    )
    for case in cases:
        for _ in range(repetitions):
            attempts.append(await _attempt(case, port_factory(), grounding_variant))
            write_matrix_progress(
                progress_path, identity=identity, repetitions=repetitions,
                planned_attempt_count=planned_attempt_count, attempts=attempts, complete=False,
            )
    runtime_outcomes = await run_scripted_runtime_decision_matrix()
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
        runtime_outcomes,
        sum(runtime_outcome_matches(item) for item in runtime_outcomes),
    )
    write_json_report(output_dir / "matrix.json", asdict(result))
    write_matrix_progress(
        progress_path, identity=identity, repetitions=repetitions,
        planned_attempt_count=planned_attempt_count, attempts=attempts, complete=True,
    )
    return result


async def _attempt(
    case: DecisionMatrixCase,
    port: ModelPort,
    grounding_variant: DecisionGroundingVariant,
) -> DecisionMatrixAttempt:
    adapter = ModelPortDecisionAdapter(
        port,
        ModelConfig(
            timeout_s=89,
            rate_limit_retries=0,
            transient_retries=0,
            prompt_version="p5-m1.1",
        ),
        grounding_variant=grounding_variant,
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
        return _result(case, "", False, _provider_failure(outcome.kind), record)
    decision = outcome.decision
    actual = _variant(decision)
    guide_identity = (
        outcome.metadata.grounding_guide_schema_version,
        outcome.metadata.grounding_guide_digest,
    )
    if actual != case.expected_variant:
        return _result(
            case, actual, False, "wrong_variant", record, decision=decision,
            guide_identity=guide_identity,
        )
    success = decision_matches_expectation(decision, case.expectation)
    if not success:
        return _result(
            case, actual, False, "wrong_field_domain", record, decision=decision,
            guide_identity=guide_identity,
        )
    replay = await replay_runtime_decision(case, decision)
    if not replay.success:
        stage = "runtime_rejected" if replay.status == "blocked" else "runtime_outcome_mismatch"
        return _result(
            case, actual, False, stage, record, decision=decision, replay=replay,
            guide_identity=guide_identity,
        )
    return _result(
        case, actual, True, "", record, decision=decision, replay=replay,
        guide_identity=guide_identity,
    )


def _result(
    case, actual, success, stage, record, *, decision=None,
    replay: ReplayedRuntimeOutcome | None = None,
    guide_identity: tuple[str, str] = ("", ""),
) -> DecisionMatrixAttempt:
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
        replay.status if replay else "",
        replay.execution_count if replay else 0,
        replay.observation_count if replay else 0,
        guide_identity[0],
        guide_identity[1],
    )


def _matches_oracle(decision, case: DecisionMatrixCase) -> bool:
    return decision_matches_expectation(decision, case.expectation)


def _provider_failure(kind: ModelFailureKind) -> str:
    if kind is ModelFailureKind.PROVIDER_UNAVAILABLE:
        return "provider_unavailable"
    if kind is ModelFailureKind.TIMEOUT:
        return "timeout"
    if kind in {ModelFailureKind.SCHEMA_ERROR, ModelFailureKind.INVALID_RESPONSE}:
        return "structured_output"
    return "schema_error"


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
    parser.add_argument(
        "--grounding",
        choices=tuple(item.value for item in DecisionGroundingVariant),
        default=DecisionGroundingVariant.COMPACT_CONTRACT.value,
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    version, models = ollama_inventory(args.ollama_base_url)
    identity = identity_from_ollama_inventory(
        args.model,
        runtime_version=version,
        models=models,
        grounding_variant=args.grounding,
        execution_profile=args.execution_profile,
    )
    asyncio.run(run_decision_matrix(
        identity,
        lambda: OllamaModelPort(model=args.model, base_url=args.ollama_base_url),
        repetitions=args.repetitions,
        output_dir=Path(args.output_dir),
        grounding_variant=DecisionGroundingVariant(args.grounding),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
