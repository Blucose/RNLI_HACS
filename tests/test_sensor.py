"""Tests for the latest-launch sensor."""
from datetime import datetime, timezone

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .common import (
    API_URL,
    LAUNCHES,
    NEW_TROON_LAUNCH,
    OLD_TROON_LAUNCH,
    TROON_EARLIER,
    TROON_LATEST,
    TROON_SENSOR,
    feed_without,
    refresh,
    setup_entry,
    station_entry,
)

TROON_LATEST_UTC = datetime(2026, 7, 14, 13, 28, tzinfo=timezone.utc)


def _restore_troon(last_launch: object) -> tuple:
    state = State(TROON_SENSOR, "2026-01-01T09:00:00+00:00")
    return ((state, {"last_launch": last_launch}),)


async def test_last_launch_survives_restart_when_absent_from_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """After a restart, the last known launch is restored even if the API no
    longer lists it."""
    aioclient_mock.get(API_URL, json=feed_without("Troon"))
    mock_restore_cache_with_extra_data(hass, _restore_troon(OLD_TROON_LAUNCH))

    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 1, 1, 9, 0, tzinfo=timezone.utc
    )
    assert state.attributes["lifeboat_id"] == "13-99"
    assert state.attributes["recent_launch_count"] == 0


async def test_newer_launch_replaces_restored(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A newer launch in the feed advances the restored last-known launch."""
    aioclient_mock.get(API_URL, json=LAUNCHES)  # contains a July Troon launch
    mock_restore_cache_with_extra_data(hass, _restore_troon(OLD_TROON_LAUNCH))

    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == TROON_LATEST_UTC
    assert state.attributes["lifeboat_id"] == "13-55"


async def test_last_launch_kept_when_station_drops_out_of_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A later refresh that no longer lists the station keeps the last launch."""
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)
    assert hass.states.get(TROON_SENSOR).attributes["lifeboat_id"] == "13-55"

    # The station scrolls out of the recent window
    await refresh(hass, entry, aioclient_mock, json=feed_without("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == TROON_LATEST_UTC
    assert state.attributes["lifeboat_id"] == "13-55"
    assert state.attributes["recent_launch_count"] == 0


async def test_unexpected_feed_fields_are_not_exposed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Only known fields reach the attributes, whatever the feed sends."""
    hostile = {
        **TROON_LATEST,
        # Home Assistant only overwrites these when the entity sets them
        "entity_picture": "https://attacker.example/pixel.png",
        "unit_of_measurement": "pwned",
        # would move the sensor's pin on the map
        "latitude": 0.0,
        "longitude": 0.0,
        # would spoof the real lifeboat_IdNo
        "lifeboat_id": "spoofed",
        "blob": "x" * 20000,
    }
    aioclient_mock.get(API_URL, json=[hostile])
    await setup_entry(hass, station_entry("Troon"))

    attributes = hass.states.get(TROON_SENSOR).attributes
    for key in ("entity_picture", "unit_of_measurement", "blob"):
        assert key not in attributes
    assert attributes["latitude"] == pytest.approx(55.548, abs=0.01)
    assert attributes["longitude"] == pytest.approx(-4.681, abs=0.01)
    assert attributes["lifeboat_id"] == "13-55"


async def test_restored_launch_is_revalidated(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Unknown fields saved by an older version are dropped on restore."""
    aioclient_mock.get(API_URL, json=feed_without("Troon"))
    mock_restore_cache_with_extra_data(
        hass,
        _restore_troon(
            {**OLD_TROON_LAUNCH, "entity_picture": "https://attacker.example/x.png"}
        ),
    )

    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert state.attributes["lifeboat_id"] == "13-99"
    assert "entity_picture" not in state.attributes


@pytest.mark.parametrize("stored", ["garbage", {"id": "x"}, None, 42])
async def test_corrupt_restore_data_is_ignored(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, stored: object
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    mock_restore_cache_with_extra_data(hass, _restore_troon(stored))

    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == TROON_LATEST_UTC


async def test_restore_from_version_without_extra_data(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Upgrading from before 0.5.0 rebuilds the launch from the old state."""
    aioclient_mock.get(API_URL, json=feed_without("Troon"))
    mock_restore_cache(
        hass,
        (
            State(
                TROON_SENSOR,
                "2026-01-01T09:00:00+00:00",
                {
                    "launch_id": 111,
                    "lifeboat_id": "13-99",
                    "station_title": "Troon, Strathclyde",
                    "station_website": "rnli.org/Troon",
                },
            ),
        ),
    )

    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 1, 1, 9, 0, tzinfo=timezone.utc
    )
    assert state.attributes["lifeboat_id"] == "13-99"


async def test_known_launch_stays_available_during_outage(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    await refresh(hass, entry, aioclient_mock, status=500)

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == TROON_LATEST_UTC


async def test_sensor_without_launch_unavailable_during_outage(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Tower")
    await setup_entry(hass, entry)
    assert hass.states.get("sensor.rnli_tower_latest_launch").state == "unknown"

    await refresh(hass, entry, aioclient_mock, status=500)
    assert hass.states.get("sensor.rnli_tower_latest_launch").state == "unavailable"

    await refresh(hass, entry, aioclient_mock, json=LAUNCHES)
    assert hass.states.get("sensor.rnli_tower_latest_launch").state == "unknown"


async def test_bad_records_do_not_hide_real_launches(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        API_URL,
        json=[
            TROON_LATEST,
            # would sort above every real date if compared as text
            {**TROON_EARLIER, "launchDate": "garbage"},
            "not-a-dict",
            {**TROON_EARLIER, "id": 5, "launchDate": 12345},
            {**TROON_EARLIER, "id": True},
        ],
    )
    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_SENSOR)
    assert datetime.fromisoformat(state.state) == TROON_LATEST_UTC
    assert state.attributes["recent_launch_count"] == 1


async def test_readme_sensor_trigger_ignores_non_launch_changes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The sensor trigger shown in the README fires only for a new launch."""
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "triggers": {
                    "trigger": "state",
                    "entity_id": TROON_SENSOR,
                    "not_from": ["unknown", "unavailable"],
                    "not_to": ["unknown", "unavailable"],
                },
                "actions": {"event": "launch_notified"},
            }
        },
    )
    fired = []
    hass.bus.async_listen("launch_notified", fired.append)

    # an older launch leaves the feed window: attribute-only change
    await refresh(hass, entry, aioclient_mock, json=[TROON_LATEST])
    # feed outage, then recovery
    await refresh(hass, entry, aioclient_mock, status=500)
    await refresh(hass, entry, aioclient_mock, json=[TROON_LATEST])
    # integration reload
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert fired == []

    await refresh(hass, entry, aioclient_mock, json=[NEW_TROON_LAUNCH, TROON_LATEST])
    assert len(fired) == 1
