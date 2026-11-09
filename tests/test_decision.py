"""Tests de la fonction de décision (pure, sans Home Assistant)."""
from __future__ import annotations

from custom_components.energy_management.decision import (
    Inputs,
    Settings,
    Targets,
    decide,
)

SETTINGS = Settings(30, 50, 5, 50, 95, 15, 20)


def make_inputs(**overrides) -> Inputs:
    """Fabrique des entrées : journée bleue, heures pleines, SOC 80 %."""
    values = {
        "grid_present": True,
        "today_red": False,
        "tomorrow_red": False,
        "off_peak": False,
        "vigilance": (),
        "vigilance_unknown": False,
        "soc": 80.0,
        "ev_charging": False,
    }
    values.update(overrides)
    return Inputs(**values)


def test_jour_normal():
    d = decide(make_inputs(), SETTINGS)
    assert d.state == "reseau"
    assert d.targets == Targets("grid", 50, 95, 15)
    assert d.reason == "Fonctionnement normal"


def test_jour_rouge_hp():
    d = decide(make_inputs(today_red=True), SETTINGS)
    assert d.state == "batterie"
    assert d.targets == Targets("battery", 30, 35, 15)
    assert d.reason == "Jour rouge, réserve 30 %"


def test_jour_rouge_vigilance():
    d = decide(
        make_inputs(today_red=True, vigilance=(("Vent violent", "Orange"),)),
        SETTINGS,
    )
    assert d.targets == Targets("battery", 50, 55, 15)
    assert d.reason == "Jour rouge, réserve 50 % (vigilance vent violent orange)"


def test_jour_rouge_deux_vigilances():
    d = decide(
        make_inputs(
            today_red=True,
            vigilance=(("Vent violent", "Orange"), ("Orages", "Rouge")),
        ),
        SETTINGS,
    )
    assert d.reason.endswith("(vigilance vent violent orange, orages rouge)")


def test_jour_rouge_vigilance_inconnue():
    d = decide(make_inputs(today_red=True, vigilance_unknown=True), SETTINGS)
    assert d.reserve == 50
    assert d.targets == Targets("battery", 50, 55, 15)
    assert d.reason.endswith("(vigilance inconnue)")


def test_jour_rouge_heures_creuses():
    d = decide(make_inputs(today_red=True, off_peak=True), SETTINGS)
    assert d.state == "reseau"
    assert d.targets == Targets("grid", 50, 95, 15)


def test_jour_rouge_soc_inconnu():
    d = decide(make_inputs(today_red=True, soc=None), SETTINGS)
    assert d.state == "reseau"
    assert d.targets == Targets("grid", 50, 95, 15)
    assert d.reason == "Jour rouge, SOC inconnu : réseau"


def test_jour_rouge_hc_inconnues():
    d = decide(make_inputs(today_red=True, off_peak=None), SETTINGS)
    assert d.state == "reseau"
    assert d.targets == Targets("grid", 50, 95, 15)
    assert d.reason == "Heures creuses inconnues : réseau"


def test_veille_rouge_hc():
    d = decide(make_inputs(tomorrow_red=True, off_peak=True), SETTINGS)
    assert d.state == "charge_renforcee"
    assert d.targets == Targets("grid", 50, 95, 20)
    assert d.reason == "Lendemain rouge : charge renforcée 20 A"


def test_veille_rouge_borne_en_charge():
    d = decide(
        make_inputs(tomorrow_red=True, off_peak=True, ev_charging=True), SETTINGS
    )
    assert d.state == "reseau"
    assert d.targets.charge == 15
    assert d.reason == "Lendemain rouge, borne en charge : charge normale"


def test_veille_rouge_hors_hc():
    d = decide(make_inputs(tomorrow_red=True, off_peak=False), SETTINGS)
    assert d.state == "reseau"
    assert d.targets == Targets("grid", 50, 95, 15)


def test_rouge_aujourdhui_et_demain_nuit():
    d = decide(
        make_inputs(today_red=True, tomorrow_red=True, off_peak=True), SETTINGS
    )
    assert d.state == "charge_renforcee"


def test_coupure_garde_cibles_precedentes():
    previous = Targets("battery", 30, 35, 15)
    d = decide(make_inputs(grid_present=False, today_red=True), SETTINGS, previous)
    assert d.state == "coupure_reseau"
    assert d.targets is previous
    assert d.reason == "Réseau absent, aucune écriture"


def test_capteur_reseau_indisponible_garde_cibles():
    """Présence réseau illisible : même gel qu'une coupure, libellé distinct."""
    previous = Targets("battery", 30, 35, 15)
    d = decide(
        make_inputs(grid_present=False, grid_unknown=True, today_red=True),
        SETTINGS,
        previous,
    )
    assert d.state == "capteur_reseau_indisponible"
    assert d.targets is previous
    assert d.reason == "Capteur de présence réseau indisponible, aucune écriture"


def test_gel_reseau_regroupe_les_deux_etats():
    from custom_components.energy_management.decision import FROZEN_STATES

    assert set(FROZEN_STATES) == {"coupure_reseau", "capteur_reseau_indisponible"}


def test_coupure_sans_precedent():
    d = decide(make_inputs(grid_present=False), SETTINGS)
    assert d.state == "coupure_reseau"
    assert d.targets is None


def test_reserve_toujours_calculee():
    d = decide(make_inputs(vigilance=(("Orages", "Orange"),)), SETTINGS)
    assert d.state == "reseau"
    assert d.reserve == 50
