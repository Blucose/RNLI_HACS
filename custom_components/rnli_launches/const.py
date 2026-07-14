"""Constants for the RNLI Launches integration."""
from datetime import timedelta

DOMAIN = "rnli_launches"
RNLI_API_URL = "https://services.rnli.org/api/launches"

CONF_STATION = "station_short_name"

ATTRIBUTION = "Data provided by the RNLI"
SCAN_INTERVAL = timedelta(minutes=5)
REQUEST_TIMEOUT = 10

# The API caps numberOfShouts at 50
MAX_SHOUTS = 50


def normalize_station(name: str) -> str:
    """Reduce a station name to a comparable base form.

    The launches feed and the RNLI open data station list disagree on
    qualifiers and punctuation ("Bangor" vs "Bangor (Co Down)",
    "Weston-super-Mare" vs "Weston Super Mare"), so comparisons drop any
    parenthetical suffix, treat hyphens as spaces, and ignore case.
    """
    base = name.split("(")[0]
    return " ".join(base.replace("-", " ").lower().split())
