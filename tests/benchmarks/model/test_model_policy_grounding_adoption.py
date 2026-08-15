from affordance_runtime.benchmarks.model_conformance.grounding import (
    CompactGroundingEvidence,
    evaluate_compact_grounding_adoption,
)


def test_compact_grounding_adoption_requires_all_declared_gates() -> None:
    evidence = CompactGroundingEvidence(
        mistral_no_regression=True, fixture_no_regression=True, parser_unchanged=True,
        runtime_admission_unchanged=True, privacy_passed=True, prompt_delta_bytes=900,
        ollama_improved=True, zero_retry_fallback=True, action_space_unchanged=True,
        model_specific_branches=False,
    )
    assert evaluate_compact_grounding_adoption(evidence) == "adoptable"
    assert evaluate_compact_grounding_adoption(
        CompactGroundingEvidence(**{**evidence.__dict__, "ollama_improved": False})
    ) == "diagnostic_only"


def test_adoption_contract_has_no_model_name_input() -> None:
    assert "model" not in CompactGroundingEvidence.__annotations__
