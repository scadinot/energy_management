"""Panneau latéral Energy Management.

Sert le fichier JS du panneau via l'URL statique `/energy_management_static`
et déclare une entrée dans la barre latérale (instance unique).
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import ACTIVE_LEVELS, CONF_PHENOMENA, DEFAULT_PHENOMENA, DOMAIN, conf_of

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "energy-management"
PANEL_TITLE = "Energy Management"
PANEL_ICON = "mdi:home-battery"
PANEL_NAME = "energy-management-panel"  # nom du Web Component

STATIC_PATH = "/energy_management_static"
JS_FILENAME = "energy_management_panel.js"

_STATIC_KEY = f"{DOMAIN}_static_registered"

# Clé du panneau -> domaine de l'entité créée par l'extension
_ENTITIES = {
    "pilotage": "switch",
    "mode_voulu": "sensor",
    "raison": "sensor",
    "reserve_active": "sensor",
    "ecart": "binary_sensor",
}


async def async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Enregistre le panneau (idempotent) avec les identifiants d'entités."""
    if not hass.data.get(_STATIC_KEY):
        frontend_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_PATH, str(frontend_dir), cache_headers=False)]
        )
        hass.data[_STATIC_KEY] = True

    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        _LOGGER.debug("Panneau déjà enregistré sur /%s", PANEL_URL_PATH)
        return

    # Les identifiants dépendent de la langue : on les lit dans le registre.
    registry = er.async_get(hass)
    config: dict = dict(conf_of(entry))
    # Même repli que le calcul (inputs.py) : sans liste, les phénomènes par défaut
    config[CONF_PHENOMENA] = config.get(CONF_PHENOMENA) or list(DEFAULT_PHENOMENA)
    config["active_levels"] = list(ACTIVE_LEVELS)
    for key, domain in _ENTITIES.items():
        config[f"{key}_entity"] = registry.async_get_entity_id(
            domain, DOMAIN, f"{entry.entry_id}_{key}"
        )

    await panel_custom.async_register_panel(
        hass=hass,
        webcomponent_name=PANEL_NAME,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{STATIC_PATH}/{JS_FILENAME}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        config=config,
        require_admin=False,
        embed_iframe=False,
    )


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Retire le panneau s'il est enregistré."""
    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
