from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field


class CompletedRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["interaction-shell.completed-run.v1"] = (
        "interaction-shell.completed-run.v1"
    )
    locator_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    run_attempt_id: str = Field(pattern=r"^attempt:[0-9a-f]{32}$")
    case_id: str = Field(min_length=1, max_length=240)
    benchmark_result: Literal["available", "not_applicable"] = "available"
    status: str = Field(min_length=1, max_length=80)
    turns: int = Field(default=0, ge=0)
    provider_input_tokens: int = Field(default=0, ge=0)
    provider_output_tokens: int = Field(default=0, ge=0)
    recoveries: int = Field(default=0, ge=0)
    control_stalls: int = Field(default=0, ge=0)
    state_oscillations: int = Field(default=0, ge=0)
    detour_disposition: Literal["suspected_detour", "not_assessed"] = "not_assessed"
    langfuse_url: str | None = None
    local_evidence_url: str | None = None


class CompletedRunSummaryResolver:
    """Read-only projection over an explicit allowlist of persisted run directories."""

    def __init__(
        self,
        run_directories: Sequence[str | Path] = (),
        *,
        langfuse_base_url: str = "",
        local_evidence_enabled: bool = False,
    ) -> None:
        self._run_directories = tuple(Path(item).resolve() for item in run_directories)
        self._langfuse_base_url = langfuse_base_url.rstrip("/")
        self._local_evidence_enabled = local_evidence_enabled
        self._locators: dict[str, tuple[Path, Path]] = {}

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None):
        values = environment or os.environ
        raw = values.get("INTERACTION_SHELL_EVIDENCE_RUNS", "")
        directories = tuple(item for item in raw.split(os.pathsep) if item.strip())
        return cls(
            directories,
            langfuse_base_url=values.get("LANGFUSE_BASE_URL", ""),
            local_evidence_enabled=bool(values.get("INTERACTION_SHELL_EVIDENCE_ACCESS_KEY", "").strip())
            and values.get(
                "INTERACTION_SHELL_LOCAL_EVIDENCE_ENABLED", ""
            ).strip().casefold()
            in {"1", "true", "yes", "on"},
        )

    def list(self) -> tuple[CompletedRunSummary, ...]:
        self._locators.clear()
        summaries = [
            summary
            for run_directory in self._run_directories
            for summary in self._read_run(run_directory)
        ]
        return tuple(sorted(summaries, key=lambda item: (item.run_attempt_id, item.case_id)))

    def result_path(self, locator_id: str) -> Path:
        if locator_id not in self._locators:
            self.list()
        try:
            run_directory, result_path = self._locators[locator_id]
        except KeyError as exc:
            raise FileNotFoundError("completed run locator is unavailable") from exc
        resolved = result_path.resolve(strict=True)
        if not resolved.is_relative_to(run_directory) or resolved.parent != run_directory / "cases":
            raise PermissionError("completed run locator escaped its allowlisted run")
        return resolved

    def _read_run(self, run_directory: Path) -> tuple[CompletedRunSummary, ...]:
        run_file = run_directory / "run.json"
        cases_directory = run_directory / "cases"
        if not run_file.is_file() or not cases_directory.is_dir():
            return ()
        try:
            run_payload = _read_json(run_file)
            identity = run_payload.get("identity")
            if not isinstance(identity, Mapping):
                return ()
            attempt_id = str(identity.get("run_attempt_id", ""))
            if not _valid_attempt_id(attempt_id):
                return ()
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return ()
        summaries = []
        for result_path in sorted(cases_directory.glob("*.json"))[:512]:
            try:
                payload = _read_json(result_path)
                case_id = str(payload["case_id"])
                if payload.get("run_attempt_id") != attempt_id or result_path.name != f"{case_id}.json":
                    continue
                locator_id = hashlib.sha256(f"{attempt_id}\0{case_id}".encode()).hexdigest()[:32]
                analysis = _read_analysis(run_directory, case_id, attempt_id)
                self._locators[locator_id] = (run_directory, result_path)
                summaries.append(
                    CompletedRunSummary(
                        locator_id=locator_id,
                        run_attempt_id=attempt_id,
                        case_id=case_id,
                        status=str(payload["status"]),
                        turns=_metric(payload, "turns"),
                        provider_input_tokens=_metric(payload, "prompt_tokens"),
                        provider_output_tokens=_metric(payload, "completion_tokens"),
                        recoveries=_metric(payload, "action_policy_recovery_calls"),
                        control_stalls=_metric(payload, "control_stall_count"),
                        state_oscillations=_metric(payload, "state_oscillation_count"),
                        detour_disposition=_detour_disposition(analysis),
                        langfuse_url=(
                            f"{self._langfuse_base_url}/sessions/{quote(attempt_id, safe='')}"
                            if self._langfuse_base_url
                            else None
                        ),
                        local_evidence_url=(
                            f"/diagnostics/evidence/{locator_id}/result"
                            if self._local_evidence_enabled
                            else None
                        ),
                    )
                )
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return tuple(summaries)


def _read_json(path: Path) -> dict[str, object]:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("evidence JSON exceeds the bounded resolver limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("evidence JSON must be an object")
    return value


def _valid_attempt_id(value: str) -> bool:
    return len(value) == 40 and value.startswith("attempt:") and all(
        character in "0123456789abcdef" for character in value[8:]
    )


def _metric(payload: Mapping[str, object], name: str) -> int:
    measurements = payload.get("measurements")
    if not isinstance(measurements, Mapping):
        return 0
    measurement = measurements.get(name)
    if not isinstance(measurement, Mapping) or measurement.get("measured") is not True:
        return 0
    value = measurement.get("value", 0)
    return max(0, int(value)) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _read_analysis(
    run_directory: Path,
    case_id: str,
    attempt_id: str,
) -> Mapping[str, object]:
    path = run_directory / "analysis" / f"{case_id}.json"
    if not path.is_file():
        return {}
    analysis = _read_json(path)
    identity = analysis.get("identity")
    if not isinstance(identity, Mapping) or identity.get("run_attempt_id") != attempt_id:
        return {}
    return analysis


def _detour_disposition(
    analysis: Mapping[str, object],
) -> Literal["suspected_detour", "not_assessed"]:
    value = analysis.get("detour_disposition")
    return "suspected_detour" if value == "suspected_detour" else "not_assessed"
