"""Data update coordinator for the RNLI Launches integration."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.hass_dict import HassKey

from .api import Launch, RNLIApiError, async_fetch_launches
from .const import DOMAIN, SCAN_INTERVAL, normalize_station

_LOGGER = logging.getLogger(__name__)

# Normalized station name -> that station's launches, newest first
type LaunchesByStation = dict[str, list[Launch]]


class RNLIUpdateCoordinator(DataUpdateCoordinator[LaunchesByStation]):
    """Fetch the launches feed for every configured station.

    The feed covers all stations, so one coordinator is shared by every
    config entry instead of each station polling the same URL.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Shared by all entries rather than owned by any one of them
            config_entry=None,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.session = async_get_clientsession(hass)

    async def _async_update_data(self) -> LaunchesByStation:
        """Fetch the latest launches and group them by station."""
        try:
            launches = await async_fetch_launches(self.session)
        except RNLIApiError as err:
            raise UpdateFailed(str(err)) from err

        by_station: LaunchesByStation = {}
        for launch in sorted(launches, key=lambda x: x.launch_time, reverse=True):
            key = normalize_station(launch.short_name)
            by_station.setdefault(key, []).append(launch)
        _LOGGER.debug(
            "Fetched %d launches from %d stations", len(launches), len(by_station)
        )
        return by_station

    def launches_for(self, station: str) -> list[Launch]:
        """Return a station's launches in the current feed, newest first."""
        if not self.data:
            return []
        return self.data.get(normalize_station(station), [])


@dataclass
class RNLIData:
    """Integration-wide state shared by every config entry."""

    coordinator: RNLIUpdateCoordinator
    entry_ids: set[str] = field(default_factory=set)
    # Serializes the first fetch when several entries load at once
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


DATA_KEY: HassKey[RNLIData] = HassKey(DOMAIN)
