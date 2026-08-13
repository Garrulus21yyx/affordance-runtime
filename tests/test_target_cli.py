from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from target_agent_loop_support import FirstOfferedActionPolicy

from affordance_runtime import cli
from affordance_runtime.agent import TOOL_ACTION_DECISION_CAPABILITIES, compose_target_runtime
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.evaluation import ProductionActionEvaluator, ProductionTaskEvaluator
from affordance_runtime.model_policy.grounded_tool_contracts import GROUNDED_TOOLS_PROTOCOL
from affordance_runtime.target_cli import (
    load_target_request,
    run_target_request,
    task_boundary_from_mapping,
)
from affordance_runtime.target_composition import compose_target_client_from_environment
from affordance_runtime.target_runtime_client import TargetRuntimeClient
from affordance_runtime.task import RiskProfile, TaskUnsupported, ThinTaskIntake


def _boundary_file(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "boundary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_target_boundary_decodes_stable_authority_without_gui_identity(tmp_path: Path) -> None:
    request = load_target_request(
        "task:cli-test",
        "Enable shared state",
        _boundary_file(tmp_path, {
            "allowed_effects": ["shared_state_enabled"],
            "risk_profile": "low",
            "success_criteria": [{
                "id": "shared-enabled",
                "kind": "fact_equals",
                "predicate": "expanded",
                "expected_value": True,
            }],
            "loop_budget": {"max_turns": 4, "max_observations": 8},
        }),
    )

    assert request.boundary.allowed_effects == ("shared_state_enabled",)
    assert request.boundary.risk_profile is RiskProfile.LOW
    assert request.boundary.loop_budget.max_turns == 4
    assert request.source_ref == "cli-boundary:boundary.json"
    assert "selector" not in repr(request)


def test_target_boundary_rejects_unknown_fields_and_empty_success(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported fields"):
        task_boundary_from_mapping({"selector": "#save"})
    with pytest.raises(ValueError, match="requires success_criteria"):
        load_target_request(
            "task:empty",
            "Inspect the page",
            _boundary_file(tmp_path, {}),
        )


def test_target_boundary_private_inputs_fail_closed_at_target_intake(tmp_path: Path) -> None:
    request = load_target_request(
        "task:private",
        "Save the form",
        _boundary_file(tmp_path, {
            "allowed_effects": ["form_saved"],
            "risk_profile": "low",
            "inputs": {"selector": "#save"},
            "success_criteria": [{
                "id": "saved",
                "kind": "fact_equals",
                "predicate": "saved",
                "expected_value": True,
            }],
        }),
    )
    admitted = ThinTaskIntake().compile(request)

    assert isinstance(admitted, TaskUnsupported)
    assert admitted.reason_code == "runtime_private_input_not_supported"


def test_target_product_composition_defaults_to_grounded_tools(monkeypatch) -> None:
    captured = {}

    class Policy:
        supported_decisions = TOOL_ACTION_DECISION_CAPABILITIES

        async def decide(self, context):
            del context
            return PolicyFailure("fixture", "fixture", False)

    def fake_policy(environment, *, call_timeout_s, interaction_protocol):
        captured.update({
            "environment": environment,
            "call_timeout_s": call_timeout_s,
            "interaction_protocol": interaction_protocol,
        })
        return Policy()

    monkeypatch.setattr(
        "affordance_runtime.target_composition.model_policy_from_environment",
        fake_policy,
    )

    client = compose_target_client_from_environment({"PROFILE": "fixture"}, call_timeout_s=7)

    assert captured == {
        "environment": {"PROFILE": "fixture"},
        "call_timeout_s": 7,
        "interaction_protocol": GROUNDED_TOOLS_PROTOCOL,
    }
    assert client.runtime.required_decisions == TOOL_ACTION_DECISION_CAPABILITIES


def test_target_run_root_cli_routes_without_changing_legacy_run(monkeypatch, tmp_path: Path) -> None:
    boundary = _boundary_file(tmp_path, {
        "success_criteria": [{
            "id": "available",
            "kind": "fact_equals",
            "predicate": "available",
            "expected_value": True,
        }],
    })
    captured = {}

    def fake_run(args):
        captured["command"] = args.command
        captured["instruction"] = args.instruction
        return {"status": "done"}

    monkeypatch.setattr("affordance_runtime.target_cli.run_target_command", fake_run)

    exit_code = cli.main([
        "target-run",
        "--target",
        "https://example.test",
        "--instruction",
        "Inspect the page",
        "--boundary",
        str(boundary),
    ])

    assert exit_code == 0
    assert captured == {"command": "target-run", "instruction": "Inspect the page"}
    parser = cli.build_parser()
    legacy = parser.parse_args(["run"])
    assert legacy.command == "run"
    assert legacy.scenario == "pricing"


def test_target_run_closes_browser_and_projects_nonready_outcome(tmp_path: Path) -> None:
    request = load_target_request(
        "task:needs-effects",
        "Modify the record",
        _boundary_file(tmp_path, {
            "risk_profile": "low",
            "success_criteria": [{
                "id": "changed",
                "kind": "fact_equals",
                "predicate": "changed",
                "expected_value": True,
            }],
        }),
    )
    class UnusedPolicy:
        async def decide(self, context):
            del context
            raise AssertionError("nonready CLI intake must not call policy")

    class UnusedEvaluator:
        async def evaluate(self, *args):
            del args
            raise AssertionError("nonready CLI intake must not evaluate")

    client = TargetRuntimeClient(compose_target_runtime(
        UnusedPolicy(),
        UnusedEvaluator(),
        UnusedEvaluator(),
    ))

    def forbidden_session_factory(target, *, headless):
        del target, headless
        raise AssertionError("nonready CLI intake must not launch a browser")

    payload = run_target_request(
        "https://example.test",
        request,
        client=client,
        session_factory=forbidden_session_factory,
    )

    assert payload["status"] == "needs_user_input"
    assert payload["reason_code"] == "effect_authority_required"


def test_target_run_executes_real_dom_through_product_runtime(tmp_path: Path) -> None:
    request = load_target_request(
        "task:cli-dom",
        "Enable shared state",
        _boundary_file(tmp_path, {
            "allowed_effects": ["shared_state_enabled"],
            "risk_profile": "low",
            "success_criteria": [{
                "id": "shared-enabled",
                "kind": "fact_equals",
                "predicate": "expanded",
                "expected_value": True,
            }],
        }),
    )
    html = """
    <!doctype html><html><body><main>
      <button id="shared" aria-expanded="false"
        onclick="this.setAttribute('aria-expanded', 'true')">Enable shared state</button>
    </main></body></html>
    """
    client = TargetRuntimeClient(compose_target_runtime(
        FirstOfferedActionPolicy(),
        ProductionActionEvaluator(),
        ProductionTaskEvaluator(),
    ))

    payload = run_target_request(
        "data:text/html," + quote(html),
        request,
        client=client,
    )

    assert payload["intake_status"] == "ready"
    assert payload["status"] == "done"
    assert payload["observation_count"] == 2
    assert payload["execution_count"] == 1
