"""Tests for setup, unload and the shared feed coordinator."""
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rnli_launches.coordinator import DATA_KEY

from .common import API_URL, LAUNCHES, setup_entry, station_entry


async def test_stations_share_one_feed_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    troon = station_entry("Troon")
    await setup_entry(hass, troon)
    await setup_entry(hass, station_entry("St Ives"))
    assert aioclient_mock.call_count == 1

    await troon.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2
    assert hass.states.get("sensor.rnli_st_ives_latest_launch").attributes[
        "lifeboat_id"
    ] == "D-803"


async def test_unloading_last_station_stops_polling(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    troon = station_entry("Troon")
    st_ives = station_entry("St Ives")
    await setup_entry(hass, troon)
    await setup_entry(hass, st_ives)

    assert await hass.config_entries.async_unload(st_ives.entry_id)
    assert DATA_KEY in hass.data

    assert await hass.config_entries.async_unload(troon.entry_id)
    assert DATA_KEY not in hass.data
    assert troon.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ({"status": 500}, "Error fetching data"),
        ({"json": {"message": "An error has occurred."}}, "Unexpected response"),
        ({"json": ["junk", "junk"]}, "no usable launches"),
    ],
)
async def test_setup_retries_while_feed_unusable(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    response: dict,
    reason: str,
) -> None:
    aioclient_mock.get(API_URL, **response)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert reason in entry.reason

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=LAUNCHES)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_empty_feed_sets_up(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=[])
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.rnli_troon_latest_launch").state == "unknown"
