"""Closed outcome algebra for one task-evaluator invocation boundary."""

from __future__ import annotations

import hashlib
import re
import traceback
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.evaluation.contracts import TaskEvaluation

_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_URL = re.compile(r"(?i)\b(?:https?|wss?)://[^\s]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|secret|credential|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)


class TaskEvaluationStage(StrEnum):
    EVALUATOR_CALL = "evaluator_call"
    RESULT_CONTRACT = "result_contract"
    EVIDENCE_INDEX = "evidence_index"
    VALIDATION = "validation"
    NATIVE_SNAPSHOT = "native_snapshot"
    NATIVE_CLASSIFICATION = "native_classification"
    NATIVE_PROJECTION = "native_projection"


@dataclass(frozen=True)
class TaskEvaluationDiagnostic:
    diagnostic_ref: str
    stage: TaskEvaluationStage
    exception_type: str
    safe_message: str
    observation_id: str
    native_snapshot_present_fields: tuple[str, ...] = ()
    traceback_ref: str = ""

    def __post_init__(self) -> None:
        if re.fullmatch(r"task-evaluation-diagnostic:[0-9a-f]{24}", self.diagnostic_ref) is None:
            raise ValueError("task evaluation diagnostic identity is invalid")
        if not isinstance(self.stage, TaskEvaluationStage):
            raise TypeError("task evaluation diagnostic stage must be typed")
        if self.exception_type and _IDENTIFIER.fullmatch(self.exception_type) is None:
            raise ValueError("task evaluation diagnostic exception type is invalid")
        for value, name, limit in (
            (self.safe_message, "message", 500),
            (self.observation_id, "observation id", 512),
        ):
            if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 for char in value):
                raise ValueError(f"task evaluation diagnostic {name} is invalid")
        fields = tuple(self.native_snapshot_present_fields)
        if len(fields) > 32 or len(set(fields)) != len(fields) or any(
            not isinstance(item, str) or _IDENTIFIER.fullmatch(item) is None for item in fields
        ):
            raise ValueError("task evaluation diagnostic snapshot fields are invalid")
        object.__setattr__(self, "native_snapshot_present_fields", fields)
        if self.traceback_ref and re.fullmatch(r"traceback:sha256:[0-9a-f]{64}", self.traceback_ref) is None:
            raise ValueError("task evaluation diagnostic traceback reference is invalid")


@dataclass(frozen=True)
class Evaluated:
    evaluation: TaskEvaluation

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation, TaskEvaluation):
            raise TypeError("evaluated task outcome requires TaskEvaluation")


@dataclass(frozen=True)
class Unavailable:
    code: str
    diagnostic: TaskEvaluationDiagnostic

    def __post_init__(self) -> None:
        _validate_failure(self.code, self.diagnostic)


@dataclass(frozen=True)
class InternalFailure:
    code: str
    diagnostic: TaskEvaluationDiagnostic

    def __post_init__(self) -> None:
        _validate_failure(self.code, self.diagnostic)


TaskEvaluationAttempt = Evaluated | Unavailable | InternalFailure


class TaskEvaluationUnavailableError(RuntimeError):
    def __init__(self, outcome: Unavailable) -> None:
        self.outcome = outcome
        super().__init__(outcome.code)


class TaskEvaluationInternalError(RuntimeError):
    def __init__(self, outcome: InternalFailure) -> None:
        self.outcome = outcome
        super().__init__(outcome.code)


def task_evaluation_diagnostic_from_exception(
    exc: BaseException,
    *,
    stage: TaskEvaluationStage,
    observation_id: str,
    native_snapshot_present_fields: tuple[str, ...] = (),
) -> TaskEvaluationDiagnostic:
    traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    traceback_digest = hashlib.sha256(traceback_text.encode("utf-8", errors="replace")).hexdigest()
    exception_type = _safe_identifier(type(exc).__name__)
    safe_message = _safe_message(str(exc))
    fields = tuple(sorted(dict.fromkeys(native_snapshot_present_fields)))
    identity = "\0".join((stage.value, exception_type, safe_message, observation_id, *fields, traceback_digest))
    return TaskEvaluationDiagnostic(
        "task-evaluation-diagnostic:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        stage,
        exception_type,
        safe_message,
        observation_id,
        fields,
        f"traceback:sha256:{traceback_digest}",
    )


def _validate_failure(code: str, diagnostic: TaskEvaluationDiagnostic) -> None:
    if not isinstance(code, str) or _CODE.fullmatch(code) is None:
        raise ValueError("task evaluation failure code must be a bounded identifier")
    if not isinstance(diagnostic, TaskEvaluationDiagnostic):
        raise TypeError("task evaluation failure diagnostic must be typed")


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value)[:128]
    if not normalized or not re.match(r"[A-Za-z_]", normalized):
        normalized = f"_{normalized}" if normalized else "Exception"
    return normalized[:128]


def _safe_message(value: str) -> str:
    normalized = " ".join(value.split())
    normalized = _URL.sub("<redacted-url>", normalized)
    normalized = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", normalized)
    return normalized[:500]
