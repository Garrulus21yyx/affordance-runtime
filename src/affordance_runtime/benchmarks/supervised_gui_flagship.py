"""Live controlled shopping flagship over the unchanged product Runtime."""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from dotenv import load_dotenv

from affordance_runtime.agent.decision_capability import GROUNDED_ACTION_DECISION_CAPABILITIES
from affordance_runtime.agent.interactions import SingleSelectionResponse
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.app.composition import compose_target_runtime
from affordance_runtime.app.interactive_environment import (
    InteractiveTaskEnvironment,
    InteractiveTaskEvaluator,
)
from affordance_runtime.app.public_session import (
    PublicRuntimeSessionSnapshot,
    PublicSessionStatus,
    RuntimeEnvironmentLease,
    TargetRuntimeSession,
)
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy import model_roles_from_environment
from affordance_runtime.surfaces.browser_bundle import (
    BrowserSessionSurfaceBundle,
    browser_surface_from_environment,
)
from affordance_runtime.surfaces.dom.thread_session import ThreadBoundBrowserSession
from affordance_runtime.task import LoopBudget, NaturalLanguageTaskRequest, RiskProfile, TaskBoundary
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

DEFAULT_FIXTURE = Path("docs/benchmarks/fixtures/supervised-gui/candidate-comparison.html")
DEFAULT_CHOICE = "Field jacket"
FLAGSHIP_TASK = """Compare all three visible jacket candidates. Their colors are available only visually: before any
GUI action, use one batched visual-property request over the three current candidate controls to determine whether
each appears blue. Then present all three candidates to me in one single-select interaction, including title, price,
size, checked color, evidence, and any uncertainty. Do not choose or click for me. After I select an option, activate
that candidate's corresponding Choose control. Confirm the fresh page says it is selected, then submit a concise final
answer with a generic PublicArtifact summarizing the selected candidate and its attributes."""


class _QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def _served_fixture(fixture: Path):
    resolved = fixture.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    handler = functools.partial(_QuietFixtureHandler, directory=str(resolved.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="shopping-flagship-fixture", daemon=True)
    thread.start()
    try:
        port = int(server.server_address[1])
        yield f"http://127.0.0.1:{port}/{resolved.name}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("shopping flagship fixture server did not stop")


def flagship_profile_errors(environment: Mapping[str, str]) -> tuple[str, ...]:
    expected = {
        "LLM_ACTIVE_PROFILE": "deepseek",
        "LLM_VISUAL_PROFILE": "deepseek",
        "LLM_DEEPSEEK_VISION_MODEL": "deepseek-v4-flash-vision-exp",
        "LLM_OBSERVATION_TOOL_PROFILE": "dynamic-visual.v1",
        "LLM_INTERACTION_TOOL_PROFILE": "structured-interaction.v1",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    }
    return tuple(
        f"{name} must equal {value}"
        for name, value in expected.items()
        if environment.get(name, "").strip().casefold() != value
    )


def _request_factory(session_id: str, instruction: str) -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        session_id,
        instruction,
        TaskBoundary(
            constraints=("Do not act before the user's explicit option selection.",),
            allowed_effects=("external_ui_interaction",),
            forbidden_effects=("external_network_side_effect", "credential_use"),
            requested_outputs=("selected_candidate_summary",),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(max_turns=20, max_observations=40),
        ),
        source_ref="benchmark:controlled-shopping-flagship",
    )


async def _wait_until_not_running(
    session: TargetRuntimeSession,
    *,
    deadline_s: float,
) -> PublicRuntimeSessionSnapshot:
    while True:
        snapshot = await session.snapshot()
        if snapshot.status is not PublicSessionStatus.RUNNING:
            return snapshot
        if time.monotonic() >= deadline_s:
            raise TimeoutError("shopping flagship session deadline exceeded")
        await asyncio.sleep(0.2)


def _matching_option(snapshot: PublicRuntimeSessionSnapshot, choice_title: str):
    request = snapshot.pending_interaction
    if request is None:
        return None
    wanted = choice_title.strip().casefold()
    exact = tuple(item for item in request.options if item.title.strip().casefold() == wanted)
    if len(exact) == 1:
        return exact[0]
    partial = tuple(item for item in request.options if wanted in item.title.strip().casefold())
    return partial[0] if len(partial) == 1 else None


