"""Sensor platform for Groupe E Tariffs v2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TARIFF_NAME,
    DOMAIN,
    SENSOR_CHEAP_WINDOW,
    SENSOR_CURRENT_PRICE,
    SENSOR_LAST_REFRESH,
    SENSOR_MAX_PRICE_TODAY,
    SENSOR_MIN_PRICE_TODAY,
    SENSOR_NEXT_PRICE,
    SENSOR_PUBLICATION_TIME,
    SENSOR_SCHEDULE,
    TARIFF_VARIO,
)
from .coordinator import GroupeETariffCoordinator

CURRENCY_UNIT = "CHF/kWh"


@dataclass(frozen=True, kw_only=True)
class GroupeESensorDescription(SensorEntityDescription):
    value_fn: Any = None
    extra_fn: Any = None


# ---------- value functions ----------

def _current_price(d):
    s = d.get("current_slot")
    return round(s["integrated"], 5) if s and s.get("integrated") is not None else None

def _next_price(d):
    s = d.get("next_slot")
    return round(s["integrated"], 5) if s and s.get("integrated") is not None else None

def _min_today(d):
    v = d.get("min_price_today")
    return round(v, 5) if v is not None else None

def _max_today(d):
    v = d.get("max_price_today")
    return round(v, 5) if v is not None else None

def _publication(d):
    return d.get("publication_timestamp")

def _last_refresh(d):
    return d.get("last_refresh")

def _schedule_state(d):
    s = d.get("current_slot")
    return round(s["integrated"], 5) if s and s.get("integrated") is not None else None


# ---------- extra attribute functions ----------

def _extra_current(d):
    s = d.get("current_slot")
    if not s:
        return {}
    return {"start": s["start"].isoformat(), "end": s["end"].isoformat()}

def _extra_next(d):
    s = d.get("next_slot")
    if not s:
        return {}
    return {"start": s["start"].isoformat(), "end": s["end"].isoformat()}

def _extra_schedule(d):
    today = d.get("schedule_today", [])
    tomorrow = d.get("schedule_tomorrow", [])
    all_slots = today + tomorrow
    prices = [
        {
            "start": s["start"],
            "end": s["end"],
            "price_chf_kwh": s.get("integrated_chf_kwh"),
        }
        for s in all_slots
    ]
    all_values = [p["price_chf_kwh"] for p in prices if p["price_chf_kwh"] is not None]
    return {
        "slot_count": len(prices),
        "today_slots": len(today),
        "tomorrow_slots": len(tomorrow),
        "tomorrow_available": d.get("tomorrow_available", False),
        "min_chf_kwh": round(min(all_values), 5) if all_values else None,
        "max_chf_kwh": round(max(all_values), 5) if all_values else None,
        "publication_timestamp": d.get("publication_timestamp").isoformat()
            if d.get("publication_timestamp") else None,
        "prices": prices,
    }


# ---------- base sensors ----------

COMMON_SENSORS: list[GroupeESensorDescription] = [
    GroupeESensorDescription(
        key=SENSOR_CURRENT_PRICE,
        name="Current Price",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=CURRENCY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_current_price,
        extra_fn=_extra_current,
    ),
    GroupeESensorDescription(
        key=SENSOR_NEXT_PRICE,
        name="Next Slot Price",
        icon="mdi:lightning-bolt-outline",
        native_unit_of_measurement=CURRENCY_UNIT,
        value_fn=_next_price,
        extra_fn=_extra_next,
    ),
    GroupeESensorDescription(
        key=SENSOR_MIN_PRICE_TODAY,
        name="Min Price Today",
        icon="mdi:trending-down",
        native_unit_of_measurement=CURRENCY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_min_today,
    ),
    GroupeESensorDescription(
        key=SENSOR_MAX_PRICE_TODAY,
        name="Max Price Today",
        icon="mdi:trending-up",
        native_unit_of_measurement=CURRENCY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_max_today,
    ),
    GroupeESensorDescription(
        key=SENSOR_PUBLICATION_TIME,
        name="Publication Timestamp",
        icon="mdi:clock-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_publication,
    ),
    GroupeESensorDescription(
        key=SENSOR_LAST_REFRESH,
        name="Last Refresh",
        icon="mdi:refresh",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_refresh,
    ),
    GroupeESensorDescription(
        key=SENSOR_SCHEDULE,
        name="Price Schedule",
        icon="mdi:chart-line",
        native_unit_of_measurement=CURRENCY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_schedule_state,
        extra_fn=_extra_schedule,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GroupeETariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    tariff_name = entry.data[CONF_TARIFF_NAME]

    entities: list[SensorEntity] = [
        GroupeESensorEntity(coordinator, desc, tariff_name)
        for desc in COMMON_SENSORS
    ]

    # Add cheap window sensors for VARIO
    if tariff_name == TARIFF_VARIO:
        window_count = coordinator.data.get("window_count", 1) if coordinator.data else 1
        for i in range(1, window_count + 1):
            entities.append(GroupeECheapWindowSensor(coordinator, tariff_name, i))

    async_add_entities(entities)


class GroupeESensorEntity(CoordinatorEntity[GroupeETariffCoordinator], SensorEntity):
    entity_description: GroupeESensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, description, tariff_name):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{tariff_name}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tariff_name)},
            "name": f"Groupe E Tariffs v2 – {tariff_name.upper()}",
            "manufacturer": "Groupe E",
            "model": tariff_name.upper(),
            "entry_type": "service",
        }

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.entity_description.extra_fn:
            return {}
        return self.entity_description.extra_fn(self.coordinator.data)


class GroupeECheapWindowSensor(CoordinatorEntity[GroupeETariffCoordinator], SensorEntity):
    """Sensor representing one of the N cheapest price windows."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cash-clock"
    _attr_native_unit_of_measurement = CURRENCY_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, tariff_name, window_index: int):
        super().__init__(coordinator)
        self._window_index = window_index
        self._attr_name = f"Cheap Window {window_index}"
        self._attr_unique_id = f"{DOMAIN}_{tariff_name}_{SENSOR_CHEAP_WINDOW}_{window_index}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tariff_name)},
            "name": f"Groupe E Tariffs v2 – {tariff_name.upper()}",
            "manufacturer": "Groupe E",
            "model": tariff_name.upper(),
            "entry_type": "service",
        }

    @property
    def native_value(self) -> float | None:
        """State = average price of the window."""
        windows = (self.coordinator.data or {}).get("cheap_windows", [])
        idx = self._window_index - 1
        if idx < len(windows):
            return windows[idx].get("avg_price_chf_kwh")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        windows = (self.coordinator.data or {}).get("cheap_windows", [])
        idx = self._window_index - 1
        if idx >= len(windows):
            return {"available": False}
        w = windows[idx]
        return {
            "available": True,
            "start": w["start"].isoformat() if hasattr(w["start"], "isoformat") else w["start"],
            "end": w["end"].isoformat() if hasattr(w["end"], "isoformat") else w["end"],
            "avg_price_chf_kwh": w.get("avg_price_chf_kwh"),
            "min_price_chf_kwh": w.get("min_price_chf_kwh"),
            "max_price_chf_kwh": w.get("max_price_chf_kwh"),
            "duration_hours": w.get("duration_hours"),
            "window_index": self._window_index,
        }
