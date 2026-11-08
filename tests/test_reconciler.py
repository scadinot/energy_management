"""Tests de l'exécuteur des écritures (Reconciler) et de read_actual."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.core import ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.energy_management import reconciler
from custom_components.energy_management.const import CONF_NOTIFY
from custom_components.energy_management.decision import Targets
from custom_components.energy_management.reconciler import (
    CMD_CHARGE,
    Actual,
    Reconciler,
    read_actual,
)

from .const import CHARGE, HIGH, LOW, MOCK_CONF, MODE_SELECT, SBU, UTI

NOTIF = "custom_components.energy_management.reconciler.persistent_notification"


@pytest.fixture(autouse=True)
def short_timeout(monkeypatch):
    """Relecture : 50 ms au lieu de 60 s."""
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 0.05)


@pytest.fixture
def notifs():
    """Compte les notifications persistantes créées et effacées."""
    with patch(f"{NOTIF}.async_create") as create, patch(
        f"{NOTIF}.async_dismiss"
    ) as dismiss:
        yield create, dismiss


def _set_state(hass, mode, low, high):
    hass.states.async_set(MODE_SELECT, mode, dict(hass.states.get(MODE_SELECT).attributes))
    hass.states.async_set(LOW, str(low), dict(hass.states.get(LOW).attributes))
    hass.states.async_set(HIGH, str(high), dict(hass.states.get(HIGH).attributes))


async def test_matin_rouge_ordre_des_appels(hass, base_states, fake_inverter, notifs):
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is True
    assert fake_inverter.calls == [(LOW, 30), (HIGH, 35), (MODE_SELECT, SBU)]


async def test_soir_rouge_ordre_des_appels(hass, base_states, fake_inverter, notifs):
    _set_state(hass, SBU, 30, 35)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("grid", 50, 95, 15), 5) is True
    assert fake_inverter.calls == [(MODE_SELECT, UTI), (HIGH, 95), (LOW, 50)]


async def test_aucune_reecriture(hass, base_states, fake_inverter, notifs):
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("grid", 50, 95, 15), 5) is True
    assert fake_inverter.calls == []


async def test_commande_indisponible_pas_terminee(
    hass, base_states, fake_inverter, notifs
):
    """Rien d'écrit, mais une commande illisible : la séquence n'est pas finie."""
    hass.states.async_set(CHARGE, "unavailable")
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("grid", 50, 95, 15), 5) is False
    assert fake_inverter.calls == []


async def test_attend_la_relecture(hass, base_states, fake_inverter, notifs, monkeypatch):
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 0.5)
    fake_inverter.delay[LOW] = 0.02
    order: list[str] = []
    @callback
    def _record(event) -> None:
        order.append(event.data["entity_id"])

    async_track_state_change_event(hass, [LOW, HIGH], _record)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is True
    # Le 13 n'est écrit (donc relu) qu'après la relecture du 12
    assert order == [LOW, HIGH]


async def test_trois_essais(hass, base_states, fake_inverter, notifs):
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert [c for c in fake_inverter.calls if c[0] == LOW] == [(LOW, 30)] * 3
    # La séquence s'arrête au premier échec
    assert len(fake_inverter.calls) == 3


async def test_echec_seuil_bloque_mode_et_notifie_une_fois(
    hass, base_states, fake_inverter, notifs
):
    create, _ = notifs
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, MOCK_CONF)
    for _ in range(5):
        assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert not [c for c in fake_inverter.calls if c[0] == MODE_SELECT]
    assert create.call_count == 1
    assert create.call_args.kwargs["notification_id"] == "energy_management_echec_low"


async def test_succes_efface_la_notification(hass, base_states, fake_inverter, notifs):
    create, dismiss = notifs
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    fake_inverter.deaf.clear()
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is True
    # Chaque relecture réussie efface la notification de sa commande
    assert [call.args[1] for call in dismiss.call_args_list] == [
        "energy_management_echec_low",
        "energy_management_echec_high",
        "energy_management_echec_mode",
    ]


async def test_echec_efface_si_regle_a_la_main(hass, base_states, fake_inverter, notifs):
    _, dismiss = notifs
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, MOCK_CONF)
    await rec.async_apply(Targets("battery", 30, 35, 15), 5)
    _set_state(hass, UTI, 30, 95)  # seuil bas réglé à la main
    await rec.async_apply(Targets("grid", 30, 95, 15), 5)
    dismiss.assert_called_once()
    assert dismiss.call_args.args[1] == "energy_management_echec_low"


async def test_service_notify_appele(hass, base_states, fake_inverter, notifs):
    calls = async_mock_service(hass, "notify", "test")
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, {**MOCK_CONF, CONF_NOTIFY: "notify.test"})
    for _ in range(3):
        await rec.async_apply(Targets("battery", 30, 35, 15), 5)
    assert len(calls) == 1
    assert "Seuil 12" in calls[0].data["message"]


async def test_une_sequence_a_la_fois(hass, base_states, fake_inverter, notifs, monkeypatch):
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 1)
    monkeypatch.setattr(reconciler, "READBACK_TIMEOUT", 0.5)
    fake_inverter.delay[LOW] = 0.02
    rec = Reconciler(hass, MOCK_CONF)
    first = asyncio.create_task(rec.async_apply(Targets("battery", 30, 35, 15), 5))
    await asyncio.sleep(0)
    assert rec.busy is True
    before = len(fake_inverter.calls)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert len(fake_inverter.calls) == before
    assert await first is True
    assert rec.busy is False


async def test_should_continue(hass, base_states, fake_inverter, notifs):
    rec = Reconciler(hass, MOCK_CONF)
    result = await rec.async_apply(
        Targets("battery", 30, 35, 15),
        5,
        should_continue=lambda: len(fake_inverter.calls) < 1,
    )
    assert result is False
    assert fake_inverter.calls == [(LOW, 30)]


async def test_exception_du_service(hass, base_states, notifs):
    attempts = []

    async def _boom(call: ServiceCall) -> None:
        attempts.append(call.data["entity_id"])
        raise HomeAssistantError("boom")

    hass.services.async_register("number", "set_value", _boom)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert attempts == [LOW] * 3


async def test_service_sans_reponse(hass, base_states, notifs):
    """Un appel qui ne revient jamais compte comme un essai raté ; verrou libéré."""
    attempts: list[str] = []
    never = asyncio.Event()

    async def _hang(call: ServiceCall) -> None:
        attempts.append(call.data["entity_id"])
        await never.wait()

    hass.services.async_register("number", "set_value", _hang)
    rec = Reconciler(hass, MOCK_CONF)
    async with asyncio.timeout(5):
        assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert attempts == [LOW] * 3
    assert rec.busy is False
    # Vérification suivante : la séquence repart
    async with asyncio.timeout(5):
        assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert attempts == [LOW] * 6


async def test_verrou_partage(hass, base_states, fake_inverter, notifs):
    """Deux Reconciler sur le même verrou : un seul écrit à la fois."""
    lock = asyncio.Lock()
    old = Reconciler(hass, MOCK_CONF, lock)
    new = Reconciler(hass, MOCK_CONF, lock)
    async with lock:
        assert old.busy is True
        assert new.busy is True
        assert await new.async_apply(Targets("battery", 30, 35, 15), 5) is False
    assert fake_inverter.calls == []
    assert await new.async_apply(Targets("battery", 30, 35, 15), 5) is True


def test_read_actual(hass, base_states):
    assert read_actual(hass, MOCK_CONF) == Actual("grid", 50.0, 95.0, 15.0)
    hass.states.async_set(MODE_SELECT, "SOL (Solar First)")
    hass.states.async_set(CHARGE, "unavailable")
    assert read_actual(hass, MOCK_CONF) == Actual("SOL (Solar First)", 50.0, 95.0, None)
    hass.states.async_set(MODE_SELECT, "unknown")
    assert read_actual(hass, MOCK_CONF).mode is None


async def test_should_continue_entre_les_essais(hass, base_states, fake_inverter, notifs):
    create, _ = notifs
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, MOCK_CONF)
    result = await rec.async_apply(
        Targets("battery", 30, 35, 15),
        5,
        should_continue=lambda: len(fake_inverter.calls) < 1,
    )
    assert result is False
    assert fake_inverter.calls == [(LOW, 30)]
    create.assert_not_called()


async def test_relecture_non_numerique_est_un_echec(hass, base_states, notifs, caplog):
    """Un seuil relu « unavailable » ne vaut pas relecture réussie."""
    appels: list[str] = []

    async def _indisponible(call: ServiceCall) -> None:
        appels.append(call.data["entity_id"])
        hass.states.async_set(call.data["entity_id"], "unavailable")

    hass.services.async_register("number", "set_value", _indisponible)
    hass.services.async_register("select", "select_option", _indisponible)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    # Trois essais sur le seuil 12, rien d'écrit ensuite (ni seuil 13, ni mode)
    assert appels == [LOW] * 3
    # Aucune exception dans la fonction de relecture (écouteur d'événement)
    assert not [r for r in caplog.records if r.levelname == "ERROR" or r.exc_info]


async def test_service_notify_introuvable(hass, base_states, fake_inverter, notifs):
    """Un service de notification introuvable ne fait pas échouer la réconciliation."""
    create, _ = notifs
    fake_inverter.deaf.add(LOW)
    rec = Reconciler(hass, {**MOCK_CONF, CONF_NOTIFY: "notify.absent"})
    assert await rec.async_apply(Targets("battery", 30, 35, 15), 5) is False
    create.assert_called_once()


def test_read_actual_nombre_non_fini(hass, base_states):
    """nan et inf ne sont pas des valeurs relues."""
    hass.states.async_set(LOW, "nan")
    hass.states.async_set(HIGH, "inf")
    hass.states.async_set(CHARGE, "-inf")
    assert read_actual(hass, MOCK_CONF) == Actual("grid", None, None, None)


async def test_notification_du_mode_avec_l_option(
    hass, base_states, fake_inverter, notifs
):
    """L'échec du mode cite l'option du select, pas grid / battery."""
    create, _ = notifs
    _set_state(hass, SBU, 50, 95)
    fake_inverter.deaf.add(MODE_SELECT)
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("grid", 50, 95, 15), 5) is False
    message = create.call_args.args[1]
    assert UTI in message
    assert "grid" not in message


async def test_succes_efface_une_notification_d_avant_rechargement(
    hass, base_states, fake_inverter, notifs
):
    """Nouveau Reconciler (rien en échec chez lui) : le succès efface quand même."""
    _, dismiss = notifs
    hass.states.async_set(LOW, "40", dict(hass.states.get(LOW).attributes))
    rec = Reconciler(hass, MOCK_CONF)
    assert await rec.async_apply(Targets("grid", 50, 95, 15), 5) is True
    dismiss.assert_called_once()
    assert dismiss.call_args.args[1] == "energy_management_echec_low"


async def test_async_apply_only(hass, base_states, fake_inverter, notifs):
    """Seule la commande visée est écrite ; les seuils en écart restent en l'état."""
    rec = Reconciler(hass, MOCK_CONF)
    result = await rec.async_apply(Targets("grid", 30, 35, 20), 5, only={CMD_CHARGE})
    assert fake_inverter.calls == [(CHARGE, 20)]
    # Terminé pour les commandes visées, même si les seuils restent en écart
    assert result is True
