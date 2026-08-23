import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.world.public_refs import (
    PUBLIC_REF_MAX_INDEX,
    PublicRefCodec,
    PublicRefKind,
)


@given(st.sampled_from(tuple(PublicRefKind)), st.integers(min_value=1, max_value=PUBLIC_REF_MAX_INDEX))
def test_public_ref_codec_round_trips_every_supported_kind_and_index(kind, index) -> None:
    encoded = PublicRefCodec.encode(kind, index)

    assert PublicRefCodec.decode(encoded, expected=kind).index == index
    assert PublicRefCodec.accepts(encoded, expected=kind)


def test_public_ref_codec_has_one_shared_e999_e1000_capacity_boundary() -> None:
    assert PublicRefCodec.accepts("E999")
    assert PublicRefCodec.accepts("E1000")
    assert PublicRefCodec.accepts("E9999")
    for invalid in ("E0", "E01", "E10000", "N0001", "X1", "E1x", ""):
        assert not PublicRefCodec.accepts(invalid)
    with pytest.raises(ValueError, match="capacity"):
        PublicRefCodec.encode(PublicRefKind.EXECUTABLE, PUBLIC_REF_MAX_INDEX + 1)

