from affordance_runtime.adapters.dom import DomAdapter


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


def test_dom_adapter_preserves_browsergym_bid_alongside_stable_selector() -> None:
    model = DomAdapter().transduce(
        '<input id="field" bid="browsergym-field" aria-label="Name">',
        environment_revision="rev-1",
    )

    assert model.affordances[0].locator == {
        "selector": "#field",
        "strategy": "css",
        "bid": "browsergym-field",
    }


def test_dom_adapter_exposes_browsergym_marked_custom_controls() -> None:
    model = DomAdapter().transduce(
        '<span class="alink" bid="link-1" browsergym_set_of_marks="1">Open report</span>'
        '<span bid="plain">not actionable</span>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.label, item.action, item.locator["bid"]) for item in model.affordances] == [
        ("button", "Open report", "click", "link-1"),
    ]


def test_dom_adapter_exposes_generic_draggable_controls() -> None:
    model = DomAdapter().transduce(
        '<li bid="source" class="ui-sortable-handle" value="0">Source</li>'
        '<li bid="destination" draggable="true">Destination</li>'
        '<div bid="jquery" class="ui-draggable ui-draggable-handle">JQuery drag</div>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [
        ("Source", "drag"),
        ("Destination", "drag"),
        ("JQuery drag", "drag"),
    ]


