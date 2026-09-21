"""Client for the public RNLI launches feed.

Everything the feed returns is treated as untrusted: records are validated
field by field, and only the fields below are ever kept, so unexpected data
cannot reach entity attributes or the restore cache.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

import aiohttp

from homeassistant.util.json import json_loads

from .const import (
    MAX_RESPONSE_BYTES,
    MAX_SHOUTS,
    MAX_STATION_LENGTH,
    REQUEST_TIMEOUT,
    RNLI_API_URL,
    RNLI_TIMEZONE,
    normalize_station,
)

_LOGGER = logging.getLogger(__name__)

# Upper bound for free-text fields; real values are well under 50 characters
MAX_FIELD_LENGTH = 200
# Upper bound for launchDate; ISO 8601 with an offset is 25 characters
MAX_DATE_LENGTH = 40


class RNLIApiError(Exception):
    """The launches feed could not be fetched or understood."""


@dataclass(frozen=True, slots=True)
class Launch:
    """One validated launch from the feed."""

    id: int
    short_name: str
    # As reported, normally UK local time without an offset
    launch_date: str
    # launch_date as a timezone-aware datetime
    launch_time: datetime
    title: str | None
    website: str | None
    lifeboat_id: str | None
    coacs: int | None

    def as_dict(self) -> dict[str, Any]:
        """Return the launch in the feed's own JSON shape."""
        return {
            "id": self.id,
            "shortName": self.short_name,
            "launchDate": self.launch_date,
            "title": self.title,
            "website": self.website,
            "lifeboat_IdNo": self.lifeboat_id,
            "cOACS": self.coacs,
        }


def _text(value: Any, max_length: int = MAX_FIELD_LENGTH) -> str | None:
    """Return value if it is a reasonably sized string, else None."""
    if isinstance(value, str) and len(value) <= max_length:
        return value
    return None


def _integer(value: Any) -> int | None:
    """Return value if it is an integer, else None."""
    # bool is a subclass of int, but a JSON true/false is not a number here
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def parse_launch_time(value: Any) -> datetime | None:
    """Parse a launchDate into a timezone-aware datetime."""
    if (text := _text(value, MAX_DATE_LENGTH)) is None:
        return None
    try:
        launch_time = datetime.fromisoformat(text)
    except ValueError:
        return None
    if launch_time.tzinfo is None:
        launch_time = launch_time.replace(tzinfo=RNLI_TIMEZONE)
    return launch_time


def parse_launch(raw: Any) -> Launch | None:
    """Validate one launch record, returning None if it is unusable."""
    if not isinstance(raw, dict):
        return None
    launch_id = _integer(raw.get("id"))
    short_name = _text(raw.get("shortName"), MAX_STATION_LENGTH)
    launch_time = parse_launch_time(raw.get("launchDate"))
    if (
        launch_id is None
        or short_name is None
        or not normalize_station(short_name)
        or launch_time is None
    ):
        return None
    return Launch(
        id=launch_id,
        short_name=short_name,
        launch_date=raw["launchDate"],
        launch_time=launch_time,
        title=_text(raw.get("title")),
        website=_text(raw.get("website")),
        lifeboat_id=_text(raw.get("lifeboat_IdNo")),
        coacs=_integer(raw.get("cOACS")),
    )


async def _async_read_limited(response: aiohttp.ClientResponse) -> bytes:
    """Read the response body, refusing anything implausibly large."""
    body = bytearray()
    async for chunk in response.content.iter_chunked(64 * 1024):
        body += chunk
        if len(body) > MAX_RESPONSE_BYTES:
            raise RNLIApiError("Response from RNLI API is too large")
    return bytes(body)


async def async_fetch_launches(session: aiohttp.ClientSession) -> list[Launch]:
    """Fetch the most recent launches across all stations.

    Malformed records are skipped individually so that one bad record does
    not hide every other launch.
    """
    try:
        async with (
            asyncio.timeout(REQUEST_TIMEOUT),
            session.get(
                RNLI_API_URL,
                headers={"Accept": "application/json"},
                params={"numberOfShouts": MAX_SHOUTS},
            ) as response,
        ):
            response.raise_for_status()
            body = await _async_read_limited(response)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise RNLIApiError(f"Error fetching data from RNLI API: {err}") from err

    try:
        data = json_loads(body)
    except ValueError as err:
        raise RNLIApiError("RNLI API returned invalid JSON") from err
    if not isinstance(data, list):
        raise RNLIApiError("Unexpected response from RNLI API")

    launches: list[Launch] = []
    for item in data:
        if (launch := parse_launch(item)) is None:
            _LOGGER.debug("Ignoring malformed launch record: %.200r", item)
            continue
        launches.append(launch)
    if data and not launches:
        # Every record was rejected: the feed format has probably changed
        raise RNLIApiError("RNLI API returned no usable launches")
    return launches
