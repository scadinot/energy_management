"""Tests du manifeste et des valeurs par défaut."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.energy_management.const import (
    CONF_CHARGE_BOOST,
    CONF_CHARGE_NORMAL,
    CONF_EV_THRESHOLD,
    CONF_GAP,
    CONF_HIGH_NORMAL,
    CONF_LOW_NORMAL,
    CONF_RESERVE_NORMAL,
    CONF_RESERVE_VIGILANCE,
    DEFAULT_PHENOMENA,
    DEFAULTS,
)

MANIFEST = (
    Path(__file__).parent.parent
    / "custom_components"
    / "energy_management"
    / "manifest.json"
)


def test_manifest():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["domain"] == "energy_management"
    assert data["name"] == "Energy Management"
    assert data["version"] == "0.1.3"
    assert data["single_config_entry"] is True
    assert data["config_flow"] is True
    assert data["iot_class"] == "calculated"
    assert set(data["dependencies"]) == {"http", "frontend", "panel_custom"}


def test_defaults():
    assert DEFAULTS[CONF_RESERVE_NORMAL] == 30 and DEFAULTS[CONF_RESERVE_VIGILANCE] == 50
    assert DEFAULTS[CONF_GAP] == 5
    assert (DEFAULTS[CONF_LOW_NORMAL], DEFAULTS[CONF_HIGH_NORMAL]) == (50, 95)
    assert (DEFAULTS[CONF_CHARGE_NORMAL], DEFAULTS[CONF_CHARGE_BOOST]) == (15, 20)
    assert DEFAULTS[CONF_EV_THRESHOLD] == 500
    assert DEFAULT_PHENOMENA == ["Vent violent", "Orages", "Neige-verglas", "Grand-froid", "Pluie-inondation"]
