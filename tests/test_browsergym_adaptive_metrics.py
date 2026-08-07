from types import SimpleNamespace

from affordance_runtime.benchmarks.browsergym import _browsergym_adaptive_runtime_stats
from affordance_runtime.benchmarks.browsergym_matrix import write_browsergym_report
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult


def _node(kind: str, payload: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, payload=payload or {})


def test_browsergym_episode_projects_m85_route_conflict_and_skill_trace_metrics() -> None:
    stats = _browsergym_adaptive_runtime_stats(
        (
            _node("RouteSelected", {"source": "dom"}),
            _node("ContractBuilt", {"fallback_reason": ""}),
            _node("SourceAssertionsArbitrated", {"decisions": [{"status": "reobserve"}]}),
            _node("TargetedPerceptionCaptured"),
            _node("RouteSelected", {"source": "visual"}),
            _node("ContractBuilt", {"fallback_reason": "DOM dispatch failed"}),
            _node("TaskSkillActivated"),
            _node("TaskSkillFellThrough"),
            _node("TaskSkillCompleted"),
        )
    )

    assert stats == {
        "route_selection_count": 2,
        "route_sources": ["dom", "visual"],
        "visual_route_count": 1,
        "fallback_route_count": 1,
        "targeted_perception_count": 1,
        "source_conflict_count": 1,
        "task_skill_activated_count": 1,
        "task_skill_completed_count": 1,
        "task_skill_fallthrough_count": 1,
    }


def test_public_browsergym_report_aggregates_m85_metrics_without_breaking_episode_schema(
    tmp_path,
) -> None:
    episode = BrowserGymEpisodeResult(
        "click-button",
        0,
        "done",
        True,
        1.0,
        True,
        False,
        1,
        ["click"],
        [],
        "",
        False,
        "trace.jsonl",
        route_selection_count=2,
        route_sources=["dom", "visual"],
        visual_route_count=1,
        fallback_route_count=1,
        targeted_perception_count=1,
        source_conflict_count=1,
        task_skill_activated_count=1,
        task_skill_completed_count=1,
    )

    report = write_browsergym_report(
        tmp_path,
        profile="smoke",
        registered_tasks=("click-button",),
        selected_tasks=("click-button",),
        seeds=(0,),
        episodes=(episode,),
    )

    assert report["adaptive_runtime_statistics"] == {
        "route_selection_count": 2,
        "route_source_counts": {"dom": 1, "visual": 1},
        "visual_route_count": 1,
        "fallback_route_count": 1,
        "targeted_perception_count": 1,
        "source_conflict_count": 1,
        "task_skill_activated_count": 1,
        "task_skill_completed_count": 1,
        "task_skill_fallthrough_count": 0,
    }
