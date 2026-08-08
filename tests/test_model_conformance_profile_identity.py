from affordance_runtime.benchmarks.model_conformance.profile_identity import (
    identity_from_ollama_inventory,
)


def test_ollama_identity_uses_exact_installed_metadata_without_endpoint() -> None:
    identity = identity_from_ollama_inventory(
        "qwen2.5:7b",
        runtime_version="0.32.0",
        models=({
            "name": "qwen2.5:7b",
            "digest": "abc123",
            "details": {
                "family": "qwen2", "parameter_size": "7.6B",
                "quantization_level": "Q4_K_M",
            },
        },),
    )
    assert identity.model_digest == "abc123"
    assert identity.family == "qwen2"
    assert identity.quantization == "Q4_K_M"
    assert "http" not in repr(identity)
