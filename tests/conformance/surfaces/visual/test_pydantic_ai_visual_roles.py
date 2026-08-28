from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from affordance_runtime.model.policy.pydantic_ai_bridge import ConfiguredPydanticAIModel
from affordance_runtime.surfaces.visual.disambiguation import VisualCandidate
from affordance_runtime.surfaces.visual.predicate_classification import (
    PredicateTruth,
    PydanticAIVisualPredicateClassifier,
    VisualPredicateClassificationRequest,
)
from affordance_runtime.surfaces.visual.pydantic_ai_inference import PydanticAIVisualInference
from affordance_runtime.surfaces.visual.semantic_classification import (
    PydanticAIVisualSemanticClassifier,
    VisualChangeClassificationRequest,
    VisualLayerRole,
    VisualLayerTransitionRequest,
    VisualSemanticRole,
    VisualSpatialClassificationRequest,
    VisualTextReadingRequest,
)


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (200, 100), "white").save(stream, format="PNG")
    return stream.getvalue()


def _inference(*outputs: str):  # type: ignore[no-untyped-def]
    scripted = list(outputs)
    records = []

    async def respond(messages, info):  # type: ignore[no-untyped-def]
        del info
        records.append(messages)
        return ModelResponse(parts=[TextPart(scripted.pop(0))])

    return (
        PydanticAIVisualInference(
            ConfiguredPydanticAIModel(
                FunctionModel(respond, model_name="visual-role-fixture"),
                "zhipu",
                "glm-4.6v-test",
                "fixture",
                True,
            ),
            timeout_s=5,
        ),
        records,
    )


def _candidates() -> tuple[VisualCandidate, ...]:
    return (
        VisualCandidate("E1", "one", "option", "First", (10, 10, 40, 20)),
        VisualCandidate("E2", "two", "option", "Second", (100, 10, 40, 20)),
    )


def test_predicate_and_semantic_roles_use_one_typed_pydantic_ai_boundary() -> None:
    inference, records = _inference(
        '{"assessments":[{"ref":"E1","truth":"true","confidence":0.9},'
        '{"ref":"E2","truth":"unknown","confidence":0.3}]}',
        '{"assessments":[{"ref":"E1","text":"Alpha","confidence":0.95},{"ref":"E2","text":null,"confidence":0.2}]}',
        '{"truth":"false","confidence":0.8}',
        '{"truth":"true","confidence":0.85}',
        '{"assessments":[{"ref":"E1","description":"A sign-in dialog with a visible QR code",'
        '"role":"dialog","occludes_primary_surface":true,"confidence":0.92},'
        '{"ref":"E2","description":null,"role":"unknown",'
        '"occludes_primary_surface":null,"confidence":0.2}]}',
    )
    image = _png()
    candidates = _candidates()
    predicate = PydanticAIVisualPredicateClassifier(inference)
    text_reader = PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.TEXT)
    spatial_classifier = PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.SPATIAL)
    change_classifier = PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.CHANGE)
    layer_observer = PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.LAYER_CHANGE)

    assessments = predicate.classify(
        VisualPredicateClassificationRequest(
            "sample:predicate",
            image,
            (200, 100),
            "is visually selected",
            candidates,
        )
    )
    readings = text_reader.read(
        VisualTextReadingRequest(
            "sample:text",
            image,
            (200, 100),
            "read the visible labels",
            candidates,
        )
    )
    spatial = spatial_classifier.classify(
        VisualSpatialClassificationRequest(
            "sample:spatial",
            image,
            (200, 100),
            "E1 is left of E2",
            candidates,
        )
    )
    change = change_classifier.classify(
        VisualChangeClassificationRequest(
            "sample:change",
            image,
            image,
            (200, 100),
            "selection state changed",
            candidates,
        )
    )
    layers = layer_observer.observe_layers(
        VisualLayerTransitionRequest(
            "sample:layers",
            image,
            image,
            (200, 100),
            candidates,
        )
    )

    assert tuple(item.truth for item in assessments) == (PredicateTruth.TRUE, PredicateTruth.UNKNOWN)
    assert tuple(item.text for item in readings) == ("Alpha", None)
    assert spatial.truth is PredicateTruth.FALSE
    assert change.truth is PredicateTruth.TRUE
    assert layers[0].role is VisualLayerRole.DIALOG
    assert layers[0].description == "A sign-in dialog with a visible QR code"
    assert layers[1].description is None
    binary_counts = []
    for messages in records:
        user = next(part for part in messages[-1].parts if isinstance(part, UserPromptPart))
        binary_counts.append(sum(isinstance(item, BinaryContent) for item in user.content))
    assert binary_counts == [1, 1, 1, 2, 2]


def test_visual_inference_rejects_text_models_and_close_is_terminal() -> None:
    async def respond(messages, info):  # type: ignore[no-untyped-def]
        del messages, info
        return ModelResponse(parts=[TextPart('{"truth":"true","confidence":0.9}')])

    configured = ConfiguredPydanticAIModel(
        FunctionModel(respond, model_name="visual-lifecycle-fixture"),
        "deepseek",
        "deepseek-v4-flash",
        "fixture",
        False,
    )
    with pytest.raises(ValueError, match="requires a multimodal model"):
        PydanticAIVisualInference(configured, timeout_s=5)

    inference, _ = _inference('{"truth":"true","confidence":0.9}')
    classifier = PydanticAIVisualSemanticClassifier(inference, VisualSemanticRole.SPATIAL)
    request = VisualSpatialClassificationRequest(
        "sample:lifecycle",
        _png(),
        (200, 100),
        "E1 is left of E2",
        _candidates(),
    )
    assert classifier.classify(request).truth is PredicateTruth.TRUE

    inference.close()
    with pytest.raises(RuntimeError, match="is closed"):
        classifier.classify(request)
