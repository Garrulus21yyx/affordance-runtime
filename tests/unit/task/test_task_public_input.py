import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.context.task_projection import project_task
from affordance_runtime.task import TaskGoal
from affordance_runtime.task.public_input import (
    TASK_PUBLIC_INPUT_BOUND,
    TaskPublicInputError,
    TaskPublicInputIssueCode,
)

_BUSINESS_KEYS = (
    "coordinates",
    "coordinate",
    "selector",
    "path",
    "viewport",
    "x",
    "y",
    "dom_id",
    "target_id",
)


@given(st.sampled_from(_BUSINESS_KEYS), st.sampled_from(("lower", "upper", "title")))
def test_public_business_key_spelling_is_lossless_on_both_task_branches(key, casing) -> None:
    renamed = {"lower": key.lower(), "upper": key.upper(), "title": key.title()}[casing]
    value = {renamed: {"nested": ["短", "punctuation!?", 3]}}
    goal = TaskGoal("task:public-key", "Use the supplied public data", inputs=value)

    assert goal.inputs == value
    assert project_task(goal).public_inputs == value


def test_task_public_input_string_binary_depth_and_total_bound_fail_typed() -> None:
    bound = TASK_PUBLIC_INPUT_BOUND
    TaskGoal("task:string-bound", "Inspect", inputs={"value": "x" * bound.max_string_chars})
    with pytest.raises(TaskPublicInputError) as string_error:
        TaskGoal("task:string-over", "Inspect", inputs={"value": "x" * (bound.max_string_chars + 1)})
    assert string_error.value.code is TaskPublicInputIssueCode.STRING_EXCEEDED

    with pytest.raises(TaskPublicInputError) as binary_error:
        TaskGoal("task:binary", "Inspect", inputs={"value": b"not-public-json"})
    assert binary_error.value.code is TaskPublicInputIssueCode.BINARY_UNSUPPORTED

    nested: object = "leaf"
    for index in range(bound.max_depth + 1):
        nested = {f"level_{index}": nested}
    with pytest.raises(TaskPublicInputError) as depth_error:
        TaskGoal("task:depth", "Inspect", inputs={"value": nested})
    assert depth_error.value.code is TaskPublicInputIssueCode.DEPTH_EXCEEDED

    with pytest.raises(TaskPublicInputError) as total_error:
        TaskGoal(
            "task:total",
            "Inspect",
            inputs={"left": "a" * 4_096, "middle": "b" * 4_096},
            success_criteria=({"id": "right", "value": "c" * 4_096},),
        )
    assert total_error.value.code is TaskPublicInputIssueCode.BYTES_EXCEEDED
