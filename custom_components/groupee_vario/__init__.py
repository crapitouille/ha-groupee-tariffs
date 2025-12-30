from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

import voluptuous as vol

from .const import ATTR_ENTRY_ID, DOMAIN, SERVICE_REFRESH_NOW
from .coordinator import GroupeEVarioCoordinator

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = GroupeEVarioCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = coordinator

    # Register a domain service once. It can refresh a specific entry (by entry_id)
    # or all entries if omitted.
    if not domain_data.get("_service_registered"):
        async def _handle_refresh(call):
            target_entry_id = call.data.get(ATTR_ENTRY_ID)
            if target_entry_id:
                target = hass.data.get(DOMAIN, {}).get(target_entry_id)
                if target:
                    await target.async_request_refresh()
                return
            # Refresh all
            for key, coord in hass.data.get(DOMAIN, {}).items():
                if key == "_service_registered":
                    continue
                await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_NOW,
            _handle_refresh,
            schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string}),
        )
        domain_data["_service_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coord = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coord is not None:
            await coord.async_stop()
    return unload_ok
