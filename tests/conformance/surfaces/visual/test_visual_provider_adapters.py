from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from affordance_runtime.integrations.omniparser import OmniParserHttpRegionProposer
from affordance_runtime.model.policy.pydantic_ai_bridge import ConfiguredPydanticAIModel
from affordance_runtime.model.providers.port import StructuredModelError
from affordance_runtime.surfaces.visual.disambiguation import (
    PydanticAIVisualCandidateDisambiguator,
    VisualCandidate,
    VisualCandidateDisambiguationRequest,
)
from affordance_runtime.surfaces.visual.grounding import (
    VisualRegionProposalRequest,
    configured_visual_region_proposer_from_environment,
    visual_region_proposer_from_environment,
)
from affordance_runtime.surfaces.visual.pydantic_ai_inference import PydanticAIVisualInference


def _png() -> bytes:
    from io import BytesIO

    output = BytesIO()
    Image.new("RGB", (200, 100), "white").save(output, format="PNG")
    return output.getvalue()


def test_omniparser_adapter_normalizes_official_parse_schema_as_observation_only() -> None:
    received: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({
                "som_image_base64": "unused",
                "parsed_content_list": [
                    {"type": "text", "bbox": [0.1, 0.1, 0.4, 0.2], "interactivity": False, "content": "Help"},
                    {"type": "icon", "bbox": [0.5, 0.4, 0.7, 0.7], "interactivity": True, "content": "Save"},
                ],
                "latency": 0.1,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    image = _png()
    try:
        regions = OmniParserHttpRegionProposer(
            f"http://127.0.0.1:{server.server_port}"
        ).propose(VisualRegionProposalRequest(
            "sample", None, image, (200, 100), "click Save", 2,
        ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert set(received[0]) == {"base64_image"}
    assert base64.b64decode(str(received[0]["base64_image"])) == image
    assert [item.label for item in regions] == ["Save", "Help"]
    assert all(item.primitive_action == "observe_only" for item in regions)
    assert regions[0].pixel_bbox((200, 100)) == pytest.approx((100, 40, 40, 30))


def test_region_factory_selects_omniparser_without_importing_an_agent_runtime() -> None:
    proposer = visual_region_proposer_from_environment({
        "VISUAL_REGION_PROVIDER": "omniparser",
        "OMNIPARSER_BASE_URL": "http://127.0.0.1:8000",
    })

    assert isinstance(proposer, OmniParserHttpRegionProposer)
    assert proposer.provider == "omniparser"

    configured = configured_visual_region_proposer_from_environment({
        "OMNIPARSER_BASE_URL": "http://127.0.0.1:8000",
    })
    assert isinstance(configured, OmniParserHttpRegionProposer)


def test_candidate_disambiguator_returns_only_a_supplied_e_ref() -> None:
    outputs = ['{"ref":"E2"}', '{"ref":"E9"}']
    received: list[list[object]] = []

    async def respond(messages, info):  # type: ignore[no-untyped-def]
        del info
        received.append(messages)
        return ModelResponse(parts=[TextPart(outputs.pop(0))])

    inference = PydanticAIVisualInference(
        ConfiguredPydanticAIModel(
            FunctionModel(respond, model_name="visual-disambiguation-fixture"),
            "zhipu",
            "glm-4.6v-test",
            "fixture",
            True,
        ),
        timeout_s=5,
    )
    request = VisualCandidateDisambiguationRequest(
        "sample",
        _png(),
        (200, 100),
        "click the right Save button",
        (
            VisualCandidate("E1", "left", "button", "Save", (10, 10, 40, 20)),
            VisualCandidate("E2", "right", "button", "Save", (100, 10, 40, 20)),
        ),
    )
    disambiguator = PydanticAIVisualCandidateDisambiguator(inference)
    assert disambiguator.choose(request) == "E2"
    with pytest.raises(StructuredModelError, match="E-ref validation"):
        disambiguator.choose(request)

    user = next(part for part in received[0][-1].parts if isinstance(part, UserPromptPart))
    assert any(isinstance(item, BinaryContent) for item in user.content)
    assert all("coordinate" not in item.casefold() for item in user.content if isinstance(item, str))
