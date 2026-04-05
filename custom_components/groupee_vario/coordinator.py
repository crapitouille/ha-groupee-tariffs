"""DataUpdateCoordinator for Groupe E Tariffs v2."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_ENDPOINT,
    BASE_URL,
    DEFAULT_DAILY_UPDATE_HOUR,
    DEFAULT_WINDOW_COUNT,
    DEFAULT_WINDOW_DURATION_HOURS,
    DOMAIN,
    PERIOD_OFFPEAK,
    PERIOD_PEAK,
    TARIFF_DOUBLE,
    TARIFF_VARIO,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _parse_slots(prices: list[dict]) -> list[dict]:
    slots = []
    for p in prices:
        try:
            start = datetime.fromisoformat(p["start_timestamp"])
            end = datetime.fromisoformat(p["end_timestamp"])
            integrated = p["integrated"][0].get("value") if p.get("integrated") else None
            grid = p["grid"][0].get("value") if p.get("grid") else None
            slots.append({"start": start, "end": end, "integrated": integrated, "grid": grid})
        except (KeyError, IndexError, ValueError) as err:
            _LOGGER.warning("Slot skipped: %s", err)
    slots.sort(key=lambda x: x["start"])
    return slots


def _parse_publication(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        ts_fixed = re.sub(r'(\.\d{6})\d+', r'\1', ts)
        return datetime.fromisoformat(ts_fixed)
    except (ValueError, TypeError):
        return None


def _determine_period(tariff_name: str, slot: dict | None, all_integrated: list[float]) -> bool | None:
    if tariff_name != TARIFF_DOUBLE or not slot or slot.get("integrated") is None:
        return None
    unique = sorted(set(round(v, 4) for v in all_integrated))
    if len(unique) >= 2:
        threshold = (unique[0] + unique[-1]) / 2
        return PERIOD_OFFPEAK if slot["integrated"] <= threshold else PERIOD_PEAK
    return PERIOD_PEAK


def _compute_cheap_windows(
    slots: list[dict],
    window_count: int,
    window_duration_hours: int,
) -> list[dict]:
    """Find N non-overlapping cheapest windows of given duration (greedy algorithm)."""
    slots_per_window = window_duration_hours * 4
    n = len(slots)
    if n < slots_per_window:
        return []

    prices = [s["integrated"] if s.get("integrated") is not None else float("inf") for s in slots]
    used = [False] * n
    windows = []

    for _ in range(window_count):
        best_avg = float("inf")
        best_start = -1

        for i in range(n - slots_per_window + 1):
            if any(used[i:i + slots_per_window]):
                continue
            avg = sum(prices[i:i + slots_per_window]) / slots_per_window
            if avg < best_avg:
                best_avg = avg
                best_start = i

        if best_start == -1:
            break

        for i in range(best_start, best_start + slots_per_window):
            used[i] = True

        window_slots = slots[best_start:best_start + slots_per_window]
        slot_prices = prices[best_start:best_start + slots_per_window]
        windows.append({
            "start": window_slots[0]["start"],
            "end": window_slots[-1]["end"],
            "avg_price_chf_kwh": round(best_avg, 5),
            "min_price_chf_kwh": round(min(slot_prices), 5),
            "max_price_chf_kwh": round(max(slot_prices), 5),
            "duration_hours": window_duration_hours,
            "slot_count": slots_per_window,
        })

    windows.sort(key=lambda w: w["start"])
    return windows


class GroupeETariffCoordinator(DataUpdateCoordinator[dict[str, Any]]):

    def __init__(
        self,
        hass: HomeAssistant,
        tariff_name: str,
        daily_update_hour: int = DEFAULT_DAILY_UPDATE_HOUR,
        window_count: int = DEFAULT_WINDOW_COUNT,
        window_duration_hours: int = DEFAULT_WINDOW_DURATION_HOURS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{tariff_name}",
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._tariff_name = tariff_name
        self._daily_update_hour = daily_update_hour
        self._window_count = window_count
        self._window_duration_hours = window_duration_hours
        self._unsub_daily: Any = None

    def start_daily_refresh(self) -> None:
        self._unsub_daily = async_track_time_change(
            self.hass, self._handle_daily_refresh,
            hour=self._daily_update_hour, minute=0, second=0,
        )

    def stop_daily_refresh(self) -> None:
        if self._unsub_daily:
            self._unsub_daily()
            self._unsub_daily = None

    @callback
    def _handle_daily_refresh(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh())

    async def _fetch_day(self, session: aiohttp.ClientSession, day: datetime) -> tuple[list[dict], str | None]:
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=0)
        params = {
            "tariff_name": self._tariff_name,
            "start_timestamp": day_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_timestamp": day_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        async with session.get(
            f"{BASE_URL}{API_ENDPOINT}", params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 400:
                body = await resp.json()
                raise UpdateFailed(f"Bad request (400): {body.get('error', 'unknown')}")
            if resp.status != 200:
                raise UpdateFailed(f"API HTTP error {resp.status}")
            raw = await resp.json()
        return _parse_slots(raw.get("prices", [])), raw.get("publication_timestamp")

    async def _async_update_data(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)

        try:
            async with aiohttp.ClientSession() as session:
                today_slots, publication = await self._fetch_day(session, now)
                try:
                    tomorrow_slots, tomorrow_pub = await self._fetch_day(session, now + timedelta(days=1))
                except UpdateFailed:
                    tomorrow_slots, tomorrow_pub = [], None
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        if not today_slots:
            raise UpdateFailed("No prices returned for today")

        # Current / next slot
        current_slot = None
        next_slot = None
        for i, slot in enumerate(today_slots):
            s = slot["start"] if slot["start"].tzinfo else slot["start"].replace(tzinfo=timezone.utc)
            e = slot["end"] if slot["end"].tzinfo else slot["end"].replace(tzinfo=timezone.utc)
            if s <= now < e:
                current_slot = slot
                next_slot = today_slots[i + 1] if i + 1 < len(today_slots) else (tomorrow_slots[0] if tomorrow_slots else None)
                break

        today_integrated = [s["integrated"] for s in today_slots if s["integrated"] is not None]
        tomorrow_integrated = [s["integrated"] for s in tomorrow_slots if s["integrated"] is not None]

        # Serialise slots — compact format [start_ISO16, price] to stay under 16 KB
        def serialise(slots):
            return [
                [s["start"].isoformat()[:16], round(s["integrated"], 5) if s["integrated"] is not None else None]
                for s in slots
            ]

        # Cheap windows computed per day independently
        cheap_windows = []
        if self._tariff_name == TARIFF_VARIO:
            cheap_windows = (
                _compute_cheap_windows(today_slots, self._window_count, self._window_duration_hours)
                + (_compute_cheap_windows(tomorrow_slots, self._window_count, self._window_duration_hours) if tomorrow_slots else [])
            )

        return {
            "current_slot": current_slot,
            "next_slot": next_slot,
            "min_price_today": min(today_integrated) if today_integrated else None,
            "max_price_today": max(today_integrated) if today_integrated else None,
            "min_price_tomorrow": min(tomorrow_integrated) if tomorrow_integrated else None,
            "max_price_tomorrow": max(tomorrow_integrated) if tomorrow_integrated else None,
            "tariff_period": _determine_period(self._tariff_name, current_slot, today_integrated),
            "publication_timestamp": _parse_publication(publication),
            "last_refresh": now,
            "tomorrow_publication_timestamp": _parse_publication(tomorrow_pub),
            "schedule_today": serialise(today_slots),
            "schedule_tomorrow": serialise(tomorrow_slots),
            "tariff_name": self._tariff_name,
            "tomorrow_available": len(tomorrow_slots) > 0,
            "cheap_windows": cheap_windows,
            "window_count": self._window_count,
            "window_duration_hours": self._window_duration_hours,
        }
