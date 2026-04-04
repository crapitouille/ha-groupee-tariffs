"""Config flow for Groupe E Tariffs v2 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DAILY_UPDATE_HOUR,
    CONF_TARIFF_NAME,
    CONF_WINDOW_COUNT,
    CONF_WINDOW_DURATION_HOURS,
    DEFAULT_DAILY_UPDATE_HOUR,
    DEFAULT_WINDOW_COUNT,
    DEFAULT_WINDOW_DURATION_HOURS,
    DOMAIN,
    TARIFF_LABELS,
    TARIFF_VARIO,
)

_LOGGER = logging.getLogger(__name__)

HOUR_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=23, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="h")
)
WINDOW_COUNT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=4, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="windows")
)
WINDOW_DURATION_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=4, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="h")
)


class GroupeEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: tariff selection + daily update hour."""
        if user_input is not None:
            self._data.update({
                CONF_TARIFF_NAME: user_input[CONF_TARIFF_NAME],
                CONF_DAILY_UPDATE_HOUR: int(user_input[CONF_DAILY_UPDATE_HOUR]),
            })
            if user_input[CONF_TARIFF_NAME] == TARIFF_VARIO:
                return await self.async_step_vario_windows()
            # DOUBLE: no extra options, create entry directly
            tariff_name = self._data[CONF_TARIFF_NAME]
            await self.async_set_unique_id(f"{DOMAIN}_{tariff_name}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Groupe E Tariffs v2 – {TARIFF_LABELS.get(tariff_name, tariff_name)}",
                data=self._data,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_TARIFF_NAME): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=k, label=v) for k, v in TARIFF_LABELS.items()],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_DAILY_UPDATE_HOUR, default=DEFAULT_DAILY_UPDATE_HOUR): HOUR_SELECTOR,
            }),
        )

    async def async_step_vario_windows(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2 (VARIO only): configure cheap window settings."""
        if user_input is not None:
            self._data.update({
                CONF_WINDOW_COUNT: int(user_input[CONF_WINDOW_COUNT]),
                CONF_WINDOW_DURATION_HOURS: int(user_input[CONF_WINDOW_DURATION_HOURS]),
            })
            tariff_name = self._data[CONF_TARIFF_NAME]
            await self.async_set_unique_id(f"{DOMAIN}_{tariff_name}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Groupe E Tariffs v2 – {TARIFF_LABELS.get(tariff_name, tariff_name)}",
                data=self._data,
            )

        return self.async_show_form(
            step_id="vario_windows",
            data_schema=vol.Schema({
                vol.Required(CONF_WINDOW_COUNT, default=DEFAULT_WINDOW_COUNT): WINDOW_COUNT_SELECTOR,
                vol.Required(CONF_WINDOW_DURATION_HOURS, default=DEFAULT_WINDOW_DURATION_HOURS): WINDOW_DURATION_SELECTOR,
            }),
            description_placeholders={
                "info": "Define the cheapest price windows to optimise your consumption."
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return GroupeEOptionsFlow(config_entry)


class GroupeEOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        is_vario = self._config_entry.data.get(CONF_TARIFF_NAME) == TARIFF_VARIO

        if user_input is not None:
            data = {CONF_DAILY_UPDATE_HOUR: int(user_input[CONF_DAILY_UPDATE_HOUR])}
            if is_vario:
                data[CONF_WINDOW_COUNT] = int(user_input[CONF_WINDOW_COUNT])
                data[CONF_WINDOW_DURATION_HOURS] = int(user_input[CONF_WINDOW_DURATION_HOURS])
            return self.async_create_entry(title="", data=data)

        def _get(key, default):
            return self._config_entry.options.get(key, self._config_entry.data.get(key, default))

        schema_dict = {
            vol.Required(CONF_DAILY_UPDATE_HOUR, default=_get(CONF_DAILY_UPDATE_HOUR, DEFAULT_DAILY_UPDATE_HOUR)): HOUR_SELECTOR,
        }
        if is_vario:
            schema_dict[vol.Required(CONF_WINDOW_COUNT, default=_get(CONF_WINDOW_COUNT, DEFAULT_WINDOW_COUNT))] = WINDOW_COUNT_SELECTOR
            schema_dict[vol.Required(CONF_WINDOW_DURATION_HOURS, default=_get(CONF_WINDOW_DURATION_HOURS, DEFAULT_WINDOW_DURATION_HOURS))] = WINDOW_DURATION_SELECTOR

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
