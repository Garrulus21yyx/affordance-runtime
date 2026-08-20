"""Loopback-only launcher and trace reader for formal MiniWoB case runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from affordance_runtime.benchmarks.external_breadth.manifest import CAMPAIGN_ID, build_breadth_manifest
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.wire_capability import ActionPolicyWireCapability

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_PROFILE_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
_STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
_DEFAULT_ACTION_MODELS = ("glm-4.6", "glm-4.1v-thinking-flashx")
_DEFAULT_GOAL_MODELS = ("glm-4.7-flash", "glm-4.6")


@dataclass(frozen=True)
class ConsoleRunSpec:
    case_id: str
    action_model: str
    goal_compiler_mode: str
    goal_compiler_model: str = ""
    perception_profile: str = DecisionPerceptionProfile.STRUCTURE_FIRST.value
    profile: str = "CONSOLE_RUN"
    action_wire_capability: str = ActionPolicyWireCapability.NATIVE_SINGLE_TOOL.value

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if _MODEL_ID.fullmatch(self.action_model) is None:
            raise ValueError("action_model is invalid")
        if self.goal_compiler_mode not in {"model", "disabled"}:
            raise ValueError("goal_compiler_mode must be model or disabled")
        if self.goal_compiler_mode == "model" and _MODEL_ID.fullmatch(self.goal_compiler_model) is None:
            raise ValueError("goal_compiler_model is invalid")
        if self.goal_compiler_mode == "disabled" and self.goal_compiler_model:
            raise ValueError("disabled GoalCompiler cannot select a model")
        DecisionPerceptionProfile(self.perception_profile)
        ActionPolicyWireCapability(self.action_wire_capability)
        if _PROFILE_ID.fullmatch(self.profile) is None:
            raise ValueError("profile must be an uppercase bounded identifier")


@dataclass
class ConsoleRun:
    run_id: str
    spec: ConsoleRunSpec
    evidence_dir: Path
    command: tuple[str, ...]
    started_at: str
    process: subprocess.Popen[str] = field(repr=False, compare=False)
    output: list[str] = field(default_factory=list, repr=False, compare=False)

    @property
    def status(self) -> str:
        code = self.process.poll()
        if code is None:
            return "running"
        return "completed" if code == 0 else "failed"

    def public_payload(self) -> dict[str, object]:
        report_path = self.evidence_dir / "report.json"
        report = _read_json(report_path) if report_path.is_file() else None
        return {
            "run_id": self.run_id,
            "status": self.status,
            "return_code": self.process.poll(),
            "started_at": self.started_at,
            "spec": asdict(self.spec),
            "evidence_dir": str(self.evidence_dir),
            "stdout_tail": self.output[-40:],
            "report": report,
        }


class ConsoleRunManager:
    """Own one local formal-run subprocess; never owns Runtime state."""

    def __init__(
        self,
        evidence_root: Path,
        *,
        python_executable: str = sys.executable,
        environment: dict[str, str] | None = None,
        manifest=None,
    ) -> None:
        self.evidence_root = Path(evidence_root).resolve()
        self.python_executable = python_executable
        self.environment = dict(os.environ if environment is None else environment)
        self.manifest = manifest or build_breadth_manifest(load_registry_census())
        self._cases = {case.case_id: case for case in self.manifest.cases}
        self._runs: dict[str, ConsoleRun] = {}
        self._active_id = ""
        self._lock = threading.Lock()

    def configuration(self) -> dict[str, object]:
        action_models = _model_choices(
            _DEFAULT_ACTION_MODELS,
            self.environment.get("LLM_ZHIPU_MODEL", ""),
        )
        goal_models = _model_choices(
            _DEFAULT_GOAL_MODELS,
            self.environment.get("LLM_GOAL_COMPILER_MODEL", ""),
        )
        return {
            "manifest": self.manifest.campaign_id,
            "provider": "zhipu",
            "provider_ready": all(
                self.environment.get(name, "").strip()
                for name in ("LLM_ZHIPU_BASE_URL", "LLM_ZHIPU_API_KEY")
            ),
            "action_models": [
                {
                    "id": model,
                    "multimodal": model.casefold() == "glm-4.1v-thinking-flashx",
                }
                for model in action_models
            ],
            "action_wire_capabilities": [item.value for item in ActionPolicyWireCapability],
            "goal_models": goal_models,
            "perception_profiles": [item.value for item in DecisionPerceptionProfile],
            "cases": [
                {
                    "case_id": case.case_id,
                    "task_id": case.task_id.removeprefix("browsergym/miniwob."),
                    "seed": case.seed,
                    "max_turns": case.max_turns,
                    "timeout_s": case.timeout_s,
                }
                for case in self.manifest.cases
            ],
        }

    def start(self, spec: ConsoleRunSpec) -> ConsoleRun:
        case = self._cases.get(spec.case_id)
        if case is None:
            raise ValueError("case_id is not in the frozen manifest")
        with self._lock:
            active = self._runs.get(self._active_id)
            if active is not None and active.process.poll() is None:
                raise RuntimeError("another console run is active")
            run_id = _run_id(spec.case_id)
            evidence_dir = self.evidence_root / run_id
            command = (
                self.python_executable,
                "-m",
                "affordance_runtime.benchmarks.external_breadth.cli",
                "run-case",
                "--manifest",
                CAMPAIGN_ID,
                "--case-id",
                spec.case_id,
                "--profile",
                spec.profile,
                "--seed",
                str(case.seed),
                "--output-dir",
                str(evidence_dir),
            )
            env = self._run_environment(spec)
            process = subprocess.Popen(
                command,
                cwd=Path.cwd(),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            run = ConsoleRun(
                run_id,
                spec,
                evidence_dir,
                command,
                datetime.now(UTC).isoformat(),
                process,
            )
            self._runs[run_id] = run
            self._active_id = run_id
            threading.Thread(target=self._drain_output, args=(run,), daemon=True).start()
            return run

    def get(self, run_id: str) -> ConsoleRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError("console run not found") from exc

    def current(self) -> ConsoleRun | None:
        return self._runs.get(self._active_id)

    def events(self, run_id: str, after: int = 0) -> dict[str, object]:
        if after < 0:
            raise ValueError("event cursor must be nonnegative")
        run = self.get(run_id)
        trace_path = run.evidence_dir / "traces" / run.spec.case_id / "trace.jsonl"
        events: list[dict[str, object]] = []
        next_cursor = after
        if trace_path.is_file():
            for index, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), start=1):
                if index <= after:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    break
                events.append(event)
                next_cursor = index
        return {"events": events, "next_cursor": next_cursor, "run": run.public_payload()}

    def stop(self, run_id: str) -> ConsoleRun:
        run = self.get(run_id)
        if run.process.poll() is None:
            run.process.terminate()
        return run

    def _run_environment(self, spec: ConsoleRunSpec) -> dict[str, str]:
        env = dict(self.environment)
        env.update(
            {
                "LLM_ACTIVE_PROFILE": "zhipu",
                "LLM_ZHIPU_MODEL": spec.action_model,
                "LLM_ACTION_POLICY_WIRE_CAPABILITY": spec.action_wire_capability,
                "LLM_DECISION_PERCEPTION": spec.perception_profile,
                "LLM_GOAL_COMPILER_MODE": spec.goal_compiler_mode,
                "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
                "MINIWOB_URL": env.get("MINIWOB_URL", "http://127.0.0.1:18888/miniwob/"),
            }
        )
        if spec.goal_compiler_mode == "model":
            env["LLM_GOAL_COMPILER_MODEL"] = spec.goal_compiler_model
        else:
            env.pop("LLM_GOAL_COMPILER_MODEL", None)
        return env

    @staticmethod
    def _drain_output(run: ConsoleRun) -> None:
        assert run.process.stdout is not None
        for line in run.process.stdout:
            run.output.append(line.rstrip())
            if len(run.output) > 200:
                del run.output[:50]


class ConsoleRequestHandler(BaseHTTPRequestHandler):
    manager: ClassVar[ConsoleRunManager]
    static_root: ClassVar[Path]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self._json(HTTPStatus.OK, self.manager.configuration())
            return
        if parsed.path == "/api/runs/current":
            run = self.manager.current()
            self._json(HTTPStatus.OK, run.public_payload() if run else None)
            return
        match = re.fullmatch(r"/api/runs/([^/]+)", parsed.path)
        if match:
            self._run_payload(match.group(1))
            return
        match = re.fullmatch(r"/api/runs/([^/]+)/events", parsed.path)
        if match:
            try:
                after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                self._json(HTTPStatus.OK, self.manager.events(match.group(1), after))
            except (KeyError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/runs":
            try:
                payload = self._request_json()
                spec = ConsoleRunSpec(**payload)
                run = self.manager.start(spec)
                self._json(HTTPStatus.CREATED, run.public_payload())
            except (TypeError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except RuntimeError as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/runs/([^/]+)/stop", self.path)
        if match:
            try:
                self._json(HTTPStatus.OK, self.manager.stop(match.group(1)).public_payload())
            except KeyError as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        return None

    def _run_payload(self, run_id: str) -> None:
        try:
            self._json(HTTPStatus.OK, self.manager.get(run_id).public_payload())
        except KeyError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

    def _request_json(self) -> dict[str, object]:
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 32 * 1024:
            raise ValueError("request body size is invalid")
        payload = json.loads(self.rfile.read(size))
        if not isinstance(payload, dict):
            raise TypeError("request body must be a JSON object")
        return payload

    def _json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str) -> None:
        name = "index.html" if path in {"", "/"} else path.removeprefix("/")
        if name not in {"index.html", "styles.css", "app.js"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        body = (self.static_root / name).read_bytes()
        media_type = _STATIC_TYPES.get(Path(name).suffix, "text/html; charset=utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", media_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(
    host: str,
    port: int,
    manager: ConsoleRunManager,
) -> ThreadingHTTPServer:
    handler = type(
        "BoundConsoleRequestHandler",
        (ConsoleRequestHandler,),
        {
            "manager": manager,
            "static_root": Path(str(files("affordance_runtime.benchmarks.console.static"))),
        },
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(prog="affordance-runtime-console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--evidence-root", type=Path, default=Path("evidence/live"))
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        raise SystemExit("non-loopback binding requires --allow-remote")
    manager = ConsoleRunManager(args.evidence_root)
    server = build_server(args.host, args.port, manager)
    print(f"Affordance Runtime Console: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _model_choices(defaults: tuple[str, ...], configured: str) -> list[str]:
    values = [*defaults]
    if configured.strip() and _MODEL_ID.fullmatch(configured.strip()) and configured.strip() not in values:
        values.append(configured.strip())
    return values


def _run_id(case_id: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"console-{timestamp}-{case_id}-{uuid.uuid4().hex[:6]}"


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    main()
