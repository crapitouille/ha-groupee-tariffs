"""Binary sensor for Groupe E Tariffs v2 – OffPeak (DOUBLE only)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TARIFF_NAME, DOMAIN, TARIFF_DOUBLE
from .coordinator import GroupeETariffCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data[CONF_TARIFF_NAME] != TARIFF_DOUBLE:
        return
    coordinator: GroupeETariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GroupeEOffPeakSensor(coordinator, entry.data[CONF_TARIFF_NAME])])


class GroupeEOffPeakSensor(CoordinatorEntity[GroupeETariffCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "OffPeak"
    _attr_icon = "mdi:clock-time-four-outline"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator, tariff_name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{tariff_name}_offpeak"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tariff_name)},
            "name": f"Groupe E Tariffs v2 – {tariff_name.upper()}",
            "manufacturer": "Groupe E",
            "model": tariff_name.upper(),
            "entry_type": "service",
        }

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("tariff_period")
