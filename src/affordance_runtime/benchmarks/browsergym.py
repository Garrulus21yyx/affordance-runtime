"""Optional BrowserGym bridge with typed actions and full Coordinator traversal."""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
from dataclasses import asdict, dataclass, field, replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, Sequence

from affordance_runtime.artifacts import ArtifactStore
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
    VerifierSpec,
)
from affordance_runtime.coordinator import PlannerDecision, RunBudget, RunCoordinator
from affordance_runtime.generalist_planner import GENERALIST_PLANNER_PROMPT_VERSION, GeneralistLMPlanner
from affordance_runtime.model_port import ModelPort
from affordance_runtime.planning import ContractBuilder, PlannerActionKind, PlannerProposal
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec

BROWSERGYM_VERSION = "0.14.3"
BROWSERGYM_MINIWOB_COMMIT = "7fd85d71a4b60325c6585396ec4f48377d049838"
BROWSERGYM_BACKEND = "browsergym"

PR_SMOKE_TASKS = (
    "click-button",
    "enter-text",
    "choose-list",
    "click-dialog",
    "click-button-sequence",
    "form-sequence",
)

# This is deliberately narrower than BrowserGym's Python execution surface.
# Values are accepted argument names; arbitrary code and unknown arguments fail.
BROWSERGYM_ACTION_ARGUMENTS: dict[str, frozenset[str]] = {
    "noop": frozenset(),
    "click": frozenset({"bid", "button", "modifiers"}),
    "dblclick": frozenset({"bid", "button", "modifiers"}),
    "fill": frozenset({"bid", "value"}),
    "select_option": frozenset({"bid", "options"}),
    "hover": frozenset({"bid"}),
    "press": frozenset({"bid", "key_comb"}),
    "focus": frozenset({"bid"}),
    "clear": frozenset({"bid"}),
    "drag_and_drop": frozenset({"from_bid", "to_bid"}),
    "scroll": frozenset({"delta_x", "delta_y"}),
    "mouse_move": frozenset({"x", "y"}),
    "mouse_click": frozenset({"x", "y", "button"}),
    "mouse_dblclick": frozenset({"x", "y", "button"}),
    "mouse_down": frozenset({"button"}),
    "mouse_up": frozenset({"button"}),
    "keyboard_press": frozenset({"key"}),
    "keyboard_type": frozenset({"text"}),
    "go_back": frozenset(),
    "go_forward": frozenset(),
    "goto": frozenset({"url"}),
    "new_tab": frozenset(),
    "tab_close": frozenset(),
    "tab_focus": frozenset({"index"}),
    "send_msg_to_user": frozenset({"text"}),
    "report_infeasible": frozenset({"reason"}),
}

_POSITIONAL_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "click": ("bid",),
    "dblclick": ("bid",),
    "fill": ("bid", "value"),
    "select_option": ("bid", "options"),
    "hover": ("bid",),
    "press": ("bid", "key_comb"),
    "focus": ("bid",),
    "clear": ("bid",),
    "drag_and_drop": ("from_bid", "to_bid"),
    "scroll": ("delta_x", "delta_y"),
    "mouse_move": ("x", "y"),
    "mouse_click": ("x", "y"),
    "mouse_dblclick": ("x", "y"),
    "keyboard_press": ("key",),
    "keyboard_type": ("text",),
    "goto": ("url",),
    "tab_focus": ("index",),
    "send_msg_to_user": ("text",),
    "report_infeasible": ("reason",),
}

_STRING_ARGUMENTS = {
    "bid",
    "from_bid",
    "to_bid",
    "button",
    "value",
    "key_comb",
    "key",
    "text",
    "url",
    "reason",
}
_NUMBER_ARGUMENTS = {"delta_x", "delta_y", "x", "y"}


