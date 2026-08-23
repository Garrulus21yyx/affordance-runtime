"""Optional environment finalization capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.world.acquisition import ObservationAcquisition


class FinalResponseCodec(Protocol):
    """Environment-owned representation adapter applied before one STOP."""

    def normalize(self, content: str) -> str: ...


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
