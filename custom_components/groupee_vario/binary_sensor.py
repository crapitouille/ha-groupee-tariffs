from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, NAME
from .coordinator import GroupeEVarioCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: GroupeEVarioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GroupeEDTOffPeakBinarySensor(coordinator, entry)])

class GroupeEDTOffPeakBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "DT off-peak"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_dt_off_peak"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=NAME,
            manufacturer="Groupe E",
        )

    @property
    def is_on(self):
        val = self.coordinator.dt_off_peak()
        if val is None:
            return None
        return bool(val)

    @property
    def extra_state_attributes(self):
        slot = self.coordinator.current_slot()
        if slot is None:
            return {}
        return {
            "slot_start": slot.start.isoformat(),
            "slot_end": slot.end.isoformat(),
            "dt_plus": slot.dt_plus,
        }

    async def async_added_to_hass(self) -> None:
        self.coordinator.async_add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.async_remove_listener(self.async_write_ha_state)
