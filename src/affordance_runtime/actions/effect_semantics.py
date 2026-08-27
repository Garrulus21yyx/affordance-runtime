"""Dependency-free closed effect semantics shared by action and execution contracts."""

from __future__ import annotations

from enum import StrEnum


class Reversibility(StrEnum):
    REVERSIBLE = "reversible"
    COMPENSATABLE = "compensatable"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


__all__ = ["Reversibility"]
