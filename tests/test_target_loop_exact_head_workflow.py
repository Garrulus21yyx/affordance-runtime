from pathlib import Path

WORKFLOW = Path(".github/workflows/target-loop-internal.yml")


def test_exact_head_workflow_runs_full_gate_and_uploads_sha_bound_artifact() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "full-exact-head-regression:" in text
    assert "python -m pytest --collect-only -q" in text
    assert "python -m pytest -q" in text
    assert text.count("set -o pipefail") >= 2
    assert "ruff check src tests" in text
    assert "mypy src" in text
    assert "git diff --check" in text
    assert "docker compose -f environments/smart_room/docker-compose.yml config" in text
    assert "target-loop-full-validation-${{ github.sha }}" in text
    assert "needs: full-exact-head-regression" in text


def test_normal_exact_head_workflow_has_no_live_or_external_execution() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "RUN_LIVE_MODEL_POLICY_ATTESTATION" not in text
    assert "RUN_EXTERNAL_SMOKE" not in text
    assert "browsergym" not in text.lower()
    assert "miniwob" not in text.lower()
