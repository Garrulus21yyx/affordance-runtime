"""Concrete local or Steel-connected open-browser interaction-shell deployment."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from affordance_runtime.agent.decision_capability import GROUNDED_ACTION_DECISION_CAPABILITIES
from affordance_runtime.agent.observability import RunTraceSink, trace_recorder_from_environment
from affordance_runtime.app.checkpoint import SQLiteRuntimeCheckpointStore
from affordance_runtime.app.composition import compose_target_runtime
from affordance_runtime.app.interactive_environment import (
    InteractiveTaskEnvironment,
    InteractiveTaskEvaluator,
)
from affordance_runtime.app.public_session import (
    PublicSessionOpenError,
    PublicSessionOpenStage,
    RuntimeEnvironmentLease,
    RuntimeRecoveryAttempt,
    RuntimeRecoveryInspection,
    TargetRuntimeSession,
    TargetRuntimeSessionFactory,
)
from affordance_runtime.benchmarks.lab import BenchmarkLabManager
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.model.policy import model_roles_from_environment
from affordance_runtime.surfaces.browser_bundle import browser_surface_from_environment
from affordance_runtime.surfaces.dom.thread_session import ThreadBoundBrowserSession
from affordance_runtime.task import (
    LoopBudget,
    NaturalLanguageTaskRequest,
    RiskProfile,
    TaskBoundary,
)
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from dotenv import load_dotenv

from .api import create_app
from .assistant import PydanticAssistantTurnRunner
from .assistant_port import AssistantSessionPort
from .completed_runs import CompletedRunSummaryResolver
from .content_filtering import (
    PINNED_UBOL_COMPLETE_PATCH_ID,
    PINNED_UBOL_VERSION,
    ContentFilterProfile,
    CosmeticFilterExtensionAttestation,
)
from .core_runtime_port import CoreRuntimeSessionPort, unavailable_viewer
from .manager import RunSessionManager
from .session_registry import SQLiteSessionRecoveryRegistry
from .steel_viewer import SteelBrowserLease, SteelViewerGateway, SteelViewerUnavailable

if TYPE_CHECKING:
    from pydantic_ai_harness.step_persistence import StepStore

logger = logging.getLogger(__name__)


@dataclass
class _DeploymentSessionCleanup:
    """Own every deployment resource created for one opaque Runtime session."""

    session_id: str
    trace_sink: RunTraceSink
    viewer_gateway: SteelViewerGateway | None = None
    viewer_lease: SteelBrowserLease | None = None
    browser: ThreadBoundBrowserSession | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def attach_browser(self, browser: ThreadBoundBrowserSession) -> None:
        if self._closed or self.browser is not None:
            raise RuntimeError("deployment browser ownership is already resolved")
        self.browser = browser

    def attach_viewer(self, lease: SteelBrowserLease) -> None:
        if self._closed or self.viewer_lease is not None or self.viewer_gateway is None:
            raise RuntimeError("deployment viewer ownership is already resolved")
        self.viewer_lease = lease

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            browser_error: BaseException | None = None
            if self.browser is not None:
                try:
                    await asyncio.to_thread(self.browser.close)
                except BaseException as exc:  # noqa: BLE001 - finish all cleanup owners
                    browser_error = exc
            if self.viewer_gateway is not None and self.viewer_lease is not None:
                await self.viewer_gateway.release(self.viewer_lease)
            flush_viewer = getattr(self.trace_sink, "flush_viewer", None)
            if callable(flush_viewer):
                try:
                    await asyncio.to_thread(flush_viewer)
                except Exception:
                    logger.exception("trace viewer cleanup failed for session %s", self.session_id)
            if browser_error is not None:
                raise browser_error


@dataclass(frozen=True)
class BrowserDeploymentSettings:
    initial_url: str
    max_turns: int
    call_timeout_s: float
    browser_provider: str = "local"
    content_filter_profile: ContentFilterProfile = ContentFilterProfile.OFF
    cosmetic_filter_extension: CosmeticFilterExtensionAttestation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content_filter_profile, ContentFilterProfile):
            raise TypeError("content filter profile must be typed")
        if (
            self.browser_provider == "local"
            and self.content_filter_profile is not ContentFilterProfile.OFF
        ):
            raise ValueError("local browser provider supports content filtering off only")

    @property
    def content_filter_trace_identity(self) -> dict[str, object]:
        if self.content_filter_profile is ContentFilterProfile.OFF:
            engine_id, engine_version, ruleset_digest = "none", "", ""
        elif self.content_filter_profile is ContentFilterProfile.NETWORK_ADS:
            engine_id, engine_version, ruleset_digest = (
                "steel.block_ads",
                "provider-managed",
                "",
            )
        else:
            artifact_digest = (
                self.cosmetic_filter_extension.artifact_sha256
                if self.cosmetic_filter_extension is not None
                else ""
            )
            engine_id, engine_version, ruleset_digest = (
                "ublock-origin-lite",
                f"{PINNED_UBOL_VERSION}+{PINNED_UBOL_COMPLETE_PATCH_ID}",
                f"sha256:{artifact_digest}" if artifact_digest else "",
            )
        return {
            "content_filter_profile": self.content_filter_profile.value,
            "content_filter_engine_id": engine_id,
            "content_filter_engine_version": engine_version,
            "content_filter_ruleset_digest": ruleset_digest,
            "content_filter_extension_configured": self.cosmetic_filter_extension is not None,
        }

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> BrowserDeploymentSettings:
        initial_url = environment.get(
            "INTERACTION_SHELL_BROWSER_INITIAL_URL",
            "about:blank",
        ).strip()
        if not _valid_initial_url(initial_url):
            raise ValueError(
                "INTERACTION_SHELL_BROWSER_INITIAL_URL must be about:blank or an HTTP(S) URL"
            )
        max_turns = _bounded_int(environment, "INTERACTION_SHELL_MAX_TURNS", 10, 1, 100)
        call_timeout_s = _bounded_float(
            environment,
            "INTERACTION_SHELL_MODEL_TIMEOUT_S",
            90.0,
            2.0,
            300.0,
        )
        browser_provider = (
            environment.get(
                "INTERACTION_SHELL_BROWSER_PROVIDER",
                "local",
            )
            .strip()
            .lower()
        )
        if browser_provider not in {"local", "steel"}:
            raise ValueError("INTERACTION_SHELL_BROWSER_PROVIDER must be local or steel")
        configured_filter_profile = environment.get(
            "INTERACTION_SHELL_CONTENT_FILTER_PROFILE",
            ContentFilterProfile.OFF.value,
        ).strip()
        try:
            content_filter_profile = ContentFilterProfile(configured_filter_profile)
        except ValueError as exc:
            supported = ", ".join(profile.value for profile in ContentFilterProfile)
            raise ValueError(
                f"INTERACTION_SHELL_CONTENT_FILTER_PROFILE must be one of: {supported}"
            ) from exc
        cosmetic_filter_extension = CosmeticFilterExtensionAttestation.from_environment(
            environment
        )
        return cls(
            initial_url,
            max_turns,
            call_timeout_s,
            browser_provider,
            content_filter_profile,
            cosmetic_filter_extension,
        )


@dataclass(frozen=True)
class BrowserDeploymentSessionFactory:
    settings: BrowserDeploymentSettings
    environment: Mapping[str, str]
    checkpoint_store: SQLiteRuntimeCheckpointStore | None = None
    viewer_gateway: SteelViewerGateway | None = None
    _target_factory: TargetRuntimeSessionFactory = field(init=False, repr=False)

    def __post_init__(self) -> None:
        def unavailable_runtime(session_id: str):
            del session_id
            raise RuntimeError("deployment recovery runtime is unavailable without a reconnector")

        def unavailable_environment(session_id: str):
            del session_id
            raise RuntimeError(
                "deployment recovery environment is unavailable without a reconnector"
            )

        object.__setattr__(
            self,
            "_target_factory",
            TargetRuntimeSessionFactory(
                unavailable_runtime,
                unavailable_environment,
                checkpoint_store=self.checkpoint_store,
                environment_reconnector=None,
            ),
        )

    async def open(self, session_id: str, expires_at: datetime) -> TargetRuntimeSession:
        try:
            roles = model_roles_from_environment(
                self.environment,
                call_timeout_s=self.settings.call_timeout_s,
                action_step_store=_model_step_store(
                    self.checkpoint_store,
                    session_id,
                ),
                conversation_id=session_id,
            )
            raw_trace_directory = self.environment.get("AFFORDANCE_TRACE_DIR", "").strip()
            trace_sink = trace_recorder_from_environment(
                self.environment,
                directory=(Path(raw_trace_directory) / session_id if raw_trace_directory else None),
                run_id=f"interaction-shell:{session_id}",
                session_id=session_id,
                analysis_identity=self.settings.content_filter_trace_identity,
            )
        except Exception as exc:
            logger.exception("runtime composition prerequisites failed for session %s", session_id)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.RUNTIME,
                "runtime_factory_failed",
            ) from exc

        cleanup = _DeploymentSessionCleanup(
            session_id,
            trace_sink,
            viewer_gateway=self.viewer_gateway,
        )
        viewer_lease: SteelBrowserLease | None = None
        if self.settings.browser_provider == "steel":
            if self.viewer_gateway is None:
                await cleanup.close()
                raise PublicSessionOpenError(
                    PublicSessionOpenStage.ENVIRONMENT,
                    "viewer_api_key_missing",
                )
            try:
                viewer_lease = await self.viewer_gateway.open(session_id, expires_at)
                try:
                    cleanup.attach_viewer(viewer_lease)
                except BaseException:
                    await self.viewer_gateway.release(viewer_lease)
                    raise
            except PublicSessionOpenError:
                raise
            except SteelViewerUnavailable as exc:
                await cleanup.close()
                raise PublicSessionOpenError(
                    PublicSessionOpenStage.ENVIRONMENT,
                    exc.code,
                ) from exc
            except Exception as exc:
                await cleanup.close()
                logger.exception(
                    "Steel environment lease creation failed for session %s", session_id
                )
                raise PublicSessionOpenError(
                    PublicSessionOpenStage.ENVIRONMENT,
                    "environment_factory_failed",
                ) from exc
        try:
            browser = await _open_browser(
                self.settings,
                self.viewer_gateway,
                viewer_lease,
            )
        except asyncio.CancelledError:
            await cleanup.close()
            raise
        except Exception as exc:
            await cleanup.close()
            logger.exception("browser environment creation failed for session %s", session_id)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_factory_failed",
            ) from exc

        cleanup.attach_browser(browser)
        try:
            surface = browser_surface_from_environment(browser, self.environment)
            world = InteractiveTaskEnvironment(UnifiedWorldEnvironment((surface,)))
            runtime = compose_target_runtime(
                roles.action_policy,
                ProductionActionOutcomeProjector(),
                InteractiveTaskEvaluator(world),
                required_decisions=GROUNDED_ACTION_DECISION_CAPABILITIES,
                trace_sink=trace_sink,
                goal_compiler=roles.goal_compiler,
                task_revision_compiler=roles.task_revision_compiler,
            )
            lease = RuntimeEnvironmentLease(cast(WorldEnvironment, world), cleanup.close)
            session = await self._target_factory.open_prepared(
                session_id,
                expires_at,
                runtime,
                lease,
                request_factory=_request_factory(self.settings.max_turns),
            )
            if self.viewer_gateway is not None and viewer_lease is not None:
                self.viewer_gateway.attach(session, viewer_lease)
            return session
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

    async def recover(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> TargetRuntimeSession:
        return await self._target_factory.recover(session_id, checkpoint_id, expires_at)

    async def inspect(self, session_id: str) -> RuntimeRecoveryInspection:
        return await self._target_factory.inspect(session_id)

    async def recover_typed(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> RuntimeRecoveryAttempt:
        return await self._target_factory.recover_typed(
            session_id,
            checkpoint_id,
            expires_at,
        )

    def health(self) -> Mapping[str, object]:
        model_ready = True
        try:
            model_roles_from_environment(
                self.environment,
                call_timeout_s=self.settings.call_timeout_s,
            )
        except (ImportError, ValueError):
            model_ready = False
        viewer_key_ready = self.viewer_gateway is not None
        steel_ready = self.settings.browser_provider != "steel" or viewer_key_ready
        runtime_ready = model_ready and steel_ready
        reason = (
            ""
            if runtime_ready
            else "runtime_factory_unavailable"
            if not model_ready
            else "viewer_api_key_missing"
        )
        viewer_ready = runtime_ready and self.settings.browser_provider == "steel"
        viewer_reason = (
            ""
            if viewer_ready
            else "viewer_runtime_profile_not_enabled"
            if self.settings.browser_provider != "steel"
            else "viewer_api_key_missing"
            if not viewer_key_ready
            else "viewer_provider_unavailable"
        )
        return {
            "status": "ok" if runtime_ready else "degraded",
            "runtime_execution": {
                "status": "available" if runtime_ready else "unavailable",
                "profile": (
                    "steel_open_browser"
                    if self.settings.browser_provider == "steel"
                    else "local_open_browser"
                ),
                "reason_code": reason,
            },
            "viewer": {
                "status": "available" if viewer_ready else "unavailable",
                "provider": "steel" if viewer_ready else None,
                "read_only": True,
                "reason_code": viewer_reason,
            },
            "durable_resume": {
                "status": "unavailable",
                "reason_code": "environment_reconnect_not_implemented",
            },
            "durable_pause": {
                "status": "available" if self.checkpoint_store is not None else "unavailable",
                "reason_code": ""
                if self.checkpoint_store is not None
                else "checkpoint_store_not_configured",
            },
        }


async def _open_browser(
    settings: BrowserDeploymentSettings,
    viewer_gateway: SteelViewerGateway | None = None,
    viewer_lease: SteelBrowserLease | None = None,
) -> ThreadBoundBrowserSession:
    """Connect one browser owner and recover it if session opening is cancelled."""

    playwright_factory = None
    if viewer_gateway is not None and viewer_lease is not None:
        playwright_factory = viewer_gateway.environment_playwright_factory(viewer_lease)
    opening = asyncio.create_task(
        asyncio.to_thread(
            ThreadBoundBrowserSession.launch,
            settings.initial_url,
            headless=settings.browser_provider != "steel",
            environment_playwright_factory=playwright_factory,
            rendered_dom_only=settings.content_filter_profile.requires_cosmetic_filtering,
        )
    )
    try:
        return await asyncio.shield(opening)
    except asyncio.CancelledError:
        try:
            browser = await opening
        except BaseException:  # noqa: BLE001, S110 - the primary cancellation wins
            pass
        else:
            try:
                await asyncio.to_thread(browser.close)
            except Exception:
                logger.exception("browser cleanup failed after session-open cancellation")
        raise


def _request_factory(max_turns: int):
    def create(session_id: str, instruction: str) -> NaturalLanguageTaskRequest:
        return NaturalLanguageTaskRequest(
            session_id,
            instruction,
            TaskBoundary(
                allowed_effects=("external_ui_interaction",),
                forbidden_effects=("external_network_side_effect", "credential_use"),
                risk_profile=RiskProfile.LOW,
                loop_budget=LoopBudget(max_turns=max_turns, max_observations=max_turns * 2),
            ),
            source_ref="interaction-shell:open-browser:goal",
        )

    return create


def _model_step_store(
    checkpoint_store: SQLiteRuntimeCheckpointStore | None,
    session_id: str,
) -> StepStore | None:
    if checkpoint_store is None:
        return None
    from pydantic_ai_harness.step_persistence import SqliteStepStore

    session_digest = hashlib.sha256(session_id.encode()).hexdigest()
    model_store_directory = checkpoint_store.path.parent / (
        checkpoint_store.path.name + ".model-steps"
    )
    return SqliteStepStore(
        database=model_store_directory / f"{session_digest}.sqlite3",
        max_snapshots_per_run=2,
    )


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


def _valid_initial_url(value: str) -> bool:
    if value == "about:blank":
        return True
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


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
settings = BrowserDeploymentSettings.from_environment(_deployment_environment)
_configured_checkpoint_path = _deployment_environment.get(
    "INTERACTION_SHELL_CHECKPOINT_DB", ""
).strip()
_checkpoint_path = (
    Path(_configured_checkpoint_path)
    if _configured_checkpoint_path
    else Path(__file__).resolve().parents[4] / ".runtime" / "interaction-shell-checkpoints.sqlite3"
)
_viewer_key = (
    _deployment_environment.get("Viewer_API_KEY", "").strip()
    or _deployment_environment.get("STEEL_API_KEY", "").strip()
)
viewer_gateway = (
    SteelViewerGateway(
        _viewer_key,
        maximum_session_timeout_ms=_bounded_int(
            _deployment_environment,
            "INTERACTION_SHELL_STEEL_MAX_SESSION_TIMEOUT_MS",
            900_000,
            60_000,
            86_400_000,
        ),
        content_filter_profile=settings.content_filter_profile,
        cosmetic_filter_extension=settings.cosmetic_filter_extension,
    )
    if settings.browser_provider == "steel" and _viewer_key
    else None
)
session_factory = BrowserDeploymentSessionFactory(
    settings,
    _deployment_environment,
    SQLiteRuntimeCheckpointStore(_checkpoint_path),
    viewer_gateway,
)
gui_runtime_port = CoreRuntimeSessionPort(
    session_factory,
    surface_projector=(
        viewer_gateway.project if viewer_gateway is not None else unavailable_viewer
    ),
)
assistant_runner = PydanticAssistantTurnRunner.from_environment(
    _deployment_environment,
    database_directory=_checkpoint_path.parent
    / (_checkpoint_path.name + ".assistant"),
    call_timeout_s=settings.call_timeout_s,
)
runtime_port = AssistantSessionPort(assistant_runner, gui_runtime_port)


def _deployment_health() -> Mapping[str, object]:
    health = dict(session_factory.health())
    health["assistant"] = {
        "status": "available",
        "profile": (
            _deployment_environment.get("INTERACTION_SHELL_ASSISTANT_PROFILE", "").strip()
            or _deployment_environment.get("LLM_ACTIVE_PROFILE", "").strip()
        ),
        "native_web_search": assistant_runner.native_web_search,
        "persistent_memory": assistant_runner.memory_store is not None,
    }
    return health


app = create_app(
    RunSessionManager(
        runtime_port,
        SQLiteSessionRecoveryRegistry(_checkpoint_path),
    ),
    health_provider=_deployment_health,
    viewer_gateway=viewer_gateway,
    completed_run_resolver=CompletedRunSummaryResolver.from_environment(_deployment_environment),
    evidence_access_key=_deployment_environment.get("INTERACTION_SHELL_EVIDENCE_ACCESS_KEY", ""),
    lab_manager=BenchmarkLabManager(
        Path(
            _deployment_environment.get(
                "INTERACTION_SHELL_LABS_EVIDENCE_ROOT",
                str(Path(__file__).resolve().parents[4] / "evidence" / "live"),
            )
        ),
        environment=_deployment_environment,
    ),
)
