"""Official WebArena-Verified intake, STOP-gated native evaluation, and diagnostics."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.agent.context.budgets import serialized_size
from affordance_runtime.agent.context.compact_world_renderer import render_compact_actor_world
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.benchmarks.browsergym_runtime import (
    DEFAULT_BROWSERGYM_RUNTIME_PYTHON,
)
from affordance_runtime.evaluation import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_policy_context import GroundedPolicyContextBinder
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolPhase,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.request_admission import ModelRequestCapacityError
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.surfaces.browsergym.environment import BrowserGymSurfaceAdapter
from affordance_runtime.surfaces.browsergym.interaction_profile import BROWSERGYM_INTERACTION_PROFILE
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
    BrowserGymTaskStateSnapshot,
)
from affordance_runtime.task import (
    LoopBudget,
    NaturalLanguageTaskRequest,
    ReadyTask,
    RiskProfile,
    TaskBoundary,
    TaskGoal,
    ThinTaskIntake,
)
from affordance_runtime.world.acquisition import AcquisitionStatus
from affordance_runtime.world.evidence_refs import canonical_artifact_ref
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

WA_BROWSERGYM_COMMIT = "9e779f087de9a65668b6974d11f9ce9816026e96"
WA_VERIFIED_COMMIT = "6473f72db5dcefc97b5725b59e734504edc28a21"
WA_HARD_SUBSET_SHA256 = "d20872f9894e4e8ffc250155fe0ad5c797c640f40d3094404654a8b1dab14e68"
WA_SELECTION_SEED = 20260818
WA_DEFAULT_TIMEOUT_S = 0.0
WA_REGISTRATION_MODULE = "browsergym.webarena_verified"
WA_FINAL_OUTPUT_ID = "webarena_final_response"
WA_SCHEMA_W0 = "webarena-verified-w0-readiness.v1"
WA_SCHEMA_W1B_WORLD = "webarena-verified-w1b-world.v1"
WA_MANIFEST_SCHEMA = "webarena-verified-target-loop-manifest.v1"
_W1B_PRIVATE_MARKERS = (
    "browsergym_id",
    "private_bid",
    "private_element_id",
    "selector",
    "xpath",
    "coordinate:",
    "bbox",
    "expected_answer",
    "target_answer",
    "raw_reward",
    "reward",
    "benchmark_oracle",
)

@dataclass(frozen=True)
class WebArenaVerifiedCaseRef:
    task_id: int
    intent_template_id: int
    revision: int
    sites: tuple[str, ...]
    task_type: str
    cohort: str

    @property
    def gym_id(self) -> str:
        return webarena_gym_task_id(self)

    def public_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["gym_id"] = self.gym_id
        payload["public_intent_digest"] = ""
        return payload


WA_W1_SMOKE_CASES: tuple[WebArenaVerifiedCaseRef, ...] = (
    WebArenaVerifiedCaseRef(0, 279, 2, ("shopping_admin",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(7, 79, 2, ("map",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(21, 222, 2, ("shopping",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(27, 33, 2, ("reddit",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(44, 303, 2, ("gitlab",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(266, 85, 4, ("wikipedia", "map"), "smoke", "w1"),
)

WA_W2_COHORT_CASES: tuple[WebArenaVerifiedCaseRef, ...] = (
    WebArenaVerifiedCaseRef(267, 85, 4, ("wikipedia", "map"), "retrieve", "w2"),
    WebArenaVerifiedCaseRef(97, 120, 2, ("map", "wikipedia"), "retrieve", "w2"),
    WebArenaVerifiedCaseRef(265, 85, 4, ("wikipedia", "map"), "retrieve", "w2"),
    WebArenaVerifiedCaseRef(268, 85, 4, ("wikipedia", "map"), "retrieve", "w2"),
    WebArenaVerifiedCaseRef(740, 94, 2, ("wikipedia", "map"), "navigate", "w2"),
    WebArenaVerifiedCaseRef(759, 42, 2, ("map", "shopping_admin"), "navigate", "w2"),
    WebArenaVerifiedCaseRef(424, 371, 2, ("wikipedia", "map"), "navigate", "w2"),
    WebArenaVerifiedCaseRef(426, 371, 2, ("wikipedia", "map"), "navigate", "w2"),
    WebArenaVerifiedCaseRef(681, 116, 2, ("reddit", "gitlab"), "mutate", "w2"),
    WebArenaVerifiedCaseRef(672, 101, 2, ("shopping", "reddit"), "mutate", "w2"),
    WebArenaVerifiedCaseRef(556, 87, 3, ("gitlab", "wikipedia"), "mutate", "w2"),
    WebArenaVerifiedCaseRef(554, 84, 2, ("gitlab", "reddit"), "mutate", "w2"),
)

WA_W0_REQUIRED_CASES: tuple[WebArenaVerifiedCaseRef, ...] = (*WA_W1_SMOKE_CASES, *WA_W2_COHORT_CASES)

_W0_PREFLIGHT_PROGRAM = r"""
import importlib
import importlib.metadata as metadata
import json
import os
import sys
import time
import urllib.error
import urllib.request

payload = json.loads(sys.stdin.read())
task_ids = tuple(payload["task_ids"])
probe_task_id = payload["probe_task_id"]
exercise = bool(payload["exercise"])

def package(name):
    try:
        version = metadata.version(name)
    except metadata.PackageNotFoundError:
        return {"installed": False, "version": "", "direct_url": {}}
    direct = {}
    try:
        dist = metadata.distribution(name)
        text = dist.read_text("direct_url.json")
        direct = json.loads(text) if text else {}
    except Exception:
        direct = {}
    return {"installed": True, "version": version, "direct_url": direct}

def redacted_url(value):
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(value)
    host = parts.hostname or ""
    if not host:
        return value
    netloc = host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/") + "/", "", ""))

