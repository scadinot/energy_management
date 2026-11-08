"""Identifiants réels (relevés le 08/11/2026) et configuration de test."""
from __future__ import annotations

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
    DEFAULT_PHENOMENA,
    DEFAULTS,
)

COLOR_TODAY = "sensor.rte_tempo_couleur_actuelle"
COLOR_TOMORROW = "sensor.rte_tempo_prochaine_couleur"
OFF_PEAK = "binary_sensor.rte_tempo_heures_creuses"
VIGILANCE = "sensor.76_weather_alert"
SOC = "sensor.sous_sol_docan_docan_soc_systeme"
EV_POWER = "sensor.shelly_em_2_channel_1_power"
GRID = "binary_sensor.sous_sol_growatt_growatt_grid_available_ond1"
MODE_SELECT = "select.sous_sol_growatt_growatt_output_priority_ond1"
LOW = "number.sous_sol_growatt_growatt_battery_low_to_utility_soc_setting_ond1"
HIGH = "number.solaire_growatt_growatt_utility_back_to_battery_soc_setting_ond1"
CHARGE = "number.sous_sol_growatt_growatt_ac_charge_current_setting_ac1_ond1"

UTI = "UTI (Utility First)"
SBU = "SBU (Solar-Battery-Utility)"
SELECT_OPTIONS = [SBU, "SOL (Solar First)", UTI, "SUB (Solar-Utility-Battery)"]

# Bornes (min, max) des trois nombres
LOW_BOUNDS = (6, 95)
HIGH_BOUNDS = (10, 100)
CHARGE_BOUNDS = (0, 80)

# Configuration complète ; CONF_NOTIFY absent (champ facultatif laissé vide)
MOCK_CONF: dict = {
    CONF_COLOR_TODAY: COLOR_TODAY,
    CONF_COLOR_TOMORROW: COLOR_TOMORROW,
    CONF_OFF_PEAK: OFF_PEAK,
    CONF_VIGILANCE: VIGILANCE,
    CONF_PHENOMENA: DEFAULT_PHENOMENA,
    CONF_SOC: SOC,
    CONF_EV_POWER: EV_POWER,
    CONF_GRID: GRID,
    CONF_MODE_SELECT: MODE_SELECT,
    CONF_LOW: LOW,
    CONF_HIGH: HIGH,
    CONF_CHARGE: CHARGE,
    CONF_OPTION_GRID: UTI,
    CONF_OPTION_BATTERY: SBU,
    CONF_RESERVE_NORMAL: DEFAULTS[CONF_RESERVE_NORMAL],
    CONF_RESERVE_VIGILANCE: DEFAULTS[CONF_RESERVE_VIGILANCE],
    CONF_GAP: DEFAULTS[CONF_GAP],
    CONF_LOW_NORMAL: DEFAULTS[CONF_LOW_NORMAL],
    CONF_HIGH_NORMAL: DEFAULTS[CONF_HIGH_NORMAL],
    CONF_CHARGE_NORMAL: DEFAULTS[CONF_CHARGE_NORMAL],
    CONF_CHARGE_BOOST: DEFAULTS[CONF_CHARGE_BOOST],
    CONF_EV_THRESHOLD: DEFAULTS[CONF_EV_THRESHOLD],
}
