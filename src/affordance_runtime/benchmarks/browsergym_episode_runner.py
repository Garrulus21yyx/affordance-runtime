"""BrowserGym single-episode lifecycle, execution, and process isolation."""

from __future__ import annotations

import json
import multiprocessing as mp
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty
from time import perf_counter
from typing import Any, Callable, Sequence, cast

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.benchmarks import browsergym_observer as _browsergym_observer
from affordance_runtime.benchmarks.browsergym_action_schema import (
    BrowserGymAction,
)
from affordance_runtime.benchmarks.browsergym_dom import browsergym_dom_adapter, browsergym_svg_observer
from affordance_runtime.benchmarks.browsergym_encoder import (
    BrowserGymContractBuilder,
    GeneralistBrowserGymContractBuilder,
)
from affordance_runtime.benchmarks.browsergym_observer import BrowserGymObserver
from affordance_runtime.benchmarks.browsergym_types import (
    BROWSERGYM_BACKEND,
    BROWSERGYM_SUCCESS_CRITERION_ID,
    BrowserGymEnvironment,
    BrowserGymEpisodeResult,
    BrowserGymEpisodeState,
    BrowserGymPolicy,
    BrowserGymPolicyRequest,
    BrowserGymRuntimeFailure,
)
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    ExecutionReceipt,
    Observation,
    RiskLevel,
    RuntimeErrorCode,
    Surface,
)
from affordance_runtime.coordinator import RunBudget
from affordance_runtime.generalist_planner import (
    GeneralistLMPlanner,
    GeneralistPlannerProfile,
    PlannerLimits,
    planner_prompt_version,
)
from affordance_runtime.grounding import EvidenceKind, GroundingSource
from affordance_runtime.immutable import (
    thaw_json_at_external_boundary,
)
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import ModelConfig, ModelPort
from affordance_runtime.model_recovery import recovery_dispatcher_for_model
from affordance_runtime.perception import (
    GenericPerceptionOrchestrator,
    derive_perception_requirements,
    perception_task_terms,
)
from affordance_runtime.planning import (
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerDoneResponse,
    PlannerProposalResponse,
    PlannerResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.semantic_audit import SemanticAudit, SemanticAuditStatus
from affordance_runtime.simplified_runtime_contracts import SPATIAL_POINT_CAPABILITY
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.step_choice_planner import (
    STEP_CHOICE_PROMPT_VERSION,
    StrictStepChoicePlanner,
)
from affordance_runtime.task_intake import (
    CompilationStatus,
    OperationClass,
    TaskSpec,
    UserRequest,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.task_planner import PlanningRouter, StrictTaskPlanner
from affordance_runtime.task_spec_authority import TaskSpecAuthority
from affordance_runtime.trace import TraceDag
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.contracts import SuccessExpression
from affordance_runtime.visual_grounding import (
    VisualGrounderPort,
    VisualRegionProposerPort,
)

_json_safe = _browsergym_observer.json_safe
BROWSERGYM_TERMINAL_COMPLETION_POLICY = "official-terminal-v1"
# BrowserGym defaults Playwright actions to 500ms. Locally served controls can
# be visible and preflighted yet still miss that narrow window, so use one
# bounded timeout uniformly for every page action in an isolated episode.
BROWSERGYM_PAGE_ACTION_TIMEOUT_MS = 1_500
# Planner proposals are compact semantic candidates, not long-form answers.
BROWSERGYM_PLANNER_MAX_TOKENS = 384


def browsergym_planner_model_config(
    *,
    timeout_s: float,
    planner_profile: GeneralistPlannerProfile,
) -> ModelConfig:
    """Return the exact planner decoding contract bound into run identity."""

    return ModelConfig(
        temperature=0.0,
        seed=None,
        max_tokens=BROWSERGYM_PLANNER_MAX_TOKENS,
        timeout_s=timeout_s,
        prompt_version=planner_prompt_version(planner_profile),
    )


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
        action.render()  # validate before constructing a contract
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
    """Use the official episode terminal state before requesting another model turn."""

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

    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerResponse | Any:
        terminal = _browsergym_terminal_response(self.episode)
        if terminal is not None:
            return terminal
        return self._planner.propose(request)

    def propose_canonical(
        self,
        request: PlanningRequest,
        observation: UnifiedObservation,
    ) -> PlannerResponse | Any:
        terminal = _browsergym_terminal_response(self.episode)
        if terminal is not None:
            return terminal
        return self._planner.propose_canonical(request, observation)


def _browsergym_terminal_response(
    episode: BrowserGymEpisodeState,
) -> PlannerDoneResponse | None:
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
    """Named AgentLab/BrowserGym action adapter at the semantic planner boundary."""


def _browser_snapshot_evidence(snapshot: BrowserSnapshot) -> frozenset[EvidenceKind]:
    evidence: set[EvidenceKind] = set()
    for source in snapshot.source_observations:
        if source.source in {GroundingSource.DOM, GroundingSource.ACCESSIBILITY}:
            evidence.update({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})
        elif source.source == GroundingSource.SVG:
            evidence.update({EvidenceKind.STRUCTURAL, EvidenceKind.SPATIAL})
        elif source.source in {GroundingSource.SOM, GroundingSource.VISUAL}:
            evidence.add(EvidenceKind.VISUAL_APPEARANCE)
    return frozenset(evidence)


@dataclass
class BrowserGymExecutor:
    environment: BrowserGymEnvironment
    episode: BrowserGymEpisodeState
    backend: str = BROWSERGYM_BACKEND

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started = perf_counter()
        try:
            payload = thaw_json_at_external_boundary(contract.parameters.get("action"))
            if not isinstance(payload, dict):
                raise ValueError("BrowserGym contract requires typed parameters.action")
            action = BrowserGymAction(str(payload.get("name") or ""), dict(payload.get("arguments") or {}))
            obs: dict[str, Any] = {}
            reward = 0.0
            terminated = truncated = False
            info: dict[str, Any] = {}
            action_error = ""
            direct_dispatch_evidence: dict[str, Any] = {}
            if action.name in {
                "click_no_navigation",
                "type_text_with_events",
                "mouse_click",
                "mouse_drag_and_drop",
            }:
                raw_environment = self.environment.unwrapped
                pre_step = getattr(raw_environment, "pre_step", None)
                post_step = getattr(raw_environment, "post_step", None)
                if not callable(pre_step) or not callable(post_step):
                    raise ValueError("BrowserGym pointer action requires pre_step/post_step lifecycle hooks")
                info, _, _ = pre_step()
                page = getattr(raw_environment, "page", None)
                mouse = getattr(page, "mouse", None)
                if action.name == "type_text_with_events":
                    locator = getattr(page, "locator", None)
                    keyboard = getattr(page, "keyboard", None)
                    type_text = getattr(keyboard, "type", None)
                    if not callable(locator) or not callable(type_text):
                        raise ValueError("BrowserGym eventful typing requires locator and keyboard")
                    bid = str(action.arguments["bid"])
                    target = cast(Callable[[str], Any], locator)(f"[bid='{bid.replace(chr(39), chr(92) + chr(39))}']")
                    focus = getattr(target, "focus", None)
                    if not callable(focus):
                        raise ValueError("BrowserGym eventful typing requires a focusable target")
                    cast(Callable[[], Any], focus)()
                    cast(Callable[[str], Any], type_text)(str(action.arguments["text"]))
                    raw_environment.last_action = "direct_type_text_with_events"
                    rendered_actions = ["direct_type_text_with_events"]
                elif action.name == "click_no_navigation":
                    evaluator = getattr(page, "evaluate", None)
                    if not callable(evaluator):
                        raise ValueError("BrowserGym navigation-safe click requires page evaluation")
                    cast(Callable[..., Any], evaluator)(
                        """bid => { const element = document.querySelector(`[bid="${CSS.escape(bid)}"]`); if (!element) throw new Error('bid not found'); element.scrollIntoView({block: 'center', inline: 'nearest'}); element.addEventListener('click', event => event.preventDefault(), {capture: true, once: true}); element.click(); }""",
                        action.arguments["bid"],
                    )
                    raw_environment.last_action = "direct_click_no_navigation"
                    rendered_actions = ["direct_click_no_navigation"]
                elif action.name == "mouse_click":
                    click = getattr(mouse, "click", None)
                    if not callable(click):
                        raise ValueError("BrowserGym pointer click requires an available page mouse")
                    cast(Callable[..., Any], click)(action.arguments["x"], action.arguments["y"], button="left")
                    raw_environment.last_action = "direct_pointer_click"
                    rendered_actions = ["direct_pointer_click"]
                else:
                    move = getattr(mouse, "move", None)
                    down = getattr(mouse, "down", None)
                    up = getattr(mouse, "up", None)
                    if not all(callable(item) for item in (move, down, up)):
                        raise ValueError("BrowserGym pointer drag requires an available page mouse")
                    from_x = action.arguments["from_x"]
                    from_y = action.arguments["from_y"]
                    to_x = action.arguments["to_x"]
                    to_y = action.arguments["to_y"]
                    from_bid = str(action.arguments.get("from_bid") or "")
                    to_bid = str(action.arguments.get("to_bid") or "")
                    bid_dispatch_done = False
                    if from_bid and to_bid:
                        evaluator = getattr(page, "evaluate", None)
                        if callable(evaluator):
                            dispatch_result = cast(Callable[..., Any], evaluator)(
                                """({fromBid, toBid}) => {
                                  const source = document.querySelector(`[bid="${CSS.escape(fromBid)}"]`);
                                  const destination = document.querySelector(`[bid="${CSS.escape(toBid)}"]`);
                                  if (!source || !destination) return false;
                                  source.scrollIntoView({block: 'center', inline: 'nearest'});
                                  destination.scrollIntoView({block: 'center', inline: 'nearest'});
                                  const event = (type, buttons) => new MouseEvent(type, {
                                    bubbles: true, cancelable: true, view: window,
                                    button: 0, buttons
                                  });
                                  const before = new Set(document.querySelectorAll('*'));
                                  source.dispatchEvent(event('mousedown', 1));
                                  source.dispatchEvent(event('mousemove', 1));
                                  destination.dispatchEvent(event('mousemove', 1));
                                  const rect = destination.getBoundingClientRect();
                                  const releaseX = rect.left + rect.width / 2;
                                  const releaseY = rect.top + rect.height / 2;
                                  const created = Array.from(document.querySelectorAll('*')).filter(
                                    element => !before.has(element)
                                  );
                                  const releaseTarget = [...created].reverse().find(element => {
                                    const box = element.getBoundingClientRect();
                                    return releaseX >= box.left && releaseX <= box.right
                                      && releaseY >= box.top && releaseY <= box.bottom;
                                  }) || document.elementFromPoint(releaseX, releaseY) || destination;
                                  releaseTarget.dispatchEvent(event('mouseup', 0));
                                  return {
                                    ok: true,
                                    createdCount: created.length,
                                    releaseTag: releaseTarget.tagName.toLowerCase(),
                                    releaseId: releaseTarget.id || '',
                                    scrollTop: Number(source.parentElement?.parentElement?.parentElement?.scrollTop || 0)
                                  };
                                }""",
                                {"fromBid": from_bid, "toBid": to_bid},
                            )
                            if not (
                                dispatch_result is True
                                or (isinstance(dispatch_result, dict) and dispatch_result.get("ok") is True)
                            ):
                                raise ValueError("BrowserGym bid-bound pointer drag targets are unavailable")
                            if isinstance(dispatch_result, dict):
                                direct_dispatch_evidence = _json_safe(dispatch_result)
                            bid_dispatch_done = True
                    if from_bid and to_bid and not bid_dispatch_done:
                        locator = getattr(page, "locator", None)
                        if not callable(locator):
                            raise ValueError("BrowserGym bid-bound pointer drag requires page locators")
                        locator_fn = cast(Callable[[str], Any], locator)
                        source_target = locator_fn(f"[bid='{from_bid}']")
                        destination_target = locator_fn(f"[bid='{to_bid}']")
                        for target in (source_target, destination_target):
                            evaluate_target = getattr(target, "evaluate", None)
                            if callable(evaluate_target):
                                cast(Callable[[str], Any], evaluate_target)(
                                    "element => element.scrollIntoView({block: 'center', inline: 'nearest'})"
                                )
                            scroll = getattr(target, "scroll_into_view_if_needed", None)
                            if callable(scroll):
                                cast(Callable[[], Any], scroll)()
                        source_box_fn = getattr(source_target, "bounding_box", None)
                        destination_box_fn = getattr(destination_target, "bounding_box", None)
                        if not callable(source_box_fn) or not callable(destination_box_fn):
                            raise ValueError("BrowserGym bid-bound pointer drag requires live geometry")
                        source_box = cast(Callable[[], Any], source_box_fn)()
                        destination_box = cast(Callable[[], Any], destination_box_fn)()
                        if not isinstance(source_box, dict) or not isinstance(destination_box, dict):
                            raise ValueError("BrowserGym bid-bound pointer drag geometry is unavailable")
                        from_x = float(source_box["x"]) + float(source_box["width"]) / 2
                        to_x = float(destination_box["x"]) + float(destination_box["width"]) / 2
                        if from_bid == to_bid:
                            from_y = float(source_box["y"]) + float(source_box["height"]) * 0.25
                            to_y = float(destination_box["y"]) + float(destination_box["height"]) * 0.75
                        else:
                            from_y = float(source_box["y"]) + float(source_box["height"]) / 2
                            to_y = float(destination_box["y"]) + float(destination_box["height"]) / 2
                    if not bid_dispatch_done:
                        move_fn = cast(Callable[..., Any], move)
                        down_fn = cast(Callable[..., Any], down)
                        up_fn = cast(Callable[..., Any], up)
                        move_fn(from_x, from_y)
                        down_fn(button="left")
                        move_fn(to_x, to_y, steps=8)
                        up_fn(button="left")
                    raw_environment.last_action = "direct_pointer_drag"
                    rendered_actions = ["direct_pointer_drag"]
                obs, reward, terminated, truncated, info = post_step(info)
                action_error = str(obs.get("last_action_error") or info.get("last_action_error") or "")
            else:
                if action.name == "click":
                    raw_environment = self.environment.unwrapped
                    page = getattr(raw_environment, "page", None)
                    evaluator = getattr(page, "evaluate", None)
                    if callable(evaluator):
                        scrolled = cast(Callable[..., Any], evaluator)(
                            """bid => { const element = document.querySelector(`[bid="${CSS.escape(bid)}"]`); if (!element) return false; element.scrollIntoView({block: 'center', inline: 'nearest'}); return true; }""",
                            action.arguments["bid"],
                        )
                        if scrolled is False:
                            raise ValueError("BrowserGym click target is unavailable")
                        direct_dispatch_evidence = {"scrolled": True}
                dispatched_actions = (action,)
                rendered_actions = [item.render() for item in dispatched_actions]
                for rendered in rendered_actions:
                    obs, reward, terminated, truncated, info = self.environment.step(rendered)
                    action_error = str(obs.get("last_action_error") or info.get("last_action_error") or "")
                    if action_error or terminated or truncated:
                        break
            overlay_cleanup = False
            if action.name == "select_option" and not (obs.get("last_action_error") or info.get("last_action_error")):
                page = getattr(self.environment.unwrapped, "page", None)
                keyboard = getattr(page, "keyboard", None)
                press = getattr(keyboard, "press", None)
                if callable(press):
                    press("Escape")
                    overlay_cleanup = True
            self.episode.observation = obs
            self.episode.reward = float(reward)
            self.episode.terminated = bool(terminated)
            self.episode.truncated = bool(truncated)
            self.episode.info = info
            self.episode.actions.append(action)
            return ExecutionReceipt(
                contract.id,
                self.backend,
                not action_error,
                observation.environment_revision,
                observation.environment_revision,
                round((perf_counter() - started) * 1_000, 3),
                evidence={
                    "browsergym_action": rendered_actions,
                    "select_overlay_cleanup": overlay_cleanup,
                    "last_action_error": action_error,
                    "official_reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    **(
                        {
                            "terminal_success": bool(terminated) and float(reward) > 0.0,
                            "terminal_failure": not (bool(terminated) and float(reward) > 0.0),
                        }
                        if terminated or truncated
                        else {}
                    ),
                    "task_info": _json_safe(info.get("task_info", {})),
                    **({"direct_dispatch": direct_dispatch_evidence} if direct_dispatch_evidence else {}),
                },
                error_code=RuntimeErrorCode.EXECUTION_FAILED if action_error else None,
                message=action_error,
            )
        except Exception as exc:
            return ExecutionReceipt(
                contract.id,
                self.backend,
                False,
                observation.environment_revision,
                observation.environment_revision,
                round((perf_counter() - started) * 1_000, 3),
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message=f"{type(exc).__name__}: {exc}",
            )


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
    result_error = ""
    unsupported: list[str] = []
    bindings: dict[str, BrowserGymAction] = {}
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
            contract_builder=BrowserGymContractBuilder(bindings=bindings),
        ).run_sync(RunRequest(task_spec=task_spec, capabilities=[SPATIAL_POINT_CAPABILITY]))
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
            result_error or planner_error or (result.error_code.value if result.error_code else ""),
            bool(result.result.get("policy_stopped", False)),
            trace_path,
            browser_version=browser_version,
        )
    except Exception as exc:
        result_error = f"{type(exc).__name__}: {exc}"
        if "unsupported BrowserGym action:" in result_error:
            unsupported.append(result_error.rsplit(":", 1)[-1].strip())
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
            result_error,
            False,
            "",
            browser_version=browser_version,
        )
    finally:
        _close_quietly(policy)
        _close_quietly(environment)


