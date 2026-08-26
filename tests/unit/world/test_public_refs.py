import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.world.public_refs import (
    PublicRefCodec,
    PublicRefKind,
)


@given(st.sampled_from(tuple(PublicRefKind)), st.integers(min_value=1, max_value=10**30))
def test_public_ref_codec_round_trips_every_supported_kind_and_index(kind, index) -> None:
    encoded = PublicRefCodec.encode(kind, index)

    assert PublicRefCodec.decode(encoded, expected=kind).index == index
    assert PublicRefCodec.accepts(encoded, expected=kind)


def test_public_ref_codec_accepts_positive_ordinals_without_a_smaller_world_capacity() -> None:
    assert PublicRefCodec.accepts("E999")
    assert PublicRefCodec.accepts("E1000")
    assert PublicRefCodec.accepts("E9999")
    assert PublicRefCodec.accepts("E10000")
    assert PublicRefCodec.accepts("F1000000000000000000000000000000")
    for invalid in ("E0", "E01", "N0001", "X1", "E1x", ""):
        assert not PublicRefCodec.accepts(invalid)
    for invalid_index in (True, 0, -1, 1.0):
        with pytest.raises(ValueError, match="index"):
            PublicRefCodec.encode(PublicRefKind.EXECUTABLE, invalid_index)
