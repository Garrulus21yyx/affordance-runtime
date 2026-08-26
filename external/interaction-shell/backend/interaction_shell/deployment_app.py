"""Concrete local BrowserGym deployment composition for the interaction shell."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from affordance_runtime.agent.decision_capability import GROUNDED_ACTION_DECISION_CAPABILITIES
from affordance_runtime.agent.observability import RunTraceSink, trace_recorder_from_environment
from affordance_runtime.app.checkpoint import SQLiteRuntimeCheckpointStore
from affordance_runtime.app.composition import compose_target_runtime
from affordance_runtime.app.public_session import (
    PublicSessionOpenError,
    PublicSessionOpenStage,
    RuntimeEnvironmentLease,
    TargetRuntimeSession,
)
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.model.policy import model_roles_from_environment
from affordance_runtime.surfaces.browsergym import (
    BrowserGymSurfaceAdapter,
    BrowserGymTaskEvaluator,
    browsergym_api_inventory,
)
from affordance_runtime.task import (
    LoopBudget,
    NaturalLanguageTaskRequest,
    RiskProfile,
    TaskBoundary,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

from .api import create_app
from .core_runtime_port import CoreRuntimeSessionPort
from .manager import RunSessionManager

logger = logging.getLogger(__name__)


@dataclass
class _DeploymentSessionCleanup:
    """Own every deployment resource created for one opaque Runtime session."""

    session_id: str
    trace_sink: RunTraceSink
    surface: BrowserGymSurfaceAdapter | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def attach_surface(self, surface: BrowserGymSurfaceAdapter) -> None:
        if self._closed or self.surface is not None:
            raise RuntimeError("deployment surface ownership is already resolved")
        self.surface = surface

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            surface_error: BaseException | None = None
            if self.surface is not None:
                try:
                    await self.surface.close()
                except BaseException as exc:
                    surface_error = exc
            flush_viewer = getattr(self.trace_sink, "flush_viewer", None)
            if callable(flush_viewer):
                try:
                    await asyncio.to_thread(flush_viewer)
                except Exception:
                    logger.exception("trace viewer cleanup failed for session %s", self.session_id)
            if surface_error is not None:
                raise surface_error


@dataclass(frozen=True)
class BrowserGymDeploymentSettings:
    task_id: str
    seed: int
    max_turns: int
    call_timeout_s: float

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> BrowserGymDeploymentSettings:
        task_id = environment.get(
            "INTERACTION_SHELL_BROWSERGYM_TASK_ID",
            "browsergym/miniwob.click-test",
        ).strip()
        if not task_id.startswith("browsergym/"):
            raise ValueError("interaction shell deployment requires a BrowserGym task ID")
        seed = _bounded_int(environment, "INTERACTION_SHELL_BROWSERGYM_SEED", 7, 0, 2**31 - 1)
        max_turns = _bounded_int(environment, "INTERACTION_SHELL_MAX_TURNS", 10, 1, 100)
        call_timeout_s = _bounded_float(
            environment,
            "INTERACTION_SHELL_MODEL_TIMEOUT_S",
            90.0,
            2.0,
            300.0,
        )
        return cls(task_id, seed, max_turns, call_timeout_s)


@dataclass(frozen=True)
class BrowserGymDeploymentSessionFactory:
    settings: BrowserGymDeploymentSettings
    environment: Mapping[str, str]
    checkpoint_store: SQLiteRuntimeCheckpointStore | None = None

    async def open(self, session_id: str, expires_at: datetime) -> TargetRuntimeSession:
        try:
            roles = model_roles_from_environment(
                self.environment,
                call_timeout_s=self.settings.call_timeout_s,
            )
            raw_trace_directory = self.environment.get("AFFORDANCE_TRACE_DIR", "").strip()
            trace_sink = trace_recorder_from_environment(
                self.environment,
                directory=(Path(raw_trace_directory) / session_id if raw_trace_directory else None),
                run_id=f"interaction-shell:{session_id}",
                session_id=session_id,
            )
        except Exception as exc:
            logger.exception("runtime composition prerequisites failed for session %s", session_id)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.RUNTIME,
                "runtime_factory_failed",
            ) from exc

        cleanup = _DeploymentSessionCleanup(session_id, trace_sink)
        try:
            surface = await _open_surface(self.settings)
        except asyncio.CancelledError:
            await cleanup.close()
            raise
        except Exception as exc:
            await cleanup.close()
            logger.exception("BrowserGym environment creation failed for session %s", session_id)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_factory_failed",
            ) from exc

        cleanup.attach_surface(surface)
        try:
            world = UnifiedWorldEnvironment((surface,))
            runtime = compose_target_runtime(
                roles.action_policy,
                ProductionActionOutcomeProjector(),
                BrowserGymTaskEvaluator(surface),
                required_decisions=GROUNDED_ACTION_DECISION_CAPABILITIES,
                trace_sink=trace_sink,
                goal_compiler=roles.goal_compiler,
            )
            lease = RuntimeEnvironmentLease(world, cleanup.close)
            return TargetRuntimeSession(
                runtime,
                lease,
                session_id,
                expires_at,
                _request_factory(
                    surface.goal_instruction,
                    self.settings.task_id,
                    self.settings.max_turns,
                ),
                self.checkpoint_store,
            )
        except Exception as exc:
            try:
                await cleanup.close()
            except Exception:
                logger.exception("resource cleanup failed after session composition failure")
            logger.exception("runtime session composition failed for session %s", session_id)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "session_initialization_failed",
            ) from exc

    def health(self) -> Mapping[str, object]:
        inventory = browsergym_api_inventory()
        model_ready = True
        try:
            model_roles_from_environment(
                self.environment,
                call_timeout_s=self.settings.call_timeout_s,
            )
        except (ImportError, ValueError):
            model_ready = False
        source_ready = bool(self.environment.get("MINIWOB_URL", "").strip())
        task_ready = self.settings.task_id in inventory.registered_task_ids
        runtime_ready = inventory.accepted and task_ready and model_ready and source_ready
        reason = (
            ""
            if runtime_ready
            else "browsergym_profile_unavailable"
            if not inventory.accepted or not task_ready
            else "runtime_factory_unavailable"
            if not model_ready
            else "environment_source_unavailable"
        )
        return {
            "status": "ok" if runtime_ready else "degraded",
            "runtime_execution": {
                "status": "available" if runtime_ready else "unavailable",
                "profile": "local_browsergym",
                "reason_code": reason,
            },
            "viewer": {
                "status": "unavailable",
                "reason_code": "viewer_provider_not_configured",
            },
            "durable_resume": {
                "status": "unavailable",
                "reason_code": "environment_reconnect_not_implemented",
            },
            "durable_pause": {
                "status": "available" if self.checkpoint_store is not None else "unavailable",
                "reason_code": "" if self.checkpoint_store is not None else "checkpoint_store_not_configured",
            },
        }


async def _open_surface(
    settings: BrowserGymDeploymentSettings,
) -> BrowserGymSurfaceAdapter:
    """Finish a non-cancellable sync open and recover its surface on request cancellation."""

    opening = asyncio.create_task(
        asyncio.to_thread(BrowserGymSurfaceAdapter.open, settings.task_id, settings.seed)
    )
    try:
        return await asyncio.shield(opening)
    except asyncio.CancelledError:
        try:
            surface = await opening
        except BaseException:
            pass
        else:
            try:
                await surface.close()
            except Exception:
                logger.exception("BrowserGym cleanup failed after session-open cancellation")
        raise


def _request_factory(goal: str, task_id: str, max_turns: int):
    def create(session_id: str, instruction: str) -> NaturalLanguageTaskRequest:
        if instruction.strip() != goal.strip():
            raise ValueError("task instruction must match the active BrowserGym environment goal")
        return NaturalLanguageTaskRequest(
            session_id,
            instruction,
            TaskBoundary(
                allowed_effects=("external_ui_interaction",),
                forbidden_effects=("external_network_side_effect", "credential_use"),
                risk_profile=RiskProfile.LOW,
                loop_budget=LoopBudget(max_turns=max_turns, max_observations=max_turns * 2),
            ),
            source_ref=f"interaction-shell:{task_id}:goal",
        )

    return create


def _bounded_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environment.get(name, "").strip()
    try:
        value = default if not raw else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be within [{minimum}, {maximum}]")
    return value


def _bounded_float(
    environment: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = environment.get(name, "").strip()
    try:
        value = default if not raw else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be within [{minimum}, {maximum}]")
    return value


def _load_project_environment() -> None:
    configured = os.environ.get("INTERACTION_SHELL_ENV_FILE", "").strip()
    repository = Path(__file__).resolve().parents[4]
    candidates = (
        Path(configured) if configured else None,
        repository / ".env",
        repository.parent / "affordance-runtime" / ".env",
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            load_dotenv(candidate, override=False)
            return


_load_project_environment()
_deployment_environment = dict(os.environ)
settings = BrowserGymDeploymentSettings.from_environment(_deployment_environment)
_configured_checkpoint_path = _deployment_environment.get(
    "INTERACTION_SHELL_CHECKPOINT_DB", ""
).strip()
_checkpoint_path = (
    Path(_configured_checkpoint_path)
    if _configured_checkpoint_path
    else Path(__file__).resolve().parents[4]
    / ".runtime"
    / "interaction-shell-checkpoints.sqlite3"
)
session_factory = BrowserGymDeploymentSessionFactory(
    settings,
    _deployment_environment,
    SQLiteRuntimeCheckpointStore(_checkpoint_path),
)
app = create_app(
    RunSessionManager(CoreRuntimeSessionPort(session_factory)),
    health_provider=session_factory.health,
)
