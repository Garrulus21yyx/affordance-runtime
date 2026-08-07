"""P5-3 BrowserGym compatibility planner and external-policy episode path."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.browsergym_action_schema import BrowserGymAction
from affordance_runtime.benchmarks.browsergym_dom import browsergym_dom_adapter, browsergym_svg_observer
from affordance_runtime.benchmarks.browsergym_encoder import GeneralistBrowserGymRouteEncoder
from affordance_runtime.benchmarks.browsergym_episode_runner import (
    BROWSERGYM_TERMINAL_COMPLETION_POLICY,
    BrowserGymExecutor,
    _accessibility_tree_text,
    _browsergym_browser_version,
    _browsergym_proposal,
    _browsergym_request_locator,
    _close_quietly,
    _goal_text,
)
from affordance_runtime.benchmarks.browsergym_observer import BrowserGymObserver
from affordance_runtime.benchmarks.browsergym_types import (
    BROWSERGYM_SUCCESS_CRITERION_ID,
    BrowserGymEnvironment,
    BrowserGymEpisodeResult,
    BrowserGymEpisodeState,
    BrowserGymPolicy,
    BrowserGymPolicyRequest,
)
from affordance_runtime.benchmarks.composition import compose_benchmark_run_coordinator as compose_run_coordinator
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.coordinator import RunBudget
from affordance_runtime.generalist_planner import (
    GeneralistLMPlanner,
    GeneralistPlannerProfile,
    PlannerLimits,
)
from affordance_runtime.model_port import ModelConfig, ModelPort
from affordance_runtime.planning import PlannerProposalProvenance, PlannerProposalSource
from affordance_runtime.planning_contracts import PlannerDoneResponse, PlannerProposalResponse, PlannerResponse
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RuntimeStep, legacy_run_request
from affordance_runtime.simplified_runtime_contracts import SPATIAL_POINT_CAPABILITY
from affordance_runtime.step_choice_planner import STEP_CHOICE_PROMPT_VERSION, StrictStepChoicePlanner
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import SuccessExpression


@dataclass
class BrowserGymPlanner:
    policy: BrowserGymPolicy
    episode: BrowserGymEpisodeState
    bindings: dict[str, BrowserGymAction]

    def propose(self, request: PlanningRequest) -> PlannerResponse:
        terminal = _browsergym_terminal_response(self.episode)
        if terminal is not None:
            return terminal
        policy_request = BrowserGymPolicyRequest(
            task_id=self.episode.task_id,
            seed=self.episode.seed,
            goal=self.episode.goal,
            step=len(self.episode.actions),
            affordances=[
                {
                    "id": item.target_id,
                    "role": item.role,
                    "label": item.label,
                    "action": item.supported_actions[0] if item.supported_actions else "",
                    "locator": _browsergym_request_locator(item.label, self.episode.observation),
                    "confidence": item.confidence,
                }
                for item in request.observation.affordances
            ],
            previous_actions=[asdict(action) for action in self.episode.actions],
            accessibility_tree=_accessibility_tree_text(self.episode.observation),
        )
        action = self.policy.propose(policy_request)
        if action is None:
            return PlannerDoneResponse(
                result={
                    "status": "incomplete",
                    "official_success": False,
                    "official_reward": self.episode.reward,
                    "terminated": False,
                    "truncated": False,
                    "policy_stopped": True,
                },
                reason="policy stopped before official termination",
            )
        action.render()
        proposal = _browsergym_proposal(action, self.episode, request)
        self.bindings[proposal.proposal_id] = action
        return PlannerProposalResponse(
            proposal=proposal,
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.EXTERNAL_POLICY,
                producer_id=type(self.policy).__name__,
                profile_id="browsergym-policy",
            ),
            reason="benchmark action translated to semantic proposal",
        )


@dataclass
class BrowserGymGeneralistPlanner:
    model: ModelPort
    episode: BrowserGymEpisodeState
    config: ModelConfig
    limits: PlannerLimits = field(default_factory=PlannerLimits)
    max_model_calls: int = 15
    planner_profile: GeneralistPlannerProfile = GeneralistPlannerProfile.STRICT_GENERALIST
    _planner: GeneralistLMPlanner = field(init=False, repr=False)
    _choice_planner: StrictStepChoicePlanner = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._planner = GeneralistLMPlanner(
            self.model,
            limits=self.limits,
            config=self.config,
            max_model_calls=self.max_model_calls,
            allow_finish=False,
            planner_profile=self.planner_profile,
        )
        self._choice_planner = StrictStepChoicePlanner(
            self.model,
            config=self.config.model_copy(
                update={
                    "max_tokens": min(self.config.max_tokens, 128),
                    "prompt_version": STEP_CHOICE_PROMPT_VERSION,
                }
            ),
        )

    @property
    def step_choice_planner(self) -> StrictStepChoicePlanner:
        return self._choice_planner

    def planner_context_ref(self) -> str:
        return self._planner.planner_context_ref()

    def compact_planner_context(self) -> tuple[str, str] | None:
        return self._planner.compact_planner_context()

    def planner_schema_ref(self) -> str:
        return self._planner.planner_schema_ref()

    def repair_planner_schema(self) -> tuple[str, str] | None:
        return self._planner.repair_planner_schema()

    @property
    def model_call_count(self) -> int:
        return self._planner.model_call_count + self._choice_planner.model_call_count

    def propose(self, request: PlanningRequest) -> PlannerResponse | Any:
        return _browsergym_terminal_response(self.episode) or self._planner.propose(request)

    def propose_canonical(self, request: PlanningRequest, observation: UnifiedObservation) -> PlannerResponse | Any:
        return _browsergym_terminal_response(self.episode) or self._planner.propose_canonical(request, observation)


def _browsergym_terminal_response(episode: BrowserGymEpisodeState) -> PlannerDoneResponse | None:
    if not episode.terminated and not episode.truncated:
        return None
    return PlannerDoneResponse(
        result={
            "official_success": episode.terminated and episode.reward > 0,
            "official_reward": episode.reward,
            "terminated": episode.terminated,
            "truncated": episode.truncated,
            "completion_policy": BROWSERGYM_TERMINAL_COMPLETION_POLICY,
        },
        reason="official BrowserGym episode terminal state",
    )


class AgentLabPlannerAdapter(BrowserGymPlanner):
    """Named AgentLab/BrowserGym compatibility adapter."""


class JsonLinePolicy:
    """External planner boundary; one JSON request and typed action response per line."""

    def __init__(self, command: str | Sequence[str]) -> None:
        arguments = shlex.split(command) if isinstance(command, str) else list(command)
        if not arguments:
            raise ValueError("policy command is empty")
        self.process = subprocess.Popen(  # noqa: S603 - caller explicitly selects the planner executable
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction | None:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("policy process pipes are unavailable")
        self.process.stdin.write(json.dumps(asdict(request), sort_keys=True) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            error = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"policy process ended without a response: {error.strip()}")
        payload = json.loads(line)
        if payload is None or payload.get("done"):
            return None
        return BrowserGymAction(str(payload.get("name") or ""), dict(payload.get("arguments") or {}))

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()


def run_browsergym_episode(
    environment: BrowserGymEnvironment,
    policy: BrowserGymPolicy,
    *,
    task_id: str,
    seed: int,
    artifact_root: Path,
    max_steps: int = 50,
) -> BrowserGymEpisodeResult:
    try:
        obs, info = environment.reset(seed=seed)
    except Exception:
        _close_quietly(policy)
        _close_quietly(environment)
        raise
    goal = _goal_text(obs.get("goal", ""))
    episode = BrowserGymEpisodeState(task_id, seed, goal, obs, info)
    browser_version = _browsergym_browser_version(environment)
    session = BrowserSession(
        environment.unwrapped.page,
        dom_adapter=browsergym_dom_adapter(),
        svg_observer=browsergym_svg_observer(),
    )
    run_id = f"browsergym-{task_id}-seed-{seed}"
    unsupported: list[str] = []
    task_spec = TaskSpec(
        task_id=run_id,
        revision=1,
        objective=goal,
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(
            (task_id,), OperationClass.READ_ONLY, f"browsergym:{task_id}:seed:{seed}", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs((task_id,)),
        success=SuccessExpression(
            expression_id="success:browsergym-official-grade",
            operator="criterion",
            criterion_id=BROWSERGYM_SUCCESS_CRITERION_ID,
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref=f"browsergym:{task_id}:seed:{seed}",
    )
    try:
        result = compose_run_coordinator(
            observer=BrowserGymObserver(session, episode, artifact_root / "screenshots" / run_id),
            executor=BrowserGymExecutor(environment, episode),
            artifacts=ArtifactStore(artifact_root / "runs"),
            budget=RunBudget(
                max_steps=max_steps,
                max_observations=max_steps * 3 + 3,
                max_replans=max_steps + 1,
                max_recoveries=3,
                max_effectful_actions=max_steps + 1,
            ),
            contract_builder=ActionTransactionMaterializer(
                route_encoder=GeneralistBrowserGymRouteEncoder()
            ),
        ).run_sync(legacy_run_request(task_spec=task_spec, capabilities=[SPATIAL_POINT_CAPABILITY]))
        planner_error = next(
            (
                str(node.payload.get("reason") or "")
                for node in reversed(result.trace.nodes)
                if node.kind == "PlannerProposalRejected"
            ),
            "",
        )
        if (
            "unsupported BrowserGym action:" in planner_error
            or "unsupported BrowserGym semantic action:" in planner_error
        ):
            unsupported.append(planner_error.rsplit(":", 1)[-1].strip())
        receipt = result.state.last_receipt
        if receipt is not None and "unsupported BrowserGym action" in receipt.message:
            unsupported.append(receipt.message.rsplit(":", 1)[-1].strip())
        trace_path = next((item.path for item in result.artifacts if item.path.endswith("events.jsonl")), "")
        return BrowserGymEpisodeResult(
            task_id,
            seed,
            result.status.value,
            episode.terminated and episode.reward > 0,
            episode.reward,
            episode.terminated,
            episode.truncated,
            len(episode.actions),
            sorted({action.name for action in episode.actions}),
            sorted(set(unsupported)),
            planner_error or (result.error_code.value if result.error_code else ""),
            bool(result.result.get("policy_stopped", False)),
            trace_path,
            browser_version=browser_version,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if "unsupported BrowserGym action:" in error:
            unsupported.append(error.rsplit(":", 1)[-1].strip())
        return BrowserGymEpisodeResult(
            task_id,
            seed,
            RuntimeStep.FAILED.value,
            False,
            episode.reward,
            episode.terminated,
            episode.truncated,
            len(episode.actions),
            sorted({action.name for action in episode.actions}),
            unsupported,
            error,
            False,
            "",
            browser_version=browser_version,
        )
    finally:
        _close_quietly(policy)
        _close_quietly(environment)
