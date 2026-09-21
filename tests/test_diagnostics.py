"""Tests for diagnostics."""
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rnli_launches.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .common import (
    API_URL,
    LAUNCHES,
    TROON_EARLIER,
    TROON_LATEST,
    setup_entry,
    station_entry,
)


async def test_diagnostics(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"] == {"station_short_name": "Troon"}
    assert diagnostics["station"] == {
        "normalized_name": "troon",
        "in_bundled_station_list": True,
        # newest first
        "launches_in_feed": [TROON_LATEST, TROON_EARLIER],
    }
    assert diagnostics["feed"] == {
        "last_update_success": True,
        "last_exception": None,
        "stations_in_feed": ["bangor", "st ives", "troon"],
    }
