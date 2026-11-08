"""Réconciliation : ordre des écritures sur l'onduleur (partie pure)."""
from __future__ import annotations

from dataclasses import dataclass

from .const import NUMBER_TOLERANCE
from .decision import MODE_BATTERY, Targets

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
    need_low = actual.low is not None and not same(actual.low, desired.low)
    need_high = actual.high is not None and not same(actual.high, desired.high)
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
    if need_low:
        return [low]
    if need_high:
        return [high]
    return []


def plan_writes(actual: Actual, desired: Targets, gap: float) -> list[Write]:
    """Ordonne les écritures nécessaires pour passer de `actual` à `desired`."""
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
