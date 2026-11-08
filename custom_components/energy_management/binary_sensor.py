"""Capteur binaire Écart : l'onduleur n'est pas aux valeurs voulues."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import signal_update
from .manager import EnergyManager, device_info
from .reconciler import COMMANDS, LABELS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Ajoute le capteur Écart."""
    async_add_entities([EcartBinarySensor(entry)])


class EcartBinarySensor(BinarySensorEntity):
    """Allumé tant qu'au moins une commande est en écart ou indisponible."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "ecart"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry: ConfigEntry) -> None:
        self._manager: EnergyManager = entry.runtime_data
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_ecart"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self._manager.gaps)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Libellés des commandes en écart, dans l'ordre de COMMANDS."""
        return {
            "commandes": [
                LABELS[command]
                for command in COMMANDS
                if command in self._manager.gaps
            ]
        }

    async def async_added_to_hass(self) -> None:
        """S'abonne aux mises à jour du manager."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
