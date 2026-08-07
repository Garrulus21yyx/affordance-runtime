"""Coordinator-facing artifact persistence seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ExecutionReceipt
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class ArtifactPhase:
    """Write runtime artifacts and keep the trace artifact index updated."""

    artifacts: ArtifactStore | None

    def write_observation(
        self,
        run_id: str,
        sequence: int,
        snapshot: BrowserSnapshot,
    ) -> ArtifactRef | None:
        if self.artifacts is None:
            return None
        return self.artifacts.write_observation(run_id, sequence, snapshot.observation)

    def write_receipt(
        self,
        run_id: str,
        sequence: int,
        receipt: ExecutionReceipt,
    ) -> ArtifactRef | None:
        if self.artifacts is None:
            return None
        download_path = receipt.evidence.get("path")
        if isinstance(download_path, str) and download_path:
            path = self.artifacts.run_dir(run_id) / "downloads" / Path(download_path).name
            if path.exists():
                self.artifacts.register_file(
                    run_id,
                    path,
                    "application/octet-stream",
                )
        return self.artifacts.write_receipt(run_id, sequence, receipt)

    def write_verification(
        self,
        run_id: str,
        sequence: int,
        report: VerificationReport,
    ) -> ArtifactRef | None:
        if self.artifacts is None:
            return None
        return self.artifacts.write_verification(run_id, sequence, report)

    @staticmethod
    def index_artifact(trace: TraceDag, artifact: ArtifactRef | None) -> None:
        if artifact is not None:
            trace.artifact_index.append(artifact.path)

    @staticmethod
    def index_paths(trace: TraceDag, paths: list[str]) -> None:
        trace.artifact_index.extend(path for path in paths if path)
