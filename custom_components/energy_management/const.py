"""Constantes de l'extension Energy Management."""
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

DOMAIN = "energy_management"

# Étape 1 de l'assistant : entrées
CONF_COLOR_TODAY = "color_today"
CONF_COLOR_TOMORROW = "color_tomorrow"
CONF_OFF_PEAK = "off_peak"
CONF_VIGILANCE = "vigilance"
CONF_PHENOMENA = "phenomena"
CONF_SOC = "soc"
CONF_EV_POWER = "ev_power"
CONF_GRID = "grid_presence"

# Étape 2 : commandes de l'onduleur
CONF_MODE_SELECT = "mode_select"
CONF_LOW = "low_threshold"
CONF_HIGH = "high_threshold"
CONF_CHARGE = "charge_current"

# Étape 3 : valeurs et réglages
CONF_OPTION_GRID = "option_grid"
CONF_OPTION_BATTERY = "option_battery"
CONF_RESERVE_NORMAL = "reserve_normal"
CONF_RESERVE_VIGILANCE = "reserve_vigilance"
CONF_GAP = "gap"
CONF_LOW_NORMAL = "low_normal"
CONF_HIGH_NORMAL = "high_normal"
CONF_CHARGE_NORMAL = "charge_normal"
CONF_CHARGE_BOOST = "charge_boost"
CONF_EV_THRESHOLD = "ev_threshold"
CONF_NOTIFY = "notify"

# Valeurs par défaut (spec § 4.3)
DEFAULTS: dict[str, Any] = {
    CONF_RESERVE_NORMAL: 30,
    CONF_RESERVE_VIGILANCE: 50,
    CONF_GAP: 5,
    CONF_LOW_NORMAL: 50,
    CONF_HIGH_NORMAL: 95,
    CONF_CHARGE_NORMAL: 15,
    CONF_CHARGE_BOOST: 20,
    CONF_EV_THRESHOLD: 500,
}

# Noms exacts des attributs de l'entité de vigilance
DEFAULT_PHENOMENA: list[str] = [
    "Vent violent",
    "Orages",
    "Neige-verglas",
    "Grand-froid",
    "Pluie-inondation",
]
KNOWN_PHENOMENA: list[str] = [
    *DEFAULT_PHENOMENA,
    "Inondation",
    "Vagues-submersion",
    "Canicule",
    "Avalanches",
]

# Niveaux de vigilance qui comptent, et couleur rouge Tempo
ACTIVE_LEVELS = ("Orange", "Rouge")
RED = "Rouge"

# Relecture des commandes
NUMBER_TOLERANCE = 0.5  # écart toléré entre valeur lue et valeur voulue
READBACK_TIMEOUT = 60  # secondes d'attente maximale de la relecture
WRITE_ATTEMPTS = 3  # essais par commande

UPDATE_INTERVAL = timedelta(minutes=1)


def signal_update(entry_id: str) -> str:
    """Nom du signal envoyé aux entités à chaque nouveau calcul."""
    return f"{DOMAIN}_update_{entry_id}"


def conf_of(entry: ConfigEntry) -> dict[str, Any]:
    """Configuration en vigueur d'une entrée.

    Les options, dès qu'elles existent, portent la configuration complète
    (l'assistant des options enregistre tout) : on les prend seules. Une
    fusion avec `entry.data` ferait revenir un champ facultatif vidé dans
    les options (présence réseau, notification).
    """
    return dict(entry.options or entry.data)
