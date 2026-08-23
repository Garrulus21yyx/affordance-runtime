"""Thin SQLite durability adapter for terminal benchmark results."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from enum import IntEnum, StrEnum
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
    CASE_BODY_RETURNED = "CASE_BODY_RETURNED"
    RESULT_PERSISTED = "RESULT_PERSISTED"
    CLEANUP_STARTED = "CLEANUP_STARTED"
    CLEANUP_FINISHED = "CLEANUP_FINISHED"
    FINAL_ATTEMPT = "FINAL_ATTEMPT"
    CASE_FINISHED = "CASE_FINISHED"


class CaseRecordRevision(IntEnum):
    BODY = 1
    CLEANUP = 2
    FINAL = 3


class CleanupDisposition(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    NOT_ACQUIRED = "not_acquired"
    NOT_APPLICABLE = "not_applicable"
    SUCCEEDED = "succeeded"
    ALREADY_CLOSED = "already_closed"
    TIMEOUT = "timeout"
    FAILED = "failed"


class ReportDisposition(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    COMMITTED = "committed"
    FAILED = "failed"


class ProjectionDisposition(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    PROJECTED = "projected"
    FAILED = "failed"


class ExportDisposition(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    EXPORTED = "exported"
    FAILED = "failed"


class FinalCommitDisposition(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    COMMITTED = "committed"
    FAILED = "failed"


@dataclass(frozen=True)
class SuiteReportDisposition:
    run_id: str
    expected_case_count: int
    report_disposition: ReportDisposition
    export_disposition: ExportDisposition
    failure_code: str = ""

    def __post_init__(self) -> None:
        if not self.run_id.strip() or self.expected_case_count < 0:
            raise ValueError("suite report disposition requires bounded run identity")
        failed = (
            self.report_disposition is ReportDisposition.FAILED
            or self.export_disposition is ExportDisposition.FAILED
        )
        if failed != bool(self.failure_code):
            raise ValueError("suite report failure code and dispositions diverge")


@dataclass(frozen=True)
class CaseOutcomeRecord:
    """Small monotonic durable owner record; official truth remains joined by digest."""

    case_id: str
    revision: CaseRecordRevision
    behavior_status: str
    failure_code: str = ""
    official_checkpoint_id: str = ""
    official_checkpoint_digest: str = ""
    cleanup_disposition: CleanupDisposition = CleanupDisposition.NOT_ATTEMPTED
    projection_disposition: ProjectionDisposition = ProjectionDisposition.NOT_ATTEMPTED
    report_disposition: ReportDisposition = ReportDisposition.NOT_ATTEMPTED
    export_disposition: ExportDisposition = ExportDisposition.NOT_ATTEMPTED
    finished: bool = False

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.behavior_status.strip():
            raise ValueError("case outcome record requires identity and behavior status")
        if not isinstance(self.revision, CaseRecordRevision):
            raise TypeError("case outcome revision must be typed")
        if bool(self.official_checkpoint_id) != bool(self.official_checkpoint_digest):
            raise ValueError("official checkpoint join requires id and digest together")
        if self.official_checkpoint_id and self.official_checkpoint_id != (
            "checkpoint:" + self.official_checkpoint_digest
        ):
            raise ValueError("official checkpoint id/digest diverge")
        if self.revision is CaseRecordRevision.BODY and (
            self.cleanup_disposition is not CleanupDisposition.NOT_ATTEMPTED
            or self.projection_disposition is not ProjectionDisposition.NOT_ATTEMPTED
            or self.report_disposition is not ReportDisposition.NOT_ATTEMPTED
            or self.export_disposition is not ExportDisposition.NOT_ATTEMPTED
            or self.finished
        ):
            raise ValueError("BODY cannot claim cleanup, reporting, or finish")
        if self.revision is CaseRecordRevision.CLEANUP and self.finished:
            raise ValueError("CLEANUP cannot claim case finish")
        if self.revision is not CaseRecordRevision.BODY and (
            self.cleanup_disposition is CleanupDisposition.NOT_ATTEMPTED
        ):
            raise ValueError("post-BODY outcome requires a cleanup disposition")
        if self.finished != (self.revision is CaseRecordRevision.FINAL):
            raise ValueError("only FINAL is a finished case")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["revision"] = int(self.revision)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class RunResultStore(Protocol):
    @property
    def location(self) -> Path: ...

    def commit_official_outcome(self, checkpoint: OfficialOutcomeCheckpoint) -> None: ...

    def commit_case_outcome(self, record: CaseOutcomeRecord) -> None: ...


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

    def commit_case_outcome(self, record: CaseOutcomeRecord) -> None:
        payload_json = json.dumps(asdict(record), sort_keys=True, separators=(",", ":"))
        try:
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT revision, record_digest, payload_json FROM case_outcomes WHERE case_id = ?",
                    (record.case_id,),
                ).fetchone()
                if existing is None:
                    if record.revision is not CaseRecordRevision.BODY:
                        raise RunResultStoreError("case outcome must begin at BODY")
                    connection.execute(
                        "INSERT INTO case_outcomes VALUES (?, ?, ?, ?)",
                        (record.case_id, int(record.revision), record.digest, payload_json),
                    )
                else:
                    revision, digest, existing_payload = existing
                    if int(record.revision) == revision:
                        if digest != record.digest or existing_payload != payload_json:
                            raise RunResultStoreError("conflicting equal-revision case outcome")
                        return
                    if int(record.revision) != revision + 1:
                        raise RunResultStoreError("stale or skipped case outcome revision")
                    changed = connection.execute(
                        """
                        UPDATE case_outcomes
                        SET revision = ?, record_digest = ?, payload_json = ?
                        WHERE case_id = ? AND revision = ? AND record_digest = ?
                        """,
                        (
                            int(record.revision),
                            record.digest,
                            payload_json,
                            record.case_id,
                            revision,
                            digest,
                        ),
                    ).rowcount
                    if changed != 1:
                        raise RunResultStoreError("case outcome CAS lost")
                    if record.revision is CaseRecordRevision.FINAL:
                        sequence = connection.execute(
                            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM case_phase_events WHERE case_id = ?",
                            (record.case_id,),
                        ).fetchone()[0]
                        connection.execute(
                            "INSERT INTO case_phase_events (case_id, sequence, phase) VALUES (?, ?, ?)",
                            (record.case_id, sequence, CaseLifecyclePhase.CASE_FINISHED.value),
                        )
                        connection.execute(
                            """
                            INSERT INTO case_lifecycle (case_id, current_phase) VALUES (?, ?)
                            ON CONFLICT(case_id) DO UPDATE SET current_phase=excluded.current_phase
                            """,
                            (record.case_id, CaseLifecyclePhase.CASE_FINISHED.value),
                        )
        except sqlite3.Error as exc:
            raise RunResultStoreError("case outcome commit failed") from exc

    def load_case_outcome(self, case_id: str) -> CaseOutcomeRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_digest, payload_json FROM case_outcomes WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if row is None:
            return None
        digest, payload_json = row
        payload = json.loads(payload_json)
        payload["revision"] = CaseRecordRevision(payload["revision"])
        payload["cleanup_disposition"] = CleanupDisposition(payload["cleanup_disposition"])
        payload["projection_disposition"] = ProjectionDisposition(payload["projection_disposition"])
        payload["report_disposition"] = ReportDisposition(payload["report_disposition"])
        payload["export_disposition"] = ExportDisposition(payload["export_disposition"])
        record = CaseOutcomeRecord(**payload)
        if record.digest != digest:
            raise RunResultStoreError("case outcome digest divergence")
        if record.official_checkpoint_id:
            with self._connect() as connection:
                official = connection.execute(
                    """
                    SELECT schema_version, checkpoint_id, task_id, observation_id,
                           evaluation_status, run_status, outcome_kind, outcome_code,
                           evidence_refs_json
                    FROM official_outcomes WHERE case_id = ?
                    """,
                    (case_id,),
                ).fetchone()
            if (
                official is None
                or official[1] != record.official_checkpoint_id
                or _official_checkpoint_digest(case_id, official) != record.official_checkpoint_digest
            ):
                raise RunResultStoreError("case outcome official checkpoint join is missing or divergent")
        return record

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
                    """
                    INSERT INTO case_reports (case_id, payload_json) VALUES (?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET payload_json=excluded.payload_json
                    """,
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
                    """
                    INSERT INTO run_reports (run_id, payload_json) VALUES (?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET payload_json=excluded.payload_json
                    """,
                    (run_id, payload),
                )
        except sqlite3.Error as exc:
            raise RunResultStoreError("run report commit failed") from exc

    def record_suite_report_disposition(self, disposition: SuiteReportDisposition) -> None:
        try:
            with self._connect() as connection:
                existing = connection.execute(
                    """
                    SELECT expected_case_count, report_disposition, export_disposition, failure_code
                    FROM run_finalization WHERE run_id = ?
                    """,
                    (disposition.run_id,),
                ).fetchone()
                payload = (
                    disposition.expected_case_count,
                    disposition.report_disposition.value,
                    disposition.export_disposition.value,
                    disposition.failure_code,
                )
                if existing is None:
                    connection.execute(
                        "INSERT INTO run_finalization VALUES (?, ?, ?, ?, ?)",
                        (disposition.run_id, *payload),
                    )
                elif tuple(existing) == payload:
                    return
                elif existing[1:3] != (
                    ReportDisposition.NOT_ATTEMPTED.value,
                    ExportDisposition.NOT_ATTEMPTED.value,
                ):
                    raise RunResultStoreError("suite report disposition is already terminal")
                else:
                    changed = connection.execute(
                        """
                        UPDATE run_finalization
                        SET expected_case_count = ?, report_disposition = ?,
                            export_disposition = ?, failure_code = ?
                        WHERE run_id = ? AND report_disposition = ? AND export_disposition = ?
                        """,
                        (
                            *payload,
                            disposition.run_id,
                            ReportDisposition.NOT_ATTEMPTED.value,
                            ExportDisposition.NOT_ATTEMPTED.value,
                        ),
                    ).rowcount
                    if changed != 1:
                        raise RunResultStoreError("suite report disposition CAS lost")
        except sqlite3.Error as exc:
            raise RunResultStoreError("suite report disposition commit failed") from exc

    def load_suite_report_disposition(self, run_id: str) -> SuiteReportDisposition | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT expected_case_count, report_disposition, export_disposition, failure_code
                FROM run_finalization WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return SuiteReportDisposition(
            run_id,
            int(row[0]),
            ReportDisposition(row[1]),
            ExportDisposition(row[2]),
            str(row[3]),
        )

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


def _official_checkpoint_digest(case_id: str, row: tuple[object, ...]) -> str:
    schema_version, _checkpoint_id, task_id, observation_id, evaluation_status, run_status, outcome_kind, outcome_code, refs = row
    try:
        evidence_refs = tuple(json.loads(str(refs)))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RunResultStoreError("official checkpoint payload is malformed") from exc
    values = {
        "schema_version": schema_version,
        "case_id": case_id,
        "task_id": task_id,
        "observation_id": observation_id,
        "evaluation_status": evaluation_status,
        "run_status": run_status,
        "outcome_kind": outcome_kind,
        "outcome_code": outcome_code,
        "evidence_refs": evidence_refs,
    }
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
CREATE TABLE IF NOT EXISTS case_outcomes (
    case_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    record_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_reports (
    run_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_finalization (
    run_id TEXT PRIMARY KEY,
    expected_case_count INTEGER NOT NULL,
    report_disposition TEXT NOT NULL,
    export_disposition TEXT NOT NULL,
    failure_code TEXT NOT NULL
);
"""
