"""Additive case presentation evidence outside benchmark outcome authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from affordance_runtime.agent.interactions import (
    PublicArtifact,
    public_artifact_public_value,
    restore_public_artifact_public_value,
)
from affordance_runtime.agent.run_state import RunState, RunStatus

CASE_PRESENTATION_SCHEMA_VERSION = "target-loop-case-presentation.v1"


class CasePresentationStore(Protocol):
    def commit_case_presentation(self, sidecar: CasePresentationSidecar) -> None: ...

    def export_case_presentation(self, case_id: str, output_dir: Path) -> Path: ...


class PresentationReportingStatus(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"


@dataclass(frozen=True)
class PresentationReportingResult:
    status: PresentationReportingStatus
    failure_code: str = ""

    def __post_init__(self) -> None:
        if (self.status is PresentationReportingStatus.FAILED) != bool(self.failure_code):
            raise ValueError("presentation reporting status and failure code diverge")


@dataclass(frozen=True)
class CasePresentationSidecar:
    """Presentation-only case payload; never a success or failure input."""

    case_id: str
    artifact: PublicArtifact | None = None
    schema_version: str = CASE_PRESENTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.case_id.strip() or len(self.case_id) > 240:
            raise ValueError("case presentation sidecar identity is invalid")
        if self.artifact is not None and not isinstance(self.artifact, PublicArtifact):
            raise TypeError("case presentation artifact must be Runtime-admitted")
        if self.schema_version != CASE_PRESENTATION_SCHEMA_VERSION:
            raise ValueError("case presentation sidecar schema is unsupported")


def project_case_presentation(case_id: str, state: RunState | None) -> CasePresentationSidecar:
    artifact = None
    if (
        state is not None
        and state.status is RunStatus.DONE
        and state.last_step is not None
    ):
        artifact = state.last_step.public_artifact
    return CasePresentationSidecar(case_id, artifact)


def public_case_presentation(sidecar: CasePresentationSidecar) -> dict[str, object]:
    return {
        "schema_version": sidecar.schema_version,
        "case_id": sidecar.case_id,
        "artifact": (
            public_artifact_public_value(sidecar.artifact)
            if sidecar.artifact is not None
            else None
        ),
    }


def decode_public_case_presentation(value: object) -> CasePresentationSidecar:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "case_id",
        "artifact",
    }:
        raise ValueError("case presentation sidecar fields are invalid")
    artifact_value = value["artifact"]
    return CasePresentationSidecar(
        str(value["case_id"]),
        (
            restore_public_artifact_public_value(artifact_value)
            if artifact_value is not None
            else None
        ),
        str(value["schema_version"]),
    )


def report_case_presentation(
    store: CasePresentationStore,
    sidecar: CasePresentationSidecar,
    output_dir: Path | None,
) -> PresentationReportingResult:
    """Persist additive presentation evidence without changing case behavior."""

    try:
        store.commit_case_presentation(sidecar)
        if output_dir is not None:
            store.export_case_presentation(sidecar.case_id, output_dir)
    except Exception:
        return PresentationReportingResult(
            PresentationReportingStatus.FAILED,
            "presentation_sidecar_reporting_failed",
        )
    return PresentationReportingResult(PresentationReportingStatus.COMMITTED)
