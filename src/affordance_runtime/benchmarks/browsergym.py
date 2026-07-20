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
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel

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

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot = self.screenshot_dir / f"observation-{self.sequence:04d}.png"
        snapshot = self.session.capture(page_id=self.episode.task_id, screenshot_path=str(screenshot))
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

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        if self.episode.terminated or self.episode.truncated:
            return PlannerDecision(
                done=True,
                result={
                    "official_success": self.episode.terminated and self.episode.reward > 0,
                    "official_reward": self.episode.reward,
                    "terminated": self.episode.terminated,
                    "truncated": self.episode.truncated,
                },
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
        )
        action = self.policy.propose(request)
        if action is None:
            return PlannerDecision(
                done=True,
                result={
                    "official_success": False,
                    "official_reward": self.episode.reward,
                    "terminated": False,
                    "truncated": False,
                    "policy_stopped": True,
                },
                reason="policy stopped before official termination",
            )
        action.render()  # validate before constructing a contract
        affordance = _action_affordance(action, snapshot)
        contract = ActionContract.from_affordance(
            affordance,
            intent=self.episode.goal,
            backend=BROWSERGYM_BACKEND,
            parameters={"action": asdict(action)},
            verifier_plan=[VerifierSpec("evidence", "last_action_error", "")],
        )
        return PlannerDecision(contract=replace(contract, action=action.name, contract_hash=""))


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
    try:
        result = RunCoordinator(
            observer=BrowserGymObserver(session, episode, artifact_root / "screenshots" / run_id),
            planner=BrowserGymPlanner(policy, episode),
            executor=BrowserGymExecutor(environment, episode),
            artifacts=ArtifactStore(artifact_root / "runs"),
            budget=RunBudget(
                max_steps=max_steps,
                max_observations=max_steps * 3 + 3,
                max_replans=max_steps + 1,
                max_recoveries=3,
                max_effectful_actions=max_steps + 1,
            ),
        ).run_sync(TaskEnvelope(run_id, goal))
        for receipt in result.state.receipts:
            if "unsupported BrowserGym action" in receipt.message:
                unsupported.append(receipt.message.rsplit(":", 1)[-1].strip())
        trace_path = next((item.path for item in result.artifacts if item.path.endswith("events.jsonl")), "")
        return BrowserGymEpisodeResult(
            task_id,
            seed,
            result.status.value,
            bool(result.result.get("official_success", False)),
            float(result.result.get("official_reward", episode.reward)),
            episode.terminated,
            episode.truncated,
            len(episode.actions),
            sorted({action.name for action in episode.actions}),
            sorted(set(unsupported)),
            result_error or (result.error_code.value if result.error_code else ""),
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
            "",
        )
    finally:
        policy.close()
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
        "runtime_failure_count": sum(episode.runtime_status != RuntimeStep.DONE.value for episode in episodes),
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


def _action_affordance(action: BrowserGymAction, snapshot: BrowserSnapshot) -> Affordance:
    bid = str(action.arguments.get("bid") or action.arguments.get("from_bid") or "")
    selector = f"[bid='{bid.replace(chr(39), chr(92) + chr(39))}']" if bid else ""
    match = next(
        (item for item in snapshot.affordance_model.affordances if item.locator.get("selector") == selector),
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


def _goal_text(goal: Any) -> str:
    if isinstance(goal, str):
        return goal
    if isinstance(goal, list):
        return "\n".join(str(item.get("text") or "") for item in goal if isinstance(item, dict)).strip()
    return str(goal)


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
