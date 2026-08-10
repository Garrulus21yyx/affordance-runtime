"""Narrow static interaction signals from the reviewed MiniWoB HTML source."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticSourceSignals:
    interaction: tuple[str, ...] = ()
    observation: tuple[str, ...] = ()


def analyze_task_source(path: Path) -> StaticSourceSignals:
    text = path.read_text(encoding="utf-8").casefold()
    interaction: set[str] = set()
    observation: set[str] = set()
    if "<canvas" in text:
        interaction.add("canvas")
        observation.add("visual_geometry")
    if re.search(r"dragstart|dragend|draggable\s*=", text):
        interaction.add("drag")
    if re.search(r"keydown|keypress|keyup", text):
        interaction.add("keypress")
    if re.search(r"overflow(?:-y)?\s*:\s*(?:scroll|auto)", text):
        interaction.add("scroll")
        observation.add("scroll_state")
    if "clipboard" in text:
        interaction.add("clipboard")
    return StaticSourceSignals(tuple(sorted(interaction)), tuple(sorted(observation)))
