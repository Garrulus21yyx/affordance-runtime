from time import perf_counter

from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    ax_node,
    raw_observation,
    reset_task_state,
)
from tests.support.surfaces.browsergym.projection_support import (
    project_browsergym_observation,
)


def test_full_9600_target_projection_is_complete_and_bounded() -> None:
    count = 9_600
    actionable_count = 1_840
    raw = raw_observation(*(
        ax_node(
            f"result-{index}",
            "link" if index < actionable_count else "StaticText",
            f"Result {index}",
        )
        for index in range(count)
    ))
    started = perf_counter()

    projection = project_browsergym_observation(
        raw,
        observation_id="obs:large-inventory",
        source_revision="revision:large-inventory",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=reset_task_state("obs:large-inventory"),
        entity_identity=BrowserGymEntityIdentityMap(
            b"browsergym-large-inventory-tests"
        ),
    )

    elapsed = perf_counter() - started
    page_targets = tuple(
        item
        for item in projection.world.targets
        if item.role not in {"browser_context", "focused_context", "viewport"}
    )
    assert len(page_targets) == count
    assert {item.label for item in page_targets} == {
        f"Result {index}" for index in range(count)
    }
    assert elapsed < 8.0
