"""Tests du manager, du cycle de vie et de l'interrupteur Pilotage."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, State, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import restore_state
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)

from custom_components.energy_management import manager as manager_module
from custom_components.energy_management import reconciler
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
    CONF_OFF_PEAK,
    CONF_OPTION_BATTERY,
    CONF_OPTION_GRID,
    CONF_PHENOMENA,
    CONF_RESERVE_NORMAL,
    CONF_RESERVE_VIGILANCE,
    CONF_SOC,
    CONF_VIGILANCE,
    DOMAIN,
    signal_update,
)
from custom_components.energy_management.manager import EnergyManager
from custom_components.energy_management.reconciler import (
    CMD_CHARGE,
    CMD_HIGH,
    CMD_MODE,
    COMMANDS,
)

from .const import (
    CHARGE,
    COLOR_TODAY,
    GRID,
    HIGH,
    LOW,
    MODE_SELECT,
    SBU,
    UTI,
)

RESTORED_ID = "switch.energy_management_pilotage"

# Champs des trois étapes des options
_STEP_1 = [
    CONF_COLOR_TODAY,
    CONF_COLOR_TOMORROW,
    CONF_OFF_PEAK,
    CONF_VIGILANCE,
    CONF_PHENOMENA,
    CONF_SOC,
    CONF_EV_POWER,
    CONF_GRID,
]
_STEP_2 = [CONF_MODE_SELECT, CONF_LOW, CONF_HIGH, CONF_CHARGE]
_STEP_3 = [
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
def short_timeout(monkeypatch):
    """Relecture : 100 ms au lieu de 60 s."""
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 0.1)


def _set(hass: HomeAssistant, entity_id: str, value: str) -> None:
    """Change l'état d'une entité en gardant ses attributs."""
    current = hass.states.get(entity_id)
    attributes = dict(current.attributes) if current else {}
    hass.states.async_set(entity_id, value, attributes)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> EnergyManager:
    """Installe l'entrée et renvoie son manager."""
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


def _switch_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Identifiant de l'interrupteur Pilotage, lu dans le registre."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry.entry_id}_pilotage"
    )
    assert entity_id is not None
    return entity_id


async def _pilotage(hass: HomeAssistant, entry: MockConfigEntry, on: bool) -> None:
    """Allume ou coupe le Pilotage par le service, puis attend la fin des calculs."""
    await hass.services.async_call(
        "switch",
        "turn_on" if on else "turn_off",
        {"entity_id": _switch_id(hass, entry)},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _tick(hass: HomeAssistant, seconds: int = 61) -> None:
    """Avance le temps et attend les calculs déclenchés par le minuteur."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


def _restore(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    state: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Prépare le registre et l'état restauré (et ses données en plus) du Pilotage."""
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "switch",
        DOMAIN,
        f"{entry.entry_id}_pilotage",
        suggested_object_id="energy_management_pilotage",
        config_entry=entry,
    )
    if extra is None:
        mock_restore_cache(hass, [State(RESTORED_ID, state)])
    else:
        mock_restore_cache_with_extra_data(hass, [(State(RESTORED_ID, state), extra)])


