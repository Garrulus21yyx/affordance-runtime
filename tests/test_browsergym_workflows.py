from pathlib import Path


def test_push_workflow_runs_real_adapter_without_provider_secrets() -> None:
    job = Path(".github/workflows/browsergym-adapter-conformance.yml").read_text()
    assert "push:" in job
    assert ".[dev,external-smoke]" in job
    assert "7fd85d71a4b60325c6585396ec4f48377d049838" in job
    assert "adapter-conformance" in job
    assert "LLM_MISTRAL_API_KEY" not in job
    assert "RUN_EXTERNAL_SMOKE" not in job


def test_manual_fixed_smoke_is_protected_explicit_and_exact_profile() -> None:
    text = Path(".github/workflows/browsergym-fixed-external-smoke.yml").read_text()
    for required in (
        "workflow_dispatch:", "type: boolean", "default: false",
        "environment: browsergym-fixed-external-smoke", "RUN_EXTERNAL_SMOKE: \"1\"",
        "mistral-medium-3-5", "format-only", "7.5", "External preflight",
        "Exact-head live Mistral attestation", "--execute", "github.sha",
    ):
        assert required in text


def test_manual_fixed_smoke_isolates_incompatible_playwright_profiles() -> None:
    text = Path(".github/workflows/browsergym-fixed-external-smoke.yml").read_text()
    assert ".[dev,web,visual,parent,external-smoke]" not in text
    assert "python -m pip install -e '.[dev,web,visual,parent]'" in text
    assert "python -m venv /tmp/browsergym-fixed-venv" in text
    assert "/tmp/browsergym-fixed-venv/bin/python -m pip install -e '.[dev,external-smoke]'" in text
    for command in (
        "adapter-conformance", "external_smoke.cli preflight", "external_smoke.cli run",
    ):
        line = next(item for item in text.splitlines() if command in item)
        assert "/tmp/browsergym-fixed-venv/bin/python" in line


def test_manual_fixed_smoke_scopes_external_fixture_and_propagates_pytest_failures() -> None:
    text = Path(".github/workflows/browsergym-fixed-external-smoke.yml").read_text()
    job_env = text.split("    steps:", maxsplit=1)[0]
    assert "MINIWOB_URL" not in job_env
    assert text.count("MINIWOB_URL: file:///tmp/miniwob-plusplus/miniwob/html/miniwob/") == 2
    full_validation_step = text.split(
        "      - name: Full exact-head CI dependency", maxsplit=1,
    )[1].split("      - name: Attest full exact-head CI", maxsplit=1)[0]
    assert "set -o pipefail" in full_validation_step
