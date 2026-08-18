"""Small episode-local facts pinned from current public World evidence."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from affordance_runtime.evaluation.evidence_records import EvidenceRecord

MAX_WORKING_FACTS = 16
MAX_WORKING_FACT_SERIALIZED_BYTES = 4 * 1024
_MAX_VALUE_CHARS = 2_000
_KEY = re.compile(r"[a-z][a-z0-9_]{0,63}")


@dataclass(frozen=True)
class WorkingFact:
    """One exact scalar value retained for the current executor episode."""

    key: str
    record: EvidenceRecord
    acquired_at_step: int
    purpose: str

    def __post_init__(self) -> None:
        if _KEY.fullmatch(self.key) is None:
            raise ValueError("working fact key is invalid")
        if not isinstance(self.record, EvidenceRecord) or self.record.kind != "fact":
            raise TypeError("working fact requires a fact evidence record")
        if not is_public_scalar(self.record.value):
            raise ValueError("working fact value must be a bounded public scalar")
        if self.acquired_at_step < 0:
            raise ValueError("working fact step cannot be negative")
        if not self.purpose.strip() or len(self.purpose) > 240:
            raise ValueError("working fact purpose must be bounded and nonblank")

    @property
    def value(self) -> str | int | float | bool:
        value = self.record.value
        assert isinstance(value, str | int | float | bool)
        return value


def public_working_facts(items: tuple[WorkingFact, ...]) -> tuple[dict[str, object], ...]:
    """Project values for the model without exposing canonical evidence identity."""

    return tuple(
        {
            "key": item.key,
            "value": item.value,
            "purpose": item.purpose,
            "acquired_at_step": item.acquired_at_step,
        }
        for item in items
    )


def validate_working_fact_collection(items: tuple[WorkingFact, ...]) -> tuple[WorkingFact, ...]:
    values = tuple(items)
    if (
        len(values) > MAX_WORKING_FACTS
        or any(not isinstance(item, WorkingFact) for item in values)
        or len({item.key for item in values}) != len(values)
    ):
        raise ValueError("episode working facts must be bounded, typed, and unique")
    encoded = json.dumps(
        public_working_facts(values),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    if len(encoded) > MAX_WORKING_FACT_SERIALIZED_BYTES:
        raise ValueError("episode working facts exceed their serialized byte budget")
    return values


def is_public_scalar(value: object) -> bool:
    if isinstance(value, bool | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and len(value) <= _MAX_VALUE_CHARS
