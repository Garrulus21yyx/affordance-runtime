"""Immutable benchmark-private diagnostics derived during BrowserGym acquisition."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

_INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "listbox", "checkbox",
    "radio", "option", "menuitem", "tab", "spinbutton", "slider",
})


@dataclass(frozen=True)
class BrowserGymDiagnosticSnapshot:
    raw_interactive_node_count: int
    raw_actionable_node_count: int
    raw_role_distribution: tuple[tuple[str, int], ...]

    def as_metrics(self) -> dict[str, object]:
        return {
            "raw_interactive_node_count": self.raw_interactive_node_count,
            "raw_actionable_node_count": self.raw_actionable_node_count,
            "raw_role_distribution": dict(self.raw_role_distribution),
        }


def diagnostic_snapshot(raw: dict[str, object]) -> BrowserGymDiagnosticSnapshot:
    tree = raw.get("axtree_object")
    nodes = tree.get("nodes", ()) if isinstance(tree, dict) else ()
    roles: Counter[str] = Counter()
    actionable = 0
    interactive = 0
    for node in nodes if isinstance(nodes, list) else ():
        if not isinstance(node, dict) or node.get("ignored") is True:
            continue
        value = node.get("role")
        role = value.get("value", "") if isinstance(value, dict) else ""
        if role not in _INTERACTIVE_ROLES:
            continue
        interactive += 1
        roles[str(role)] += 1
        actionable += int(role != "option")
    return BrowserGymDiagnosticSnapshot(interactive, actionable, tuple(sorted(roles.items())))
