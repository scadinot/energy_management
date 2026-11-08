"""Réconciliation : ordre des écritures sur l'onduleur et exécution."""
from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_CHARGE,
    CONF_HIGH,
    CONF_LOW,
    CONF_MODE_SELECT,
    CONF_NOTIFY,
    CONF_OPTION_BATTERY,
    CONF_OPTION_GRID,
    DOMAIN,
    NUMBER_TOLERANCE,
    READBACK_TIMEOUT,
    WRITE_ATTEMPTS,
)
from .decision import MODE_BATTERY, MODE_GRID, Targets

_LOGGER = logging.getLogger(__name__)

CMD_MODE = "mode"
CMD_LOW = "low"
CMD_HIGH = "high"
CMD_CHARGE = "charge"
COMMANDS = (CMD_MODE, CMD_LOW, CMD_HIGH, CMD_CHARGE)


@dataclass(frozen=True)
class Actual:
    """Valeurs relues sur l'onduleur ; None = commande indisponible."""

    mode: str | None  # MODE_GRID, MODE_BATTERY, autre option brute, ou None
    low: float | None
    high: float | None
    charge: float | None


@dataclass(frozen=True)
class Write:
    """Une écriture à faire ; `value` vaut MODE_* pour CMD_MODE."""

    command: str
    value: str | float


def same(actual: float | None, wanted: float) -> bool:
    """Valeur relue égale à la valeur voulue, à la tolérance près."""
    if actual is None:
        return False
    return abs(actual - wanted) < NUMBER_TOLERANCE


def _threshold_writes(actual: Actual, desired: Targets, gap: float) -> list[Write]:
    """Écritures des seuils, dans l'ordre qui préserve haut >= bas + écart."""
    # Un seuil illisible garde sa vraie valeur sur l'onduleur : écrire l'autre
    # seul pourrait violer haut >= bas + écart. Seule l'abstention le garantit.
    if actual.low is None or actual.high is None:
        return []
    need_low = not same(actual.low, desired.low)
    need_high = not same(actual.high, desired.high)
    low = Write(CMD_LOW, desired.low)
    high = Write(CMD_HIGH, desired.high)

    if need_low and need_high:
        # États intermédiaires : bas d'abord = (voulu.bas, réel.haut),
        # haut d'abord = (réel.bas, voulu.haut).
        low_first_ok = actual.high >= desired.low + gap
        high_first_ok = desired.high >= actual.low + gap
        if low_first_ok != high_first_ok:
            high_first = high_first_ok
        else:
            # Les deux ordres conviennent, ou aucun : règle de la spec.
            high_first = desired.high > actual.high
        return [high, low] if high_first else [low, high]
    # Un seul seuil à écrire : le couple obtenu doit respecter l'écart, sinon
    # abstention. Ex. remise limitée au seuil 12 alors que le seuil 13 a été
    # réglé à la main trop bas.
    if need_low:
        return [low] if actual.high >= desired.low + gap - NUMBER_TOLERANCE else []
    if need_high:
        return [high] if desired.high >= actual.low + gap - NUMBER_TOLERANCE else []
    return []


def _restrict(actual: Actual, desired: Targets, only: Collection[str]) -> Targets:
    """Cibles où chaque commande hors de `only` garde sa valeur relue.

    Une commande illisible hors de `only` garde sa cible : elle reste
    illisible, donc non écrite, et l'abstention des seuils s'applique.
    """

    def keep(command: str, current: Any, wanted: Any) -> Any:
        return current if command not in only and current is not None else wanted

    return replace(
        desired,
        mode=keep(CMD_MODE, actual.mode, desired.mode),
        low=keep(CMD_LOW, actual.low, desired.low),
        high=keep(CMD_HIGH, actual.high, desired.high),
        charge=keep(CMD_CHARGE, actual.charge, desired.charge),
    )


def plan_writes(
    actual: Actual,
    desired: Targets,
    gap: float,
    only: Collection[str] | None = None,
) -> list[Write]:
    """Ordonne les écritures nécessaires pour passer de `actual` à `desired`.

    `only` limite les écritures à ces commandes (None : toutes).
    """
    if only is not None:
        desired = _restrict(actual, desired, only)
    need_mode = actual.mode is not None and actual.mode != desired.mode
    thresholds = _threshold_writes(actual, desired, gap)
    mode = Write(CMD_MODE, desired.mode)

    writes: list[Write] = []
    if need_mode and desired.mode == MODE_BATTERY:
        # Vers la batterie : seuils d'abord ; mode omis si un seuil est indisponible.
        writes.extend(thresholds)
        if actual.low is not None and actual.high is not None:
            writes.append(mode)
    elif need_mode:
        # Vers le réseau : mode d'abord, sans condition.
        writes.append(mode)
        writes.extend(thresholds)
    else:
        writes.extend(thresholds)

    if actual.charge is not None and not same(actual.charge, desired.charge):
        writes.append(Write(CMD_CHARGE, desired.charge))
    return writes


