"""Panneau : entités de l'extension retrouvées même après un renommage.

Exécute tests/panel_harness.js avec Node (DOM minimal, hass simulé).
Sauté si Node n'est pas installé.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "panel_harness.js"
# Linux (CI) : node ; WSL : le node.exe de Windows, accessible par l'interopérabilité
NODE = shutil.which("node") or shutil.which("node.exe")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node absent")


def _chemin_pour_node(chemin: Path) -> str:
    """Chemin lisible par Node : converti pour node.exe lancé depuis WSL."""
    if NODE.endswith(".exe") and shutil.which("wslpath"):
        return subprocess.run(
            ["wslpath", "-w", str(chemin)], check=True, capture_output=True, text=True
        ).stdout.strip()
    return str(chemin)


@pytest.fixture(scope="module")
def rendu() -> dict:
    sortie = subprocess.run(
        [NODE, _chemin_pour_node(HARNESS)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return json.loads(sortie.stdout.decode("utf-8"))


def test_entites_renommees_retrouvees(rendu):
    """Identifiants renommés après l'enregistrement : le panneau les retrouve."""
    r = rendu["renamed"]
    assert "Réseau" in r["decision"]
    assert "Fonctionnement normal" in r["decision"]
    assert "30 %" in r["battery"]
    assert "Écart : Seuil 12" in r["header"]
    # Pilotage trouvé (actif) et non le leurre d'une autre intégration (off)
    assert "checked" in r["header"] and "disabled" not in r["header"]
    assert "Pilotage actif" in r["header"]
    # Valeur voulue lue dans les attributs de Mode voulu
    assert "50 %" in r["inverters"]


def test_repli_sur_la_configuration(rendu):
    """Sans hass.entities, les identifiants de la configuration servent encore."""
    r = rendu["fallback"]
    assert "Réseau" in r["decision"]
    assert "30 %" in r["battery"]


def test_renommage_apres_le_premier_rendu(rendu):
    """Un nouvel objet hass.entities est relu : le renommage suivant est suivi."""
    r = rendu["renamedLater"]
    assert "Réseau" in r["decision"]
    assert "Pilotage actif" in r["header"]


def test_presence_reseau_coupure_et_capteur_distincts(rendu):
    """Vraie coupure, capteur illisible ou absent, non configuré : quatre libellés."""
    g = rendu["grid"]
    assert "Présent" in g["on"]["battery"]
    assert "Absent" in g["off"]["battery"]
    assert "Coupure réseau" in g["off"]["decision"]
    for cas in ("unavailable", "missing"):
        assert "Capteur indisponible" in g[cas]["battery"]
        assert "Absent" not in g[cas]["battery"]
        assert "Non configurée" not in g[cas]["battery"]
        assert "Capteur réseau indisponible" in g[cas]["decision"]
    assert "Non configurée" in g["notConfigured"]["battery"]


def test_entites_introuvables(rendu):
    """Rien dans le registre ni dans la configuration : affichage « — »."""
    r = rendu["lost"]
    assert "Réseau" not in r["decision"]
    assert "—" in r["decision"]
    assert "disabled" in r["header"]
