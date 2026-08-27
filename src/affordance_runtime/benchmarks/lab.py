"""Benchmark-owned launch and evidence service for the Interaction Shell Labs UI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from affordance_runtime.benchmarks.external_breadth.manifest import (
    CAMPAIGN_ID,
    build_breadth_manifest,
)
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.wire_capability import ActionPolicyWireCapability
from affordance_runtime.model.providers.capabilities import model_supports_multimodal

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_PROFILE_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_PROVIDER_PREFIXES = {
    "aliyun": "LLM_ALIYUN",
    "deepseek": "LLM_DEEPSEEK",
    "gemini": "LLM_GEMINI",
    "local": "LLM_LOCAL",
    "mistral": "LLM_MISTRAL",
    "zhipu": "LLM_ZHIPU",
}


class BenchmarkLabRunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=240)
    action_model: str = Field(min_length=1, max_length=120)
    goal_compiler_mode: Literal["model", "disabled"]
    goal_compiler_model: str = Field(default="", max_length=120)
    perception_profile: str = DecisionPerceptionProfile.STRUCTURE_FIRST.value
    profile: str = "CONSOLE_RUN"
    action_wire_capability: str = ActionPolicyWireCapability.NATIVE_SINGLE_TOOL.value

    @model_validator(mode="after")
    def validate_contract(self) -> BenchmarkLabRunSpec:
        if _MODEL_ID.fullmatch(self.action_model) is None:
            raise ValueError("action_model is invalid")
        if self.goal_compiler_mode == "model" and _MODEL_ID.fullmatch(self.goal_compiler_model) is None:
            raise ValueError("goal_compiler_model is invalid")
        if self.goal_compiler_mode == "disabled" and self.goal_compiler_model:
            raise ValueError("disabled GoalCompiler cannot select a model")
        DecisionPerceptionProfile(self.perception_profile)
        ActionPolicyWireCapability(self.action_wire_capability)
        if _PROFILE_ID.fullmatch(self.profile) is None:
            raise ValueError("profile must be an uppercase bounded identifier")
        return self


class BenchmarkLabCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    task_id: str
    seed: int
    max_turns: int
    timeout_s: float


class BenchmarkLabModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    multimodal: bool = False


class BenchmarkLabConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: str
    provider: str
    provider_ready: bool
    action_models: tuple[BenchmarkLabModel, ...]
    action_wire_capabilities: tuple[str, ...]
    goal_models: tuple[str, ...]
    perception_profiles: tuple[str, ...]
    cases: tuple[BenchmarkLabCase, ...]


class BenchmarkLabRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    status: Literal["running", "completed", "failed"]
    return_code: int | None
    started_at: str
    spec: BenchmarkLabRunSpec
    evidence_dir: str
    stdout_tail: tuple[str, ...] = ()
    report: dict[str, Any] | None = None


class BenchmarkLabEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    events: tuple[dict[str, Any], ...]
    next_cursor: int = Field(ge=0)
    run: BenchmarkLabRunSummary


class BenchmarkLabRunList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runs: tuple[BenchmarkLabRunSummary, ...]


class BenchmarkLabBrowserFrame(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    data: bytes
    media_type: str
    sha256: str
    observation_id: str

    @model_validator(mode="after")
    def validate_frame(self) -> BenchmarkLabBrowserFrame:
        if self.media_type not in _IMAGE_TYPES:
            raise ValueError("benchmark browser frame media type is unsupported")
        if not self.data or hashlib.sha256(self.data).hexdigest() != self.sha256:
            raise ValueError("benchmark browser frame digest does not match bytes")
        if not self.observation_id.strip():
            raise ValueError("benchmark browser frame requires an observation identity")
        return self


class BenchmarkLabRun:
    def __init__(
        self,
        run_id: str,
        spec: BenchmarkLabRunSpec,
        evidence_dir: Path,
        command: tuple[str, ...],
        started_at: str,
        process: subprocess.Popen[str],
    ) -> None:
        self.run_id = run_id
        self.spec = spec
        self.evidence_dir = evidence_dir
        self.command = command
        self.started_at = started_at
        self.process = process
        self.output: list[str] = []

    @property
    def status(self) -> Literal["running", "completed", "failed"]:
        code = self.process.poll()
        if code is None:
            return "running"
        return "completed" if code == 0 else "failed"

    def public_summary(self) -> BenchmarkLabRunSummary:
        report_path = self.evidence_dir / "report.json"
        report = _read_json(report_path) if report_path.is_file() else None
        return BenchmarkLabRunSummary(
            run_id=self.run_id,
            status=self.status,
            return_code=self.process.poll(),
            started_at=self.started_at,
            spec=self.spec,
            evidence_dir=str(self.evidence_dir),
            stdout_tail=tuple(self.output[-40:]),
            report=report if isinstance(report, dict) else None,
        )


class BenchmarkLabManager:
    """Own formal benchmark subprocesses and read their persisted evidence."""

    def __init__(
        self,
        evidence_root: Path,
        *,
        python_executable: str = sys.executable,
        environment: dict[str, str] | None = None,
        manifest=None,
    ) -> None:
        self.evidence_root = Path(evidence_root).resolve()
        self.python_executable = python_executable
        self.environment = dict(os.environ if environment is None else environment)
        self.manifest = manifest or build_breadth_manifest(load_registry_census())
        self._cases = {case.case_id: case for case in self.manifest.cases}
        self._runs: dict[str, BenchmarkLabRun] = {}
        self._active_id = ""
        self._lock = threading.Lock()
        self._frame_cache: dict[str, tuple[int, int, BenchmarkLabBrowserFrame | None]] = {}

    def configuration(self) -> BenchmarkLabConfiguration:
        provider = self.environment.get("LLM_ACTIVE_PROFILE", "local").strip().casefold()
        action_model = _configured_action_model(self.environment, provider)
        action_models = (action_model,) if _valid_model_id(action_model) else ()
        goal_models = _model_choices(
            action_models,
            self.environment.get("LLM_GOAL_COMPILER_MODEL", ""),
        )
        return BenchmarkLabConfiguration(
            manifest=self.manifest.campaign_id,
            provider=provider,
            provider_ready=_provider_ready(self.environment, provider),
            action_models=tuple(
                BenchmarkLabModel(
                    id=model,
                    multimodal=model_supports_multimodal(provider, model),
                )
                for model in action_models
            ),
            action_wire_capabilities=tuple(item.value for item in ActionPolicyWireCapability),
            goal_models=tuple(goal_models),
            perception_profiles=tuple(item.value for item in DecisionPerceptionProfile),
            cases=tuple(
                BenchmarkLabCase(
                    case_id=case.case_id,
                    task_id=case.task_id.removeprefix("browsergym/miniwob."),
                    seed=case.seed,
                    max_turns=case.max_turns,
                    timeout_s=case.timeout_s,
                )
                for case in self.manifest.cases
            ),
        )

    def start(self, spec: BenchmarkLabRunSpec) -> BenchmarkLabRunSummary:
        case = self._cases.get(spec.case_id)
        if case is None:
            raise ValueError("case_id is not in the frozen manifest")
        self._validate_spec(spec)
        with self._lock:
            active = self._runs.get(self._active_id)
            if active is not None and active.process.poll() is None:
                raise RuntimeError("another Labs run is active")
            run_id = _run_id(spec.case_id)
            evidence_dir = self.evidence_root / run_id
            command = (
                self.python_executable,
                "-m",
                "affordance_runtime.benchmarks.external_breadth.cli",
                "run-case",
                "--manifest",
                CAMPAIGN_ID,
                "--case-id",
                spec.case_id,
                "--profile",
                spec.profile,
                "--seed",
                str(case.seed),
                "--output-dir",
                str(evidence_dir),
            )
            process = subprocess.Popen(
                command,
                cwd=Path.cwd(),
                env=self._run_environment(spec),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            run = BenchmarkLabRun(
                run_id,
                spec,
                evidence_dir,
                command,
                datetime.now(UTC).isoformat(),
                process,
            )
            self._runs[run_id] = run
            self._active_id = run_id
            threading.Thread(target=self._drain_output, args=(run,), daemon=True).start()
            return run.public_summary()

    def get(self, run_id: str) -> BenchmarkLabRunSummary:
        return self._get_run(run_id).public_summary()

    def current(self) -> BenchmarkLabRunSummary | None:
        run = self._runs.get(self._active_id)
        return run.public_summary() if run is not None else None

    def list_runs(self) -> BenchmarkLabRunList:
        runs = sorted(self._runs.values(), key=lambda item: item.started_at, reverse=True)
        return BenchmarkLabRunList(runs=tuple(item.public_summary() for item in runs[:100]))

    def events(self, run_id: str, after: int = 0) -> BenchmarkLabEventPage:
        if after < 0:
            raise ValueError("event cursor must be nonnegative")
        run = self._get_run(run_id)
        trace_path = run.evidence_dir / "traces" / run.spec.case_id / "trace.jsonl"
        events: list[dict[str, Any]] = []
        next_cursor = after
        if trace_path.is_file():
            for index, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), start=1):
                if index <= after:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    break
                if isinstance(event, dict):
                    events.append(event)
                    next_cursor = index
        return BenchmarkLabEventPage(
            events=tuple(events),
            next_cursor=next_cursor,
            run=run.public_summary(),
        )

    def activity(self, run_id: str, after: int = 0) -> BenchmarkLabEventPage:
        payload = self.events(run_id, after)
        return payload.model_copy(update={"events": tuple(_public_activity_event(item) for item in payload.events)})

    def browser_frame(self, run_id: str) -> BenchmarkLabBrowserFrame | None:
        run = self._get_run(run_id)
        trace_path = run.evidence_dir / "traces" / run.spec.case_id / "trace.jsonl"
        try:
            stat = trace_path.stat()
        except FileNotFoundError:
            return None
        cache_key = (stat.st_mtime_ns, stat.st_size)
        cached = self._frame_cache.get(run_id)
        if cached is not None and cached[:2] == cache_key:
            return cached[2]
        frame = _latest_browser_frame(trace_path)
        self._frame_cache[run_id] = (*cache_key, frame)
        return frame

    def stop(self, run_id: str) -> BenchmarkLabRunSummary:
        run = self._get_run(run_id)
        if run.process.poll() is None:
            run.process.terminate()
        return run.public_summary()

    def _get_run(self, run_id: str) -> BenchmarkLabRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError("Labs run not found") from exc

    def _run_environment(self, spec: BenchmarkLabRunSpec) -> dict[str, str]:
        env = dict(self.environment)
        provider = env.get("LLM_ACTIVE_PROFILE", "local").strip().casefold()
        model_key = _provider_model_key(provider, env)
        env.update(
            {
                "LLM_ACTIVE_PROFILE": provider,
                model_key: spec.action_model,
                "LLM_ACTION_POLICY_WIRE_CAPABILITY": spec.action_wire_capability,
                "LLM_DECISION_PERCEPTION": spec.perception_profile,
                "LLM_GOAL_COMPILER_MODE": spec.goal_compiler_mode,
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "MINIWOB_URL": env.get("MINIWOB_URL", "http://127.0.0.1:18888/miniwob/"),
            }
        )
        if spec.goal_compiler_mode == "model":
            env["LLM_GOAL_COMPILER_MODEL"] = spec.goal_compiler_model
        else:
            env.pop("LLM_GOAL_COMPILER_MODEL", None)
        return env

    def _validate_spec(self, spec: BenchmarkLabRunSpec) -> None:
        configuration = self.configuration()
        if not configuration.provider_ready:
            raise ValueError(f"active model provider {configuration.provider!r} is not configured")
        action_models = {item.id: item for item in configuration.action_models}
        selected = action_models.get(spec.action_model)
        if selected is None:
            raise ValueError("action_model is not configured for the active provider")
        if spec.goal_compiler_mode == "model" and spec.goal_compiler_model not in configuration.goal_models:
            raise ValueError("goal_compiler_model is not configured for the active provider")
        if spec.perception_profile == DecisionPerceptionProfile.SCREENSHOT_AX.value and not selected.multimodal:
            raise ValueError("screenshot-ax perception requires a configured multimodal action model")

    @staticmethod
    def _drain_output(run: BenchmarkLabRun) -> None:
        assert run.process.stdout is not None
        for line in run.process.stdout:
            run.output.append(line.rstrip())
            if len(run.output) > 200:
                del run.output[:50]


def _model_choices(defaults: tuple[str, ...], configured: str) -> list[str]:
    values = [*defaults]
    if configured.strip() and _MODEL_ID.fullmatch(configured.strip()) and configured.strip() not in values:
        values.append(configured.strip())
    return values


def _valid_model_id(model: str) -> bool:
    return bool(model and _MODEL_ID.fullmatch(model))


def _configured_action_model(environment: dict[str, str], provider: str) -> str:
    if provider == "local":
        return (environment.get("LLM_LOCAL_MODEL_ID") or environment.get("LLM_LOCAL_MODEL") or "qwen2.5:7b").strip()
    prefix = _PROVIDER_PREFIXES.get(provider)
    return "" if prefix is None else environment.get(f"{prefix}_MODEL", "").strip()


def _provider_model_key(provider: str, environment: dict[str, str]) -> str:
    if provider == "local":
        return "LLM_LOCAL_MODEL_ID" if environment.get("LLM_LOCAL_MODEL_ID", "").strip() else "LLM_LOCAL_MODEL"
    prefix = _PROVIDER_PREFIXES.get(provider)
    if prefix is None:
        raise ValueError(f"unsupported LLM_ACTIVE_PROFILE: {provider}")
    return f"{prefix}_MODEL"


def _provider_ready(environment: dict[str, str], provider: str) -> bool:
    if provider == "local":
        return _valid_model_id(_configured_action_model(environment, provider))
    prefix = _PROVIDER_PREFIXES.get(provider)
    if prefix is None:
        return False
    return all(environment.get(f"{prefix}_{suffix}", "").strip() for suffix in ("BASE_URL", "API_KEY", "MODEL"))


def _run_id(case_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"lab-{timestamp}-{case_id}-{uuid.uuid4().hex[:6]}"


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _public_activity_event(event: dict[str, Any]) -> dict[str, Any]:
    """Expose user-legible owner facts without private World or binding payloads."""

    kind = str(event.get("event") or "trace")
    public: dict[str, Any] = {
        "event": kind,
        "sequence": int(event.get("sequence") or 0),
    }
    if kind == "run_started":
        task = event.get("task") if isinstance(event.get("task"), dict) else {}
        public.update(
            instruction=str(task.get("instruction") or ""),
            initial_status=str(event.get("initial_status") or "running"),
            max_steps=int(event.get("max_steps") or 0),
        )
    elif kind == "goal_compiler_completed":
        diagnostic = event.get("diagnostic") if isinstance(event.get("diagnostic"), dict) else {}
        public.update(
            disposition=str(diagnostic.get("final_disposition") or "unknown"),
            provider_attempt_count=int(diagnostic.get("provider_attempt_count") or 0),
        )
    elif kind == "model_turn":
        attempts = event.get("generation_attempts") if isinstance(event.get("generation_attempts"), list) else []
        public.update(
            outcome=str(event.get("outcome") or "unknown"),
            attempt_count=len(attempts),
            latency_ms=round(
                sum(float(item.get("latency_ms") or 0) for item in attempts if isinstance(item, dict)),
                3,
            ),
        )
    elif kind == "step_completed":
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        execution = result.get("execution") if isinstance(result.get("execution"), dict) else None
        request = (
            execution.get("request")
            if isinstance(execution, dict) and isinstance(execution.get("request"), dict)
            else {}
        )
        intent = request.get("intent") if isinstance(request.get("intent"), dict) else {}
        receipt = (
            execution.get("result") if isinstance(execution, dict) and isinstance(execution.get("result"), dict) else {}
        )
        evaluation = result.get("task_evaluation") if isinstance(result.get("task_evaluation"), dict) else {}
        public.update(
            step=int(event.get("step") or 0),
            status_after=str(result.get("status_after") or "running"),
            feedback=str(result.get("feedback") or ""),
            semantic_action=str(intent.get("semantic_action") or ""),
            dispatch_status=str(receipt.get("dispatch_status") or ""),
            execution_completed=execution is not None,
            evaluation_status=str(evaluation.get("status") or ""),
        )
    elif kind == "observation":
        public.update(
            observation_id=str(event.get("observation_id") or ""),
            browser_frame_available=bool(_observation_screenshot_media(event)),
        )
    elif kind == "run_finished":
        public.update(
            status=str(event.get("status") or "failed"),
            step_count=int(event.get("step_count") or 0),
            observation_count=int(event.get("observation_count") or 0),
            execution_count=int(event.get("execution_count") or 0),
        )
    elif kind == "run_paused":
        public["status"] = str(event.get("status") or "waiting_user")
    elif kind == "run_error":
        public["exception_class"] = str(event.get("exception_class") or "RuntimeError")
    return public


def _latest_browser_frame(trace_path: Path) -> BenchmarkLabBrowserFrame | None:
    trace_root = trace_path.parent.resolve()
    latest: BenchmarkLabBrowserFrame | None = None
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            break
        if event.get("event") != "observation":
            continue
        for media in _observation_screenshot_media(event):
            data_value = media.get("data")
            artifact = data_value.get("artifact", {}) if isinstance(data_value, dict) else {}
            relative = artifact.get("path") if isinstance(artifact, dict) else None
            digest = str(media.get("sha256") or artifact.get("sha256") or "")
            if not isinstance(relative, str) or not relative or not digest:
                continue
            candidate = (trace_root / relative).resolve()
            if not candidate.is_relative_to(trace_root) or not candidate.is_file():
                continue
            try:
                latest = BenchmarkLabBrowserFrame(
                    data=candidate.read_bytes(),
                    media_type=str(media["mime_type"]),
                    sha256=digest,
                    observation_id=str(event.get("observation_id") or ""),
                )
            except (OSError, TypeError, ValueError):
                continue
    return latest


def _observation_screenshot_media(event: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Read screenshot media from the trace's authoritative World observation."""

    observation = event.get("observation")
    if not isinstance(observation, dict) or not isinstance(observation.get("media"), list):
        return ()
    screenshots: list[dict[str, Any]] = []
    for item in observation["media"]:
        media = item.get("media") if isinstance(item, dict) else None
        if isinstance(media, dict) and media.get("kind") == "screenshot" and media.get("mime_type") in _IMAGE_TYPES:
            screenshots.append(media)
    return tuple(screenshots)
