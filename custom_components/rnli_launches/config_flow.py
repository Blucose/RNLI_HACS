"""Config flow for RNLI Launches integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import location as location_util

from .api import Launch, RNLIApiError, async_fetch_launches
from .const import CONF_STATION, DOMAIN, MAX_STATION_LENGTH, normalize_station
from .coordinator import DATA_KEY
from .stations import STATIONS

_LOGGER = logging.getLogger(__name__)


def _validate_station(user_input: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Return the cleaned-up station name and any form errors."""
    station = str(user_input[CONF_STATION]).strip()
    # A name like "(Co Down)" normalizes to nothing and matches no station
    if not normalize_station(station):
        return station, {CONF_STATION: "invalid_station"}
    if len(station) > MAX_STATION_LENGTH:
        return station, {CONF_STATION: "station_too_long"}
    return station, {}


class RNLIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RNLI Launches."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize RNLI config flow."""
        # Maps normalized station name -> {value, label, latitude, longitude}.
        # Seeded with the bundled station list; live feed spellings are
        # overlaid on top because they are what launches report.
        self._stations: dict[str, dict[str, Any]] = {
            normalize_station(name): {
                "value": name,
                "label": info["label"],
                "latitude": info["latitude"],
                "longitude": info["longitude"],
            }
            for name, info in STATIONS.items()
        }
        self._live_stations_loaded = False

    async def _async_recent_launches(self) -> list[Launch]:
        """Return recent launches, reusing the running integration's feed."""
        if (data := self.hass.data.get(DATA_KEY)) and data.coordinator.data:
            return [
                launch
                for launches in data.coordinator.data.values()
                for launch in launches
            ]
        return await async_fetch_launches(async_get_clientsession(self.hass))

    async def _async_overlay_live_stations(self) -> None:
        """Overlay station names seen in the recent-launches feed, once."""
        if self._live_stations_loaded:
            return
        self._live_stations_loaded = True
        try:
            launches = await self._async_recent_launches()
        except RNLIApiError as err:
            # The bundled station list still populates the dropdown, so a
            # feed problem here is not fatal to setup.
            _LOGGER.warning("Could not fetch recent RNLI launches: %s", err)
            return

        for launch in launches:
            key = normalize_station(launch.short_name)
            entry = self._stations.setdefault(key, {})
            entry["value"] = launch.short_name
            entry.setdefault("label", launch.title or launch.short_name)

    def _station_options(self) -> list[SelectOptionDict]:
        """Build dropdown options, nearest to the home location first."""
        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude

        def sort_key(entry: dict[str, Any]) -> tuple[int, float, str]:
            if home_lat and home_lon and entry.get("latitude") is not None:
                dist = location_util.distance(
                    home_lat, home_lon, entry["latitude"], entry["longitude"]
                )
                if dist is not None:
                    return (0, dist, entry["label"])
            return (1, 0.0, entry["label"])

        options = []
        for entry in sorted(self._stations.values(), key=sort_key):
            group, dist, _ = sort_key(entry)
            label = entry["label"]
            if group == 0:
                label = f"{label} ({dist / 1000:.0f} km)"
            options.append(SelectOptionDict(value=entry["value"], label=label))
        return options

    def _entry_title(self, station: str) -> str:
        """Return the entry title for a station, preferring its full label."""
        entry = self._stations.get(normalize_station(station), {})
        return f"RNLI {entry.get('label', station)}"

    async def _async_show_station_form(
        self, step_id: str, errors: dict[str, str], station: str | None = None
    ) -> ConfigFlowResult:
        """Show the station picker, prefilled with a station if given."""
        await self._async_overlay_live_stations()
        schema = vol.Schema(
            {
                vol.Required(CONF_STATION): SelectSelector(
                    SelectSelectorConfig(
                        options=self._station_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                        sort=False,
                    )
                )
            }
        )
        if station is not None:
            schema = self.add_suggested_values_to_schema(
                schema, {CONF_STATION: station}
            )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station, errors = _validate_station(user_input)
            if not errors:
                await self.async_set_unique_id(normalize_station(station))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._entry_title(station),
                    data={CONF_STATION: station},
                )
        return await self._async_show_station_form("user", errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user switch an existing entry to another station."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            station, errors = _validate_station(user_input)
            if not errors:
                unique_id = normalize_station(station)
                if unique_id != entry.unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=self._entry_title(station),
                    data_updates={CONF_STATION: station},
                )
        return await self._async_show_station_form(
            "reconfigure", errors, entry.data[CONF_STATION]
        )
