"""Public-safe typed facts produced by semantic action admission owners."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


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


@dataclass(frozen=True)
class AdmissionIssue:
    """A bounded rejection fact; it deliberately omits the rejected value."""

    code: AdmissionIssueCode
    public_field_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.code, AdmissionIssueCode) or _CODE.fullmatch(self.code.value) is None:
            raise ValueError("admission issue code is invalid")
        paths = tuple(sorted(set(self.public_field_paths)))
        if not paths or len(paths) > 4 or any(path not in _PUBLIC_PATHS for path in paths):
            raise ValueError("admission issue paths are not public and bounded")
        object.__setattr__(self, "public_field_paths", paths)


def invalid_parameters_issue() -> AdmissionIssue:
    return AdmissionIssue(AdmissionIssueCode.INVALID_ACTION_PARAMETERS, ("parameters",))
