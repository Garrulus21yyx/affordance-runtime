from affordance_runtime.adapters.dom import (
    AuthoredInteractiveExtension,
    DomAdapter,
)

_AUTHORED_EXTENSION = AuthoredInteractiveExtension(
    marker_attribute="data-runtime-interactive",
    backend_handle_attribute="data-runtime-handle",
    visibility_ratio_attribute="data-runtime-visibility",
    semantic_patterns=frozenset(
        {"calendar_range", "quantity_control", "owner_collection", "color_target"}
    ),
)


def _authored_adapter() -> DomAdapter:
    return DomAdapter(extension=_AUTHORED_EXTENSION)


def test_dom_adapter_extracts_interactables_with_leases() -> None:
    html = """
    <html><head><style>.x{}</style></head><body>
      <button id="save">Save</button>
      <input name="email" placeholder="Email" />
      <script>ignore()</script>
    </body></html>
    """

    model = DomAdapter().transduce(html, environment_revision="rev-1", url="https://example.test")

    assert model.raw_node_count >= 2
    assert model.kept_node_count == 2
    assert [item.label for item in model.affordances] == ["Save", "Email"]
    assert all(item.lease.environment_revision == "rev-1" for item in model.affordances)


def test_dom_adapter_preserves_authored_backend_handle_alongside_stable_selector() -> None:
    model = _authored_adapter().transduce(
        '<input id="field" data-runtime-handle="field-handle" aria-label="Name">',
        environment_revision="rev-1",
    )

    assert model.affordances[0].locator == {
        "selector": "#field",
        "strategy": "css",
        "backend_handle": "field-handle",
    }


def test_dom_adapter_does_not_enable_unknown_authored_markers_without_profile() -> None:
    html = (
        '<span data-runtime-handle="custom" data-runtime-interactive="1">Custom</span>'
        '<button id="native">Native</button>'
    )

    model = DomAdapter().transduce(html, environment_revision="rev-1")

    assert [(item.label, item.action) for item in model.affordances] == [("Native", "click")]


def test_dom_adapter_exposes_authored_marked_custom_controls() -> None:
    model = _authored_adapter().transduce(
        '<span class="alink" data-runtime-handle="link-1" data-runtime-interactive="1">Open report</span>'
        '<span data-runtime-handle="plain">not actionable</span>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.label, item.action, item.locator["backend_handle"]) for item in model.affordances] == [
        ("button", "Open report", "click", "link-1"),
    ]


def test_dom_adapter_exposes_generic_draggable_controls() -> None:
    model = _authored_adapter().transduce(
        '<li data-runtime-handle="source" class="ui-sortable-handle" value="0">Source</li>'
        '<li data-runtime-handle="destination" draggable="true">Destination</li>'
        '<div data-runtime-handle="jquery" class="ui-draggable ui-draggable-handle">JQuery drag</div>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [
        ("Source", "drag"),
        ("Destination", "drag"),
        ("JQuery drag", "drag"),
    ]


def test_dom_adapter_exposes_authored_calendar_slots_as_distinct_range_endpoints() -> None:
    html = (
        '<div class="hour" data-hour="12" data-runtime-visibility="0">'
        '<span class="calendar">'
        '<div class="half-hour" id="hh-24" data-runtime-handle="slot-24"></div>'
        '<div class="half-hour" id="hh-25" data-runtime-handle="slot-25"></div>'
        "</span></div>"
    )

    assert _authored_adapter().transduce(html, environment_revision="rev-1").affordances == []
    model = _authored_adapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

    assert [(item.label, item.action, item.locator["backend_handle"]) for item in model.affordances] == [
        ("12:00pm calendar slot", "drag", "slot-24"),
        ("12:00pm calendar slot end boundary", "drop", "slot-24"),
        ("12:30pm calendar slot", "drag", "slot-25"),
        ("12:30pm calendar slot end boundary", "drop", "slot-25"),
    ]
    source, destination = model.affordances[:2]
    assert source.id != destination.id
    assert source.state["calendar_slot_index"] == destination.state["calendar_slot_index"] == 24
    assert source.state["calendar_endpoint"] == "start"
    assert destination.state["calendar_endpoint"] == "end"
    assert source.state["accepts_drop"] is False
    assert destination.state["accepts_drop"] is True


