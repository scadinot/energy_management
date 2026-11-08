"""Tests des fixtures communes (base_states, fake_inverter)."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .const import (
    CHARGE,
    CHARGE_BOUNDS,
    COLOR_TODAY,
    COLOR_TOMORROW,
    EV_POWER,
    GRID,
    HIGH,
    LOW,
    MODE_SELECT,
    OFF_PEAK,
    SBU,
    SELECT_OPTIONS,
    SOC,
    UTI,
    VIGILANCE,
)

PHENOMENA = {
    "Vent violent",
    "Pluie-inondation",
    "Orages",
    "Neige-verglas",
    "Grand-froid",
    "Inondation",
    "Vagues-submersion",
}


async def test_base_states(hass: HomeAssistant, base_states) -> None:
    """La journée bleue pose les 11 entités avec les bons états et attributs."""
    expected = {
        COLOR_TODAY: "Bleu",
        COLOR_TOMORROW: "Bleu",
        OFF_PEAK: "off",
        VIGILANCE: "Vert",
        SOC: "97.7",
        EV_POWER: "38",
        GRID: "on",
        MODE_SELECT: UTI,
        LOW: "50",
        HIGH: "95",
        CHARGE: "15",
    }
    for entity_id, state in expected.items():
        assert hass.states.get(entity_id).state == state, entity_id
    assert hass.states.get(MODE_SELECT).attributes["options"] == SELECT_OPTIONS
    low = hass.states.get(CHARGE).attributes
    assert (low["min"], low["max"], low["step"]) == (*CHARGE_BOUNDS, 1)
    attrs = hass.states.get(VIGILANCE).attributes
    assert PHENOMENA <= set(attrs)
    assert all(attrs[name] == "Vert" for name in PHENOMENA)


async def test_ecriture_immediate(hass: HomeAssistant, base_states, fake_inverter) -> None:
    """Une écriture met l'état à jour, garde les attributs et est enregistrée."""
    await hass.services.async_call(
        "number", "set_value", {"entity_id": LOW, "value": 30}, blocking=True
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": MODE_SELECT, "option": SBU},
        blocking=True,
    )
    assert hass.states.get(LOW).state == "30"
    assert hass.states.get(LOW).attributes["max"] == 95
    assert hass.states.get(MODE_SELECT).state == SBU
    assert hass.states.get(MODE_SELECT).attributes["options"] == SELECT_OPTIONS
    assert fake_inverter.calls == [(LOW, 30), (MODE_SELECT, SBU)]


async def test_entite_sourde(hass: HomeAssistant, base_states, fake_inverter) -> None:
    """Une entité sourde enregistre l'appel mais garde son état."""
    fake_inverter.deaf.add(LOW)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": LOW, "value": 30}, blocking=True
    )
    assert hass.states.get(LOW).state == "50"
    assert fake_inverter.calls == [(LOW, 30)]


async def test_ecriture_differee(hass: HomeAssistant, base_states, fake_inverter) -> None:
    """Avec un délai, l'état ne change qu'après l'échéance."""
    fake_inverter.delay[HIGH] = 0.05
    await hass.services.async_call(
        "number", "set_value", {"entity_id": HIGH, "value": 80}, blocking=True
    )
    assert hass.states.get(HIGH).state == "95"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert hass.states.get(HIGH).state == "80"
    assert fake_inverter.calls == [(HIGH, 80)]
