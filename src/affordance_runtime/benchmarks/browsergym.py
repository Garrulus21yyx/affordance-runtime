"""Optional BrowserGym bridge with typed actions and full Coordinator traversal."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import shlex
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty
from time import perf_counter
from typing import Any, Callable, Sequence, cast

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks import browsergym_encoder as _browsergym_encoder
from affordance_runtime.benchmarks import browsergym_observer as _browsergym_observer
from affordance_runtime.benchmarks.browsergym_action_schema import (
    BROWSERGYM_ACTION_ARGUMENTS as _BROWSERGYM_ACTION_ARGUMENTS,
)
from affordance_runtime.benchmarks.browsergym_action_schema import (
    BrowserGymAction,
)
from affordance_runtime.benchmarks.browsergym_dom import browsergym_dom_adapter, browsergym_svg_observer
from affordance_runtime.benchmarks.browsergym_encoder import (
    BrowserGymContractBuilder,
    GeneralistBrowserGymContractBuilder,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    BROWSERGYM_VERSION,
    NIGHTLY_ACTION_FAMILY_MANIFEST,
    NIGHTLY_TASK_MANIFEST_VERSION,
    BrowserGymProfile,
    browsergym_episode_schedule,
    browsergym_failure_envelope,
    browsergym_profile,
    write_browsergym_report,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    PR_SMOKE_TASKS as _PR_SMOKE_TASKS,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    browsergym_batch_circuit_breaker as _browsergym_batch_circuit_breaker,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    cluster_browsergym_failure_envelopes as _cluster_browsergym_failure_envelopes,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    load_browsergym_checkpoints as _load_browsergym_checkpoints,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    prepare_browsergym_checkpoint_metadata as _prepare_browsergym_checkpoint_metadata,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    update_browsergym_batch_circuit_state as _update_browsergym_batch_circuit_state,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    write_browsergym_checkpoint as _write_browsergym_checkpoint,
)
from affordance_runtime.benchmarks.browsergym_miniwob_source import (
    BROWSERGYM_MINIWOB_COMMIT,
    ensure_browsergym_miniwob,
    registered_miniwob_tasks,
)
from affordance_runtime.benchmarks.browsergym_observer import BrowserGymObserver
from affordance_runtime.benchmarks.browsergym_types import (
    BROWSERGYM_BACKEND,
    BrowserGymEnvironment,
    BrowserGymEpisodeResult,
    BrowserGymEpisodeState,
    BrowserGymPolicy,
    BrowserGymPolicyRequest,
)
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
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
from affordance_runtime.coordinator import PlannerDecision, RunBudget, RunCoordinator
from affordance_runtime.generalist_planner import (
    GENERALIST_PLANNER_CONTEXT_POLICY_VERSION,
    GENERALIST_PLANNER_PROMPT_VERSION,
    GeneralistLMPlanner,
    PlannerLimits,
    PlannerProposalCandidate,
)
from affordance_runtime.grounding import EvidenceKind, GroundingSource
from affordance_runtime.model_port import ModelConfig, ModelPort
from affordance_runtime.perception import (
    GenericPerceptionOrchestrator,
    derive_perception_requirements,
    perception_task_terms,
)
from affordance_runtime.planning import (
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.visual_grounding import (
    VisualGrounderPort,
    VisualRegionProposerPort,
)

# Compatibility export for callers that used the original bridge module.
BROWSERGYM_ACTION_ARGUMENTS = _BROWSERGYM_ACTION_ARGUMENTS
# Nightly selection metadata remains available from the public bridge facade.
# Keeping this here avoids coupling benchmark callers to the matrix module split.
NIGHTLY_MANIFEST_VERSION = NIGHTLY_TASK_MANIFEST_VERSION
NIGHTLY_ACTION_FAMILIES = NIGHTLY_ACTION_FAMILY_MANIFEST
PR_SMOKE_TASKS = _PR_SMOKE_TASKS
cluster_browsergym_failure_envelopes = _cluster_browsergym_failure_envelopes
browsergym_batch_circuit_breaker = _browsergym_batch_circuit_breaker
update_browsergym_batch_circuit_state = _update_browsergym_batch_circuit_state
_fuse_visual_candidates = _browsergym_observer.fuse_visual_candidates
_json_safe = _browsergym_observer.json_safe
_refresh_dom_grounding_candidates = _browsergym_observer.refresh_dom_grounding_candidates
_visual_fallback_affordance = _browsergym_observer.visual_fallback_affordance
BrowserGymGestureEncoder = _browsergym_encoder.BrowserGymGestureEncoder
BrowserGymPointEncoder = _browsergym_encoder.BrowserGymPointEncoder
_browsergym_action_verifiers = _browsergym_encoder.browsergym_action_verifiers
_browsergym_fill_value = _browsergym_encoder.browsergym_fill_value
_browsergym_requires_keyboard_events = _browsergym_encoder.browsergym_requires_keyboard_events
_is_sortable_list_binding = _browsergym_encoder.is_sortable_list_binding
_viewport_box = _browsergym_encoder.viewport_box

BROWSERGYM_TERMINAL_COMPLETION_POLICY = "official-terminal-v1"
# BrowserGym defaults Playwright actions to 500ms.  Locally served controls can
# be visible and preflighted yet still miss that narrow window, so set one
# bounded timeout uniformly for every page action in an isolated episode.
BROWSERGYM_PAGE_ACTION_TIMEOUT_MS = 1_500
# Planner proposals are compact semantic candidates, not long-form answers.
# Keep local single-slot models responsive after a timed-out episode.
BROWSERGYM_PLANNER_MAX_TOKENS = 384


@dataclass
class BrowserGymPlanner:
    policy: BrowserGymPolicy
    episode: BrowserGymEpisodeState
    bindings: dict[str, BrowserGymAction]

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        terminal = _browsergym_terminal_decision(self.episode, state, snapshot)
        if terminal is not None:
            return terminal
        request = BrowserGymPolicyRequest(
            task_id=self.episode.task_id,
            seed=self.episode.seed,
            goal=self.episode.goal,
            step=state.step_count,
            affordances=[
                {
                    "id": item.id,
                    "role": item.role,
                    "label": item.label,
                    "action": item.action,
                    "locator": _browsergym_policy_locator(item.locator),
                    "confidence": item.confidence,
                }
                for item in snapshot.affordance_model.affordances
            ],
            previous_actions=[asdict(action) for action in self.episode.actions],
            accessibility_tree=_accessibility_tree_text(self.episode.observation),
        )
        action = self.policy.propose(request)
        if action is None:
            return PlannerDecision(
                proposal=PlannerProposal(
                    proposal_id=f"browsergym-{self.episode.task_id}-{self.episode.seed}-stopped",
                    based_on_task_revision=1,
                    based_on_state_version=state.version,
                    snapshot_id=snapshot.observation.snapshot_id,
                    action_kind=PlannerActionKind.FINISH,
                    done=True,
                    result={
                        "official_success": False,
                        "official_reward": self.episode.reward,
                        "terminated": False,
                        "truncated": False,
                        "policy_stopped": True,
                    },
                ),
                reason="policy stopped before official termination",
            )
        action.render()  # validate before constructing a contract
        proposal = _browsergym_proposal(action, self.episode, state, snapshot)
        self.bindings[proposal.proposal_id] = action
        return PlannerDecision(
            proposal=proposal,
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
    _planner: GeneralistLMPlanner = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._planner = GeneralistLMPlanner(
            self.model,
            limits=self.limits,
            config=self.config,
            max_model_calls=self.max_model_calls,
            allow_finish=False,
        )

    @property
    def model_call_count(self) -> int:
        return self._planner.model_call_count

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision | Any:
        terminal = _browsergym_terminal_decision(self.episode, state, snapshot)
        if terminal is not None:
            return terminal
        return self._planner.propose(envelope, state, snapshot)


def _browsergym_terminal_decision(
    episode: BrowserGymEpisodeState,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlannerDecision | None:
    if not episode.terminated and not episode.truncated:
        return None
    return PlannerDecision(
        proposal=PlannerProposal(
            proposal_id=f"browsergym-{episode.task_id}-{episode.seed}-official-terminal",
            based_on_task_revision=1,
            based_on_state_version=state.version,
            snapshot_id=snapshot.observation.snapshot_id,
            action_kind=PlannerActionKind.FINISH,
            done=True,
            result={
                "official_success": episode.terminated and episode.reward > 0,
                "official_reward": episode.reward,
                "terminated": episode.terminated,
                "truncated": episode.truncated,
                "completion_policy": BROWSERGYM_TERMINAL_COMPLETION_POLICY,
            },
        )
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
            payload = contract.parameters.get("action")
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
                    **(
                        {"direct_dispatch": direct_dispatch_evidence}
                        if direct_dispatch_evidence
                        else {}
                    ),
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
        targets=(task_id,),
        success_criteria=("official BrowserGym environment terminates with positive reward",),
        evidence_requirements=("official reward and termination",),
        source_request_ref=f"browsergym:{task_id}:seed:{seed}",
    )
    try:
        result = RunCoordinator(
            observer=BrowserGymObserver(session, episode, artifact_root / "screenshots" / run_id),
            planner=BrowserGymPlanner(policy, episode, bindings),
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
        ).run_sync(TaskEnvelope(task_spec=task_spec))
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
        for receipt in result.state.receipts:
            if "unsupported BrowserGym action" in receipt.message:
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
    visual_grounder: VisualGrounderPort | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
) -> BrowserGymEpisodeResult:
    """Run the same GeneralistLMPlanner port through BrowserGym's typed executor."""

    try:
        obs, info = environment.reset(seed=seed)
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
        run_id = f"browsergym-generalist-{task_id}-seed-{seed}"
        task_spec = TaskSpec(
            task_id=run_id,
            revision=1,
            objective=goal,
            operation_class=OperationClass.READ_ONLY,
            targets=(task_id,),
            success_criteria=("official BrowserGym environment terminates with positive reward",),
            evidence_requirements=("official reward and termination",),
            source_request_ref=f"browsergym:{task_id}:seed:{seed}",
        )
        perception_requirements = derive_perception_requirements(task_spec)
        planner_limits = PlannerLimits(
            max_steps=max_steps,
            max_observations=max_steps * 3 + 3,
            max_recoveries=3,
            max_effectful_actions=max_steps + 1,
        )
        planner = BrowserGymGeneralistPlanner(
            model,
            episode,
            config=ModelConfig(
                max_tokens=BROWSERGYM_PLANNER_MAX_TOKENS,
                timeout_s=model_timeout_s,
                prompt_version=GENERALIST_PLANNER_PROMPT_VERSION,
            ),
            limits=planner_limits,
            max_model_calls=max_model_calls,
        )
        result = RunCoordinator(
            observer=BrowserGymObserver(
                session,
                episode,
                artifact_root / "screenshots" / run_id,
                perception_requirements=perception_requirements,
                task_terms=perception_task_terms(task_spec),
            ),
            planner=planner,
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
        ).run_sync(TaskEnvelope(task_spec=task_spec))
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
            **_browsergym_model_stats(result.trace.nodes, planner.model_call_count),
            **_browsergym_context_stats(result.trace.nodes, planner_limits.max_affordances),
            **_browsergym_adaptive_runtime_stats(result.trace.nodes),
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
            **model_stats,
        )
    except Exception as exc:
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
            "",
        )
    finally:
        _close_quietly(environment)


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


