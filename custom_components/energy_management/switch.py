"""Interrupteur Pilotage : autorise les écritures sur l'onduleur."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import (
    ExtraStoredData,
    RestoredExtraData,
    RestoreEntity,
)

from .const import signal_update
from .manager import EnergyManager, device_info
from .reconciler import COMMANDS, LABELS

# Clé des données conservées : commandes encore à remettre aux normales
RESET_PENDING = "remise_en_attente"
# Attributs d'état : remise en attente et libellés des commandes à remettre
ATTR_RESET_PENDING = "remise_en_attente"
ATTR_RESET_COMMANDS = "commandes_a_remettre"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Ajoute l'interrupteur Pilotage."""
    async_add_entities([PilotageSwitch(entry)])


def _restored_reset(value: Any) -> set[str]:
    """Commandes à remettre lues dans les données conservées.

    Liste de commandes (valeurs inconnues ignorées) ; ancien format booléen :
    True = toutes les commandes ; autre chose ou absent = rien.
    """
    if value is True:
        return set(COMMANDS)
    if isinstance(value, list):
        return {command for command in COMMANDS if command in value}
    return set()


class PilotageSwitch(SwitchEntity, RestoreEntity):
    """Pilotage : coupé par défaut, état conservé au redémarrage."""

    _attr_has_entity_name = True
    _attr_translation_key = "pilotage"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._manager: EnergyManager = entry.runtime_data
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_pilotage"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        """État du Pilotage tenu par le manager."""
        return self._manager.pilotage

    def _pending(self) -> list[str]:
        """Commandes encore à remettre, dans l'ordre de COMMANDS."""
        return [c for c in COMMANDS if c in self._manager.reset_pending]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Remise en attente et libellés des commandes encore à remettre."""
        pending = self._pending()
        return {
            ATTR_RESET_PENDING: bool(pending),
            ATTR_RESET_COMMANDS: [LABELS[command] for command in pending],
        }

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Conserve une remise demandée au redémarrage et au rechargement."""
        return RestoredExtraData({RESET_PENDING: self._pending()})

    async def async_added_to_hass(self) -> None:
        """Restaure l'état et une remise déjà demandée, puis suit le manager.

        Un Pilotage restauré coupé sans remise en attente n'écrit rien
        (décision 1) ; une remise demandée avant l'arrêt part au calcul suivant.
        """
        await super().async_added_to_hass()
        # Chaque calcul peut faire avancer la remise : attributs et données
        # conservées restent à jour.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry_id), self._handle_update
            )
        )
        last = await self.async_get_last_state()
        if last is not None and last.state == STATE_ON:
            await self._manager.async_set_pilotage(True, restored=True)
            return
        extra = await self.async_get_last_extra_data()
        if extra is not None:
            self._manager.reset_pending = _restored_reset(
                extra.as_dict().get(RESET_PENDING)
            )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allume le Pilotage."""
        await self._manager.async_set_pilotage(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Coupe le Pilotage : la séquence en cours s'arrête, remise aux normales."""
        await self._manager.async_set_pilotage(False)
        self.async_write_ha_state()