def compute_gaps(actual: Actual, desired: Targets) -> list[str]:
    """Commandes en écart ou indisponibles, dans l'ordre de COMMANDS."""
    gaps: list[str] = []
    if actual.mode is None or actual.mode != desired.mode:
        gaps.append(CMD_MODE)
    if not same(actual.low, desired.low):
        gaps.append(CMD_LOW)
    if not same(actual.high, desired.high):
        gaps.append(CMD_HIGH)
    if not same(actual.charge, desired.charge):
        gaps.append(CMD_CHARGE)
    return gaps


# Entité de chaque commande et libellé français pour les notifications
_ENTITY_KEY = {
    CMD_MODE: CONF_MODE_SELECT,
    CMD_LOW: CONF_LOW,
    CMD_HIGH: CONF_HIGH,
    CMD_CHARGE: CONF_CHARGE,
}
LABELS = {
    CMD_MODE: "Mode de sortie",
    CMD_LOW: "Seuil 12",
    CMD_HIGH: "Seuil 13",
    CMD_CHARGE: "Charge réseau",
}


def _number(hass: HomeAssistant, entity_id: str) -> float | None:
    """Valeur numérique finie d'une entité, None si absente ou illisible."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        number = float(state.state)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def read_actual(hass: HomeAssistant, conf: Mapping[str, Any]) -> Actual:
    """Lit les quatre commandes de l'onduleur."""
    mode: str | None = None
    state = hass.states.get(conf[CONF_MODE_SELECT])
    if state is not None and state.state not in ("unknown", "unavailable"):
        if state.state == conf[CONF_OPTION_GRID]:
            mode = MODE_GRID
        elif state.state == conf[CONF_OPTION_BATTERY]:
            mode = MODE_BATTERY
        else:
            mode = state.state
    return Actual(
        mode,
        _number(hass, conf[CONF_LOW]),
        _number(hass, conf[CONF_HIGH]),
        _number(hass, conf[CONF_CHARGE]),
    )


