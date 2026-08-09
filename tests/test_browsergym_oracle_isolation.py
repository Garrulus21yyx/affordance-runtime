from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST


def test_conformance_policy_uses_production_policy_parser_and_agent_loop() -> None:
    composition = Path("src/affordance_runtime/benchmarks/external_smoke/composition.py").read_text()
    runner = Path("src/affordance_runtime/benchmarks/target_loop/runner.py").read_text()
    assert "ModelBackedAgentPolicy" in composition
    assert "ModelDecisionResponse" in composition
    assert "parse_agent_decision" not in composition
    assert "AgentEpisodeRunner" in runner
    policy_source = composition.split("class BrowserGymMechanicalActionEvaluator", 1)[0]
    assert "benchmark_task_id" not in policy_source
    assert ".execute(" not in composition


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