def test_dom_adapter_marks_download_links_as_download_actions() -> None:
    model = _authored_adapter().transduce(
        '<a id="export" href="/report.csv" download="report.csv">Export report</a>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "download"


def test_dom_adapter_preserves_native_select_ownership_for_option_semantics() -> None:
    model = _authored_adapter().transduce(
        '<select data-runtime-handle="select-bid" data-runtime-interactive="1">'
        '<option data-runtime-handle="option-bid" value="earth">Earth</option></select>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "select"
    assert model.affordances[0].role == "combobox"
    option = model.affordances[1]
    assert option.action == "click"
    assert option.role == "option"
    assert option.locator["select_owner_backend_handle"] == "select-bid"
    assert option.locator["select_option"] == "earth"


def test_dom_adapter_exposes_focusable_controls_as_keyboard_affordances() -> None:
    model = _authored_adapter().transduce(
        '<span data-runtime-handle="slider" class="ui-slider-handle" tabindex="0"></span>',
        environment_revision="rev-1",
    )

    affordance = model.affordances[0]
    assert affordance.label == "ui-slider-handle"
    assert affordance.action == "press"
    assert affordance.locator["backend_handle"] == "slider"


def test_dom_adapter_exposes_all_aria_tabs_as_typed_disclosures_independent_of_roving_focus() -> None:
    model = _authored_adapter().transduce(
        '<h3 id="first" role="tab" tabindex="0" aria-expanded="false" aria-controls="panel-1" '
        'data-runtime-handle="first">First</h3>'
        '<h3 id="second" role="tab" tabindex="-1" aria-expanded="true" aria-controls="panel-2" '
        'data-runtime-handle="second">Second</h3>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [
        ("First", "click"),
        ("Second", "click"),
    ]
    assert model.affordances[0].state | {"visible": True} == {
        "enabled": True,
        "visible": True,
        "element_tag": "h3",
        "disclosure": True,
        "expanded": False,
        "aria_expanded": "false",
        "aria_controls": "panel-1",
    }
    assert model.affordances[1].state["expanded"] is True
    assert [item.locator["backend_handle"] for item in model.affordances] == ["first", "second"]


def test_dom_adapter_preserves_concise_nearby_visible_text_for_focusable_controls() -> None:
    model = _authored_adapter().transduce(
        '<div><div id="slider"><span data-runtime-handle="slider" tabindex="0"></span></div><div>-1</div></div>',
        environment_revision="rev-1",
    )

    affordance = model.affordances[0]
    assert affordance.state["context_text"] == "-1"


def test_dom_adapter_does_not_duplicate_container_text_on_native_controls() -> None:
    model = _authored_adapter().transduce(
        "<div><button>Save</button><div>untrusted container text</div></div>",
        environment_revision="rev-1",
    )

    assert "context_text" not in model.affordances[0].state


def test_dom_adapter_merges_a_nested_label_into_its_checkbox_control() -> None:
    model = _authored_adapter().transduce(
        '<label data-runtime-handle="label-bid"><input id="choice" data-runtime-handle="input-bid" type="checkbox" value="on">Nb</label>'
        "<button>Submit</button>",
        environment_revision="rev-1",
    )

    assert [(item.role, item.label) for item in model.affordances] == [
        ("checkbox", "Nb"),
        ("button", "Submit"),
    ]
    assert model.affordances[0].locator["backend_handle"] == "input-bid"


def test_dom_adapter_associates_adjacent_labels_without_exposing_proxy_actions() -> None:
    model = _authored_adapter().transduce(
        '<p><label data-runtime-handle="label-1" data-runtime-interactive="1">Password</label>'
        '<input id="password" data-runtime-handle="input-1" type="password"></p>'
        '<p><label data-runtime-handle="label-2" data-runtime-interactive="1">Verify password</label>'
        '<input id="verify" data-runtime-handle="input-2" type="password"></p>'
        '<button data-runtime-handle="submit">Submit</button>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.label, item.action) for item in model.affordances] == [
        ("textbox", "Password", "type"),
        ("textbox", "Verify password", "type"),
        ("button", "Submit", "click"),
    ]
    assert [item.state.get("label_source") for item in model.affordances[:2]] == [
        "native_label",
        "native_label",
    ]


def test_dom_adapter_requires_independent_semantics_for_marked_descriptive_tags() -> None:
    model = _authored_adapter().transduce(
        '<label role="button" data-runtime-handle="role-label" data-runtime-interactive="1">Open chooser</label>'
        '<form data-runtime-handle="marked-form" data-runtime-interactive="1">Form text</form>'
        '<span data-runtime-handle="custom" data-runtime-interactive="1">Custom control</span>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [
        ("Open chooser", "click"),
        ("Custom control", "click"),
    ]


def test_dom_adapter_distinguishes_radio_and_textbox_roles() -> None:
    model = _authored_adapter().transduce(
        '<input type="radio" value="1"><input type="text" id="answer">',
        environment_revision="rev-1",
    )

    assert [item.role for item in model.affordances] == ["radio", "textbox"]


def test_dom_adapter_preserves_native_input_type_for_contract_binding() -> None:
    model = _authored_adapter().transduce('<input data-runtime-handle="date" type="date">', environment_revision="rev-1")

    assert model.affordances[0].state["input_type"] == "date"


def test_dom_adapter_exposes_readonly_picker_input_as_activation() -> None:
    model = _authored_adapter().transduce(
        '<input data-runtime-handle="date" id="datepicker" type="text" readonly>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "click"
    assert model.affordances[0].role == "picker"
    assert model.affordances[0].state["readonly"] is True
    assert model.affordances[0].state["element_tag"] == "input"


def test_dom_adapter_exposes_autocomplete_options_without_label_or_menu_container_noise() -> None:
    model = _authored_adapter().transduce(
        '<label for="tags" data-runtime-handle="label">Tags:</label>'
        '<input id="tags" data-runtime-handle="input" class="ui-autocomplete-input">'
        '<button data-runtime-handle="submit">Submit</button>'
        '<ul id="menu" data-runtime-handle="menu" tabindex="0"><li><div data-runtime-handle="option" tabindex="-1">Colombia</div></li></ul>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.label, item.action) for item in model.affordances] == [
        ("textbox", "Tags:", "type"),
        ("button", "Submit", "click"),
        ("option", "Colombia", "click"),
    ]
    assert model.affordances[0].state["label_source"] == "native_label"
    assert model.affordances[0].state["autocomplete"] is True
    assert model.affordances[-1].state["programmatic_option"] is True


def test_dom_adapter_omits_hidden_focusable_menu_containers() -> None:
    model = _authored_adapter().transduce(
        '<input id="tags" class="ui-autocomplete-input">'
        '<ul data-runtime-handle="menu" tabindex="0" style="display: none"><li><div data-runtime-handle="option" tabindex="-1">Hidden</div></li></ul>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.action) for item in model.affordances] == [("textbox", "type")]


def test_dom_adapter_honors_authored_rendered_visibility_annotations() -> None:
    model = _authored_adapter().transduce(
        '<div data-runtime-visibility="0">'
        '<input data-runtime-handle="hidden" id="search-input" data-runtime-visibility="1">'
        "</div>"
        '<button data-runtime-handle="visible" data-runtime-visibility="1">Open search</button>',
        environment_revision="rev-1",
    )

    assert [item.label for item in model.affordances] == ["Open search"]


def test_dom_adapter_keeps_hidden_native_select_as_programmatic_semantic_control() -> None:
    model = _authored_adapter().transduce(
        '<select data-runtime-handle="dropdown" id="height" data-runtime-visibility="0">'
        '<option data-runtime-visibility="0">5ft 10in</option>'
        "</select>"
        '<input data-runtime-handle="hidden" data-runtime-visibility="0">',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [("5ft 10in", "select")]
    assert model.affordances[0].state["programmatic_select"] is True
    assert model.affordances[0].state["rendered_visible"] is False


def test_dom_adapter_text_input_identity_does_not_change_with_mutable_value() -> None:
    empty = _authored_adapter().transduce(
        '<input data-runtime-handle="search" id="search-text" value="">',
        environment_revision="rev-1",
    )
    filled = _authored_adapter().transduce(
        '<input data-runtime-handle="search" id="search-text" value="Kasie">',
        environment_revision="rev-2",
    )

    assert empty.affordances[0].label == filled.affordances[0].label == "search-text"


def test_dom_adapter_preserves_link_role_and_bounded_container_context() -> None:
    model = _authored_adapter().transduce(
        '<div><a data-runtime-handle="result">Ada</a><div>https://example.test</div><div>Result summary</div></div>',
        environment_revision="rev-1",
    )

    result = model.affordances[0]
    assert result.role == "link"
    assert result.state["container_context"] == "Ada https://example.test Result summary"


def test_dom_adapter_does_not_bind_native_button_identity_to_mutable_siblings() -> None:
    model = _authored_adapter().transduce(
        '<div><button data-runtime-handle="search">Search</button><div>Changing results</div></div>',
        environment_revision="rev-1",
    )

    assert "container_context" not in model.affordances[0].state


def test_dom_adapter_normalizes_collection_positions() -> None:
    model = _authored_adapter().transduce(
        '<a data-result="2">third</a><button aria-posinset="4">fourth</button>',
        environment_revision="rev-1",
    )

    assert [item.state["collection_position"] for item in model.affordances] == [3, 4]


def test_dom_adapter_inherits_collection_position_from_structural_ancestor() -> None:
    model = _authored_adapter().transduce(
        '<div data-result="3"><a data-runtime-handle="result">Ashlea</a></div>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].state["collection_position"] == 4


def test_dom_adapter_exposes_semantically_coloured_rendered_targets() -> None:
    model = _authored_adapter().transduce(
        '<div id="query-color" class="color"></div>'
        '<div class="color" data-color="olive" style="background-color: olive" data-runtime-handle="13"></div>'
        '<div class="color" data-color="yellow" style="background-color: yellow" data-runtime-handle="14"></div>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [
        ("olive", "click"),
        ("yellow", "click"),
    ]
    assert model.affordances[0].locator["backend_handle"] == "13"
    assert model.affordances[0].state["observed_color"] == "olive"


def test_dom_adapter_exposes_authored_offscreen_quantity_controls_with_state_identity() -> None:
    html = (
        '<div class="food-item" data-item="Peanut bowl" data-quantity="0" '
        'data-runtime-visibility="0">'
        '<img alt="peanuts"><span class="add" data-runtime-handle="add" data-runtime-visibility="0">+</span>'
        "</div>"
        '<button data-runtime-handle="order" data-runtime-visibility="0">Order!</button>'
    )
    model = _authored_adapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

    assert [(item.label, item.action) for item in model.affordances] == [
        ("increase Peanut bowl quantity", "click"),
        ("Order!", "click"),
    ]
    quantity = model.affordances[0]
    assert quantity.state["item_name"] == "Peanut bowl"
    assert quantity.state["item_types"] == ["peanuts"]
    assert quantity.state["current_quantity"] == 0
    assert quantity.state["quantity_delta"] == 1
    assert quantity.state["repeatable"] is True

    updated = _authored_adapter().transduce(
        html.replace('data-quantity="0"', 'data-quantity="1"'),
        environment_revision="rev-2",
        allow_offscreen=True,
    )
    assert updated.affordances[0].id == quantity.id
    assert updated.page_revision != model.page_revision
    assert updated.affordances[0].target_fingerprint != quantity.target_fingerprint


def test_dom_adapter_exposes_only_structurally_coherent_calendar_boundaries() -> None:
    model = _authored_adapter().transduce(
        '<div class="hour" data-hour="12"><span class="hour-label">12pm</span>'
        '<span class="calendar"><div id="hh-24" class="half-hour" data-runtime-handle="start"></div>'
        '<div id="hh-25" class="half-hour" data-runtime-handle="half"></div></span></div>'
        '<div class="hour" data-hour="4"><span class="calendar">'
        '<div id="hh-24" class="half-hour" data-runtime-handle="mismatch"></div></span></div>'
        '<div id="hh-26" class="half-hour" data-runtime-handle="unowned"></div>',
        environment_revision="rev-1",
        allow_offscreen=True,
    )

    assert [(item.label, item.action, item.role) for item in model.affordances] == [
        ("12:00pm calendar slot", "drag", "time_slot"),
        ("12:00pm calendar slot end boundary", "drop", "time_slot_end"),
        ("12:30pm calendar slot", "drag", "time_slot"),
        ("12:30pm calendar slot end boundary", "drop", "time_slot_end"),
    ]
    assert [item.state["calendar_slot_index"] for item in model.affordances] == [24, 24, 25, 25]
    assert model.affordances[0].state["accepts_drop"] is False
    assert model.affordances[1].state["accepts_drop"] is True
    assert model.affordances[0].locator["backend_handle"] == model.affordances[1].locator["backend_handle"] == "start"


def test_dom_adapter_exposes_owner_scoped_collection_actions_without_admitting_hidden_menu() -> None:
    html = (
        '<div class="media" data-result="2" data-runtime-handle="item">'
        '<div class="details"><span class="username">@alice</span></div>'
        '<div class="body">current post</div><div class="controls">'
        '<span class="like active" data-runtime-handle="like" data-runtime-visibility="0"></span>'
        '<span class="more" data-runtime-handle="more" data-runtime-visibility="0"></span>'
        '<span><ul class="hide"><li class="share" data-runtime-handle="share">Share via DM</li></ul></span>'
        "</div></div>"
    )

    model = _authored_adapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

    assert [(item.label, item.action) for item in model.affordances] == [
        ("Like", "click"),
        ("More", "click"),
    ]
    assert model.affordances[0].state["collection_position"] == 3
    assert model.affordances[0].state["collection_action"] == "Like"
    assert model.affordances[0].state["collection_owner"] == "@alice"
    assert model.affordances[0].state["toggle_selected"] is True


def test_dom_adapter_exposes_visible_owner_scoped_collection_menu_item() -> None:
    html = (
        '<div class="media" data-result="0"><span class="username">@alice</span>'
        '<div class="controls"><span><ul>'
        '<li class="share" data-runtime-handle="share">Share via DM</li>'
        "</ul></span></div></div>"
        '<div class="controls"><span class="like" data-runtime-handle="unowned"></span></div>'
    )

    model = _authored_adapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

    assert len(model.affordances) == 1
    assert model.affordances[0].label == "Share via DM"
    assert model.affordances[0].state["collection_owner"] == "@alice"
    assert model.affordances[0].state["collection_position"] == 1