def run_browsergym_generalist_episode(
    environment: BrowserGymEnvironment,
    model: ModelPort,
    *,
    task_id: str,
    seed: int,
    artifact_root: Path,
    max_steps: int = 50,
    model_timeout_s: float = 10.0,
    max_model_calls: int = 15,
    planner_profile: GeneralistPlannerProfile = GeneralistPlannerProfile.STRICT_GENERALIST,
    visual_grounder: VisualGrounderPort | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
) -> BrowserGymEpisodeResult:
    """Run the same GeneralistLMPlanner port through BrowserGym's typed executor."""

    run_id = f"browsergym-generalist-{task_id}-seed-{seed}"
    browser_version = ""
    intake_trace: TraceDag | None = None
    intent_call_attempted = False
    intent_compiler: LLMIntentCompiler | None = None
    episode_phase = "environment"
    try:
        obs, info = environment.reset(seed=seed)
        browser_version = _browsergym_browser_version(environment)
        page = getattr(environment.unwrapped, "page", None)
        set_default_timeout = getattr(page, "set_default_timeout", None)
        if callable(set_default_timeout):
            set_default_timeout(BROWSERGYM_PAGE_ACTION_TIMEOUT_MS)
        goal = _goal_text(obs.get("goal", ""))
        episode = BrowserGymEpisodeState(task_id, seed, goal, obs, info)
        session = BrowserSession(
            environment.unwrapped.page,
            svg_executor=BROWSERGYM_BACKEND,
            dom_executor=BROWSERGYM_BACKEND,
            dom_adapter=browsergym_dom_adapter(),
            svg_observer=browsergym_svg_observer(),
            perception_orchestrator=(
                GenericPerceptionOrchestrator(
                    region_proposer=visual_region_proposer,
                    point_grounder=visual_grounder,
                )
                if visual_region_proposer is not None or visual_grounder is not None
                else None
            ),
            visual_executor=BROWSERGYM_BACKEND,
        )
        intake_trace = TraceDag(run_id=run_id)
        intent_call_attempted = True
        episode_phase = "intent_compilation"
        intent_compiler = LLMIntentCompiler(model)
        user_request = UserRequest(
            request_id=run_id,
            raw_text=goal,
            channel="browser-runtime",
        )
        envelope = SourceEnvelopeBuilder().build(user_request)
        parent = intake_trace.add(
            "SourceEnvelopeBuilt",
            {
                "source_envelope_ref": envelope.identity,
                "source_binding_digest": envelope.binding_digest,
                "content_digest": envelope.content_digest,
                "content_length": envelope.content_length,
            },
        )
        proposal = resolve_awaitable(intent_compiler.propose(user_request, envelope, trace=intake_trace, parent=parent))
        admitted_effect_refs = tuple(
            effect.effect_id or f"requirement:effect:{index}"
            for index, effect in enumerate(proposal.requested_effects, start=1)
        )
        proposal = proposal.model_copy(
            update={
                "success": SuccessExpression(
                    expression_id="success:browsergym-official-grade",
                    operator="criterion",
                    criterion_id=BROWSERGYM_SUCCESS_CRITERION_ID,
                    requirement_refs=admitted_effect_refs,
                )
            }
        )
        audit = SemanticAudit().evaluate(envelope, proposal)
        parent = intake_trace.add(
            "SemanticAuditEvaluated",
            audit.model_dump(mode="json"),
            parents=[intake_trace.nodes[-1].id],
        )
        if audit.status != SemanticAuditStatus.PASS:
            raise ValueError(f"semantic audit {audit.status.value}: {','.join(audit.issue_codes)}")
        compilation = TaskSpecAuthority().admit(
            user_request,
            envelope,
            proposal,
            task_id=run_id,
        )
        intake_trace.add(
            "TaskSpecAdmissionDecided",
            {
                "status": compilation.status.value,
                "authority": "TaskSpecAuthority",
                "task_spec_identity": compilation.task_spec.identity if compilation.task_spec else "",
            },
            parents=[parent.id],
        )
        if compilation.status != CompilationStatus.READY or compilation.task_spec is None:
            issue_codes = ",".join(item.code for item in compilation.issues)
            raise ValueError(f"intent compilation {compilation.status.value}: {issue_codes}")
        episode_phase = "runtime"
        task_spec = compilation.task_spec
        perception_requirements = derive_perception_requirements(task_spec)
        task_planner = StrictTaskPlanner(model)
        choice_planner = StrictStepChoicePlanner(
            model,
            config=browsergym_planner_model_config(
                timeout_s=model_timeout_s,
                planner_profile=planner_profile,
            ).model_copy(
                update={
                    "max_tokens": 128,
                    "prompt_version": STEP_CHOICE_PROMPT_VERSION,
                }
            ),
        )
        result = compose_run_coordinator(
            observer=BrowserGymObserver(
                session,
                episode,
                artifact_root / "screenshots" / run_id,
                perception_requirements=perception_requirements,
                task_terms=perception_task_terms(task_spec),
            ),
            executor=BrowserGymExecutor(environment, episode),
            artifacts=ArtifactStore(artifact_root / "runs"),
            budget=RunBudget(
                max_steps=max_steps,
                max_observations=max_steps * 3 + 3,
                max_replans=max_steps + 1,
                max_recoveries=3,
                max_effectful_actions=max_steps + 1,
            ),
            contract_builder=GeneralistBrowserGymContractBuilder(),
            task_planner=PlanningRouter(complex_planner=task_planner),
            step_choice_planner=choice_planner,
            recovery_owner_dispatcher=recovery_dispatcher_for_model(model),
        ).run_sync(
            RunRequest(task_spec=task_spec, capabilities=[SPATIAL_POINT_CAPABILITY]),
            intake_trace,
        )
        planner_error = next(
            (
                str(node.payload.get("reason") or "")
                for node in reversed(result.trace.nodes)
                if node.kind == "PlannerProposalRejected"
            ),
            "",
        )
        trace_path = next((item.path for item in result.artifacts if item.path.endswith("events.jsonl")), "")
        model_stats = {
            **_browsergym_model_stats(
                result.trace.nodes,
                task_planner.model_call_count + choice_planner.model_call_count + intent_compiler.model_call_count,
            ),
            **_browsergym_planning_stats(result.trace.nodes),
            **_browsergym_adaptive_runtime_stats(result.trace.nodes),
            **_browsergym_failure_stats(result.trace.nodes),
            "last_verified_step": result.state.step_count,
        }
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
            [],
            planner_error or (result.error_code.value if result.error_code else ""),
            False,
            trace_path,
            browser_version=browser_version,
            **model_stats,
        )
    except Exception as exc:
        trace_path = ""
        failure_model_stats: dict[str, Any] = {}
        if intake_trace is not None:
            intake_trace.add(
                "BrowserGymEpisodeFailed",
                {
                    "phase": episode_phase,
                    "error_type": type(exc).__name__,
                },
                parents=[intake_trace.nodes[-1].id] if intake_trace.nodes else None,
            )
            artifacts = ArtifactStore(artifact_root / "runs").finalize(
                run_id,
                intake_trace,
                {
                    "status": RuntimeStep.FAILED.value,
                    "phase": episode_phase,
                    "error_type": type(exc).__name__,
                },
            )
            trace_path = next((item.path for item in artifacts if item.path.endswith("events.jsonl")), "")
            failure_model_stats = _browsergym_model_stats(
                intake_trace.nodes,
                intent_compiler.model_call_count if intent_compiler is not None else int(intent_call_attempted),
            )
        return BrowserGymEpisodeResult(
            task_id,
            seed,
            RuntimeStep.FAILED.value,
            False,
            0.0,
            False,
            False,
            0,
            [],
            [],
            f"{type(exc).__name__}: {exc}",
            False,
            trace_path,
            browser_version=browser_version,
            **failure_model_stats,
        )
    finally:
        _close_quietly(environment)


