"""Benchmark case admission, dependency, and mechanical verifier policy boundary."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Protocol

from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.surfaces.browsergym.environment import (
    BrowserGymPort,
    BrowserGymSurfaceAdapter,
)
from affordance_runtime.surfaces.visual.disambiguation import VisualCandidateDisambiguatorPort
from affordance_runtime.surfaces.visual.grounding import VisualGrounderPort, VisualRegionProposerPort
from affordance_runtime.surfaces.visual.predicate_classification import VisualPredicateClassifierPort
from affordance_runtime.task import (
    LoopBudget,
    NaturalLanguageTaskRequest,
    ReadyTask,
    RiskProfile,
    TaskBoundary,
    TaskGoal,
    ThinTaskIntake,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


@dataclass(frozen=True)
class ExternalDependencyStatus:
    available: bool
    package_name: str
    package_version: str
    target_loop_adapter_ready: bool


class ExternalVerifierStatus(StrEnum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    TERMINAL_TASK_FAILURE = "terminal_task_failure"
    UNAVAILABLE = "unavailable"


class VerifierFactSource(StrEnum):
    RESET = "reset"
    POST_ACTION = "post_action"
    READ_ONLY_PROBE = "read_only_probe"


class ExternalVerifierReason(StrEnum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_RUNNING = "verified_running"
    VERIFIED_TERMINAL_TASK_FAILURE = "verified_terminal_task_failure"
    MISSING_FACTS = "missing_facts"
    INVALID_FACTS = "invalid_facts"
    NON_FINITE_FACTS = "non_finite_facts"
    INCONSISTENT_FACTS = "inconsistent_facts"
    SOURCE_INSUFFICIENT = "source_insufficient"
    UNSUPPORTED_STATE = "unsupported_state"


@dataclass(frozen=True)
class ExternalVerifierResult:
    source: VerifierFactSource
    status: ExternalVerifierStatus
    reason: ExternalVerifierReason
    observation_id: str
    source_observation_id: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        from affordance_runtime.evaluation.evidence import validate_evidence_refs

        if not isinstance(self.source, VerifierFactSource):
            raise TypeError("external verifier source must be typed")
        if not isinstance(self.status, ExternalVerifierStatus):
            raise TypeError("external verifier status must be typed")
        if not isinstance(self.reason, ExternalVerifierReason):
            raise TypeError("external verifier reason must be typed")
        if (
            not isinstance(self.observation_id, str)
            or not isinstance(self.source_observation_id, str)
            or not self.observation_id.strip()
            or not self.source_observation_id.strip()
        ):
            raise ValueError("external verifier result requires observation lineage")
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=True),
        )
        expected_reason = {
            ExternalVerifierStatus.SUCCESS: ExternalVerifierReason.VERIFIED_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: ExternalVerifierReason.VERIFIED_RUNNING,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: (ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE),
        }.get(self.status)
        if expected_reason is not None and self.reason is not expected_reason:
            raise ValueError("external verifier status and reason conflict")
        terminal = self.status in {
            ExternalVerifierStatus.SUCCESS,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
        }
        if terminal != bool(self.evidence_refs):
            raise ValueError("external verifier terminal proof is inconsistent")


class ExternalVerifierPort(Protocol):
    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult: ...


@dataclass
class BrowserGymCaseEnvironment:
    """Benchmark case policy around the reusable BrowserGym surface."""

    benchmark_task_id: str
    surface: BrowserGymSurfaceAdapter
    world: UnifiedWorldEnvironment
    verifier_queries: int = 0
    official_success_count: int = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.surface, name)

    @property
    def observation_capabilities(self):
        return self.world.observation_capabilities

    async def reset(self, task):
        return await self.world.reset(task)

    async def revise_task(self, task):
        return await self.world.revise_task(task)

    async def capture(self, request):
        return await self.world.capture(request)

    async def execute(self, request):
        return await self.world.execute(request)

    async def execute_form_fields(self, command):
        return await self.world.execute_form_fields(command)

    def is_current(self, request):
        return self.world.is_current(request)

    async def close(self) -> None:
        await self.surface.close()

    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
        if benchmark_task_id != self.benchmark_task_id:
            raise ValueError("mechanical verifier request does not match the benchmark case")
        from affordance_runtime.benchmarks.external_smoke.verifier_policy import (
            as_external_result,
            assess_browsergym_task_state,
        )

        self.verifier_queries += 1
        result = as_external_result(assess_browsergym_task_state(self.surface.current_task_state()))
        if result.status is ExternalVerifierStatus.SUCCESS:
            self.official_success_count += 1
        return result


def open_browsergym_case(
    benchmark_task_id: str,
    seed: int,
    *,
    gym_factory: Callable[..., BrowserGymPort] | None = None,
    max_turns: int = 20,
    admitted_task_ids: frozenset[str] | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
    visual_point_grounder: VisualGrounderPort | None = None,
    visual_candidate_disambiguator: VisualCandidateDisambiguatorPort | None = None,
    visual_predicate_classifier: VisualPredicateClassifierPort | None = None,
    marked_candidate_policy_available: bool = False,
) -> tuple[BrowserGymCaseEnvironment, TaskGoal]:
    """Admit one reviewed benchmark case and bind it to the generic surface."""

    from affordance_runtime.benchmarks.external_smoke.manifest import REVIEWED_TASK_IDS

    admitted = frozenset(REVIEWED_TASK_IDS) if admitted_task_ids is None else admitted_task_ids
    if benchmark_task_id not in admitted:
        raise ValueError("BrowserGym task ID is outside the reviewed fixed manifest")
    surface = BrowserGymSurfaceAdapter.open(
        benchmark_task_id,
        seed,
        gym_factory=gym_factory,
        visual_region_proposer=visual_region_proposer,
        visual_point_grounder=visual_point_grounder,
        visual_candidate_disambiguator=visual_candidate_disambiguator,
        visual_predicate_classifier=visual_predicate_classifier,
        marked_candidate_policy_available=marked_candidate_policy_available,
    )
    try:
        intake = ThinTaskIntake().compile(
            NaturalLanguageTaskRequest(
                f"task:{uuid.uuid4().hex}",
                surface.goal_instruction,
                TaskBoundary(
                    allowed_effects=("external_ui_interaction",),
                    forbidden_effects=("external_network_side_effect", "credential_use"),
                    risk_profile=RiskProfile.LOW,
                    loop_budget=LoopBudget(
                        max_turns=max_turns,
                        max_observations=max_turns * 2,
                    ),
                ),
                source_ref=f"browsergym:{benchmark_task_id}:goal",
            )
        )
        if not isinstance(intake, ReadyTask):
            raise RuntimeError(f"BrowserGym task intake rejected its reviewed profile: {intake.status.value}")
        return BrowserGymCaseEnvironment(
            benchmark_task_id,
            surface,
            UnifiedWorldEnvironment((surface,)),
        ), intake.task
    except BaseException:
        surface.gym_environment.close()
        raise


@dataclass(frozen=True)
class ExternalEnvironmentTaskEvaluator:
    benchmark_task_id: str
    verifier: ExternalVerifierPort

    async def evaluate(self, task, observation) -> TaskEvaluation:
        verifier_result = self.verifier.current_result(self.benchmark_task_id)
        current_source_ids = {item.observation_id for item in observation.sources}
        verifier_lineage = {
            verifier_result.observation_id,
            verifier_result.source_observation_id,
        }
        if not (
            verifier_lineage == {observation.observation_id}
            or len(verifier_lineage) == 1
            and verifier_result.source_observation_id in current_source_ids
        ):
            verifier_result = ExternalVerifierResult(
                verifier_result.source,
                ExternalVerifierStatus.UNAVAILABLE,
                ExternalVerifierReason.SOURCE_INSUFFICIENT,
                observation.observation_id,
                observation.observation_id,
            )
        mapped = {
            ExternalVerifierStatus.SUCCESS: TaskEvaluationStatus.COMPLETE,
            ExternalVerifierStatus.INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: TaskEvaluationStatus.BLOCKED,
            ExternalVerifierStatus.UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
        }[verifier_result.status]
        from affordance_runtime.evaluation import TaskOutcomeFact, TaskOutcomeKind

        outcome_kind = {
            ExternalVerifierStatus.SUCCESS: TaskOutcomeKind.TERMINAL_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: TaskOutcomeKind.RUNNING_INCOMPLETE,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: TaskOutcomeKind.TERMINAL_FAILURE,
            ExternalVerifierStatus.UNAVAILABLE: TaskOutcomeKind.VERIFIER_UNAVAILABLE,
        }[verifier_result.status]
        refs = verifier_result.evidence_refs
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            mapped,
            f"environment-native verifier: {verifier_result.reason.value}",
            completion_evidence_refs=(refs if outcome_kind is TaskOutcomeKind.TERMINAL_SUCCESS else ()),
            outcome=TaskOutcomeFact(outcome_kind, verifier_result.reason.value, refs),
        )


def external_dependency_status(adapter_attestation: Path | None = None) -> ExternalDependencyStatus:
    try:
        installed = version("browsergym-miniwob")
    except PackageNotFoundError:
        return ExternalDependencyStatus(False, "browsergym-miniwob", "", False)
    path = adapter_attestation
    if path is None and os.environ.get("BROWSERGYM_ADAPTER_CONFORMANCE_ATTESTATION"):
        path = Path(os.environ["BROWSERGYM_ADAPTER_CONFORMANCE_ATTESTATION"])
    ready = _adapter_attestation_ready(path, installed) if path is not None else False
    return ExternalDependencyStatus(True, "browsergym-miniwob", installed, ready)


def _adapter_attestation_ready(path: Path, installed: str) -> bool:
    from affordance_runtime.benchmarks.external_smoke.manifest import (
        EXTERNAL_SMOKE_MANIFEST,
        REVIEWED_TASK_IDS,
        SOURCE_COMMIT,
        external_manifest_digest,
    )

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(value, dict)
        and value.get("accepted") is True
        and value.get("git_dirty") is False
        and value.get("package_version") == installed == EXTERNAL_SMOKE_MANIFEST.package_version
        and value.get("source_commit") == SOURCE_COMMIT
        and value.get("manifest_digest") == external_manifest_digest(EXTERNAL_SMOKE_MANIFEST)
        and tuple(value.get("task_ids", ())) == REVIEWED_TASK_IDS
        and value.get("target_loop_adapter_ready") is True
    )
