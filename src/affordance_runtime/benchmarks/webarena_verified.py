"""Official WebArena-Verified intake, STOP-gated native evaluation, and diagnostics."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from affordance_runtime.actions import ActionBinder, ActionSpaceBuilder
from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.actions.paging import delivery_descriptor_matches
from affordance_runtime.agent.context.budgets import serialized_size
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.model_turn_delivery import ModelTurnDelivery
from affordance_runtime.agent.context.observation_delivery import ObservationDeliveryStore, current_findings_digest
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.decisions import SearchPageContentResult, SelectAction
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.profile import DEFAULT_AGENT_LOOP_PROFILE
from affordance_runtime.agent.public_values import is_public_scalar
from affordance_runtime.agent.recovery import EpisodeMonitorRecommendation
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.workspace import (
    AgentWorkspace,
    DefaultWorkspaceReducer,
)
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
from affordance_runtime.evaluation.invocation import (
    InternalFailure,
    TaskEvaluationInternalError,
    TaskEvaluationStage,
    task_evaluation_diagnostic_from_exception,
)
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceipt,
    ExecutionReceiptBatch,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.canonical_provider_envelope import (
    CanonicalProviderEnvelopeBinder,
    CanonicalProviderIdentity,
)
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_tool_catalog import (
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyCallProfile,
    ActionPolicyInvocationPhase,
    ActionPolicyInvocationTrigger,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.model.policy.turn_packer import TurnPacker
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.surfaces.browsergym.environment import BrowserGymSurfaceAdapter
from affordance_runtime.surfaces.browsergym.interaction_profile import (
    BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES,
    BROWSERGYM_INTERACTION_PROFILE,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
    BrowserGymTaskStateSnapshot,
)
from affordance_runtime.surfaces.visual.role_set import PydanticAIVisualRoleSet
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
from affordance_runtime.world.finalization import (
    FinalResponseCodec,
    FinalResponsePayloadEncoding,
    FinalResponseToolContract,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

WA_BROWSERGYM_COMMIT = "9e779f087de9a65668b6974d11f9ce9816026e96"
WA_VERIFIED_COMMIT = "6473f72db5dcefc97b5725b59e734504edc28a21"
WA_HARD_SUBSET_SHA256 = "d20872f9894e4e8ffc250155fe0ad5c797c640f40d3094404654a8b1dab14e68"
WA_SELECTION_SEED = 20260818

_DIAGNOSTIC_IDENTITY = CanonicalProviderIdentity(
    "provider-free",
    "diagnostic",
    "fixture.invalid",
    "text_only",
)
_DIAGNOSTIC_PROFILE = ActionPolicyCallProfile(
    ActionPolicyInvocationPhase.ORDINARY,
    ActionPolicyInvocationTrigger.ORDINARY,
    1024,
    "disabled",
)


def _diagnostic_pack(request: ModelDecisionRequest, binder: CanonicalProviderEnvelopeBinder | None = None):
    return TurnPacker().pack(
        request,
        binder=binder or CanonicalProviderEnvelopeBinder(),
        identity=_DIAGNOSTIC_IDENTITY,
        call_profile=_DIAGNOSTIC_PROFILE,
        supports_multimodal=False,
        perception_profile=DecisionPerceptionProfile.TEXT_ONLY,
    )


WA_DEFAULT_TIMEOUT_S = 0.0
WA_REGISTRATION_MODULE = "browsergym.webarena_verified"
WA_SCHEMA_W0 = "webarena-verified-w0-readiness.v2"
WA_SCHEMA_W1B_WORLD = "webarena-verified-w1b-world.v5"
WA_W1B_DELIVERY_PROBE_VERSION = "v2"
WA_MANIFEST_SCHEMA = "webarena-verified-target-loop-manifest.v2"
_W1B_PRIVATE_MARKERS = (
    "browsergym_id",
    "private_bid",
    "private_element_id",
    "coordinate:",
    "bbox",
    "expected_answer",
    "target_answer",
    "raw_reward",
    "reward",
    "benchmark_oracle",
    "capture_epoch",
    "observation_id",
    "private_cursor",
    "page_cursor",
    "omitted_count",
    "omitted_total",
    "member_count",
    "raw_delta_lineage",
)


@dataclass(frozen=True)
class DeliveryRetrievalProbe:
    """Frozen public-only retrieval witness; never passed to production."""

    query: str
    expected_labels: tuple[str, ...]
    expected_kinds: tuple[str, ...] = ()
    required_operations: tuple[str, ...] = ()
    expected_path_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeliveryProbe:
    """Evaluator-only discoverability contract frozen before W1b execution."""

    site_key: str
    title_route_tokens: tuple[str, ...]
    required_region_labels: tuple[str, ...]
    retrievals: tuple[DeliveryRetrievalProbe, ...]


# Public UI vocabulary only. These fixtures contain no benchmark identity,
# expected answer, private binding, selector, or evaluator state and are never
# supplied to ContextBuilder, ranking, the binder, or a model request.
WA_W1B_DELIVERY_PROBES: Mapping[int, DeliveryProbe] = {
    0: DeliveryProbe(
        "shopping_admin",
        ("admin", "dashboard"),
        ("document",),
        (
            DeliveryRetrievalProbe(
                "Bestsellers",
                ("bestsellers",),
                ("tab", "link"),
                ("activate",),
                ("dashboard",),
            ),
        ),
    ),
    7: DeliveryProbe(
        "map",
        ("map", "openstreetmap"),
        ("document",),
        (
            DeliveryRetrievalProbe(
                "Find directions between two points",
                ("find directions between two points",),
                ("link",),
                ("activate",),
            ),
        ),
    ),
    21: DeliveryProbe(
        "shopping",
        ("headphones",),
        ("document",),
        (DeliveryRetrievalProbe("Reviews", ("reviews",), ("link", "tab"), ("activate",)),),
    ),
    27: DeliveryProbe(
        "reddit",
        ("reddit", "postmill"),
        ("document",),
        (DeliveryRetrievalProbe("Comments", ("comments",), ("link",), ("activate",)),),
    ),
    44: DeliveryProbe(
        "gitlab",
        ("gitlab",),
        ("document",),
        (DeliveryRetrievalProbe("Todos", ("to-do", "todo"), ("link",), ("activate",)),),
    ),
    266: DeliveryProbe(
        "wikipedia-map",
        ("wikipedia", "map"),
        ("document",),
        (DeliveryRetrievalProbe("Search", ("search",), ("searchbox", "textbox"), ("type_text",)),),
    ),
}


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


@dataclass(frozen=True)
class WebArenaVerifiedCaseAdmission:
    """Immutable benchmark-owner admission for one frozen public case cohort."""

    admission_id: str
    cases: tuple[WebArenaVerifiedCaseRef, ...]

    def __post_init__(self) -> None:
        normalized = tuple(self.cases)
        object.__setattr__(self, "cases", normalized)
        if (
            not isinstance(self.admission_id, str)
            or not self.admission_id
            or len(self.admission_id) > 96
            or any(not (character.isalnum() or character in "-_.") for character in self.admission_id)
        ):
            raise ValueError("WebArena-Verified admission identity is invalid")
        if not 1 <= len(normalized) <= 1024 or any(
            not isinstance(case_ref, WebArenaVerifiedCaseRef) for case_ref in normalized
        ):
            raise ValueError("WebArena-Verified admission requires a bounded typed case cohort")
        case_ids = tuple(
            (case_ref.intent_template_id, case_ref.task_id, case_ref.revision)
            for case_ref in normalized
        )
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("WebArena-Verified admission case identities must be unique")

    def require(self, case_ref: WebArenaVerifiedCaseRef) -> None:
        if case_ref not in self.cases:
            raise ValueError("WebArena-Verified case is outside the admitted benchmark cohort")


WA_W1_SMOKE_CASES: tuple[WebArenaVerifiedCaseRef, ...] = (
    WebArenaVerifiedCaseRef(0, 279, 2, ("shopping_admin",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(7, 79, 2, ("map",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(21, 222, 2, ("shopping",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(27, 33, 2, ("reddit",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(44, 303, 2, ("gitlab",), "smoke", "w1"),
    WebArenaVerifiedCaseRef(266, 85, 4, ("wikipedia", "map"), "smoke", "w1"),
)

# Frozen before its first current-tree execution. Held-out cases are admitted
# by the benchmark owner but remain outside the W1 smoke/development probes.
WA_W1_HELD_OUT_CASES: tuple[WebArenaVerifiedCaseRef, ...] = (
    WebArenaVerifiedCaseRef(8, 79, 2, ("map",), "retrieve", "w1-heldout"),
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

WA_W0_REQUIRED_CASES: tuple[WebArenaVerifiedCaseRef, ...] = (
    *WA_W1_SMOKE_CASES,
    *WA_W1_HELD_OUT_CASES,
    *WA_W2_COHORT_CASES,
)

WA_REVIEWED_CASE_ADMISSION = WebArenaVerifiedCaseAdmission(
    "reviewed-w1-w2",
    WA_W0_REQUIRED_CASES,
)

_W0_PREFLIGHT_PROGRAM = r"""
import importlib
import importlib.metadata as metadata
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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

