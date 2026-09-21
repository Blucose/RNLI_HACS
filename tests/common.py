"""Shared test data and helpers."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

DOMAIN = "rnli_launches"
API_URL = "https://services.rnli.org/api/launches"

TROON_SENSOR = "sensor.rnli_troon_latest_launch"
TROON_EVENT = "event.rnli_troon_launch"

TROON_LATEST = {
    "shortName": "Troon",
    "launchDate": "2026-07-14T14:28:00",
    "id": 638989,
    "cOACS": 606,
    "title": "Troon, Strathclyde",
    "website": "rnli.org/Troon",
    "lifeboat_IdNo": "13-55",
}
TROON_EARLIER = {
    **TROON_LATEST,
    "launchDate": "2026-07-13T10:00:00",
    "id": 638900,
    "lifeboat_IdNo": "14-38",
}

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
    TROON_EARLIER,
    TROON_LATEST,
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

# A launch older than the API's recent window; the feed no longer lists it.
OLD_TROON_LAUNCH = {
    "shortName": "Troon",
    "launchDate": "2026-01-01T09:00:00",
    "id": 111,
    "title": "Troon, Strathclyde",
    "website": "rnli.org/Troon",
    "lifeboat_IdNo": "13-99",
}

# A brand-new Troon launch, newer than anything in LAUNCHES
NEW_TROON_LAUNCH = {
    **TROON_LATEST,
    "launchDate": "2026-07-14T16:45:00",
    "id": 639000,
    "lifeboat_IdNo": "D-999",
}


def feed_without(station: str) -> list[dict[str, Any]]:
    """Return LAUNCHES minus one station's launches."""
    return [launch for launch in LAUNCHES if launch["shortName"] != station]


def station_entry(station: str) -> MockConfigEntry:
    """Return a config entry for a station, as the config flow creates it."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={"station_short_name": station},
        unique_id=station.lower(),
        title=f"RNLI {station}",
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add a config entry and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def refresh(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    **response: Any,
) -> None:
    """Serve a new feed response and refresh the shared coordinator."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, **response)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
