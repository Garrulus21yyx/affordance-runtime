"""Legacy task-specific MiniWoB++ compatibility diagnostic.

The current M8.2B scored path is the BrowserGym Generalist planner. This
module is retained only to reproduce earlier M8 compatibility evidence; its
task-specific parsing and selectors make it ineligible for M8.2B scoring.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import asdict, dataclass, replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.contracts import ActionContract
from affordance_runtime.executors import DomExecutor

MINIWOB_REPOSITORY = "https://github.com/Farama-Foundation/MiniWoB-plusplus.git"
MINIWOB_COMMIT = "eb59fed60fabe8951350275ba8650633b740013b"
LEGACY_MINIWOB_DIAGNOSTIC_VERSION = "legacy-task-specific-v1"


@dataclass(frozen=True)
class MiniWobTask:
    task_id: str
    family: str


@dataclass(frozen=True)
class MiniWobEpisode:
    task_id: str
    family: str
    seed: int
    success: bool
    done: bool
    raw_reward: float
    reward: float
    reward_reason: str
    query: str
    action_count: int
    failed_action_count: int
    diagnostic: str


CURATED_TASKS = (
    MiniWobTask("click-button", "click"),
    MiniWobTask("enter-text", "type"),
    MiniWobTask("choose-list", "select"),
    MiniWobTask("click-dialog", "dialog"),
    MiniWobTask("click-button-sequence", "sequence"),
    MiniWobTask("form-sequence", "form"),
)


def ensure_official_miniwob(checkout_root: Path) -> Path:
    checkout_root = checkout_root.resolve()
    repository = checkout_root / "MiniWoB-plusplus"
    checkout_root.mkdir(parents=True, exist_ok=True)
    if not (repository / ".git").exists():
        _git(
            checkout_root,
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            MINIWOB_REPOSITORY,
            str(repository),
        )
        _git(repository, "sparse-checkout", "init", "--cone")
        _git(repository, "sparse-checkout", "set", "miniwob/html")
    _git(repository, "fetch", "--depth", "1", "origin", MINIWOB_COMMIT)
    _git(repository, "checkout", "--detach", MINIWOB_COMMIT)
    commit = _git(repository, "rev-parse", "HEAD", capture=True)
    if commit != MINIWOB_COMMIT:
        raise RuntimeError(f"official MiniWoB++ commit mismatch: expected {MINIWOB_COMMIT}, got {commit}")
    html_root = repository / "miniwob" / "html"
    if not html_root.is_dir():
        raise RuntimeError(f"official MiniWoB++ HTML root is missing: {html_root}")
    return html_root


def run_official_miniwob_suite(
    output_dir: Path,
    *,
    seeds: tuple[int, ...] = (0, 1, 2),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_root = ensure_official_miniwob(output_dir / "source")
    handler = _quiet_handler(html_root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    episodes: list[MiniWobEpisode] = []
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        for task in CURATED_TASKS:
            url = f"{base_url}/miniwob/{task.task_id}.html"
            with BrowserSession.launch(url) as session:
                for seed in seeds:
                    session.open(url)
                    receipts: list[dict[str, Any]] = []
                    query = ""
                    diagnostic = ""
                    reward: dict[str, Any] = {"done": False, "raw_reward": 0.0, "reward": 0.0, "reason": ""}
                    try:
                        session.evaluate(f"Math.seedrandom({seed}); core.startEpisodeReal();")
                        query = str(session.text_content("#query") or "").strip()
                        _solve_task(task.task_id, query, session, receipts)
                        reward = session.evaluate(
                            "() => ({done: WOB_DONE_GLOBAL, raw_reward: WOB_RAW_REWARD_GLOBAL, reward: WOB_REWARD_GLOBAL, reason: WOB_REWARD_REASON || ''})"
                        )
                    except Exception as exc:
                        diagnostic = f"{type(exc).__name__}: {exc}"
                    failed_actions = sum(not bool(receipt.get("success")) for receipt in receipts)
                    done = bool(reward.get("done"))
                    raw_reward = float(reward.get("raw_reward", 0.0))
                    episodes.append(
                        MiniWobEpisode(
                            task.task_id,
                            task.family,
                            seed,
                            done and raw_reward == 1.0 and failed_actions == 0,
                            done,
                            raw_reward,
                            float(reward.get("reward", 0.0)),
                            str(reward.get("reason", "")),
                            query,
                            len(receipts),
                            failed_actions,
                            diagnostic,
                        )
                    )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    errors: list[str] = []
    expected_count = len(CURATED_TASKS) * len(seeds)
    if len(episodes) != expected_count:
        errors.append(f"expected {expected_count} episodes, got {len(episodes)}")
    if not all(episode.success for episode in episodes):
        failed = [f"{episode.task_id}:seed-{episode.seed}:{episode.diagnostic or episode.raw_reward}" for episode in episodes if not episode.success]
        errors.append("failed official episodes: " + ", ".join(failed))
    families = {episode.family for episode in episodes if episode.success}
    required_families = {task.family for task in CURATED_TASKS}
    if families != required_families:
        errors.append(f"missing successful task families: {sorted(required_families - families)}")
    report = {
        "suite_version": "official-miniwob-curated-v1",
        "diagnostic_solver_version": LEGACY_MINIWOB_DIAGNOSTIC_VERSION,
        "m8_2b_scoring_eligible": False,
        "official_score_claimed": False,
        "repository": MINIWOB_REPOSITORY,
        "commit": MINIWOB_COMMIT,
        "seeds": list(seeds),
        "task_families": sorted(required_families),
        "episodes": [asdict(episode) for episode in episodes],
        "success_rate": sum(episode.success for episode in episodes) / len(episodes),
        "mean_raw_reward": sum(episode.raw_reward for episode in episodes) / len(episodes),
        "mean_official_reward": sum(episode.reward for episode in episodes) / len(episodes),
        "acceptance_errors": errors,
    }
    (output_dir / "miniwob-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    markdown = [
        "# Official MiniWoB++ Curated Report",
        "",
        "- Track: legacy task-specific compatibility diagnostic; not M8.2B score eligible",
        f"- Commit: `{MINIWOB_COMMIT}`",
        f"- Tasks: `{len(CURATED_TASKS)}` across `{', '.join(sorted(required_families))}`",
        f"- Seeds per task: `{len(seeds)}`",
        f"- Episodes: `{len(episodes)}`",
        f"- Raw-reward success rate: `{report['success_rate']:.4f}`",
        f"- Mean raw reward: `{report['mean_raw_reward']:.4f}`",
        f"- Mean official time-adjusted reward: `{report['mean_official_reward']:.4f}`",
        f"- Acceptance: `{'PASS' if not errors else 'FAIL'}`",
        "",
    ]
    (output_dir / "miniwob-report.md").write_text("\n".join(markdown), encoding="utf-8")
    return report


def _solve_task(task_id: str, query: str, session: BrowserSession, receipts: list[dict[str, Any]]) -> None:
    if task_id == "click-button":
        match = re.search(r'Click on the "(.+)" button', query)
        if match is None:
            raise ValueError(f"cannot parse click target: {query}")
        _execute(session, receipts, action="click", label=match.group(1))
        return
    if task_id == "enter-text":
        match = re.search(r'Enter "(.+)" into the text field', query)
        if match is None:
            raise ValueError(f"cannot parse text target: {query}")
        _execute(session, receipts, action="fill", selector="#tt", value=match.group(1))
        _execute(session, receipts, action="click", selector="#subbtn")
        return
    if task_id == "choose-list":
        match = re.search(r"Select (.+) from the list", query)
        if match is None:
            raise ValueError(f"cannot parse list target: {query}")
        _execute(session, receipts, action="select", selector="#options", value=match.group(1))
        _execute(session, receipts, action="click", label="Submit")
        return
    if task_id == "click-dialog":
        _execute(session, receipts, action="click", selector="button.ui-dialog-titlebar-close")
        return
    if task_id == "click-button-sequence":
        _execute(session, receipts, action="click", label="ONE")
        _execute(session, receipts, action="click", label="TWO")
        return
    if task_id == "form-sequence":
        match = re.search(r"Select (-?\d+) with the slider, click the (\d)(?:st|nd|rd|th) checkbox", query)
        if match is None:
            raise ValueError(f"cannot parse form target: {query}")
        target = int(match.group(1))
        checkbox = int(match.group(2))
        _execute(session, receipts, action="press", selector=".ui-slider-handle", key="Home")
        for _ in range(target + 10):
            _execute(session, receipts, action="press", selector=".ui-slider-handle", key="ArrowRight")
        _execute(session, receipts, action="click", selector=f"#checkbox-{checkbox}")
        _execute(session, receipts, action="click", selector="#subbtn")
        return
    raise KeyError(task_id)


def _execute(
    session: BrowserSession,
    receipts: list[dict[str, Any]],
    *,
    action: str,
    selector: str = "",
    label: str = "",
    value: str = "",
    key: str = "",
) -> None:
    snapshot = session.capture()
    affordance = next(
        (
            item
            for item in snapshot.affordance_model.affordances
            if (selector and item.locator.get("selector") == selector) or (label and item.label == label)
        ),
        None,
    )
    parameters = {"value": value} if value else ({"key": key} if key else {})
    if affordance is not None:
        contract = replace(
            ActionContract.from_affordance(
                affordance,
                intent=f"MiniWoB++ {action} {label or selector}",
                backend="dom",
                parameters=parameters,
            ),
            action=action,
            contract_hash="",
        )
    else:
        contract = ActionContract(
            id=f"miniwob-{len(receipts)}-{action}",
            intent=f"MiniWoB++ {action} {label or selector}",
            affordance_id=f"manual-{selector}",
            action=action,
            backend="dom",
            environment_revision=snapshot.observation.environment_revision,
            locator={"selector": selector},
            parameters=parameters,
            snapshot_id=snapshot.observation.snapshot_id,
            page_revision=snapshot.observation.page_revision,
        )
    receipt = DomExecutor(session).execute(contract, snapshot.observation)
    receipts.append(asdict(receipt))
    if not receipt.success:
        raise RuntimeError(receipt.message)


def _quiet_handler(root: Path) -> type[SimpleHTTPRequestHandler]:
    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    return QuietHandler


def _git(cwd: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip() if capture else ""
