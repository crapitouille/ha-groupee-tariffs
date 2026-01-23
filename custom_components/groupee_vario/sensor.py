from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, NAME
from .coordinator import GroupeEVarioCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: GroupeEVarioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            GroupeEVarioCurrentSensor(coordinator, entry),
            GroupeEDTNextOffPeakStartSensor(coordinator, entry),
        ]
    )

class _BaseGroupeESensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=NAME,
            manufacturer="Groupe E",
        )

    async def async_added_to_hass(self) -> None:
        self.coordinator.async_add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.async_remove_listener(self.async_write_ha_state)

class GroupeEVarioCurrentSensor(_BaseGroupeESensor):
    _attr_name = "Vario current"
    _attr_icon = "mdi:currency-usd"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_vario_current"

    @property
    def native_value(self):
        slot = self.coordinator.current_slot()
        if slot is None:
            return None
        return slot.vario_plus

    @property
    def native_unit_of_measurement(self):
        slot = self.coordinator.current_slot()
        if slot is None:
            return None
        # API returns "Rp./kWh"; we keep as-is.
        return slot.unit or "Rp./kWh"

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

class GroupeEDTNextOffPeakStartSensor(_BaseGroupeESensor):
    _attr_name = "DT next off-peak start"
    _attr_icon = "mdi:eye"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_dt_next_off_peak_start"

    @property
    def native_value(self):
        # Return timezone-aware datetime or None
        return self.coordinator.next_offpeak_start()
