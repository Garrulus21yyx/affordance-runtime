"""Explicit one-shot CLI for the target natural-language Runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from affordance_runtime.browser_thread_session import ThreadBoundBrowserSession
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.target_composition import compose_target_client_from_environment
from affordance_runtime.target_runtime_client import TargetRuntimeClient, TargetRuntimeRunOutcome
from affordance_runtime.task import (
    EvaluationSpec,
    LoopBudget,
    MaterialBinding,
    NaturalLanguageTaskRequest,
    ReadyTask,
    RiskProfile,
    TaskBoundary,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

_BOUNDARY_FIELDS = frozenset({
    "constraints",
    "allowed_effects",
    "forbidden_effects",
    "inputs",
    "success_criteria",
    "requested_outputs",
    "risk_profile",
    "material_bindings",
    "loop_budget",
    "evaluation_spec",
})


def add_target_run_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "target-run",
        help="run one natural-language task through the target Runtime",
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--request-id", default="task:cli")
    parser.add_argument(
        "--boundary",
        type=Path,
        required=True,
        help="JSON stable task boundary; must include success criteria or requested outputs",
    )
    parser.add_argument("--headed", action="store_true")


def run_target_command(args: argparse.Namespace) -> dict[str, object]:
    request = load_target_request(args.request_id, args.instruction, args.boundary)
    return run_target_request(
        args.target,
        request,
        headless=not args.headed,
    )


def load_target_request(
    request_id: str,
    instruction: str,
    boundary_path: Path,
) -> NaturalLanguageTaskRequest:
    payload = json.loads(boundary_path.read_text(encoding="utf-8"))
    boundary = task_boundary_from_mapping(payload)
    if not boundary.success_criteria and not boundary.requested_outputs:
        raise ValueError(
            "target CLI boundary requires success_criteria or requested_outputs"
        )
    return NaturalLanguageTaskRequest(
        request_id,
        instruction,
        boundary,
        source_ref=f"cli-boundary:{boundary_path.name}",
    )


def task_boundary_from_mapping(payload: object) -> TaskBoundary:
    if not isinstance(payload, Mapping):
        raise TypeError("target task boundary must be a JSON object")
    unknown = set(payload) - _BOUNDARY_FIELDS
    if unknown:
        raise ValueError(f"target task boundary has unsupported fields: {sorted(unknown)}")
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise TypeError("target task boundary inputs must be an object")
    return TaskBoundary(
        constraints=_string_sequence(payload.get("constraints", ()), "constraints"),
        allowed_effects=_string_sequence(
            payload.get("allowed_effects", ()),
            "allowed_effects",
        ),
        forbidden_effects=_string_sequence(
            payload.get("forbidden_effects", ()),
            "forbidden_effects",
        ),
        inputs=dict(inputs),
        success_criteria=_mapping_sequence(
            payload.get("success_criteria", ()),
            "success_criteria",
        ),
        requested_outputs=_string_sequence(
            payload.get("requested_outputs", ()),
            "requested_outputs",
        ),
        risk_profile=RiskProfile(str(payload.get("risk_profile", RiskProfile.READ_ONLY))),
        material_bindings=_material_bindings(payload.get("material_bindings", ())),
        loop_budget=_loop_budget(payload.get("loop_budget")),
        evaluation_spec=_evaluation_spec(payload.get("evaluation_spec")),
    )


def run_target_request(
    target: str,
    request: NaturalLanguageTaskRequest,
    *,
    headless: bool = True,
    client: TargetRuntimeClient | None = None,
    session_factory=ThreadBoundBrowserSession.launch,
) -> dict[str, object]:
    target_client = client or compose_target_client_from_environment()
    admitted = target_client.admit(request)
    if not isinstance(admitted, ReadyTask):
        return target_run_payload(TargetRuntimeRunOutcome(admitted))
    with session_factory(target, headless=headless) as session:
        world = UnifiedWorldEnvironment((DomSurfaceAdapter(session),))
        outcome = asyncio.run(target_client.run_admitted(world, admitted))
    return target_run_payload(outcome)


def target_run_payload(outcome: TargetRuntimeRunOutcome) -> dict[str, object]:
    result = outcome.result
    return {
        "request_id": outcome.intake.request_id,
        "intake_status": outcome.intake.status.value,
        "started": outcome.started,
        "status": result.status.value if result is not None else outcome.intake.status.value,
        "reason_code": result.reason_code if result is not None else getattr(
            outcome.intake,
            "reason_code",
            "",
        ),
        "message": result.message if result is not None else getattr(
            outcome.intake,
            "question",
            "",
        ),
        "observation_count": result.observation_count if result is not None else 0,
        "execution_count": result.execution_count if result is not None else 0,
        "task_revision": result.task.revision if result is not None else 0,
        "user_input_request": to_json_compatible(
            result.user_input_request if result is not None else None
        ),
        "confirmation_request": to_json_compatible(
            result.confirmation_request if result is not None else None
        ),
        "task_outcome": to_json_compatible(
            result.task_outcome if result is not None else None
        ),
    }


def _string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError(f"target task boundary {field_name} must be a string array")
    if any(not isinstance(item, str) for item in value):
        raise TypeError(f"target task boundary {field_name} must be a string array")
    return tuple(value)


def _mapping_sequence(value: object, field_name: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError(f"target task boundary {field_name} must be an object array")
    if any(not isinstance(item, Mapping) for item in value):
        raise TypeError(f"target task boundary {field_name} must be an object array")
    return tuple(dict(item) for item in value)


def _loop_budget(value: object) -> LoopBudget:
    if value is None:
        return LoopBudget()
    if not isinstance(value, Mapping) or set(value) - {"max_turns", "max_observations"}:
        raise ValueError("target task loop_budget is unsupported")
    return LoopBudget(**dict(value))


def _material_bindings(value: object) -> tuple[MaterialBinding, ...]:
    items = _mapping_sequence(value, "material_bindings")
    allowed = {"name", "digest", "media_type", "public_reference"}
    if any(set(item) - allowed for item in items):
        raise ValueError("target task material binding is unsupported")
    return tuple(MaterialBinding(**dict(item)) for item in items)


def _evaluation_spec(value: object) -> EvaluationSpec | None:
    if value is None:
        return None
    allowed = {
        "success_expression",
        "required_output_integrity",
        "authoritative_checks",
        "strict_source_lineage",
    }
    if not isinstance(value, Mapping) or set(value) - allowed:
        raise ValueError("target task evaluation_spec is unsupported")
    authoritative = _string_sequence(
        value.get("authoritative_checks", ()),
        "evaluation_spec.authoritative_checks",
    )
    strict = value.get("strict_source_lineage", False)
    if not isinstance(strict, bool):
        raise TypeError("target task strict_source_lineage must be boolean")
    return EvaluationSpec(
        success_expression=dict(value.get("success_expression", {})),
        required_output_integrity=dict(value.get("required_output_integrity", {})),
        authoritative_checks=authoritative,
        strict_source_lineage=strict,
    )
