from __future__ import annotations

import pytest

from affordance_runtime.world.page_cursor import (
    DeliveryCursorMode,
    DeliveryCursorPosition,
    decode_delivery_cursor,
    encode_delivery_cursor,
)


@pytest.mark.parametrize(
    "position",
    (
        DeliveryCursorPosition(DeliveryCursorMode.ITEMS, 7),
        DeliveryCursorPosition(DeliveryCursorMode.DETAIL, 3, 2, 4096, 128),
    ),
)
def test_delivery_cursor_round_trips_typed_position(position: DeliveryCursorPosition) -> None:
    cursor = encode_delivery_cursor(position, "fingerprint:current")

    assert decode_delivery_cursor(cursor, "fingerprint:current") == position


def test_delivery_cursor_fails_closed_across_streams_and_tampering() -> None:
    cursor = encode_delivery_cursor(
        DeliveryCursorPosition(DeliveryCursorMode.DETAIL, 1, 0, 128, 128),
        "fingerprint:before",
    )

    with pytest.raises(ValueError, match="malformed"):
        decode_delivery_cursor(cursor, "fingerprint:after")
    with pytest.raises(ValueError, match="malformed"):
        decode_delivery_cursor(cursor[:-2] + "xx", "fingerprint:before")


def test_item_cursor_cannot_smuggle_detail_state() -> None:
    with pytest.raises(ValueError, match="cannot carry detail"):
        DeliveryCursorPosition(DeliveryCursorMode.ITEMS, 1, detail_offset=1)
