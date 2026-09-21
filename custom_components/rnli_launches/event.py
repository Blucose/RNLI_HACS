"""Event platform for RNLI Launches.

The event entity fires once when a new launch appears in the feed. Unlike a
state trigger on the sensor, it does not fire for feed outages, restarts,
reloads or attribute changes, which makes it the natural automation trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.event import EventEntity, EventExtraStoredData
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from . import RNLIConfigEntry
from .api import Launch
from .const import CONF_STATION, EVENT_TYPE_LAUNCH, MAX_EVENT_AGE
from .coordinator import RNLIUpdateCoordinator
from .entity import RNLIEntity

# Comfortably more than the feed ever holds, so a launch that is still in
# the feed is never forgotten and announced a second time.
MAX_SEEN_LAUNCHES = 100


@dataclass
class RNLIEventExtraStoredData(EventExtraStoredData):
    """Event restore data, plus the launches already seen."""

    seen_launch_ids: list[int] | None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RNLIConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RNLI launch event entity from a config entry."""
    async_add_entities([RNLILaunchEvent(entry.runtime_data, entry.data[CONF_STATION])])


class RNLILaunchEvent(RNLIEntity, EventEntity):
    """Fires a launch event for each new launch from the configured station."""

    _attr_event_types = [EVENT_TYPE_LAUNCH]
    _attr_icon = "mdi:lifebuoy"
    _attr_translation_key = "launch"

    def __init__(self, coordinator: RNLIUpdateCoordinator, station: str) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator, station, "launch")
        # IDs of launches already seen, oldest first. None until the first
        # feed has been processed, which only records what is already there.
        self._seen_ids: list[int] | None = None

    @property
    def available(self) -> bool:
        """Stay available while the feed is down.

        An event has no value that can go stale, and flipping to unavailable
        and back would look like a state change to automations.
        """
        return True

    @property
    def extra_restore_state_data(self) -> RNLIEventExtraStoredData:
        """Persist the seen launches so a restart does not repeat events."""
        stored = super().extra_restore_state_data
        return RNLIEventExtraStoredData(
            stored.last_event_type, stored.last_event_attributes, self._seen_ids
        )

    async def async_added_to_hass(self) -> None:
        """Restore the seen launches, then check the feed once started."""
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None:
            seen = extra.as_dict().get("seen_launch_ids")
            if isinstance(seen, list):
                self._seen_ids = [
                    launch_id for launch_id in seen if isinstance(launch_id, int)
                ][-MAX_SEEN_LAUNCHES:]
        # Launches that arrived while Home Assistant was offline are
        # announced only once it has started, when automations are listening.
        self.async_on_remove(async_at_started(self.hass, self._async_started))

    @callback
    def _async_started(self, hass: HomeAssistant) -> None:
        """Process the current feed once Home Assistant has started."""
        self._process_launches()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.hass.state is CoreState.running:
            self._process_launches()

    @callback
    def _process_launches(self) -> None:
        """Fire an event if the feed holds launches not seen before."""
        launches = self.station_launches
        if self._seen_ids is None:
            # First run: launches already in the feed are history, not news
            self._seen_ids = [launch.id for launch in reversed(launches)]
            return

        new = [launch for launch in launches if launch.id not in self._seen_ids]
        if not new:
            return
        self._seen_ids.extend(launch.id for launch in reversed(new))
        del self._seen_ids[:-MAX_SEEN_LAUNCHES]

        # One event per update for the newest launch. An event entity's
        # state has millisecond resolution, so a second event in the same
        # update would not register as a state change.
        newest = new[0]
        if newest.launch_time < dt_util.utcnow() - MAX_EVENT_AGE:
            return
        self._trigger_event(EVENT_TYPE_LAUNCH, _event_attributes(newest))
        self.async_write_ha_state()


def _event_attributes(launch: Launch) -> dict[str, Any]:
    """Return the attributes describing a launch event."""
    return {
        "launch_id": launch.id,
        "lifeboat_id": launch.lifeboat_id,
        "launch_time": launch.launch_time.isoformat(),
        "station_title": launch.title,
        "station_website": launch.website,
    }