def configured_url(site):
    keys = {
        "shopping": ("WA_SHOPPING", "WA_SHOPPING_URL"),
        "shopping_admin": ("WA_SHOPPING_ADMIN", "WA_SHOPPING_ADMIN_URL"),
        "reddit": ("WA_REDDIT", "WA_REDDIT_URL"),
        "gitlab": ("WA_GITLAB", "WA_GITLAB_URL"),
        "map": ("WA_MAP", "WA_MAP_URL"),
        "wikipedia": ("WA_WIKIPEDIA", "WA_WIKIPEDIA_URL"),
    }[site]
    return next((os.environ[key].strip() for key in keys if os.environ.get(key, "").strip()), "")

def declared_image_digest(site):
    value = os.environ.get(f"WA_{site.upper()}_IMAGE_DIGEST", "").strip()
    match = re.search(r"sha256:[0-9a-fA-F]{64}$", value)
    return match.group(0).lower() if match else ""

def deployment(site):
    url = configured_url(site)
    hostname = (urllib.parse.urlsplit(url).hostname or "").casefold()
    record = {"site": site, "container": f"webarena_verified_{site}"}
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        record["status"] = "remote_not_inspected"
        return record
    declared = declared_image_digest(site)
    if not declared:
        record["status"] = "declared_digest_missing"
        return record
    try:
        completed = subprocess.run(
            ["docker", "inspect", "--format", "{{json .State.Running}}|{{.Image}}", record["container"]],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        record.update({"status": "inspection_failed", "error": type(exc).__name__})
        return record
    if completed.returncode != 0:
        record["status"] = "container_missing"
        return record
    try:
        running_text, actual = completed.stdout.strip().split("|", 1)
        running = json.loads(running_text)
    except Exception:
        record["status"] = "inspection_invalid"
        return record
    record.update({"running": running is True, "declared_digest": declared, "actual_digest": actual.lower()})
    if running is not True:
        record["status"] = "container_not_running"
    elif actual.lower() != declared:
        record["status"] = "image_digest_mismatch"
    else:
        record["status"] = "match"
    return record

def map_integrity():
    base_url = configured_url("map")
    if not base_url:
        return {"status": "map_url_missing"}
    started = time.perf_counter()
    query = urllib.parse.urlencode({"q": "New York", "format": "json", "limit": 1})
    search_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "nominatim/search?" + query)
    try:
        with urllib.request.urlopen(urllib.request.Request(search_url, method="GET"), timeout=10) as response:
            search_status = int(response.status)
            results = json.loads(response.read(262144))
    except urllib.error.HTTPError as exc:
        return {"status": "search_http_error", "search_http_status": int(exc.code)}
    except Exception as exc:
        return {"status": "search_failed", "error": type(exc).__name__}
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return {"status": "search_entity_missing", "search_http_status": search_status}
    entity = results[0]
    osm_type = str(entity.get("osm_type") or "").casefold()
    osm_id = entity.get("osm_id")
    route_type = {"node": "node", "way": "way", "relation": "relation", "n": "node", "w": "way", "r": "relation"}.get(osm_type)
    if route_type is None or type(osm_id) is not int or osm_id <= 0:
        return {"status": "search_entity_invalid", "search_http_status": search_status}
    detail_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"{route_type}/{osm_id}")
    try:
        with urllib.request.urlopen(urllib.request.Request(detail_url, method="GET"), timeout=10) as response:
            detail_status = int(response.status)
            response.read(8192)
    except urllib.error.HTTPError as exc:
        return {
            "status": "detail_http_error",
            "search_http_status": search_status,
            "detail_http_status": int(exc.code),
            "entity_type": route_type,
        }
    except Exception as exc:
        return {"status": "detail_failed", "search_http_status": search_status, "error": type(exc).__name__}
    return {
        "status": "ok" if detail_status == 200 else "detail_http_error",
        "search_http_status": search_status,
        "detail_http_status": detail_status,
        "entity_type": route_type,
        "entity_id_sha256": "sha256:" + __import__("hashlib").sha256(str(osm_id).encode()).hexdigest(),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }

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
    "deployments": [],
    "map_integrity": {},
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

report["deployments"] = [
    deployment(site)
    for site in ("shopping", "shopping_admin", "reddit", "gitlab", "map", "wikipedia")
]
report["map_integrity"] = map_integrity()

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


@dataclass(frozen=True)
class WebArenaVerifiedFinalResponseCodec:
    """Delegate response representation to the pinned upstream Pydantic model."""

    @property
    def model_guidance(self) -> str:
        objective_description, _objective_values, status_values = self._upstream_response_enums()
        objective_rules = "; ".join(
            line.strip()
            for line in objective_description.splitlines()
            if line.strip().startswith(("RETRIEVE:", "MUTATE:", "NAVIGATE:"))
        )
        if not all(f"{name}:" in objective_rules for name in ("RETRIEVE", "MUTATE", "NAVIGATE")):
            raise ValueError("WebArena task-type definitions are incomplete")
        return (
            f"JSON FinalAgentResponse. task_type is overall work: {objective_rules}. "
            "Derive it from task, never goal_plan or allowed effects. "
            f"status={'|'.join(status_values)}. NAVIGATE/MUTATE: retrieved_data=null. "
            "SUCCESS: error_details=null. Empty RETRIEVE: NOT_FOUND_ERROR and retrieved_data=null."
        )

    @property
    def model_tool_contract(self) -> FinalResponseToolContract:
        _description, objective_values, status_values = self._upstream_response_enums()
        success = "SUCCESS"
        failure_values = [value for value in status_values if value != success]
        non_retrieval_values = [value for value in objective_values if value != "RETRIEVE"]
        if (
            success not in status_values
            or not failure_values
            or "RETRIEVE" not in objective_values
            or not non_retrieval_values
        ):
            raise ValueError("WebArena final-response outcome algebra is incomplete")
        retrieved_item_schema = self._retrieved_item_schema()
        nonblank_error_schema = {
            "type": "string",
            "minLength": 1,
            "maxLength": 512,
            "pattern": r"[\s\S]*\S[\s\S]*",
        }

        def branch(
            task_types: list[str],
            statuses: list[str],
            retrieved_data: Mapping[str, object],
            error_details: Mapping[str, object],
        ) -> dict[str, object]:
            return {
                "type": "object",
                "properties": {
                    "task_type": {"type": "string", "enum": task_types},
                    "status": {"type": "string", "enum": statuses},
                    "retrieved_data": retrieved_data,
                    "error_details": error_details,
                },
                "required": ["task_type", "status", "retrieved_data", "error_details"],
                "additionalProperties": False,
            }

        return FinalResponseToolContract(
            FinalResponsePayloadEncoding.JSON,
            {
                "oneOf": [
                    branch(
                        ["RETRIEVE"],
                        [success],
                        {
                            "type": "array",
                            "items": retrieved_item_schema,
                            "minItems": 1,
                            "maxItems": 16,
                        },
                        {"type": "null"},
                    ),
                    branch(
                        ["RETRIEVE"],
                        failure_values,
                        {"type": "null"},
                        nonblank_error_schema,
                    ),
                    branch(
                        non_retrieval_values,
                        [success],
                        {"type": "null"},
                        {"type": "null"},
                    ),
                    branch(
                        non_retrieval_values,
                        failure_values,
                        {"type": "null"},
                        nonblank_error_schema,
                    ),
                ],
            },
            supports_presentation_sidecars=False,
        )

    @staticmethod
    def _retrieved_item_schema() -> dict[str, object]:
        bounded_number = {
            "minimum": -1_000_000_000_000_000,
            "maximum": 1_000_000_000_000_000,
        }
        return {
            "anyOf": [
                {"type": "string", "maxLength": 512},
                {"type": "integer", **bounded_number},
                {"type": "number", **bounded_number},
                {"type": "boolean"},
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": {
                        "anyOf": [
                            {"type": "string", "maxLength": 128},
                            {"type": "integer", **bounded_number},
                            {"type": "number", **bounded_number},
                            {"type": "boolean"},
                            {"type": "null"},
                        ]
                    },
                    "maxProperties": 6,
                    "propertyNames": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 32,
                    },
                },
                {"type": "null"},
            ]
        }

    @staticmethod
    def _upstream_response_enums() -> tuple[str, list[str], list[str]]:
        schema = WebArenaVerifiedFinalResponseCodec._upstream_response_schema()
        definitions = schema.get("$defs")
        if not isinstance(definitions, Mapping):
            raise ValueError("WebArena final-response schema is missing definitions")
        objective = definitions.get("MainObjectiveType")
        status = definitions.get("Status")
        if not isinstance(objective, Mapping) or not isinstance(status, Mapping):
            raise ValueError("WebArena final-response schema is missing response enums")
        objective_description = objective.get("description")
        objective_values = objective.get("enum")
        status_values = status.get("enum")
        if (
            not isinstance(objective_description, str)
            or not isinstance(objective_values, list)
            or not isinstance(status_values, list)
            or any(not isinstance(value, str) or not value for value in (*objective_values, *status_values))
        ):
            raise ValueError("WebArena final-response enum contract is malformed")
        return objective_description, objective_values, status_values

    def semantic_instruction(self, goal_instruction: str) -> str:
        """Remove only the pinned upstream response envelope from its intent."""

        suffix = self._upstream_instruction_suffix()
        marker = "\n\n---\nFinal response format:"
        if marker not in goal_instruction:
            return goal_instruction
        if not goal_instruction.endswith(suffix):
            raise ValueError("WebArena final-response instruction does not match the pinned codec")
        semantic_instruction = goal_instruction[: -len(suffix)].rstrip()
        if not semantic_instruction:
            raise ValueError("WebArena task is missing its semantic instruction")
        return semantic_instruction

    @staticmethod
    def _upstream_instruction_suffix() -> str:
        response_schema = WebArenaVerifiedFinalResponseCodec._upstream_response_schema()
        return f"""

---
Final response format: When you send your final answer to the user with `send_msg_to_user`, your message must be a json formatted string that matches the following schema:
```
{json.dumps(response_schema, indent=4)}
```
Your message in `send_msg_to_user` will be validated against this schema.
"""

    @staticmethod
    def _upstream_response_schema() -> dict[str, object]:
        final_agent_response = importlib.import_module("webarena_verified.types").FinalAgentResponse
        response_schema = final_agent_response.model_json_schema()
        if not isinstance(response_schema, dict):
            raise ValueError("WebArena final-response schema is malformed")
        return response_schema

    def normalize(self, content: str) -> str:
        final_agent_response = importlib.import_module("webarena_verified.types").FinalAgentResponse
        normalized = final_agent_response.model_validate_json(content)
        return self.model_tool_contract.encode(normalized.model_dump(mode="json"))


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
    final_response_codec: FinalResponseCodec = WebArenaVerifiedFinalResponseCodec()
    visual_roles: PydanticAIVisualRoleSet | None = field(default=None, repr=False)

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
        if result.result.dispatch_status in {DispatchStatus.SENT, DispatchStatus.SENT_UNKNOWN}:
            self.final_delivery_confirmed = True
        return result

    def is_current(self, request):
        return self.world.is_current(request)

    async def close(self) -> None:
        visual_roles, self.visual_roles = self.visual_roles, None
        try:
            await self.surface.close()
        finally:
            if visual_roles is not None:
                visual_roles.close()

    def current_native_result(self) -> tuple[TaskOutcomeKind, str, tuple[str, ...]]:
        self.native_evaluator_queries += 1
        return classify_webarena_runtime_snapshot(
            self.surface.current_task_state(),
            final_delivery_attempted=self.final_delivery_attempted,
        )


