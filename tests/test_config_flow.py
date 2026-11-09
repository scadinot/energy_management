"""Tests de l'assistant de configuration et des options."""
from __future__ import annotations

import json
from pathlib import Path

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


MENU = ["sources", "commands", "values", "confirm"]


async def _menu(hass, entry):
    """Ouvre les options : menu de configuration."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "init"
    assert result["menu_options"] == MENU
    return result


async def _page(hass, result, page):
    """Depuis le menu, ouvre une page."""
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": page}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == page
    return result


async def _enregistrer(hass, result):
    """Depuis le menu, « Valider et enregistrer »."""
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "confirm"}
    )


async def test_options_menu(hass, base_states, mock_entry):
    """Les options s'ouvrent sur un menu : trois pages et l'enregistrement."""
    mock_entry.add_to_hass(hass)
    await _menu(hass, mock_entry)


async def test_options_flow(hass, base_states, mock_entry):
    """Une seule page modifiée, retour au menu, puis enregistrement complet."""
    mock_entry.add_to_hass(hass)
    result = await _page(hass, await _menu(hass, mock_entry), "values")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_part(MOCK_CONF, STEP_3), CONF_CHARGE_BOOST: 18}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "init"
    result = await _enregistrer(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_entry.options[CONF_CHARGE_BOOST] == 18
    assert mock_entry.options[CONF_SOC] == MOCK_CONF[CONF_SOC]


async def test_options_enregistrer_sans_modifier(hass, base_states, mock_entry):
    """Enregistrer directement : configuration actuelle conservée telle quelle."""
    mock_entry.add_to_hass(hass)
    result = await _enregistrer(hass, await _menu(hass, mock_entry))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(mock_entry.options) == MOCK_CONF


async def test_options_chaque_page_revient_au_menu(hass, base_states, mock_entry):
    mock_entry.add_to_hass(hass)
    result = await _menu(hass, mock_entry)
    for page, keys in (("sources", STEP_1), ("commands", STEP_2), ("values", STEP_3)):
        result = await _page(hass, result, page)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], _part(MOCK_CONF, keys)
        )
        assert result["type"] is FlowResultType.MENU, page
    assert mock_entry.options == {}  # rien d'enregistré avant « Valider »


async def test_options_flow_champ_facultatif_vide(hass, base_states, mock_entry):
    """Vider la présence réseau la retire de la configuration."""
    mock_entry.add_to_hass(hass)
    result = await _page(hass, await _menu(hass, mock_entry), "sources")
    sans_reseau = [key for key in STEP_1 if key != CONF_GRID]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, sans_reseau)
    )
    result = await _enregistrer(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_GRID not in mock_entry.options


async def test_options_page_valeurs_erreur(hass, base_states, mock_entry):
    """Page Valeurs fautive : erreur affichée, pas de retour au menu."""
    mock_entry.add_to_hass(hass)
    result = await _page(hass, await _menu(hass, mock_entry), "values")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_part(MOCK_CONF, STEP_3), CONF_RESERVE_VIGILANCE: 10}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "values"
    assert result["errors"] == {CONF_RESERVE_VIGILANCE: "reserve_order"}


async def test_options_enregistrer_revalide(hass, base_states, mock_entry):
    """Commandes changées sans revoir les valeurs : l'enregistrement revérifie,
    montre la page Valeurs en erreur, puis enregistre dès qu'elle est corrigée."""
    autre = "select.autre_mode"
    hass.states.async_set(autre, "A", {"options": ["A", "B"]})
    mock_entry.add_to_hass(hass)
    result = await _page(hass, await _menu(hass, mock_entry), "commands")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**_part(MOCK_CONF, STEP_2), CONF_MODE_SELECT: autre}
    )
    result = await _enregistrer(hass, result)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "values"
    assert result["errors"] == {
        CONF_OPTION_GRID: "option_missing",
        CONF_OPTION_BATTERY: "option_missing",
    }
    assert mock_entry.options == {}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**_part(MOCK_CONF, STEP_3), CONF_OPTION_GRID: "A", CONF_OPTION_BATTERY: "B"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_entry.options[CONF_MODE_SELECT] == autre
    assert mock_entry.options[CONF_OPTION_BATTERY] == "B"


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


def _bornes(hass, low, high):
    """Pose les bornes des entités des seuils 12 et 13."""
    hass.states.async_set(LOW, "50", {"min": low[0], "max": low[1], "step": 1})
    hass.states.async_set(HIGH, "95", {"min": high[0], "max": high[1], "step": 1})


async def test_reserve_basse_valide_si_reserve_plus_ecart_dans_les_bornes(
    hass, base_states
):
    _bornes(hass, (0, 95), (10, 100))
    conf = {**MOCK_CONF, CONF_RESERVE_NORMAL: 5, CONF_GAP: 5}
    assert validate_values(hass, conf) == {}


async def test_reserve_vigilance_plus_ecart_hors_bornes(hass, base_states):
    _bornes(hass, (0, 100), (10, 100))
    conf = {**MOCK_CONF, CONF_RESERVE_VIGILANCE: 98, CONF_GAP: 5}
    assert validate_values(hass, conf) == {CONF_GAP: "out_of_bounds"}


async def test_reserve_plus_ecart_sans_bornes_du_seuil_13(hass, base_states):
    """Bornes du seuil 13 inconnues : réserve + écart reste plafonné à 100."""
    _bornes(hass, (0, 100), (10, 100))
    hass.states.async_set(HIGH, "95")  # plus d'attributs min / max
    conf = {**MOCK_CONF, CONF_RESERVE_VIGILANCE: 98, CONF_GAP: 5}
    assert validate_values(hass, conf) == {CONF_GAP: "out_of_bounds"}
    conf = {**MOCK_CONF, CONF_RESERVE_VIGILANCE: 95, CONF_GAP: 5}
    assert validate_values(hass, conf) == {}


async def _options_jusqu_aux_valeurs(hass, entry):
    """Options : menu puis page Valeurs."""
    return await _page(hass, await _menu(hass, entry), "values")


async def test_options_notify_conserve_sans_service(hass, base_states):
    """Aucun service notify : le champ n'est pas montré, la cible enregistrée reste."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_CONF, CONF_NOTIFY: "notify.telephone"},
        unique_id=DOMAIN,
        version=1,
    )
    entry.add_to_hass(hass)
    result = await _options_jusqu_aux_valeurs(hass, entry)
    assert CONF_NOTIFY not in {str(key) for key in result["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_3)
    )
    result = await _enregistrer(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_NOTIFY] == "notify.telephone"


async def test_options_notify_vide_retire(hass, base_states):
    """Champ notify montré et laissé vide : la cible est retirée."""
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_mock_service,
    )

    async_mock_service(hass, "notify", "telephone")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_CONF, CONF_NOTIFY: "notify.telephone"},
        unique_id=DOMAIN,
        version=1,
    )
    entry.add_to_hass(hass)
    result = await _options_jusqu_aux_valeurs(hass, entry)
    assert CONF_NOTIFY in {str(key) for key in result["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _part(MOCK_CONF, STEP_3)
    )
    result = await _enregistrer(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_NOTIFY not in entry.options
