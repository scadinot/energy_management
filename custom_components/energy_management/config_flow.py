"""Assistant de configuration et options d'Energy Management.

Trois pages : sources, commandes de l'onduleur, valeurs et réglages.
À l'installation, elles s'enchaînent. Dans les options, un menu de
configuration mène à chacune, puis « Valider et enregistrer ».
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
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
    DEFAULT_PHENOMENA,
    DEFAULTS,
    DOMAIN,
    KNOWN_PHENOMENA,
    conf_of,
)

# Champs facultatifs : absents de la configuration s'ils sont laissés vides
OPTIONAL_KEYS = (CONF_GRID, CONF_NOTIFY)

# Menu des options : les trois pages, puis l'enregistrement
OPTIONS_MENU = ["sources", "commands", "values", "confirm"]


def _entity(domain: str) -> selector.EntitySelector:
    """Sélecteur d'une entité d'un domaine."""
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def _number(maximum: float, unit: str, minimum: float = 0) -> selector.NumberSelector:
    """Sélecteur numérique en champ de saisie, au pas de 1."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _select(options: list[str], **kwargs: Any) -> selector.SelectSelector:
    """Sélecteur de liste à partir d'une liste de valeurs."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, **kwargs)
    )


def _field(key: str, current: Mapping[str, Any], default: Any = None) -> vol.Marker:
    """Champ obligatoire prérempli, avec `default` si rien n'est enregistré."""
    value = current.get(key, default)
    if value is None:
        return vol.Required(key)
    return vol.Required(key, default=value)


def _optional(key: str, current: Mapping[str, Any]) -> vol.Marker:
    """Champ facultatif : valeur suggérée, jamais imposée."""
    if current.get(key) is None:
        return vol.Optional(key)
    return vol.Optional(key, description={"suggested_value": current[key]})


def sources_schema(current: Mapping[str, Any]) -> vol.Schema:
    """Étape 1 : entités sources."""
    return vol.Schema(
        {
            _field(CONF_COLOR_TODAY, current): _entity("sensor"),
            _field(CONF_COLOR_TOMORROW, current): _entity("sensor"),
            _field(CONF_OFF_PEAK, current): _entity("binary_sensor"),
            _field(CONF_VIGILANCE, current): _entity("sensor"),
            _field(CONF_PHENOMENA, current, DEFAULT_PHENOMENA): _select(
                KNOWN_PHENOMENA, multiple=True, custom_value=True
            ),
            _field(CONF_SOC, current): _entity("sensor"),
            _field(CONF_EV_POWER, current): _entity("sensor"),
            _optional(CONF_GRID, current): _entity("binary_sensor"),
        }
    )


def commands_schema(current: Mapping[str, Any]) -> vol.Schema:
    """Étape 2 : commandes de l'onduleur."""
    return vol.Schema(
        {
            _field(CONF_MODE_SELECT, current): _entity("select"),
            _field(CONF_LOW, current): _entity("number"),
            _field(CONF_HIGH, current): _entity("number"),
            _field(CONF_CHARGE, current): _entity("number"),
        }
    )


def select_options(hass: HomeAssistant, entity_id: str | None) -> list[str]:
    """Options actuelles d'un `select` ; vide s'il est absent ou sans options."""
    state = hass.states.get(entity_id) if entity_id else None
    options = state.attributes.get("options") if state else None
    return [str(option) for option in options] if options else []


def _default_option(options: list[str], prefix: str) -> str | None:
    """Option qui commence par `prefix`, sinon la première."""
    for option in options:
        if option.startswith(prefix):
            return option
    return options[0] if options else None


