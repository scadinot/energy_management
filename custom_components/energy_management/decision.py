"""Décision : calcul de l'état voulu (Python pur, sans Home Assistant)."""
from __future__ import annotations

from dataclasses import dataclass

MODE_GRID = "grid"
MODE_BATTERY = "battery"

STATE_GRID = "reseau"
STATE_BATTERY = "batterie"
STATE_BOOST = "charge_renforcee"
STATE_OUTAGE = "coupure_reseau"
STATE_GRID_UNKNOWN = "capteur_reseau_indisponible"
STATES = [STATE_GRID, STATE_BATTERY, STATE_BOOST, STATE_OUTAGE, STATE_GRID_UNKNOWN]
# États sans écriture : réseau absent ou présence illisible (même gel)
FROZEN_STATES = (STATE_OUTAGE, STATE_GRID_UNKNOWN)


@dataclass(frozen=True)
class Inputs:
    """Entrées lues, déjà interprétées."""

    grid_present: bool
    today_red: bool
    tomorrow_red: bool
    off_peak: bool | None  # None = inconnu
    vigilance: tuple[tuple[str, str], ...]  # (phénomène, niveau) actifs
    vigilance_unknown: bool
    soc: float | None
    ev_charging: bool
    grid_unknown: bool = False  # capteur de présence illisible ou absent


@dataclass(frozen=True)
class Settings:
    """Réglages de l'utilisateur."""

    reserve_normal: int
    reserve_vigilance: int
    gap: int
    low_normal: int
    high_normal: int
    charge_normal: int
    charge_boost: int


@dataclass(frozen=True)
class Targets:
    """Valeurs voulues pour les commandes de l'onduleur."""

    mode: str
    low: float
    high: float
    charge: float


@dataclass(frozen=True)
class Decision:
    """Résultat du calcul."""

    state: str
    reason: str
    reserve: int
    targets: Targets | None


def normal_targets(settings: Settings) -> Targets:
    """Valeurs du fonctionnement normal (mode réseau)."""
    return Targets(
        MODE_GRID, settings.low_normal, settings.high_normal, settings.charge_normal
    )


def _vigilance_suffix(inputs: Inputs) -> str:
    """Complément de raison décrivant la vigilance."""
    if inputs.vigilance:
        names = ", ".join(
            f"{phenomenon} {level}".lower() for phenomenon, level in inputs.vigilance
        )
        return f" (vigilance {names})"
    if inputs.vigilance_unknown:
        return " (vigilance inconnue)"
    return ""


def decide(
    inputs: Inputs, settings: Settings, previous: Targets | None = None
) -> Decision:
    """Calcule l'état voulu ; `previous` est conservé pendant une coupure réseau."""
    reserve = (
        settings.reserve_vigilance
        if inputs.vigilance or inputs.vigilance_unknown
        else settings.reserve_normal
    )
    normal = normal_targets(settings)

    if not inputs.grid_present:
        if inputs.grid_unknown:
            return Decision(
                STATE_GRID_UNKNOWN,
                "Capteur de présence réseau indisponible, aucune écriture",
                reserve,
                previous,
            )
        return Decision(
            STATE_OUTAGE, "Réseau absent, aucune écriture", reserve, previous
        )

    if inputs.today_red and inputs.off_peak is False:
        if inputs.soc is None:
            return Decision(
                STATE_GRID, "Jour rouge, SOC inconnu : réseau", reserve, normal
            )
        targets = Targets(
            MODE_BATTERY, reserve, reserve + settings.gap, settings.charge_normal
        )
        reason = f"Jour rouge, réserve {reserve} %{_vigilance_suffix(inputs)}"
        return Decision(STATE_BATTERY, reason, reserve, targets)

    if inputs.off_peak is True and inputs.tomorrow_red:
        if inputs.ev_charging:
            return Decision(
                STATE_GRID,
                "Lendemain rouge, borne en charge : charge normale",
                reserve,
                normal,
            )
        boosted = Targets(MODE_GRID, normal.low, normal.high, settings.charge_boost)
        return Decision(
            STATE_BOOST,
            f"Lendemain rouge : charge renforcée {settings.charge_boost} A",
            reserve,
            boosted,
        )

    if inputs.off_peak is None:
        return Decision(
            STATE_GRID, "Heures creuses inconnues : réseau", reserve, normal
        )

    return Decision(STATE_GRID, "Fonctionnement normal", reserve, normal)
