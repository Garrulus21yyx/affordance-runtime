from affordance_runtime.trace import JsonlTraceWriter, TraceDag


def test_jsonl_trace_writer_round_trips_events(tmp_path) -> None:
    trace = TraceDag("run-1")
    root = trace.add("observation", {"revision": "rev-1"})
    trace.add("contract", {"id": "contract-1"}, parents=[root.id])
    writer = JsonlTraceWriter(tmp_path / "run-1" / "events.jsonl")

    path = writer.write(trace)
    rows = writer.read()

    assert path.exists()
    assert [row["sequence"] for row in rows] == [0, 1]
    assert rows[1]["parent_event_ids"] == [root.id]


def test_trace_rejects_unknown_parent() -> None:
    trace = TraceDag("run-1")
    try:
        trace.add("contract", {}, parents=["missing"])
    except ValueError as exc:
        assert "parent does not exist" in str(exc)
    else:
        raise AssertionError("unknown trace parent should be rejected")
