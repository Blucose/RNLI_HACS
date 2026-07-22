"""Sensor platform for RNLI Launches."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RNLIConfigEntry
from .const import ATTRIBUTION, DOMAIN, normalize_station
from .coordinator import RNLIUpdateCoordinator
from .stations import STATIONS

_LOGGER = logging.getLogger(__name__)

# The RNLI feed reports launch times in UK local time without a UTC offset
RNLI_TIMEZONE = ZoneInfo("Europe/London")


def _launch_datetime(launch: dict[str, Any] | None) -> datetime | None:
    """Parse a launch's timestamp into a timezone-aware datetime."""
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


def _launch_from_state(state: State) -> dict[str, Any] | None:
    """Rebuild a launch dict from a restored state (upgrade fallback).

    Used only when restoring from a version that did not persist the raw
    launch; newer restarts use the stored extra data instead.
    """
    if state.state in (None, "", "unknown", "unavailable"):
        return None
    attrs = state.attributes
    return {
        "launchDate": state.state,
        "id": attrs.get("launch_id"),
        "lifeboat_IdNo": attrs.get("lifeboat_id"),
        "title": attrs.get("station_title"),
        "website": attrs.get("station_website"),
    }


@dataclass
class RNLIRestoreData(ExtraStoredData):
    """The last known launch, persisted across restarts."""

    last_launch: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {"last_launch": self.last_launch}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RNLIConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RNLI Launch sensor from a config entry."""
    async_add_entities([RNLILaunchSensor(entry.runtime_data)])


class RNLILaunchSensor(
    CoordinatorEntity[RNLIUpdateCoordinator], RestoreEntity, SensorEntity
):
    """Timestamp of the most recent known launch from the configured station."""

    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:sail-boat"

    def __init__(self, coordinator: RNLIUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        # The last launch we have ever seen for this station. It only ever
        # advances to a newer launch, and is restored on restart, so it
        # survives the station scrolling out of the API's recent window.
        self._last_launch: dict[str, Any] | None = None
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
    def extra_restore_state_data(self) -> RNLIRestoreData:
        """Persist the last known launch so it survives a restart."""
        return RNLIRestoreData(self._last_launch)

    async def async_added_to_hass(self) -> None:
        """Restore the last known launch, then reconcile with fresh data."""
        await super().async_added_to_hass()

        if (extra := await self.async_get_last_extra_data()) is not None:
            stored = extra.as_dict().get("last_launch")
            if stored:
                self._last_launch = stored
        elif (state := await self.async_get_last_state()) is not None:
            self._last_launch = _launch_from_state(state)

        # The first refresh may already carry a newer launch than we restored.
        self._update_last_launch()
        self.async_write_ha_state()

    @callback
    def _update_last_launch(self) -> bool:
        """Advance to the newest launch in the feed, if it is newer."""
        newest = self.coordinator.data[0] if self.coordinator.data else None
        if newest is None:
            return False
        new_dt = _launch_datetime(newest)
        current_dt = _launch_datetime(self._last_launch)
        if new_dt is not None and (current_dt is None or new_dt > current_dt):
            self._last_launch = newest
            return True
        return False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_last_launch()
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last known launch."""
        return _launch_datetime(self._last_launch)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attributes: dict[str, Any] = {
            "station_monitored": self.coordinator.station,
            # How many launches for this station are in the current feed window
            "recent_launch_count": len(self.coordinator.data),
        }
        if self._station_info:
            # latitude/longitude place the sensor on the Home Assistant map
            attributes["latitude"] = self._station_info["latitude"]
            attributes["longitude"] = self._station_info["longitude"]
            attributes["station_url"] = self._station_info["url"]
            attributes["what3words"] = self._station_info["what3words"]
            attributes["station_type"] = self._station_info["station_type"]

        launch = self._last_launch
        if launch is None:
            attributes["last_launch_info"] = (
                "No launches seen yet for this station."
            )
            return attributes

        attributes["launch_id"] = launch.get("id")
        attributes["lifeboat_id"] = launch.get("lifeboat_IdNo")
        attributes["station_title"] = launch.get("title")
        attributes["station_website"] = launch.get("website")
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