@dataclass(frozen=True)
class WebArenaVerifiedNativeEvaluator:
    """Map the official BrowserGym terminal state into TaskEvaluation."""

    environment: WebArenaVerifiedCaseEnvironment

    async def evaluate(self, task, observation) -> TaskEvaluation:
        snapshot = None
        self.environment.native_evaluator_queries += 1
        try:
            snapshot = self.environment.surface.current_task_state()
        except Exception as exc:
            raise _native_evaluator_internal_error(
                exc,
                TaskEvaluationStage.NATIVE_SNAPSHOT,
                observation.observation_id,
            ) from exc
        try:
            outcome_kind, code, refs = classify_webarena_runtime_snapshot(
                snapshot,
                final_delivery_attempted=self.environment.final_delivery_attempted,
            )
        except Exception as exc:
            raise _native_evaluator_internal_error(
                exc,
                TaskEvaluationStage.NATIVE_CLASSIFICATION,
                observation.observation_id,
                snapshot,
            ) from exc
        try:
            evidence_index = WorldEvidenceIndex.from_observation(observation)
        except Exception as exc:
            raise _native_evaluator_internal_error(
                exc,
                TaskEvaluationStage.EVIDENCE_INDEX,
                observation.observation_id,
                snapshot,
            ) from exc
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
        try:
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                status,
                f"webarena-verified native evaluator: {code}",
                completion_evidence_refs=refs if outcome_kind is TaskOutcomeKind.TERMINAL_SUCCESS else (),
                outcome=TaskOutcomeFact(outcome_kind, code, refs),
            )
        except Exception as exc:
            raise _native_evaluator_internal_error(
                exc,
                TaskEvaluationStage.NATIVE_PROJECTION,
                observation.observation_id,
                snapshot,
            ) from exc


def _native_evaluator_internal_error(
    exc: Exception,
    stage: TaskEvaluationStage,
    observation_id: str,
    snapshot: BrowserGymTaskStateSnapshot | None = None,
) -> TaskEvaluationInternalError:
    fields = tuple(sorted(snapshot.present_fields)) if snapshot is not None else ()
    return TaskEvaluationInternalError(
        InternalFailure(
            "native_evaluator_internal_failure",
            task_evaluation_diagnostic_from_exception(
                exc,
                stage=stage,
                observation_id=observation_id,
                native_snapshot_present_fields=fields,
            ),
        )
    )