def test_dom_adapter_exposes_authored_calendar_slots_as_distinct_range_endpoints() -> None:
    html = (
        '<div class="hour" data-hour="12" browsergym_visibility_ratio="0">'
        '<span class="calendar">'
        '<div class="half-hour" id="hh-24" bid="slot-24"></div>'
        '<div class="half-hour" id="hh-25" bid="slot-25"></div>'
        "</span></div>"
    )

    assert DomAdapter().transduce(html, environment_revision="rev-1").affordances == []
    model = DomAdapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

    assert [(item.label, item.action, item.locator["bid"]) for item in model.affordances] == [
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
    model = DomAdapter().transduce(
        '<a id="export" href="/report.csv" download="report.csv">Export report</a>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "download"


def test_dom_adapter_preserves_native_select_ownership_for_option_semantics() -> None:
    model = DomAdapter().transduce(
        '<select bid="select-bid" browsergym_set_of_marks="1">'
        '<option bid="option-bid" value="earth">Earth</option></select>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "select"
    assert model.affordances[0].role == "combobox"
    option = model.affordances[1]
    assert option.action == "click"
    assert option.role == "option"
    assert option.locator["select_owner_bid"] == "select-bid"
    assert option.locator["select_option"] == "earth"


def test_dom_adapter_exposes_focusable_controls_as_keyboard_affordances() -> None:
    model = DomAdapter().transduce(
        '<span bid="slider" class="ui-slider-handle" tabindex="0"></span>',
        environment_revision="rev-1",
    )

    affordance = model.affordances[0]
    assert affordance.label == "ui-slider-handle"
    assert affordance.action == "press"
    assert affordance.locator["bid"] == "slider"


def test_dom_adapter_preserves_concise_nearby_visible_text_for_focusable_controls() -> None:
    model = DomAdapter().transduce(
        '<div><div id="slider"><span bid="slider" tabindex="0"></span></div><div>-1</div></div>',
        environment_revision="rev-1",
    )

    affordance = model.affordances[0]
    assert affordance.state["context_text"] == "-1"


def test_dom_adapter_does_not_duplicate_container_text_on_native_controls() -> None:
    model = DomAdapter().transduce(
        "<div><button>Save</button><div>untrusted container text</div></div>",
        environment_revision="rev-1",
    )

    assert "context_text" not in model.affordances[0].state


def test_dom_adapter_merges_a_nested_label_into_its_checkbox_control() -> None:
    model = DomAdapter().transduce(
        '<label bid="label-bid"><input id="choice" bid="input-bid" type="checkbox" value="on">Nb</label>'
        "<button>Submit</button>",
        environment_revision="rev-1",
    )

    assert [(item.role, item.label) for item in model.affordances] == [
        ("checkbox", "Nb"),
        ("button", "Submit"),
    ]
    assert model.affordances[0].locator["bid"] == "input-bid"


def test_dom_adapter_distinguishes_radio_and_textbox_roles() -> None:
    model = DomAdapter().transduce(
        '<input type="radio" value="1"><input type="text" id="answer">',
        environment_revision="rev-1",
    )

    assert [item.role for item in model.affordances] == ["radio", "textbox"]


def test_dom_adapter_preserves_native_input_type_for_contract_binding() -> None:
    model = DomAdapter().transduce('<input bid="date" type="date">', environment_revision="rev-1")

    assert model.affordances[0].state["input_type"] == "date"


def test_dom_adapter_exposes_readonly_picker_input_as_activation() -> None:
    model = DomAdapter().transduce(
        '<input bid="date" id="datepicker" type="text" readonly>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "click"
    assert model.affordances[0].role == "picker"
    assert model.affordances[0].state["readonly"] is True
    assert model.affordances[0].state["element_tag"] == "input"


def test_dom_adapter_exposes_autocomplete_options_without_label_or_menu_container_noise() -> None:
    model = DomAdapter().transduce(
        '<label for="tags" bid="label">Tags:</label>'
        '<input id="tags" bid="input" class="ui-autocomplete-input">'
        '<button bid="submit">Submit</button>'
        '<ul id="menu" bid="menu" tabindex="0"><li><div bid="option" tabindex="-1">Colombia</div></li></ul>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.label, item.action) for item in model.affordances] == [
        ("textbox", "tags", "type"),
        ("button", "Submit", "click"),
        ("option", "Colombia", "click"),
    ]
    assert model.affordances[0].state["autocomplete"] is True
    assert model.affordances[-1].state["programmatic_option"] is True


def test_dom_adapter_omits_hidden_focusable_menu_containers() -> None:
    model = DomAdapter().transduce(
        '<input id="tags" class="ui-autocomplete-input">'
        '<ul bid="menu" tabindex="0" style="display: none"><li><div bid="option" tabindex="-1">Hidden</div></li></ul>',
        environment_revision="rev-1",
    )

    assert [(item.role, item.action) for item in model.affordances] == [("textbox", "type")]


def test_dom_adapter_honors_browsergym_rendered_visibility_annotations() -> None:
    model = DomAdapter().transduce(
        '<div browsergym_visibility_ratio="0">'
        '<input bid="hidden" id="search-input" browsergym_visibility_ratio="1">'
        "</div>"
        '<button bid="visible" browsergym_visibility_ratio="1">Open search</button>',
        environment_revision="rev-1",
    )

    assert [item.label for item in model.affordances] == ["Open search"]


def test_dom_adapter_keeps_hidden_native_select_as_programmatic_semantic_control() -> None:
    model = DomAdapter().transduce(
        '<select bid="dropdown" id="height" browsergym_visibility_ratio="0">'
        '<option browsergym_visibility_ratio="0">5ft 10in</option>'
        "</select>"
        '<input bid="hidden" browsergym_visibility_ratio="0">',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [("5ft 10in", "select")]
    assert model.affordances[0].state["programmatic_select"] is True
    assert model.affordances[0].state["rendered_visible"] is False


def test_dom_adapter_text_input_identity_does_not_change_with_mutable_value() -> None:
    empty = DomAdapter().transduce(
        '<input bid="search" id="search-text" value="">',
        environment_revision="rev-1",
    )
    filled = DomAdapter().transduce(
        '<input bid="search" id="search-text" value="Kasie">',
        environment_revision="rev-2",
    )

    assert empty.affordances[0].label == filled.affordances[0].label == "search-text"


def test_dom_adapter_preserves_link_role_and_bounded_container_context() -> None:
    model = DomAdapter().transduce(
        '<div><a bid="result">Ada</a><div>https://example.test</div><div>Result summary</div></div>',
        environment_revision="rev-1",
    )

    result = model.affordances[0]
    assert result.role == "link"
    assert result.state["container_context"] == "Ada https://example.test Result summary"


def test_dom_adapter_does_not_bind_native_button_identity_to_mutable_siblings() -> None:
    model = DomAdapter().transduce(
        '<div><button bid="search">Search</button><div>Changing results</div></div>',
        environment_revision="rev-1",
    )

    assert "container_context" not in model.affordances[0].state


def test_dom_adapter_normalizes_collection_positions() -> None:
    model = DomAdapter().transduce(
        '<a data-result="2">third</a><button aria-posinset="4">fourth</button>',
        environment_revision="rev-1",
    )

    assert [item.state["collection_position"] for item in model.affordances] == [3, 4]


def test_dom_adapter_exposes_semantically_coloured_rendered_targets() -> None:
    model = DomAdapter().transduce(
        '<div id="query-color" class="color"></div>'
        '<div class="color" data-color="olive" style="background-color: olive" bid="13"></div>'
        '<div class="color" data-color="yellow" style="background-color: yellow" bid="14"></div>',
        environment_revision="rev-1",
    )

    assert [(item.label, item.action) for item in model.affordances] == [
        ("olive", "click"),
        ("yellow", "click"),
    ]
    assert model.affordances[0].locator["bid"] == "13"
    assert model.affordances[0].state["observed_color"] == "olive"


def test_dom_adapter_exposes_authored_offscreen_quantity_controls_with_state_identity() -> None:
    html = (
        '<div class="food-item" data-item="Peanut bowl" data-quantity="0" '
        'browsergym_visibility_ratio="0">'
        '<img alt="peanuts"><span class="add" bid="add" browsergym_visibility_ratio="0">+</span>'
        "</div>"
        '<button bid="order" browsergym_visibility_ratio="0">Order!</button>'
    )
    model = DomAdapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

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

    updated = DomAdapter().transduce(
        html.replace('data-quantity="0"', 'data-quantity="1"'),
        environment_revision="rev-2",
        allow_offscreen=True,
    )
    assert updated.affordances[0].id == quantity.id
    assert updated.page_revision != model.page_revision
    assert updated.affordances[0].target_fingerprint != quantity.target_fingerprint


def test_dom_adapter_exposes_only_structurally_coherent_calendar_boundaries() -> None:
    model = DomAdapter().transduce(
        '<div class="hour" data-hour="12"><span class="hour-label">12pm</span>'
        '<span class="calendar"><div id="hh-24" class="half-hour" bid="start"></div>'
        '<div id="hh-25" class="half-hour" bid="half"></div></span></div>'
        '<div class="hour" data-hour="4"><span class="calendar">'
        '<div id="hh-24" class="half-hour" bid="mismatch"></div></span></div>'
        '<div id="hh-26" class="half-hour" bid="unowned"></div>',
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
    assert model.affordances[0].locator["bid"] == model.affordances[1].locator["bid"] == "start"


def test_dom_adapter_exposes_owner_scoped_collection_actions_without_admitting_hidden_menu() -> None:
    html = (
        '<div class="media" data-result="2" bid="item">'
        '<div class="details"><span class="username">@alice</span></div>'
        '<div class="body">current post</div><div class="controls">'
        '<span class="like active" bid="like" browsergym_visibility_ratio="0"></span>'
        '<span class="more" bid="more" browsergym_visibility_ratio="0"></span>'
        '<span><ul class="hide"><li class="share" bid="share">Share via DM</li></ul></span>'
        "</div></div>"
    )

    model = DomAdapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

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
        '<li class="share" bid="share">Share via DM</li>'
        "</ul></span></div></div>"
        '<div class="controls"><span class="like" bid="unowned"></span></div>'
    )

    model = DomAdapter().transduce(html, environment_revision="rev-1", allow_offscreen=True)

    assert len(model.affordances) == 1
    assert model.affordances[0].label == "Share via DM"
    assert model.affordances[0].state["collection_owner"] == "@alice"
    assert model.affordances[0].state["collection_position"] == 1
