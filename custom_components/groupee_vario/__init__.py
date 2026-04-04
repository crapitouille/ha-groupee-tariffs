"""The Groupe E Tariffs v2 integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DAILY_UPDATE_HOUR,
    CONF_TARIFF_NAME,
    CONF_WINDOW_COUNT,
    CONF_WINDOW_DURATION_HOURS,
    DEFAULT_DAILY_UPDATE_HOUR,
    DEFAULT_WINDOW_COUNT,
    DEFAULT_WINDOW_DURATION_HOURS,
    DOMAIN,
)
from .coordinator import GroupeETariffCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "calendar"]


def _get_option(entry: ConfigEntry, key: str, default):
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = GroupeETariffCoordinator(
        hass,
        tariff_name=entry.data[CONF_TARIFF_NAME],
        daily_update_hour=int(_get_option(entry, CONF_DAILY_UPDATE_HOUR, DEFAULT_DAILY_UPDATE_HOUR)),
        window_count=int(_get_option(entry, CONF_WINDOW_COUNT, DEFAULT_WINDOW_COUNT)),
        window_duration_hours=int(_get_option(entry, CONF_WINDOW_DURATION_HOURS, DEFAULT_WINDOW_DURATION_HOURS)),
    )

    await coordinator.async_config_entry_first_refresh()
    coordinator.start_daily_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: GroupeETariffCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        coordinator.stop_daily_refresh()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
