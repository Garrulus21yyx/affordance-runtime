from __future__ import annotations

from typing import Protocol

from .diagnosis import CaseDiagnosis


class LangfuseClientPort(Protocol):
    def create_score(self, **kwargs: object) -> object: ...


class LangfuseDiagnosisSink:
    """Optional projection only; callers must invoke it through project_fail_open."""

    def __init__(self, client: LangfuseClientPort, trace_id: str) -> None:
        self._client = client
        self._trace_id = trace_id

    async def project(self, diagnosis: CaseDiagnosis) -> None:
        common = {
            "trace_id": self._trace_id,
            "metadata": {
                "case_id": diagnosis.case_id,
                "terminal_stage": diagnosis.terminal_stage,
                "terminal_code": diagnosis.terminal_code,
                "likely_upstream_stage": diagnosis.likely_upstream_stage,
                "confidence": diagnosis.confidence,
                "context_health": diagnosis.context_health.classification,
                "evidence_refs": list(diagnosis.evidence_refs),
            },
        }
        self._client.create_score(
            **common,
            name="interaction_shell_success",
            value=1 if diagnosis.success is True else 0,
        )
        self._client.create_score(
            **common,
            name="interaction_shell_context_fill_ratio",
            value=diagnosis.context_health.fill_ratio or 0,
        )
