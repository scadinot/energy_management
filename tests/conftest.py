"""Fixtures communes de la suite de tests Energy Management."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.event import async_call_later
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_management.const import DOMAIN

from .const import (
    CHARGE,
    CHARGE_BOUNDS,
    COLOR_TODAY,
    COLOR_TOMORROW,
    EV_POWER,
    GRID,
    HIGH,
    HIGH_BOUNDS,
    LOW,
    LOW_BOUNDS,
    MOCK_CONF,
    MODE_SELECT,
    OFF_PEAK,
    SELECT_OPTIONS,
    SOC,
    UTI,
    VIGILANCE,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Autorise le chargement des extensions personnalisées dans les tests."""
    yield


def _number(hass: HomeAssistant, entity_id: str, value: str, bounds: tuple) -> None:
    """Pose un `number` avec ses attributs min, max et pas."""
    hass.states.async_set(
        entity_id, value, {"min": bounds[0], "max": bounds[1], "step": 1}
    )


@pytest.fixture
def base_states(hass: HomeAssistant) -> None:
    """Journée bleue normale : tout est en place, rien à faire."""
    hass.states.async_set(COLOR_TODAY, "Bleu")
    hass.states.async_set(COLOR_TOMORROW, "Bleu")
    hass.states.async_set(OFF_PEAK, "off")
    hass.states.async_set(
        VIGILANCE,
        "Vert",
        {
            "Vent violent": "Vert",
            "Pluie-inondation": "Vert",
            "Orages": "Vert",
            "Inondation": "Vert",
            "Neige-verglas": "Vert",
            "Vagues-submersion": "Vert",
            "attribution": "Données Météo-France",
            "icon": "mdi:weather-cloudy-alert",
            "friendly_name": "76 Weather alert",
            "Grand-froid": "Vert",
        },
    )
    hass.states.async_set(SOC, "97.7")
    hass.states.async_set(EV_POWER, "38")
    hass.states.async_set(GRID, "on")
    hass.states.async_set(MODE_SELECT, UTI, {"options": SELECT_OPTIONS})
    _number(hass, LOW, "50", LOW_BOUNDS)
    _number(hass, HIGH, "95", HIGH_BOUNDS)
    _number(hass, CHARGE, "15", CHARGE_BOUNDS)


class FakeInverter:
    """Onduleur simulé : enregistre les appels et recopie les valeurs écrites."""

    def __init__(self) -> None:
        # Appels reçus, dans l'ordre : (entité, valeur)
        self.calls: list[tuple[str, Any]] = []
        # Entités qui ignorent les écritures (appel enregistré, état inchangé)
        self.deaf: set[str] = set()
        # Secondes avant que l'état relu soit posé, par entité
        self.delay: dict[str, float] = {}


@pytest.fixture
def fake_inverter(hass: HomeAssistant) -> FakeInverter:
    """Enregistre `select.select_option` et `number.set_value` sur le hass de test."""
    inverter = FakeInverter()

    def _apply(entity_id: str, value: str) -> None:
        """Pose le nouvel état en gardant les attributs existants."""
        current = hass.states.get(entity_id)
        attributes = dict(current.attributes) if current else {}
        hass.states.async_set(entity_id, value, attributes)

    def _write(entity_id: str, value: Any, stored: str) -> None:
        inverter.calls.append((entity_id, value))
        if entity_id in inverter.deaf:
            return
        delay = inverter.delay.get(entity_id)
        if delay:

            @callback
            def _later(_now) -> None:
                _apply(entity_id, stored)

            async_call_later(hass, timedelta(seconds=delay), _later)
        else:
            _apply(entity_id, stored)

    def _entities(call: ServiceCall) -> list[str]:
        entity_ids = call.data["entity_id"]
        return [entity_ids] if isinstance(entity_ids, str) else list(entity_ids)

    async def _select_option(call: ServiceCall) -> None:
        for entity_id in _entities(call):
            _write(entity_id, call.data["option"], call.data["option"])

    async def _set_value(call: ServiceCall) -> None:
        for entity_id in _entities(call):
            # Comme l'ESP : la valeur relue est la forme texte du nombre écrit
            _write(entity_id, call.data["value"], str(call.data["value"]))

    hass.services.async_register("select", "select_option", _select_option)
    hass.services.async_register("number", "set_value", _set_value)
    return inverter


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """Entrée de configuration complète avec les valeurs par défaut."""
    return MockConfigEntry(domain=DOMAIN, data=MOCK_CONF, unique_id=DOMAIN, version=1)
