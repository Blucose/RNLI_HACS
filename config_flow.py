"""Config flow for RNLI Launches integration."""
import logging

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, RNLI_API_URL # Import constants from a new const.py

_LOGGER = logging.getLogger(__name__)

# Define schema for user input
# This will be dynamically populated with station names
DATA_SCHEMA = vol.Schema({
    vol.Required("station_short_name"): vol.In([]) # Placeholder, will be filled dynamically
})

class RNLIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RNLI Launches."""

    VERSION = 1

    def __init__(self):
        """Initialize RNLI config flow."""
        self.available_stations = {} # To store station_short_name: station_title

    async def async_step_user(
        self, user_input: dict[str, any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Fetch available stations if not already fetched
        if not self.available_stations:
            try:
                # Use Home Assistant's aiohttp client
                session = self.hass.helpers.aiohttp_client.get_client()
                headers = {"Accept": "application/json"}
                async with async_timeout.timeout(10):
                    response = await session.get(RNLI_API_URL, headers=headers)
                    response.raise_for_status()
                    data = await response.json()

                    # Extract unique shortNames and map them to titles for display
                    for launch in data:
                        short_name = launch.get("shortName")
                        title = launch.get("title")
                        if short_name and title and short_name not in self.available_stations:
                            self.available_stations[short_name] = title

                    if not self.available_stations:
                        errors["base"] = "no_stations_found"

            except (aiohttp.ClientError, async_timeout.TimeoutError) as err:
                _LOGGER.error("Error fetching RNLI stations: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.error("Unknown error fetching RNLI stations: %s", err)
                errors["base"] = "unknown"

        # If there are no stations or an error occurred, show form with error
        if errors:
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA, errors=errors
            )

        # Dynamically create the schema with available stations
        # We'll use the title for display, but store the shortName
        stations_for_selection = {
            sn: f"{title} ({sn})" for sn, title in self.available_stations.items()
        }
        selection_schema = vol.Schema({
            vol.Required("station_short_name"): vol.In(stations_for_selection)
        })

        if user_input is not None:
            selected_station_short_name = user_input["station_short_name"]

            # Prevent duplicate entries
            await self.async_set_unique_id(selected_station_short_name)
            self._abort_if_unique_id_configured()

            # Create a config entry for the selected station
            return self.async_create_entry(
                title=f"RNLI {selected_station_short_name}",
                data={"station_short_name": selected_station_short_name},
            )

        # Show the form to the user
        return self.async_show_form(
            step_id="user", data_schema=selection_schema, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, any] | None = None
    ) -> FlowResult:
        """Handle re-configuration of the integration."""
        return await self.async_step_user(user_input)
