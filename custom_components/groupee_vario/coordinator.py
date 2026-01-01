from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import API_URL, CONF_REFRESH_TIME, DEFAULT_REFRESH_TIME, DOMAIN

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class TariffSlice:
    start: datetime
    end: datetime
    vario_plus: float | None
    dt_plus: float | None
    unit: str | None

def _parse_iso(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return dt

def _local_midnight_range(now_local: datetime) -> tuple[datetime, datetime]:
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # IMPORTANT: use an *exclusive* end (exactly +2 days) so we don't
    # accidentally drop the last 15-minute slice of the second day.
    # The API slices end exactly at HH:00/15/30/45, so using 23:59:59 can
    # exclude the final slice (23:45-00:00) and cause "stale"/missing data
    # around midnight.
    end_local = start_local + timedelta(days=2)
    return start_local, end_local

def _parse_refresh_time(value: str) -> dtime:
    parts = value.split(":")
    if len(parts) == 2:
        h, m = parts
        s = "0"
    else:
        h, m, s = parts[:3]
    return dtime(int(h), int(m), int(s))

class GroupeEVarioCoordinator(DataUpdateCoordinator[list[TariffSlice]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        refresh_time_str = entry.options.get(
            CONF_REFRESH_TIME,
            entry.data.get(CONF_REFRESH_TIME, DEFAULT_REFRESH_TIME),
        )
        self._refresh_time = _parse_refresh_time(refresh_time_str)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_method=self._async_update_data,
            update_interval=None,  # we trigger refresh on a schedule
        )

        self._unsub_refresh = None
        self._unsub_tick = async_track_time_interval(
            self.hass, self._async_time_tick, timedelta(minutes=1)
        )

        # Schedule the first run and then reschedule daily
        self._schedule_next_refresh(dt_util.now())

    async def _async_time_tick(self, _now: datetime) -> None:
        """Notify listeners so entities can update their *current* value.

        The upstream API only changes once per day, but entity values must still
        move to the next 15-minute slice as time passes. We keep API polling on
        the configured daily schedule and simply trigger listener updates every
        minute.
        """

        self.async_update_listeners()

    async def async_stop(self) -> None:
        """Cancel scheduled callbacks."""

        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None

        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None

    def _schedule_next_refresh(self, now: datetime) -> None:
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None
        next_run = dt_util.as_local(now).replace(
            hour=self._refresh_time.hour,
            minute=self._refresh_time.minute,
            second=self._refresh_time.second,
            microsecond=0,
        )
        if next_run <= dt_util.as_local(now):
            next_run += timedelta(days=1)

        async def _do_refresh(_now: datetime) -> None:
            await self.async_request_refresh()
            self._schedule_next_refresh(_now)

        self._unsub_refresh = async_track_point_in_time(self.hass, _do_refresh, next_run)

    async def _async_update_data(self) -> list[TariffSlice]:
        now_local = dt_util.as_local(dt_util.now())
        start_local, end_local = _local_midnight_range(now_local)

        params = {
            "start_timestamp": start_local.isoformat(),
            "end_timestamp": end_local.isoformat(),
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.get(API_URL, params=params, timeout=20) as resp:
                resp.raise_for_status()
                payload = await resp.json()
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"API request failed: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error while fetching tariffs: {err}") from err

        if not isinstance(payload, list):
            raise UpdateFailed(f"Unexpected API response type: {type(payload)}")

        data: list[TariffSlice] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            try:
                start = _parse_iso(row["start_timestamp"])
                end = _parse_iso(row["end_timestamp"])
                vario_plus = row.get("vario_plus")
                dt_plus = row.get("dt_plus")
                unit = row.get("unit")
                data.append(
                    TariffSlice(
                        start=start,
                        end=end,
                        vario_plus=float(vario_plus) if vario_plus is not None else None,
                        dt_plus=float(dt_plus) if dt_plus is not None else None,
                        unit=str(unit) if unit is not None else None,
                    )
                )
            except Exception:
                continue

        data.sort(key=lambda s: s.start)
        return data

    def get_current_slice(self, now: datetime | None = None) -> TariffSlice | None:
        if now is None:
            now = dt_util.as_local(dt_util.now())
        else:
            now = dt_util.as_local(now)
        for sl in self.data or []:
            if sl.start <= now < sl.end:
                return sl
        return None

    def is_dt_offpeak(self, now: datetime | None = None) -> bool | None:
        if now is None:
            now = dt_util.as_local(dt_util.now())
        else:
            now = dt_util.as_local(now)

        sl = self.get_current_slice(now)
        if sl is None or sl.dt_plus is None:
            return None

        day = now.date()
        day_slices = [x for x in (self.data or []) if dt_util.as_local(x.start).date() == day and x.dt_plus is not None]
        if not day_slices:
            return None

        min_dt = min(x.dt_plus for x in day_slices if x.dt_plus is not None)
        max_dt = max(x.dt_plus for x in day_slices if x.dt_plus is not None)
        if min_dt == max_dt:
            return False

        return sl.dt_plus == min_dt
