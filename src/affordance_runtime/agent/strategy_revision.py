"""Bounded, non-authoritative semantic progress for recovery turns."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum

_MAX_FACTS = 8
_MAX_HYPOTHESES = 4
_MAX_QUESTIONS = 8
_MAX_FAILED_STRATEGIES = 3


def _bounded_text(value: str, *, field_name: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > max_length:
        raise ValueError(f"strategy revision {field_name} is invalid")
    return normalized


class StrategyDisposition(StrEnum):
    CONTINUE = "continue"
    READY_TO_SUBMIT = "ready_to_submit"
    NO_SUPPORTED_ROUTE = "no_supported_route"


@dataclass(frozen=True)
class StrategyFact:
    claim: str
    value: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim", _bounded_text(self.claim, field_name="fact claim", max_length=240))
        object.__setattr__(self, "value", _bounded_text(self.value, field_name="fact value", max_length=500))
        object.__setattr__(self, "source", _bounded_text(self.source, field_name="fact source", max_length=240))


@dataclass(frozen=True)
class WorkingHypothesis:
    claim: str
    needs_verification: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim", _bounded_text(self.claim, field_name="hypothesis", max_length=300))
        if self.needs_verification is not True:
            raise ValueError("working hypotheses must remain explicitly unverified")


@dataclass(frozen=True)
class StrategyRevision:
    """One whole replacement produced only at a typed strategy-recovery boundary.

    This value records model-authored working state. It is neither World truth,
    task completion evidence, nor a mutable plan maintained by Runtime.
    """

    task_revision: int
    source_recovery_signature: str
    source_recovery_attempt: int
    disposition: StrategyDisposition
    verified_facts: tuple[StrategyFact, ...]
    working_hypotheses: tuple[WorkingHypothesis, ...]
    remaining_questions: tuple[str, ...]
    next_intent: str
    failed_strategies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.task_revision < 1:
            raise ValueError("strategy revision requires a current task revision")
        signature = self.source_recovery_signature.strip()
        if not signature or len(signature) > 1_000:
            raise ValueError("strategy revision requires one bounded recovery signature")
        if not 1 <= self.source_recovery_attempt <= 3:
            raise ValueError("strategy revision recovery attempt is invalid")
        object.__setattr__(self, "source_recovery_signature", signature)
        object.__setattr__(self, "disposition", StrategyDisposition(self.disposition))
        facts = tuple(self.verified_facts)
        hypotheses = tuple(self.working_hypotheses)
        questions = tuple(
            _bounded_text(item, field_name="remaining question", max_length=300) for item in self.remaining_questions
        )
        failed = tuple(
            _bounded_text(item, field_name="failed strategy", max_length=300) for item in self.failed_strategies
        )
        if (
            len(facts) > _MAX_FACTS
            or len(hypotheses) > _MAX_HYPOTHESES
            or len(questions) > _MAX_QUESTIONS
            or len(failed) > _MAX_FAILED_STRATEGIES
            or any(not isinstance(item, StrategyFact) for item in facts)
            or any(not isinstance(item, WorkingHypothesis) for item in hypotheses)
        ):
            raise ValueError("strategy revision collections exceed their bounds")
        if len(set(questions)) != len(questions) or len(set(failed)) != len(failed):
            raise ValueError("strategy revision collections must be unique")
        next_intent = _bounded_text(self.next_intent, field_name="next intent", max_length=400)
        if self.disposition is StrategyDisposition.READY_TO_SUBMIT and (questions or hypotheses):
            raise ValueError("ready-to-submit strategy cannot retain unresolved claims")
        object.__setattr__(self, "verified_facts", facts)
        object.__setattr__(self, "working_hypotheses", hypotheses)
        object.__setattr__(self, "remaining_questions", questions)
        object.__setattr__(self, "next_intent", next_intent)
        object.__setattr__(self, "failed_strategies", failed)

    @property
    def revision_digest(self) -> str:
        payload = {
            "task_revision": self.task_revision,
            "source_recovery_signature": self.source_recovery_signature,
            "source_recovery_attempt": self.source_recovery_attempt,
            "disposition": self.disposition.value,
            "verified_facts": [asdict(item) for item in self.verified_facts],
            "working_hypotheses": [asdict(item) for item in self.working_hypotheses],
            "remaining_questions": self.remaining_questions,
            "next_intent": self.next_intent,
            "failed_strategies": self.failed_strategies,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def public_projection(self) -> dict[str, object]:
        return {
            "disposition": self.disposition.value,
            "verified_facts": tuple(
                {"claim": item.claim, "value": item.value, "source": item.source} for item in self.verified_facts
            ),
            "working_hypotheses": tuple(
                {"claim": item.claim, "needs_verification": item.needs_verification} for item in self.working_hypotheses
            ),
            "remaining_questions": self.remaining_questions,
            "next_intent": self.next_intent,
            "failed_strategies": self.failed_strategies,
            "source_recovery_attempt": self.source_recovery_attempt,
            "revision_digest": self.revision_digest,
        }

    def checkpoint_projection(self) -> dict[str, object]:
        return {
            "task_revision": self.task_revision,
            "source_recovery_signature": self.source_recovery_signature,
            **self.public_projection(),
        }

    @classmethod
    def from_checkpoint(cls, payload: object) -> StrategyRevision:
        if not isinstance(payload, Mapping):
            raise TypeError("strategy revision checkpoint must be a mapping")
        raw_facts = payload.get("verified_facts", ())
        raw_hypotheses = payload.get("working_hypotheses", ())
        raw_questions = payload.get("remaining_questions", ())
        raw_failed = payload.get("failed_strategies", ())
        if (
            not isinstance(raw_facts, Sequence)
            or isinstance(raw_facts, str | bytes)
            or not isinstance(raw_hypotheses, Sequence)
            or isinstance(raw_hypotheses, str | bytes)
            or not isinstance(raw_questions, Sequence)
            or isinstance(raw_questions, str | bytes)
            or not isinstance(raw_failed, Sequence)
            or isinstance(raw_failed, str | bytes)
            or any(not isinstance(item, Mapping) for item in raw_facts)
            or any(not isinstance(item, Mapping) for item in raw_hypotheses)
        ):
            raise TypeError("strategy revision checkpoint collections are invalid")
        revision = cls(
            task_revision=int(payload["task_revision"]),
            source_recovery_signature=str(payload["source_recovery_signature"]),
            source_recovery_attempt=int(payload["source_recovery_attempt"]),
            disposition=StrategyDisposition(str(payload["disposition"])),
            verified_facts=tuple(
                StrategyFact(str(item["claim"]), str(item["value"]), str(item["source"])) for item in raw_facts
            ),
            working_hypotheses=tuple(
                WorkingHypothesis(str(item["claim"]), item.get("needs_verification") is True) for item in raw_hypotheses
            ),
            remaining_questions=tuple(str(item) for item in raw_questions),
            next_intent=str(payload["next_intent"]),
            failed_strategies=tuple(str(item) for item in raw_failed),
        )
        expected = payload.get("revision_digest")
        if expected is not None and expected != revision.revision_digest:
            raise ValueError("strategy revision checkpoint digest is invalid")
        return revision


__all__ = [
    "StrategyDisposition",
    "StrategyFact",
    "StrategyRevision",
    "WorkingHypothesis",
]
