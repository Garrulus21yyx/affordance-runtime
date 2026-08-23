"""Typed, lossless public TaskGoal intake bound."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import to_json_compatible


class TaskPublicInputIssueCode(StrEnum):
    DEPTH_EXCEEDED = "task_public_input_depth_exceeded"
    ITEMS_EXCEEDED = "task_public_input_items_exceeded"
    STRING_EXCEEDED = "task_public_input_string_exceeded"
    BINARY_UNSUPPORTED = "task_public_input_binary_unsupported"
    VALUE_UNSUPPORTED = "task_public_input_value_unsupported"
    BYTES_EXCEEDED = "task_public_input_bytes_exceeded"


class TaskPublicInputError(ValueError):
    def __init__(self, code: TaskPublicInputIssueCode, path: str) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value}: {path}")


@dataclass(frozen=True)
class TaskPublicInputBound:
    max_depth: int = 8
    max_items_per_container: int = 128
    max_string_chars: int = 4_096
    max_total_bytes: int = 12 * 1024


TASK_PUBLIC_INPUT_BOUND = TaskPublicInputBound()


def admit_public_task_value(
    value: Any,
    *,
    path: str,
    bound: TaskPublicInputBound = TASK_PUBLIC_INPUT_BOUND,
) -> Any:
    _validate(value, path=path, depth=0, bound=bound)
    compatible = to_json_compatible(value)
    encoded = json.dumps(
        compatible,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(encoded) > bound.max_total_bytes:
        raise TaskPublicInputError(TaskPublicInputIssueCode.BYTES_EXCEEDED, path)
    return compatible


def _validate(value: object, *, path: str, depth: int, bound: TaskPublicInputBound) -> None:
    if depth > bound.max_depth:
        raise TaskPublicInputError(TaskPublicInputIssueCode.DEPTH_EXCEEDED, path)
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TaskPublicInputError(TaskPublicInputIssueCode.VALUE_UNSUPPORTED, path)
        return
    if isinstance(value, str):
        if len(value) > bound.max_string_chars:
            raise TaskPublicInputError(TaskPublicInputIssueCode.STRING_EXCEEDED, path)
        return
    if isinstance(value, bytes | bytearray):
        raise TaskPublicInputError(TaskPublicInputIssueCode.BINARY_UNSUPPORTED, path)
    if isinstance(value, Mapping):
        if len(value) > bound.max_items_per_container:
            raise TaskPublicInputError(TaskPublicInputIssueCode.ITEMS_EXCEEDED, path)
        for key, item in value.items():
            if not isinstance(key, str):
                raise TaskPublicInputError(TaskPublicInputIssueCode.VALUE_UNSUPPORTED, path)
            if len(key) > bound.max_string_chars:
                raise TaskPublicInputError(TaskPublicInputIssueCode.STRING_EXCEEDED, f"{path}.{key}")
            _validate(item, path=f"{path}.{key}", depth=depth + 1, bound=bound)
        return
    if isinstance(value, Sequence):
        if len(value) > bound.max_items_per_container:
            raise TaskPublicInputError(TaskPublicInputIssueCode.ITEMS_EXCEEDED, path)
        for index, item in enumerate(value):
            _validate(item, path=f"{path}[{index}]", depth=depth + 1, bound=bound)
        return
    raise TaskPublicInputError(TaskPublicInputIssueCode.VALUE_UNSUPPORTED, path)
