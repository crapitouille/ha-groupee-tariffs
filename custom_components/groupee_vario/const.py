from __future__ import annotations

DOMAIN = "groupee_vario"
NAME = "Groupe E Tariffs"

CONF_REFRESH_TIME = "refresh_time"  # "HH:MM"
DEFAULT_REFRESH_TIME = "18:00"

# Duration for the "cheapest" contiguous Vario window, in hours.
CONF_CHEAP_WINDOW_HOURS = "cheap_window_hours"  # 1..4 (hours)
DEFAULT_CHEAP_WINDOW_HOURS = 1

API_URL = "https://api.tariffs.groupe-e.ch/v1/tariffs"
USER_AGENT = "homeassistant-groupee-vario/0.3.1"