async def _options_sans_reseau(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Passe les trois étapes des options en vidant la présence réseau."""
    conf = {**entry.data, **entry.options}
    steps = (
        [key for key in _STEP_1 if key != CONF_GRID],
        _STEP_2,
        _STEP_3,
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    for keys in steps:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {key: conf[key] for key in keys if key in conf}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def _matin_rouge(hass, entry, fake_inverter) -> EnergyManager:
    """Pilotage actif un jour rouge : onduleur en SBU 30/35."""
    manager = await _setup(hass, entry)
    await _pilotage(hass, entry, True)
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35), (MODE_SELECT, SBU)]
    return manager


async def test_pilotage_coupe_aucune_ecriture(
    hass, base_states, fake_inverter, mock_entry
):
    manager = await _setup(hass, mock_entry)
    assert manager.pilotage is False
    assert hass.states.get(_switch_id(hass, mock_entry)).state == "off"
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    assert manager.decision.state == "batterie"
    assert manager.gaps == ["mode", "low", "high"]
    await _tick(hass)
    assert fake_inverter.calls == []


async def test_pilotage_actif_matin_rouge(hass, base_states, fake_inverter, mock_entry):
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    assert manager.pilotage is True
    assert hass.states.get(_switch_id(hass, mock_entry)).state == "on"
    # Écarts recalculés après la séquence
    assert manager.gaps == []


async def test_minuteur(hass, base_states, fake_inverter, mock_entry):
    await _setup(hass, mock_entry)
    await _pilotage(hass, mock_entry, True)
    assert fake_inverter.calls == []
    _set(hass, LOW, "40")
    await hass.async_block_till_done()
    assert fake_inverter.calls == []
    await _tick(hass)
    assert fake_inverter.calls == [(LOW, 50)]


async def test_commandes_non_ecoutees(hass, base_states, fake_inverter, mock_entry):
    manager = await _setup(hass, mock_entry)
    signals: list[None] = []

    @callback
    def _count() -> None:
        signals.append(None)

    unsub = async_dispatcher_connect(hass, signal_update(mock_entry.entry_id), _count)
    for entity_id, value in ((LOW, "40"), (HIGH, "90"), (MODE_SELECT, SBU)):
        _set(hass, entity_id, value)
    await hass.async_block_till_done()
    # Aucun calcul : écarts inchangés, aucun signal
    assert signals == []
    assert manager.gaps == []
    await _tick(hass)
    assert signals
    assert manager.gaps == ["mode", "low", "high"]
    assert fake_inverter.calls == []
    unsub()


async def test_coupure_pilotage_remet_les_normales(
    hass, base_states, fake_inverter, mock_entry
):
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    await _pilotage(hass, mock_entry, False)
    assert fake_inverter.calls[-3:] == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == set()
    count = len(fake_inverter.calls)
    await _tick(hass)
    assert len(fake_inverter.calls) == count


async def test_remise_attend_le_retour_du_select(
    hass, base_states, fake_inverter, mock_entry
):
    """Select indisponible à la coupure : la remise reste due jusqu'au mode réseau."""
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    _set(hass, MODE_SELECT, "unavailable")
    await hass.async_block_till_done()
    await _pilotage(hass, mock_entry, False)
    # Seuils remis, mode illisible donc non écrit : remise pas terminée
    assert fake_inverter.calls == [(HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == {CMD_MODE}
    # Le select revient, toujours en SBU : la vérification suivante finit la remise
    _set(hass, MODE_SELECT, SBU)
    await hass.async_block_till_done()
    await _tick(hass)
    assert fake_inverter.calls[-1] == (MODE_SELECT, UTI)
    assert manager.reset_pending == set()
    # Remise finie : plus aucune écriture ensuite
    count = len(fake_inverter.calls)
    await _tick(hass)
    assert len(fake_inverter.calls) == count


async def test_remise_tout_indisponible_reste_due(
    hass, base_states, fake_inverter, mock_entry
):
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    for entity_id in (MODE_SELECT, LOW, HIGH, CHARGE):
        _set(hass, entity_id, "unavailable")
    await hass.async_block_till_done()
    await _pilotage(hass, mock_entry, False)
    assert fake_inverter.calls == []
    assert manager.reset_pending == set(COMMANDS)
    await _tick(hass)
    assert fake_inverter.calls == []
    assert manager.reset_pending == set(COMMANDS)


async def test_redemarrage_pilotage_coupe_aucune_ecriture(
    hass, base_states, fake_inverter, mock_entry
):
    _set(hass, MODE_SELECT, SBU)
    _set(hass, LOW, "30")
    _set(hass, HIGH, "35")
    _restore(hass, mock_entry, "off")
    manager = await _setup(hass, mock_entry)
    assert _switch_id(hass, mock_entry) == RESTORED_ID
    await _tick(hass, 61)
    await _tick(hass, 122)
    assert fake_inverter.calls == []
    assert manager.pilotage is False
    assert manager.reset_pending == set()
    assert hass.states.get(RESTORED_ID).state == "off"


async def test_redemarrage_pilotage_actif(hass, base_states, fake_inverter, mock_entry):
    _set(hass, COLOR_TODAY, "Rouge")
    _restore(hass, mock_entry, "on")
    manager = await _setup(hass, mock_entry)
    assert manager.pilotage is True
    assert manager.reset_pending == set()
    assert hass.states.get(RESTORED_ID).state == "on"
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35), (MODE_SELECT, SBU)]
    assert manager.gaps == []


async def test_aucune_ecriture_avant_demarrage_complet(
    hass, base_states, fake_inverter, mock_entry
):
    """Redémarrage un jour rouge, Tempo pas encore chargé : pas de SBU → UTI → SBU."""
    _set(hass, MODE_SELECT, SBU)
    _set(hass, LOW, "30")
    _set(hass, HIGH, "35")
    _set(hass, COLOR_TODAY, "unknown")
    _restore(hass, mock_entry, "on")
    hass.set_state(CoreState.starting)
    manager = await _setup(hass, mock_entry)
    assert manager.pilotage is True
    # Couleur inconnue = non rouge : calculé et affiché, mais rien d'écrit
    assert manager.decision.state == "reseau"
    assert manager.gaps == ["mode", "low", "high"]
    await _tick(hass)
    assert fake_inverter.calls == []
    # Tempo chargé avant la fin du démarrage
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    assert fake_inverter.calls == []
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    # Déjà en SBU 30/35 : rien à écrire
    assert fake_inverter.calls == []
    assert manager.gaps == []


async def test_matin_rouge_au_demarrage_complet(
    hass, base_states, fake_inverter, mock_entry
):
    _set(hass, COLOR_TODAY, "unknown")
    _restore(hass, mock_entry, "on")
    hass.set_state(CoreState.starting)
    manager = await _setup(hass, mock_entry)
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    assert manager.decision.state == "batterie"
    assert fake_inverter.calls == []
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35), (MODE_SELECT, SBU)]


