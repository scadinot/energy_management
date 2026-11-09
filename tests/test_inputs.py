"""Tests de la lecture des entrées."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.energy_management.const import CONF_GRID
from custom_components.energy_management.decision import Settings
from custom_components.energy_management.inputs import (
    input_entities,
    read_inputs,
    settings_from_conf,
)

from .const import (
    COLOR_TODAY,
    COLOR_TOMORROW,
    EV_POWER,
    GRID,
    MOCK_CONF,
    OFF_PEAK,
    SOC,
    VIGILANCE,
)


async def test_journee_bleue(hass: HomeAssistant, base_states) -> None:
    """Journée bleue normale : toutes les entrées sont lues."""
    inputs = read_inputs(hass, MOCK_CONF)
    assert inputs.today_red is False
    assert inputs.tomorrow_red is False
    assert inputs.off_peak is False
    assert inputs.vigilance == ()
    assert inputs.vigilance_unknown is False
    assert inputs.soc == 97.7
    assert inputs.ev_charging is False
    assert inputs.grid_present is True


async def test_rouge(hass: HomeAssistant, base_states) -> None:
    """La couleur « Rouge » donne un jour rouge."""
    hass.states.async_set(COLOR_TODAY, "Rouge")
    assert read_inputs(hass, MOCK_CONF).today_red is True


@pytest.mark.parametrize("etat", ["Bleu", "Blanc", "inconnu", "unknown", "unavailable"])
async def test_couleur_non_rouge(hass: HomeAssistant, base_states, etat) -> None:
    """Toute autre valeur n'est pas rouge."""
    hass.states.async_set(COLOR_TODAY, etat)
    assert read_inputs(hass, MOCK_CONF).today_red is False


async def test_entite_couleur_absente(hass: HomeAssistant, base_states) -> None:
    """Une entité absente n'est pas rouge."""
    hass.states.async_remove(COLOR_TODAY)
    assert read_inputs(hass, MOCK_CONF).today_red is False


async def test_heures_creuses_indisponibles(hass: HomeAssistant, base_states) -> None:
    """Heures creuses indisponibles ou absentes : inconnues."""
    hass.states.async_set(OFF_PEAK, "unavailable")
    assert read_inputs(hass, MOCK_CONF).off_peak is None
    hass.states.async_remove(OFF_PEAK)
    assert read_inputs(hass, MOCK_CONF).off_peak is None
    hass.states.async_set(OFF_PEAK, "on")
    assert read_inputs(hass, MOCK_CONF).off_peak is True


def _vigilance(hass: HomeAssistant, **changes: str) -> None:
    """Remplace des attributs de l'entité de vigilance."""
    current = hass.states.get(VIGILANCE)
    hass.states.async_set(VIGILANCE, current.state, {**current.attributes, **changes})


async def test_vigilance_orange(hass: HomeAssistant, base_states) -> None:
    """Un phénomène orange est actif."""
    _vigilance(hass, **{"Vent violent": "Orange"})
    inputs = read_inputs(hass, MOCK_CONF)
    assert inputs.vigilance == (("Vent violent", "Orange"),)
    assert inputs.vigilance_unknown is False


async def test_vigilance_jaune_ignoree(hass: HomeAssistant, base_states) -> None:
    """Un phénomène jaune est ignoré."""
    _vigilance(hass, Orages="Jaune")
    assert read_inputs(hass, MOCK_CONF).vigilance == ()


async def test_vigilance_phenomene_non_surveille(
    hass: HomeAssistant, base_states
) -> None:
    """Un phénomène hors de la liste configurée est ignoré."""
    _vigilance(hass, **{"Vagues-submersion": "Rouge"})
    assert read_inputs(hass, MOCK_CONF).vigilance == ()


@pytest.mark.parametrize("etat", ["unknown", "unavailable"])
async def test_vigilance_indisponible(hass: HomeAssistant, base_states, etat) -> None:
    """Vigilance indisponible ou absente : inconnue."""
    hass.states.async_set(VIGILANCE, etat)
    inputs = read_inputs(hass, MOCK_CONF)
    assert inputs.vigilance_unknown is True
    assert inputs.vigilance == ()
    hass.states.async_remove(VIGILANCE)
    assert read_inputs(hass, MOCK_CONF).vigilance_unknown is True


async def test_vigilance_attribut_manquant_ignore(
    hass: HomeAssistant, base_states
) -> None:
    """Un attribut manquant est ignoré ; l'ordre suit la configuration."""
    hass.states.async_set(
        VIGILANCE, "Orange", {"Grand-froid": "Rouge", "Orages": "Orange"}
    )
    inputs = read_inputs(hass, MOCK_CONF)
    assert inputs.vigilance == (("Orages", "Orange"), ("Grand-froid", "Rouge"))
    assert inputs.vigilance_unknown is False