def health(url):
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            return {"status": "ok", "http_status": int(response.status), "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except urllib.error.HTTPError as exc:
        return {"status": "http_error", "http_status": int(exc.code), "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        return {"status": "failed", "error": type(exc).__name__, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}

report = {
    "sys_executable": sys.executable,
    "python_version": ".".join(str(part) for part in sys.version_info[:3]),
    "packages": {
        "playwright": package("playwright"),
        "browsergym-miniwob": package("browsergym-miniwob"),
        "browsergym-webarena": package("browsergym-webarena"),
        "browsergym-webarena-verified": package("browsergym-webarena-verified"),
        "nltk": package("nltk"),
        "webarena-verified": package("webarena-verified"),
    },
    "registration": {"imported": False, "missing_task_ids": list(task_ids), "registered_task_ids": []},
    "sites": [],
    "exercise": {"attempted": exercise, "reset": "not_attempted", "evaluator": "not_attempted"},
}

try:
    importlib.import_module("browsergym.webarena_verified")
    import gymnasium as gym
    registry = {str(key) for key in gym.envs.registry.keys()}
    registered = sorted(task_id for task_id in task_ids if task_id in registry)
    report["registration"] = {
        "imported": True,
        "missing_task_ids": sorted(set(task_ids) - set(registered)),
        "registered_task_ids": registered,
    }
except Exception as exc:
    report["registration"]["error"] = type(exc).__name__

for key in sorted(os.environ):
    if not key.startswith("WA_"):
        continue
    upper = key.upper()
    if any(secret in upper for secret in ("KEY", "TOKEN", "SECRET", "PASSWORD", "HEADER", "COOKIE")):
        continue
    value = os.environ[key].strip()
    if not value:
        continue
    item = {"env": key, "value_sha256": "sha256:" + __import__("hashlib").sha256(value.encode()).hexdigest()}
    if value.startswith(("http://", "https://")):
        item["redacted_url"] = redacted_url(value)
        item["health"] = health(value)
    elif "DIGEST" in upper or value.startswith("sha256:"):
        item["image_digest"] = value
    report["sites"].append(item)

if exercise and not report["registration"]["missing_task_ids"]:
    try:
        import gymnasium as gym
        env = gym.make(probe_task_id, headless=True, tags_to_mark="all")
        try:
            obs, info = env.reset(seed=payload["seed"])
            report["exercise"]["reset"] = {
                "status": "ok",
                "goal_present": isinstance(obs, dict) and isinstance(obs.get("goal"), str) and bool(obs.get("goal", "").strip()),
                "info_keys": sorted(str(key) for key in info.keys()) if isinstance(info, dict) else [],
            }
            obs, reward, terminated, truncated, info = env.step('send_msg_to_user("W0 readiness probe")')
            report["exercise"]["evaluator"] = {
                "status": "ok",
                "terminated": terminated is True,
                "truncated": truncated is True,
                "reward_type": type(reward).__name__,
                "info_keys": sorted(str(key) for key in info.keys()) if isinstance(info, dict) else [],
            }
        finally:
            env.close()
    except Exception as exc:
        if report["exercise"]["reset"] == "not_attempted":
            report["exercise"]["reset"] = {"status": "failed", "error": type(exc).__name__}
        else:
            report["exercise"]["evaluator"] = {"status": "failed", "error": type(exc).__name__}

print(json.dumps(report, sort_keys=True))
"""


def webarena_gym_task_id(task: WebArenaVerifiedCaseRef | WebArenaVerifiedTaskRef) -> str:
    return f"browsergym/webarena_verified.{task.intent_template_id}.{task.task_id}.{task.revision}"


@dataclass
class WebArenaVerifiedCaseEnvironment:
    """Official BrowserGym WebArena-Verified case facade."""

    case_ref: WebArenaVerifiedCaseRef
    surface: BrowserGymSurfaceAdapter
    world: UnifiedWorldEnvironment
    adapter_task: TaskGoal
    native_evaluator_queries: int = 0
    final_delivery_attempted: bool = False
    final_delivery_confirmed: bool = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.surface, name)

    @property
    def observation_capabilities(self):
        return self.world.observation_capabilities

    @property
    def supports_finalization(self) -> bool:
        return self.world.supports_finalization

    async def reset(self, task):
        _ensure_public_task(task, self.adapter_task)
        return await self.world.reset(self.adapter_task)

    async def revise_task(self, task):
        _ensure_public_task(task, self.adapter_task)
        return await self.world.revise_task(self.adapter_task)

    async def capture(self, request):
        return await self.world.capture(request)

    async def execute(self, request):
        return await self.world.execute(request)

    async def finalize(self, content: str):
        self.final_delivery_attempted = True
        result = await self.world.finalize(content)
        if result.result.dispatch_status is DispatchStatus.SENT:
            self.final_delivery_confirmed = True
        return result

    def is_current(self, request):
        return self.world.is_current(request)

    async def close(self) -> None:
        await self.surface.close()

    def current_native_result(self) -> tuple[TaskOutcomeKind, str, tuple[str, ...]]:
        self.native_evaluator_queries += 1
        if not self.final_delivery_confirmed:
            return TaskOutcomeKind.RUNNING_INCOMPLETE, "stop_not_confirmed", ()
        return classify_webarena_terminal_snapshot(self.surface.current_task_state())


@dataclass(frozen=True)
class WebArenaVerifiedNativeEvaluator:
    """Map the official BrowserGym terminal state into TaskEvaluation."""

    environment: WebArenaVerifiedCaseEnvironment

    async def evaluate(self, task, observation) -> TaskEvaluation:
        outcome_kind, code, refs = self.environment.current_native_result()
        evidence_index = WorldEvidenceIndex.from_observation(observation)
        if refs and not all(evidence_index.resolve_record(ref) is not None for ref in refs):
            outcome_kind, code, refs = (
                TaskOutcomeKind.VERIFIER_UNAVAILABLE,
                "source_insufficient",
                (),
            )
        status = {
            TaskOutcomeKind.TERMINAL_SUCCESS: TaskEvaluationStatus.COMPLETE,
            TaskOutcomeKind.TERMINAL_FAILURE: TaskEvaluationStatus.BLOCKED,
            TaskOutcomeKind.RUNNING_INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
            TaskOutcomeKind.VERIFIER_UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
        }[outcome_kind]
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            f"webarena-verified native evaluator: {code}",
            completion_evidence_refs=refs if outcome_kind is TaskOutcomeKind.TERMINAL_SUCCESS else (),
            outcome=TaskOutcomeFact(outcome_kind, code, refs),
        )


def open_webarena_verified_case(
    case_ref: WebArenaVerifiedCaseRef,
    seed: int = WA_SELECTION_SEED,
    *,
    gym_factory: Any | None = None,
    max_turns: int = 100,
) -> tuple[WebArenaVerifiedCaseEnvironment, TaskGoal, WebArenaVerifiedNativeEvaluator]:
    """Open one official case using only public BrowserGym task intake."""

    if case_ref not in WA_W0_REQUIRED_CASES:
        raise ValueError("WebArena-Verified case is outside the reviewed W1/W2 manifest")
    surface = BrowserGymSurfaceAdapter.open(
        case_ref.gym_id,
        seed,
        gym_factory=gym_factory,
        registration_modules=(WA_REGISTRATION_MODULE,),
    )
    try:
        public_instruction, final_response_contract = _public_webarena_goal(surface.goal_instruction)
        intake = ThinTaskIntake().compile(
            NaturalLanguageTaskRequest(
                "task:webarena_verified",
                public_instruction,
                TaskBoundary(
                    allowed_effects=("external_ui_interaction",),
                    forbidden_effects=("credential_use",),
                    constraints=(
                        "Provide exactly one final response matching the public task format when ready.",
                    ),
                    inputs=(
                        {PUBLIC_FINAL_RESPONSE_CONTRACT_KEY: final_response_contract}
                        if final_response_contract
                        else {}
                    ),
                    requested_outputs=(WA_FINAL_OUTPUT_ID,),
                    risk_profile=RiskProfile.LOW,
                    loop_budget=LoopBudget(max_turns=max_turns, max_observations=max_turns * 2),
                ),
                source_ref=f"browsergym:{case_ref.gym_id}:goal",
            )
        )
        if not isinstance(intake, ReadyTask):
            raise RuntimeError(f"WebArena task intake rejected public profile: {intake.status.value}")
        environment = WebArenaVerifiedCaseEnvironment(
            case_ref,
            surface,
            UnifiedWorldEnvironment((surface,)),
            replace(intake.task, instruction=surface.goal_instruction),
        )
        return environment, intake.task, WebArenaVerifiedNativeEvaluator(environment)
    except BaseException:
        surface.gym_environment.close()
        raise


def _ensure_public_task(task: TaskGoal, adapter_task: TaskGoal) -> None:
    if task.task_id != adapter_task.task_id or task.revision != adapter_task.revision:
        raise ValueError("WebArena public task identity must match the adapter task")


def classify_webarena_terminal_snapshot(
    snapshot: BrowserGymTaskStateSnapshot,
) -> tuple[TaskOutcomeKind, str, tuple[str, ...]]:
    terminal = snapshot.value("terminated", False) is True or snapshot.value("truncated", False) is True
    reward = snapshot.value("reward", None)
    raw_reward = snapshot.value("raw_reward", None)
    done = snapshot.value("done", None)
    if not terminal and done is not True:
        return TaskOutcomeKind.RUNNING_INCOMPLETE, "verified_running", ()
    score = reward if type(reward) in {int, float} else raw_reward
    refs = (canonical_artifact_ref(snapshot.source_observation_id, BROWSERGYM_TASK_STATE_EVIDENCE_KEY),)
    if type(score) in {int, float} and score > 0:
        return TaskOutcomeKind.TERMINAL_SUCCESS, "verified_success", refs
    if type(score) in {int, float}:
        return TaskOutcomeKind.TERMINAL_FAILURE, "verified_terminal_task_failure", refs
    return TaskOutcomeKind.VERIFIER_UNAVAILABLE, "missing_terminal_score", ()


def _public_webarena_instruction(goal: str) -> str:
    return _public_webarena_goal(goal)[0]


def _public_webarena_goal(goal: str) -> tuple[str, dict[str, object]]:
    for marker in ("\n\n---\nFinal response format:", "\n---\nFinal response format:"):
        if marker in goal:
            instruction, format_text = goal.split(marker, 1)
            contract = _public_final_response_contract(format_text)
            return instruction.strip(), contract
    return goal.strip(), {}


def _public_final_response_contract(format_text: str) -> dict[str, object]:
    text = format_text.strip()
    if not text:
        return {}
    contract: dict[str, object] = {"format": text[:4096]}
    schema = _extract_json_object(text)
    if isinstance(schema, Mapping):
        contract["json_schema"] = to_json_compatible(schema)
    return contract


def _extract_json_object(text: str) -> object | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    return None


def write_webarena_verified_w0_manifest(
    output_path: Path,
    *,
    timeout_s: float = WA_DEFAULT_TIMEOUT_S,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write the frozen W0/W1/W2 public identity manifest without private evaluator data."""

    env = os.environ if environment is None else environment
    manifest = {
        "schema_version": WA_MANIFEST_SCHEMA,
        "stage": "w0",
        "browsergym_commit": WA_BROWSERGYM_COMMIT,
        "webarena_verified_commit": WA_VERIFIED_COMMIT,
        "hard_subset_sha256": f"sha256:{WA_HARD_SUBSET_SHA256}",
        "selection_seed": WA_SELECTION_SEED,
        "case_timeout_s": timeout_s,
        "timeout_frozen": timeout_s > 0,
        "final_output_id": WA_FINAL_OUTPUT_ID,
        "registration_module": WA_REGISTRATION_MODULE,
        "smoke_cases": [case.public_payload() for case in WA_W1_SMOKE_CASES],
        "proof_cohort_cases": [case.public_payload() for case in WA_W2_COHORT_CASES],
        "configured_sites": _site_config_from_environment(env),
        "site_environment_frozen": _site_environment_frozen(env),
        "official_expected_values_included": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def inspect_webarena_verified_w0_readiness(
    *,
    runtime_python: Path = DEFAULT_BROWSERGYM_RUNTIME_PYTHON,
    output_path: Path | None = None,
    environment: Mapping[str, str] | None = None,
    exercise_environment: bool = True,
) -> dict[str, Any]:
    """Inspect official package/site/reset/evaluator readiness in the BrowserGym runtime."""

    env = dict(os.environ if environment is None else environment)
    program_input = {
        "task_ids": [case.gym_id for case in WA_W0_REQUIRED_CASES],
        "probe_task_id": WA_W1_SMOKE_CASES[0].gym_id,
        "seed": WA_SELECTION_SEED,
        "exercise": exercise_environment,
    }
    completed = subprocess.run(
        [str(runtime_python), "-c", _W0_PREFLIGHT_PROGRAM],
        input=json.dumps(program_input),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        payload: dict[str, Any] = {
            "subprocess_returncode": completed.returncode,
            "stderr_digest": f"sha256:{hashlib.sha256(completed.stderr.encode()).hexdigest()}",
        }
    else:
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {"invalid_stdout_digest": f"sha256:{hashlib.sha256(completed.stdout.encode()).hexdigest()}"}
    report = _w0_report(payload, runtime_python=runtime_python)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


async def inspect_webarena_verified_w1b_world(
    output_dir: Path,
    *,
    seed: int = WA_SELECTION_SEED,
) -> dict[str, Any]:
    """Persist the read-only W1b-World gate using the production context chain."""

    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    for case_ref in WA_W1_SMOKE_CASES:
        report = await _inspect_w1b_world_case(case_ref, seed=seed)
        cases.append(report)
        case_path = output_dir / f"w1b-world-task-{case_ref.task_id}.json"
        case_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "schema_version": WA_SCHEMA_W1B_WORLD,
        "stage": "w1b-world",
        "selection_seed": seed,
        "case_count": len(cases),
        "ready": all(item.get("status") == "ok" and not item.get("acceptance_errors") for item in cases),
        "failure_origin": "none" if all(item.get("status") == "ok" for item in cases) else "environment_or_projection",
        "acceptance_errors": tuple(
            error
            for case in cases
            for error in case.get("acceptance_errors", ())
        ),
        "cases": cases,
    }
    (output_dir / "w1b-world-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


async def _inspect_w1b_world_case(case_ref: WebArenaVerifiedCaseRef, *, seed: int) -> dict[str, Any]:
    environment: WebArenaVerifiedCaseEnvironment | None = None
    try:
        environment, task, _evaluator = open_webarena_verified_case(case_ref, seed=seed)
        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return _w1b_world_failure(
                case_ref,
                "environment",
                "initial_observation_unavailable",
                {
                    "acquisition_status": acquisition.status.value,
                    "reason_code": acquisition.reason_code,
                    "stage": acquisition.stage.value,
                },
            )
        observation = acquisition.observation
        action_space = ActionSpaceBuilder().build(task, observation)
        evaluation = TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "w1b-world read-only diagnostic",
        )
        context = ContextBuilder().build(
            task,
            observation,
            action_space,
            evaluation,
            observation_capabilities=environment.observation_capabilities,
            runtime_controls=("yield_subtask",),
        )
        catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
        request_budget = _w1b_request_budget(context, catalog)
        rendered = render_compact_actor_world(
            context.actor_world,
            context.grounding,
            include_images=False,
        )
        return _w1b_world_success(case_ref, environment, task, observation, action_space, context, catalog, rendered, request_budget)
    except Exception as exc:
        return _w1b_world_failure(
            case_ref,
            "environment" if environment is None else "projection",
            "w1b_world_diagnostic_failed",
            {
                "exception_class": type(exc).__name__,
                "message_digest": f"sha256:{hashlib.sha256(str(exc).encode()).hexdigest()}",
            },
        )
    finally:
        if environment is not None:
            try:
                await environment.close()
            except Exception:
                pass


def _w1b_world_success(
    case_ref: WebArenaVerifiedCaseRef,
    environment: WebArenaVerifiedCaseEnvironment,
    task: TaskGoal,
    observation,
    action_space,
    context,
    catalog,
    rendered: str,
    request_budget: Mapping[str, object],
) -> dict[str, Any]:
    source_counts = _source_counts(observation)
    actor_refs, actor_paths = _actor_ref_index(context.actor_world)
    tool_refs = _tool_schema_refs(catalog)
    option_refs = _action_option_refs(context)
    missing_tool_refs = tuple(sorted(set(tool_refs) - set(actor_refs)))
    state_metrics = _action_state_metrics(context, actor_refs)
    closure_violations = _structural_closure_violations(context.actor_world, actor_paths)
    leak_markers = _private_leak_markers(rendered, catalog)
    find_actions_offered = "find_actions" in {item.name for item in catalog.specs}
    recoverability = _recoverability_diagnostic(
        environment,
        task,
        observation,
        action_space,
        context,
        catalog,
    )
    acceptance_errors = []
    if missing_tool_refs:
        acceptance_errors.append(f"tool_targets_missing_from_actor:{len(missing_tool_refs)}")
    if state_metrics["verb_mismatch_count"]:
        acceptance_errors.append(f"verb_state_mismatch:{state_metrics['verb_mismatch_count']}")
    if closure_violations:
        acceptance_errors.append(f"structural_closure_violations:{len(closure_violations)}")
    if leak_markers:
        acceptance_errors.append(f"private_model_input_leaks:{len(leak_markers)}")
    if context.actions.has_more and not find_actions_offered:
        acceptance_errors.append("partial_action_inventory_without_find_actions")
    acceptance_errors.extend(recoverability["acceptance_errors"])
    return {
        "schema_version": WA_SCHEMA_W1B_WORLD,
        "status": "ok",
        "acceptance_errors": tuple(acceptance_errors),
        "case": case_ref.public_payload(),
        "source": {
            **source_counts,
            "browsergym_diagnostic": environment.surface.diagnostic_snapshot().as_metrics(),
        },
        "world": {
            "target_count": len(observation.targets),
            "fact_count": len(observation.facts),
            "binding_count": len(observation.bindings),
            "source_count": len(observation.sources),
            "semantic_digest": _semantic_world_digest(observation),
            "serialized_bytes": _diagnostic_json_size(observation),
        },
        "actor": {
            "document_count": len(context.actor_world.documents),
            "retained_node_count": sum(item.retained_node_count for item in context.actor_world.documents),
            "total_node_count": sum(item.total_node_count for item in context.actor_world.documents),
            "source_coverage": tuple(to_json_compatible(item) for item in context.actor_world.sources),
            "serialized_bytes": serialized_size(context.actor_world),
            "rendered_bytes": len(rendered.encode()),
            "rendered_token_estimate": max(1, math.ceil(len(rendered) / 4)),
        },
        "tools": {
            "offered_tool_target_count": len(tool_refs),
            "offered_action_ref_count": len(option_refs),
            "actor_missing_offered_targets": missing_tool_refs,
            "catalog_tool_count": len(catalog.specs),
            "catalog_serialized_bytes": catalog.serialized_bytes,
            "find_actions_offered": find_actions_offered,
        },
        "action_inventory": {
            "visible_count": context.actions.page_size,
            "total_count": context.actions.total_count,
            "partial": context.actions.has_more,
            "recovery": "find_actions" if context.actions.has_more else "not_required",
        },
        "capability_census": _capability_census(context, catalog),
        "decision_state": state_metrics,
        "structural_closure": {
            "violation_count": len(closure_violations),
            "violations": closure_violations[:32],
        },
        "presentation_collapse": _collapsed_presentation_counts(context.actor_world),
        "private_isolation": {
            "leak_count": len(leak_markers),
            "markers": leak_markers,
        },
        "recoverability": recoverability,
        "perception_route": {
            "profile": "TEXT_ONLY",
            "image_attached": False,
            "reason": "w1b-world read-only structured diagnostic",
        },
        "request_budget": dict(request_budget),
    }


def _w1b_request_budget(context, catalog) -> dict[str, object]:
    binder = GroundedPolicyContextBinder()
    request = ModelDecisionRequest(
        request_id=f"diagnostic:{context.context_id}",
        agent_context=context,
    )
    try:
        admitted = binder.action_request(
            request,
            catalog.specs,
            supports_multimodal=False,
            perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
            include_tool_menu=False,
        )
        return admitted.breakdown.as_diagnostics()
    except ModelRequestCapacityError as exc:
        return exc.breakdown.as_diagnostics()


def _recoverability_diagnostic(
    environment: WebArenaVerifiedCaseEnvironment,
    task: TaskGoal,
    observation,
    action_space,
    context,
    catalog,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, object] = {}
    semantic_before = _semantic_world_digest(observation)
    browsergym_before = environment.surface.diagnostic_snapshot().as_metrics()
    region_index = context.region_index
    if region_index is None or not region_index.regions:
        return {
            "status": "failed",
            "acceptance_errors": ("recoverability:no_region_index",),
            "checks": {"region_index": False},
        }
    target_by_id = {item.target_id: item for item in observation.targets}
    option_by_target = {item.target_id: item for item in action_space.options}
    sample_region = next(
        (
            region
            for region in region_index.regions
            if any(target_id in option_by_target for target_id in region.member_target_ids)
        ),
        next((region for region in region_index.regions if region.member_target_ids), region_index.regions[0]),
    )
    sample_target_id = next(
        (target_id for target_id in sample_region.member_target_ids if target_id in option_by_target),
        "",
    ) or next(
        (target_id for target_id in sample_region.member_target_ids if target_id in target_by_id),
        "",
    )
    sample_target = target_by_id.get(sample_target_id)
    query = _recoverability_query(sample_region, sample_target, observation)
    try:
        opened = resolve_grounded_tool_call(
            catalog,
            ToolCall(
                "inspect_world",
                {"action": "open_region", "region_ref": sample_region.public_ref},
                "recoverability:open",
            ),
            expected_context_id=context.context_id,
            expected_catalog_id=catalog.catalog_id,
        ).decision
        open_content = str(opened.result.get("content", ""))
        checks["open_region"] = bool(open_content.strip())
        if not checks["open_region"]:
            errors.append("recoverability:open_region_empty")
        if sample_target is not None and sample_target.label and sample_target.label not in open_content:
            errors.append("recoverability:open_region_missing_target_label")
        lens = getattr(opened, "delivery_lens", None)
        checks["lens_effect"] = bool(lens and lens.selected_region_key == sample_region.key)
        if not checks["lens_effect"]:
            errors.append("recoverability:open_region_missing_lens_effect")
    except Exception as exc:
        return _recoverability_failure("open_region", exc)
    if query:
        try:
            found = resolve_grounded_tool_call(
                catalog,
                ToolCall("inspect_world", {"action": "find", "query": query}, "recoverability:find"),
                expected_context_id=context.context_id,
                expected_catalog_id=catalog.catalog_id,
            ).decision
            matches = tuple(found.result.get("matches", ()))
            checks["find"] = bool(matches)
            if not matches:
                errors.append("recoverability:find_no_match")
            elif not any(item.get("region_ref") == sample_region.public_ref for item in matches if isinstance(item, Mapping)):
                errors.append("recoverability:find_wrong_region")
        except Exception as exc:
            return _recoverability_failure("find", exc)
    try:
        viewed = resolve_grounded_tool_call(
            catalog,
            ToolCall("inspect_world", {"action": "view_all"}, "recoverability:view_all"),
            expected_context_id=context.context_id,
            expected_catalog_id=catalog.catalog_id,
        ).decision
        page = viewed.result.get("page", {})
        regions = tuple(viewed.result.get("regions", ()))
        checks["view_all"] = any(
            isinstance(item, Mapping) and item.get("region_ref") == sample_region.public_ref
            for item in regions
        ) or bool(page.get("has_more"))
        if not checks["view_all"]:
            errors.append("recoverability:view_all_missing_regions")
        if page.get("has_more"):
            cursor = str(page.get("next_cursor", ""))
            continued = resolve_grounded_tool_call(
                catalog,
                ToolCall("inspect_world", {"action": "view_all", "cursor": cursor}, "recoverability:view_all:2"),
                expected_context_id=context.context_id,
                expected_catalog_id=catalog.catalog_id,
            ).decision
            checks["cursor"] = bool(continued.result.get("regions", ()))
            if not checks["cursor"]:
                errors.append("recoverability:view_all_cursor_empty")
        else:
            checks["cursor"] = True
    except Exception as exc:
        return _recoverability_failure("view_all", exc)
    if lens is not None and sample_target_id:
        try:
            builder = ContextBuilder()
            page = builder.page_for_delivery_lens(action_space, observation, lens, region_index)
            next_context = builder.build(
                task,
                observation,
                action_space,
                TaskEvaluation(
                    task.task_id,
                    observation.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "w1b-world recoverability rerender",
                ),
                action_page=page,
                delivery_lens=lens,
                region_index=region_index,
            )
            next_catalog = compile_grounded_tool_catalog(next_context, GroundedToolPhase.ACTION_SELECTION)
            rendered = render_compact_actor_world(
                next_context.actor_world,
                next_context.grounding,
                include_images=False,
                region_index=next_context.region_index,
                observation=next_context.current_observation,
                selected_region_keys=frozenset({lens.selected_region_key}),
                selected_cursor=lens.cursor,
                max_rendered_bytes=1,
            )
            action_target_id = next(
                (
                    option.target_id
                    for option in next_context.actions.options
                    if option.target_id in sample_region.member_target_ids
                ),
                sample_target_id,
            )
            current_ref = next_context.grounding.target_refs.get(action_target_id, "")
            checks["expanded_current_ref"] = bool(current_ref and f"[{current_ref}]" in rendered)
            if not checks["expanded_current_ref"]:
                errors.append("recoverability:expanded_region_missing_current_ref")
            checks["expanded_tool_target"] = any(
                option.target_id == action_target_id and option.target_ref == current_ref
                for option in next_context.actions.options
            ) and _catalog_has_action_tool(next_catalog)
            if not checks["expanded_tool_target"]:
                errors.append("recoverability:expanded_region_missing_tool_target")
        except Exception as exc:
            return _recoverability_failure("lens_rerender", exc)
    try:
        resolve_grounded_tool_call(
            catalog,
            ToolCall(
                "inspect_world",
                {"action": "open_region", "region_ref": sample_region.public_ref},
                "recoverability:stale",
            ),
            expected_context_id="context:" + "0" * 64,
            expected_catalog_id=catalog.catalog_id,
        )
        errors.append("recoverability:stale_context_not_rejected")
        checks["stale_context"] = False
    except GroundedToolResolutionError:
        checks["stale_context"] = True
    browsergym_after = environment.surface.diagnostic_snapshot().as_metrics()
    checks["semantic_digest_unchanged"] = semantic_before == _semantic_world_digest(observation)
    checks["zero_dispatch_metrics_unchanged"] = browsergym_before == browsergym_after
    if not checks["semantic_digest_unchanged"]:
        errors.append("recoverability:world_digest_changed")
    if not checks["zero_dispatch_metrics_unchanged"]:
        errors.append("recoverability:browsergym_metrics_changed")
    return {
        "status": "ok" if not errors else "failed",
        "acceptance_errors": tuple(errors),
        "sample": {
            "region_ref": sample_region.public_ref,
            "target_id_digest": _digest_public_id(sample_target_id),
            "query": query,
        },
        "checks": checks,
    }


def _recoverability_failure(stage: str, exc: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "acceptance_errors": (f"recoverability:{stage}_failed",),
        "checks": {stage: False},
        "failure": {
            "exception_class": type(exc).__name__,
            "message_digest": f"sha256:{hashlib.sha256(str(exc).encode()).hexdigest()}",
        },
    }


def _recoverability_query(region, target, observation) -> str:
    if target is not None and target.label.strip():
        return target.label.strip()[:120]
    for fact in observation.facts:
        if fact.fact_id in region.member_fact_ids:
            return str(fact.value)[:120]
    return region.heading[:120]


def _catalog_has_action_tool(catalog) -> bool:
    local_tools = {
        "inspect_world",
        "find_actions",
        "request_evidence",
        "count_" + "children",
        "pin_fact",
        "ask_user",
        "wait",
        "abort",
        "yield_subtask",
    }
    return any(spec.name not in local_tools for spec in catalog.specs)


def _digest_public_id(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest() if value else ""


def _w1b_world_failure(
    case_ref: WebArenaVerifiedCaseRef,
    origin: str,
    code: str,
    detail: Mapping[str, object],
) -> dict[str, Any]:
    return {
        "schema_version": WA_SCHEMA_W1B_WORLD,
        "status": "failed",
        "acceptance_errors": (f"{origin}:{code}",),
        "case": case_ref.public_payload(),
        "failure_origin": origin,
        "failure_code": code,
        "detail": to_json_compatible(detail),
    }


def _source_counts(observation) -> dict[str, Any]:
    structures = sum(source.structure_total_count for source in observation.sources)
    retained_structures = sum(len(source.structure) for source in observation.sources)
    entity_total = sum(source.entity_inventory.entity_total_count for source in observation.sources)
    fact_total = sum(source.entity_inventory.fact_total_count for source in observation.sources)
    return {
        "raw_structure_total_count": structures,
        "raw_target_total_count": entity_total,
        "raw_fact_total_count": fact_total,
        "world_source_structure_count": retained_structures,
        "world_source_target_count": sum(len(source.targets) for source in observation.sources),
        "world_source_fact_count": sum(len(source.facts) for source in observation.sources),
        "coverage": tuple(
            {
                "source": source.surface,
                "coverage": source.coverage.value,
                "entity_inventory": source.entity_inventory.status.value,
                "entity_issues": tuple(item.value for item in source.entity_inventory.issue_codes),
                "semantic_inventory": source.semantic_inventory.status.value,
            }
            for source in observation.sources
        ),
    }


def _actor_ref_index(snapshot) -> tuple[dict[str, object], dict[str, tuple[object, ...]]]:
    refs: dict[str, object] = {}
    paths: dict[str, tuple[object, ...]] = {}

    def visit(node, path: tuple[object, ...]) -> None:
        current = (*path, node)
        if node.ref.startswith("E"):
            refs[node.ref] = node
            paths[node.ref] = current
        for child in node.children:
            visit(child, current)

    for document in snapshot.documents:
        for root in document.roots:
            visit(root, ())
    return refs, paths


def _tool_schema_refs(catalog) -> tuple[str, ...]:
    refs: list[str] = []
    for spec in catalog.specs:
        schema = spec.input_schema
        properties = schema.get("properties") if isinstance(schema, Mapping) else None
        if not isinstance(properties, Mapping):
            continue
        for name in ("target", "source", "destination"):
            field = properties.get(name)
            enum = field.get("enum") if isinstance(field, Mapping) else None
            if isinstance(enum, list | tuple):
                refs.extend(str(item) for item in enum if isinstance(item, str) and item.startswith("E"))
    return tuple(dict.fromkeys(refs))


def _action_option_refs(context) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        ref
        for option in context.actions.options
        for ref in (
            option.target_ref,
            *(item.grounding_ref for item in option.destinations.items),
        )
        if ref
    ))


def _capability_census(context, catalog) -> tuple[dict[str, object], ...]:
    supported = {item.semantic_action: item for item in BROWSERGYM_INTERACTION_PROFILE.capabilities}
    eligible = Counter(option.semantic_action for option in context.actions.options)
    exposed = {item.name for item in catalog.specs}
    paged = bool(context.actions.has_more and "find_actions" in exposed)
    result = []
    for definition in INTERACTION_CAPABILITY_REGISTRY.definitions:
        action = definition.semantic_action
        adapter_supported = action in supported
        currently_eligible = eligible[action]
        model_exposed = action in exposed
        absence_reason = ""
        if not adapter_supported:
            absence_reason = "adapter_not_supported"
        elif currently_eligible == 0:
            absence_reason = "no_current_eligible_binding"
        elif not model_exposed and paged:
            absence_reason = "paged_searchable"
        elif not model_exposed:
            absence_reason = "not_model_exposed"
        result.append({
            "semantic_action": action,
            "registry_defined": True,
            "adapter_supported": adapter_supported,
            "currently_eligible": currently_eligible,
            "model_exposed": model_exposed,
            "paged_searchable": bool(not model_exposed and paged and currently_eligible),
            "absence_reason": absence_reason,
            "subject_kinds": tuple(item.value for item in definition.subject_kinds),
            "primitive_actions": supported[action].primitive_actions if adapter_supported else (),
        })
    return tuple(result)


def _action_state_metrics(context, actor_refs: Mapping[str, object]) -> dict[str, Any]:
    grounding = {item.ref: item for item in context.grounding.entities}
    required_fields = {
        "value", "selected_options", "checked", "selected", "active",
        "expanded", "required", "option_domain", "grid_coordinate",
    }
    retained = 0
    total = 0
    mismatches = []
    for option in context.actions.options:
        node = actor_refs.get(option.target_ref)
        entity = grounding.get(option.target_ref)
        if node is None or entity is None or option.operation not in entity.verbs:
            mismatches.append({"ref": option.target_ref, "issue": "verb"})
            continue
        option_state = {
            key: value for key, value in option.target_state.items() if key in required_fields
        }
        total += len(option_state)
        node_state = getattr(node, "state", {})
        retained += sum(1 for key, value in option_state.items() if node_state.get(key) == value)
        missing = tuple(sorted(key for key, value in option_state.items() if node_state.get(key) != value))
        if missing:
            mismatches.append({"ref": option.target_ref, "issue": "state", "fields": missing})
    return {
        "retained": retained,
        "total": total,
        "coverage": "complete" if retained == total else "partial",
        "verb_mismatch_count": len(mismatches),
        "mismatches": tuple(mismatches[:32]),
    }


def _structural_closure_violations(snapshot, actor_paths: Mapping[str, tuple[object, ...]]) -> tuple[dict[str, str], ...]:
    violations: list[dict[str, str]] = []
    control_roles = {
        "button", "checkbox", "clickable", "combobox", "draggable", "link",
        "listbox", "menuitem", "radio", "searchbox", "slider", "spinbutton",
        "tab", "textbox",
    }
    for ref, path in actor_paths.items():
        node = path[-1]
        ancestors = path[:-1]
        role = str(getattr(node, "role", "")).casefold()
        if role in control_roles and not _has_semantic_text(node, ancestors):
            violations.append({"ref": ref, "code": "control_without_label_or_context"})
        if role in {"cell", "columnheader", "rowheader"}:
            ancestor_roles = {str(getattr(item, "role", "")).casefold() for item in ancestors}
            if "row" not in ancestor_roles or "table" not in ancestor_roles:
                violations.append({"ref": ref, "code": "table_cell_without_row_or_table"})
        if role == "dialog":
            continue
        if any(str(getattr(item, "role", "")).casefold() == "dialog" for item in ancestors):
            continue
    return tuple(violations)


def _has_semantic_text(node, ancestors: tuple[object, ...]) -> bool:
    candidates = (node, *reversed(ancestors))
    for item in candidates:
        if str(getattr(item, "label", "")).strip():
            return True
        classes = getattr(item, "state", {}).get("semantic.dom.attribute.class_tokens")
        if isinstance(classes, tuple | list) and any(str(value).strip() for value in classes):
            return True
    return False


def _collapsed_presentation_counts(snapshot) -> dict[str, int]:
    counts = Counter()
    for document in snapshot.documents:
        for root in document.roots:
            for node in _walk_actor_nodes(root):
                role = str(node.role)
                if role == "InlineTextBox":
                    counts["inline_text_boxes"] += 1
                if role == "StaticText" and not node.label.strip():
                    counts["empty_static_text"] += 1
                if role.casefold() == "generic" and not node.ref.startswith("E") and not node.label.strip():
                    counts["empty_generic_wrappers"] += 1
                counts["appearance_state_fields"] += sum(
                    1 for key in node.state if str(key).startswith("appearance.")
                )
    return dict(counts)


def _walk_actor_nodes(root):
    yield root
    for child in root.children:
        yield from _walk_actor_nodes(child)


def _private_leak_markers(rendered: str, catalog) -> tuple[str, ...]:
    public_tools = tuple(
        {"name": item.name, "description": item.description, "input_schema": to_json_compatible(item.input_schema)}
        for item in catalog.specs
    )
    payload = (rendered + "\n" + json.dumps(public_tools, sort_keys=True, ensure_ascii=False)).casefold()
    return tuple(marker for marker in _W1B_PRIVATE_MARKERS if marker in payload)


def _semantic_world_digest(observation) -> str:
    public = {
        "targets": tuple(to_json_compatible(item) for item in observation.targets),
        "facts": tuple(to_json_compatible(item) for item in observation.facts),
        "bindings": tuple(
            {
                "target_id": item.target_id,
                "semantic_action": item.semantic_action,
                "primitive_action": item.primitive_action,
                "destination_required": item.destination_required,
                "eligible_destination_ids": item.eligible_destination_ids,
                "schema_digest": schema_digest(item.parameter_schema),
            }
            for item in observation.bindings
        ),
    }
    encoded = json.dumps(public, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def _diagnostic_json_size(value: object) -> int:
    return len(json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode())


def _w0_report(payload: dict[str, Any], *, runtime_python: Path) -> dict[str, Any]:
    errors: list[str] = []
    packages = payload.get("packages") if isinstance(payload.get("packages"), dict) else {}
    for package_name in (
        "playwright",
        "browsergym-webarena",
        "browsergym-webarena-verified",
        "nltk",
        "webarena-verified",
    ):
        package = packages.get(package_name) if isinstance(packages, dict) else None
        if not isinstance(package, dict) or package.get("installed") is not True:
            errors.append(f"environment:{package_name}_missing")
    registration = payload.get("registration") if isinstance(payload.get("registration"), dict) else {}
    if registration.get("imported") is not True:
        errors.append("environment:registration_import_failed")
    missing = registration.get("missing_task_ids")
    if isinstance(missing, list) and missing:
        errors.append(f"environment:registered_task_ids_missing:{len(missing)}")
    sites = payload.get("sites") if isinstance(payload.get("sites"), list) else []
    required_sites = {"shopping", "shopping_admin", "reddit", "gitlab", "map", "wikipedia"}
    configured_site_names = _configured_site_names(sites)
    missing_sites = sorted(required_sites - configured_site_names)
    if missing_sites:
        errors.append(f"environment:wa_sites_missing:{','.join(missing_sites)}")
    unhealthy = [
        str(item.get("env"))
        for item in sites
        if isinstance(item, dict)
        and isinstance(item.get("health"), dict)
        and item["health"].get("status") != "ok"
    ]
    if unhealthy:
        errors.append(f"environment:wa_site_health_failed:{','.join(sorted(unhealthy))}")
    exercise = payload.get("exercise") if isinstance(payload.get("exercise"), dict) else {}
    if exercise.get("attempted") is True:
        reset = exercise.get("reset") if isinstance(exercise.get("reset"), dict) else {}
        evaluator = exercise.get("evaluator") if isinstance(exercise.get("evaluator"), dict) else {}
        if reset.get("status") != "ok" or reset.get("goal_present") is not True:
            errors.append("environment:official_reset_failed")
        if evaluator.get("status") != "ok":
            errors.append("environment:official_evaluator_invocation_failed")
    report = {
        "schema_version": WA_SCHEMA_W0,
        "ready": not errors,
        "failure_origin": "none" if not errors else "environment",
        "acceptance_errors": errors,
        "runtime_python": str(runtime_python),
        "pins": {
            "browsergym_commit": WA_BROWSERGYM_COMMIT,
            "webarena_verified_commit": WA_VERIFIED_COMMIT,
            "hard_subset_sha256": f"sha256:{WA_HARD_SUBSET_SHA256}",
        },
        "required_task_ids": [case.gym_id for case in WA_W0_REQUIRED_CASES],
        "smoke_task_ids": [case.gym_id for case in WA_W1_SMOKE_CASES],
        "proof_cohort_task_ids": [case.gym_id for case in WA_W2_COHORT_CASES],
        "subprocess": payload,
    }
    return report


def _configured_site_names(sites: list[object]) -> set[str]:
    names: set[str] = set()
    for item in sites:
        if not isinstance(item, dict):
            continue
        env_name = str(item.get("env") or "")
        suffix = env_name.removeprefix("WA_").casefold()
        for ending in ("_url", "_base_url", "_image_digest", "_digest"):
            suffix = suffix.removesuffix(ending)
        if suffix:
            names.add(suffix)
    return names


def _site_config_from_environment(environment: Mapping[str, str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for key, value in sorted(environment.items()):
        if not key.startswith("WA_") or not value.strip():
            continue
        upper = key.upper()
        if any(secret in upper for secret in ("KEY", "TOKEN", "SECRET", "PASSWORD", "HEADER", "COOKIE")):
            continue
        record = {
            "env": key,
            "value_sha256": f"sha256:{hashlib.sha256(value.strip().encode()).hexdigest()}",
        }
        if value.startswith(("http://", "https://")):
            record["redacted_url"] = _redact_url(value.strip())
        elif "DIGEST" in upper or value.startswith("sha256:"):
            record["image_digest"] = value.strip()
        records.append(record)
    return records


def _site_environment_frozen(environment: Mapping[str, str]) -> bool:
    records = _site_config_from_environment(environment)
    site_urls = _configured_site_names([
        item for item in records if "redacted_url" in item
    ])
    has_digest = any("image_digest" in item for item in records)
    return {"shopping", "shopping_admin", "reddit", "gitlab", "map", "wikipedia"}.issubset(site_urls) and has_digest


def _redact_url(value: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(value)
    host = parts.hostname or ""
    if not host:
        return value
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    path = parts.path.rstrip("/") + "/"
    return urlunsplit((parts.scheme, netloc, path, "", ""))


@dataclass(frozen=True)
class WebArenaVerifiedTaskRef:
    task_id: int
    sites: tuple[str, ...]
    intent_template_id: int
    revision: int


def load_webarena_verified_tasks(dataset_path: Path) -> list[WebArenaVerifiedTaskRef]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("WebArena-Verified dataset must be a JSON array")
    tasks: list[WebArenaVerifiedTaskRef] = []
    ids: set[int] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"dataset[{index}] must be an object")
        task_id = item.get("task_id")
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 0:
            raise ValueError(f"dataset[{index}].task_id must be a non-negative integer")
        if task_id in ids:
            raise ValueError(f"duplicate WebArena-Verified task id: {task_id}")
        ids.add(task_id)
        sites = item.get("sites")
        if not isinstance(sites, list) or not sites or any(not isinstance(site, str) or not site for site in sites):
            raise ValueError(f"dataset[{index}].sites must be a non-empty string array")
        template_id = item.get("intent_template_id")
        revision = item.get("revision")
        if isinstance(template_id, bool) or not isinstance(template_id, int):
            raise ValueError(f"dataset[{index}].intent_template_id must be an integer")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError(f"dataset[{index}].revision must be an integer")
        tasks.append(WebArenaVerifiedTaskRef(task_id, tuple(sites), template_id, revision))
    return tasks


def select_stratified_webarena_subset(
    tasks: Iterable[WebArenaVerifiedTaskRef], *, count: int = 30
) -> list[WebArenaVerifiedTaskRef]:
    """Select a deterministic round-robin sample across primary benchmark sites."""

    if not 30 <= count <= 50:
        raise ValueError("WebArena-Verified subset count must be between 30 and 50")
    groups: dict[str, list[WebArenaVerifiedTaskRef]] = defaultdict(list)
    for task in sorted(tasks, key=lambda item: item.task_id):
        groups[task.sites[0]].append(task)
    if not groups:
        raise ValueError("WebArena-Verified dataset contains no tasks")
    selected: list[WebArenaVerifiedTaskRef] = []
    cursors = {site: 0 for site in sorted(groups)}
    while len(selected) < count:
        progressed = False
        for site in sorted(groups):
            cursor = cursors[site]
            if cursor >= len(groups[site]):
                continue
            selected.append(groups[site][cursor])
            cursors[site] += 1
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            raise ValueError(f"WebArena-Verified dataset has fewer than {count} tasks")
    return selected


def write_webarena_verified_subset(
    dataset_path: Path, output_path: Path, *, count: int = 30
) -> dict[str, Any]:
    tasks = load_webarena_verified_tasks(dataset_path)
    selected = select_stratified_webarena_subset(tasks, count=count)
    source_digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    site_distribution = Counter(task.sites[0] for task in selected)
    manifest = {
        "schema_version": "webarena-verified-subset-v1",
        "official_evaluator": "webarena-verified eval-tasks",
        "source_dataset_sha256": f"sha256:{source_digest}",
        "source_task_count": len(tasks),
        "selection_policy": "sorted-primary-site-round-robin-v1",
        "selected_task_count": len(selected),
        "task_ids": [task.task_id for task in selected],
        "site_distribution": dict(sorted(site_distribution.items())),
        "tasks": [asdict(task) for task in selected],
        "official_score_claimed": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def evaluate_webarena_verified_manifest(
    manifest_path: Path,
    agent_logs_dir: Path,
    *,
    config_path: Path | None = None,
    executable: str = "webarena-verified",
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Delegate scoring to upstream's deterministic evaluator without a shell."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "webarena-verified-subset-v1":
        raise ValueError("invalid WebArena-Verified subset manifest")
    task_ids = manifest.get("task_ids")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in task_ids)
    ):
        raise ValueError("WebArena-Verified manifest task_ids must be a non-empty non-negative integer array")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("WebArena-Verified manifest task_ids must be unique")
    selected_count = manifest.get("selected_task_count")
    if selected_count is not None and selected_count != len(task_ids):
        raise ValueError("WebArena-Verified manifest selected_task_count does not match task_ids")
    source_digest = manifest.get("source_dataset_sha256")
    if not _is_sha256(source_digest):
        raise ValueError("WebArena-Verified manifest requires a valid source dataset SHA-256")
    command = [
        executable,
        "eval-tasks",
        "--task-ids",
        ",".join(str(task_id) for task_id in task_ids),
        "--output-dir",
        str(agent_logs_dir),
    ]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    try:
        completed = runner(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return _evaluation_report(
            manifest,
            manifest_path,
            command,
            task_ids,
            {},
            {},
            {},
            f"official evaluator unavailable: {type(exc).__name__}",
        )
    if completed.returncode != 0:
        return _evaluation_report(
            manifest,
            manifest_path,
            command,
            task_ids,
            {},
            {},
            {},
            f"official evaluator failed: exit_{completed.returncode}",
        )
    results: dict[int, dict[str, Any]] = {}
    result_digests: dict[int, str] = {}
    invalid_results: dict[int, str] = {}
    resolved_logs = agent_logs_dir.resolve()
    for task_id in task_ids:
        path = agent_logs_dir / str(task_id) / "eval_result.json"
        if not path.exists():
            continue
        try:
            resolved_path = path.resolve()
            resolved_path.relative_to(resolved_logs)
        except (OSError, ValueError):
            invalid_results[task_id] = "result_path_escape"
            continue
        try:
            raw_result = resolved_path.read_bytes()
            value = json.loads(raw_result.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            invalid_results[task_id] = f"unreadable_result:{type(exc).__name__}"
            continue
        error = _validate_upstream_result(value, task_id)
        if error:
            invalid_results[task_id] = error
            continue
        results[task_id] = value
        result_digests[task_id] = f"sha256:{hashlib.sha256(raw_result).hexdigest()}"
    return _evaluation_report(
        manifest,
        manifest_path,
        command,
        task_ids,
        results,
        result_digests,
        invalid_results,
        "",
    )


def _evaluation_report(
    manifest: dict[str, Any],
    manifest_path: Path,
    command: list[str],
    task_ids: list[int],
    results: dict[int, dict[str, Any]],
    result_digests: dict[int, str],
    invalid_results: dict[int, str],
    evaluator_error: str,
) -> dict[str, Any]:
    missing = [
        task_id
        for task_id in task_ids
        if task_id not in results and task_id not in invalid_results
    ]
    scores = [float(result["score"]) for result in results.values()]
    report = {
        "schema_version": "webarena-verified-evaluation-v2",
        "official_evaluator": "webarena-verified eval-tasks",
        "source_dataset_sha256": manifest.get("source_dataset_sha256", ""),
        "manifest_sha256": f"sha256:{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}",
        "manifest_task_ids": task_ids,
        "evaluated_task_count": len(results),
        "missing_result_ids": missing,
        "invalid_results": {str(task_id): invalid_results[task_id] for task_id in sorted(invalid_results)},
        "upstream_result_sha256": {
            str(task_id): result_digests[task_id] for task_id in sorted(result_digests)
        },
        # Absence of an upstream result is not an official zero.  Keeping this
        # nullable makes fail-closed preflight reports impossible to misread as
        # a scored run.
        "mean_official_score": sum(scores) / len(scores) if scores else None,
        "upstream_results": {str(task_id): results[task_id] for task_id in sorted(results)},
        "command": command,
        "official_score_claimed": False,
        "acceptance_errors": [],
    }
    if evaluator_error:
        report["acceptance_errors"].append(evaluator_error)
    if missing:
        report["acceptance_errors"].append(f"missing official results: {len(missing)}")
    if invalid_results:
        report["acceptance_errors"].append(f"invalid official results: {len(invalid_results)}")
    return report


def _validate_upstream_result(value: Any, expected_task_id: int) -> str:
    if not isinstance(value, dict):
        return "result_not_object"
    task_id = value.get("task_id")
    if task_id != expected_task_id:
        return "task_id_mismatch"
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "score_not_numeric"
    if not math.isfinite(float(score)) or not 0.0 <= float(score) <= 1.0:
        return "score_out_of_range"
    return ""


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)
