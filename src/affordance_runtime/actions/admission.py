"""Public-safe typed facts produced by semantic action admission owners."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.immutable import freeze_json


class AdmissionIssueCode(StrEnum):
    ACTION_OUTSIDE_ACTION_SPACE = "action_outside_action_space"
    ACTION_OUTSIDE_CURRENT_PAGE = "action_outside_current_page"
    DESTINATION_OUTSIDE_CURRENT_PAGE = "destination_outside_current_page"
    INVALID_ACTION_PARAMETERS = "invalid_action_parameters"


_PUBLIC_PATHS = frozenset({
    "action_id",
    "actions",
    "destination_id",
    "parameters",
})
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PATH = re.compile(r"parameters(?:\.[A-Za-z][A-Za-z0-9_-]{0,63})*|action_id|actions|destination_id")
_PRIVATE_PARTS = frozenset({
    "password", "secret", "token", "credential", "authorization", "api", "key",
    "selector", "coordinate", "bbox", "point", "href", "method", "backend", "executor",
})


class AdmissionContractOwner(StrEnum):
    CURRENT_ACTION_PAGE = "current_action_page"
    CURRENT_ACTION_SPACE = "current_action_space"


@dataclass(frozen=True)
class AdmissionIssue:
    """A bounded rejection fact; it deliberately omits the rejected value."""

    code: AdmissionIssueCode
    public_field_paths: tuple[str, ...]
    contract_owner: AdmissionContractOwner = AdmissionContractOwner.CURRENT_ACTION_SPACE
    expected: Mapping[str, object] = field(default_factory=dict)
    actual: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, AdmissionIssueCode) or _CODE.fullmatch(self.code.value) is None:
            raise ValueError("admission issue code is invalid")
        if not isinstance(self.contract_owner, AdmissionContractOwner):
            raise TypeError("admission contract owner must be typed")
        paths = tuple(sorted(set(self.public_field_paths)))
        if not paths or len(paths) > 4 or any(not _public_path(path) for path in paths):
            raise ValueError("admission issue paths are not public and bounded")
        object.__setattr__(self, "public_field_paths", paths)
        object.__setattr__(self, "expected", freeze_json(self.expected or {}))
        object.__setattr__(self, "actual", freeze_json(self.actual or {}))


def invalid_parameters_issue(
    *,
    field_path: str = "parameters",
    expected: Mapping[str, object] | None = None,
    actual: Mapping[str, object] | None = None,
) -> AdmissionIssue:
    return AdmissionIssue(
        AdmissionIssueCode.INVALID_ACTION_PARAMETERS,
        (field_path,),
        AdmissionContractOwner.CURRENT_ACTION_SPACE,
        expected or {},
        actual or {},
    )


def _public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    if _PATH.fullmatch(path) is None:
        return False
    parts = {part.casefold() for part in re.split(r"[._-]", path)}
    return not bool(parts & _PRIVATE_PARTS)
