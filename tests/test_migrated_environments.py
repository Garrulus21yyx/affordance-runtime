import json
from pathlib import Path

import pytest

from affordance_runtime.surfaces.wot.thing_description import WotAdapter
from affordance_runtime.testing.failure_injection import FAILURE_CATALOGUE, failure_spec

ROOT = Path(__file__).resolve().parents[1]
SMART_ROOM = ROOT / "environments" / "smart_room"
MOCK_WEB = ROOT / "environments" / "mock_web"


def test_smart_room_compose_build_contexts_and_runtime_assets_exist() -> None:
    compose = (SMART_ROOM / "docker-compose.yml").read_text(encoding="utf-8")

    assert "build: ./node_wot_server" in compose
    assert "build: ./react_dashboard" in compose
    assert "container_name:" not in compose
    assert "SMART_ROOM_WOT_PORT" in compose
    assert (SMART_ROOM / "node_wot_server" / "server.js").is_file()
    assert (SMART_ROOM / "react_dashboard" / "src" / "App.jsx").is_file()
    assert (SMART_ROOM / "node_wot_server" / "package-lock.json").is_file()
    assert (SMART_ROOM / "react_dashboard" / "package-lock.json").is_file()
    assert "npm ci" in (SMART_ROOM / "node_wot_server" / "Dockerfile").read_text(encoding="utf-8")
    assert "npm ci" in (SMART_ROOM / "react_dashboard" / "Dockerfile").read_text(encoding="utf-8")


def test_thermostat_postcondition_mismatch_keeps_related_state_atomic() -> None:
    server = (SMART_ROOM / "node_wot_server" / "server.js").read_text(encoding="utf-8")

    assert 'return false;' in server
    assert 'if (!applyWrite("thermostat", "targetTemperature", v)) return undefined;' in server


def test_all_migrated_td_fixtures_parse_into_source_local_models() -> None:
    paths = sorted((SMART_ROOM / "wot_td").glob("*.td.json"))
    assert len(paths) == 5

    models = [
        WotAdapter().parse(json.loads(path.read_text(encoding="utf-8")), environment_revision="fixture-v1")
        for path in paths
    ]

    assert {model.thing_id for model in models} == {
        "blinds_A",
        "lights_A",
        "occupancy_A",
        "projector_A",
        "thermostat_A",
    }
    assert all(model.state_sources for model in models)


def test_mock_web_task_oracles_reference_real_page_markers() -> None:
    tasks = json.loads((MOCK_WEB / "tasks.json").read_text(encoding="utf-8"))

    assert {task["task_id"] for task in tasks} == {
        "mock-shopping-checkout",
        "mock-email-reply",
        "mock-forum-post",
    }
    for task in tasks:
        page = (MOCK_WEB / task["page"]).read_text(encoding="utf-8")
        selector = task["success"]["selector"]
        assert selector.startswith("#")
        assert f'id="{selector[1:]}"' in page
        assert task["forbidden_side_effects"]


def test_failure_catalogue_describes_observable_outcomes_not_recovery_tiers() -> None:
    assert len(FAILURE_CATALOGUE) >= 8
    assert failure_spec("wot_timeout").expected_evaluation == "post_state_required"
    assert all(not hasattr(item, "expected_tier") for item in FAILURE_CATALOGUE)

    with pytest.raises(KeyError):
        failure_spec("unknown")
