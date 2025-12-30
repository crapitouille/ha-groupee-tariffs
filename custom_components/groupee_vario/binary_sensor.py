from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    async_add_entities([GroupeEDtOffpeakBinarySensor(coordinator, entry)], True)

class GroupeEDtOffpeakBinarySensor(CoordinatorEntity[GroupeEVarioCoordinator], BinarySensorEntity):
    _attr_name = "Groupe E DT off-peak"
    _attr_icon = "mdi:clock"

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_dt_offpeak"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.is_dt_offpeak()

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
