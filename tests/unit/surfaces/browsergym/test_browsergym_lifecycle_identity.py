import pytest

from affordance_runtime.surfaces.browsergym.lifecycle_identity import episode_identity


def test_episode_identity_prefers_browsergym_value() -> None:
    assert episode_identity({"EPISODE_ID": 42}, fallback="run:fallback") == "42"


def test_episode_identity_uses_explicit_fallback_for_official_tasks_without_episode_id() -> None:
    assert episode_identity({}, fallback="run:local") == "run:local"


def test_episode_identity_still_fails_closed_without_fallback() -> None:
    with pytest.raises(RuntimeError, match="omitted episode identity"):
        episode_identity({})