def values_schema(hass: HomeAssistant, current: Mapping[str, Any]) -> vol.Schema:
    """Étape 3 : valeurs, réglages et notification."""
    options = select_options(hass, current.get(CONF_MODE_SELECT))
    # Sans options lisibles, la saisie libre évite un formulaire bloqué
    free = not options
    schema: dict[vol.Marker, Any] = {
        _field(
            CONF_OPTION_GRID, current, _default_option(options, "UTI")
        ): _select(options, custom_value=free),
        _field(
            CONF_OPTION_BATTERY, current, _default_option(options, "SBU")
        ): _select(options, custom_value=free),
        _field(CONF_RESERVE_NORMAL, current, DEFAULTS[CONF_RESERVE_NORMAL]): _number(
            100, "%"
        ),
        _field(
            CONF_RESERVE_VIGILANCE, current, DEFAULTS[CONF_RESERVE_VIGILANCE]
        ): _number(100, "%"),
        _field(CONF_GAP, current, DEFAULTS[CONF_GAP]): _number(50, "%", minimum=1),
        _field(CONF_LOW_NORMAL, current, DEFAULTS[CONF_LOW_NORMAL]): _number(100, "%"),
        _field(CONF_HIGH_NORMAL, current, DEFAULTS[CONF_HIGH_NORMAL]): _number(
            100, "%"
        ),
        _field(CONF_CHARGE_NORMAL, current, DEFAULTS[CONF_CHARGE_NORMAL]): _number(
            100, "A"
        ),
        _field(CONF_CHARGE_BOOST, current, DEFAULTS[CONF_CHARGE_BOOST]): _number(
            100, "A"
        ),
        _field(CONF_EV_THRESHOLD, current, DEFAULTS[CONF_EV_THRESHOLD]): _number(
            22000, "W"
        ),
    }
    services = sorted(hass.services.async_services_for_domain("notify"))
    if services:
        schema[_optional(CONF_NOTIFY, current)] = _select(
            [f"notify.{service}" for service in services]
        )
    return vol.Schema(schema)


def _bounds(hass: HomeAssistant, entity_id: str | None) -> tuple[float, float] | None:
    """Bornes `min` / `max` d'un `number`, ou None si elles sont inconnues."""
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
        return None
    try:
        return float(state.attributes["min"]), float(state.attributes["max"])
    except (KeyError, TypeError, ValueError):
        return None


def validate_values(hass: HomeAssistant, conf: Mapping[str, Any]) -> dict[str, str]:
    """Contrôle les valeurs saisies ; renvoie {champ: clé d'erreur}."""
    errors: dict[str, str] = {}

    # Options « réseau » et « batterie »
    options = select_options(hass, conf.get(CONF_MODE_SELECT))
    if options:
        for key in (CONF_OPTION_GRID, CONF_OPTION_BATTERY):
            if conf[key] not in options:
                errors[key] = "option_missing"
    if CONF_OPTION_BATTERY not in errors and (
        conf[CONF_OPTION_GRID] == conf[CONF_OPTION_BATTERY]
    ):
        errors[CONF_OPTION_BATTERY] = "same_option"

    # Bornes des entités `number` choisies
    gap = conf[CONF_GAP]
    low_bounds = _bounds(hass, conf.get(CONF_LOW))
    high_bounds = _bounds(hass, conf.get(CONF_HIGH))
    charge_bounds = _bounds(hass, conf.get(CONF_CHARGE))
    bound_errors: dict[str, str] = {}

    def check(field: str, value: float, bounds: tuple[float, float] | None) -> bool:
        """Note l'erreur sur `field` si `value` sort des bornes."""
        if bounds is None or bounds[0] <= value <= bounds[1]:
            return True
        bound_errors.setdefault(field, "out_of_bounds")
        return False

    for key in (CONF_RESERVE_NORMAL, CONF_RESERVE_VIGILANCE, CONF_LOW_NORMAL):
        check(key, conf[key], low_bounds)
    for key in (CONF_RESERVE_NORMAL, CONF_RESERVE_VIGILANCE):
        # Seuil 13 : réserve plus écart (une réserve déjà fautive porte l'erreur
        # seule) ; bornes inconnues : un pourcentage, donc au plus 100
        if key not in bound_errors:
            check(CONF_GAP, conf[key] + gap, high_bounds or (0, 100))
    check(CONF_HIGH_NORMAL, conf[CONF_HIGH_NORMAL], high_bounds)
    check(CONF_CHARGE_NORMAL, conf[CONF_CHARGE_NORMAL], charge_bounds)
    check(CONF_CHARGE_BOOST, conf[CONF_CHARGE_BOOST], charge_bounds)
    errors.update(bound_errors)

    # Cohérence des seuils : seulement si les bornes sont respectées, sinon
    # l'erreur de bornes explique déjà le problème
    if not bound_errors:
        if conf[CONF_RESERVE_VIGILANCE] < conf[CONF_RESERVE_NORMAL]:
            errors.setdefault(CONF_RESERVE_VIGILANCE, "reserve_order")
        if conf[CONF_HIGH_NORMAL] < conf[CONF_LOW_NORMAL] + gap:
            errors.setdefault(CONF_HIGH_NORMAL, "gap_order")
    return errors


