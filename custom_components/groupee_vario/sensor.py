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

DEVICE_INFO_CACHE: dict[str, dict] = {}


def _device_info(tariff_name: str) -> dict:
    return {
        "identifiers": {(DOMAIN, tariff_name)},
        "name": f"Groupe E Tariffs v2 – {tariff_name.upper()}",
        "manufacturer": "Groupe E",
        "model": tariff_name.upper(),
        "entry_type": "service",
    }


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
    """
    Compact format: prices = [[start_ISO16, price], ...]
    192 slots × ~30 bytes ≈ 5.7 KB, well under HA's 16 KB limit.
    Use in apexcharts: prices.map(p => [new Date(p[0]).getTime(), p[1]])
    """
    today = d.get("schedule_today", [])
    tomorrow = d.get("schedule_tomorrow", [])
    prices = today + tomorrow
    all_values = [p[1] for p in prices if p[1] is not None]
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


# ---------- sensor descriptions ----------

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
        self._attr_device_info = _device_info(tariff_name)

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
    _attr_has_entity_name = True
    _attr_icon = "mdi:cash-clock"
    _attr_native_unit_of_measurement = CURRENCY_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, tariff_name, window_index: int):
        super().__init__(coordinator)
        self._window_index = window_index
        self._attr_name = f"Cheap Window {window_index}"
        self._attr_unique_id = f"{DOMAIN}_{tariff_name}_{SENSOR_CHEAP_WINDOW}_{window_index}"
        self._attr_device_info = _device_info(tariff_name)

    def _get_window(self) -> dict | None:
        windows = (self.coordinator.data or {}).get("cheap_windows", [])
        # Find windows for today only (first N windows belong to today)
        today_windows = [w for w in windows if self._is_today(w["start"])]
        idx = self._window_index - 1
        return today_windows[idx] if idx < len(today_windows) else None

    def _is_today(self, dt) -> bool:
        from datetime import date
        if isinstance(dt, str):
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(dt)
        now = __import__("datetime").datetime.now(dt.tzinfo or __import__("datetime").timezone.utc)
        return dt.date() == now.date()

    @property
    def native_value(self) -> float | None:
        w = self._get_window()
        return w.get("avg_price_chf_kwh") if w else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        windows = (self.coordinator.data or {}).get("cheap_windows", [])
        # All windows (today + tomorrow), filtered by index across each day
        result = {}
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)

        today_wins = [w for w in windows if (w["start"] if w["start"].tzinfo else w["start"].replace(tzinfo=_tz.utc)).date() == now.date()]
        tomorrow_wins = [w for w in windows if (w["start"] if w["start"].tzinfo else w["start"].replace(tzinfo=_tz.utc)).date() == (now + __import__("datetime").timedelta(days=1)).date()]

        idx = self._window_index - 1

        if idx < len(today_wins):
            w = today_wins[idx]
            result["today"] = {
                "start": w["start"].isoformat(),
                "end": w["end"].isoformat(),
                "avg_price_chf_kwh": w.get("avg_price_chf_kwh"),
                "min_price_chf_kwh": w.get("min_price_chf_kwh"),
                "max_price_chf_kwh": w.get("max_price_chf_kwh"),
                "duration_hours": w.get("duration_hours"),
            }

        if idx < len(tomorrow_wins):
            w = tomorrow_wins[idx]
            result["tomorrow"] = {
                "start": w["start"].isoformat(),
                "end": w["end"].isoformat(),
                "avg_price_chf_kwh": w.get("avg_price_chf_kwh"),
                "min_price_chf_kwh": w.get("min_price_chf_kwh"),
                "max_price_chf_kwh": w.get("max_price_chf_kwh"),
                "duration_hours": w.get("duration_hours"),
            }

        result["tomorrow_available"] = idx < len(tomorrow_wins)
        return result
