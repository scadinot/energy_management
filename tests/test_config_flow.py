"""Tests de l'assistant de configuration et des options."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.energy_management.const import (
    CONF_CHARGE,
    CONF_CHARGE_BOOST,
    CONF_CHARGE_NORMAL,
    CONF_COLOR_TODAY,
    CONF_COLOR_TOMORROW,
    CONF_EV_POWER,
    CONF_EV_THRESHOLD,
    CONF_GAP,
    CONF_GRID,
    CONF_HIGH,
    CONF_HIGH_NORMAL,
    CONF_LOW,
    CONF_LOW_NORMAL,
    CONF_MODE_SELECT,
    CONF_NOTIFY,
    CONF_OFF_PEAK,
    CONF_OPTION_BATTERY,
    CONF_OPTION_GRID,
    CONF_PHENOMENA,
    CONF_RESERVE_NORMAL,
    CONF_RESERVE_VIGILANCE,
    CONF_SOC,
    CONF_VIGILANCE,
    DOMAIN,
)

from custom_components.energy_management.config_flow import validate_values

from .const import HIGH, LOW, MOCK_CONF, MODE_SELECT, SBU, SELECT_OPTIONS, UTI

STEP_1 = [
    CONF_COLOR_TODAY,
    CONF_COLOR_TOMORROW,
    CONF_OFF_PEAK,
    CONF_VIGILANCE,
    CONF_PHENOMENA,
    CONF_SOC,
    CONF_EV_POWER,
    CONF_GRID,
]
STEP_2 = [CONF_MODE_SELECT, CONF_LOW, CONF_HIGH, CONF_CHARGE]
STEP_3 = [
    CONF_OPTION_GRID,
    CONF_OPTION_BATTERY,
    CONF_RESERVE_NORMAL,
    CONF_RESERVE_VIGILANCE,
    CONF_GAP,
    CONF_LOW_NORMAL,
    CONF_HIGH_NORMAL,
    CONF_CHARGE_NORMAL,
    CONF_CHARGE_BOOST,
    CONF_EV_THRESHOLD,
]


@pytest.fixture(autouse=True)
def sans_dependances():
    """Ne charge pas `frontend` et `panel_custom` : l'assistant n'en a pas besoin."""
    with patch("homeassistant.config_entries.async_process_deps_reqs", AsyncMock()):
        yield


def _part(conf: dict, keys: list[str]) -> dict:
    """Extrait de `conf` les champs d'une étape."""
    return {key: conf[key] for key in keys if key in conf}


async def _flux_values(hass):
    """Config flow jusqu'au formulaire de l'étape 3."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_1)
    )
    assert result["step_id"] == "commands"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_2)
    )
    assert result["step_id"] == "values"
    return result


async def test_parcours_complet(hass, base_states):
    result = await _flux_values(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_3)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Energy Management"
    assert result["data"] == MOCK_CONF


async def test_options_de_l_etape_3(hass, base_states):
    result = await _flux_values(hass)
    schema = result["data_schema"].schema
    keys = {str(key): key for key in schema}
    for name in (CONF_OPTION_GRID, CONF_OPTION_BATTERY):
        config = schema[keys[name]].config
        assert list(config["options"]) == SELECT_OPTIONS
    assert keys[CONF_OPTION_GRID].default() == UTI
    assert keys[CONF_OPTION_BATTERY].default() == SBU
    # Aucun service notify : le champ est absent du schéma
    assert CONF_NOTIFY not in keys


async def test_une_seule_instance(hass, base_states, mock_entry):
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.parametrize(
    "champ,valeur,erreur",
    [
        (CONF_RESERVE_VIGILANCE, 20, "reserve_order"),
        (CONF_HIGH_NORMAL, 54, "gap_order"),
        (CONF_LOW_NORMAL, 96, "out_of_bounds"),
        (CONF_RESERVE_NORMAL, 3, "out_of_bounds"),
        (CONF_CHARGE_BOOST, 90, "out_of_bounds"),
        (CONF_OPTION_BATTERY, UTI, "same_option"),
    ],
)
async def test_controles(hass, base_states, champ, valeur, erreur):
    result = await _flux_values(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**_part(MOCK_CONF, STEP_3), champ: valeur}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "values"
    assert result["errors"] == {champ: erreur}


async def test_option_absente_du_select(hass, base_states):
    """Le sélecteur refuse déjà une valeur inconnue ; validate_values la refuse aussi."""
    conf = {**MOCK_CONF, CONF_OPTION_BATTERY: "Inconnue"}
    assert validate_values(hass, conf) == {CONF_OPTION_BATTERY: "option_missing"}
    # Select indisponible ou sans options : contrôle sauté
    hass.states.async_set(MODE_SELECT, "unavailable")
    assert validate_values(hass, conf) == {}


async def test_bornes_ignorees_si_entite_absente(hass, base_states):
    hass.states.async_remove(LOW)
    hass.states.async_remove(HIGH)
    result = await _flux_values(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**_part(MOCK_CONF, STEP_3), CONF_RESERVE_NORMAL: 3}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow(hass, base_states, mock_entry):
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_1)
    )
    assert result["step_id"] == "commands"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_2)
    )
    assert result["step_id"] == "values"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_part(MOCK_CONF, STEP_3), CONF_CHARGE_BOOST: 18}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_entry.options[CONF_CHARGE_BOOST] == 18
    assert mock_entry.options[CONF_SOC] == MOCK_CONF[CONF_SOC]


async def test_options_flow_champ_facultatif_vide(hass, base_states, mock_entry):
    """Vider la présence réseau la retire de la configuration."""
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    sans_reseau = [key for key in STEP_1 if key != CONF_GRID]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, sans_reseau)
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_2)
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_3)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_GRID not in mock_entry.options


def _structure(node):
    """Réduit un JSON imbriqué à l'arbre de ses clés."""
    if isinstance(node, dict):
        return {key: _structure(value) for key, value in node.items()}
    return None


def test_traductions_coherentes():
    dossier = Path(__file__).parent.parent / "custom_components" / "energy_management"
    strings = json.loads((dossier / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((dossier / "translations" / "en.json").read_text(encoding="utf-8"))
    fr = json.loads((dossier / "translations" / "fr.json").read_text(encoding="utf-8"))
    assert strings == en
    assert _structure(strings) == _structure(fr)
