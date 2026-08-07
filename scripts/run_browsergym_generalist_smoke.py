#!/usr/bin/env python3
"""Run one official MiniWoB task through the GeneralistLMPlanner boundary."""

from __future__ import annotations

import argparse
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from affordance_runtime.benchmarks.browsergym import run_browsergym_generalist_episode_isolated
from affordance_runtime.model_port import model_port_from_environment


def run(
    task_id: str,
    seed: int,
    miniwob_root: Path,
    artifact_root: Path,
    *,
    episode_timeout_s: float = 165.0,
    model_call_timeout_s: float = 10.0,
    max_model_calls: int = 15,
) -> dict[str, Any]:
    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("BrowserGym is not installed; use the browsergym isolated environment") from exc

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(miniwob_root), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}/miniwob/"
        result = run_browsergym_generalist_episode_isolated(
            model_port_from_environment(),
            task_id=task_id,
            seed=seed,
            base_url=base_url,
            headless=True,
            artifact_root=artifact_root,
            timeout_s=episode_timeout_s,
            model_timeout_s=model_call_timeout_s,
            max_model_calls=max_model_calls,
        )
        return result.__dict__
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="click-button")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--miniwob-root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--episode-timeout-s", type=float, default=165.0)
    parser.add_argument("--model-call-timeout-s", type=float, default=10.0)
    parser.add_argument("--max-model-calls", type=int, default=15)
    args = parser.parse_args()
    value = run(
        args.task,
        args.seed,
        args.miniwob_root,
        args.artifacts,
        episode_timeout_s=args.episode_timeout_s,
        model_call_timeout_s=args.model_call_timeout_s,
        max_model_calls=args.max_model_calls,
    )
    rendered = json.dumps(value, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if value["runtime_status"] == "done" and value["official_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