class _StepsMixin:
    """Les trois pages communes à l'installation et aux options."""

    hass: HomeAssistant
    _data: dict[str, Any]
    # Le champ notify figurait-il dans le dernier formulaire des valeurs ?
    _notify_shown = False

    def _merge(self, user_input: Mapping[str, Any], keys: tuple[str, ...]) -> None:
        """Ajoute la saisie ; un champ facultatif vide disparaît de la configuration."""
        for key in OPTIONAL_KEYS:
            if key in keys:
                self._data.pop(key, None)
        self._data.update(user_input)

    async def _next(self, done: str):
        """Suite après une page validée (`done` : sources, commands ou values)."""
        raise NotImplementedError

    async def _sources(self, step_id: str, user_input: dict[str, Any] | None):
        if user_input is not None:
            self._merge(user_input, (CONF_GRID,))
            return await self._next("sources")
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id=step_id, data_schema=sources_schema(self._data)
        )

    async def async_step_commands(self, user_input: dict[str, Any] | None = None):
        """Commandes de l'onduleur."""
        if user_input is not None:
            self._merge(user_input, ())
            return await self._next("commands")
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="commands", data_schema=commands_schema(self._data)
        )

    async def async_step_values(self, user_input: dict[str, Any] | None = None):
        """Valeurs et réglages, avec contrôle de saisie."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Champ notify absent du formulaire (aucun service) : la cible
            # enregistrée est conservée, pas retirée comme un champ vidé.
            self._merge(user_input, (CONF_NOTIFY,) if self._notify_shown else ())
            errors = validate_values(self.hass, self._data)
            if not errors:
                return await self._next("values")
        return self._values_form(errors)

    def _values_form(self, errors: dict[str, str]):
        """Formulaire des valeurs, prérempli, avec les erreurs éventuelles."""
        schema = values_schema(self.hass, self._data)
        self._notify_shown = CONF_NOTIFY in schema.schema
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="values",
            data_schema=schema,
            errors=errors,
        )


class EnergyManagementConfigFlow(_StepsMixin, ConfigFlow, domain=DOMAIN):
    """Installation : les trois pages s'enchaînent."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Page 1 : sources."""
        return await self._sources("user", user_input)

    async def _next(self, done: str) -> ConfigFlowResult:
        if done == "sources":
            return await self.async_step_commands()
        if done == "commands":
            return await self.async_step_values()
        return self.async_create_entry(title="Energy Management", data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EnergyManagementOptionsFlow:
        """Options : menu de configuration."""
        return EnergyManagementOptionsFlow()


class EnergyManagementOptionsFlow(_StepsMixin, OptionsFlow):
    """Options : menu vers les trois pages ; enregistre la configuration complète."""

    _data: dict[str, Any]
    # « Valider et enregistrer » a renvoyé vers les valeurs en erreur :
    # une fois corrigées, on enregistre sans repasser par le menu.
    _saving = False

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu de configuration, prérempli avec la configuration actuelle."""
        if not hasattr(self, "_data"):
            self._data = conf_of(self.config_entry)
        return self.async_show_menu(step_id="init", menu_options=OPTIONS_MENU)

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Page des sources."""
        return await self._sources("sources", user_input)

    async def _next(self, done: str) -> ConfigFlowResult:
        if done == "values" and self._saving:
            return self.async_create_entry(data=self._data)
        return await self.async_step_init()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Valider et enregistrer ; des valeurs devenues fautives (par exemple
        après un changement de commandes) renvoient vers leur page."""
        errors = validate_values(self.hass, self._data)
        if errors:
            self._saving = True
            return self._values_form(errors)
        return self.async_create_entry(data=self._data)
