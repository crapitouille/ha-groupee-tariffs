"""Calendar platform for Groupe E Tariffs v2 – Cheap Windows (VARIO only)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TARIFF_NAME, DOMAIN, TARIFF_VARIO
from .coordinator import GroupeETariffCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data[CONF_TARIFF_NAME] != TARIFF_VARIO:
        return

    coordinator: GroupeETariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GroupeECheapWindowCalendar(coordinator, entry.data[CONF_TARIFF_NAME])])


class GroupeECheapWindowCalendar(CoordinatorEntity[GroupeETariffCoordinator], CalendarEntity):
    """Calendar exposing cheapest price windows as events."""

    _attr_has_entity_name = True
    _attr_name = "Cheap Windows"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: GroupeETariffCoordinator, tariff_name: str) -> None:
        super().__init__(coordinator)
        self._tariff_name = tariff_name
        self._attr_unique_id = f"{DOMAIN}_{tariff_name}_cheap_windows_calendar"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, tariff_name)},
            "name": f"Groupe E Tariffs v2 – {tariff_name.upper()}",
            "manufacturer": "Groupe E",
            "model": tariff_name.upper(),
            "entry_type": "service",
        }

    def _build_events(self) -> list[CalendarEvent]:
        """Build CalendarEvent list from current cheap_windows data."""
        windows = (self.coordinator.data or {}).get("cheap_windows", [])
        events = []
        for i, w in enumerate(windows, start=1):
            start = w["start"]
            end = w["end"]

            # Ensure timezone-aware datetimes
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)

            duration_h = w.get("duration_hours", "?")
            avg = w.get("avg_price_chf_kwh")
            avg_str = f"{avg:.4f} CHF/kWh" if avg is not None else "N/A"

            events.append(CalendarEvent(
                start=start,
                end=end,
                summary=f"⚡ Cheap Window {i} – {avg_str}",
                description=(
                    f"Window {i} of {len(windows)}\n"
                    f"Duration: {duration_h}h\n"
                    f"Avg price: {avg_str}\n"
                    f"Min: {w.get('min_price_chf_kwh', 'N/A')} CHF/kWh\n"
                    f"Max: {w.get('max_price_chf_kwh', 'N/A')} CHF/kWh"
                ),
            ))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming cheap window event."""
        now = datetime.now(timezone.utc)
        events = self._build_events()

        # First: return an ongoing event if any
        for e in events:
            if e.start <= now < e.end:
                return e

        # Otherwise: return the next upcoming event
        future = [e for e in events if e.start > now]
        if future:
            return min(future, key=lambda e: e.start)

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return all cheap window events within the requested date range."""
        events = self._build_events()
        return [
            e for e in events
            if e.end > start_date and e.start < end_date
        ]
