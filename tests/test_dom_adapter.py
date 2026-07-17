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