async def test_vigilance_sans_liste_configuree(
    hass: HomeAssistant, base_states
) -> None:
    """Sans liste de phénomènes configurée, les phénomènes par défaut servent."""
    _vigilance(hass, Orages="Orange")
    conf = {k: v for k, v in MOCK_CONF.items() if k != "phenomena"}
    assert read_inputs(hass, conf).vigilance == (("Orages", "Orange"),)


@pytest.mark.parametrize("etat", ["unknown", "unavailable", "abc", "-5", "120"])
async def test_soc_invalide(hass: HomeAssistant, base_states, etat) -> None:
    """SOC non numérique ou hors de 0-100 : inconnu."""
    hass.states.async_set(SOC, etat)
    assert read_inputs(hass, MOCK_CONF).soc is None


@pytest.mark.parametrize("etat,attendu", [("0", 0.0), ("100", 100.0)])
async def test_soc_bornes_incluses(
    hass: HomeAssistant, base_states, etat, attendu
) -> None:
    """0 et 100 sont acceptés."""
    hass.states.async_set(SOC, etat)
    assert read_inputs(hass, MOCK_CONF).soc == attendu


@pytest.mark.parametrize(
    "etat,attendu", [("500", False), ("500.1", True), ("unavailable", True)]
)
async def test_borne(hass: HomeAssistant, base_states, etat, attendu) -> None:
    """Borne en charge si au-dessus du seuil ou illisible."""
    hass.states.async_set(EV_POWER, etat)
    assert read_inputs(hass, MOCK_CONF).ev_charging is attendu


async def test_borne_absente(hass: HomeAssistant, base_states) -> None:
    """Une borne absente est considérée en charge."""
    hass.states.async_remove(EV_POWER)
    assert read_inputs(hass, MOCK_CONF).ev_charging is True


async def test_borne_seuil_configure(hass: HomeAssistant, base_states) -> None:
    """Le seuil de la configuration est utilisé."""
    hass.states.async_set(EV_POWER, "300")
    conf = {**MOCK_CONF, "ev_threshold": 200}
    assert read_inputs(hass, conf).ev_charging is True
    assert read_inputs(hass, MOCK_CONF).ev_charging is False


@pytest.mark.parametrize(
    "etat,attendu",
    [("on", True), ("off", False), ("unavailable", False), ("unknown", False)],
)
async def test_presence_reseau(hass: HomeAssistant, base_states, etat, attendu) -> None:
    """Réseau présent seulement si l'état vaut « on »."""
    hass.states.async_set(GRID, etat)
    assert read_inputs(hass, MOCK_CONF).grid_present is attendu


@pytest.mark.parametrize(
    "etat,attendu",
    [("on", False), ("off", False), ("unavailable", True), ("unknown", True)],
)
async def test_presence_reseau_illisible(
    hass: HomeAssistant, base_states, etat, attendu
) -> None:
    """« off » est une vraie coupure ; indisponible ou inconnu est un capteur illisible."""
    hass.states.async_set(GRID, etat)
    assert read_inputs(hass, MOCK_CONF).grid_unknown is attendu


async def test_presence_reseau_entite_absente(
    hass: HomeAssistant, base_states
) -> None:
    """Entité configurée mais absente : réseau absent."""
    hass.states.async_remove(GRID)
    assert read_inputs(hass, MOCK_CONF).grid_present is False
    assert read_inputs(hass, MOCK_CONF).grid_unknown is True


async def test_presence_reseau_non_configuree(hass: HomeAssistant, base_states) -> None:
    """Sans entité configurée, le réseau est présent."""
    conf = {k: v for k, v in MOCK_CONF.items() if k != CONF_GRID}
    assert read_inputs(hass, conf).grid_present is True
    assert read_inputs(hass, conf).grid_unknown is False


def test_settings_from_conf() -> None:
    """Les réglages viennent de la configuration, sinon des défauts."""
    attendu = Settings(30, 50, 5, 50, 95, 15, 20)
    assert settings_from_conf(MOCK_CONF) == attendu
    assert settings_from_conf({}) == attendu


def test_settings_from_conf_flottants() -> None:
    """Les nombres flottants du formulaire sont convertis en entiers."""
    conf = {**MOCK_CONF, "reserve_normal": 25.0, "gap": 7.0}
    settings = settings_from_conf(conf)
    assert settings.reserve_normal == 25
    assert isinstance(settings.reserve_normal, int)
    assert settings.gap == 7


def test_input_entities() -> None:
    """Sept sources avec MOCK_CONF, six sans présence réseau."""
    assert input_entities(MOCK_CONF) == [
        COLOR_TODAY,
        COLOR_TOMORROW,
        OFF_PEAK,
        VIGILANCE,
        SOC,
        EV_POWER,
        GRID,
    ]
    conf = {k: v for k, v in MOCK_CONF.items() if k != CONF_GRID}
    assert len(input_entities(conf)) == 6
    assert GRID not in input_entities(conf)