class Reconciler:
    """Exécute les écritures planifiées, une séquence à la fois."""

    def __init__(
        self,
        hass: HomeAssistant,
        conf: Mapping[str, Any],
        lock: asyncio.Lock | None = None,
    ) -> None:
        self._hass = hass
        self._conf = conf
        # Verrou fourni par le manager : partagé entre rechargements d'une entrée
        self._lock = lock if lock is not None else asyncio.Lock()
        self._failed: set[str] = set()  # commandes en échec, déjà notifiées

    @property
    def busy(self) -> bool:
        """Une séquence d'écritures est en cours."""
        return self._lock.locked()

    async def async_apply(
        self,
        desired: Targets,
        gap: float,
        should_continue: Callable[[], bool] = lambda: True,
        only: Collection[str] | None = None,
    ) -> bool:
        """Écrit ce qui manque, seulement sur les commandes de `only` si donné.

        True seulement si, après la séquence, les commandes visées (les quatre
        si `only` vaut None) sont relues à leur valeur voulue ; False sinon
        (échec, arrêt demandé, commande indisponible donc non écrite) ou si
        une séquence est déjà en cours.
        """
        if self._lock.locked():
            _LOGGER.debug("Séquence d'écritures déjà en cours : vérification ignorée")
            return False
        async with self._lock:
            actual = read_actual(self._hass, self._conf)
            # Une commande en échec revenue d'elle-même à sa valeur : effacer.
            gaps = compute_gaps(actual, desired)
            for command in sorted(self._failed - set(gaps)):
                self._clear_failure(command)
            for write in plan_writes(actual, desired, gap, only):
                # False = échec ou arrêt demandé : la séquence s'arrête.
                if not await self._write(write, should_continue):
                    return False
            # plan_writes omet une commande illisible : seule la relecture
            # finale dit si tout est vraiment en place.
            scope = set(COMMANDS if only is None else only)
            remaining = compute_gaps(read_actual(self._hass, self._conf), desired)
            return not scope.intersection(remaining)

    async def _write(
        self, write: Write, should_continue: Callable[[], bool]
    ) -> bool:
        """Écrit une commande avec ses essais ; gère les notifications.

        Renvoie False sur échec (notifié) ou sur arrêt demandé (non notifié) :
        `should_continue` est contrôlé avant chaque essai.
        """
        for attempt in range(1, WRITE_ATTEMPTS + 1):
            if not should_continue():
                return False
            if await self._try_write(write):
                self._clear_failure(write.command)
                return True
            _LOGGER.warning(
                "Écriture %s non relue (essai %s/%s)",
                write.command,
                attempt,
                WRITE_ATTEMPTS,
            )
        await self._notify_failure(write)
        return False

    def _option(self, mode: str | float) -> str:
        """Option du select pour MODE_BATTERY ou MODE_GRID."""
        return self._conf[
            CONF_OPTION_BATTERY if mode == MODE_BATTERY else CONF_OPTION_GRID
        ]

    def _call(
        self, write: Write
    ) -> tuple[str, str, dict[str, Any], Callable[[str], bool]]:
        """Service, données et test de relecture d'une écriture."""
        entity_id = self._conf[_ENTITY_KEY[write.command]]
        if write.command == CMD_MODE:
            option = self._option(write.value)
            return (
                "select",
                "select_option",
                {"entity_id": entity_id, "option": option},
                lambda state: state == option,
            )

        def _matches(state: str) -> bool:
            try:
                return same(float(state), float(write.value))
            except ValueError:
                return False

        return (
            "number",
            "set_value",
            {"entity_id": entity_id, "value": write.value},
            _matches,
        )

    async def _try_write(self, write: Write) -> bool:
        """Un essai : appel du service, puis attente de la relecture."""
        domain, service, data, matches = self._call(write)
        entity_id = data["entity_id"]
        done = asyncio.Event()

        @callback
        def _on_change(event: Event) -> None:
            new = event.data.get("new_state")
            if new is not None and matches(new.state):
                done.set()

        # Abonnement avant l'appel : une mise à jour rapide ne doit pas être ratée.
        unsub = async_track_state_change_event(self._hass, [entity_id], _on_change)
        try:
            try:
                # Un appel qui ne revient jamais garderait le verrou pour toujours.
                async with asyncio.timeout(READBACK_TIMEOUT):
                    await self._hass.services.async_call(
                        domain, service, data, blocking=True
                    )
            except HomeAssistantError as err:
                _LOGGER.warning("Appel %s.%s en erreur : %s", domain, service, err)
                return False
            except TimeoutError:
                _LOGGER.warning("Appel %s.%s sans réponse", domain, service)
                return False
            current = self._hass.states.get(entity_id)
            if current is not None and matches(current.state):
                return True
            try:
                async with asyncio.timeout(READBACK_TIMEOUT):
                    await done.wait()
            except TimeoutError:
                return False
            return True
        finally:
            unsub()

    def _clear_failure(self, command: str) -> None:
        """Retire la notification d'une commande qui n'est plus en échec.

        Toujours appelé à la relecture réussie, même si la commande n'est pas
        dans `_failed` : la notification peut venir d'avant un rechargement
        (async_dismiss ne fait rien si elle n'existe pas).
        """
        self._failed.discard(command)
        persistent_notification.async_dismiss(self._hass, f"{DOMAIN}_echec_{command}")

    async def _notify_failure(self, write: Write) -> None:
        """Notifie l'échec, une seule fois par épisode et par commande."""
        if write.command in self._failed:
            return
        self._failed.add(write.command)
        entity_id = self._conf[_ENTITY_KEY[write.command]]
        # Pour le mode : l'option du select (ex. « SBU (...) »), pas grid / battery
        value = (
            self._option(write.value) if write.command == CMD_MODE else write.value
        )
        title = "Energy Management"
        message = (
            f"{LABELS[write.command]} : la valeur {value} voulue sur "
            f"{entity_id} n'a pas été relue après {WRITE_ATTEMPTS} essais."
        )
        persistent_notification.async_create(
            self._hass,
            message,
            title=title,
            notification_id=f"{DOMAIN}_echec_{write.command}",
        )
        if target := self._conf.get(CONF_NOTIFY):
            domain, _, service = target.partition(".")
            try:
                await self._hass.services.async_call(
                    domain, service, {"title": title, "message": message}
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Notification %s impossible : %s", target, err)
