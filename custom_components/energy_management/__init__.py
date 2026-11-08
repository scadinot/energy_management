"""Extension Energy Management (EMS Tempo) : pilotage de l'onduleur selon Tempo et la vigilance."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN  # noqa: F401
from .manager import EnergyManager

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Crée le manager, ajoute les entités puis démarre les calculs."""
    manager = EnergyManager(hass, entry)
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options modifiées : recharge l'entrée avec la nouvelle configuration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Arrête le manager, puis retire les entités."""
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