def run_browsergym_miniwob_suite(
    output_dir: Path,
    *,
    profile: BrowserGymProfile,
    policy_command: str | Sequence[str],
    headless: bool = True,
) -> dict[str, Any]:
    """Run an official, unmodified BrowserGym track with an external policy."""

    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "BrowserGym is not installed; use an isolated affordance-runtime[browsergym] environment"
        ) from exc

    html_root = ensure_browsergym_miniwob(output_dir / "source")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _quiet_handler(html_root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    registered = registered_miniwob_tasks()
    selected, seeds = browsergym_profile(registered, profile)
    missing_tasks = sorted(set(selected) - set(registered))
    episodes: list[BrowserGymEpisodeResult] = []
    try:
        base_url = f"http://{server.server_name}:{server.server_port}/miniwob/"
        for task_id, seed in browsergym_episode_schedule(selected, seeds):
            if task_id in missing_tasks:
                continue
            environment = gym.make(
                f"browsergym/miniwob.{task_id}",
                task_kwargs={"base_url": base_url},
                headless=headless,
            )
            episodes.append(
                run_browsergym_episode(
                    cast(BrowserGymEnvironment, environment),
                    JsonLinePolicy(policy_command),
                    task_id=task_id,
                    seed=seed,
                    artifact_root=output_dir / "artifacts",
                )
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    report = write_browsergym_report(
        output_dir,
        profile=profile,
        registered_tasks=registered,
        selected_tasks=selected,
        seeds=seeds,
        episodes=episodes,
    )
    report["acceptance_errors"] = [
        *(f"registered task missing: {task}" for task in missing_tasks),
        *report["acceptance_errors"],
    ]
    (output_dir / "browsergym-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def run_browsergym_miniwob_generalist_suite(
    output_dir: Path,
    *,
    profile: BrowserGymProfile,
    model: ModelPort,
    visual_grounder: VisualGrounderPort | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
    task_ids: Sequence[str] | None = None,
    seed_count: int | None = None,
    headless: bool = True,
    resume: bool = False,
    episode_timeout_s: float = 165.0,
    model_call_timeout_s: float = 10.0,
    max_model_calls: int = 15,
    execution_reserve_s: float = 15.0,
) -> dict[str, Any]:
    """Run the standard MiniWoB matrix through the common GeneralistLMPlanner.

    This is intentionally separate from the external-policy suite: official
    score, unsupported action coverage, and runtime diagnostics remain in the
    same report schema, while no task-specific JSON-lines policy is involved.
    """

    _validate_browsergym_time_budgets(
        episode_timeout_s=episode_timeout_s,
        model_call_timeout_s=model_call_timeout_s,
        max_model_calls=max_model_calls,
        execution_reserve_s=execution_reserve_s,
    )
    run_identity = _frozen_run_identity()
    _require_frozen_profile_identity(profile, run_identity)
    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "BrowserGym is not installed; use an isolated affordance-runtime[browsergym] environment"
        ) from exc

    html_root = ensure_browsergym_miniwob(output_dir / "source")
    server_context = mp.get_context("fork")
    server_ready = server_context.Queue()
    source_server = server_context.Process(
        target=_browsergym_source_server_worker,
        args=(server_ready, str(html_root)),
    )
    source_server.start()
    try:
        server_name, server_port = server_ready.get(timeout=10)
    except Empty as exc:
        source_server.terminate()
        source_server.join(timeout=5)
        server_ready.close()
        raise RuntimeError("BrowserGym source server failed to start") from exc
    server_ready.close()
    registered = registered_miniwob_tasks()
    profile_tasks, profile_seeds = browsergym_profile(registered, profile)
    selected = tuple(task_ids) if task_ids else profile_tasks
    if len(set(selected)) != len(selected):
        raise ValueError("targeted BrowserGym task ids must be unique")
    if seed_count is not None and seed_count <= 0:
        raise ValueError("targeted BrowserGym seed count must be positive")
    seeds = tuple(range(seed_count)) if seed_count is not None else profile_seeds
    missing_tasks = sorted(set(selected) - set(registered))
    episodes: list[BrowserGymEpisodeResult] = []
    expected = {(task_id, seed) for task_id in selected if task_id not in missing_tasks for seed in seeds}
    checkpoint_dir = output_dir / "episodes"
    checkpoint_metadata = {
        "schema_version": "browsergym-generalist-checkpoint-v5",
        "run_identity": run_identity,
        "profile": profile,
        "selected_task_ids": list(selected),
        "seeds": list(seeds),
        "model_provider": model.provider,
        "model_name": model.model,
        "model_endpoint_class": model.endpoint_class,
        "visual_grounder_provider": visual_grounder.provider if visual_grounder is not None else "disabled",
        "visual_grounder_model": visual_grounder.model if visual_grounder is not None else "",
        "visual_grounder_prompt_version": visual_grounder.prompt_version if visual_grounder is not None else "",
        "visual_region_proposer_provider": visual_region_proposer.provider
        if visual_region_proposer is not None
        else "disabled",
        "visual_region_proposer_model": visual_region_proposer.model if visual_region_proposer is not None else "",
        "visual_region_proposer_prompt_version": visual_region_proposer.prompt_version
        if visual_region_proposer is not None
        else "",
        "planner_prompt_version": GENERALIST_PLANNER_PROMPT_VERSION,
        "planner_context_policy_version": GENERALIST_PLANNER_CONTEXT_POLICY_VERSION,
        "planner_schema_sha256": _planner_schema_sha256(),
        "model_max_tokens": BROWSERGYM_PLANNER_MAX_TOKENS,
        "episode_timeout_s": episode_timeout_s,
        "model_call_timeout_s": model_call_timeout_s,
        "max_model_calls": max_model_calls,
        "execution_reserve_s": execution_reserve_s,
        "terminal_completion_policy": BROWSERGYM_TERMINAL_COMPLETION_POLICY,
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
    }
    _prepare_browsergym_checkpoint_metadata(checkpoint_dir, checkpoint_metadata, resume=resume)
    reused = _load_browsergym_checkpoints(checkpoint_dir, expected) if resume else {}
    episodes.extend(reused.values())
    newly_completed = 0
    interrupted = False
    circuit_break_reason = ""
    try:
        base_url = f"http://{server_name}:{server_port}/miniwob/"
        family_map = {task: family for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items() for task in tasks}
        failure_envelopes = [
            envelope
            for episode in episodes
            if (envelope := browsergym_failure_envelope(episode, task_family_map=family_map)) is not None
        ]
        consecutive_batch_failures: list[dict[str, Any]] = []
        schema_compatible_episode_observed = any(
            episode.runtime_status == RuntimeStep.DONE.value and not episode.policy_stopped for episode in episodes
        )
        for task_id, seed in browsergym_episode_schedule(selected, seeds):
            if task_id in missing_tasks or (task_id, seed) in reused:
                continue
            episode = run_browsergym_generalist_episode_isolated(
                model,
                task_id=task_id,
                seed=seed,
                base_url=base_url,
                headless=headless,
                artifact_root=output_dir / "artifacts",
                timeout_s=episode_timeout_s,
                model_timeout_s=model_call_timeout_s,
                max_model_calls=max_model_calls,
                visual_grounder=visual_grounder,
                visual_region_proposer=visual_region_proposer,
            )
            episodes.append(episode)
            _write_browsergym_checkpoint(checkpoint_dir, episode)
            newly_completed += 1
            envelope = browsergym_failure_envelope(episode, task_family_map=family_map)
            if envelope is not None:
                failure_envelopes.append(envelope)
            schema_compatible_episode_observed, circuit_break_reason = update_browsergym_batch_circuit_state(
                consecutive_batch_failures,
                episode,
                envelope,
                schema_compatible_episode_observed=schema_compatible_episode_observed,
            )
            if circuit_break_reason:
                break
    except KeyboardInterrupt:
        interrupted = True
    finally:
        if source_server.is_alive():
            source_server.terminate()
        source_server.join(timeout=5)
    episodes.sort(key=lambda item: (item.task_id, item.seed))
    report = write_browsergym_report(
        output_dir,
        profile=profile,
        registered_tasks=registered,
        selected_tasks=selected,
        seeds=seeds,
        episodes=episodes,
    )
    report.update(
        {
            "planner_boundary": "GeneralistLMPlanner",
            "model_provider": model.provider,
            "model_name": model.model,
            "model_endpoint_class": model.endpoint_class,
            "checkpoint_reused_episode_count": len(reused),
            "checkpoint_new_episode_count": newly_completed,
            "checkpoint_metadata": checkpoint_metadata,
            "batch_circuit_break_reason": circuit_break_reason,
            "run_complete": (
                not interrupted
                and not circuit_break_reason
                and len({(item.task_id, item.seed) for item in episodes}) == len(expected)
            ),
        }
    )
    report["official_score_claimed"] = bool(
        profile == "nightly" and report["run_complete"] and not report["acceptance_errors"]
    )
    report["batch_status"] = (
        "complete" if report["run_complete"] else ("incomplete_diagnostic" if profile == "diagnostic" else "incomplete")
    )
    report["acceptance_errors"] = [
        *(f"registered task missing: {task}" for task in missing_tasks),
        *(["run interrupted; resume with --resume"] if interrupted else []),
        *([f"batch circuit breaker: {circuit_break_reason}"] if circuit_break_reason else []),
        *report["acceptance_errors"],
    ]
    (output_dir / "browsergym-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _validate_browsergym_time_budgets(
    *,
    episode_timeout_s: float,
    model_call_timeout_s: float,
    max_model_calls: int,
    execution_reserve_s: float,
) -> None:
    if min(episode_timeout_s, model_call_timeout_s) <= 0 or max_model_calls <= 0 or execution_reserve_s < 0:
        raise ValueError("BrowserGym time budgets must be positive")
    if model_call_timeout_s * max_model_calls + execution_reserve_s > episode_timeout_s:
        raise ValueError("model-call budget plus execution reserve exceeds episode timeout")


def _planner_schema_sha256() -> str:
    payload = PlannerProposalCandidate.model_json_schema()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _frozen_run_identity() -> dict[str, str | bool]:
    """Bind a matrix to its revision and exact runtime-source contents."""

    repository = Path(__file__).resolve().parents[3]
    source_tree_sha256 = _runtime_source_sha256(repository)
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {
            "git_sha": "unavailable",
            "working_tree_clean": False,
            "source_tree_sha256": source_tree_sha256,
        }
    return {
        "git_sha": revision,
        "working_tree_clean": not dirty,
        "source_tree_sha256": source_tree_sha256,
    }


def _runtime_source_sha256(repository: Path) -> str:
    """Hash runtime inputs while deliberately excluding local secrets and outputs."""

    candidates = list((repository / "src").rglob("*.py"))
    candidates.extend(
        path
        for path in (
            repository / "scripts" / "run_browsergym_generalist.py",
            repository / "pyproject.toml",
        )
        if path.is_file()
    )
    requirements = repository / "requirements"
    if requirements.is_dir():
        candidates.extend(path for path in requirements.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(set(candidates)):
        relative = path.relative_to(repository).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _require_frozen_profile_identity(
    profile: BrowserGymProfile,
    run_identity: dict[str, str | bool],
) -> None:
    if profile in {"nightly", "release"} and not run_identity["working_tree_clean"]:
        raise ValueError(
            f"Frozen {profile} requires a clean committed worktree; "
            "choose a new output directory after committing"
        )


def _browsergym_model_stats(nodes: Sequence[Any], attempted_calls: int) -> dict[str, Any]:
    records = [
        node.payload.get("model_call")
        for node in nodes
        if node.kind == "PlannerProposalProduced" and isinstance(node.payload.get("model_call"), dict)
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


def _browsergym_adaptive_runtime_stats(nodes: Sequence[Any]) -> dict[str, Any]:
    """Project M8.5 trace decisions into the public episode schema."""

    route_nodes = [node for node in nodes if node.kind == "RouteSelected"]
    route_sources = [str(node.payload.get("source") or "") for node in route_nodes]
    conflict_count = 0
    for node in nodes:
        if node.kind != "SourceAssertionsArbitrated":
            continue
        decisions = node.payload.get("decisions")
        if not isinstance(decisions, list):
            continue
        conflict_count += sum(
            isinstance(item, dict) and str(item.get("status") or "") in {"conflict", "inconclusive", "reobserve"}
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


def _browsergym_context_stats(nodes: Sequence[Any], affordance_limit: int) -> dict[str, Any]:
    """Recover the final bounded planner context without retaining its content."""

    contexts = [
        node.payload.get("context")
        for node in nodes
        if node.kind == "PlannerContextBuilt" and isinstance(node.payload.get("context"), dict)
    ]
    if not contexts:
        return {
            "planner_context_size": 0,
            "planner_context_truncation": "unknown",
            "planner_affordance_count": 0,
            "planner_permitted_action_kinds": [],
        }
    context = contexts[-1]
    size = len(json.dumps(context, sort_keys=True, separators=(",", ":")))
    affordances = context.get("affordances")
    affordance_count = int(context.get("affordance_count") or 0)
    if not affordance_count and isinstance(affordances, list):
        affordance_count = len(affordances)
    truncation = "affordance_limit_reached" if affordance_count >= affordance_limit else "not_observed"
    permitted = context.get("permitted_action_kinds")
    return {
        "planner_context_size": size,
        "planner_context_truncation": truncation,
        "planner_affordance_count": affordance_count,
        "planner_permitted_action_kinds": [str(item) for item in permitted] if isinstance(permitted, list) else [],
    }


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
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlannerProposal:
    affordance = _action_affordance(action, snapshot)
    semantic_kind = {
        "click": PlannerActionKind.ACTIVATE,
        "dblclick": PlannerActionKind.ACTIVATE,
        "fill": PlannerActionKind.TYPE_TEXT,
        "select_option": PlannerActionKind.SELECT_OPTION,
        "press": PlannerActionKind.PRESS_KEY,
    }.get(action.name)
    if semantic_kind is None:
        raise ValueError(f"unsupported BrowserGym semantic action: {action.name}")
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
        based_on_state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
        subgoal=episode.goal,
        action_kind=semantic_kind,
        target_affordance_id=affordance.id,
        parameters=parameters,
        expected_effects=("BrowserGym action has no action error",),
        evidence_requirements=("last_action_error receipt field is empty",),
    )


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
