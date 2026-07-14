"""Config flow for RNLI Launches integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import location as location_util
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_STATION,
    DOMAIN,
    MAX_SHOUTS,
    REQUEST_TIMEOUT,
    RNLI_API_URL,
    normalize_station,
)
from .stations import STATIONS

_LOGGER = logging.getLogger(__name__)


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

    async def _async_overlay_live_stations(self) -> None:
        """Overlay station names seen in the recent-launches feed."""
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(REQUEST_TIMEOUT):
            response = await session.get(
                RNLI_API_URL,
                headers={"Accept": "application/json"},
                params={"numberOfShouts": MAX_SHOUTS},
            )
            response.raise_for_status()
            data = await response.json()

        for launch in data:
            short_name = launch.get("shortName")
            if not short_name:
                continue
            key = normalize_station(short_name)
            entry = self._stations.setdefault(key, {})
            entry["value"] = short_name
            entry.setdefault("label", launch.get("title") or short_name)

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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = user_input[CONF_STATION].strip()
            if station:
                await self.async_set_unique_id(normalize_station(station))
                self._abort_if_unique_id_configured()

                entry = self._stations.get(normalize_station(station), {})
                return self.async_create_entry(
                    title=f"RNLI {entry.get('label', station)}",
                    data={CONF_STATION: station},
                )
            errors["base"] = "invalid_station"

        try:
            await self._async_overlay_live_stations()
        except (aiohttp.ClientError, TimeoutError) as err:
            # The bundled station list still populates the dropdown, so a
            # feed hiccup here is not fatal to setup.
            _LOGGER.warning("Could not fetch recent RNLI launches: %s", err)

        options = self._station_options()
        schema = vol.Schema(
            {
                vol.Required(CONF_STATION): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                        sort=False,
                    )
                )
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
