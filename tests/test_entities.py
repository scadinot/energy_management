"""Tests des entités d'état : Mode voulu, Raison, Réserve active, Écart."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_management.const import DOMAIN

from .const import CHARGE, COLOR_TODAY, VIGILANCE

CLES = ("mode_voulu", "raison", "reserve_active", "ecart")
DOMAINES = {
    "mode_voulu": "sensor",
    "raison": "sensor",
    "reserve_active": "sensor",
    "ecart": "binary_sensor",
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    """Identifiant d'une entité, lu dans le registre."""
    entity_id = er.async_get(hass).async_get_entity_id(
        DOMAINES[key], DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    return hass.states.get(_id(hass, entry, key))


def _set(hass: HomeAssistant, entity_id: str, value: str) -> None:
    current = hass.states.get(entity_id)
    attributes = dict(current.attributes) if current else {}
    hass.states.async_set(entity_id, value, attributes)


async def test_entites_creees(hass, base_states, mock_entry):
    await _setup(hass, mock_entry)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, mock_entry.entry_id)
    assert {e.unique_id for e in entries} == {
        f"{mock_entry.entry_id}_{key}" for key in (*CLES, "pilotage")
    }
    assert len(entries) == 5


async def test_journee_normale(hass, base_states, mock_entry):
    await _setup(hass, mock_entry)
    assert _state(hass, mock_entry, "mode_voulu").state == "reseau"
    assert _state(hass, mock_entry, "raison").state == "Fonctionnement normal"
    reserve = _state(hass, mock_entry, "reserve_active")
    assert reserve.state == "30"
    assert reserve.attributes["unit_of_measurement"] == "%"
    assert _state(hass, mock_entry, "ecart").state == "off"


async def test_jour_rouge_pilotage_coupe(hass, base_states, fake_inverter, mock_entry):
    await _setup(hass, mock_entry)
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    mode = _state(hass, mock_entry, "mode_voulu")
    assert mode.state == "batterie"
    assert mode.attributes["mode"] == "battery"
    assert mode.attributes["seuil_12"] == 30
    assert mode.attributes["seuil_13"] == 35
    assert mode.attributes["charge"] == 15
    ecart = _state(hass, mock_entry, "ecart")
    assert ecart.state == "on"
    assert ecart.attributes["commandes"] == [
        "Mode de sortie",
        "Seuil 12",
        "Seuil 13",
    ]
    # Pilotage coupé : affichage seul, aucune écriture
    assert fake_inverter.calls == []


async def test_vigilance(hass, base_states, mock_entry):
    await _setup(hass, mock_entry)
    attributes = dict(hass.states.get(VIGILANCE).attributes)
    attributes["Vent violent"] = "Orange"
    hass.states.async_set(VIGILANCE, "Orange", attributes)
    await hass.async_block_till_done()
    assert _state(hass, mock_entry, "reserve_active").state == "50"


async def test_commande_indisponible(hass, base_states, mock_entry):
    await _setup(hass, mock_entry)
    _set(hass, CHARGE, "unavailable")
    # Les commandes sont lues, jamais écoutées : on attend le calcul suivant
    await mock_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    ecart = _state(hass, mock_entry, "ecart")
    assert ecart.state == "on"
    assert ecart.attributes["commandes"] == ["Charge réseau"]
