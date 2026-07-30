from affordance_runtime.active_step_targeting import (
    ActiveStepTargetView,
    resolve_active_step_target_ids,
)


def test_resolves_button_subject_with_article_to_unique_exact_label() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="the no button",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:no:1",
                role="button",
                label="no",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
            ActiveStepTargetView(
                target_id="semantic:ok:1",
                role="button",
                label="Ok",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
        ),
    )

    assert target_ids == ("semantic:no:1",)


def test_button_subject_label_mapping_fails_closed_when_label_is_not_unique() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="the no button",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:no:1",
                role="button",
                label="no",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
            ActiveStepTargetView(
                target_id="semantic:no:2",
                role="button",
                label="No",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
        ),
    )

    assert target_ids == ()


def test_resolves_role_prefixed_button_subject_to_unique_exact_label() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="button ONE",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:one:1",
                role="button",
                label="ONE",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
            ActiveStepTargetView(
                target_id="semantic:two:1",
                role="button",
                label="TWO",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
        ),
    )

    assert target_ids == ("semantic:one:1",)