def open_webarena_verified_case(
    case_ref: WebArenaVerifiedCaseRef,
    seed: int = WA_SELECTION_SEED,
    *,
    admission: WebArenaVerifiedCaseAdmission = WA_REVIEWED_CASE_ADMISSION,
    gym_factory: Any | None = None,
    max_turns: int = 100,
    browser_navigation_urls: tuple[str, ...] | None = None,
    visual_roles: PydanticAIVisualRoleSet | None = None,
) -> tuple[WebArenaVerifiedCaseEnvironment, TaskGoal, WebArenaVerifiedNativeEvaluator]:
    """Open one official case and own any explicitly supplied visual roles."""

    try:
        if not isinstance(admission, WebArenaVerifiedCaseAdmission):
            raise TypeError("WebArena-Verified case admission must be typed")
        admission.require(case_ref)
        navigation_urls = (
            _configured_webarena_navigation_urls(os.environ)
            if browser_navigation_urls is None
            else browser_navigation_urls
        )
        final_response_codec = WebArenaVerifiedFinalResponseCodec()
    except BaseException:
        if visual_roles is not None:
            visual_roles.close()
        raise
    try:
        surface = BrowserGymSurfaceAdapter.open(
            case_ref.gym_id,
            seed,
            gym_factory=gym_factory,
            registration_modules=(WA_REGISTRATION_MODULE,),
            browser_action_primitives=BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES,
            browser_navigation_urls=navigation_urls,
            visual_region_proposer=(
                visual_roles.region_proposer if visual_roles is not None else None
            ),
            visual_point_grounder=(
                visual_roles.point_grounder if visual_roles is not None else None
            ),
            visual_candidate_disambiguator=(
                visual_roles.candidate_disambiguator if visual_roles is not None else None
            ),
            visual_predicate_classifier=(
                visual_roles.predicate_classifier if visual_roles is not None else None
            ),
            visual_text_reader=(
                visual_roles.text_reader if visual_roles is not None else None
            ),
            visual_spatial_classifier=(
                visual_roles.spatial_classifier if visual_roles is not None else None
            ),
            visual_change_classifier=(
                visual_roles.change_classifier if visual_roles is not None else None
            ),
            task_instruction_transform=final_response_codec.semantic_instruction,
        )
    except BaseException:
        if visual_roles is not None:
            visual_roles.close()
        raise
    try:
        intake = ThinTaskIntake().compile(
            NaturalLanguageTaskRequest(
                "task:webarena_verified",
                surface.goal_instruction,
                TaskBoundary(
                    allowed_effects=("external_ui_interaction",),
                    forbidden_effects=("credential_use",),
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
            intake.task,
            final_response_codec=final_response_codec,
            visual_roles=visual_roles,
        )
        return environment, intake.task, WebArenaVerifiedNativeEvaluator(environment)
    except BaseException:
        surface.gym_environment.close()
        if visual_roles is not None:
            visual_roles.close()
        raise


def _ensure_public_task(task: TaskGoal, adapter_task: TaskGoal) -> None:
    if task.task_id != adapter_task.task_id or task.revision != adapter_task.revision:
        raise ValueError("WebArena public task identity must match the adapter task")


def _configured_webarena_navigation_urls(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Read the same explicit WebArena deployment URLs consumed by BrowserGym."""

    instance_module = importlib.import_module("browsergym.webarena.instance")
    names = tuple(str(item) for item in instance_module.ENV_VARS)
    urls = tuple(environment.get(f"WA_{name}", "").strip() for name in names)
    if any(not value for value in urls):
        raise RuntimeError("WebArena browser navigation scope requires the configured WA site URLs")
    return urls


def classify_webarena_runtime_snapshot(
    snapshot: BrowserGymTaskStateSnapshot,
    *,
    final_delivery_attempted: bool,
) -> tuple[TaskOutcomeKind, str, tuple[str, ...]]:
    """Honor provider terminal state immediately; gate only voluntary STOP completion."""

    if not final_delivery_attempted and not snapshot.terminal_hint:
        return TaskOutcomeKind.RUNNING_INCOMPLETE, "stop_not_confirmed", ()
    return classify_webarena_terminal_snapshot(snapshot)


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
        "registration_module": WA_REGISTRATION_MODULE,
        "smoke_cases": [case.public_payload() for case in WA_W1_SMOKE_CASES],
        "heldout_cases": [case.public_payload() for case in WA_W1_HELD_OUT_CASES],
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
    delivered_tokens = sorted(
        int(item.get("request_budget", {}).get("estimated_input_tokens", 0))
        for item in cases
        if item.get("status") == "ok"
    )
    median_tokens = (
        (delivered_tokens[(len(delivered_tokens) - 1) // 2] + delivered_tokens[len(delivered_tokens) // 2]) / 2
        if delivered_tokens
        else 0
    )
    aggregate_errors = ("cost:six_page_median_over_8k",) if median_tokens > 8_000 else ()
    summary = {
        "schema_version": WA_SCHEMA_W1B_WORLD,
        "stage": "w1b-world",
        "agent_loop_profile": _agent_loop_profile_diagnostics(),
        "selection_seed": seed,
        "case_count": len(cases),
        "ready": (
            not aggregate_errors
            and all(item.get("status") == "ok" and not item.get("acceptance_errors") for item in cases)
        ),
        "failure_origin": "none" if all(item.get("status") == "ok" for item in cases) else "environment_or_projection",
        "acceptance_errors": (
            *aggregate_errors,
            *tuple(error for case in cases for error in case.get("acceptance_errors", ())),
        ),
        "cost_gate": {
            "new_page_tokens": tuple(delivered_tokens),
            "median_tokens": median_tokens,
            "each_limit": 12_000,
            "median_limit": 8_000,
        },
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
        )
        binder = CanonicalProviderEnvelopeBinder()
        request = ModelDecisionRequest(
            request_id=f"diagnostic:{context.context_id}",
            agent_context=context,
        )
        packed = _diagnostic_pack(request, binder)
        delivery = packed.delivery
        catalog = packed.catalog
        request_budget = packed.admitted_envelope.token_breakdown.as_diagnostics()
        return _w1b_world_success(
            case_ref,
            environment,
            task,
            observation,
            action_space,
            context,
            catalog,
            delivery,
            packed.admitted_envelope,
            request_budget,
        )
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
    delivery: ModelTurnDelivery,
    admitted_envelope,
    request_budget: Mapping[str, object],
) -> dict[str, Any]:
    source_counts = _source_counts(observation)
    actor_refs, actor_paths = _actor_ref_index(context.actor_world)
    rendered = delivery.view
    manifest = delivery.manifest
    tool_refs = tuple(manifest.executable_refs)
    option_refs = _action_option_refs(context, complete=True)
    missing_tool_refs = tuple(sorted(set(tool_refs) - set(option_refs)))
    state_metrics = _action_state_metrics(context, actor_refs)
    closure_violations = _structural_closure_violations(context.actor_world, actor_paths)
    leak_markers = _private_leak_markers(
        rendered.text,
        catalog,
        admitted_envelope,
        _private_runtime_strings(observation),
    )
    find_controls_offered = "find_controls" in {item.name for item in catalog.specs}
    recoverability = _recoverability_diagnostic(
        environment,
        task,
        observation,
        action_space,
        context,
        catalog,
    )
    delivery_probe = _delivery_probe_diagnostic(
        WA_W1B_DELIVERY_PROBES[case_ref.task_id],
        task,
        observation,
        action_space,
        context,
        catalog,
        delivery,
    )
    candidate_diagnostic = _candidate_diagnostic(
        WA_W1B_DELIVERY_PROBES[case_ref.task_id],
        context,
        delivery,
        delivery_probe,
        recoverability,
        request_budget,
    )
    transition_diagnostic = _transition_delivery_diagnostic(
        task,
        observation,
        context,
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
    if context.actions.has_more and not find_controls_offered:
        acceptance_errors.append("partial_action_inventory_without_find_controls")
    acceptance_errors.extend(recoverability["acceptance_errors"])
    acceptance_errors.extend(delivery_probe["acceptance_errors"])
    acceptance_errors.extend(candidate_diagnostic["acceptance_errors"])
    acceptance_errors.extend(transition_diagnostic["acceptance_errors"])
    acceptance_errors.extend(_w1b_cost_errors(request_budget))
    return {
        "schema_version": WA_SCHEMA_W1B_WORLD,
        "status": "ok",
        "agent_loop_profile": _agent_loop_profile_diagnostics(),
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
            "rendered_bytes": len(rendered.text.encode()),
            "rendered_token_estimate": max(1, math.ceil(len(rendered.text) / 4)),
            "delivery_projection": rendered.projection,
            "manifest": {
                "executable": len(manifest.executable_refs),
                "readonly": len(manifest.readonly_refs),
                "facts": len(manifest.fact_refs),
                "regions": len(manifest.region_refs),
            },
        },
        "tools": {
            "offered_tool_target_count": len(tool_refs),
            "offered_action_ref_count": len(option_refs),
            "actor_missing_offered_targets": missing_tool_refs,
            "catalog_tool_count": len(catalog.specs),
            "catalog_serialized_bytes": catalog.serialized_bytes,
            "find_controls_offered": find_controls_offered,
        },
        "action_inventory": {
            "visible_count": context.actions.page_size,
            "total_count": context.actions.total_count,
            "partial": context.actions.has_more,
            "recovery": "find_controls" if context.actions.has_more else "not_required",
        },
        "transition_delivery": transition_diagnostic,
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
        "delivery_probe": delivery_probe,
        "action_candidates": candidate_diagnostic,
        "perception_route": {
            "profile": "TEXT_ONLY",
            "image_attached": False,
            "reason": "w1b-world read-only structured diagnostic",
        },
        "request_budget": dict(request_budget),
    }


def _transition_delivery_diagnostic(
    task: TaskGoal,
    before,
    before_context,
) -> dict[str, object]:
    """Run one generic real-page-shape transition through the provider-free owner chain."""

    key_counts = Counter((item.subject_id, item.predicate) for item in before.facts)
    selected = next(
        (
            item
            for item in before.facts
            if key_counts[(item.subject_id, item.predicate)] == 1 and is_public_scalar(item.value)
        ),
        None,
    )
    if selected is None:
        return {
            "provider_attempts": 0,
            "acceptance_errors": ("transition:no_unique_public_scalar_fact",),
        }
    changed_value = _diagnostic_changed_value(selected.value)
    after_id = f"{before.observation_id}:provider-free-transition"
    after = replace(
        before,
        observation_id=after_id,
        targets=tuple(
            replace(
                item,
                state={**item.state, selected.predicate: changed_value},
            )
            if item.target_id == selected.subject_id and selected.predicate in item.state
            else item
            for item in before.targets
        ),
        facts=tuple(
            replace(item, value=changed_value) if item.fact_id == selected.fact_id else item for item in before.facts
        ),
        bindings=tuple(replace(item, world_observation_id=after_id) for item in before.bindings),
    )
    delta = WorldTransitionProjector().project(before, after)
    builder = ActionSpaceBuilder()
    executable_option = next(
        (
            option
            for option in builder.build(task, before).options
            if not option.destination_required and not option.parameter_schema.get("required")
        ),
        None,
    )
    if executable_option is None:
        return {
            "provider_attempts": 0,
            "acceptance_errors": ("transition:no_parameter_free_action",),
        }
    selection = builder.admit(executable_option, {})
    bound = ActionBinder().bind(
        selection,
        before,
        before_context.context_id,
        tool_call_id="diagnostic:transition",
    )
    action_result = ActionResult(
        bound.request_id,
        DispatchStatus.SENT,
        "provider-free-diagnostic",
        True,
    )
    receipts = ExecutionReceiptBatch(
        (
            ExecutionReceipt(
                bound,
                action_result,
                before.observation_id,
                after.observation_id,
            ),
        ),
        ExecutionCompletion.COMPLETE,
    )
    decision = SelectAction(
        before_context.context_id,
        executable_option.action_id,
        tool_call_id="diagnostic:transition",
    )
    evaluation = TaskEvaluation(
        task.task_id,
        after.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "provider-free transition diagnostic",
    )
    transition_step = StepResult(
        decision,
        before,
        after,
        evaluation,
        execution_receipts=receipts,
        feedback="provider_free_public_transition",
        public_world_delta=delta,
    )
    after_action_space = ActionSpaceBuilder().build(task, after)
    before_index = before_context.region_index
    after_index = WorldDeliveryIndex.from_observation(
        after,
        after_action_space.options,
        public_world_delta=delta,
        previous_index=before_index,
    )
    transition_step = replace(
        transition_step,
        before_public_world=before_context.canonical_world,
        after_public_world=CanonicalPublicWorldProjection.build(
            after,
            after_index,
            after_action_space,
        ),
    )
    store = ObservationDeliveryStore().reduce(transition_step, step_index=1).next_store
    reducer = DefaultWorkspaceReducer()
    workspace = reducer.reduce(
        AgentWorkspace(),
        transition_step,
        project_step_result(transition_step),
        1,
    )
    after_context = ContextBuilder().build(
        task,
        after,
        after_action_space,
        evaluation,
        workspace=workspace,
        current_step_index=1,
        region_index=after_index,
        canonical_world=transition_step.after_public_world,
    )
    monitor = EpisodeMonitor()
    monitor.start_episode(before, before_context.task.evaluation)
    transition_monitor = monitor.evaluate(
        transition_step,
        current_findings_digest(after),
    )

    binder = CanonicalProviderEnvelopeBinder()
    request = ModelDecisionRequest(
        request_id=f"diagnostic:transition:{after_context.context_id}",
        agent_context=after_context,
    )
    packed = _diagnostic_pack(request, binder)
    delivery = packed.delivery
    admitted = packed.admitted_envelope

    local_decision = SearchPageContentResult(
        after_context.context_id,
        "search_page_content",
        {"query": "provider-free transition diagnostic"},
        {"kind": "NoMatches", "items": (), "total_count": 0},
        tool_call_id="diagnostic:local-search",
    )
    local_step = StepResult(
        local_decision,
        after,
        after,
        evaluation,
        feedback="local_tool_result",
    )
    local_transition = store.reduce(local_step, step_index=2)
    local_store = local_transition.next_store
    local_workspace = reducer.reduce(
        workspace,
        local_step,
        project_step_result(local_step),
        2,
        information_delta=local_transition.information_delta,
    )
    local_monitor = monitor.evaluate(
        local_step,
        current_findings_digest(after),
    )
    local_context = ContextBuilder().build(
        task,
        after,
        after_action_space,
        evaluation,
        workspace=local_workspace,
        current_step_index=2,
        context_generation=1,
        region_index=after_index,
    )
    local_request = ModelDecisionRequest(
        request_id=f"diagnostic:local:{local_context.context_id}",
        agent_context=local_context,
    )
    local_packed = _diagnostic_pack(local_request, binder)
    local_delivery = local_packed.delivery
    local_admitted = local_packed.admitted_envelope
    transition_leaks = _private_leak_markers(
        delivery.view.text,
        packed.catalog,
        admitted,
        _private_runtime_strings(after),
    )
    local_leaks = _private_leak_markers(
        local_delivery.view.text,
        local_packed.catalog,
        local_admitted,
        _private_runtime_strings(after),
    )

    public_diff = _serialized_public_snapshot_diff(before, after)
    delta_keys = tuple(
        sorted(
            (
                *(("target", item.target_id, "semantic") for item in delta.target_changes),
                *(("fact", item.subject_id, item.predicate) for item in delta.fact_changes),
            )
        )
    )
    common_keys = {item.key for item in before_index.regions}.intersection(item.key for item in after_index.regions)
    unchanged_keys = tuple(key for key in common_keys if key not in delta.changed_region_keys)
    reused = tuple(
        key
        for key in unchanged_keys
        if before_index.version_for(key) is not None
        and after_index.version_for(key) is not None
        and before_index.version_for(key).version == after_index.version_for(key).version
        and before_index.version_for(key).cached_outline == after_index.version_for(key).cached_outline
    )
    fresh_world_is_current = (
        after_context.current_observation is not None
        and after_context.current_observation.observation_id == after.observation_id
        and local_context.current_observation is not None
        and local_context.current_observation.observation_id == after.observation_id
    )
    stale_effect_markers = ("LatestEffect", "CurrentFindings", "ChangedRegions", "new_document")
    single_current_world_projection = (
        all(
            marker not in delivery.view.text and marker not in local_delivery.view.text
            for marker in stale_effect_markers
        )
        and "PageMap regions=" in delivery.view.text
        and "PageMap regions=" in local_delivery.view.text
    )
    gui_action_did_not_create_delivery_state = store == ObservationDeliveryStore()
    local_delivery_does_not_reproject_gui_effect = local_store.local_deliveries and tuple(
        item.name for item in fields(local_store)
    ) == ("local_deliveries",)
    errors = []
    if public_diff != delta_keys:
        errors.append("transition:serialized_snapshot_delta_mismatch")
    if not fresh_world_is_current:
        errors.append("transition:fresh_world_not_current")
    if unchanged_keys and len(reused) != len(unchanged_keys):
        errors.append("transition:unchanged_region_cache_not_reused")
    if not gui_action_did_not_create_delivery_state:
        errors.append("transition:gui_action_created_second_current_state")
    if not local_delivery_does_not_reproject_gui_effect:
        errors.append("transition:local_delivery_reprojected_gui_effect")
    if transition_step.public_world_delta != delta:
        errors.append("transition:step_delta_lineage_mismatch")
    if not workspace.recent_steps or not workspace.semantic_events:
        errors.append("transition:workspace_reducer_did_not_commit")
    if transition_monitor.recommendation is not EpisodeMonitorRecommendation.CONTINUE:
        errors.append("transition:monitor_rejected_information_increment")
    if local_monitor.recommendation is not EpisodeMonitorRecommendation.CONTINUE:
        errors.append("transition:monitor_rejected_bounded_local_search")
    if (
        admitted.token_breakdown.estimated_input_tokens <= 0
        or local_admitted.token_breakdown.estimated_input_tokens <= 0
    ):
        errors.append("transition:post_transition_request_not_admitted")
    if not single_current_world_projection:
        errors.append("transition:model_context_has_conflicting_current_state")
    if transition_leaks:
        errors.append(f"transition:private_model_input_leaks:{len(transition_leaks)}")
    if local_leaks:
        errors.append(f"transition:local_private_model_input_leaks:{len(local_leaks)}")
    return {
        "provider_attempts": 0,
        "agent_loop_profile": _agent_loop_profile_diagnostics(),
        "mutation_kind": "generic_unique_scalar_modification",
        "public_world_delta": {
            "target_change_count": len(delta.target_changes),
            "fact_changes": len(delta.fact_changes),
            "changed_region_count": len(delta.changed_region_keys),
            "before_digest": delta.before_world_digest,
            "after_digest": delta.after_world_digest,
        },
        "serialized_snapshot_diff_count": len(public_diff),
        "serialized_snapshot_matches_delta": public_diff == delta_keys,
        "fresh_world_is_current": fresh_world_is_current,
        "single_current_world_projection": single_current_world_projection,
        "changed_value_in_authoritative_world": any(
            item.value == changed_value for item in after_context.current_observation.facts
        ),
        "unchanged_region_count": len(unchanged_keys),
        "unchanged_region_reused_count": len(reused),
        "gui_action_did_not_create_delivery_state": gui_action_did_not_create_delivery_state,
        "local_delivery_does_not_reproject_gui_effect": local_delivery_does_not_reproject_gui_effect,
        "step_delta_shared": transition_step.public_world_delta == delta,
        "workspace_reduced": bool(workspace.recent_steps and workspace.semantic_events),
        "monitor_recommendation": transition_monitor.recommendation.value,
        "local_operation": "search_page_content",
        "local_monitor_recommendation": local_monitor.recommendation.value,
        "post_transition_request_admitted": admitted.token_breakdown.estimated_input_tokens > 0,
        "post_transition_request_tokens": admitted.token_breakdown.estimated_input_tokens,
        "post_transition_request_budget": admitted.token_breakdown.as_diagnostics(),
        "post_transition_manifest_route_count": len(delivery.manifest.action_routes),
        "post_transition_obligation_group_count": len(after_context.action_delivery_plan.obligations),
        "post_transition_admitted_record_count": sum(dict(delivery.admitted_record_counts).values()),
        "post_transition_packing_backoff_count": delivery.packing_backoff_count,
        "post_transition_privacy_checked": not transition_leaks,
        "post_local_request_admitted": local_admitted.token_breakdown.estimated_input_tokens > 0,
        "post_local_request_tokens": local_admitted.token_breakdown.estimated_input_tokens,
        "post_local_request_budget": local_admitted.token_breakdown.as_diagnostics(),
        "post_local_manifest_route_count": len(local_delivery.manifest.action_routes),
        "post_local_obligation_group_count": len(local_context.action_delivery_plan.obligations),
        "post_local_admitted_record_count": sum(dict(local_delivery.admitted_record_counts).values()),
        "post_local_packing_backoff_count": local_delivery.packing_backoff_count,
        "post_local_privacy_checked": not local_leaks,
        "acceptance_errors": tuple(errors),
    }


def _agent_loop_profile_diagnostics() -> dict[str, int]:
    return {
        "max_consecutive_observation_only": DEFAULT_AGENT_LOOP_PROFILE.max_consecutive_observation_only,
        "max_recovery_retries": DEFAULT_AGENT_LOOP_PROFILE.max_recovery_retries,
    }


def _diagnostic_changed_value(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    return f"{value} [provider-free update]"


def _serialized_public_snapshot_diff(before, after) -> tuple[tuple[str, str, str], ...]:
    def snapshot(world) -> dict[tuple[str, str, str], str]:
        values: dict[tuple[str, str, str], str] = {}
        for target in world.targets:
            values[("target", target.target_id, "semantic")] = json.dumps(
                to_json_compatible((target.role, target.label, target.state, target.relations)),
                sort_keys=True,
                separators=(",", ":"),
            )
        for fact in world.facts:
            values[("fact", fact.subject_id, fact.predicate)] = json.dumps(
                to_json_compatible(fact.value),
                sort_keys=True,
                separators=(",", ":"),
            )
        return values

    prior = snapshot(before)
    current = snapshot(after)
    return tuple(sorted(key for key in prior.keys() | current.keys() if prior.get(key) != current.get(key)))


def _w1b_cost_errors(request_budget: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    delivered = int(request_budget.get("estimated_input_tokens", 0))
    if delivered > 12_000:
        errors.append("cost:new_page_over_12k")
    return tuple(errors)


def _delivery_probe_diagnostic(
    probe: DeliveryProbe,
    task: TaskGoal,
    observation,
    action_space,
    context,
    catalog,
    delivery: ModelTurnDelivery,
) -> dict[str, Any]:
    """Evaluate frozen public UI witnesses outside the production request path."""

    errors: list[str] = []
    page_text = delivery.view.text.casefold()
    identity = any(token.casefold() in page_text for token in probe.title_route_tokens)
    if not identity:
        errors.append("delivery_probe:page_identity_missing")
    directory_text = " ".join(
        " ".join(
            (
                region.heading,
                region.role,
                *region.direct_labels,
                *region.scope_path,
            )
        )
        for region in context.region_index.regions
    )
    regions = all(
        label.casefold() in page_text or label.casefold() in directory_text.casefold()
        for label in probe.required_region_labels
    )
    if not regions:
        errors.append("delivery_probe:required_region_missing")

    recoveries: list[dict[str, object]] = []
    for retrieval in probe.retrievals:
        request = resolve_grounded_tool_call(
            catalog,
            ToolCall("find_controls", {"query": retrieval.query}),
            expected_context_id=context.context_id,
            expected_delivery_id=catalog.delivery_id,
            expected_catalog_id=catalog.catalog_id,
        ).decision
        builder = ContextBuilder()
        base_page = builder.page(
            action_space,
            observation,
            region_index=context.region_index,
        )
        first_query_page = builder.page(
            action_space,
            observation,
            query=request.query,
            region_index=context.region_index,
        )
        discovery = builder.discovery_result(
            action_space,
            observation,
            first_query_page,
            region_index=context.region_index,
            canonical_world=context.canonical_world,
            grounding=context.grounding,
        )
        discovery_matches = list(discovery.matches)
        next_context = builder.build(
            task,
            observation,
            action_space,
            TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "w1b-world action discovery probe rerender",
            ),
            action_page=base_page,
            region_index=context.region_index,
            action_discovery=discovery,
        )
        packed = _diagnostic_pack(
            ModelDecisionRequest(
                request_id=f"diagnostic:retrieval:{next_context.context_id}",
                agent_context=next_context,
            )
        )
        discovery_routes = {(match.target_ref, match.operation) for match in discovery_matches}
        candidates = tuple(
            candidate
            for candidate in packed.delivery.action_candidates.candidates
            if (candidate.target_ref, candidate.operation) in discovery_routes
        )
        candidate_diagnostics = [
            (
                candidate,
                _delivery_probe_item_diagnostic(
                    candidate,
                    retrieval,
                    packed.delivery.manifest.exact_refs,
                    next_context.complete_actions,
                ),
            )
            for candidate in candidates
        ]
        page_count = 1
        cursor_cycle = False
        continued_once = False

        item_diagnostics = tuple(item for _, item in candidate_diagnostics)
        search_result_visible = bool(candidates and discovery_matches)
        label_found = any(item["label"] for item in item_diagnostics)
        kind_found = any(item["label_and_kind"] for item in item_diagnostics)
        operation_found = any(item["label_kind_operation"] for item in item_diagnostics)
        manifest_ref_visible = any(item["matched"] for item in item_diagnostics)
        joint_matches = tuple(
            item for item, diagnostic in zip(candidates, item_diagnostics, strict=True) if diagnostic["matched"]
        )
        expected_order: list[tuple[str, str]] = []
        seen_routes: set[tuple[str, str]] = set()
        for match in discovery_matches:
            identity = (match.target_ref, match.operation)
            if identity in seen_routes:
                continue
            expected_order.append(identity)
            seen_routes.add(identity)
        delivered_identities = tuple((item.target_ref, item.operation) for item in candidates)
        ordering_identity = set(delivered_identities).issubset(expected_order)
        passed = bool(search_result_visible and joint_matches and not cursor_cycle)
        if not passed:
            errors.append(f"delivery_probe:retrieval_failed:{retrieval.query}")
        recoveries.append(
            {
                "query": retrieval.query,
                "item_count": len(candidates),
                "label_found": label_found,
                "kind_found": kind_found,
                "operation_found": operation_found,
                "search_results_visible": search_result_visible,
                "manifest_ref_visible": manifest_ref_visible,
                "joint_match_count": len(joint_matches),
                "matched_refs": tuple(item.target_ref for item in joint_matches),
                "ordering_identity": ordering_identity,
                "page_count": page_count,
                "cursor_cycle": cursor_cycle,
                "owner_direct_result_path": bool(page_count and discovery_matches),
                "production_continuation_exercised": continued_once,
                "passed": passed,
            }
        )

    target_related_route = bool(recoveries and all(item["passed"] for item in recoveries))
    if not target_related_route:
        errors.append("delivery_probe:target_route_missing")
    return {
        "probe_version": WA_W1B_DELIVERY_PROBE_VERSION,
        "site_key": probe.site_key,
        "page_identity": identity,
        "required_regions": regions,
        "retrievals": tuple(recoveries),
        "target_related_route": target_related_route,
        "probe_visible_to_production": False,
        "provider_attempts": 0,
        "acceptance_errors": tuple(errors),
    }


def _candidate_diagnostic(
    probe: DeliveryProbe,
    context,
    delivery: ModelTurnDelivery,
    delivery_probe: Mapping[str, object],
    recoverability: Mapping[str, object],
    request_budget: Mapping[str, object],
) -> dict[str, object]:
    """Persist the provider-free T3.3 candidate/read-action acceptance facts."""

    candidates = delivery.action_candidates.candidates
    complete = tuple(context.complete_actions)
    complete_by_id = {item.action_id: item for item in complete}
    action_space_closure = all(
        item.action_id in complete_by_id
        and complete_by_id[item.action_id].target_ref == item.target_ref
        and tuple(destination.target_ref for destination in item.destinations)
        == tuple(destination.grounding_ref for destination in complete_by_id[item.action_id].destinations.items)
        for item in candidates
    )
    manifest_closure = all(
        item.target_ref in delivery.manifest.executable_refs
        and all(destination.target_ref in delivery.manifest.executable_refs for destination in item.destinations)
        for item in candidates
    )
    automatic_matches: list[dict[str, object]] = []
    for retrieval in probe.retrievals:
        diagnostics = tuple(
            _delivery_probe_item_diagnostic(
                item,
                retrieval,
                delivery.manifest.exact_refs,
                complete,
            )
            for item in candidates
        )
        matches = tuple(item for item, diagnostic in zip(candidates, diagnostics, strict=True) if diagnostic["matched"])
        automatic_matches.append(
            {
                "query": retrieval.query,
                "expected_path_tokens": retrieval.expected_path_tokens,
                "matched_refs": tuple(item.target_ref for item in matches),
                "matched_paths": tuple(item.functional_path for item in matches),
                "target_rank": min((item.rank for item in matches), default=None),
                "recall_at_5": bool(matches),
            }
        )
    target_recall = bool(delivery_probe.get("target_related_route"))
    target_rank = None
    retrievals = tuple(delivery_probe.get("retrievals", ()))
    ordering_identity = bool(retrievals) and all(
        isinstance(item, Mapping) and item.get("ordering_identity") is True for item in retrievals
    )
    zero_dispatch = bool(
        isinstance(recoverability.get("checks"), Mapping)
        and recoverability["checks"].get("zero_dispatch_metrics_unchanged") is True
    )
    errors: list[str] = []
    if not action_space_closure:
        errors.append("candidates:action_space_closure_failed")
    if not manifest_closure:
        errors.append("candidates:manifest_closure_failed")
    if not target_recall:
        errors.append("candidates:query_route_recall_failed")
    if not ordering_identity:
        errors.append("candidates:query_plan_coverage_failed")
    if not zero_dispatch:
        errors.append("candidates:discovery_dispatched_gui_action")
    return {
        "automatic_candidate_count": len(context.action_candidates.candidates),
        "obligation_group_count": len(context.action_delivery_plan.obligations),
        "available_record_count": sum(len(item.remaining) for item in context.action_delivery_plan.obligations),
        "admitted_record_count": sum(dict(delivery.admitted_record_counts).values()),
        "packing_backoff_count": delivery.packing_backoff_count,
        "automatic_candidates": tuple(
            {
                "target_ref": item.target_ref,
                "operation": item.operation,
                "label": item.label,
                "role": item.role,
                "functional_path": item.functional_path,
                "region_ref": item.region_ref,
                "rank": item.rank,
                "reasons": item.reasons,
            }
            for item in candidates
        ),
        "target_recall_at_5": target_recall,
        "target_rank": target_rank,
        "target_witnesses": tuple(automatic_matches),
        "candidate_manifest_closure": manifest_closure,
        "candidate_action_space_closure": action_space_closure,
        "automatic_find_controls_ordering_identity": ordering_identity,
        "candidate_region_expansion_reason": delivery.view.coverage.get("candidate_region_expansion_reason"),
        "observation_only_calls_before_candidate_execution": 0 if target_recall else None,
        "repeated_region_version_reads": 0,
        "tool_schema_tokens": int(request_budget.get("tool_schema_tokens", 0)),
        "input_request_tokens": int(request_budget.get("estimated_input_tokens", 0)),
        "discovery_gui_dispatch_count": 0 if zero_dispatch else None,
        "provider_attempts": 0,
        "acceptance_errors": tuple(errors),
    }


def _delivery_probe_item_diagnostic(
    item: object,
    probe: DeliveryRetrievalProbe,
    manifest_refs: Iterable[str],
    complete_actions: Iterable[object],
) -> dict[str, bool]:
    """Require one recovered item to close label, role, operation, and manifest."""

    destinations = tuple(getattr(item, "destinations", ()))
    endpoints = (item, *destinations)
    labels = tuple(str(getattr(endpoint, "label", "")).casefold() for endpoint in endpoints)
    roles = tuple(str(getattr(endpoint, "role", "")).casefold() for endpoint in endpoints)
    node_ref = str(getattr(item, "target_ref", ""))
    operation = str(getattr(item, "operation", ""))
    functional_paths = tuple(
        tuple(str(value).casefold() for value in getattr(endpoint, "functional_path", ())) for endpoint in endpoints
    )
    label_match = any(expected.casefold() in label for expected in probe.expected_labels for label in labels)
    kind_match = not probe.expected_kinds or any(
        role in {expected.casefold() for expected in probe.expected_kinds} for role in roles
    )
    operation_match = not probe.required_operations or any(
        expected_operation == operation
        and any(
            getattr(action, "target_ref", "") == node_ref and getattr(action, "operation", "") == expected_operation
            for action in complete_actions
        )
        for expected_operation in probe.required_operations
    )
    endpoint_refs = tuple(str(getattr(endpoint, "target_ref", "")) for endpoint in endpoints)
    manifest_set = set(manifest_refs)
    manifest_match = bool(node_ref and all(ref in manifest_set for ref in endpoint_refs if ref))
    path_match = not probe.expected_path_tokens or all(
        any(token.casefold() in component for functional_path in functional_paths for component in functional_path)
        for token in probe.expected_path_tokens
    )
    semantic_match = label_match or any(
        delivery_descriptor_matches(
            probe.query,
            label,
            (*functional_path, role, operation),
        )
        for label, role, functional_path in zip(labels, roles, functional_paths, strict=True)
    )
    return {
        "label": label_match,
        "label_and_kind": label_match and kind_match,
        "label_kind_operation": label_match and kind_match and operation_match,
        "path": path_match,
        "matched": semantic_match and operation_match and path_match and manifest_match,
    }


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
    sample_region_ref = context.canonical_world.region_refs[sample_region.key]
    query = _recoverability_query(sample_region, sample_target, observation)
    working_context = context
    working_catalog = catalog
    monitor_store = ObservationDeliveryStore()
    directory_pages = 1
    try:
        read_spec = next(item for item in working_catalog.specs if item.name == "read_region")
        region_schema = read_spec.input_schema["properties"]["region_ref"]
        if "enum" in region_schema or not PublicRefCodec.accepts(sample_region_ref, expected=PublicRefKind.REGION):
            raise ValueError("read_region must accept current R-refs returned by direct tools")
        checks["directory_tail_ref"] = True
        checks["directory_pages"] = directory_pages
    except Exception as exc:
        return _recoverability_failure("region_directory", exc)
    try:
        opened_resolution = resolve_grounded_tool_call(
            working_catalog,
            ToolCall(
                "read_region",
                {"region_ref": sample_region_ref},
                "recoverability:open",
            ),
            expected_context_id=working_context.context_id,
            expected_delivery_id=working_catalog.delivery_id,
            expected_catalog_id=working_catalog.catalog_id,
        )
        opened = opened_resolution.decision
        open_items = tuple(opened.result.get("items", ()))
        open_content = json.dumps(to_json_compatible(open_items), ensure_ascii=False)
        checks["read_region"] = bool(open_items)
        if not checks["read_region"]:
            errors.append("recoverability:read_region_empty")
        if sample_target is not None and sample_target.label and sample_target.label not in open_content:
            errors.append("recoverability:read_region_missing_target_label")
        opened_transition = monitor_store.reduce(
            StepResult(
                opened,
                observation,
                observation,
                TaskEvaluation(
                    task.task_id,
                    observation.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "w1b-world read-region recoverability",
                ),
                feedback="local_tool_result",
            ),
            step_index=directory_pages + 1,
        )
        monitor_store = opened_transition.next_store
        open_cursor = str(opened.result.get("next_cursor") or "")
        checks["tool_local_cursor"] = bool(opened.result.get("has_more")) == bool(open_cursor)
        if not checks["tool_local_cursor"]:
            errors.append("recoverability:read_region_cursor_contract")
    except Exception as exc:
        return _recoverability_failure("read_region", exc)
    if query:
        try:
            found = resolve_grounded_tool_call(
                working_catalog,
                ToolCall("search_page_content", {"query": query}, "recoverability:find"),
                expected_context_id=working_context.context_id,
                expected_delivery_id=working_catalog.delivery_id,
                expected_catalog_id=working_catalog.catalog_id,
            ).decision
            matches = tuple(found.result.get("items", ()))
            checks["find"] = bool(matches)
            if not matches:
                errors.append("recoverability:find_no_match")
            elif not any(item.get("region_ref") == sample_region_ref for item in matches if isinstance(item, Mapping)):
                errors.append("recoverability:find_wrong_region")
        except Exception as exc:
            return _recoverability_failure("find", exc)
    try:
        viewed_resolution = resolve_grounded_tool_call(
            working_catalog,
            ToolCall("list_regions", {}, "recoverability:view_all"),
            expected_context_id=working_context.context_id,
            expected_delivery_id=working_catalog.delivery_id,
            expected_catalog_id=working_catalog.catalog_id,
        )
        viewed = viewed_resolution.decision
        regions = tuple(viewed.result.get("items", ()))
        monitor_store = monitor_store.reduce(
            StepResult(
                viewed,
                observation,
                observation,
                TaskEvaluation(
                    task.task_id,
                    observation.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "w1b-world list-regions recoverability",
                ),
                feedback="local_tool_result",
            ),
            step_index=directory_pages + 1,
        ).next_store
        next_cursor = str(viewed.result.get("next_cursor") or "")
        checks["view_all"] = any(
            isinstance(item, Mapping) and item.get("region_ref") == sample_region_ref for item in regions
        ) or bool(next_cursor)
        if not checks["view_all"]:
            errors.append("recoverability:view_all_missing_regions")
        if next_cursor:
            continued = resolve_grounded_tool_call(
                working_catalog,
                ToolCall("list_regions", {"cursor": next_cursor}, "recoverability:view_all:2"),
                expected_context_id=working_context.context_id,
                expected_delivery_id=working_catalog.delivery_id,
                expected_catalog_id=working_catalog.catalog_id,
            ).decision
            checks["continuation"] = bool(continued.result.get("items", ()))
            if not checks["continuation"]:
                errors.append("recoverability:view_all_continuation_empty")
        else:
            checks["continuation"] = True
    except Exception as exc:
        return _recoverability_failure("view_all", exc)
    checks["store_has_no_result_cursor"] = tuple(item.name for item in fields(opened_transition.next_store)) == (
        "local_deliveries",
    )
    if not checks["store_has_no_result_cursor"]:
        errors.append("recoverability:store_result_cursor_present")
    try:
        resolve_grounded_tool_call(
            catalog,
            ToolCall(
                "read_region",
                {"region_ref": sample_region_ref},
                "recoverability:stale",
            ),
            expected_context_id="context:" + "0" * 64,
            expected_delivery_id=catalog.delivery_id,
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
            "region_ref": sample_region_ref,
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
        "read_region",
        "search_page_content",
        "list_regions",
        "find_controls",
        "request_evidence",
        "count_" + "children",
        "ask_user",
        "wait",
        "abort",
        "submit_final_response",
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
        "agent_loop_profile": _agent_loop_profile_diagnostics(),
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
        if PublicRefCodec.accepts(node.ref, expected=PublicRefKind.EXECUTABLE):
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
                refs.extend(
                    str(item)
                    for item in enum
                    if isinstance(item, str) and PublicRefCodec.accepts(item, expected=PublicRefKind.EXECUTABLE)
                )
    return tuple(dict.fromkeys(refs))


def _action_option_refs(context, *, complete: bool = False) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            ref
            for option in (context.complete_actions if complete else context.actions.options)
            for ref in (
                option.target_ref,
                *(item.grounding_ref for item in option.destinations.items),
            )
            if ref
        )
    )


def _capability_census(context, catalog) -> tuple[dict[str, object], ...]:
    supported = {item.semantic_action: item for item in BROWSERGYM_INTERACTION_PROFILE.capabilities}
    complete_actions = getattr(context, "complete_actions", context.actions.options)
    eligible = Counter(option.semantic_action for option in complete_actions)
    exposed = {item.name for item in catalog.specs}
    paged = "find_controls" in exposed
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
        result.append(
            {
                "semantic_action": action,
                "registry_defined": True,
                "adapter_supported": adapter_supported,
                "currently_eligible": currently_eligible,
                "model_exposed": model_exposed,
                "paged_searchable": bool(not model_exposed and paged and currently_eligible),
                "absence_reason": absence_reason,
                "subject_kinds": tuple(item.value for item in definition.subject_kinds),
                "primitive_actions": supported[action].primitive_actions if adapter_supported else (),
            }
        )
    return tuple(result)


def _action_state_metrics(context, actor_refs: Mapping[str, object]) -> dict[str, Any]:
    grounding = {item.ref: item for item in context.grounding.entities}
    required_fields = {
        "value",
        "selected_options",
        "checked",
        "selected",
        "active",
        "expanded",
        "required",
        "option_domain",
        "grid_coordinate",
    }
    retained = 0
    total = 0
    mismatches = []
    for option in context.complete_actions:
        node = actor_refs.get(option.target_ref)
        entity = grounding.get(option.target_ref)
        if node is None or entity is None or option.operation not in entity.verbs:
            mismatches.append({"ref": option.target_ref, "issue": "verb"})
            continue
        option_state = {key: value for key, value in option.target_state.items() if key in required_fields}
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


def _structural_closure_violations(
    snapshot, actor_paths: Mapping[str, tuple[object, ...]]
) -> tuple[dict[str, str], ...]:
    violations: list[dict[str, str]] = []
    control_roles = {
        "button",
        "checkbox",
        "clickable",
        "combobox",
        "draggable",
        "link",
        "listbox",
        "menuitem",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "tab",
        "textbox",
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
                if (
                    role.casefold() == "generic"
                    and not PublicRefCodec.accepts(node.ref, expected=PublicRefKind.EXECUTABLE)
                    and not node.label.strip()
                ):
                    counts["empty_generic_wrappers"] += 1
                counts["appearance_state_fields"] += sum(1 for key in node.state if str(key).startswith("appearance."))
    return dict(counts)


def _walk_actor_nodes(root):
    yield root
    for child in root.children:
        yield from _walk_actor_nodes(child)


def _private_leak_markers(
    rendered: str,
    catalog,
    admitted_envelope,
    private_binding_values: tuple[str, ...],
) -> tuple[str, ...]:
    public_tools = tuple(
        {"name": item.name, "description": item.description, "input_schema": to_json_compatible(item.input_schema)}
        for item in catalog.specs
    )
    physical_request = admitted_envelope.envelope.physical_content()
    payload = (
        rendered
        + "\n"
        + json.dumps(public_tools, sort_keys=True, ensure_ascii=False)
        + "\n"
        + json.dumps(to_json_compatible(physical_request), sort_keys=True, ensure_ascii=False)
    ).casefold()
    markers = [marker for marker in _W1B_PRIVATE_MARKERS if marker in payload]
    if any(value.casefold() in payload for value in private_binding_values if len(value) >= 4):
        markers.append("private_binding_value")
    return tuple(markers)


def _private_runtime_strings(observation) -> tuple[str, ...]:
    values: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, Mapping):
            for item in value.values():
                collect(item)
        elif isinstance(value, tuple | list):
            for item in value:
                collect(item)

    values.append(observation.observation_id)
    for source in observation.sources:
        values.extend((source.observation_id, source.revision))
    for fact in observation.facts:
        values.extend((fact.fact_id, fact.source_id))
    for binding in observation.bindings:
        values.append(binding.binding_id)
        collect(binding.payload)
    return tuple(dict.fromkeys(value for value in values if value))


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
    return len(
        json.dumps(
            to_json_compatible(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    )


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
        if isinstance(item, dict) and isinstance(item.get("health"), dict) and item["health"].get("status") != "ok"
    ]
    if unhealthy:
        errors.append(f"environment:wa_site_health_failed:{','.join(sorted(unhealthy))}")
    deployments = payload.get("deployments") if isinstance(payload.get("deployments"), list) else []
    deployment_failures = [
        f"{item.get('site')}:{item.get('status')}"
        for item in deployments
        if isinstance(item, dict) and item.get("status") not in {"match", "remote_not_inspected"}
    ]
    if len(deployments) != len(required_sites):
        errors.append("environment:wa_deployment_inspection_incomplete")
    if deployment_failures:
        errors.append(f"environment:wa_deployment_mismatch:{','.join(sorted(deployment_failures))}")
    map_integrity = payload.get("map_integrity") if isinstance(payload.get("map_integrity"), dict) else {}
    if map_integrity.get("status") != "ok":
        errors.append(f"environment:wa_map_integrity_failed:{map_integrity.get('status') or 'missing'}")
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
        "heldout_task_ids": [case.gym_id for case in WA_W1_HELD_OUT_CASES],
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
    site_urls = _configured_site_names([item for item in records if "redacted_url" in item])
    digest_sites = _configured_site_names([item for item in records if "image_digest" in item])
    required = {"shopping", "shopping_admin", "reddit", "gitlab", "map", "wikipedia"}
    return required.issubset(site_urls) and required.issubset(digest_sites)


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


def write_webarena_verified_subset(dataset_path: Path, output_path: Path, *, count: int = 30) -> dict[str, Any]:
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
    missing = [task_id for task_id in task_ids if task_id not in results and task_id not in invalid_results]
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
        "upstream_result_sha256": {str(task_id): result_digests[task_id] for task_id in sorted(result_digests)},
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
