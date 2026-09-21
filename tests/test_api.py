"""Tests for the feed client: validation and error handling."""
from datetime import datetime, timezone

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.rnli_launches.api import (
    RNLIApiError,
    async_fetch_launches,
    parse_launch,
    parse_launch_time,
)
from custom_components.rnli_launches.const import MAX_RESPONSE_BYTES

from .common import API_URL, TROON_LATEST


def test_parse_valid_launch() -> None:
    launch = parse_launch(TROON_LATEST)
    assert launch is not None
    assert launch.id == 638989
    assert launch.short_name == "Troon"
    assert launch.lifeboat_id == "13-55"
    assert launch.coacs == 606
    # the feed's own shape round-trips, so the restore cache stays compatible
    assert launch.as_dict() == TROON_LATEST


def test_unknown_fields_are_dropped() -> None:
    launch = parse_launch(
        {**TROON_LATEST, "entity_picture": "https://attacker.example/x.png"}
    )
    assert launch is not None
    assert "entity_picture" not in launch.as_dict()


@pytest.mark.parametrize(
    ("launch_date", "expected_utc"),
    [
        # naive times are UK local time: BST in summer, GMT in winter
        ("2026-07-14T14:28:00", datetime(2026, 7, 14, 13, 28, tzinfo=timezone.utc)),
        ("2026-01-14T14:28:00", datetime(2026, 1, 14, 14, 28, tzinfo=timezone.utc)),
        # an explicit offset is respected
        (
            "2026-07-14T14:28:00+00:00",
            datetime(2026, 7, 14, 14, 28, tzinfo=timezone.utc),
        ),
    ],
)
def test_parse_launch_time(launch_date: str, expected_utc: datetime) -> None:
    assert parse_launch_time(launch_date) == expected_utc


@pytest.mark.parametrize(
    "record",
    [
        "not-a-dict",
        None,
        [TROON_LATEST],
        {**TROON_LATEST, "id": None},
        {**TROON_LATEST, "id": "638989"},
        {**TROON_LATEST, "id": True},
        {**TROON_LATEST, "shortName": None},
        {**TROON_LATEST, "shortName": ""},
        {**TROON_LATEST, "shortName": "(Co Down)"},
        {**TROON_LATEST, "shortName": "A" * 101},
        {**TROON_LATEST, "launchDate": "garbage"},
        {**TROON_LATEST, "launchDate": 12345},
        {**TROON_LATEST, "launchDate": "2026-07-14T14:28:00" + " " * 50},
    ],
)
def test_unusable_records_are_rejected(record: object) -> None:
    assert parse_launch(record) is None


def test_bad_optional_fields_become_none() -> None:
    launch = parse_launch(
        {
            **TROON_LATEST,
            "title": 5,
            "website": "x" * 201,
            "lifeboat_IdNo": ["13-55"],
            "cOACS": "606",
        }
    )
    assert launch is not None
    assert (launch.title, launch.website, launch.lifeboat_id, launch.coacs) == (
        None,
        None,
        None,
        None,
    )


async def test_fetch_skips_malformed_records(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        API_URL, json=[TROON_LATEST, "junk", {**TROON_LATEST, "launchDate": 1}]
    )
    launches = await async_fetch_launches(async_get_clientsession(hass))
    assert [launch.id for launch in launches] == [638989]


async def test_fetch_empty_feed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(API_URL, json=[])
    assert await async_fetch_launches(async_get_clientsession(hass)) == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({"status": 500}, "Error fetching data"),
        ({"exc": TimeoutError()}, "Error fetching data"),
        ({"exc": aiohttp.ClientError()}, "Error fetching data"),
        ({"json": {"message": "An error has occurred."}}, "Unexpected response"),
        ({"text": '[{"shortName": "Tro'}, "invalid JSON"),
        ({"text": "<html>Just a moment...</html>"}, "invalid JSON"),
        ({"json": ["junk", 1, None]}, "no usable launches"),
        # valid JSON, but far bigger than the feed ever is
        ({"text": "[" + " " * MAX_RESPONSE_BYTES + "]"}, "too large"),
    ],
)
async def test_fetch_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    response: dict,
    message: str,
) -> None:
    aioclient_mock.get(API_URL, **response)
    with pytest.raises(RNLIApiError, match=message):
        await async_fetch_launches(async_get_clientsession(hass))
