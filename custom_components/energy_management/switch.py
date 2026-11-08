"""Interrupteur Pilotage : autorise les écritures sur l'onduleur."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import (
    ExtraStoredData,
    RestoredExtraData,
    RestoreEntity,
)

from .manager import EnergyManager, device_info

# Clé des données conservées : remise aux normales demandée, pas encore faite
RESET_PENDING = "remise_en_attente"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Ajoute l'interrupteur Pilotage."""
    async_add_entities([PilotageSwitch(entry)])


class PilotageSwitch(SwitchEntity, RestoreEntity):
    """Pilotage : coupé par défaut, état conservé au redémarrage."""

    _attr_has_entity_name = True
    _attr_translation_key = "pilotage"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._manager: EnergyManager = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_pilotage"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        """État du Pilotage tenu par le manager."""
        return self._manager.pilotage

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Conserve une remise demandée au redémarrage et au rechargement."""
        return RestoredExtraData({RESET_PENDING: self._manager.reset_pending})

    async def async_added_to_hass(self) -> None:
        """Restaure l'état et une remise déjà demandée.

        Un Pilotage restauré coupé sans remise en attente n'écrit rien
        (décision 1) ; une remise demandée avant l'arrêt part au calcul suivant.
        """
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_ON:
            await self._manager.async_set_pilotage(True, restored=True)
            return
        extra = await self.async_get_last_extra_data()
        if extra is not None and extra.as_dict().get(RESET_PENDING) is True:
            self._manager.reset_pending = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allume le Pilotage."""
        await self._manager.async_set_pilotage(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Coupe le Pilotage : la séquence en cours s'arrête, remise aux normales."""
        await self._manager.async_set_pilotage(False)
        self.async_write_ha_state()