@dataclass(frozen=True)
class BrowserGymAction:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        allowed = BROWSERGYM_ACTION_ARGUMENTS.get(self.name)
        if allowed is None:
            raise ValueError(f"unsupported BrowserGym action: {self.name}")
        unknown = sorted(set(self.arguments) - allowed)
        if unknown:
            raise ValueError(f"unsupported arguments for {self.name}: {', '.join(unknown)}")
        positional = _POSITIONAL_ARGUMENTS.get(self.name, ())
        missing = [name for name in positional if name not in self.arguments]
        if missing:
            raise ValueError(f"missing arguments for {self.name}: {', '.join(missing)}")
        for name, value in self.arguments.items():
            if name in _STRING_ARGUMENTS and not isinstance(value, str):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected string")
            if name in _NUMBER_ARGUMENTS and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected number")
            if name == "index" and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected integer")
            if name == "modifiers" and (
                not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            ):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected string list")
            if name == "options" and not (
                isinstance(value, str)
                or (isinstance(value, list) and all(isinstance(item, str) for item in value))
            ):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected string or string list")
        rendered = [repr(self.arguments[name]) for name in positional]
        rendered.extend(
            f"{name}={self.arguments[name]!r}"
            for name in sorted(self.arguments)
            if name not in positional
        )
        return f"{self.name}({', '.join(rendered)})"


@dataclass(frozen=True)
class BrowserGymPolicyRequest:
    task_id: str
    seed: int
    goal: str
    step: int
    affordances: list[dict[str, Any]]
    previous_actions: list[dict[str, Any]]
    accessibility_tree: str = ""


class BrowserGymPolicy(Protocol):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction | None: ...

    def close(self) -> None: ...


class BrowserGymEnvironment(Protocol):
    @property
    def unwrapped(self) -> Any: ...

    def reset(self, *, seed: int) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]: ...

    def close(self) -> None: ...


@dataclass
class BrowserGymEpisodeState:
    task_id: str
    seed: int
    goal: str
    observation: dict[str, Any]
    info: dict[str, Any]
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    actions: list[BrowserGymAction] = field(default_factory=list)


@dataclass
class BrowserGymObserver:
    session: BrowserSession
    episode: BrowserGymEpisodeState
    screenshot_dir: Path
    sequence: int = 0
    lease_ttl_ms: int = 120_000

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot = self.screenshot_dir / f"observation-{self.sequence:04d}.png"
        snapshot = self.session.capture(
            page_id=self.episode.task_id,
            ttl_ms=self.lease_ttl_ms,
            screenshot_path=str(screenshot),
        )
        metadata = {
            **snapshot.observation.metadata,
            "browsergym": {
                "goal": self.episode.goal,
                "reward": self.episode.reward,
                "terminated": self.episode.terminated,
                "truncated": self.episode.truncated,
                "task_info": _json_safe(self.episode.info.get("task_info", {})),
            },
        }
        return BrowserSnapshot(
            replace(snapshot.observation, metadata=metadata),
            snapshot.affordance_model,
        )


@dataclass
class BrowserGymPlanner:
    policy: BrowserGymPolicy
    episode: BrowserGymEpisodeState
    bindings: dict[str, BrowserGymAction]

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        if self.episode.terminated or self.episode.truncated:
            return PlannerDecision(
                proposal=PlannerProposal(
                    proposal_id=f"browsergym-{self.episode.task_id}-{self.episode.seed}-finish",
                    based_on_task_revision=1,
                    based_on_state_version=state.version,
                    snapshot_id=snapshot.observation.snapshot_id,
                    action_kind=PlannerActionKind.FINISH,
                    done=True,
                    result={
                        "official_success": self.episode.terminated and self.episode.reward > 0,
                        "official_reward": self.episode.reward,
                        "terminated": self.episode.terminated,
                        "truncated": self.episode.truncated,
                    },
                )
            )
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
                    "locator": item.locator,
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


class AgentLabPlannerAdapter(BrowserGymPlanner):
    """Named AgentLab/BrowserGym action adapter at the semantic planner boundary."""


