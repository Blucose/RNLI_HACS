"""End-to-end test: config flow GUI -> entry -> sensor entity."""
from datetime import datetime, timezone

import pytest
from homeassistant.core import HomeAssistant

API_URL = "https://services.rnli.org/api/launches"

LAUNCHES = [
    {
        "shortName": "St Ives",
        "launchDate": "2026-07-14T14:01:07",
        "id": 638983,
        "cOACS": 586,
        "title": "St Ives, Cornwall",
        "website": "rnli.org/StIves",
        "lifeboat_IdNo": "D-803",
    },
    {
        "shortName": "Troon",
        "launchDate": "2026-07-13T10:00:00",
        "id": 638900,
        "cOACS": 606,
        "title": "Troon, Strathclyde",
        "website": "rnli.org/Troon",
        "lifeboat_IdNo": "14-38",
    },
    {
        "shortName": "Troon",
        "launchDate": "2026-07-14T14:28:00",
        "id": 638989,
        "cOACS": 606,
        "title": "Troon, Strathclyde",
        "website": "rnli.org/Troon",
        "lifeboat_IdNo": "13-55",
    },
    {
        # The feed drops the "(Co Down)" qualifier that the bundled
        # station list uses
        "shortName": "Bangor",
        "launchDate": "2026-07-14T12:00:00",
        "id": 638990,
        "cOACS": 100,
        "title": "Bangor, Co. Down",
        "website": "rnli.org/Bangor",
        "lifeboat_IdNo": "B-999",
    },
]


async def test_full_flow_creates_sensor(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
    assert result["type"] == "form", result
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "create_entry", result
    # the bundled station list's label wins over the feed title
    assert result["title"] == "RNLI Troon, Ayrshire and Arran"
    await hass.async_block_till_done()

    state = hass.states.get("sensor.rnli_troon_latest_launch")
    assert state is not None, hass.states.async_entity_ids()
    # 14:28 UK time on 2026-07-14 (BST) == 13:28 UTC
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 7, 14, 13, 28, tzinfo=timezone.utc
    )
    assert state.attributes["lifeboat_id"] == "13-55"
    assert state.attributes["station_title"] == "Troon, Strathclyde"
    assert state.attributes["recent_launch_count"] == 2


async def test_duplicate_station_aborts(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_short_name": "Troon"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_dropdown_lists_all_stations(hass: HomeAssistant, aioclient_mock) -> None:
    """The form offers the full bundled station list, with live names overlaid."""
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
    selector = result["data_schema"].schema["station_short_name"]
    values = [option["value"] for option in selector.config["options"]]
    assert len(values) >= 238
    assert "Aith" in values  # static-only station, no recent launches
    # the live feed's spelling replaces the bundled "Bangor (Co Down)"
    assert "Bangor" in values
    assert "Bangor (Co Down)" not in values


async def test_static_station_name_matches_feed_variant(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A stored bundled name still matches the feed's different spelling."""
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
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
    hass: HomeAssistant, aioclient_mock
) -> None:
    """With a home location set, the nearest station is offered first."""
    aioclient_mock.get(API_URL, json=LAUNCHES)
    hass.config.latitude = 55.55  # just up the road from Troon lifeboat station
    hass.config.longitude = -4.68

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
    selector = result["data_schema"].schema["station_short_name"]
    options = selector.config["options"]
    assert options[0]["value"] == "Troon"
    assert "(0 km)" in options[0]["label"]


async def test_custom_station_no_launches(hass: HomeAssistant, aioclient_mock) -> None:
    """A typed-in station that has no recent launches still sets up."""
    aioclient_mock.get(API_URL, json=LAUNCHES)

    result = await hass.config_entries.flow.async_init(
        "rnli_launches", context={"source": "user"}
    )
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
