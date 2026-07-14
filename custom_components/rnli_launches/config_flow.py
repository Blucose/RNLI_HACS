"""Config flow for RNLI Launches integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
        # Maps normalized station name -> (value to store, display label).
        # Seeded with the bundled station list; the live feed is overlaid on
        # top because its exact shortName spelling is what launches report.
        self._stations: dict[str, tuple[str, str]] = {
            normalize_station(name): (name, label)
            for name, label in STATIONS.items()
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
            if short_name:
                self._stations[normalize_station(short_name)] = (
                    short_name,
                    launch.get("title") or short_name,
                )

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

                _, label = self._stations.get(
                    normalize_station(station), (station, station)
                )
                return self.async_create_entry(
                    title=f"RNLI {label}",
                    data={CONF_STATION: station},
                )
            errors["base"] = "invalid_station"

        try:
            await self._async_overlay_live_stations()
        except (aiohttp.ClientError, TimeoutError) as err:
            # The bundled station list still populates the dropdown, so a
            # feed hiccup here is not fatal to setup.
            _LOGGER.warning("Could not fetch recent RNLI launches: %s", err)

        options = [
            SelectOptionDict(value=value, label=label)
            for value, label in sorted(
                self._stations.values(), key=lambda item: item[1]
            )
        ]
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