@dataclass
class BrowserGymContractBuilder(ContractBuilder):
    bindings: dict[str, BrowserGymAction] = field(default_factory=dict)

    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        contract = super().build(proposal, task_spec, state, snapshot)
        action = self.bindings.get(proposal.proposal_id)
        if action is None:
            raise ValueError(f"BrowserGym action binding is missing: {proposal.proposal_id}")
        return replace(
            contract,
            action=action.name,
            backend=BROWSERGYM_BACKEND,
            parameters={"action": asdict(action)},
            verifier_plan=[VerifierSpec("evidence", "last_action_error", "")],
            contract_hash="",
        )


@dataclass
class GeneralistBrowserGymContractBuilder(ContractBuilder):
    """Bind the common semantic vocabulary to typed BrowserGym actions."""

    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        contract = super().build(proposal, task_spec, state, snapshot)
        affordance = next(item for item in snapshot.affordance_model.affordances if item.id == proposal.target_affordance_id)
        bid = str(affordance.locator.get("bid") or "")
        if not bid:
            raise ValueError("Generalist BrowserGym binding requires an affordance bid")
        if proposal.action_kind == PlannerActionKind.ACTIVATE:
            select_owner_bid = str(affordance.locator.get("select_owner_bid") or "")
            select_option = str(affordance.locator.get("select_option") or "")
            if select_owner_bid and select_option:
                action = BrowserGymAction(
                    "select_option", {"bid": select_owner_bid, "options": select_option}
                )
            else:
                action = BrowserGymAction("click", {"bid": bid})
        elif proposal.action_kind == PlannerActionKind.TYPE_TEXT:
            action = BrowserGymAction("fill", {"bid": bid, "value": str(proposal.parameters["text"])})
        elif proposal.action_kind == PlannerActionKind.SELECT_OPTION:
            option = proposal.parameters["option"]
            action = BrowserGymAction("select_option", {"bid": bid, "options": option})
        else:
            raise ValueError(f"unsupported generalist BrowserGym semantic action: {proposal.action_kind.value}")
        action.render()
        return replace(
            contract,
            action=action.name,
            backend=BROWSERGYM_BACKEND,
            parameters={"action": asdict(action)},
            verifier_plan=[VerifierSpec("evidence", "last_action_error", "")],
            contract_hash="",
        )


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
            rendered = action.render()
            obs, reward, terminated, truncated, info = self.environment.step(rendered)
            self.episode.observation = obs
            self.episode.reward = float(reward)
            self.episode.terminated = bool(terminated)
            self.episode.truncated = bool(truncated)
            self.episode.info = info
            self.episode.actions.append(action)
            action_error = str(obs.get("last_action_error") or info.get("last_action_error") or "")
            return ExecutionReceipt(
                contract.id,
                self.backend,
                not action_error,
                observation.environment_revision,
                observation.environment_revision,
                round((perf_counter() - started) * 1_000, 3),
                evidence={
                    "browsergym_action": rendered,
                    "last_action_error": action_error,
                    "official_reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "task_info": _json_safe(info.get("task_info", {})),
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


@dataclass(frozen=True)
class BrowserGymEpisodeResult:
    task_id: str
    seed: int
    runtime_status: str
    official_success: bool
    official_reward: float
    terminated: bool
    truncated: bool
    action_count: int
    action_families: list[str]
    unsupported_actions: list[str]
    runtime_error: str
    policy_stopped: bool
    trace_path: str


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
        policy.close()
        environment.close()
        raise
    goal = _goal_text(obs.get("goal", ""))
    episode = BrowserGymEpisodeState(task_id, seed, goal, obs, info)
    session = BrowserSession(environment.unwrapped.page)
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
        if "unsupported BrowserGym action:" in planner_error or "unsupported BrowserGym semantic action:" in planner_error:
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
        policy.close()
        environment.close()


def run_browsergym_generalist_episode(
    environment: BrowserGymEnvironment,
    model: ModelPort,
    *,
    task_id: str,
    seed: int,
    artifact_root: Path,
    max_steps: int = 50,
) -> BrowserGymEpisodeResult:
    """Run the same GeneralistLMPlanner port through BrowserGym's typed executor."""

    try:
        obs, info = environment.reset(seed=seed)
        goal = _goal_text(obs.get("goal", ""))
        episode = BrowserGymEpisodeState(task_id, seed, goal, obs, info)
        session = BrowserSession(environment.unwrapped.page)
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
        result = RunCoordinator(
            observer=BrowserGymObserver(session, episode, artifact_root / "screenshots" / run_id),
            planner=GeneralistLMPlanner(model),
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
        environment.close()


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


def browsergym_profile(task_ids: Sequence[str], profile: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    available = tuple(sorted(task_ids))
    if profile == "pr":
        return PR_SMOKE_TASKS, (0, 1, 2)
    if profile == "nightly":
        return available[:30], tuple(range(10))
    if profile == "release":
        return available, tuple(range(5))
    raise ValueError(f"unsupported BrowserGym profile: {profile}")


def write_browsergym_report(
    output_dir: Path,
    *,
    profile: str,
    registered_tasks: Sequence[str],
    selected_tasks: Sequence[str],
    seeds: Sequence[int],
    episodes: Sequence[BrowserGymEpisodeResult],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = tuple(selected_tasks)
    expected = {(task, seed) for task in selected for seed in seeds}
    observed = {(episode.task_id, episode.seed) for episode in episodes}
    missing = sorted(expected - observed)
    errors = [f"missing episode: {task}:seed-{seed}" for task, seed in missing]
    errors.extend(
        f"unsupported actions: {episode.task_id}:seed-{episode.seed}:{','.join(episode.unsupported_actions)}"
        for episode in episodes
        if episode.unsupported_actions
    )
    errors.extend(
        f"runtime failure: {episode.task_id}:seed-{episode.seed}:{episode.runtime_error}"
        for episode in episodes
        if episode.runtime_status != RuntimeStep.DONE.value
    )
    errors.extend(
        f"policy stopped: {episode.task_id}:seed-{episode.seed}"
        for episode in episodes
        if episode.policy_stopped
    )
    statistics = {
        task: _task_statistics([episode for episode in episodes if episode.task_id == task])
        for task in selected
    }
    report = {
        "schema_version": "browsergym-full-path-v1",
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
        "profile": profile,
        "official_track": True,
        "fault_injection": False,
        "registered_task_count": len(set(registered_tasks)),
        "selected_task_count": len(selected),
        "seed_count": len(tuple(seeds)),
        "expected_episode_count": len(expected),
        "observed_episode_count": len(episodes),
        "coverage_rate": len(observed & expected) / len(expected) if expected else 0.0,
        "official_success_rate": (
            sum(episode.official_success for episode in episodes) / len(episodes) if episodes else 0.0
        ),
        "mean_official_reward": (
            sum(episode.official_reward for episode in episodes) / len(episodes) if episodes else 0.0
        ),
        "task_statistics": statistics,
        "action_family_coverage": sorted({name for episode in episodes for name in episode.action_families}),
        "unsupported_actions": sorted({name for episode in episodes for name in episode.unsupported_actions}),
        "runtime_failure_count": sum(
            episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped
            for episode in episodes
        ),
        "episodes": [asdict(episode) for episode in episodes],
        "acceptance_errors": errors,
    }
    (output_dir / "browsergym-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def ensure_browsergym_miniwob(checkout_root: Path) -> Path:
    """Fetch the exact MiniWoB source pinned by BrowserGym 0.14.3."""

    repository = checkout_root.resolve() / "MiniWoB-plusplus"
    checkout_root.mkdir(parents=True, exist_ok=True)
    if not (repository / ".git").exists():
        _git(
            checkout_root,
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            "https://github.com/Farama-Foundation/MiniWoB-plusplus.git",
            str(repository),
        )
        _git(repository, "sparse-checkout", "init", "--cone")
        _git(repository, "sparse-checkout", "set", "miniwob/html")
    _git(repository, "fetch", "--depth", "1", "origin", BROWSERGYM_MINIWOB_COMMIT)
    _git(repository, "checkout", "--detach", BROWSERGYM_MINIWOB_COMMIT)
    commit = _git(repository, "rev-parse", "HEAD", capture=True)
    if commit != BROWSERGYM_MINIWOB_COMMIT:
        raise RuntimeError(f"BrowserGym MiniWoB commit mismatch: {commit}")
    root = repository / "miniwob" / "html"
    if not (root / "miniwob").is_dir():
        raise RuntimeError(f"BrowserGym MiniWoB HTML root is missing: {root}")
    return root


def registered_miniwob_tasks() -> tuple[str, ...]:
    """Discover BrowserGym registrations without silently maintaining a local list."""

    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "BrowserGym is not installed; use an isolated affordance-runtime[browsergym] environment"
        ) from exc
    prefix = "browsergym/miniwob."
    return tuple(sorted(str(item).removeprefix(prefix) for item in gym.envs.registry if str(item).startswith(prefix)))


def run_browsergym_miniwob_suite(
    output_dir: Path,
    *,
    profile: str,
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
        for task_id in selected:
            if task_id in missing_tasks:
                continue
            for seed in seeds:
                environment = gym.make(
                    f"browsergym/miniwob.{task_id}",
                    task_kwargs={"base_url": base_url},
                    headless=headless,
                )
                episodes.append(
                    run_browsergym_episode(
                        environment,
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
    (output_dir / "browsergym-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def run_browsergym_miniwob_generalist_suite(
    output_dir: Path,
    *,
    profile: str,
    model: ModelPort,
    headless: bool = True,
    resume: bool = False,
) -> dict[str, Any]:
    """Run the standard MiniWoB matrix through the common GeneralistLMPlanner.

    This is intentionally separate from the external-policy suite: official
    score, unsupported action coverage, and runtime diagnostics remain in the
    same report schema, while no task-specific JSON-lines policy is involved.
    """

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
    expected = {(task_id, seed) for task_id in selected if task_id not in missing_tasks for seed in seeds}
    checkpoint_dir = output_dir / "episodes"
    checkpoint_metadata = {
        "schema_version": "browsergym-generalist-checkpoint-v1",
        "profile": profile,
        "model_provider": model.provider,
        "model_name": model.model,
        "model_endpoint_class": model.endpoint_class,
        "planner_prompt_version": GENERALIST_PLANNER_PROMPT_VERSION,
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
    }
    _prepare_browsergym_checkpoint_metadata(checkpoint_dir, checkpoint_metadata, resume=resume)
    reused = _load_browsergym_checkpoints(checkpoint_dir, expected) if resume else {}
    episodes.extend(reused.values())
    newly_completed = 0
    interrupted = False
    try:
        base_url = f"http://{server.server_name}:{server.server_port}/miniwob/"
        for task_id in selected:
            if task_id in missing_tasks:
                continue
            for seed in seeds:
                if (task_id, seed) in reused:
                    continue
                environment = gym.make(
                    f"browsergym/miniwob.{task_id}",
                    task_kwargs={"base_url": base_url},
                    headless=headless,
                )
                episode = run_browsergym_generalist_episode(
                    environment,
                    model,
                    task_id=task_id,
                    seed=seed,
                    artifact_root=output_dir / "artifacts",
                )
                episodes.append(episode)
                _write_browsergym_checkpoint(checkpoint_dir, episode)
                newly_completed += 1
    except KeyboardInterrupt:
        interrupted = True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
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
            "run_complete": not interrupted and len({(item.task_id, item.seed) for item in episodes}) == len(expected),
        }
    )
    report["acceptance_errors"] = [
        *(f"registered task missing: {task}" for task in missing_tasks),
        *( ["run interrupted; resume with --resume"] if interrupted else [] ),
        *report["acceptance_errors"],
    ]
    (output_dir / "browsergym-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def _checkpoint_filename(task_id: str, seed: int) -> str:
    safe_task = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in task_id)
    return f"{safe_task}-seed-{seed}.json"


def _prepare_browsergym_checkpoint_metadata(
    directory: Path, metadata: dict[str, str], *, resume: bool
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "matrix-metadata.json"
    episode_files = list(directory.glob("*-seed-*.json"))
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored != metadata:
            raise ValueError("BrowserGym checkpoint metadata does not match the requested matrix")
        return
    if resume and episode_files:
        raise ValueError("BrowserGym checkpoints lack matrix metadata; cannot safely resume")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _write_browsergym_checkpoint(directory: Path, episode: BrowserGymEpisodeResult) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _checkpoint_filename(episode.task_id, episode.seed)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(episode), indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _load_browsergym_checkpoints(
    directory: Path, expected: set[tuple[str, int]]
) -> dict[tuple[str, int], BrowserGymEpisodeResult]:
    if not directory.exists():
        return {}
    results: dict[tuple[str, int], BrowserGymEpisodeResult] = {}
    for path in directory.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"invalid BrowserGym checkpoint: {path}")
        episode = BrowserGymEpisodeResult(**payload)
        key = (episode.task_id, episode.seed)
        if key in expected:
            if key in results:
                raise ValueError(f"duplicate BrowserGym checkpoint: {key[0]}:seed-{key[1]}")
            results[key] = episode
    return results


def _action_affordance(action: BrowserGymAction, snapshot: BrowserSnapshot) -> Affordance:
    bid = str(action.arguments.get("bid") or action.arguments.get("from_bid") or "")
    selector = f"[bid='{bid.replace(chr(39), chr(92) + chr(39))}']" if bid else ""
    match = next(
        (
            item
            for item in snapshot.affordance_model.affordances
            if item.locator.get("bid") == bid or item.locator.get("selector") == selector
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
        locator={"bid": bid, "selector": selector, "action_name": action.name},
        lease=lease,
        backend_candidates=[BROWSERGYM_BACKEND],
        risk=RiskLevel.LOW,
    )


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
    }.get(action.name)
    if semantic_kind is None:
        raise ValueError(f"unsupported BrowserGym semantic action: {action.name}")
    parameters: dict[str, Any] = {}
    if semantic_kind == PlannerActionKind.TYPE_TEXT:
        parameters["text"] = str(action.arguments["value"])
    elif semantic_kind == PlannerActionKind.SELECT_OPTION:
        value = action.arguments["options"]
        parameters["option"] = value if isinstance(value, list) else str(value)
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
        from browsergym.utils.obs import flatten_axtree_to_str  # type: ignore[import-not-found]

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


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(item) for item in value]
        return str(value)


def _task_statistics(episodes: Sequence[BrowserGymEpisodeResult]) -> dict[str, float | int]:
    if not episodes:
        return {"episodes": 0, "success_rate": 0.0, "mean_reward": 0.0, "reward_variance": 0.0}
    rewards = [episode.official_reward for episode in episodes]
    mean = sum(rewards) / len(rewards)
    return {
        "episodes": len(episodes),
        "success_rate": sum(episode.official_success for episode in episodes) / len(episodes),
        "mean_reward": mean,
        "reward_variance": sum((reward - mean) ** 2 for reward in rewards) / len(rewards),
    }


def _quiet_handler(root: Path) -> type[SimpleHTTPRequestHandler]:
    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    return QuietHandler


def _git(cwd: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(  # noqa: S603 - fixed git executable and repository arguments
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip() if capture else ""
