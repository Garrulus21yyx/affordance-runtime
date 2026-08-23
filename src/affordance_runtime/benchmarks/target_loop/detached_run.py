"""PTY-independent lifecycle and status for long target-loop benchmark runs."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

DETACHED_RUN_SCHEMA_VERSION = "target-loop-detached-run.v1"


@dataclass(frozen=True)
class DetachedRunIdentity:
    schema_version: str
    pid: int
    session_id: int
    process_start_ticks: int | None
    started_at_utc: str
    output_dir: str
    log_path: str
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != DETACHED_RUN_SCHEMA_VERSION:
            raise ValueError("detached benchmark launch schema is unsupported")
        if type(self.pid) is not int or self.pid <= 0 or type(self.session_id) is not int or self.session_id <= 0:
            raise ValueError("detached benchmark process identity is invalid")
        if self.session_id != self.pid:
            raise ValueError("detached benchmark must be a session leader")
        if self.process_start_ticks is not None and (
            type(self.process_start_ticks) is not int or self.process_start_ticks <= 0
        ):
            raise ValueError("detached benchmark process start identity is invalid")
        if any(not isinstance(value, str) or not value for value in (self.started_at_utc, self.output_dir, self.log_path)):
            raise ValueError("detached benchmark paths and start time are required")
        if (
            not isinstance(self.command, tuple)
            or not self.command
            or len(self.command) > 128
            or any(not isinstance(item, str) or not item or len(item) > 4096 for item in self.command)
        ):
            raise ValueError("detached benchmark command identity is invalid")


def launch_detached(
    command: Sequence[str],
    output_dir: str | Path,
    *,
    cwd: str | Path | None = None,
    environment: dict[str, str] | None = None,
) -> DetachedRunIdentity:
    """Start one new-session process and durably record its real process identity."""
    normalized = tuple(command)
    if not normalized or any(not isinstance(item, str) or not item for item in normalized):
        raise ValueError("detached command must contain bounded nonblank arguments")
    root = Path(output_dir).resolve()
    _require_new_run_directory(root)
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / "benchmark.log"
    log = log_path.open("ab", buffering=0)
    process = None
    try:
        process = subprocess.Popen(
            normalized,
            cwd=Path(cwd).resolve() if cwd is not None else Path.cwd(),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        session_id = os.getsid(process.pid)
        if session_id != process.pid:
            raise RuntimeError("detached benchmark did not become a session leader")
        identity = DetachedRunIdentity(
            DETACHED_RUN_SCHEMA_VERSION,
            process.pid,
            session_id,
            _process_start_ticks(process.pid),
            datetime.now(UTC).isoformat(),
            str(root),
            str(log_path),
            normalized,
        )
        _atomic_write(root / "run.pid", f"{identity.pid}\n")
        _atomic_write(
            root / "launch.json",
            json.dumps(asdict(identity), indent=2, sort_keys=True) + "\n",
        )
        return identity
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        raise
    finally:
        log.close()


def detached_status(output_dir: str | Path) -> dict[str, object]:
    """Read process identity and durable evidence without owning benchmark state."""
    root = Path(output_dir).resolve()
    identity = _read_identity(root / "launch.json")
    running = _same_process(identity.pid, identity.process_start_ticks, identity.command)
    run_report = root / "run.json"
    summary = root / "summary.json"
    case_reports = tuple(sorted((root / "cases").glob("*.json"))) if (root / "cases").is_dir() else ()
    traces = tuple(sorted((root / "traces").glob("**/trace.jsonl"))) if (root / "traces").is_dir() else ()
    durable = _durable_status(root / "run-results.sqlite3")
    if running:
        state = "running"
    elif durable == "run_final":
        state = "completed_reported"
    elif durable in {"suite_report_failed", "suite_export_failed"}:
        state = "stopped_with_suite_report_failure"
    elif durable == "case_complete":
        state = "stopped_with_complete_cases"
    elif durable in {"partial_run", "case_final", "durable_prefix"}:
        state = "stopped_with_partial_cases"
    elif durable == "absent" and run_report.is_file() and summary.is_file():
        # Compatibility for evidence produced before SQLite became the
        # primary finalization authority. Existing SQLite always wins.
        state = "completed_reported"
    else:
        state = "stopped_without_report"
    return {
        "schema_version": DETACHED_RUN_SCHEMA_VERSION,
        "state": state,
        "pid": identity.pid,
        "session_id": identity.session_id,
        "process_identity_matches": running,
        "started_at_utc": identity.started_at_utc,
        "output_dir": identity.output_dir,
        "log_path": identity.log_path,
        "run_report": str(run_report) if run_report.is_file() else "",
        "summary_report": str(summary) if summary.is_file() else "",
        "case_reports": tuple(str(item) for item in case_reports),
        "traces": tuple(
            {
                "path": str(item),
                "size_bytes": item.stat().st_size,
                "modified_ns": item.stat().st_mtime_ns,
            }
            for item in traces
        ),
        "durable_status": durable,
    }


def _durable_status(location: Path) -> str:
    if not location.is_file():
        return "absent"
    try:
        with sqlite3.connect(location) as connection:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            run_count = (
                connection.execute("SELECT COUNT(*) FROM run_reports").fetchone()[0]
                if "run_reports" in tables
                else 0
            )
            revisions = tuple(
                int(row[0])
                for row in connection.execute("SELECT revision FROM case_outcomes")
            ) if "case_outcomes" in tables else ()
            suite = (
                connection.execute(
                    """
                    SELECT expected_case_count, report_disposition, export_disposition
                    FROM run_finalization LIMIT 1
                    """
                ).fetchone()
                if "run_finalization" in tables
                else None
            )
    except (sqlite3.Error, TypeError, ValueError):
        return "invalid"
    if suite is not None:
        expected_case_count, report_disposition, export_disposition = suite
        if report_disposition == "failed":
            return "suite_report_failed"
        if export_disposition == "failed":
            return "suite_export_failed"
        if report_disposition == "committed" and export_disposition == "exported" and run_count:
            return "run_final"
        final_count = sum(item == 3 for item in revisions)
        if final_count == int(expected_case_count) and len(revisions) == int(expected_case_count):
            return "case_complete"
        if revisions or int(expected_case_count) > 0:
            return "partial_run"
    if run_count:
        return "run_final"
    if revisions and all(item == 3 for item in revisions):
        return "case_final"
    if revisions:
        return "durable_prefix"
    return "empty"


def _require_new_run_directory(root: Path) -> None:
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("detached benchmark output directory already contains run evidence")


def _read_identity(path: Path) -> DetachedRunIdentity:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("detached benchmark launch identity is unavailable") from exc
    expected = set(DetachedRunIdentity.__dataclass_fields__)
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("detached benchmark launch identity is malformed")
    if payload.get("schema_version") != DETACHED_RUN_SCHEMA_VERSION:
        raise ValueError("detached benchmark launch schema is unsupported")
    command = payload.get("command")
    if not isinstance(command, list) or any(not isinstance(item, str) for item in command):
        raise ValueError("detached benchmark command identity is malformed")
    payload["command"] = tuple(command)
    try:
        return DetachedRunIdentity(**payload)
    except TypeError as exc:
        raise ValueError("detached benchmark launch identity is malformed") from exc


def _same_process(
    pid: int,
    expected_start_ticks: int | None,
    expected_command: tuple[str, ...],
) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    observed, state = _process_stat(pid)
    if state == "Z":
        return False
    if expected_start_ticks is not None:
        return observed == expected_start_ticks
    try:
        os.kill(pid, 0)
        command = tuple(
            item.decode("utf-8")
            for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if item
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return command == expected_command


def _process_start_ticks(pid: int) -> int | None:
    return _process_stat(pid)[0]


def _process_stat(pid: int) -> tuple[int | None, str]:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields_after_name = raw[raw.rfind(")") + 2 :].split()
        return int(fields_after_name[19]), fields_after_name[0]
    except (OSError, ValueError, IndexError):
        return None, ""


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
