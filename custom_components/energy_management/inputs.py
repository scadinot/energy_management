"""Lecture prudente des entrées : états Home Assistant vers `Inputs`."""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .const import (
    ACTIVE_LEVELS,
    CONF_CHARGE_BOOST,
    CONF_CHARGE_NORMAL,
    CONF_COLOR_TODAY,
    CONF_COLOR_TOMORROW,
    CONF_EV_POWER,
    CONF_EV_THRESHOLD,
    CONF_GAP,
    CONF_GRID,
    CONF_HIGH_NORMAL,
    CONF_LOW_NORMAL,
    CONF_OFF_PEAK,
    CONF_PHENOMENA,
    CONF_RESERVE_NORMAL,
    CONF_RESERVE_VIGILANCE,
    CONF_SOC,
    CONF_VIGILANCE,
    DEFAULT_PHENOMENA,
    DEFAULTS,
    RED,
)
from .decision import Inputs, Settings

_UNREADABLE = (STATE_UNKNOWN, STATE_UNAVAILABLE)


def _state(hass: HomeAssistant, conf: Mapping[str, Any], key: str) -> str | None:
    """État d'une source configurée ; None si non configurée ou absente."""
    entity_id = conf.get(key)
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    return state.state if state else None


def _number(value: str | None) -> float | None:
    """Convertit un état en nombre fini ; None s'il n'est pas lisible."""
    if value is None or value in _UNREADABLE:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if isfinite(number) else None


def _vigilance(
    hass: HomeAssistant, conf: Mapping[str, Any]
) -> tuple[tuple[tuple[str, str], ...], bool]:
    """Phénomènes actifs (dans l'ordre configuré) et indicateur « inconnue »."""
    entity_id = conf.get(CONF_VIGILANCE)
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in _UNREADABLE:
        return (), True
    phenomena = conf.get(CONF_PHENOMENA) or DEFAULT_PHENOMENA
    active = tuple(
        (name, state.attributes[name])
        for name in phenomena
        if state.attributes.get(name) in ACTIVE_LEVELS
    )
    return active, False


def read_inputs(hass: HomeAssistant, conf: Mapping[str, Any]) -> Inputs:
    """Lit les sources configurées ; toute valeur douteuse reste prudente."""
    vigilance, vigilance_unknown = _vigilance(hass, conf)

    off_peak = {"on": True, "off": False}.get(_state(hass, conf, CONF_OFF_PEAK))

    soc = _number(_state(hass, conf, CONF_SOC))
    if soc is not None and not 0 <= soc <= 100:
        soc = None

    # Borne illisible = en charge (cas prudent)
    threshold = float(conf.get(CONF_EV_THRESHOLD, DEFAULTS[CONF_EV_THRESHOLD]))
    ev_power = _number(_state(hass, conf, CONF_EV_POWER))
    ev_charging = ev_power is None or ev_power > threshold

    # Non configurée = présente ; configurée = présente seulement si « on »
    grid_present = (
        _state(hass, conf, CONF_GRID) == "on" if conf.get(CONF_GRID) else True
    )

    return Inputs(
        grid_present=grid_present,
        today_red=_state(hass, conf, CONF_COLOR_TODAY) == RED,
        tomorrow_red=_state(hass, conf, CONF_COLOR_TOMORROW) == RED,
        off_peak=off_peak,
        vigilance=vigilance,
        vigilance_unknown=vigilance_unknown,
        soc=soc,
        ev_charging=ev_charging,
    )


def settings_from_conf(conf: Mapping[str, Any]) -> Settings:
    """Réglages de la configuration, valeurs absentes remplacées par les défauts."""

    def value(key: str) -> int:
        return int(conf.get(key, DEFAULTS[key]))

    return Settings(
        reserve_normal=value(CONF_RESERVE_NORMAL),
        reserve_vigilance=value(CONF_RESERVE_VIGILANCE),
        gap=value(CONF_GAP),
        low_normal=value(CONF_LOW_NORMAL),
        high_normal=value(CONF_HIGH_NORMAL),
        charge_normal=value(CONF_CHARGE_NORMAL),
        charge_boost=value(CONF_CHARGE_BOOST),
    )


def input_entities(conf: Mapping[str, Any]) -> list[str]:
    """Identifiants des sources configurées, sans les valeurs vides."""
    keys = (
        CONF_COLOR_TODAY,
        CONF_COLOR_TOMORROW,
        CONF_OFF_PEAK,
        CONF_VIGILANCE,
        CONF_SOC,
        CONF_EV_POWER,
        CONF_GRID,
    )
    return [conf[key] for key in keys if conf.get(key)]
