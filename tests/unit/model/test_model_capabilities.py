from affordance_runtime.model.providers.capabilities import model_supports_multimodal


def test_declared_visual_model_families_are_multimodal_and_text_siblings_are_not() -> None:
    assert model_supports_multimodal("zhipu", "glm-4.6v-flash")
    assert model_supports_multimodal("gemini", "gemini-2.5-flash")
    assert model_supports_multimodal("deepseek", "deepseek-v4-flash-vision-exp")
    assert not model_supports_multimodal("zhipu", "glm-4.6")
    assert not model_supports_multimodal("deepseek", "deepseek-v4-flash")
    assert not model_supports_multimodal("unknown", "vision-model")
