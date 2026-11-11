"""Tests du panneau latéral."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.components import frontend
from homeassistant.helpers import entity_registry as er

from custom_components.energy_management.const import CONF_MODE_SELECT, DOMAIN
from custom_components.energy_management.frontend import (
    JS_FILENAME,
    PANEL_URL_PATH,
)

from .const import MODE_SELECT

JS = Path(__file__).parent.parent / "custom_components" / "energy_management" / "frontend" / JS_FILENAME


async def _setup(hass, entry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_panneau_enregistre(hass, base_states, mock_entry):
    with patch(
        "custom_components.energy_management.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await _setup(hass, mock_entry)
    register.assert_called_once()
    kwargs = register.call_args.kwargs
    assert kwargs["frontend_url_path"] == "energy-management"
    assert kwargs["webcomponent_name"] == "energy-management-panel"
    assert kwargs["sidebar_icon"] == "mdi:home-battery"
    assert kwargs["require_admin"] is False
    config = kwargs["config"]
    registry = er.async_get(hass)
    for cle, domaine in (
        ("pilotage", "switch"),
        ("mode_voulu", "sensor"),
        ("raison", "sensor"),
        ("reserve_active", "sensor"),
        ("ecart", "binary_sensor"),
    ):
        reel = registry.async_get_entity_id(domaine, DOMAIN, f"{mock_entry.entry_id}_{cle}")
        assert reel is not None
        assert config[f"{cle}_entity"] == reel
    assert config[CONF_MODE_SELECT] == MODE_SELECT


async def test_adresse_du_panneau_versionnee(hass, base_states, mock_entry):
    """La version du manifeste est dans l'adresse : pas d'ancien fichier en cache."""
    manifest = json.loads((JS.parent.parent / "manifest.json").read_text(encoding="utf-8"))
    with patch(
        "custom_components.energy_management.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await _setup(hass, mock_entry)
    assert register.call_args.kwargs["module_url"] == (
        f"/energy_management_static/{JS_FILENAME}?v={manifest['version']}"
    )


async def test_panneau_retire_au_dechargement(hass, base_states, mock_entry):
    await _setup(hass, mock_entry)
    assert PANEL_URL_PATH in hass.data[frontend.DATA_PANELS]
    with patch(
        "custom_components.energy_management.frontend.frontend.async_remove_panel",
        wraps=frontend.async_remove_panel,
    ) as remove:
        assert await hass.config_entries.async_unload(mock_entry.entry_id)
        await hass.async_block_till_done()
    remove.assert_called_once_with(hass, "energy-management")
    assert PANEL_URL_PATH not in hass.data[frontend.DATA_PANELS]


def test_fichier_js_present():
    assert JS.is_file()
    assert 'customElements.define("energy-management-panel"' in JS.read_text(encoding="utf-8")


def test_js_un_seul_service():
    appels = re.findall(r"callService\(([^)]*)\)", JS.read_text(encoding="utf-8"))
    assert len(appels) == 1
    assert appels[0].lstrip().startswith('"switch"')


async def test_panneau_phenomenes_par_defaut(hass, base_states):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.energy_management.const import (
        ACTIVE_LEVELS,
        CONF_PHENOMENA,
        DEFAULT_PHENOMENA,
    )

    from .const import MOCK_CONF

    conf = {k: v for k, v in MOCK_CONF.items() if k != CONF_PHENOMENA}
    entry = MockConfigEntry(domain=DOMAIN, data=conf, unique_id=DOMAIN, version=1)
    with patch(
        "custom_components.energy_management.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await _setup(hass, entry)
    config = register.call_args.kwargs["config"]
    assert config[CONF_PHENOMENA] == DEFAULT_PHENOMENA
    assert config["active_levels"] == list(ACTIVE_LEVELS)
