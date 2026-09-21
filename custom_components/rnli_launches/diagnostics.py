"""Diagnostics support for RNLI Launches."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import RNLIConfigEntry
from .const import CONF_STATION, normalize_station
from .entity import station_info


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RNLIConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Nothing here is sensitive: the integration has no credentials and the
    feed is public. The home location is deliberately left out.
    """
    coordinator = entry.runtime_data
    station = entry.data[CONF_STATION]
    return {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
        },
        "station": {
            "normalized_name": normalize_station(station),
            "in_bundled_station_list": station_info(station) is not None,
            "launches_in_feed": [
                launch.as_dict() for launch in coordinator.launches_for(station)
            ],
        },
        "feed": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": (
                repr(coordinator.last_exception)
                if coordinator.last_exception
                else None
            ),
            # Helps spot a station whose feed spelling does not match
            "stations_in_feed": sorted(coordinator.data or {}),
        },
    }
