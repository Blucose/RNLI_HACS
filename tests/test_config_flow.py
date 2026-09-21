"""Tests for the config flow: setup GUI and reconfigure."""
from datetime import datetime, timezone

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .common import (
    API_URL,
    DOMAIN,
    LAUNCHES,
    TROON_SENSOR,
    setup_entry,
    station_entry,
)


async def _start_flow(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )


async def _start_reconfigure(hass: HomeAssistant, entry) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )


def _device_identifiers(device_registry: dr.DeviceRegistry, entry) -> list[set]:
    return [
        device.identifiers
        for device in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        )
    ]


def _options(result: dict) -> list[dict]:
    return result["data_schema"].schema["station_short_name"].config["options"]


async def test_full_flow_creates_sensor(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await _start_flow(hass)
    assert result["type"] == "form", result
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "create_entry", result
    # the bundled station list's label wins over the feed title
    assert result["title"] == "RNLI Troon, Ayrshire and Arran"
    await hass.async_block_till_done()

    state = hass.states.get(TROON_SENSOR)
    assert state is not None, hass.states.async_entity_ids()
    # entity name comes from translations, prefixed with the device name
    assert state.attributes["friendly_name"] == "RNLI Troon Latest launch"
    # 14:28 UK time on 2026-07-14 (BST) == 13:28 UTC
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 7, 14, 13, 28, tzinfo=timezone.utc
    )
    assert state.attributes["lifeboat_id"] == "13-55"
    assert state.attributes["station_title"] == "Troon, Strathclyde"
    assert state.attributes["recent_launch_count"] == 2
    assert hass.states.get("event.rnli_troon_launch") is not None


async def test_duplicate_station_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_dropdown_lists_all_stations(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The form offers the full bundled station list, with live names overlaid."""
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await _start_flow(hass)
    values = [option["value"] for option in _options(result)]
    assert len(values) >= 238
    assert "Aith" in values  # static-only station, no recent launches
    # the live feed's spelling replaces the bundled "Bangor (Co Down)"
    assert "Bangor" in values
    assert "Bangor (Co Down)" not in values


async def test_static_station_name_matches_feed_variant(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A stored bundled name still matches the feed's different spelling."""
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Bangor (Co Down)"}
    )
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()

    state = hass.states.get("sensor.rnli_bangor_co_down_latest_launch")
    assert state is not None, hass.states.async_entity_ids()
    assert state.attributes["lifeboat_id"] == "B-999"
    # station metadata from the bundled list, placing the sensor on the map
    assert state.attributes["latitude"] == pytest.approx(54.66, abs=0.1)
    assert state.attributes["longitude"] == pytest.approx(-5.67, abs=0.1)
    assert state.attributes["station_type"] in ("ALB", "ILB")
    assert state.attributes["station_url"].startswith("https://rnli.org/")


async def test_dropdown_sorted_by_distance_from_home(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With a home location set, the nearest station is offered first."""
    aioclient_mock.get(API_URL, json=LAUNCHES)
    hass.config.latitude = 55.55  # just up the road from Troon lifeboat station
    hass.config.longitude = -4.68

    options = _options(await _start_flow(hass))
    assert options[0]["value"] == "Troon"
    assert "(0 km)" in options[0]["label"]


async def test_custom_station_no_launches(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A typed-in station that has no recent launches still sets up."""
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Tower"}
    )
    assert result["type"] == "create_entry", result
    # "Tower" is in the bundled station list, so it gets the full label
    assert result["title"] == "RNLI Tower, Greater London"
    await hass.async_block_till_done()

    state = hass.states.get("sensor.rnli_tower_latest_launch")
    assert state is not None
    assert state.state == "unknown"
    assert "last_launch_info" in state.attributes


@pytest.mark.parametrize(
    "response",
    [
        {"status": 500},
        {"exc": TimeoutError()},
        {"exc": aiohttp.ClientError()},
        {"json": {"message": "An error has occurred."}},
        {"text": '[{"shortName": "Tro'},
        {"json": ["junk", 1, None]},
    ],
)
async def test_form_survives_feed_problems(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, response: dict
) -> None:
    """A broken feed still leaves the bundled station list to choose from."""
    aioclient_mock.get(API_URL, **response)

    result = await _start_flow(hass)
    assert result["type"] == "form"
    assert len(_options(result)) >= 238


@pytest.mark.parametrize(
    ("station", "error"),
    [
        ("   ", "invalid_station"),
        # normalizes to nothing, so it would match no station
        ("(Co Down)", "invalid_station"),
        ("A" * 101, "station_too_long"),
    ],
)
async def test_invalid_station_names(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, station: str, error: str
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": station}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"station_short_name": error}
    # the feed is fetched once per flow, not again for the redisplayed form
    assert aioclient_mock.call_count == 1


async def test_flow_reuses_running_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Adding a second station does not fetch the feed again."""
    aioclient_mock.get(API_URL, json=LAUNCHES)
    await setup_entry(hass, station_entry("Troon"))
    assert aioclient_mock.call_count == 1

    result = await _start_flow(hass)
    assert "Bangor" in [option["value"] for option in _options(result)]
    assert aioclient_mock.call_count == 1


async def test_reconfigure_changes_station(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)
    assert _device_identifiers(device_registry, entry) == [{(DOMAIN, "troon")}]

    result = await _start_reconfigure(hass, entry)
    assert result["type"] == "form"
    # the current station is prefilled
    key = next(iter(result["data_schema"].schema))
    assert key.description == {"suggested_value": "Troon"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "St Ives"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.data == {"station_short_name": "St Ives"}
    assert entry.unique_id == "st ives"
    assert entry.title == "RNLI St Ives, Cornwall"
    # the old station's device and entities are gone, the new ones exist
    assert _device_identifiers(device_registry, entry) == [{(DOMAIN, "st ives")}]
    assert entity_registry.async_get(TROON_SENSOR) is None
    assert hass.states.get(TROON_SENSOR) is None
    state = hass.states.get("sensor.rnli_st_ives_latest_launch")
    assert state.attributes["lifeboat_id"] == "D-803"


async def test_reconfigure_to_configured_station_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    troon = station_entry("Troon")
    await setup_entry(hass, troon)
    await setup_entry(hass, station_entry("St Ives"))

    result = await _start_reconfigure(hass, troon)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "St Ives"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert troon.data == {"station_short_name": "Troon"}


async def test_reconfigure_keeps_same_station(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert hass.states.get(TROON_SENSOR).attributes["lifeboat_id"] == "13-55"
