from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_URL, CONF_REFRESH_TIME, DEFAULT_REFRESH_TIME, DOMAIN, USER_AGENT

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class TariffSlot:
    start: datetime
    end: datetime
    vario_plus: float
    dt_plus: float
    unit: str | None

class GroupeEVarioCoordinator(DataUpdateCoordinator[list[TariffSlot]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=None,  # we drive refresh manually
        )
        self.entry = entry
        self._tz = ZoneInfo(hass.config.time_zone or "UTC")
        self._session = async_get_clientsession(hass)

        self._last_valid_data: list[TariffSlot] | None = None
        self._last_day_seen: date | None = None
        self._last_refresh_attempt: datetime | None = None
        self._refresh_lock = asyncio.Lock()

        self._unsub_tick = None
        self._unsub_daily = None

        # Periodic tick: updates entities (without hitting API) and handles midnight rollover.
        self._unsub_tick = async_track_time_interval(hass, self._async_time_tick, timedelta(minutes=1))

        # Daily refresh at configured time (default 18:00), aligned with API publishing.
        self._setup_daily_refresh()

        # Service for manual refresh
        hass.services.async_register(DOMAIN, "refresh_now", self._handle_refresh_service)

    def _setup_daily_refresh(self) -> None:
        # Unsubscribe previous if options changed
        if self._unsub_daily is not None:
            self._unsub_daily()
            self._unsub_daily = None

        hhmm = self.entry.options.get(CONF_REFRESH_TIME, DEFAULT_REFRESH_TIME)
        hour, minute = 18, 0
        try:
            parts = str(hhmm).split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            hour = max(0, min(23, hour))
            minute = max(0, min(59, minute))
        except Exception:
            _LOGGER.warning("Invalid refresh_time option '%s', using %s", hhmm, DEFAULT_REFRESH_TIME)

        self._unsub_daily = async_track_time_change(
            self.hass, self._async_daily_refresh, hour=hour, minute=minute, second=0
        )

    async def async_shutdown(self) -> None:
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None
        if self._unsub_daily is not None:
            self._unsub_daily()
            self._unsub_daily = None

        # Best effort: unregister service (may be used by multiple entries in future)
        try:
            self.hass.services.async_remove(DOMAIN, "refresh_now")
        except Exception:
            pass

    @callback
    async def _async_daily_refresh(self, *args: Any, **kwargs: Any) -> None:
        _LOGGER.debug("Daily refresh trigger fired")
        await self._safe_request_refresh(reason="daily_schedule")

    async def _handle_refresh_service(self, call) -> None:
        # For future multi-entry support, we could accept entry_id and filter.
        await self._safe_request_refresh(reason="service")

    @callback
    async def _async_time_tick(self, now: datetime) -> None:
        # 1) Detect midnight rollover and refresh.
        local_now = now.astimezone(self._tz)
        today = local_now.date()

        if self._last_day_seen is None:
            self._last_day_seen = today
        elif today != self._last_day_seen:
            _LOGGER.info("Day rollover detected (%s -> %s). Forcing API refresh.", self._last_day_seen, today)
            self._last_day_seen = today
            # Fire and forget; do not block tick loop
            self.hass.async_create_task(self._safe_request_refresh(reason="midnight_rollover"))

        # 2) If we cannot resolve a current slot, attempt an API refresh (cooldown).
        if self._last_valid_data:
            if self.current_slot(local_now) is None:
                # Cooldown to avoid hammering API if it's temporarily missing data
                if self._should_attempt_refresh(local_now):
                    _LOGGER.warning("No current slot found for %s. Attempting API refresh.", local_now.isoformat())
                    self.hass.async_create_task(self._safe_request_refresh(reason="no_current_slot"))

        # 3) Update listeners so entities recalculate based on current time.
        try:
            self.async_update_listeners()
        except Exception:
            _LOGGER.exception("Failed to update listeners on tick")

    def _should_attempt_refresh(self, now: datetime) -> bool:
        if self._last_refresh_attempt is None:
            return True
        return (now - self._last_refresh_attempt) >= timedelta(minutes=10)

    async def _safe_request_refresh(self, reason: str) -> None:
        # Ensure only one refresh at a time.
        async with self._refresh_lock:
            self._last_refresh_attempt = datetime.now(tz=self._tz)
            try:
                await self.async_request_refresh()
                _LOGGER.debug("Refresh completed (reason=%s)", reason)
            except Exception:
                _LOGGER.exception("Refresh failed (reason=%s); keeping last known data", reason)
                # Keep coordinator.data as last valid if possible
                if self._last_valid_data is not None:
                    self.async_set_updated_data(self._last_valid_data)

    async def _async_update_data(self) -> list[TariffSlot]:
        # Fetch tariffs for today + tomorrow (2 days) with an exclusive end boundary.
        try:
            slots = await self._fetch_slots_window()
            if not slots:
                raise UpdateFailed("Empty response from Groupe E tariffs API")
            self._last_valid_data = slots
            return slots
        except Exception as err:
            # Do not force entities to unknown: keep last valid data if present.
            if self._last_valid_data is not None:
                _LOGGER.error("Update failed: %s (keeping last valid data)", err)
                return self._last_valid_data
            raise UpdateFailed(str(err)) from err

    async def _fetch_slots_window(self) -> list[TariffSlot]:
        now = datetime.now(tz=self._tz)
        start_local = datetime.combine(now.date(), time(0, 0), tzinfo=self._tz)
        end_local = start_local + timedelta(days=2)  # exclusive end

        params = {
            "start_timestamp": start_local.isoformat(),
            "end_timestamp": end_local.isoformat(),
        }

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        _LOGGER.debug("Fetching tariffs window start=%s end=%s", params["start_timestamp"], params["end_timestamp"])

        async with self._session.get(API_URL, params=params, headers=headers, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise UpdateFailed(f"HTTP {resp.status}: {text[:300]}")
            raw = await resp.json()

        if not isinstance(raw, list):
            raise UpdateFailed(f"Unexpected API payload type: {type(raw)}")

        slots: list[TariffSlot] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                start = datetime.fromisoformat(item["start_timestamp"]).astimezone(self._tz)
                end = datetime.fromisoformat(item["end_timestamp"]).astimezone(self._tz)
                vario_plus = float(item.get("vario_plus"))
                dt_plus = float(item.get("dt_plus"))
                unit = item.get("unit")
                slots.append(TariffSlot(start=start, end=end, vario_plus=vario_plus, dt_plus=dt_plus, unit=unit))
            except Exception:
                # Skip malformed row but keep going
                continue

        # Sort to be safe
        slots.sort(key=lambda s: s.start)
        _LOGGER.debug("Fetched %d tariff slots", len(slots))
        return slots

    def current_slot(self, now_local: Optional[datetime] = None) -> TariffSlot | None:
        if not self._last_valid_data:
            return None
        if now_local is None:
            now_local = datetime.now(tz=self._tz)
        # Inclusive start, exclusive end
        for slot in self._last_valid_data:
            if slot.start <= now_local < slot.end:
                return slot
        return None

    def dt_off_peak(self, now_local: Optional[datetime] = None) -> bool | None:
        slot = self.current_slot(now_local)
        if slot is None or not self._last_valid_data:
            return None

        day = slot.start.date()
        # Determine lowest dt_plus for that civil day (local time)
        vals = [s.dt_plus for s in self._last_valid_data if s.start.date() == day]
        if not vals:
            return None
        low = min(vals)
        return slot.dt_plus == low
