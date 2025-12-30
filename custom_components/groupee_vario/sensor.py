from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTR_END, ATTR_START, ATTR_UNIT, DOMAIN
from .coordinator import GroupeEVarioCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GroupeEVarioCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GroupeEVarioCurrentVarioSensor(coordinator, entry)], True)

class GroupeEVarioCurrentVarioSensor(CoordinatorEntity[GroupeEVarioCoordinator], SensorEntity):
    _attr_name = "Groupe E Vario current"
    _attr_icon = "mdi:cash"
    _attr_native_unit_of_measurement = "Rp./kWh"  # API returns unit in each slice; keep stable here

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_vario_current"

    @property
    def native_value(self) -> float | None:
        sl = self.coordinator.get_current_slice()
        return sl.vario_plus if sl else None

    @property
    def extra_state_attributes(self) -> dict:
        sl = self.coordinator.get_current_slice()
        if not sl:
            return {}
        return {
            ATTR_START: dt_util.as_local(sl.start).isoformat(),
            ATTR_END: dt_util.as_local(sl.end).isoformat(),
            ATTR_UNIT: sl.unit,
        }
