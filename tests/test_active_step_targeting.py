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


def test_resolves_canonical_text_field_subject_to_unique_textbox() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="text_field",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:tt:1",
                role="textbox",
                label="tt",
                actions=("type_text",),
                state={"visible": True, "enabled": True, "control_value": ""},
            ),
        ),
    )

    assert target_ids == ("semantic:tt:1",)


def test_resolves_canonical_list_subject_to_unique_combobox() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="list",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:options:1",
                role="combobox",
                label="options",
                actions=("select_option",),
                state={"visible": True, "enabled": True, "selected_options": ("Ertha",)},
            ),
        ),
    )

    assert target_ids == ("semantic:options:1",)


def test_resolves_canonical_button_label_descriptor() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="button:label:no",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:no:1",
                role="button",
                label="No",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
            ActiveStepTargetView(
                target_id="semantic:yes:1",
                role="button",
                label="Yes",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
        ),
    )

    assert target_ids == ("semantic:no:1",)


def test_resolves_quoted_canonical_button_label_descriptor() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="button:label='cancel'",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:cancel:1",
                role="button",
                label="cancel",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
            ActiveStepTargetView(
                target_id="semantic:ok:1",
                role="button",
                label="ok",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
        ),
    )

    assert target_ids == ("semantic:cancel:1",)


def test_resolves_canonical_text_field_value_descriptor_to_unique_textbox() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="text_field:Myron",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:tt:1",
                role="textbox",
                label="tt",
                actions=("type_text",),
                state={"visible": True, "enabled": True, "control_value": ""},
            ),
        ),
    )

    assert target_ids == ("semantic:tt:1",)


def test_resolves_canonical_composite_button_descriptor_to_exact_label() -> None:
    target_ids = resolve_active_step_target_ids(
        subject="dialog_box_close_button",
        affordances=(
            ActiveStepTargetView(
                target_id="semantic:close:1",
                role="button",
                label="Close",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
            ActiveStepTargetView(
                target_id="semantic:cancel:1",
                role="button",
                label="Cancel",
                actions=("activate",),
                state={"visible": True, "enabled": True},
            ),
        ),
    )

    assert target_ids == ("semantic:close:1",)
