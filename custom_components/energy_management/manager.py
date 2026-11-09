"""Manager : écoutes, minuteur, verrou du Pilotage et remise aux valeurs normales."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    CoreState,
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
from homeassistant.helpers.start import async_at_started

from .const import DOMAIN, UPDATE_INTERVAL, conf_of, signal_update
from .decision import FROZEN_STATES, Decision, Settings, decide, normal_targets
from .inputs import grid_present, input_entities, read_inputs, settings_from_conf
from .reconciler import COMMANDS, Reconciler, compute_gaps, read_actual

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
        self.conf: dict[str, Any] = conf_of(entry)
        self.settings: Settings = settings_from_conf(self.conf)
        self.pilotage = False  # coupé par défaut
        self.decision: Decision | None = None
        self.gaps: list[str] = []
        # Commandes (CMD_*) encore à remettre aux valeurs normales ; vide = rien
        self.reset_pending: set[str] = set()
        # Un verrou par entrée, conservé d'un rechargement à l'autre : une
        # séquence de l'ancien manager bloque le nouveau jusqu'à son arrêt.
        locks: dict[str, asyncio.Lock] = hass.data.setdefault(DOMAIN, {})
        lock = locks.setdefault(entry.entry_id, asyncio.Lock())
        self._reconciler = Reconciler(hass, self.conf, lock)
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
        if self.hass.state is not CoreState.running:
            # Démarrage de HA en cours : nouveau calcul une fois HA démarré.
            self._unsubs.append(async_at_started(self.hass, self._on_started))
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
    def _on_started(self, _hass: HomeAssistant) -> None:
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
        try:
            await self._async_refresh()
        except Exception:
            # Un minuteur ou une écoute ne doit jamais planter : on journalise.
            _LOGGER.exception("Calcul ou réconciliation de l'onduleur en erreur")

    def _grid(self) -> bool:
        """Réseau présent, relu à chaque essai d'une séquence."""
        return grid_present(self.hass, self.conf)

    async def _async_refresh(self) -> None:
        """Corps du calcul ; les exceptions sont journalisées par l'appelant."""
        previous = self.decision.targets if self.decision else None
        decision = decide(read_inputs(self.hass, self.conf), self.settings, previous)
        self.decision = decision
        self._update_gaps()

        # Réseau absent ou capteur de présence illisible : aucune écriture, une remise demandée reste en attente.
        # La présence est aussi contrôlée avant chaque essai d'une séquence en
        # cours (gel en coupure, décision 6) ; une remise interrompue reste
        # alors en attente et repart au retour du réseau (décision 2).
        if decision.state in FROZEN_STATES:
            return
        # Démarrage de HA pas terminé : une source peut ne pas être chargée
        # (couleur Tempo inconnue = non rouge) alors que l'onduleur se lit
        # déjà. On calcule et on affiche, sans écrire ni remettre.
        if self.hass.state is not CoreState.running:
            return
        if not self.pilotage and self.reset_pending:
            await self._async_reset()
        elif self.pilotage and decision.targets is not None:
            await self._reconciler.async_apply(
                decision.targets,
                self.settings.gap,
                should_continue=lambda: self._running and self.pilotage and self._grid(),
            )
        else:
            return
        self._update_gaps()

    def _prune_reset(self) -> None:
        """Retire de la remise les commandes relues à leur valeur normale.

        Une commande illisible reste à remettre ; une commande remise puis
        réglée à la main n'y revient jamais.
        """
        actual = read_actual(self.hass, self.conf)
        self.reset_pending &= set(compute_gaps(actual, normal_targets(self.settings)))

    async def _async_reset(self) -> None:
        """Remise aux valeurs normales, limitée aux commandes encore à remettre."""
        # Séquence précédente encore en cours (Pilotage coupé pendant une
        # écriture) : une écriture peut être en vol, la commande se relit
        # encore à sa valeur normale et serait retirée à tort. On n'élague ni
        # n'écrit : la vérification suivante reprend. Aucun `await` entre ce
        # test, l'élagage et la prise du verrou par async_apply.
        # Cas résiduel accepté : une écriture déclarée en échec (3 essais de
        # 60 s) qui arriverait encore plus tard.
        if self._reconciler.busy:
            return
        self._prune_reset()
        if not self.reset_pending:
            return
        await self._reconciler.async_apply(
            normal_targets(self.settings),
            self.settings.gap,
            should_continue=lambda: (
                self._running and not self.pilotage and self._grid()
            ),
            only=frozenset(self.reset_pending),
        )
        self._prune_reset()

    async def async_set_pilotage(self, on: bool, *, restored: bool = False) -> None:
        """Allume ou coupe le Pilotage ; la coupure demande une remise aux normales.

        Le drapeau change tout de suite (une séquence en cours le voit avant
        l'écriture suivante) ; le calcul part en tâche pour ne pas bloquer
        l'interrupteur pendant une séquence d'écritures.
        """
        if on:
            self.reset_pending = set()
        elif self.pilotage and not restored:
            # Décision 1 : remise seulement au passage actif → coupé.
            self.reset_pending = set(COMMANDS)
        self.pilotage = on
        self._schedule_refresh()
