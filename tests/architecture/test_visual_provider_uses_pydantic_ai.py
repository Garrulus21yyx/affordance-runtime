from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VISUAL = ROOT / "src" / "affordance_runtime" / "surfaces" / "visual"


def test_model_backed_visual_roles_have_no_direct_provider_transport() -> None:
    role_sources = "\n".join(
        (VISUAL / name).read_text(encoding="utf-8")
        for name in (
            "grounding.py",
            "predicate_classification.py",
            "disambiguation.py",
            "semantic_classification.py",
        )
    )

    assert "PydanticAIVisualInference" in role_sources
    for forbidden in (
        "_post_json",
        "_structured_json_content",
        "AsyncOpenAI",
        "urllib.request",
        "requests.post",
        "httpx.",
    ):
        assert forbidden not in role_sources


def test_product_visual_roles_share_one_pydantic_ai_inference_owner() -> None:
    bundle = (
        ROOT / "src" / "affordance_runtime" / "surfaces" / "browser_bundle.py"
    ).read_text(encoding="utf-8")

    assert bundle.count("pydantic_ai_visual_inference_from_environment(environment)") == 1
    assert bundle.count("inference=inference") == 8
