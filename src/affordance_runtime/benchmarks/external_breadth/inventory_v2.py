"""Multi-axis, source-bound MiniWoB requirement inventory v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.capability_inventory import build_capability_inventory
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobRegistryCensus
from affordance_runtime.benchmarks.external_breadth.requirements import (
    DeclaredAgentCapabilities,
    MiniWobTaskRequirements,
    TaskReadiness,
)
from affordance_runtime.benchmarks.external_breadth.source_analysis import analyze_task_source


def current_declared_capabilities() -> DeclaredAgentCapabilities:
    return DeclaredAgentCapabilities(
        interaction=("activate", "fill", "select"),
        observation=(
            "structural_label", "structural_role", "structural_value",
            "structural_selection_state", "structural_checked_state",
        ),
        reasoning=("direct_match", "copy"),
        control=("single_target", "form_submit", "option_select", "multi_step_sequence"),
    )


def build_capability_inventory_v2(
    census: MiniWobRegistryCensus,
    source_root: Path | None = None,
) -> tuple[MiniWobTaskRequirements, ...]:
    primitive = {item.task_id: item.required_primitives for item in build_capability_inventory(census)}
    records = tuple(_requirements(task_id, primitive[task_id], source_root) for task_id in census.task_ids)
    if len(records) != len(census.task_ids) or len({item.task_id for item in records}) != len(records):
        raise ValueError("capability inventory v2 must cover every registry task exactly once")
    return records


def task_readiness(
    requirements: MiniWobTaskRequirements,
    capabilities: DeclaredAgentCapabilities,
) -> TaskReadiness:
    required = (
        (requirements.interaction_requirements, capabilities.interaction),
        (requirements.observation_requirements, capabilities.observation),
        (requirements.reasoning_requirements, capabilities.reasoning),
        (requirements.control_requirements, capabilities.control),
    )
    if any(any(item != "unknown" and item not in declared for item in values) for values, declared in required):
        return TaskReadiness.DECLARED_UNSUPPORTED
    if any("unknown" in values for values, _declared in required):
        return TaskReadiness.UNASSESSED
    return TaskReadiness.DECLARED_SUPPORTED


def capability_inventory_v2_digest(
    census: MiniWobRegistryCensus,
    inventory: tuple[MiniWobTaskRequirements, ...],
    capabilities: DeclaredAgentCapabilities,
) -> str:
    payload = {
        "schema_version": "miniwob-capability-inventory.v2",
        "package": (census.package_name, census.package_version, census.core_version),
        "source_commit": census.source_commit,
        "declared_capabilities": capabilities.__dict__,
        "tasks": [
            {**item.__dict__, "readiness": task_readiness(item, capabilities).value}
            for item in sorted(inventory, key=lambda value: value.task_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def _requirements(
    task_id: str,
    primitives: tuple[str, ...],
    source_root: Path | None,
) -> MiniWobTaskRequirements:
    slug = task_id.removeprefix("browsergym/miniwob.")
    interaction = set(primitives)
    observation, reasoning, control, reviewed = _reviewed_semantics(slug)
    source = f"miniwob/html/miniwob/{slug}.html@7fd85d71a4b6"
    method = "reviewed_source_rule.v2"
    if source_root is not None:
        path = source_root / "miniwob" / "html" / "miniwob" / f"{slug}.html"
        if not path.is_file():
            raise ValueError(f"pinned MiniWoB source is missing for {slug}")
        signals = analyze_task_source(path)
        interaction.update(signals.interaction)
        observation.update(signals.observation)
        method = "static_source+reviewed_rule.v2"
    if not reviewed:
        observation.add("unknown")
        reasoning.add("unknown")
        control.add("unknown")
    return MiniWobTaskRequirements(
        task_id,
        tuple(sorted(interaction)),
        tuple(sorted(observation)),
        tuple(sorted(reasoning)),
        tuple(sorted(control)),
        (source,),
        method,
        "medium" if reviewed else "unassessed",
    )


def _reviewed_semantics(slug: str) -> tuple[set[str], set[str], set[str], bool]:
    observation = {"structural_label", "structural_role"}
    reasoning: set[str] = set()
    control: set[str] = set()
    reviewed = False
    if _matches(slug, ("click-test", "click-button", "click-link", "click-option", "click-tab")):
        reasoning.add("direct_match")
        control.add("single_target")
        reviewed = True
    if _matches(slug, ("enter-text", "login-user")):
        observation.add("structural_value")
        reasoning.add("copy")
        control.add("form_submit")
        reviewed = True
    if _matches(slug, ("choose-list",)):
        observation.add("structural_selection_state")
        reasoning.add("direct_match")
        control.add("option_select")
        reviewed = True
    special = _special_semantics(slug)
    if special is not None:
        extra_observation, extra_reasoning, extra_control = special
        observation.update(extra_observation)
        reasoning.update(extra_reasoning)
        control.update(extra_control)
        reviewed = True
    return observation, reasoning, control, reviewed


def _special_semantics(slug: str) -> tuple[set[str], set[str], set[str]] | None:
    if _matches(slug, ("grid-coordinate", "click-pie", "click-shades", "visual-")):
        return {"visual_geometry", "visual_spatial"}, {"direct_match"}, {"single_target"}
    if _matches(slug, ("read-table", "stock-market", "phone-book")):
        return {"table_extraction", "structural_relations"}, {"compare"}, {"single_target"}
    if _matches(slug, ("simple-algebra", "visual-addition")):
        return {"structural_value"}, {"arithmetic"}, {"form_submit"}
    if _matches(slug, ("text-transform",)):
        return {"structural_value"}, {"text_transform"}, {"form_submit"}
    if _matches(slug, ("tic-tac-toe", "hot-cold")):
        return {"dynamic_change"}, {"stateful_game", "memory_across_turns"}, {"game_loop"}
    if _matches(slug, ("ascending-numbers",)):
        return {"list_relation"}, {"sort", "multi_target_sequence"}, {"multi_step_sequence"}
    if _matches(slug, ("find-greatest",)):
        return {"list_relation"}, {"compare"}, {"single_target"}
    if _matches(slug, ("copy-paste",)):
        return {"structural_value"}, {"copy"}, {"clipboard_flow"}
    if _matches(slug, ("form-sequence", "button-sequence", "social-media", "email-inbox")):
        return {"dynamic_change"}, {"multi_target_sequence"}, {"multi_step_sequence"}
    if _matches(slug, ("scroll-", "click-scroll-list")):
        return {"scroll_state"}, {"direct_match"}, {"single_target"}
    return None


def _matches(slug: str, markers: tuple[str, ...]) -> bool:
    return any(marker in slug for marker in markers)
