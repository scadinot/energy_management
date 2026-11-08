"""Tests du manager, du cycle de vie et de l'interrupteur Pilotage."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.energy_management import reconciler
from custom_components.energy_management.const import (
    CONF_RESERVE_NORMAL,
    DOMAIN,
    signal_update,
)
from custom_components.energy_management.manager import EnergyManager

from .const import (
    COLOR_TODAY,
    GRID,
    HIGH,
    LOW,
    MODE_SELECT,
    SBU,
    UTI,
)

RESTORED_ID = "switch.energy_management_pilotage"


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


def _restore(hass: HomeAssistant, entry: MockConfigEntry, state: str) -> None:
    """Prépare le registre et l'état restauré de l'interrupteur Pilotage."""
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "switch",
        DOMAIN,
        f"{entry.entry_id}_pilotage",
        suggested_object_id="energy_management_pilotage",
        config_entry=entry,
    )
    mock_restore_cache(hass, [State(RESTORED_ID, state)])


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
    assert manager.reset_pending is False
    count = len(fake_inverter.calls)
    await _tick(hass)
    assert len(fake_inverter.calls) == count


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
    assert manager.reset_pending is False
    assert hass.states.get(RESTORED_ID).state == "off"


async def test_redemarrage_pilotage_actif(hass, base_states, fake_inverter, mock_entry):
    _set(hass, COLOR_TODAY, "Rouge")
    _restore(hass, mock_entry, "on")
    manager = await _setup(hass, mock_entry)
    assert manager.pilotage is True
    assert manager.reset_pending is False
    assert hass.states.get(RESTORED_ID).state == "on"
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35), (MODE_SELECT, SBU)]
    assert manager.gaps == []


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
    assert manager.reset_pending is True
    await _tick(hass)
    assert fake_inverter.calls == []
    _set(hass, GRID, "on")
    await hass.async_block_till_done()
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]
    assert manager.reset_pending is False


async def test_remise_annulee_si_pilotage_reactive(
    hass, base_states, fake_inverter, mock_entry
):
    manager = await _matin_rouge(hass, mock_entry, fake_inverter)
    fake_inverter.calls.clear()
    _set(hass, GRID, "off")
    await hass.async_block_till_done()
    await _pilotage(hass, mock_entry, False)
    await _pilotage(hass, mock_entry, True)
    assert manager.reset_pending is False
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
