"""One generation-local public reference grammar for every live boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class PublicRefKind(StrEnum):
    EXECUTABLE = "E"
    NODE = "N"
    FACT = "F"
    REGION = "R"


PUBLIC_REF_MAX_INDEX = 9_999


@dataclass(frozen=True)
class DecodedPublicRef:
    kind: PublicRefKind
    index: int


class PublicRefCodec:
    """Closed encoder/decoder with one cardinality decision."""

    max_index: int = PUBLIC_REF_MAX_INDEX

    @classmethod
    def pattern(cls, expected: PublicRefKind | str | None = None) -> str:
        prefix = PublicRefKind(expected).value if expected is not None else "[ENFR]"
        digits = len(str(cls.max_index))
        return rf"^({prefix})([1-9][0-9]{{0,{digits - 1}}})$"

    @classmethod
    def encode(cls, kind: PublicRefKind | str, index: int) -> str:
        selected = PublicRefKind(kind)
        if type(index) is not int or not 1 <= index <= cls.max_index:
            raise ValueError("public reference capacity exceeded")
        return f"{selected.value}{index}"

    @classmethod
    def decode(cls, value: str, *, expected: PublicRefKind | str | None = None) -> DecodedPublicRef:
        match = re.fullmatch(cls.pattern(), value) if isinstance(value, str) else None
        if match is None:
            raise ValueError("public reference is invalid")
        decoded = DecodedPublicRef(PublicRefKind(match.group(1)), int(match.group(2)))
        if decoded.index > cls.max_index:
            raise ValueError("public reference capacity exceeded")
        if expected is not None and decoded.kind is not PublicRefKind(expected):
            raise ValueError("public reference kind is invalid")
        return decoded

    @classmethod
    def accepts(cls, value: str, *, expected: PublicRefKind | str | None = None) -> bool:
        try:
            cls.decode(value, expected=expected)
        except (TypeError, ValueError):
            return False
        return True

    @classmethod
    def enum_schema(cls, values: tuple[str, ...], *, expected: PublicRefKind | str) -> dict[str, object]:
        if not values or any(not cls.accepts(value, expected=expected) for value in values):
            raise ValueError("public reference enum is invalid")
        if len(set(values)) != len(values):
            raise ValueError("public reference enum must be unique")
        return {"type": "string", "enum": list(values)}
