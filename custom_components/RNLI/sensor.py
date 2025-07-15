"""Sensor platform for RNLI Launches."""
from datetime import datetime, timedelta
import logging

import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, RNLI_API_URL

_LOGGER = logging.getLogger(__name__)

# Default interval for updating data (e.g., every 5 minutes)
SCAN_INTERVAL = timedelta(minutes=5)

# Attribution for the data source
ATTRIBUTION = "Data provided by RNLI Web API"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RNLI Launch sensor from a config entry."""
    # Retrieve the station short name from the config entry data
    station_short_name = config_entry.data.get("station_short_name")

    if not station_short_name:
        _LOGGER.error("No station_short_name found in config entry. Cannot set up sensor.")
        return

    _LOGGER.debug("Setting up RNLI Launch sensor for station: %s", station_short_name)

    # Create a DataUpdateCoordinator to manage fetching data
    coordinator = RNLIUpdateCoordinator(hass, station_short_name)

    # Fetch initial data and register for updates
    await coordinator.async_config_entry_first_refresh()

    # Add the sensor entity
    async_add_entities([RNLILaunchSensor(coordinator, station_short_name)])


class RNLIUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching RNLI launch data from the API."""

    def __init__(self, hass: HomeAssistant, station_short_name: str) -> None:
        """Initialize."""
        self.station_short_name = station_short_name
        self.session = hass.helpers.aiohttp_client.get_client()
        self.headers = {"Accept": "application/json"} # Explicitly request JSON

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{station_short_name}", # Name coordinator uniquely per station
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data from the RNLI API."""
        try:
            _LOGGER.debug("Fetching RNLI launch data for %s", self.station_short_name)
            async with async_timeout.timeout(10): # Timeout after 10 seconds
                response = await self.session.get(RNLI_API_URL, headers=self.headers)
                response.raise_for_status() # Raise an exception for bad status codes
                data = await response.json()

                # Filter launches for the specified station
                station_launches = [
                    launch for launch in data
                    if launch.get("shortName") == self.station_short_name
                ]

                # Sort by launch date (most recent first)
                station_launches.sort(key=lambda x: x.get("launchDate", ""), reverse=True)

                _LOGGER.debug("Found %d launches for %s", len(station_launches), self.station_short_name)
                return station_launches

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching data from RNLI API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unknown error parsing RNLI API data: {err}") from err


class RNLILaunchSensor(CoordinatorEntity, SensorEntity):
    """Representation of an RNLI Launch sensor."""

    def __init__(self, coordinator: RNLIUpdateCoordinator, station_short_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._station_short_name = station_short_name
        self._name = f"RNLI {station_short_name} Latest Launch"
        self._state = None
        self._attributes = {}
        self._unique_id = f"{DOMAIN}_{station_short_name.lower().replace(' ', '_')}_latest_launch"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique ID to use for this sensor."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        # The state will be the timestamp of the latest launch, or 'unknown'
        if self.coordinator.data and len(self.coordinator.data) > 0:
            latest_launch = self.coordinator.data[0]
            # Convert the launchDate string to a datetime object for better handling
            try:
                # Assuming launchDate format is ISO 8601
                return datetime.fromisoformat(latest_launch.get("launchDate")).isoformat()
            except ValueError:
                _LOGGER.warning("Could not parse launchDate: %s", latest_launch.get("launchDate"))
                return "unknown"
        return "unknown"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "station_monitored": self._station_short_name,
        }
        if self.coordinator.data and len(self.coordinator.data) > 0:
            latest_launch = self.coordinator.data[0]
            attributes["launch_id"] = latest_launch.get("id")
            attributes["lifeboat_id"] = latest_launch.get("lifeboat_IdNo")
            attributes["station_title"] = latest_launch.get("title")
            attributes["station_website"] = latest_launch.get("website")
            # Add all other fields from the latest launch as attributes
            for key, value in latest_launch.items():
                if key not in ["id", "lifeboat_IdNo", "title", "website", "shortName", "launchDate"]:
                    attributes[key] = value
        else:
            attributes["last_launch_info"] = "No recent launches found for this station."
        return attributes

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        return "mdi:boat"

