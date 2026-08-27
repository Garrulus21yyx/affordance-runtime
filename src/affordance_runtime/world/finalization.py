"""Optional environment finalization capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.world.acquisition import ObservationAcquisition

FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS = 700


class FinalResponseCodec(Protocol):
    """Environment-owned representation adapter applied before one STOP."""

    def normalize(self, content: str) -> str: ...


def final_response_model_guidance(codec: FinalResponseCodec) -> str:
    """Return optional bounded tool guidance owned by the response codec."""

    guidance = getattr(codec, "model_guidance", "")
    if not isinstance(guidance, str):
        raise TypeError("final response model guidance must be text")
    guidance = " ".join(guidance.split())
    if len(guidance) > FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS:
        raise ValueError("final response model guidance exceeds its tool-contract bound")
    return guidance


@dataclass(frozen=True)
class PlainTextFinalResponseCodec:
    """Identity codec for environments whose native response is plain text."""

    def normalize(self, content: str) -> str:
        return content


PLAIN_TEXT_FINAL_RESPONSE_CODEC = PlainTextFinalResponseCodec()


@dataclass(frozen=True)
class EnvironmentFinalization:
    result: ActionResult
    post_acquisition: ObservationAcquisition | None = None


class FinalizingEnvironment(Protocol):
    @property
    def final_response_codec(self) -> FinalResponseCodec: ...

    @property
    def supports_finalization(self) -> bool: ...

    async def finalize(self, content: str) -> EnvironmentFinalization: ...