def _provider_usage(events: Sequence[Mapping[str, object]]) -> dict[str, int | float]:
    attempts: list[Mapping[str, object]] = []
    for event in events:
        raw_attempts = event.get("generation_attempts")
        if event.get("event") == "model_turn" and isinstance(raw_attempts, list | tuple):
            attempts.extend(item for item in raw_attempts if isinstance(item, Mapping))
    def number(item: Mapping[str, object], key: str) -> int | float:
        value = item.get(key)
        return value if isinstance(value, int | float) and not isinstance(value, bool) else 0

    return {
        "action_policy_turns": sum(event.get("event") == "model_turn" for event in events),
        "provider_attempts": len(attempts),
        "prompt_tokens": int(sum(number(item, "prompt_tokens") for item in attempts)),
        "completion_tokens": int(sum(number(item, "completion_tokens") for item in attempts)),
        "total_tokens": int(sum(number(item, "total_tokens") for item in attempts)),
        "latency_ms": round(sum(number(item, "latency_ms") for item in attempts), 3),
    }


def _trace_segments(
    events: Sequence[Mapping[str, object]],
    *,
    choice_title: str,
) -> dict[str, object]:
    steps = tuple(event for event in events if event.get("event") == "step_completed")
    turns = tuple(event for event in events if event.get("event") == "model_turn")
    visual_steps = []
    for event in steps:
        result = event.get("result")
        decision = result.get("decision") if isinstance(result, Mapping) else None
        if (
            isinstance(result, Mapping)
            and isinstance(decision, Mapping)
            and decision.get("purpose") == "visual_property"
        ):
            subjects = decision.get("subject_ids")
            visual_steps.append({
                "step": event.get("step"),
                "query_id": decision.get("query_id", ""),
                "subject_count": len(subjects) if isinstance(subjects, list | tuple) else 0,
                "predicate": decision.get("predicate", ""),
                "outcome": result.get("observation_outcome"),
            })

    def scope_label(event: Mapping[str, object]) -> str:
        grounding = event.get("selected_grounding")
        source = grounding.get("source") if isinstance(grounding, Mapping) else None
        state = source.get("state") if isinstance(source, Mapping) else None
        return str(state.get("semantic_scope_label", "")) if isinstance(state, Mapping) else ""

    action_turn = next(
        (
            event
            for event in turns
            if scope_label(event).strip().casefold() == choice_title.strip().casefold()
        ),
        None,
    )
    action_id = ""
    action_decision = action_turn.get("decision") if isinstance(action_turn, Mapping) else None
    if isinstance(action_decision, Mapping):
        action_id = str(action_decision.get("action_id", ""))

    def step_action_id(event: Mapping[str, object]) -> str:
        result = event.get("result")
        decision = result.get("decision") if isinstance(result, Mapping) else None
        return str(decision.get("action_id", "")) if isinstance(decision, Mapping) else ""

    action_step = next(
        (
            event
            for event in steps
            if action_id and step_action_id(event) == action_id
        ),
        None,
    )
    dispatches: list[str] = []
    action_result = action_step.get("result") if isinstance(action_step, Mapping) else None
    if isinstance(action_result, Mapping):
        receipts = action_result.get("execution_receipts")
        if isinstance(receipts, Mapping):
            raw_receipts = receipts.get("receipts")
            for receipt in raw_receipts if isinstance(raw_receipts, list | tuple) else ():
                receipt_result = receipt.get("result") if isinstance(receipt, Mapping) else None
                if isinstance(receipt_result, Mapping):
                    dispatches.append(str(receipt_result.get("dispatch_status", "")))
    screenshot_lineage: list[dict[str, object]] = []
    for event in events:
        observation = event.get("observation")
        if event.get("event") != "observation" or not isinstance(observation, Mapping):
            continue
        raw_media = observation.get("media")
        for source in raw_media if isinstance(raw_media, list | tuple) else ():
            media = source.get("media") if isinstance(source, Mapping) else None
            if isinstance(media, Mapping) and media.get("kind") == "screenshot":
                screenshot_lineage.append({
                    "sha256": media.get("sha256", ""),
                    "capture_group_id": media.get("capture_group_id", ""),
                    "dimensions": media.get("dimensions", ()),
                })
    return {
        "visual_property": visual_steps,
        "selected_action": {
            "action_id": action_id,
            "grounding": action_turn.get("selected_grounding") if isinstance(action_turn, Mapping) else None,
            "dispatch_statuses": dispatches,
        },
        "screenshot_lineage": screenshot_lineage,
    }


