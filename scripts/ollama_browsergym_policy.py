#!/usr/bin/env python3
"""Generic Ollama policy for the BrowserGym JSON-lines planner boundary."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

ACTION_SCHEMA = {
    "noop": [],
    "click": ["bid"],
    "dblclick": ["bid"],
    "fill": ["bid", "value"],
    "select_option": ["bid", "options"],
    "hover": ["bid"],
    "press": ["bid", "key_comb"],
    "focus": ["bid"],
    "clear": ["bid"],
    "drag_and_drop": ["from_bid", "to_bid"],
    "scroll": ["delta_x", "delta_y"],
    "keyboard_press": ["key"],
    "keyboard_type": ["text"],
}

SYSTEM_PROMPT = """You are a generic browser action planner. Choose exactly one next action that advances the supplied goal.
Return only a JSON object with keys name and arguments. Use only the action names and required arguments in action_schema.
For element actions, copy bid values exactly from an affordance locator. Do not invent elements or use CSS selectors, JavaScript, task-specific rules, or explanations.
Use the accessibility tree for semantic relationships and current values. Use select_option on a select/combobox, click on buttons and checkboxes, fill on textboxes, and press with a single string key_comb such as ArrowRight.
Use prior actions to continue multi-step work without repeating completed steps. Prefer semantic labels and roles. If no safe useful action exists, return {\"done\": true}."""


def _request_payload(request: dict[str, Any]) -> dict[str, Any]:
    affordances = []
    for item in request.get("affordances", []):
        locator = item.get("locator") if isinstance(item, dict) else {}
        bid = locator.get("bid") if isinstance(locator, dict) else None
        if not bid and isinstance(locator, dict):
            selector = str(locator.get("selector") or "")
            if selector.startswith("[bid='") and selector.endswith("']"):
                bid = selector[6:-2]
        affordances.append(
            {
                "bid": bid,
                "role": item.get("role"),
                "label": item.get("label"),
                "action": item.get("action"),
            }
        )
    return {
        "goal": request.get("goal", ""),
        "step": request.get("step", 0),
        "affordances": affordances,
        "previous_actions": request.get("previous_actions", []),
        "accessibility_tree": str(request.get("accessibility_tree") or "")[:16000],
        "action_schema": ACTION_SCHEMA,
    }


def propose(request: dict[str, Any], *, url: str, model: str, timeout: float) -> dict[str, Any]:
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(_request_payload(request), sort_keys=True)},
        ],
        "options": {"temperature": 0},
    }
    http_request = urllib.request.Request(
        f"{url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=timeout) as response:  # noqa: S310 - explicit local/provider URL
        result = json.loads(response.read())
    content = json.loads(result["message"]["content"])
    if content.get("done"):
        return {"done": True}
    name = str(content.get("name") or "")
    arguments = content.get("arguments")
    if name not in ACTION_SCHEMA:
        raise ValueError("model returned an invalid typed action")
    if isinstance(arguments, list):
        arguments = dict(zip(ACTION_SCHEMA[name], arguments, strict=False))
    if not isinstance(arguments, dict):
        raise ValueError("model returned invalid action arguments")
    required = set(ACTION_SCHEMA[name])
    if not required <= set(arguments):
        raise ValueError(f"model omitted required arguments for {name}")
    return {"name": name, "arguments": arguments}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = propose(request, url=args.url, model=args.model, timeout=args.timeout)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            print(f"planner error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            response = {"done": True}
        print(json.dumps(response, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
