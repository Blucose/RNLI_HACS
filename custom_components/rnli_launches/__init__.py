"""The RNLI Launches integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import RNLIUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type RNLIConfigEntry = ConfigEntry[RNLIUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RNLIConfigEntry) -> bool:
    """Set up RNLI Launches from a config entry."""
    coordinator = RNLIUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RNLIConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