def flagship_acceptance_errors(report: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    interaction = report.get("interaction")
    trace = report.get("trace_segments")
    completion = report.get("completion")
    visual = trace.get("visual_property") if isinstance(trace, Mapping) else None
    action = trace.get("selected_action") if isinstance(trace, Mapping) else None
    if not isinstance(visual, list) or not visual or max(int(item.get("subject_count", 0)) for item in visual) < 3:
        errors.append("missing batched three-subject visual_property evidence")
    if not isinstance(interaction, Mapping) or int(interaction.get("option_count", 0)) < 3:
        errors.append("missing three-option user decision")
    if not isinstance(interaction, Mapping) or not interaction.get("selected_option_id"):
        errors.append("declared user choice was not admitted")
    dispatches = action.get("dispatch_statuses") if isinstance(action, Mapping) else None
    if not isinstance(dispatches, list) or "sent" not in dispatches:
        errors.append("selected candidate GUI action was not dispatched")
    if report.get("terminal_status") != "done":
        errors.append("Runtime did not finish successfully")
    if not isinstance(completion, Mapping) or completion.get("outcome") != "success":
        errors.append("public completion was not successful")
    if not isinstance(completion, Mapping) or not completion.get("artifact"):
        errors.append("final PublicArtifact was not materialized")
    return tuple(errors)


async def _run_flagship(
    output_directory: Path,
    *,
    fixture: Path,
    environment: Mapping[str, str],
    choice_title: str,
    timeout_s: float,
) -> dict[str, object]:
    profile_errors = flagship_profile_errors(environment)
    if profile_errors:
        return {
            "schema_version": "supervised-gui-flagship-run.v1",
            "accepted": False,
            "acceptance_errors": profile_errors,
        }
    output_directory.mkdir(parents=True, exist_ok=True)
    trace = RunTraceRecorder(
        output_directory / "trace",
        run_id="controlled-shopping-flagship",
        analysis_identity={
            "scenario_id": "candidate_comparison_flagship",
            "action_policy_provider": environment["LLM_ACTIVE_PROFILE"],
            "action_policy_model": environment.get("LLM_DEEPSEEK_MODEL", ""),
            "visual_provider": environment["LLM_VISUAL_PROFILE"],
            "visual_model": environment["LLM_DEEPSEEK_VISION_MODEL"],
            "observation_tool_profile": environment["LLM_OBSERVATION_TOOL_PROFILE"],
            "interaction_tool_profile": environment["LLM_INTERACTION_TOOL_PROFILE"],
        },
    )
    session: TargetRuntimeSession | None = None
    interaction: dict[str, object] = {}
    with _served_fixture(fixture) as url:
        browser = ThreadBoundBrowserSession.launch(url, headless=True, lease_ttl_ms=900_000)
        surface = browser_surface_from_environment(browser, environment)
        if not isinstance(surface, BrowserSessionSurfaceBundle):
            browser.close()
            raise RuntimeError("shopping flagship requires the configured browser visual bundle")
        inference = getattr(surface.predicate_classifier, "inference", None)

        async def cleanup() -> None:
            await asyncio.to_thread(browser.close)
            close = getattr(inference, "close", None)
            if callable(close):
                close()

        world = InteractiveTaskEnvironment(UnifiedWorldEnvironment((surface,)))
        roles = model_roles_from_environment(
            environment,
            call_timeout_s=min(120.0, timeout_s),
            conversation_id="controlled-shopping-flagship",
        )
        runtime = compose_target_runtime(
            roles.action_policy,
            ProductionActionOutcomeProjector(),
            InteractiveTaskEvaluator(world),
            required_decisions=GROUNDED_ACTION_DECISION_CAPABILITIES,
            trace_sink=trace,
            goal_compiler=roles.goal_compiler,
            task_revision_compiler=roles.task_revision_compiler,
        )
        session = TargetRuntimeSession(
            runtime,
            RuntimeEnvironmentLease(cast(WorldEnvironment, world), cleanup),
            "controlled-shopping-flagship",
            datetime.now(UTC) + timedelta(seconds=timeout_s + 60),
            request_factory=_request_factory,
        )
        deadline = time.monotonic() + timeout_s
        try:
            await session.start(FLAGSHIP_TASK)
            waiting = await _wait_until_not_running(session, deadline_s=deadline)
            option = _matching_option(waiting, choice_title)
            request = waiting.pending_interaction
            interaction = {
                "status": waiting.status.value,
                "request_id": request.request_id if request is not None else "",
                "prompt": request.prompt if request is not None else "",
                "response_kind": request.response_kind.value if request is not None else "",
                "option_count": len(request.options) if request is not None else 0,
                "options": to_json_compatible(request.options) if request is not None else [],
                "selected_title": option.title if option is not None else choice_title,
                "selected_option_id": option.option_id if option is not None else "",
            }
            if waiting.status is PublicSessionStatus.WAITING_USER and request is not None and option is not None:
                await session.respond(SingleSelectionResponse(request.request_id, option.option_id))
                final = await _wait_until_not_running(session, deadline_s=deadline)
            else:
                final = waiting
            public_events = await session.events(0)
        finally:
            await session.close()

    trace_events = tuple(trace.events)
    report: dict[str, object] = {
        "schema_version": "supervised-gui-flagship-run.v1",
        "scenario_id": "candidate_comparison_flagship",
        "fixture": fixture.name,
        "task": FLAGSHIP_TASK,
        "declared_user_choice": choice_title,
        "model_identity": dict(trace.analysis_identity),
        "provider_usage": _provider_usage(trace_events),
        "interaction": interaction,
        "trace_segments": _trace_segments(trace_events, choice_title=choice_title),
        "terminal_status": final.status.value,
        "completion": to_json_compatible(final.completion),
        "public_events": to_json_compatible(public_events),
        "trace_path": "trace/trace.jsonl",
    }
    errors = flagship_acceptance_errors(report)
    report["accepted"] = not errors
    report["acceptance_errors"] = errors
    return report


def run_controlled_shopping_flagship(
    output_directory: Path,
    *,
    fixture: Path = DEFAULT_FIXTURE,
    environment: Mapping[str, str] | None = None,
    choice_title: str = DEFAULT_CHOICE,
    timeout_s: float = 600.0,
) -> dict[str, object]:
    output = output_directory.resolve()
    if (output / "trace" / "trace.jsonl").exists():
        raise FileExistsError("shopping flagship output already contains a trace")
    try:
        report = asyncio.run(
            _run_flagship(
                output,
                fixture=fixture,
                environment=dict(os.environ if environment is None else environment),
                choice_title=choice_title,
                timeout_s=timeout_s,
            )
        )
    except Exception as exc:
        report = {
            "schema_version": "supervised-gui-flagship-run.v1",
            "scenario_id": "candidate_comparison_flagship",
            "accepted": False,
            "acceptance_errors": (f"runner_exception:{type(exc).__name__}",),
        }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(to_json_compatible(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run-supervised-gui-flagship")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--choice", default=DEFAULT_CHOICE)
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(args.env_file, override=False)
    report = run_controlled_shopping_flagship(
        args.output,
        fixture=args.fixture,
        choice_title=args.choice,
        timeout_s=args.timeout_s,
    )
    print(json.dumps(to_json_compatible(report), indent=2, sort_keys=True))
    return 0 if report.get("accepted") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_CHOICE",
    "DEFAULT_FIXTURE",
    "FLAGSHIP_TASK",
    "flagship_acceptance_errors",
    "flagship_profile_errors",
    "run_controlled_shopping_flagship",
]