async def test_remise_differee_au_demarrage_complet(
    hass, base_states, fake_inverter, mock_entry
):
    _set(hass, MODE_SELECT, SBU)
    _set(hass, LOW, "30")
    _set(hass, HIGH, "35")
    _restore(hass, mock_entry, "off", {"remise_en_attente": True})
    hass.set_state(CoreState.starting)
    manager = await _setup(hass, mock_entry)
    await _tick(hass)
    assert fake_inverter.calls == []
    assert manager.reset_pending == set(COMMANDS)
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == set()


async def test_reseau_absent_gel(hass, base_states, fake_inverter, mock_entry):
    manager = await _setup(hass, mock_entry)
    await _pilotage(hass, mock_entry, True)
    _set(hass, GRID, "off")
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    assert manager.decision.state == "coupure_reseau"
    # Seuil 12 modifié à la main : les cibles conservées sont en écart, mais gel
    _set(hass, LOW, "40")
    await _tick(hass)
    assert fake_inverter.calls == []
    assert manager.decision.state == "coupure_reseau"
    assert manager.gaps == ["low"]


async def test_remise_reportee_pendant_coupure(
    hass, base_states, fake_inverter, mock_entry
):
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    _set(hass, GRID, "off")
    await hass.async_block_till_done()
    await _pilotage(hass, mock_entry, False)
    assert fake_inverter.calls == []
    assert manager.reset_pending == set(COMMANDS)
    await _tick(hass)
    assert fake_inverter.calls == []
    _set(hass, GRID, "on")
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == set()


async def test_remise_annulee_si_pilotage_reactive(
    hass, base_states, fake_inverter, mock_entry
):
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    _set(hass, GRID, "off")
    await hass.async_block_till_done()
    await _pilotage(hass, mock_entry, False)
    await _pilotage(hass, mock_entry, True)
    assert manager.reset_pending == set()
    _set(hass, GRID, "on")
    await hass.async_block_till_done()
    # Jour rouge toujours en cours : déjà en SBU 30/35, rien à écrire
    assert fake_inverter.calls == []


async def test_pilotage_off_interrompt_sequence(
    hass, base_states, fake_inverter, mock_entry, monkeypatch
):
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 1)
    fake_inverter.delay[HIGH] = 0.5
    manager = await _setup(hass, mock_entry)
    await _pilotage(hass, mock_entry, True)
    _set(hass, COLOR_TODAY, "Rouge")
    # Attendre que le 13 soit écrit et sa relecture en attente
    async with asyncio.timeout(5):
        while (HIGH, 35) not in fake_inverter.calls:
            await asyncio.sleep(0.01)
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35)]
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": _switch_id(hass, mock_entry)}, blocking=True
    )
    assert manager.pilotage is False
    await hass.async_block_till_done()
    assert (MODE_SELECT, SBU) not in fake_inverter.calls
    # La remise aux normales peut partir ensuite ; jamais de SBU
    await _tick(hass)
    assert (MODE_SELECT, SBU) not in fake_inverter.calls


