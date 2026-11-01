"""Market data source abstraction.

Phase 1 ships :class:`~app.market.demo.DemoMarketSource`. Phase 2 adds an MT5
source implementing the same protocol, so the hub, protocol and UI do not
change when real data is connected.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .models import SymbolSpec, Tick


class MarketDataSource(Protocol):
    name: str  # e.g. "synthetic", "mt5"
    is_synthetic: bool

    async def symbol_spec(self, symbol: str) -> SymbolSpec: ...

    def ticks(self, symbol: str) -> AsyncIterator[Tick]: ...

    async def close(self) -> None: ...