def _browsergym_browser_version(environment: BrowserGymEnvironment) -> str:
    page = getattr(environment.unwrapped, "page", None)
    context = getattr(page, "context", None)
    browser = getattr(context, "browser", None)
    return str(getattr(browser, "version", "") or "")


def _generalist_episode_worker(
    result_queue: Any,
    model: ModelPort,
    *,
    task_id: str,
    seed: int,
    base_url: str,
    headless: bool,
    artifact_root: str,
    model_timeout_s: float,
    max_model_calls: int,
    planner_profile: GeneralistPlannerProfile,
    visual_grounder: VisualGrounderPort | None,
    visual_region_proposer: VisualRegionProposerPort | None,
) -> None:
    """Child-process owner for one BrowserGym/Playwright episode."""

    try:
        import browsergym.miniwob  # type: ignore[import-not-found,import-untyped]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]

        environment_kwargs: dict[str, Any] = {
            "task_kwargs": {"base_url": base_url},
            "headless": headless,
        }
        from browsergym.core.action.highlevel import HighLevelActionSet  # type: ignore[import-not-found,import-untyped]

        # The semantic planner cannot author low-level actions. Enabling the
        # bounded coordinate subset here lets only the trusted backend encoder
        # execute current SVG/visual contracts while retaining bid actions.
        environment_kwargs["action_mapping"] = HighLevelActionSet(subsets=["bid", "miniwob_all"]).to_python_code
        environment = gym.make(f"browsergym/miniwob.{task_id}", **environment_kwargs)
        result = run_browsergym_generalist_episode(
            cast(BrowserGymEnvironment, environment),
            model,
            task_id=task_id,
            seed=seed,
            artifact_root=Path(artifact_root),
            model_timeout_s=model_timeout_s,
            max_model_calls=max_model_calls,
            planner_profile=planner_profile,
            visual_grounder=visual_grounder,
            visual_region_proposer=visual_region_proposer,
        )
    except BaseException as exc:
        result = BrowserGymEpisodeResult(
            task_id,
            seed,
            RuntimeStep.FAILED.value,
            False,
            0.0,
            False,
            False,
            0,
            [],
            [],
            f"worker_error:{type(exc).__name__}",
            False,
            "",
        )
    result_queue.put(asdict(result))


