"""Filesystem-backed run artifacts for reproducible traces and evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from affordance_runtime.contracts import ExecutionReceipt, Observation
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.trace import JsonlTraceWriter, TraceDag
from affordance_runtime.verification import VerificationReport


def _safe_run_id(run_id: str) -> str:
    if not run_id or run_id in {".", ".."} or any(character in run_id for character in ("/", "\\", "\0")):
        raise ValueError(f"unsafe run id: {run_id!r}")
    return run_id


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    media_type: str


@dataclass
class ArtifactStore:
    root: Path
    _refs: dict[str, list[ArtifactRef]] = field(default_factory=dict)

    def run_dir(self, run_id: str) -> Path:
        path = self.root / _safe_run_id(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, run_id: str, relative_path: str, value: Any) -> ArtifactRef:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe artifact path: {relative_path!r}")
        path = self.run_dir(run_id) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            to_json_compatible(value),
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        path.write_bytes(encoded)
        return self._record(run_id, ArtifactRef(str(path), hashlib.sha256(encoded).hexdigest(), "application/json"))

    def register_file(self, run_id: str, path: Path, media_type: str) -> ArtifactRef:
        encoded = path.read_bytes()
        return self._record(run_id, ArtifactRef(str(path), hashlib.sha256(encoded).hexdigest(), media_type))

    def references(self, run_id: str) -> list[ArtifactRef]:
        return list(self._refs.get(run_id, []))

    def _record(self, run_id: str, artifact: ArtifactRef) -> ArtifactRef:
        refs = self._refs.setdefault(run_id, [])
        refs[:] = [item for item in refs if item.path != artifact.path]
        refs.append(artifact)
        return artifact

    def write_observation(self, run_id: str, sequence: int, observation: Observation) -> ArtifactRef:
        return self.write_json(run_id, f"observations/observation_{sequence:04d}.json", asdict(observation))

    def write_receipt(self, run_id: str, sequence: int, receipt: ExecutionReceipt) -> ArtifactRef:
        return self.write_json(run_id, f"receipts/receipt_{sequence:04d}.json", asdict(receipt))

    def write_verification(self, run_id: str, sequence: int, report: VerificationReport) -> ArtifactRef:
        return self.write_json(run_id, f"receipts/verification_{sequence:04d}.json", asdict(report))

    def finalize(self, run_id: str, trace: TraceDag, run_summary: dict[str, Any]) -> list[ArtifactRef]:
        summary_ref = self.write_json(run_id, "run.json", run_summary)
        trace.artifact_index = sorted(set(trace.artifact_index + [summary_ref.path]))
        trace_path = JsonlTraceWriter(self.run_dir(run_id) / "events.jsonl").write(trace)
        trace_bytes = trace_path.read_bytes()
        trace_ref = self._record(
            run_id,
            ArtifactRef(str(trace_path), hashlib.sha256(trace_bytes).hexdigest(), "application/x-ndjson"),
        )
        return [summary_ref, trace_ref]
