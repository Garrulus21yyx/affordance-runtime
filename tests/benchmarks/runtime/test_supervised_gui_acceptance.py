from __future__ import annotations

import json
from pathlib import Path

from affordance_runtime.benchmarks.supervised_gui_acceptance import (
    DEFAULT_FIXTURE_ROOT,
    preflight_public_shadow,
    supervised_gui_acceptance_manifest,
    supervised_gui_acceptance_manifest_digest,
)


def test_committed_supervised_gui_manifest_matches_typed_contract() -> None:
    committed = json.loads(
        Path("docs/benchmarks/supervised-gui-acceptance-v1.json").read_text(encoding="utf-8")
    )

    assert committed == {
        **supervised_gui_acceptance_manifest(),
        "manifest_digest": supervised_gui_acceptance_manifest_digest(),
    }
    assert committed["production_specialization_prohibited"] is True
    assert committed["controlled"]["content_filter_profile"] == "off"
    assert committed["controlled"]["agent_calls"] == 0
    assert committed["controlled"]["visual_provider_calls"] == 0
    assert committed["public_shadow"]["required_content_filter_profile"] == "ads_and_cosmetic.v1"
    assert committed["public_shadow"]["mode"] == "read_only"
    assert committed["public_shadow"]["allowed_effects"] == []
    assert committed["public_shadow"]["live_authorization_required"] is True


def test_controlled_fixtures_are_self_contained_and_cross_domain() -> None:
    fixtures = {item["fixture"] for item in supervised_gui_acceptance_manifest()["controlled"]["scenarios"]}

    assert fixtures == {
        "candidate-comparison.html",
        "chart-analysis.html",
        "map-spatial.html",
        "file-list.html",
    }
    for fixture in fixtures:
        source = (DEFAULT_FIXTURE_ROOT / fixture).read_text(encoding="utf-8")
        assert "http://" not in source
        assert "https://" not in source
        assert 'src="//' not in source
        assert 'href="//' not in source


def test_flagship_keeps_color_pixel_only_and_starts_without_a_selection() -> None:
    source = (DEFAULT_FIXTURE_ROOT / "candidate-comparison.html").read_text(encoding="utf-8")

    assert source.count('aria-label="Fabric sample"') == 3
    assert 'aria-label="Red fabric sample"' not in source
    assert 'aria-label="Blue fabric sample"' not in source
    assert 'aria-label="Green fabric sample"' not in source
    assert source.count('data-selected="false"') == 3
    assert source.count('aria-pressed="false"') == 3


def test_public_shadow_preflight_does_not_open_browser_or_network(tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"

    report = preflight_public_shadow({}, output)

    assert report["input_ready"] is False
    assert report["live_execution_ready"] is False
    assert report["surface_filter_admission_required"] is True
    assert report["browser_opened"] is False
    assert report["network_requests"] == 0
    assert len(report["errors"]) == 2
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_public_shadow_preflight_keeps_only_origins(tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"
    environment = {
        "SUPERVISED_GUI_SHADOW_SHOPPING_URL": "https://shop.example/private/item?campaign=secret",
        "SUPERVISED_GUI_SHADOW_CONTENT_URL": "http://content.example/article#tracking",
    }

    report = preflight_public_shadow(environment, output)
    serialized = output.read_text(encoding="utf-8")

    assert report["input_ready"] is True
    assert report["live_execution_ready"] is False
    assert report["preflight_scope"] == "url_inputs_only"
    assert report["required_content_filter_profile"] == "ads_and_cosmetic.v1"
    assert [item["configured_origin"] for item in report["cases"]] == [
        "https://shop.example",
        "http://content.example",
    ]
    assert "/private/item" not in serialized
    assert "campaign" not in serialized
    assert "article" not in serialized
    assert "tracking" not in serialized
    assert report["browser_opened"] is False
    assert report["network_requests"] == 0


def test_public_shadow_preflight_rejects_embedded_credentials_and_invalid_hosts(
    tmp_path: Path,
) -> None:
    report = preflight_public_shadow(
        {
            "SUPERVISED_GUI_SHADOW_SHOPPING_URL": "https://user:password@shop.example/item",
            "SUPERVISED_GUI_SHADOW_CONTENT_URL": "https://[invalid",
        },
        tmp_path / "preflight.json",
    )

    assert report["input_ready"] is False
    assert all(not item["ready"] for item in report["cases"])
    assert all(item["configured_origin"] == "" for item in report["cases"])
