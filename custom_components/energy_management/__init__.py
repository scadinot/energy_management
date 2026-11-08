"""Extension Energy Management (EMS Tempo) : pilotage de l'onduleur selon Tempo et la vigilance."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN  # noqa: F401


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Installe l'entrée (rien à démarrer pour l'instant)."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge l'entrée."""
    return True
