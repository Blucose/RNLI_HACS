"""End-to-end test: config flow GUI -> entry -> sensor entity."""
from datetime import datetime, timezone

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
    assert result["title"] == "RNLI Troon, Strathclyde"
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
    assert result["title"] == "RNLI Tower"
    await hass.async_block_till_done()

    state = hass.states.get("sensor.rnli_tower_latest_launch")
    assert state is not None
    assert state.state == "unknown"
    assert "last_launch_info" in state.attributes
