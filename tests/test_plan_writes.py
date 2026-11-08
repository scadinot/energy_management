"""Tests de l'ordre des écritures (pur, sans Home Assistant)."""
from __future__ import annotations

from itertools import permutations

from custom_components.energy_management.decision import (
    MODE_BATTERY,
    MODE_GRID,
    Targets,
)
from custom_components.energy_management.reconciler import (
    CMD_CHARGE,
    CMD_HIGH,
    CMD_LOW,
    CMD_MODE,
    Actual,
    Write,
    compute_gaps,
    plan_writes,
)

GAP = 5
NORMAL = Targets(MODE_GRID, 50, 95, 15)
BOOST = Targets(MODE_GRID, 50, 95, 20)
RED = Targets(MODE_BATTERY, 30, 35, 15)


def apply(actual: Actual, writes: list[Write]) -> list[tuple[float, float]]:
    """Rejoue les écritures ; renvoie les couples (bas, haut) après chaque écriture de seuil."""
    low, high = actual.low, actual.high
    steps: list[tuple[float, float]] = []
    for write in writes:
        if write.command == CMD_LOW:
            low = write.value
            steps.append((low, high))
        elif write.command == CMD_HIGH:
            high = write.value
            steps.append((low, high))
    return steps


def test_matin_rouge():
    actual = Actual(MODE_GRID, 50, 95, 15)
    writes = plan_writes(actual, RED, GAP)
    assert writes == [
        Write(CMD_LOW, 30),
        Write(CMD_HIGH, 35),
        Write(CMD_MODE, MODE_BATTERY),
    ]
    assert apply(actual, writes) == [(30, 95), (30, 35)]


def test_soir_rouge():
    actual = Actual(MODE_BATTERY, 30, 35, 15)
    writes = plan_writes(actual, NORMAL, GAP)
    assert writes == [
        Write(CMD_MODE, MODE_GRID),
        Write(CMD_HIGH, 95),
        Write(CMD_LOW, 50),
    ]
    assert apply(actual, writes) == [(30, 95), (50, 95)]


def test_vigilance_en_journee():
    actual = Actual(MODE_BATTERY, 30, 35, 15)
    writes = plan_writes(actual, Targets(MODE_BATTERY, 50, 55, 15), GAP)
    assert writes == [Write(CMD_HIGH, 55), Write(CMD_LOW, 50)]


def test_vigilance_levee():
    actual = Actual(MODE_BATTERY, 50, 55, 15)
    writes = plan_writes(actual, RED, GAP)
    assert writes == [Write(CMD_LOW, 30), Write(CMD_HIGH, 35)]


def test_invariant_a_chaque_etape():
    points = [(50, 95), (30, 35), (50, 55), (30, 95)]
    for start, end in permutations(points, 2):
        actual = Actual(MODE_GRID, start[0], start[1], 15)
        desired = Targets(MODE_GRID, end[0], end[1], 15)
        steps = apply(actual, plan_writes(actual, desired, GAP))
        assert steps, (start, end)
        for low, high in steps:
            assert high >= low + GAP, (start, end, steps)
        assert steps[-1] == end


def test_seuils_hors_invariant():
    actual = Actual(MODE_GRID, 50, 50, 15)
    writes = plan_writes(actual, RED, GAP)
    assert writes == [
        Write(CMD_LOW, 30),
        Write(CMD_HIGH, 35),
        Write(CMD_MODE, MODE_BATTERY),
    ]


def test_rien_a_ecrire():
    assert plan_writes(Actual(MODE_GRID, 50, 95, 15), NORMAL, GAP) == []


def test_tolerance():
    assert plan_writes(Actual(MODE_GRID, 50.3, 94.6, 15.0), NORMAL, GAP) == []


def test_charge_en_dernier():
    actual = Actual(MODE_GRID, 50, 95, 15)
    assert plan_writes(actual, BOOST, GAP) == [Write(CMD_CHARGE, 20)]
    desired = Targets(MODE_BATTERY, 30, 35, 20)
    writes = plan_writes(actual, desired, GAP)
    assert [w.command for w in writes] == [CMD_LOW, CMD_HIGH, CMD_MODE, CMD_CHARGE]


def test_seuil_indisponible_bloque_batterie():
    actual = Actual(MODE_GRID, None, 95, 15)
    assert plan_writes(actual, RED, GAP) == []


def test_seuil_13_indisponible_retour_reseau():
    actual = Actual(MODE_BATTERY, 30, None, 15)
    assert plan_writes(actual, NORMAL, GAP) == [Write(CMD_MODE, MODE_GRID)]


def test_seuil_indisponible_charge_ecrite():
    actual = Actual(MODE_GRID, None, 95, 15)
    assert plan_writes(actual, BOOST, GAP) == [Write(CMD_CHARGE, 20)]


def test_mode_indisponible():
    actual = Actual(None, 50, 95, 15)
    assert plan_writes(actual, RED, GAP) == [Write(CMD_LOW, 30), Write(CMD_HIGH, 35)]


def test_mode_inconnu():
    actual = Actual("SOL (Solar First)", 50, 95, 15)
    assert plan_writes(actual, NORMAL, GAP) == [Write(CMD_MODE, MODE_GRID)]


def test_compute_gaps():
    actual = Actual(MODE_GRID, None, 95, 20)
    assert compute_gaps(actual, NORMAL) == [CMD_LOW, CMD_CHARGE]
