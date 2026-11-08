"""Capteurs d'état : Mode voulu, Raison, Réserve active."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import signal_update
from .decision import STATES
from .manager import EnergyManager, device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Ajoute les trois capteurs."""
    async_add_entities(
        [ModeVouluSensor(entry), RaisonSensor(entry), ReserveActiveSensor(entry)]
    )


class _EtatSensor(SensorEntity):
    """Capteur de la décision du manager, mis à jour à chaque calcul."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _key: str

    def __init__(self, entry: ConfigEntry) -> None:
        self._manager: EnergyManager = entry.runtime_data
        self._entry_id = entry.entry_id
        self._attr_translation_key = self._key
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_device_info = device_info(entry)

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


class ModeVouluSensor(_EtatSensor):
    """État voulu, avec les valeurs cibles en attributs."""

    _key = "mode_voulu"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    @property
    def native_value(self) -> str | None:
        decision = self._manager.decision
        return decision.state if decision else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        decision = self._manager.decision
        targets = decision.targets if decision else None
        return {
            "mode": targets.mode if targets else None,
            "seuil_12": targets.low if targets else None,
            "seuil_13": targets.high if targets else None,
            "charge": targets.charge if targets else None,
        }


class RaisonSensor(_EtatSensor):
    """Raison en clair de la décision."""

    _key = "raison"

    @property
    def native_value(self) -> str | None:
        decision = self._manager.decision
        return decision.reason if decision else None


class ReserveActiveSensor(_EtatSensor):
    """Réserve de batterie retenue (en %)."""

    _key = "reserve_active"
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> int | None:
        decision = self._manager.decision
        return decision.reserve if decision else None
