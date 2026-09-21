"""Sensor platform for RNLI Launches."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from . import RNLIConfigEntry
from .api import Launch, parse_launch
from .const import CONF_STATION
from .coordinator import RNLIUpdateCoordinator
from .entity import RNLIEntity


def _launch_from_state(state: State, station: str) -> Launch | None:
    """Rebuild a launch from a restored state (upgrade fallback).

    Used only when restoring from a version before 0.5.0, which did not
    persist the raw launch; newer versions restore the stored extra data.
    """
    attrs = state.attributes
    return parse_launch(
        {
            "id": attrs.get("launch_id"),
            "shortName": station,
            "launchDate": state.state,
            "title": attrs.get("station_title"),
            "website": attrs.get("station_website"),
            "lifeboat_IdNo": attrs.get("lifeboat_id"),
            "cOACS": attrs.get("cOACS"),
        }
    )


@dataclass
class RNLIRestoreData(ExtraStoredData):
    """The last known launch, persisted across restarts."""

    last_launch: Launch | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "last_launch": self.last_launch.as_dict() if self.last_launch else None
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RNLIConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RNLI Launch sensor from a config entry."""
    async_add_entities(
        [RNLILaunchSensor(entry.runtime_data, entry.data[CONF_STATION])]
    )


class RNLILaunchSensor(RNLIEntity, RestoreEntity, SensorEntity):
    """Timestamp of the most recent known launch from the configured station."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:sail-boat"
    _attr_translation_key = "latest_launch"

    def __init__(self, coordinator: RNLIUpdateCoordinator, station: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, station, "latest_launch")
        # The last launch we have ever seen for this station. It only ever
        # advances to a newer launch, and is restored on restart, so it
        # survives the station scrolling out of the API's recent window.
        self._last_launch: Launch | None = None

    @property
    def extra_restore_state_data(self) -> RNLIRestoreData:
        """Persist the last known launch so it survives a restart."""
        return RNLIRestoreData(self._last_launch)

    async def async_added_to_hass(self) -> None:
        """Restore the last known launch, then reconcile with fresh data."""
        await super().async_added_to_hass()

        if (extra := await self.async_get_last_extra_data()) is not None:
            # Validate again: older versions stored every field the feed sent
            self._last_launch = parse_launch(extra.as_dict().get("last_launch"))
        elif (state := await self.async_get_last_state()) is not None:
            self._last_launch = _launch_from_state(state, self.station)

        # The first refresh may already carry a newer launch than we restored.
        self._update_last_launch()

    @callback
    def _update_last_launch(self) -> None:
        """Advance to the newest launch in the feed, if it is newer."""
        if not (launches := self.station_launches):
            return
        newest = launches[0]
        if (
            self._last_launch is None
            or newest.launch_time > self._last_launch.launch_time
        ):
            self._last_launch = newest

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_last_launch()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Stay available through feed outages once a launch is known.

        The last known launch is still accurate while the feed is down, so
        only a sensor with nothing to show reports unavailable.
        """
        return super().available or self._last_launch is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last known launch."""
        return self._last_launch.launch_time if self._last_launch else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attributes: dict[str, Any] = {
            "station_monitored": self.station,
            # How many launches for this station are in the current feed window
            "recent_launch_count": len(self.station_launches),
        }
        if info := self.station_info:
            # latitude/longitude place the sensor on the Home Assistant map
            attributes["latitude"] = info["latitude"]
            attributes["longitude"] = info["longitude"]
            attributes["station_url"] = info["url"]
            attributes["what3words"] = info["what3words"]
            attributes["station_type"] = info["station_type"]

        if (launch := self._last_launch) is None:
            attributes["last_launch_info"] = "No launches seen yet for this station."
            return attributes

        attributes["launch_id"] = launch.id
        attributes["lifeboat_id"] = launch.lifeboat_id
        attributes["station_title"] = launch.title
        attributes["station_website"] = launch.website
        attributes["cOACS"] = launch.coacs
        return attributes
