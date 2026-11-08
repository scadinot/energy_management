"""Extension Energy Management (EMS Tempo) : pilotage de l'onduleur selon Tempo et la vigilance."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN  # noqa: F401
from .frontend import async_register_panel, async_unregister_panel
from .manager import EnergyManager

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Crée le manager, ajoute les entités puis démarre les calculs."""
    manager = EnergyManager(hass, entry)
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_start()
    # Arrêt garanti si une étape suivante échoue (HA traite alors les
    # async_on_unload) ; sans effet après l'arrêt fait au déchargement.
    entry.async_on_unload(manager.async_stop)
    await async_register_panel(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options modifiées : recharge l'entrée avec la nouvelle configuration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Arrête le manager, retire les entités, puis le panneau."""
    await entry.runtime_data.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await async_unregister_panel(hass)
    return unloaded
