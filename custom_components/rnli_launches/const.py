"""Constants for the RNLI Launches integration."""
from datetime import timedelta
from zoneinfo import ZoneInfo

DOMAIN = "rnli_launches"
RNLI_API_URL = "https://services.rnli.org/api/launches"

CONF_STATION = "station_short_name"

ATTRIBUTION = "Data provided by the RNLI"
SCAN_INTERVAL = timedelta(minutes=5)
REQUEST_TIMEOUT = 10

# The API caps numberOfShouts at 50
MAX_SHOUTS = 50

# A full feed of 50 launches is under 10 KB. Anything far larger is not the
# feed we expect, so stop reading instead of buffering it all in memory.
MAX_RESPONSE_BYTES = 1024 * 1024

# Longest station name accepted from the setup form or from the feed
MAX_STATION_LENGTH = 100

# The RNLI feed reports launch times in UK local time without a UTC offset
RNLI_TIMEZONE = ZoneInfo("Europe/London")

EVENT_TYPE_LAUNCH = "launch"

# Launches older than this are never announced as new, e.g. ones that
# happened while Home Assistant was offline for a long time.
MAX_EVENT_AGE = timedelta(hours=24)


def normalize_station(name: str) -> str:
    """Reduce a station name to a comparable base form.

    The launches feed and the RNLI open data station list disagree on
    qualifiers and punctuation ("Bangor" vs "Bangor (Co Down)",
    "Weston-super-Mare" vs "Weston Super Mare"), so comparisons drop any
    parenthetical suffix, treat hyphens as spaces, and ignore case.
    """
    base = name.split("(")[0]
    return " ".join(base.replace("-", " ").lower().split())
