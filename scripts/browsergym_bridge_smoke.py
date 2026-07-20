#!/usr/bin/env python3
"""Real BrowserGym bridge smoke; this is adapter evidence, not an official score."""

from __future__ import annotations

import argparse
import json
import re
import threading
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
import gymnasium as gym  # type: ignore[import-not-found]

from affordance_runtime.benchmarks.browsergym import (
    BROWSERGYM_MINIWOB_COMMIT,
    BROWSERGYM_VERSION,
    BrowserGymAction,
    BrowserGymPolicyRequest,
    ensure_browsergym_miniwob,
    registered_miniwob_tasks,
    run_browsergym_episode,
)


class ExactQuotedLabelPolicy:
    """Generic one-step policy used only to exercise the bridge."""

    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        quoted = re.findall(r'"([^"]+)"', request.goal)
        for value in quoted:
            for affordance in request.affordances:
                if affordance["label"] == value:
                    selector = str(affordance["locator"].get("selector") or "")
                    if selector.startswith("[bid='") and selector.endswith("']"):
                        return BrowserGymAction("click", {"bid": selector[6:-2]})
        raise RuntimeError(f"no exact quoted affordance label in goal: {request.goal}")

    def close(self) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    html_root = ensure_browsergym_miniwob(args.output / "source")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *values: Any, **kwargs: Any) -> None:
            super().__init__(*values, directory=str(html_root), **kwargs)

        def log_message(self, format: str, *values: Any) -> None:
            del format, values

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = gym.make(
            "browsergym/miniwob.click-button",
            task_kwargs={"base_url": f"http://127.0.0.1:{server.server_port}/miniwob/"},
            headless=True,
        )
        result = run_browsergym_episode(
            environment,
            ExactQuotedLabelPolicy(),
            task_id="click-button",
            seed=0,
            artifact_root=args.output / "artifacts",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    report = {
        "schema_version": "browsergym-bridge-smoke-v1",
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
        "registered_task_count": len(registered_miniwob_tasks()),
        "scored_benchmark": False,
        "result": asdict(result),
        "acceptance": "passed" if result.official_success and result.runtime_status == "done" else "failed",
    }
    (args.output / "browsergym-bridge-smoke.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["acceptance"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
