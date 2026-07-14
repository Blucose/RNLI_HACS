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

from .const import CONF_STATION, DOMAIN, REQUEST_TIMEOUT, RNLI_API_URL

_LOGGER = logging.getLogger(__name__)


class RNLIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RNLI Launches."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize RNLI config flow."""
        # Maps station shortName -> display title, e.g. "Troon" -> "Troon, Strathclyde"
        self._stations: dict[str, str] = {}

    async def _async_fetch_stations(self) -> None:
        """Populate the station list from the recent-launches feed."""
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(REQUEST_TIMEOUT):
            response = await session.get(
                RNLI_API_URL, headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            data = await response.json()

        for launch in data:
            short_name = launch.get("shortName")
            if short_name and short_name not in self._stations:
                self._stations[short_name] = launch.get("title") or short_name

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = user_input[CONF_STATION].strip()
            if station:
                await self.async_set_unique_id(station.lower())
                self._abort_if_unique_id_configured()

                title = self._stations.get(station, station)
                return self.async_create_entry(
                    title=f"RNLI {title}",
                    data={CONF_STATION: station},
                )
            errors["base"] = "invalid_station"

        if not self._stations:
            try:
                await self._async_fetch_stations()
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.error("Error fetching RNLI stations: %s", err)
                # The feed is only used to offer suggestions; the user can
                # still type a station name manually, so just warn.
                errors["base"] = "cannot_connect"

        options = [
            SelectOptionDict(value=short_name, label=title)
            for short_name, title in sorted(
                self._stations.items(), key=lambda item: item[1]
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
