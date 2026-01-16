from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN

class GroupeEVarioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        # Single instance by default; change to allow multi-instance later if needed.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

        return self.async_create_entry(title="Groupe E Tariffs", data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GroupeEVarioOptionsFlowHandler(config_entry)

class GroupeEVarioOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        # Keep options minimal and fully serializable (no custom validators).
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # We keep refresh_time as a simple string "HH:MM" to avoid serializer issues.
        current = self._config_entry.options.get("refresh_time", "18:00")
        schema = vol.Schema({
            vol.Optional("refresh_time", default=current): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
