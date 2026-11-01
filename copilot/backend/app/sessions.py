"""Trading-session classification (by UTC hour; London/NY hours shift with DST,
so these are approximate buckets used consistently everywhere)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")

SESSIONS = ("Asia", "London", "London/NY", "New York", "Sen kveld")


def session_of(utc_ms: int) -> str:
    h = datetime.fromtimestamp(utc_ms / 1000, tz=UTC).hour
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 16:
        return "London/NY"
    if 16 <= h < 21:
        return "New York"
    if 21 <= h < 23:
        return "Sen kveld"
    return "Asia"


def oslo(utc_ms: int) -> datetime:
    return datetime.fromtimestamp(utc_ms / 1000, tz=OSLO)