async def test_erreur_inattendue_journalisee(
    hass, base_states, fake_inverter, mock_entry, caplog
):
    manager = await _setup(hass, mock_entry)
    with patch.object(
        reconciler.Reconciler, "async_apply", side_effect=ValueError("boum")
    ):
        await _pilotage(hass, mock_entry, True)
        await _tick(hass)
    assert "boum" in caplog.text
    assert manager.pilotage is True
    assert manager.decision.state == "reseau"
    # Erreur dans la lecture des entrées : journalisée aussi
    with patch.object(
        manager_module, "read_inputs", side_effect=KeyError("entrée")
    ):
        await _tick(hass)
    assert "entrée" in caplog.text
    # Patch retiré : le calcul suivant fonctionne normalement
    _set(hass, LOW, "40")
    await _tick(hass)
    assert fake_inverter.calls == [(LOW, 50)]
    assert manager.gaps == []


async def test_coupure_reseau_interrompt_sequence(
    hass, base_states, fake_inverter, mock_entry, monkeypatch
):
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 1)
    fake_inverter.delay[HIGH] = 0.5
    manager = await _setup(hass, mock_entry)
    await _pilotage(hass, mock_entry, True)
    _set(hass, COLOR_TODAY, "Rouge")
    # Attendre que le 13 soit écrit et sa relecture en attente
    async with asyncio.timeout(5):
        while (HIGH, 35) not in fake_inverter.calls:
            await asyncio.sleep(0.01)
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35)]
    _set(hass, GRID, "off")
    await hass.async_block_till_done()
    assert manager.pilotage is True
    assert (MODE_SELECT, SBU) not in fake_inverter.calls
    await _tick(hass)
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35)]
    assert manager.decision.state == "coupure_reseau"


async def test_remise_conservee_au_redemarrage(
    hass, base_states, fake_inverter, mock_entry
):
    _set(hass, MODE_SELECT, SBU)
    _set(hass, LOW, "30")
    _set(hass, HIGH, "35")
    _restore(hass, mock_entry, "off", {"remise_en_attente": True})
    manager = await _setup(hass, mock_entry)
    assert manager.pilotage is False
    assert fake_inverter.calls[-3:] == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == set()


async def test_remise_conservee_au_rechargement(
    hass, base_states, fake_inverter, mock_entry
):
    await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    _set(hass, GRID, "off")
    await hass.async_block_till_done()
    await _pilotage(hass, mock_entry, False)
    assert mock_entry.runtime_data.reset_pending == set(COMMANDS)
    await hass.config_entries.async_reload(mock_entry.entry_id)
    await hass.async_block_till_done()
    manager = mock_entry.runtime_data
    assert manager.pilotage is False
    assert manager.reset_pending == set(COMMANDS)
    assert fake_inverter.calls == []
    _set(hass, GRID, "on")
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == set()


async def test_verrou_commun_au_rechargement(
    hass, base_states, fake_inverter, mock_entry
):
    """Le nouveau manager voit occupé le verrou tenu par l'ancien."""
    old = await _setup(hass, mock_entry)
    await hass.config_entries.async_reload(mock_entry.entry_id)
    await hass.async_block_till_done()
    new = mock_entry.runtime_data
    assert new is not old
    async with old._reconciler._lock:
        assert new._reconciler.busy is True
    assert new._reconciler.busy is False


async def test_options_retire_presence_reseau(
    hass, base_states, fake_inverter, mock_entry
):
    await _setup(hass, mock_entry)
    await _options_sans_reseau(hass, mock_entry)
    manager = mock_entry.runtime_data
    assert CONF_GRID not in manager.conf
    # Capteur retiré puis indisponible : plus de gel
    _set(hass, GRID, "unavailable")
    await hass.async_block_till_done()
    assert manager.decision.state == "reseau"
    # Les options suivantes ne le proposent plus
    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    schema = result["data_schema"].schema
    grid = next(key for key in schema if key == CONF_GRID)
    assert not (grid.description or {}).get("suggested_value")
    hass.config_entries.options.async_abort(result["flow_id"])


async def test_options_rechargent_sans_remise(
    hass, base_states, fake_inverter, mock_entry
):
    await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    hass.config_entries.async_update_entry(
        mock_entry, options={**mock_entry.data, CONF_RESERVE_NORMAL: 40}
    )
    await hass.async_block_till_done()
    manager = mock_entry.runtime_data
    assert manager.settings.reserve_normal == 40
    # Pilotage conservé au rechargement : aucune remise, nouvelle réserve appliquée
    assert manager.pilotage is True
    assert fake_inverter.calls == [(HIGH, 45), (LOW, 40)]


