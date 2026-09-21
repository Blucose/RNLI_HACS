"""Tests for the launch event entity."""
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, State
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .common import (
    API_URL,
    LAUNCHES,
    NEW_TROON_LAUNCH,
    TROON_EARLIER,
    TROON_EVENT,
    TROON_LATEST,
    refresh,
    setup_entry,
    station_entry,
)

# Shortly after the launches in LAUNCHES, so they count as recent
NOW = "2026-07-14 16:00:00+00:00"
LAST_EVENT = "2026-07-13T10:05:00.000+00:00"


def _event_cache(seen_launch_ids: list[int]) -> tuple:
    """Restore data for the Troon event entity, as a previous run left it."""
    return (
        (
            State(TROON_EVENT, LAST_EVENT),
            {
                "last_event_type": "launch",
                "last_event_attributes": {"launch_id": TROON_EARLIER["id"]},
                "seen_launch_ids": seen_launch_ids,
            },
        ),
    )


async def _start(hass: HomeAssistant) -> None:
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()


async def test_no_event_for_launches_already_in_feed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    await setup_entry(hass, station_entry("Troon"))

    state = hass.states.get(TROON_EVENT)
    assert state.state == "unknown"
    assert state.attributes["friendly_name"] == "RNLI Troon Launch"


async def test_new_launch_fires_event_once(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    await refresh(hass, entry, aioclient_mock, json=[NEW_TROON_LAUNCH, *LAUNCHES])

    state = hass.states.get(TROON_EVENT)
    assert state.state == "2026-07-14T16:00:00.000+00:00"
    assert state.attributes["event_type"] == "launch"
    assert state.attributes["launch_id"] == 639000
    assert state.attributes["lifeboat_id"] == "D-999"
    assert state.attributes["launch_time"] == "2026-07-14T16:45:00+01:00"
    assert state.attributes["station_title"] == "Troon, Strathclyde"

    # still in the feed on the next poll, but already announced
    freezer.tick(300)
    await refresh(hass, entry, aioclient_mock, json=[NEW_TROON_LAUNCH, *LAUNCHES])
    assert hass.states.get(TROON_EVENT).state == "2026-07-14T16:00:00.000+00:00"


async def test_other_stations_do_not_fire(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    st_ives = {**LAUNCHES[0], "id": 639001, "launchDate": "2026-07-14T16:50:00"}
    await refresh(hass, entry, aioclient_mock, json=[st_ives, *LAUNCHES])

    assert hass.states.get(TROON_EVENT).state == "unknown"


async def test_several_new_launches_fire_one_event_for_the_newest(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)

    second = {**NEW_TROON_LAUNCH, "id": 639002, "launchDate": "2026-07-14T16:40:00"}
    feed = [second, NEW_TROON_LAUNCH, *LAUNCHES]
    await refresh(hass, entry, aioclient_mock, json=feed)

    assert hass.states.get(TROON_EVENT).attributes["launch_id"] == 639000
    # neither is announced again later
    freezer.tick(300)
    await refresh(hass, entry, aioclient_mock, json=feed)
    assert hass.states.get(TROON_EVENT).state == "2026-07-14T16:00:00.000+00:00"


async def test_restart_does_not_repeat_events(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    mock_restore_cache_with_extra_data(
        hass, _event_cache([TROON_EARLIER["id"], TROON_LATEST["id"]])
    )

    await setup_entry(hass, station_entry("Troon"))

    assert hass.states.get(TROON_EVENT).state == LAST_EVENT


async def test_launch_while_offline_is_announced_once_started(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A launch that arrived while Home Assistant was down is announced, but
    only after startup, when automations are listening."""
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    # the previous run had seen only the earlier Troon launch
    mock_restore_cache_with_extra_data(hass, _event_cache([TROON_EARLIER["id"]]))
    hass.set_state(CoreState.starting)

    await setup_entry(hass, station_entry("Troon"))
    assert hass.states.get(TROON_EVENT).state == LAST_EVENT

    await _start(hass)
    state = hass.states.get(TROON_EVENT)
    assert state.state == "2026-07-14T16:00:00.000+00:00"
    assert state.attributes["launch_id"] == TROON_LATEST["id"]


async def test_first_setup_during_startup_does_not_fire(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    hass.set_state(CoreState.starting)

    await setup_entry(hass, station_entry("Troon"))
    await _start(hass)

    assert hass.states.get(TROON_EVENT).state == "unknown"


async def test_stale_launch_is_not_announced(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a long time offline, day-old launches are recorded silently."""
    freezer.move_to("2026-07-20 12:00:00+00:00")
    aioclient_mock.get(API_URL, json=LAUNCHES)
    mock_restore_cache_with_extra_data(hass, _event_cache([TROON_EARLIER["id"]]))
    entry = station_entry("Troon")

    await setup_entry(hass, entry)
    assert hass.states.get(TROON_EVENT).state == LAST_EVENT

    # and it is remembered, so it is not announced later either
    freezer.tick(300)
    await refresh(hass, entry, aioclient_mock, json=LAUNCHES)
    assert hass.states.get(TROON_EVENT).state == LAST_EVENT


async def test_seen_launches_are_persisted(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOW)
    aioclient_mock.get(API_URL, json=LAUNCHES)
    entry = station_entry("Troon")
    await setup_entry(hass, entry)
    await refresh(hass, entry, aioclient_mock, json=[NEW_TROON_LAUNCH, *LAUNCHES])

    entity = hass.data["entity_components"]["event"].get_entity(TROON_EVENT)
    stored = entity.extra_restore_state_data.as_dict()
    assert stored["seen_launch_ids"] == [
        TROON_EARLIER["id"],
        TROON_LATEST["id"],
        NEW_TROON_LAUNCH["id"],
    ]
    assert stored["last_event_type"] == "launch"


async def test_readme_automation_fires_once_per_launch(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The automation shown in the README fires for a new launch and nothing
    else."""
    freezer.move_to(NOW)
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
                    "entity_id": TROON_EVENT,
                    "not_from": "unavailable",
                    "not_to": "unavailable",
                },
                "actions": {"event": "launch_notified"},
            }
        },
    )
    fired = []
    hass.bus.async_listen("launch_notified", fired.append)

    # an older launch leaves the feed window
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

    # a reload after an event has fired does not fire it again
    freezer.tick(60)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(fired) == 1
