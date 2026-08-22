"""Thin SQLite durability adapter for terminal benchmark results."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from affordance_runtime.benchmarks.target_loop.outcome_checkpoint import (
    OfficialOutcomeCheckpoint,
)


class RunResultStoreError(RuntimeError):
    """Typed adapter failure; the runner maps its meaning into harness facts."""


class CaseLifecyclePhase(StrEnum):
    CASE_STARTED = "CASE_STARTED"
    ENVIRONMENT_READY = "ENVIRONMENT_READY"
    PLANNER_STARTED = "PLANNER_STARTED"
    PLANNER_RETURNED = "PLANNER_RETURNED"
    CASE_BODY_RETURNED = "CASE_BODY_RETURNED"
    RESULT_PERSISTED = "RESULT_PERSISTED"
    CLEANUP_STARTED = "CLEANUP_STARTED"
    CLEANUP_FINISHED = "CLEANUP_FINISHED"
    CASE_FINISHED = "CASE_FINISHED"


class RunResultStore(Protocol):
    @property
    def location(self) -> Path: ...

    def commit_official_outcome(self, checkpoint: OfficialOutcomeCheckpoint) -> None: ...


@dataclass(frozen=True)
class SQLiteRunResultStore:
    location: Path

    def __post_init__(self) -> None:
        path = Path(self.location)
        path.parent.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "location", path)
        try:
            with self._connect() as connection:
                connection.executescript(_SCHEMA)
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(case_lifecycle)")}
                if "current_phase" not in columns:
                    connection.execute("ALTER TABLE case_lifecycle ADD COLUMN current_phase TEXT NOT NULL DEFAULT ''")
        except sqlite3.Error as exc:
            raise RunResultStoreError("result store initialization failed") from exc

    def commit_official_outcome(self, checkpoint: OfficialOutcomeCheckpoint) -> None:
        payload = (
            checkpoint.case_id,
            checkpoint.schema_version,
            checkpoint.checkpoint_id,
            checkpoint.task_id,
            checkpoint.observation_id,
            checkpoint.evaluation_status.value,
            checkpoint.run_status.value,
            checkpoint.outcome_kind.value if checkpoint.outcome_kind is not None else "",
            checkpoint.outcome_code,
            json.dumps(checkpoint.evidence_refs),
        )
        try:
            with self._connect() as connection:
                existing = connection.execute(
                    """
                    SELECT schema_version, checkpoint_id, task_id, observation_id, evaluation_status,
                           run_status, outcome_kind, outcome_code, evidence_refs_json
                    FROM official_outcomes WHERE case_id = ?
                    """,
                    (checkpoint.case_id,),
                ).fetchone()
                if existing is not None and tuple(existing) != payload[1:]:
                    raise RunResultStoreError("conflicting official outcome checkpoint")
                if existing is None:
                    connection.execute(
                        """
                    INSERT INTO official_outcomes (
                        case_id, schema_version, checkpoint_id, task_id, observation_id,
                        evaluation_status, run_status, outcome_kind, outcome_code,
                        evidence_refs_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        payload,
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO case_lifecycle (case_id) VALUES (?)",
                    (checkpoint.case_id,),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("official outcome commit failed") from exc

    def record_cleanup(
        self,
        case_id: str,
        status: str,
        failure_code: str = "",
        exception_class: str = "",
    ) -> None:
        if status not in {"not_run", "succeeded", "already_closed", "timeout", "failed"}:
            raise ValueError("cleanup status is outside the closed vocabulary")
        if (status in {"timeout", "failed"}) != bool(failure_code and exception_class):
            raise ValueError("cleanup status and failure details are inconsistent")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO case_lifecycle (
                        case_id, cleanup_status, cleanup_failure_code,
                        cleanup_exception_class
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET
                        cleanup_status=excluded.cleanup_status,
                        cleanup_failure_code=excluded.cleanup_failure_code,
                        cleanup_exception_class=excluded.cleanup_exception_class
                    """,
                    (case_id, status, failure_code, exception_class),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("cleanup outcome commit failed") from exc

    def record_case_phase(self, case_id: str, phase: CaseLifecyclePhase) -> None:
        phase = CaseLifecyclePhase(phase)
        try:
            with self._connect() as connection:
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM case_phase_events WHERE case_id = ?",
                    (case_id,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO case_phase_events (case_id, sequence, phase) VALUES (?, ?, ?)",
                    (case_id, sequence, phase.value),
                )
                connection.execute(
                    """
                    INSERT INTO case_lifecycle (case_id, current_phase) VALUES (?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET current_phase=excluded.current_phase
                    """,
                    (case_id, phase.value),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("case lifecycle phase commit failed") from exc

    def load_case_phases(self, case_id: str) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT phase FROM case_phase_events WHERE case_id = ? ORDER BY sequence",
                (case_id,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def commit_case_report(self, result: object) -> None:
        case_id = str(getattr(result, "case_id"))
        payload = json.dumps(asdict(result), sort_keys=True)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO case_reports (case_id, payload_json) VALUES (?, ?)",
                    (case_id, payload),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("case report commit failed") from exc

    def commit_run_report(self, result: object) -> None:
        run_id = str(getattr(getattr(result, "identity"), "run_id"))
        payload = json.dumps(asdict(result), sort_keys=True)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO run_reports (run_id, payload_json) VALUES (?, ?)",
                    (run_id, payload),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("run report commit failed") from exc

    def export_run_report(self, run_id: str, output_dir: Path) -> tuple[Path, Path]:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM run_reports WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
            if row is None:
                raise RunResultStoreError("run report is not committed")
            payload = json.loads(row[0])
            root = Path(output_dir)
            root.mkdir(parents=True, exist_ok=True)
            run_path = root / "run.json"
            summary_path = root / "summary.json"
            _write_json_projection(run_path, payload)
            _write_json_projection(
                summary_path,
                {
                    "identity": payload["identity"],
                    "acceptance": payload["acceptance"],
                    "rates": payload["rates"],
                },
            )
            return run_path, summary_path
        except OSError as exc:
            raise RunResultStoreError("run report export failed") from exc

    def export_case_report(self, case_id: str, output_dir: Path) -> Path:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM case_reports WHERE case_id = ?",
                    (case_id,),
                ).fetchone()
            if row is None:
                raise RunResultStoreError("case report is not committed")
            cases = Path(output_dir) / "cases"
            cases.mkdir(parents=True, exist_ok=True)
            path = cases / f"{case_id}.json"
            _write_json_projection(path, json.loads(row[0]))
            self.record_report_status(case_id, "exported")
            return path
        except OSError as exc:
            self.record_report_status(case_id, "failed", "json_export_failed")
            raise RunResultStoreError("case report export failed") from exc

    def record_report_status(
        self,
        case_id: str,
        status: str,
        failure_code: str = "",
    ) -> None:
        if status not in {"not_generated", "exported", "failed"}:
            raise ValueError("report status is outside the closed vocabulary")
        if (status == "failed") != bool(failure_code):
            raise ValueError("report status and failure code are inconsistent")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO case_lifecycle (case_id, report_status, report_failure_code)
                    VALUES (?, ?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET
                        report_status=excluded.report_status,
                        report_failure_code=excluded.report_failure_code
                    """,
                    (case_id, status, failure_code),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("report status commit failed") from exc

    def load_lifecycle(self, case_id: str) -> dict[str, str]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT current_phase, cleanup_status, cleanup_failure_code, cleanup_exception_class,
                       report_status, report_failure_code
                FROM case_lifecycle WHERE case_id = ?
                """,
                (case_id,),
            ).fetchone()
        if row is None:
            return {}
        names = (
            "current_phase",
            "cleanup_status",
            "cleanup_failure_code",
            "cleanup_exception_class",
            "report_status",
            "report_failure_code",
        )
        return dict(zip(names, row, strict=True))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.location)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _write_json_projection(path: Path, payload: object) -> None:
    """Replace a rebuildable JSON projection without claiming durability."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS official_outcomes (
    case_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    evaluation_status TEXT NOT NULL,
    run_status TEXT NOT NULL,
    outcome_kind TEXT NOT NULL,
    outcome_code TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_lifecycle (
    case_id TEXT PRIMARY KEY,
    current_phase TEXT NOT NULL DEFAULT '',
    cleanup_status TEXT NOT NULL DEFAULT 'not_run',
    cleanup_failure_code TEXT NOT NULL DEFAULT '',
    cleanup_exception_class TEXT NOT NULL DEFAULT '',
    report_status TEXT NOT NULL DEFAULT 'not_generated',
    report_failure_code TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS case_phase_events (
    case_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    phase TEXT NOT NULL,
    PRIMARY KEY (case_id, sequence)
);
CREATE TABLE IF NOT EXISTS case_reports (
    case_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_reports (
    run_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
"""
