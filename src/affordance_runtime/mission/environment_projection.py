"""One deterministic, non-authoritative Manager projection from fresh World."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.mission.contracts import MissionEnvironmentView
from affordance_runtime.world.contracts import WorldObservation

_CAPABILITY_DESCRIPTIONS = {
    "activate": "activate an offered control",
    "press_key": "use the keyboard on the focused control",
    "type_text": "enter text into an offered field",
    "select_option": "choose from an offered set of options",
    "scroll": "move within the current page",
    "drag_to": "drag between offered controls",
    "focus": "focus an offered control",
    "hover": "inspect an offered control by hovering",
    "set_value": "set a value on an offered control",
    "read": "read content exposed by the current application",
}


def project_mission_environment(
    observation: WorldObservation,
    recent_steps: Sequence[AgentTurnView] = (),
) -> MissionEnvironmentView:
    """Describe execution scope without forwarding World, refs, screenshots, or trajectory."""

    document_title = _page_title(observation)
    heading = _primary_heading(observation)
    current_route = _current_route(observation)
    identity_conflict = bool(
        document_title
        and (heading or current_route)
        and document_title.casefold() not in f"{heading} {current_route}".casefold()
    )
    preferred_title = heading or document_title
    page_title, application = _page_and_application(preferred_title)
    operations = tuple(sorted({item.semantic_action for item in observation.bindings if item.semantic_action}))
    capabilities = [
        "read content visible in the current application",
        "find content within the current application",
        *(
            _CAPABILITY_DESCRIPTIONS.get(
                operation,
                "use another interaction currently offered by the application",
            )
            for operation in operations
        ),
    ]
    if operations:
        capabilities.append("navigate within the current application")
    return MissionEnvironmentView(
        surface=_surface_family(observation),
        application=application,
        page_title=page_title,
        route_family=_route_family(observation),
        document_title=document_title,
        current_route=current_route,
        visible_primary_heading=heading,
        identity_conflict=identity_conflict,
        available_capabilities=tuple(dict.fromkeys(capabilities)),
        unavailable_capabilities=("search the public web outside the current application",),
        last_successful_transitions=_successful_transitions(recent_steps),
    )


def _page_title(observation: WorldObservation) -> str:
    for source in observation.sources:
        for item in source.structure:
            if item.role.casefold() in {"document", "webarea", "rootwebarea"} and item.label.strip():
                return item.label.strip()[:240]
    target_title = next(
        (
            item.label.strip()
            for item in observation.targets
            if item.role.casefold() in {"document", "webarea", "rootwebarea"} and item.label.strip()
        ),
        "",
    )
    if target_title:
        return target_title[:240]
    heading = next(
        (item.label.strip() for item in observation.targets if item.role.casefold() == "heading" and item.label.strip()),
        "",
    )
    return heading[:240]


def _primary_heading(observation: WorldObservation) -> str:
    return next(
        (
            item.label.strip()[:240]
            for item in observation.targets
            if item.role.casefold() in {"heading", "status", "alert"} and item.label.strip()
        ),
        "",
    )


def _current_route(observation: WorldObservation) -> str:
    raw = next(
        (
            str(item.state["page.route"])
            for item in observation.targets
            if item.role.casefold() == "viewport" and item.state.get("page.route")
        ),
        "",
    )
    if not raw:
        return ""
    parsed = urlsplit(raw)
    return (parsed.path or "/")[:240]


def _page_and_application(title: str) -> tuple[str, str]:
    for separator in (" / ", " | ", " — "):
        parts = tuple(item.strip() for item in title.split(separator) if item.strip())
        if len(parts) > 1:
            return parts[0][:240], parts[-1][:240]
    return title[:240], title[:240]


def _surface_family(observation: WorldObservation) -> str:
    surfaces = tuple(dict.fromkeys(item.surface.strip().casefold() for item in observation.sources if item.surface.strip()))
    if any("browser" in item for item in surfaces):
        return "browser"
    if any("http" in item for item in surfaces):
        return "http"
    if any("wot" in item for item in surfaces):
        return "device"
    return surfaces[0][:80] if surfaces else "unknown"


def _route_family(observation: WorldObservation) -> str:
    route = next(
        (
            str(item.state["page.route"])
            for item in observation.targets
            if item.role.casefold() == "viewport" and item.state.get("page.route")
        ),
        "",
    )
    if not route:
        return ""
    path = urlsplit(route).path
    segments = tuple(item for item in path.split("/") if item)[:2]
    return f"/{'/'.join(segments)}/" if segments else "/"


def _successful_transitions(recent_steps: Sequence[AgentTurnView]) -> tuple[str, ...]:
    transitions: list[str] = []
    for step in recent_steps:
        if (
            step.decision_kind != "selectaction"
            or step.dispatch_status in {"", "not_sent"}
            or step.local_postcondition != "satisfied"
            or step.target is None
        ):
            continue
        label = step.target.label.strip() or step.target.role.strip()
        summary = " ".join(item for item in (step.semantic_action.strip(), label) if item)[:240]
        if summary and summary not in transitions:
            transitions.append(summary)
    return tuple(transitions[-4:])
