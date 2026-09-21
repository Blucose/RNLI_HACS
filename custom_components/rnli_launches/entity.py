"""Base entity for RNLI Launches."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Launch
from .const import ATTRIBUTION, DOMAIN, normalize_station
from .coordinator import RNLIUpdateCoordinator
from .stations import STATIONS

_STATIONS_BY_KEY = {normalize_station(name): info for name, info in STATIONS.items()}


def station_info(station: str) -> dict[str, Any] | None:
    """Return the bundled open data details for a station, if known."""
    return _STATIONS_BY_KEY.get(normalize_station(station))


def device_identifier(station: str) -> tuple[str, str]:
    """Return the device registry identifier for a station."""
    return (DOMAIN, station.lower())


class RNLIEntity(CoordinatorEntity[RNLIUpdateCoordinator]):
    """An entity belonging to one lifeboat station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RNLIUpdateCoordinator, station: str, key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.station = station
        self.station_info = station_info(station)
        self._attr_unique_id = f"{DOMAIN}_{station.lower().replace(' ', '_')}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(station)},
            name=f"RNLI {station}",
            manufacturer="RNLI",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=(
                self.station_info["url"] if self.station_info else None
            ),
        )

    @property
    def station_launches(self) -> list[Launch]:
        """Return this station's launches in the current feed, newest first."""
        return self.coordinator.launches_for(self.station)
