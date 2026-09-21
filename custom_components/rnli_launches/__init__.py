"""The RNLI Launches integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONF_STATION
from .coordinator import DATA_KEY, RNLIData, RNLIUpdateCoordinator
from .entity import device_identifier

PLATFORMS: list[Platform] = [Platform.EVENT, Platform.SENSOR]

type RNLIConfigEntry = ConfigEntry[RNLIUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RNLIConfigEntry) -> bool:
    """Set up RNLI Launches from a config entry."""
    if (data := hass.data.get(DATA_KEY)) is None:
        data = hass.data[DATA_KEY] = RNLIData(RNLIUpdateCoordinator(hass))
    coordinator = data.coordinator

    async with data.lock:
        # The first entry to load fetches the feed; later ones share it
        if coordinator.data is None:
            await coordinator.async_refresh()
    if coordinator.data is None:
        raise ConfigEntryNotReady(
            f"Unable to fetch RNLI launches: {coordinator.last_exception}"
        )

    _async_remove_stale_devices(hass, entry)
    data.entry_ids.add(entry.entry_id)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RNLIConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    data = hass.data[DATA_KEY]
    data.entry_ids.discard(entry.entry_id)
    if not data.entry_ids:
        # The last station is gone: stop polling and drop the cached feed
        hass.data.pop(DATA_KEY)
        await data.coordinator.async_shutdown()
    return True


@callback
def _async_remove_stale_devices(hass: HomeAssistant, entry: RNLIConfigEntry) -> None:
    """Remove devices left over from a station the entry no longer monitors.

    Reconfiguring an entry to another station creates a new device; this
    removes the old one along with its entities.
    """
    device_registry = dr.async_get(hass)
    current = device_identifier(entry.data[CONF_STATION])
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if current not in device.identifiers:
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )
