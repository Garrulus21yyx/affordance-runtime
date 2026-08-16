from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST


def test_conformance_policy_uses_typed_agent_context_and_production_loop() -> None:
    composition = Path("src/affordance_runtime/benchmarks/external_smoke/composition.py").read_text()
    runner = Path("src/affordance_runtime/benchmarks/target_loop/runner.py").read_text()
    assert "ModelBackedAgentPolicy" in composition
    assert "ResolvedModelDecision" in composition
    assert "request.agent_context" in composition
    assert "payload_to_decision" not in composition
    assert "serialized_context" not in composition
    assert "TargetRuntime" in runner
    assert "AgentEpisodeRunner(" not in runner
    assert "AgentLoop(" not in runner
    policy_source = composition.split("def _public_decision", 1)[1]
    assert "benchmark_task_id" not in policy_source
    assert ".execute(" not in composition
    evaluator = Path("src/affordance_runtime/evaluation/action_evaluator.py").read_text()
    for private in ("benchmark_task_id", "private_element_id", "selector", "raw_reward"):
        assert private not in evaluator


def test_adapter_case_report_excludes_oracle_and_private_routes(tmp_path) -> None:
    from affordance_runtime.benchmarks.external_smoke import adapter_reporting

    payload = {
        "schema_version": "browsergym-adapter-conformance-report.v1",
        "accepted": True,
        "errors": (),
        "package_version": "0.14.3",
        "target_loop_adapter_ready": True,
        "suite": {"cases": ({"case_id": "miniwob-click-button"},)},
    }
    path = tmp_path / "adapter-conformance.json"
    adapter_reporting._atomic_json(path, payload)
    text = path.read_text().casefold()
    for case in EXTERNAL_SMOKE_MANIFEST.cases:
        assert case.benchmark_task_id.casefold() not in text
    for marker in (
        "expected_answer", "target_answer", "reference_action", "hidden_state",
        "raw_reward", "selector", "private_element_id", "credential", "endpoint_url",
    ):
        assert marker not in text
