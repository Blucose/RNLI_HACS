"""Data update coordinator for the RNLI Launches integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_STATION, DOMAIN, REQUEST_TIMEOUT, RNLI_API_URL, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class RNLIUpdateCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Fetch RNLI launch data and filter it for one station."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.station = entry.data[CONF_STATION]
        self.session = async_get_clientsession(hass)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.station}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch the latest launches for the configured station."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self.session.get(
                    RNLI_API_URL, headers={"Accept": "application/json"}
                )
                response.raise_for_status()
                data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching data from RNLI API: {err}") from err

        if not isinstance(data, list):
            raise UpdateFailed("Unexpected response from RNLI API")

        station_launches = [
            launch
            for launch in data
            if (launch.get("shortName") or "").lower() == self.station.lower()
        ]
        # ISO 8601 date strings sort correctly as plain strings
        station_launches.sort(key=lambda x: x.get("launchDate") or "", reverse=True)

        _LOGGER.debug(
            "Found %d launches for %s", len(station_launches), self.station
        )
        return station_launches
