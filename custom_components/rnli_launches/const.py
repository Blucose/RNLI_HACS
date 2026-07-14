"""Constants for the RNLI Launches integration."""
from datetime import timedelta

DOMAIN = "rnli_launches"
RNLI_API_URL = "https://services.rnli.org/api/launches"

CONF_STATION = "station_short_name"

ATTRIBUTION = "Data provided by the RNLI"
SCAN_INTERVAL = timedelta(minutes=5)
REQUEST_TIMEOUT = 10
