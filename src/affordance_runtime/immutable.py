"""Deeply immutable JSON-compatible values for runtime contract boundaries."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = Any
FrozenObject: TypeAlias = Any


class FrozenList(Sequence[JsonValue]):
    """Immutable JSON list that keeps comparison compatibility with list/tuple."""

    def __init__(self, values: Sequence[Any]) -> None:
        self._values = tuple(freeze_json(value) for value in values)

    def __getitem__(self, index: int | slice) -> JsonValue | tuple[JsonValue, ...]:
        return self._values[index]

    def __iter__(self) -> Iterator[JsonValue]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenList):
            return self._values == other._values
        if isinstance(other, (list, tuple)):
            return tuple(thaw_json_at_external_boundary(item) for item in self._values) == tuple(other)
        return False

    def __repr__(self) -> str:
        return repr(tuple(thaw_json_at_external_boundary(item) for item in self._values))


class FrozenSequence(tuple[Any, ...]):
    """Immutable non-JSON sequence with list/tuple comparison compatibility."""

    __hash__ = tuple.__hash__

    def __new__(cls, values: Sequence[Any]) -> "FrozenSequence":
        return super().__new__(cls, tuple(values))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            return tuple(self) == tuple(other)
        return False


class FrozenDict(Mapping[str, JsonValue]):
    """Immutable JSON object with deterministic key ordering."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        items: list[tuple[str, JsonValue]] = []
        for key, value in values.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys must be str, got {type(key).__name__}")
            items.append((key, freeze_json(value)))
        self._items = tuple(sorted(items, key=lambda item: item[0]))
        self._mapping = dict(self._items)

    def __getitem__(self, key: str) -> JsonValue:
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenDict):
            return self._items == other._items
        if isinstance(other, Mapping):
            return thaw_json_at_external_boundary(self) == dict(other)
        return False

    def __repr__(self) -> str:
        return repr(thaw_json_at_external_boundary(self))


def freeze_json(value: Any) -> JsonValue:
    """Return a deep immutable copy of a JSON-compatible value."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, FrozenDict | FrozenList):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return FrozenList(value)
    raise TypeError(f"value is not JSON-compatible: {type(value).__name__}")


def thaw_json_at_external_boundary(value: Any) -> Any:
    """Return mutable JSON-compatible containers for adapters/API boundaries."""

    if isinstance(value, FrozenDict):
        return {key: thaw_json_at_external_boundary(item) for key, item in value.items()}
    if isinstance(value, FrozenList):
        return [thaw_json_at_external_boundary(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {key: thaw_json_at_external_boundary(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json_at_external_boundary(item) for item in value]
    return value


def to_json_compatible(value: Any) -> Any:
    """Project dataclasses/enums/frozen JSON values into canonical JSON data."""

    if isinstance(value, FrozenDict | FrozenList):
        return thaw_json_at_external_boundary(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_json_compatible(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): to_json_compatible(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [to_json_compatible(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
