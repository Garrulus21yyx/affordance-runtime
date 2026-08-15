import pytest

from affordance_runtime.model.providers.tool_transport import tool_transport_for_model
from affordance_runtime.model.providers.tool_transport_contracts import ToolTransportKind


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    (
        ("mistral", "mistral-medium-3-5", ToolTransportKind.NATIVE_REQUIRED_ONE),
        ("zhipu", "glm-4.6v-flash", ToolTransportKind.NATIVE_AUTO),
        ("zhipu", "glm-4.6v", ToolTransportKind.NATIVE_AUTO),
        ("zhipu", "glm-4.1v-thinking-flashx", ToolTransportKind.COMPACT_JSON),
    ),
)
def test_exact_model_capability_routing(provider, model, expected) -> None:
    assert tool_transport_for_model(provider, model) is expected


@pytest.mark.parametrize(
    ("provider", "model"),
    (
        ("zhipu", "glm-4.1v-thinking"),
        ("zhipu", "glm-4.7-flash"),
        ("mistral", "unknown"),
        ("other", "glm-4.6v"),
    ),
)
def test_unreviewed_tool_profiles_fail_closed(provider, model) -> None:
    with pytest.raises(ValueError, match="no admitted"):
        tool_transport_for_model(provider, model)
