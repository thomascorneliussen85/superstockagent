# Architecture

```
┌──────────────── Chrome ────────────────┐        ┌──────────── Local PC ─────────────┐
│ tradingview.com tab                    │        │ FastAPI backend (127.0.0.1:8765)  │
│  └─ content.js                         │        │                                   │
│     └─ Shadow DOM ─ React panel        │        │  MarketHub ── CandleBuilder ×4 TF │
│          ▲ chrome.runtime Port         │        │     ▲  (1m/5m/15m/1h, bid-based)  │
│ background.js (service worker)         │  WS    │     │                             │
│  └─ BackendClient ─────────────────────┼───────►│  /ws  (origin check + token)      │
│     auth · ping · backoff · liveness   │        │  /api/health, /api/status         │
└────────────────────────────────────────┘        │     │                             │
                                                  │  MarketDataSource                 │
                                                  │   ├─ DemoMarketSource             │
                                                  │   └─ Mt5MarketSource (read-only)  │
                                                  └───────────────────────────────────┘
```

## Key decisions

| Decision | Why |
|---|---|
| The WebSocket lives in the **service worker**, not the content script | Network calls from a content script are subject to TradingView's CSP and carry the page's origin. The worker has the `chrome-extension://<id>` origin, which the backend can validate. This was tested end-to-end against a page with a strict `connect-src 'self'` CSP. |
| The panel is rendered in a **Shadow DOM** and Tailwind CSS is injected inline | TradingView's CSS and the panel's CSS cannot affect each other. |
| The panel **does not read TradingView's chart** | There is no supported API for that. All data comes from our backend (MT5), so the analysis does not depend on TradingView's DOM. |
| Key and wheel events are stopped at the panel | Typing in the panel does not trigger TradingView hotkeys, and scrolling it does not zoom the chart. |
| `PanelRelay` keeps the latest state | A panel that mounts or reconnects late always starts from a full snapshot. A real bug of this kind was found and fixed during e2e testing. |
| **One `CandleBuilder`** for live data and replay | Candles are built deterministically from ticks, bid-based like MT5 charts. Published candles are immutable snapshots, so replay cannot leak future data (Phase 7). |
| The source is a `Protocol` | MT5 and the demo feed are interchangeable; the hub, the protocol and the UI do not care which one is used. |
| Deterministic analysis is kept separate from the LLM | Indicators will be computed in Python. The LLM only gets a compact, event-triggered summary (Phase 3). |

## MT5 data path

1. **Connect.** `initialize()` attaches to the running terminal. The account type (`account_info().trade_mode`) decides whether the mode is `mt5_demo` or `mt5_live`. `mt5_demo`/`mt5_live` in config refuse to run if the account type differs.
2. **Find the symbol.** The broker's symbol is resolved (`XAUUSD`, `XAUUSD.m`, `GOLD`, …). Inside the app it is always called `XAUUSD`.
3. **Contract spec.** Comes from `symbol_info`: contract size, volume min/step/max, tick value/size, digits.
4. **Broker time.** The server time offset is measured from live ticks (rounded to 30 min) and saved in `data/mt5_utc_offset.json`. All timestamps are then converted to UTC.
5. **History.** `copy_rates_from_pos` loads 500 bars per timeframe. The newest bar seeds the `CandleBuilder` as the still-forming candle.
6. **Live ticks.** `copy_ticks_from(COPY_TICKS_INFO)` is polled every 100 ms. This delivers every tick, unlike polling `symbol_info_tick`, which can miss some. Ticks are deduplicated by `time_msc`, and by count when several share the same millisecond.
7. **Health.** `terminal_info().connected` is checked every 5 s. Any error makes the hub reconnect with backoff, and the panel shows a plain message.
8. **Read-only guard.** `tests/test_readonly.py` fails if any trading call (such as `order_send` or `order_check`) appears in `app/`.

## Analysis layer

`app/analysis/` is pure, deterministic Python with no language model. The indicator definitions follow TradingView's built-ins (`ta.ema`, `ta.rma`, `ta.rsi`, `ta.atr`, `ta.supertrend`), so the values can be compared with the chart. RSI is tested against Wilder's published example.

- Indicators include the still-forming candle, like a live chart.
- Structure, levels, patterns and events use only closed candles. A swing needs 3 bars after it before it counts, so nothing depends on data that hasn't happened yet.
- Results are published as `analysis` messages at most once per second, and only when data has changed. Each one is retained so a newly connected panel gets it straight away.

## Security model

- The backend refuses to bind to anything other than loopback (enforced by a config validator).
- **Origin check** on the WebSocket handshake. Pages from other websites, including tradingview.com itself, get a 403. Extension IDs can be pinned. Clients that send no Origin header (scripts and tools) still need the token.
- A **token** (32 random bytes) is sent as the first WebSocket message, never in the URL, and compared in constant time. REST calls use `Authorization: Bearer`. `/api/health` is the only unauthenticated endpoint, and it reveals nothing about the account.
- If authentication fails, the connection closes with code 4401. The client then backs off for 30 s rather than hammering the server.
- **Demo and live are clearly separated.** `mode` is part of every `hello`/`status` message. The panel always shows a badge: `SIMULERT` (amber), `MT5 DEMO` (blue) or `LIVE` (red). A banner appears whenever the data is synthetic.
- The system is read-only: no endpoint exists that can trade.

## WebSocket protocol (v1)

Client → server: `{"type":"auth","token":"…"}` (must arrive first, within 5 s), then `{"type":"ping","t":…}`.

Server → client:

| type | data |
|---|---|
| `hello` | `serverVersion, protocol, mode, readOnly, symbol` |
| `status` / `heartbeat` | `state (starting/live/stale/disconnected), mode, source, synthetic, lastTickAgeMs, ticksReceived, reconnects, lastError` |
| `symbol` | contract spec: `digits, point, contractSize, volumeMin/Step/Max, currencyProfit` |
| `tick` | `symbol, t, bid, ask, spread` |
| `candle` | `tf, t, o, h, l, c, n, maxSpread, closed` (forming candles update in place) |
| `candles` | `tf, candles[]` (snapshot when a client connects) |
| `analysis` | per-timeframe indicators/trend/structure/levels/liquidity/patterns/events, `alignment`, `spread` stats, `recentEvents` |

All times are UTC epoch milliseconds. Backend datetimes are always timezone-aware.

## Reliability

- **Slow clients:** each client has a bounded queue that drops the oldest messages first, so a frozen tab cannot block the feed.
- **Source errors:** the hub restarts the data source with exponential backoff, up to 30 s.
- **Freshness:** the backend reports `live`/`stale`/`disconnected`. The panel separately shows how old the last tick is, based on when it arrived locally.
- **Client side:** the client reconnects with jittered exponential backoff. If nothing arrives for 45 s, it forces a reconnect. It pings every 20 s, which also keeps the MV3 worker alive (Chrome 116+). If the service worker restarts, the content-script Port reconnects automatically.
