from pathlib import Path

WORKFLOW = Path(".github/workflows/target-loop-live-policy.yml")


def test_live_policy_workflow_is_manual_false_by_default_and_environment_protected() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "run_live_policy:" in text and "default: false" in text
    assert "if: inputs.run_live_policy" in text
    assert "environment: live-model-policy" in text
    assert "RUN_LIVE_MODEL_POLICY_ATTESTATION: \"1\"" in text


def test_live_policy_workflow_does_not_run_external_or_semantic_evaluator() -> None:
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    assert "run_external_smoke" not in text
    assert "browsergym" not in text and "miniwob" not in text
    assert "semantic-judge" not in text and "semantic_evaluator" not in text
