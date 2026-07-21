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


def test_dom_adapter_marks_download_links_as_download_actions() -> None:
    model = DomAdapter().transduce(
        '<a id="export" href="/report.csv" download="report.csv">Export report</a>',
        environment_revision="rev-1",
    )

    assert model.affordances[0].action == "download"


def test_dom_adapter_preserves_native_select_ownership_for_option_semantics() -> None:
    model = DomAdapter().transduce(
        '<select bid="select-bid"><option bid="option-bid" value="earth">Earth</option></select>',
        environment_revision="rev-1",
    )

    option = model.affordances[1]
    assert option.action == "click"
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
