"""Manager : écoutes, minuteur, verrou du Pilotage et remise aux valeurs normales."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import DOMAIN, UPDATE_INTERVAL, signal_update
from .decision import STATE_OUTAGE, Decision, Settings, decide, normal_targets
from .inputs import input_entities, read_inputs, settings_from_conf
from .reconciler import Reconciler, compute_gaps, read_actual

_LOGGER = logging.getLogger(__name__)


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Appareil « Energy Management » commun à toutes les entités de l'entrée."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Energy Management",
        entry_type=DeviceEntryType.SERVICE,
    )


class EnergyManager:
    """Instance de l'extension : calcule l'état voulu et pilote l'onduleur."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.conf: dict[str, Any] = {**entry.data, **entry.options}
        self.settings: Settings = settings_from_conf(self.conf)
        self.pilotage = False  # coupé par défaut
        self.decision: Decision | None = None
        self.gaps: list[str] = []
        self.reset_pending = False  # remise aux normales demandée, pas encore faite
        self._reconciler = Reconciler(hass, self.conf)
        self._running = False
        self._unsubs: list[CALLBACK_TYPE] = []

    async def async_start(self) -> None:
        """Pose les écoutes et le minuteur, puis lance le premier calcul."""
        self._running = True
        # Les quatre commandes sont lues, jamais écoutées : chaque relecture
        # relancerait sinon un calcul (décision 7).
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, input_entities(self.conf), self._on_input_change
            )
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._on_tick, UPDATE_INTERVAL)
        )
        self._schedule_refresh()

    async def async_stop(self) -> None:
        """Retire écoutes et minuteur ; une séquence en cours s'arrête."""
        self._running = False
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def _on_input_change(self, _event: Event[EventStateChangedData]) -> None:
        self._schedule_refresh()

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self._schedule_refresh()

    @callback
    def _schedule_refresh(self) -> None:
        """Lance un calcul en tâche suivie par l'entrée (attendue au déchargement)."""
        self.entry.async_create_task(
            self.hass, self.async_refresh(), "energy_management_refresh"
        )

    def _update_gaps(self) -> None:
        """Recalcule les écarts et prévient les entités."""
        targets = self.decision.targets if self.decision else None
        self.gaps = (
            compute_gaps(read_actual(self.hass, self.conf), targets)
            if targets is not None
            else []
        )
        async_dispatcher_send(self.hass, signal_update(self.entry.entry_id))

    async def async_refresh(self) -> None:
        """Calcule l'état voulu puis, si permis, réconcilie l'onduleur."""
        if not self._running:
            return
        previous = self.decision.targets if self.decision else None
        decision = decide(read_inputs(self.hass, self.conf), self.settings, previous)
        self.decision = decision
        self._update_gaps()

        # Réseau absent : aucune écriture, une remise demandée reste en attente.
        if decision.state == STATE_OUTAGE:
            return
        try:
            if not self.pilotage and self.reset_pending:
                if await self._reconciler.async_apply(
                    normal_targets(self.settings),
                    self.settings.gap,
                    should_continue=lambda: self._running and not self.pilotage,
                ):
                    self.reset_pending = False
            elif self.pilotage and decision.targets is not None:
                await self._reconciler.async_apply(
                    decision.targets,
                    self.settings.gap,
                    should_continue=lambda: self._running and self.pilotage,
                )
            else:
                return
        except Exception:
            # Un minuteur ou une écoute ne doit jamais planter : on journalise.
            _LOGGER.exception("Réconciliation de l'onduleur en erreur")
        self._update_gaps()

    async def async_set_pilotage(self, on: bool, *, restored: bool = False) -> None:
        """Allume ou coupe le Pilotage ; la coupure demande une remise aux normales.

        Le drapeau change tout de suite (une séquence en cours le voit avant
        l'écriture suivante) ; le calcul part en tâche pour ne pas bloquer
        l'interrupteur pendant une séquence d'écritures.
        """
        if on:
            self.reset_pending = False
        elif self.pilotage and not restored:
            # Décision 1 : remise seulement au passage actif → coupé.
            self.reset_pending = True
        self.pilotage = on
        self._schedule_refresh()
