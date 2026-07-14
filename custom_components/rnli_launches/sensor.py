"""Sensor platform for RNLI Launches."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RNLIConfigEntry
from .const import ATTRIBUTION, DOMAIN, normalize_station
from .coordinator import RNLIUpdateCoordinator
from .stations import STATIONS

_LOGGER = logging.getLogger(__name__)

# The RNLI feed reports launch times in UK local time without a UTC offset
RNLI_TIMEZONE = ZoneInfo("Europe/London")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RNLIConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RNLI Launch sensor from a config entry."""
    async_add_entities([RNLILaunchSensor(entry.runtime_data)])


class RNLILaunchSensor(CoordinatorEntity[RNLIUpdateCoordinator], SensorEntity):
    """Timestamp of the most recent launch from the configured station."""

    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:sail-boat"

    def __init__(self, coordinator: RNLIUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        station = coordinator.station
        station_key = normalize_station(station)
        self._station_info = next(
            (
                info
                for name, info in STATIONS.items()
                if normalize_station(name) == station_key
            ),
            None,
        )
        self._attr_name = f"RNLI {station} Latest Launch"
        self._attr_unique_id = (
            f"{DOMAIN}_{station.lower().replace(' ', '_')}_latest_launch"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station.lower())},
            name=f"RNLI {station}",
            manufacturer="RNLI",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=(
                self._station_info["url"] if self._station_info else None
            ),
        )

    @property
    def _latest_launch(self) -> dict[str, Any] | None:
        """Return the most recent launch, if any."""
        if self.coordinator.data:
            return self.coordinator.data[0]
        return None

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the latest launch."""
        launch = self._latest_launch
        if not launch or not launch.get("launchDate"):
            return None
        try:
            launch_time = datetime.fromisoformat(launch["launchDate"])
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse launchDate: %s", launch.get("launchDate"))
            return None
        if launch_time.tzinfo is None:
            launch_time = launch_time.replace(tzinfo=RNLI_TIMEZONE)
        return launch_time

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attributes: dict[str, Any] = {
            "station_monitored": self.coordinator.station,
        }
        if self._station_info:
            # latitude/longitude place the sensor on the Home Assistant map
            attributes["latitude"] = self._station_info["latitude"]
            attributes["longitude"] = self._station_info["longitude"]
            attributes["station_url"] = self._station_info["url"]
            attributes["what3words"] = self._station_info["what3words"]
            attributes["station_type"] = self._station_info["station_type"]
        launch = self._latest_launch
        if launch is None:
            attributes["last_launch_info"] = (
                "No recent launches found for this station."
            )
            return attributes

        attributes["launch_id"] = launch.get("id")
        attributes["lifeboat_id"] = launch.get("lifeboat_IdNo")
        attributes["station_title"] = launch.get("title")
        attributes["station_website"] = launch.get("website")
        attributes["recent_launch_count"] = len(self.coordinator.data)
        # Include any other fields the API provides for the latest launch
        for key, value in launch.items():
            if key not in (
                "id",
                "lifeboat_IdNo",
                "title",
                "website",
                "shortName",
                "launchDate",
            ):
                attributes[key] = value
        return attributes
