from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import CONF_REFRESH_TIME, DEFAULT_REFRESH_TIME, DOMAIN

class GroupeEVarioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Groupe E Tariffs", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_REFRESH_TIME,
                    default=DEFAULT_REFRESH_TIME,
                ): selector.TimeSelector(selector.TimeSelectorConfig()),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry):
        return GroupeEVarioOptionsFlowHandler(config_entry)

class GroupeEVarioOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_REFRESH_TIME, self._config_entry.data.get(CONF_REFRESH_TIME, DEFAULT_REFRESH_TIME)
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_REFRESH_TIME, default=current): selector.TimeSelector(
                    selector.TimeSelectorConfig()
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
