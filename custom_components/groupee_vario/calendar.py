from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GroupeEVarioCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GroupeEVarioCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            GroupeEDTOffPeakCalendar(coordinator, entry),
            GroupeEVarioCheapestWindowCalendar(coordinator, entry),
        ]
    )


class _BaseGroupeECalendar(CoordinatorEntity[GroupeEVarioCoordinator], CalendarEntity):
    _attr_should_poll = False

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:  # type: ignore[override]
        return self._event

    def _set_current_or_next_event(self, events: List[CalendarEvent]) -> None:
        """Set the entity's current/next event for UI state."""
        now = datetime.now(tz=self.coordinator._tz)

        current: CalendarEvent | None = None
        upcoming: CalendarEvent | None = None

        for ev in sorted(events, key=lambda e: e.start):
            if ev.start <= now < ev.end:
                current = ev
                break
            if ev.start >= now:
                upcoming = ev
                break

        self._event = current or upcoming


class GroupeEDTOffPeakCalendar(_BaseGroupeECalendar):
    _attr_name = "Groupe E DT Off-peak"
    _attr_icon = "mdi:clock"

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_dt_offpeak_calendar"

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:  # type: ignore[override]
        events: List[CalendarEvent] = []

        # We only have at most today + tomorrow from the API.
        start_day = start_date.astimezone(self.coordinator._tz).date()
        end_day = end_date.astimezone(self.coordinator._tz).date()

        day = start_day
        while day <= end_day:
            for block_start, block_end in self.coordinator.dt_offpeak_blocks(day):
                if block_end <= start_date or block_start >= end_date:
                    continue
                events.append(
                    CalendarEvent(
                        summary="DT off-peak",
                        start=block_start,
                        end=block_end,
                        description=None,
                        location=None,
                    )
                )
            day = day + timedelta(days=1)

        # Update state event (best effort)
        self._set_current_or_next_event(events)
        return events

    @callback
    def _handle_coordinator_update(self) -> None:
        # Recompute event state using a small window around "now".
        now = datetime.now(tz=self.coordinator._tz)
        # Use a 36h window so we catch current + next.
        start = now - timedelta(hours=12)
        end = now + timedelta(hours=36)
        # This method is sync, so we just clear event; HA will query events when needed.
        self._event = self._event  # no-op
        super()._handle_coordinator_update()


class GroupeEVarioCheapestWindowCalendar(_BaseGroupeECalendar):
    _attr_name = "Groupe E Vario Cheapest Window"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: GroupeEVarioCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_vario_cheapest_window_calendar"

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:  # type: ignore[override]
        events: List[CalendarEvent] = []

        hours = self.coordinator.cheap_window_hours()
        count = self.coordinator.cheap_window_count()
        start_day = start_date.astimezone(self.coordinator._tz).date()
        end_day = end_date.astimezone(self.coordinator._tz).date()

        day = start_day
        while day <= end_day:
            windows = self.coordinator.cheapest_vario_windows(day, hours=hours, count=count)
            for idx, (block_start, block_end) in enumerate(windows, start=1):
                if block_end <= start_date or block_start >= end_date:
                    continue
                suffix = f" #{idx}" if count > 1 else ""
                events.append(
                    CalendarEvent(
                        summary=f"Cheapest Vario ({hours}h){suffix}",
                        start=block_start,
                        end=block_end,
                        description=None,
                        location=None,
                    )
                )
            day = day + timedelta(days=1)

        self._set_current_or_next_event(events)
        return events

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
