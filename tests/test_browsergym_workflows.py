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