async def test_dechargement(hass, base_states, fake_inverter, mock_entry):
    manager = await _setup(hass, mock_entry)
    await _pilotage(hass, mock_entry, True)
    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
    _set(hass, LOW, "40")
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    await _tick(hass)
    assert fake_inverter.calls == []
    assert manager.gaps == []
    assert manager.decision.state == "reseau"


async def test_echec_du_panneau_arrete_le_manager(
    hass, base_states, fake_inverter, mock_entry
):
    """Une erreur après le démarrage du manager ne le laisse pas tourner."""
    with patch(
        "custom_components.energy_management.async_register_panel",
        side_effect=RuntimeError("panneau"),
    ):
        mock_entry.add_to_hass(hass)
        assert not await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    manager = mock_entry.runtime_data
    assert manager._running is False
    manager.pilotage = True
    _set(hass, COLOR_TODAY, "Rouge")
    await hass.async_block_till_done()
    await _tick(hass)
    assert fake_inverter.calls == []


async def _remise_sans_charge(hass, entry, fake_inverter) -> EnergyManager:
    """Jour rouge en SBU 30/35, entité de charge supprimée, puis Pilotage coupé."""
    manager = await _matin_rouge(hass, entry, fake_inverter)
    fake_inverter.calls.clear()
    hass.states.async_remove(CHARGE)
    await hass.async_block_till_done()
    await _pilotage(hass, entry, False)
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == {CMD_CHARGE}
    return manager


def _restore_data(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """Données de restauration que l'interrupteur enregistrerait maintenant."""
    stored = next(
        s
        for s in restore_state.async_get(hass).async_get_stored_states()
        if s.state.entity_id == entity_id
    )
    assert stored.extra_data is not None
    return stored.extra_data.as_dict()


async def test_remise_ne_reecrit_pas_un_reglage_manuel(
    hass, base_states, fake_inverter, mock_entry
):
    """Charge définitivement absente : la remise ne réécrit pas un seuil réglé à la main."""
    await _remise_sans_charge(hass, mock_entry, fake_inverter)
    switch_id = _switch_id(hass, mock_entry)
    assert _restore_data(hass, switch_id) == {"remise_en_attente": [CMD_CHARGE]}
    _set(hass, LOW, "40")
    await hass.async_block_till_done()
    await _tick(hass, 61)
    await _tick(hass, 122)
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]


async def test_restauration_ancien_format_booleen(
    hass, base_states, fake_inverter, mock_entry
):
    _set(hass, MODE_SELECT, SBU)
    _set(hass, LOW, "30")
    _set(hass, HIGH, "35")
    _restore(hass, mock_entry, "off", {"remise_en_attente": True})
    hass.set_state(CoreState.starting)
    manager = await _setup(hass, mock_entry)
    # Avant le premier calcul effectif : toutes les commandes à remettre
    assert manager.reset_pending == set(COMMANDS)
    assert fake_inverter.calls == []
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending == set()


async def test_restauration_liste_de_commandes(
    hass, base_states, fake_inverter, mock_entry
):
    """Nouveau format : seules les commandes listées sont remises ; inconnues ignorées."""
    _set(hass, MODE_SELECT, SBU)
    _set(hass, LOW, "30")
    _set(hass, HIGH, "35")
    _restore(
        hass, mock_entry, "off", {"remise_en_attente": [CMD_MODE, CMD_HIGH, "inconnue"]}
    )
    hass.set_state(CoreState.starting)
    manager = await _setup(hass, mock_entry)
    assert manager.reset_pending == {CMD_MODE, CMD_HIGH}
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    # Le seuil 12, absent de la liste, garde sa valeur (30/95 respecte l'écart)
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95)]
    assert hass.states.get(LOW).state == "30"
    assert manager.reset_pending == set()


async def test_restauration_ancien_format_faux(
    hass, base_states, fake_inverter, mock_entry
):
    """Ancien format, remise déjà faite : rien à remettre, aucune écriture."""
    _set(hass, MODE_SELECT, SBU)
    _restore(hass, mock_entry, "off", {"remise_en_attente": False})
    manager = await _setup(hass, mock_entry)
    await _tick(hass)
    assert manager.reset_pending == set()
    assert fake_inverter.calls == []


async def test_coupure_deja_coupe_sans_remise(
    hass, base_states, fake_inverter, mock_entry
):
    """Couper un Pilotage déjà coupé ne demande aucune remise."""
    manager = await _setup(hass, mock_entry)
    _set(hass, LOW, "40")
    await _pilotage(hass, mock_entry, False)
    await _tick(hass)
    assert manager.reset_pending == set()
    assert fake_inverter.calls == []
