#!/usr/bin/env python3
"""Run one raw-request GeneralistLMPlanner path against local SaaS fixtures."""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from affordance_runtime.approval_contracts import ConfiguredApprovalProvider
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.contracts import RiskLevel, VerifierSpec
from affordance_runtime.coordinator import RunCoordinator
from affordance_runtime.executors import DomExecutor, ExecutorRouter
from affordance_runtime.fixtures import EXPORT_SHA256, create_fixture_server
from affordance_runtime.generalist_planner import GeneralistLMPlanner
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import model_port_from_environment
from affordance_runtime.planning import ContractBuilder, ContractRequirements
from affordance_runtime.task_intake import UserRequest
from affordance_runtime.task_pipeline import GeneralistTaskPipeline


@dataclass(frozen=True)
class Scenario:
    path: str
    request: str
    constraints: dict[str, Any]
    grants: tuple[str, ...]
    requirements: dict[str, ContractRequirements]
    approval_capabilities: frozenset[str] = frozenset()


def _scenario(name: str, base_url: str) -> Scenario:
    if name == "pricing":
        return Scenario(
            path="/pricing",
            request="Read the Pro and Enterprise plan limits and return both plans' users, projects, and support.",
            constraints={"read_only": True, "must_return_evidence": True},
            grants=(),
            requirements={
                "dom_button_1": ContractRequirements(
                    verifier_plan=(VerifierSpec("dom_contains", "html", 'data-plan="pro" data-visible="true"'),),
                ),
                "dom_button_2": ContractRequirements(
                    verifier_plan=(
                        VerifierSpec("dom_contains", "html", 'data-plan="enterprise" data-visible="true"'),
                    ),
                ),
            },
        )
    if name == "settings":
        return Scenario(
            path="/settings",
            request="Enable notifications in my personal settings and confirm that the change persisted.",
            constraints={"must_return_evidence": True},
            grants=("settings.write.reversible",),
            requirements={
                "dom_button_1": ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "http_json",
                            f"{base_url}/api/state",
                            {"path": "settings.notifications", "value": "enabled"},
                        ),
                    ),
                    required_capabilities=("settings.write.reversible",),
                    risk=RiskLevel.MEDIUM,
                    idempotency_key="fixture-settings-enable-v1",
                    compensation="restore notifications=disabled",
                ),
            },
        )
    if name == "export":
        return Scenario(
            path="/reports",
            request=(
                "Export the report available on this page after the runtime approval gate; "
                "no additional user choice is needed. Return the downloaded file receipt."
            ),
            constraints={"approval_required": True, "must_return_evidence": True},
            grants=("report.export",),
            requirements={
                "dom_a_1": ContractRequirements(
                    verifier_plan=(VerifierSpec("evidence", "sha256", EXPORT_SHA256),),
                    required_capabilities=("report.export",),
                    risk=RiskLevel.HIGH,
                    idempotency_key="fixture-report-export-v1",
                ),
            },
            approval_capabilities=frozenset({"report.export"}),
        )
    raise ValueError(f"unknown scenario: {name}")


def run(scenario_name: str, artifact_root: Path) -> dict[str, Any]:
    fixture = create_fixture_server(port=0)
    server_thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    server_thread.start()
    try:
        base_url = f"http://{fixture.server_name}:{fixture.server_port}"
        scenario = _scenario(scenario_name, base_url)
        target = f"{base_url}{scenario.path}"
        model = model_port_from_environment()
        with BrowserSession.launch(target, headless=True, lease_ttl_ms=120_000) as session:
            router = ExecutorRouter()
            router.register(DomExecutor(session))
            pipeline = GeneralistTaskPipeline(
                compiler=LLMIntentCompiler(model),
                coordinator=RunCoordinator(
                    observer=session,
                    planner=GeneralistLMPlanner(model),
                    executor=router,
                    contract_builder=ContractBuilder(requirements=scenario.requirements),
                    approval_provider=(
                        ConfiguredApprovalProvider("fixture-user", set(scenario.approval_capabilities))
                        if scenario.approval_capabilities
                        else None
                    ),
                    artifacts=ArtifactStore(artifact_root),
                ),
                constraints=scenario.constraints,
                granted_capabilities=scenario.grants,
            )
            result = pipeline.run_sync(
                UserRequest(
                    request_id=f"generalist-{scenario_name}",
                    raw_text=scenario.request,
                    target_refs=(target,),
                    caller_identity="fixture-user",
                )
            )
        coordinator = result.coordinator
        return {
            "scenario": scenario_name,
            "status": result.status,
            "compilation_status": result.compilation.status.value,
            "runtime_error": coordinator.error_code.value if coordinator and coordinator.error_code else None,
            "result": coordinator.result if coordinator else {},
            "event_types": [node.kind for node in result.trace.nodes],
            "model_calls": [
                node.payload.get("model_call")
                for node in result.trace.nodes
                if node.kind in {"IntentDraftProduced", "PlannerProposalProduced"}
                and node.payload.get("model_call") is not None
            ],
        }
    finally:
        fixture.shutdown()
        fixture.server_close()
        server_thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=("pricing", "settings", "export"))
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = run(args.scenario, args.artifacts)
    rendered = json.dumps(value, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if value["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
