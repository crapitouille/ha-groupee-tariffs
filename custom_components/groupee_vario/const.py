"""Constants for the Groupe E Tariffs v2 integration."""

DOMAIN = "groupe_e"

CONF_TARIFF_NAME = "tariff_name"
CONF_DAILY_UPDATE_HOUR = "daily_update_hour"
CONF_WINDOW_COUNT = "window_count"
CONF_WINDOW_DURATION_HOURS = "window_duration_hours"

TARIFF_VARIO = "vario"
TARIFF_DOUBLE = "double"
TARIFFS = [TARIFF_VARIO, TARIFF_DOUBLE]

TARIFF_LABELS = {
    "vario": "VARIO (dynamic)",
    "double": "DOUBLE (HP/HC)",
}

BASE_URL = "https://api.tariffs.groupe-e.ch"
API_ENDPOINT = "/v2/tariffs"

UPDATE_INTERVAL_MINUTES = 15
DEFAULT_DAILY_UPDATE_HOUR = 18
DEFAULT_WINDOW_COUNT = 1
DEFAULT_WINDOW_DURATION_HOURS = 2

SENSOR_CURRENT_PRICE = "current_price"
SENSOR_NEXT_PRICE = "next_price"
SENSOR_MIN_PRICE_TODAY = "min_price_today"
SENSOR_MAX_PRICE_TODAY = "max_price_today"
SENSOR_PUBLICATION_TIME = "publication_timestamp"
SENSOR_SCHEDULE = "price_schedule"
SENSOR_LAST_REFRESH = "last_refresh"
SENSOR_CHEAP_WINDOW = "cheap_window"

PERIOD_OFFPEAK = True
PERIOD_PEAK = False