def _browsergym_source_server_worker(ready_queue: Any, html_root: str) -> None:
    """Serve pinned MiniWoB files outside the parent that forks episodes."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _quiet_handler(Path(html_root)))
    try:
        ready_queue.put((server.server_name, server.server_port))
        server.serve_forever()
    finally:
        server.server_close()


def run_browsergym_generalist_episode_isolated(
    model: ModelPort,
    *,
    task_id: str,
    seed: int,
    base_url: str,
    headless: bool,
    artifact_root: Path,
    timeout_s: float,
    model_timeout_s: float,
    max_model_calls: int,
    planner_profile: GeneralistPlannerProfile = GeneralistPlannerProfile.STRICT_GENERALIST,
    visual_grounder: VisualGrounderPort | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
) -> BrowserGymEpisodeResult:
    """Run one episode in a killable process and preserve timeout diagnostics."""

    context = mp.get_context("fork")
    result_queue = context.Queue()
    worker = context.Process(
        target=_generalist_episode_worker,
        args=(result_queue, model),
        kwargs={
            "task_id": task_id,
            "seed": seed,
            "base_url": base_url,
            "headless": headless,
            "artifact_root": str(artifact_root),
            "model_timeout_s": model_timeout_s,
            "max_model_calls": max_model_calls,
            "planner_profile": planner_profile,
            "visual_grounder": visual_grounder,
            "visual_region_proposer": visual_region_proposer,
        },
    )
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        worker.terminate()
        worker.join(timeout=5)
        result_queue.close()
        return BrowserGymEpisodeResult(
            task_id,
            seed,
            RuntimeStep.FAILED.value,
            False,
            0.0,
            False,
            False,
            0,
            [],
            [],
            "episode_timeout",
            False,
            "",
        )
    try:
        payload = result_queue.get(timeout=1)
    except Empty:
        result_queue.close()
        return BrowserGymEpisodeResult(
            task_id,
            seed,
            RuntimeStep.FAILED.value,
            False,
            0.0,
            False,
            False,
            0,
            [],
            [],
            f"worker_exit:{worker.exitcode}",
            False,
            "",
        )
    result_queue.close()
    return BrowserGymEpisodeResult(**payload)


def _close_quietly(resource: Any) -> None:
    """Best-effort BrowserGym cleanup must not replace an episode diagnosis."""

    try:
        resource.close()
    except Exception:
        pass


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


def _browsergym_model_stats(nodes: Sequence[Any], attempted_calls: int) -> dict[str, Any]:
    records = [
        node.payload.get("model_call")
        for node in nodes
        if node.kind
        in {
            "MinimalIntentProposalProduced",
            "PlannerProposalProduced",
        }
        and isinstance(node.payload.get("model_call"), Mapping)
    ]
    provider_failures = [
        str(node.payload.get("provider_failure") or "")
        for node in nodes
        if node.kind == "PlannerDeferred" and node.payload.get("provider_failure")
    ]
    return {
        "model_call_count": max(attempted_calls, len(records)),
        "model_call_latency_ms": round(sum(float(item.get("latency_ms") or 0.0) for item in records), 3),
        "rate_limit_retry_count": sum(int(item.get("rate_limit_retry_count") or 0) for item in records),
        "transient_retry_count": sum(int(item.get("transient_retry_count") or 0) for item in records),
        "provider_failures": provider_failures,
    }


def _browsergym_failure_stats(nodes: Sequence[Any]) -> dict[str, Any]:
    """Project the last Runtime-owned failure or explicit safety stop."""

    for index in range(len(nodes) - 1, -1, -1):
        node = nodes[index]
        if node.kind != "FailureDetected":
            continue
        failure = node.payload.get("failure")
        if not isinstance(failure, Mapping):
            continue
        phase = str(failure.get("phase") or "")
        failure_class = str(failure.get("failure_class") or "")
        error_code = str(failure.get("error_code") or "")
        effect_status = str(failure.get("effect_status") or "")
        if not all((phase, failure_class, error_code, effect_status)):
            continue
        detail_code = ""
        if phase == "proposal_validation":
            rejected = next(
                (previous for previous in reversed(nodes[:index]) if previous.kind == "PlannerProposalRejected"),
                None,
            )
            if rejected is not None:
                detail_code = str(rejected.payload.get("rejection_code") or "")
        elif phase == "task_planning":
            rejected = next(
                (
                    previous
                    for previous in reversed(nodes[:index])
                    if previous.kind in {"TaskPlanRejected", "TaskReplanRejected"}
                ),
                None,
            )
            issues = rejected.payload.get("issues") if rejected is not None else None
            if isinstance(issues, Sequence) and issues and isinstance(issues[0], Mapping):
                detail_code = str(issues[0].get("code") or "")
        elif phase == "verification":
            failed = next(
                (
                    previous
                    for previous in reversed(nodes[:index])
                    if previous.kind == "PostActionEvaluated"
                    and previous.payload.get("action_effect_status") != "passed"
                ),
                None,
            )
            evidence = failed.payload.get("evidence") if failed is not None else None
            if isinstance(evidence, Sequence):
                failed_kinds = list(
                    dict.fromkeys(
                        str(item.get("verifier_kind") or "")
                        for item in evidence
                        if isinstance(item, Mapping) and item.get("passed") is False
                    )
                )
                if len(failed_kinds) == 1:
                    detail_code = failed_kinds[0]
        evidence_refs = failure.get("evidence_refs")
        return {
            "runtime_failure": BrowserGymRuntimeFailure(
                phase=phase,
                failure_class=failure_class,
                error_code=error_code,
                effect_status=effect_status,
                detail_code=detail_code,
                message=str(failure.get("message") or ""),
                evidence_refs=(
                    [str(item) for item in evidence_refs]
                    if isinstance(evidence_refs, Sequence) and not isinstance(evidence_refs, (str, bytes))
                    else []
                ),
            )
        }
    if any(node.kind == "HumanApprovalRequested" for node in nodes):
        return {
            "runtime_failure": BrowserGymRuntimeFailure(
                phase="preflight",
                failure_class="authority",
                error_code="approval_required",
                effect_status="not_dispatched",
                message="human approval is required before dispatch",
            )
        }
    return {"runtime_failure": None}


def _browsergym_adaptive_runtime_stats(nodes: Sequence[Any]) -> dict[str, Any]:
    """Project M8.5 trace decisions into the public episode schema."""

    route_nodes = [node for node in nodes if node.kind == "RouteSelected"]
    route_sources = [str(node.payload.get("source") or "") for node in route_nodes]
    conflict_count = 0
    for node in nodes:
        if node.kind != "SourceAssertionsArbitrated":
            continue
        decisions = node.payload.get("decisions")
        if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
            continue
        conflict_count += sum(
            isinstance(item, Mapping) and str(item.get("status") or "") in {"conflict", "inconclusive", "reobserve"}
            for item in decisions
        )
    return {
        "route_selection_count": len(route_nodes),
        "route_sources": route_sources,
        "visual_route_count": sum(source in {"visual", "som"} for source in route_sources),
        "fallback_route_count": sum(
            node.kind == "ContractBuilt" and bool(node.payload.get("fallback_reason")) for node in nodes
        ),
        "targeted_perception_count": sum(node.kind == "TargetedPerceptionCaptured" for node in nodes),
        "source_conflict_count": conflict_count,
        "task_skill_activated_count": sum(node.kind == "TaskSkillActivated" for node in nodes),
        "task_skill_completed_count": sum(node.kind == "TaskSkillCompleted" for node in nodes),
        "task_skill_fallthrough_count": sum(node.kind == "TaskSkillFellThrough" for node in nodes),
    }


def _browsergym_planning_stats(nodes: Sequence[Any]) -> dict[str, Any]:
    """Project canonical planning facts without retaining planner context."""

    turns = [node for node in nodes if node.kind == "PlanningTurnEvaluated"]
    if not turns:
        return {
            "planning_turn_count": 0,
            "model_stage": "unknown",
            "grounded_target_count": None,
            "action_choice_count": None,
            "selection_source": "unknown",
        }
    diagnostic_turn = next(
        (turn for turn in reversed(turns) if str(turn.payload.get("model_stage") or "unknown") != "unknown"),
        turns[-1],
    )
    payload = diagnostic_turn.payload
    return {
        "planning_turn_count": len(turns),
        "model_stage": str(payload.get("model_stage") or "unknown"),
        "grounded_target_count": _optional_nonnegative_int(payload.get("grounded_target_count")),
        "action_choice_count": _optional_nonnegative_int(payload.get("action_choice_count")),
        "selection_source": str(payload.get("selection_source") or "unknown"),
    }


def _optional_nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _action_affordance(action: BrowserGymAction, snapshot: BrowserSnapshot) -> Affordance:
    bid = str(action.arguments.get("bid") or action.arguments.get("from_bid") or "")
    selector = f"[bid='{bid.replace(chr(39), chr(92) + chr(39))}']" if bid else ""
    match = next(
        (
            item
            for item in snapshot.affordance_model.affordances
            if item.locator.get("backend_handle") == bid or item.locator.get("selector") == selector
        ),
        None,
    )
    if match is not None:
        return match
    fingerprint = f"browsergym:{action.name}:{bid}" if bid else ""
    lease = AffordanceLease.issue(
        environment_revision=snapshot.observation.environment_revision,
        provenance=["browsergym", "typed_action"],
        snapshot_id=snapshot.observation.snapshot_id,
        page_revision=snapshot.observation.page_revision,
        target_fingerprint=fingerprint,
    )
    return Affordance(
        id=f"browsergym_{action.name}_{bid or 'global'}",
        surface=Surface.DOM,
        role="browser_action",
        label=bid or action.name,
        action=action.name,
        locator={"backend_handle": bid, "selector": selector, "action_name": action.name},
        lease=lease,
        backend_candidates=[BROWSERGYM_BACKEND],
        risk=RiskLevel.LOW,
    )


def _browsergym_policy_locator(locator: dict[str, Any]) -> dict[str, Any]:
    """Expose BrowserGym naming only at its legacy policy adapter boundary."""

    encoded = dict(locator)
    backend_handle = str(encoded.pop("backend_handle", "") or "")
    if backend_handle:
        encoded["bid"] = backend_handle
    owner_handle = str(encoded.pop("select_owner_backend_handle", "") or "")
    if owner_handle:
        encoded["select_owner_bid"] = owner_handle
    return encoded


def _browsergym_proposal(
    action: BrowserGymAction,
    episode: BrowserGymEpisodeState,
    request: PlanningRequest,
) -> PlannerProposal:
    semantic_kind = {
        "click": PlannerActionKind.ACTIVATE,
        "dblclick": PlannerActionKind.ACTIVATE,
        "fill": PlannerActionKind.TYPE_TEXT,
        "select_option": PlannerActionKind.SELECT_OPTION,
        "press": PlannerActionKind.PRESS_KEY,
    }.get(action.name)
    if semantic_kind is None:
        raise ValueError(f"unsupported BrowserGym semantic action: {action.name}")
    bid = str(action.arguments.get("bid") or action.arguments.get("from_bid") or "")
    affordance = next(
        (
            item
            for item in request.observation.affordances
            if item.target_id == bid
            or item.label.casefold() == bid.casefold()
            or item.target_id.casefold().endswith(f"_{bid.casefold()}")
        ),
        None,
    )
    if affordance is None:
        raise ValueError(f"BrowserGym action target is absent from PlanningRequest: {bid}")
    parameters: dict[str, Any] = {}
    if semantic_kind == PlannerActionKind.TYPE_TEXT:
        parameters["text"] = str(action.arguments["value"])
    elif semantic_kind == PlannerActionKind.SELECT_OPTION:
        value = action.arguments["options"]
        parameters["option"] = value if isinstance(value, list) else str(value)
    elif semantic_kind == PlannerActionKind.PRESS_KEY:
        parameters["key"] = str(action.arguments["key_comb"])
    index = len(episode.actions) + 1
    return PlannerProposal(
        proposal_id=f"browsergym-{episode.task_id}-{episode.seed}-step-{index}",
        based_on_task_revision=1,
        based_on_state_version=request.identity.evaluated_at_state_version,
        snapshot_id=request.identity.snapshot_id,
        subgoal=episode.goal,
        action_kind=semantic_kind,
        target_affordance_id=affordance.target_id,
        parameters=parameters,
        expected_effects=("BrowserGym action has no action error",),
        evidence_requirements=("last_action_error receipt field is empty",),
    )


def _browsergym_request_locator(label: str, observation: dict[str, Any]) -> dict[str, str]:
    """Reconstruct the benchmark policy locator outside the canonical planner view."""

    tree = observation.get("axtree_object")
    nodes = tree.get("nodes", ()) if isinstance(tree, dict) else ()
    for node in nodes:
        if not isinstance(node, dict) or node.get("ignored"):
            continue
        name = str((node.get("name") or {}).get("value") or "")
        bid = str(node.get("browsergym_id") or "")
        if bid and name.casefold() == label.casefold():
            return {"selector": f"[bid='{bid}']", "bid": bid}
    fallback = label.strip().casefold().replace(" ", "-")
    return {"selector": f"[bid='{fallback}']", "bid": fallback} if fallback else {}


def _goal_text(goal: Any) -> str:
    if isinstance(goal, str):
        return goal
    if isinstance(goal, list):
        return "\n".join(str(item.get("text") or "") for item in goal if isinstance(item, dict)).strip()
    return str(goal)


def _accessibility_tree_text(observation: dict[str, Any]) -> str:
    tree = observation.get("axtree_object")
    if not isinstance(tree, dict):
        return ""
    try:
        from browsergym.utils.obs import flatten_axtree_to_str  # type: ignore[import-not-found,import-untyped]

        return str(
            flatten_axtree_to_str(
                tree,
                extra_properties=observation.get("extra_element_properties"),
                with_visible=True,
                with_clickable=True,
                filter_visible_only=True,
            )
        )
    except (ImportError, KeyError, TypeError, ValueError):
        lines: list[str] = []
        for node in tree.get("nodes", []):
            if not isinstance(node, dict) or node.get("ignored"):
                continue
            role = str((node.get("role") or {}).get("value") or "")
            name = str((node.get("name") or {}).get("value") or "")
            bid = str(node.get("browsergym_id") or "")
            if role or name or bid:
                lines.append(f"[{bid}] {role} {name}".strip())
        return "\n".join(lines)


def _quiet_handler(root: Path) -> type[SimpleHTTPRequestHandler]:
    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    return QuietHandler
