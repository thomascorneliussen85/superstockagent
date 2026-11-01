"""Core market data types.

Timestamps are always timezone-aware UTC internally and serialized as integer
milliseconds since the Unix epoch on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def utc_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        raise ValueError("naive datetime: all timestamps must be timezone-aware")
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"

    @property
    def ms(self) -> int:
        return {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}[self.value]


@dataclass(frozen=True, slots=True)
class Tick:
    symbol: str
    time_ms: int
    bid: float
    ask: float
    volume: float = 0.0  # tick volume where available; not exchange volume for spot gold

    def __post_init__(self) -> None:
        if self.ask < self.bid:
            raise ValueError(f"ask {self.ask} < bid {self.bid}")

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    def to_wire(self, digits: int) -> dict:
        return {
            "symbol": self.symbol,
            "t": self.time_ms,
            "bid": round(self.bid, digits),
            "ask": round(self.ask, digits),
            "spread": round(self.spread, digits),
        }


@dataclass(slots=True)
class Candle:
    """OHLC candle built from bid prices (matches MT5 chart convention)."""

    symbol: str
    timeframe: Timeframe
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    tick_count: int = 1
    max_spread: float = 0.0
    closed: bool = False

    def to_wire(self, digits: int) -> dict:
        return {
            "symbol": self.symbol,
            "tf": self.timeframe.value,
            "t": self.open_time_ms,
            "o": round(self.open, digits),
            "h": round(self.high, digits),
            "l": round(self.low, digits),
            "c": round(self.close, digits),
            "n": self.tick_count,
            "maxSpread": round(self.max_spread, digits),
            "closed": self.closed,
        }


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    """Instrument contract specification.

    Risk must be computed from these values, never from assumptions: one *lot*
    of XAUUSD is commonly 100 troy ounces, but this varies by broker. In MT5
    the authoritative source is ``symbol_info().trade_contract_size``.
    """

    symbol: str
    digits: int
    point: float
    contract_size: float  # units (troy ounces for gold) per 1.0 lot
    volume_min: float
    volume_step: float
    volume_max: float
    currency_profit: str
    description: str = ""
    source: str = field(default="demo")

    def to_wire(self) -> dict:
        return {
            "symbol": self.symbol,
            "digits": self.digits,
            "point": self.point,
            "contractSize": self.contract_size,
            "volumeMin": self.volume_min,
            "volumeStep": self.volume_step,
            "volumeMax": self.volume_max,
            "currencyProfit": self.currency_profit,
            "description": self.description,
            "source": self.source,
        }
