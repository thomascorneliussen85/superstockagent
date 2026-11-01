# AI Trading Copilot (XAUUSD)

A Chrome extension that adds an AI panel to TradingView, plus a local Python backend that reads data from MetaTrader 5. It is built for manual scalping of gold (XAUUSD) on the 1-minute chart.

> **Status: Phase 4 (trade monitoring) is done.** The **Posisjoner** tab reads your MT5 account and open positions (read-only). It shows risk to stop-loss in money and % of balance, computed from the broker's contract spec, plus today's result against your daily loss limit. It warns about missing SL, oversized risk, price approaching SL, correlated positions, high spread while in a trade and low margin, with optional voice alerts. Phase 3: Claude writes short Norwegian comments and possible setups when something meaningful happens in the market, within a hard monthly budget; optional Norwegian voice alerts. Phase 2: The backend reads XAUUSD from your logged-in MetaTrader 5 terminal (read-only), backfills history, and computes RSI, Supertrend, EMA 9/20/50/200, ATR, market structure, support/resistance, liquidity, breakouts and candlestick patterns on 1m/5m/15m/1h. The panel's **Analyse** tab shows it with a rule-based Norwegian summary. AI commentary is Phase 3.
>
> The system is **read-only**. It never places, modifies or closes trades. Nothing in it guarantees profit.

```
copilot/
  backend/     FastAPI server (Python 3.11+): auth, WebSocket hub, candle builder, data sources
  extension/   Chrome MV3 extension (React + TypeScript + Tailwind)
  docs/        Architecture, research findings, roadmap
```

## Quick start (Windows)

### 1. Backend

**Easiest:** start MetaTrader 5 and log in, then double-click `copilot\backend\start-backend.bat`. On first run it creates a Python environment, installs packages (including `MetaTrader5`) and creates `.env` in **MT5 mode**. Python 3.12–3.14 is required; `MetaTrader5` has no wheels for 3.15 yet.

Manual alternative:

```powershell
cd copilot\backend
py -3.14 -m venv .venv   # 3.12–3.14; MetaTrader5 does not support 3.15 yet
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app
```

When it starts, the backend prints its URL (`http://127.0.0.1:8765`) and a **token**. The token is also saved in `copilot\backend\data\auth_token`. The server only listens on localhost.

### 2. Extension

```powershell
cd copilot\extension
npm install
npm run build
```

1. Open `chrome://extensions` and switch on **Developer mode**.
2. Click **Load unpacked** and choose `copilot\extension\dist`.
3. Open the extension's **Options** (right-click the icon, then *Options*). Paste the token, click **Lagre** (save), then **Test tilkobling** (test connection).
4. Optional, for stronger security: copy the extension ID shown on the options page into `copilot\backend\.env`:
   `COPILOT_ALLOWED_EXTENSION_IDS=["<id>"]`. Then restart the backend.
5. Open a chart on tradingview.com. The **AI Copilot** panel appears on the right.

Using the panel:
- Drag it by the header and resize it from the bottom-right corner.
- Double-click the header (or press ▴) to collapse it.
- Press ✕ or **Alt+Shift+A** to hide it. Clicking the extension icon also toggles it.
- Position, size, collapsed state and the selected tab are remembered.

### Dev harness (no Chrome extension needed)

```bash
cd copilot/extension && npm run dev
# open http://localhost:5173/?token=<token>
```

This shows the same panel on a mock chart page, connected directly to the backend.

## Tests

```bash
cd copilot/backend && pytest            # 87 tests: account risk (contract-spec risk, alerts, daily limit,
                                        # read-only MT5 allow-list),  AI (budget, triggers, setup validation, real-SDK request
                                        # with mocked HTTP, service end-to-end), plus: indicators (RSI checked against Wilder's published values),
                                        # structure/levels/patterns, engine, MT5 source (fake terminal),
                                        # read-only guard, candles, auth/origin, WebSocket, hub
cd copilot/extension && npm test        # 34 tests: reducer, Norwegian summaries, voice alerts, geometry, WebSocket client
cd copilot/extension && npm run build   # type-check + production build
```

CI runs all of these in `.github/workflows/copilot-ci.yml`.

## What you see in the panel

- **Marked** shows bid/ask/spread, a 1m mini chart, OHLC per timeframe, and the broker's contract spec: oz per lot, and USD per 1 USD move per 0.10 lot.
- **Analyse** has three parts:
  - **Overview:** trend, RSI, EMA stack, Supertrend and volatility per timeframe.
  - **Summary:** a short Norwegian summary for the selected timeframe, with its EMAs, RSI, ATR, Supertrend, structure, support/resistance (with distance), liquidity and patterns.
  - **Spread and log:** spread state and cost per lot, and an event log of breakouts, false breakouts and structure breaks on closed candles.
- **Status line:** connection state, data age, broker server and account currency, and `KUN LESING` (read only). Errors appear as a red line with a plain explanation, such as "MT5 is not running".

### How the trend label is decided (fixed, deterministic rule)

There are four votes, each −1, 0 or +1:
1. EMA 9 > 20 > 50 (bull), the reverse (bear), or mixed.
2. Supertrend (10, 3) direction.
3. Swing structure: higher highs and higher lows, or lower highs and lower lows.
4. Price above or below EMA 200.

A sum of +2 or more means **Opptrend** (uptrend). −2 or less means **Nedtrend** (downtrend). Anything else is **Sideveis/uklar** (sideways/unclear). This is a description of the current state, not a prediction.

## AI commentary (Phase 3)

1. Get an API key at console.anthropic.com and add `ANTHROPIC_API_KEY=sk-ant-...` to `copilot/backend/.env`. The key stays on the PC; the browser never sees it.
2. Restart the backend. The window shows `AI: claude-opus-5-5, maks 50 kr/mnd`.
3. Open the **AI** tab in the panel.

**How it works**

- **Event-driven.** The deterministic analysis is compared with the previous state, once per second. A new AI call is triggered only by meaningful changes:
  - a structure break, breakout or false breakout on 1m/5m/15m
  - a trend change on 5m/15m/1h
  - 5m RSI entering overbought or oversold
  - spread turning high
  - price reaching a level with two or more touches

  Automatic calls are at least 2 minutes apart. Pending reasons are batched into one call. **Spør AI nå** (ask now) skips the wait, but never the budget. No AI calls are made while the market is closed or on demo data.
- **What Claude gets.** A compact JSON snapshot of about 1.5k tokens (`app/ai/prompt.py`). It returns structured JSON: summary, bias, a possible setup, warnings, and evidence for and against.
- **What code checks.** The levels must be on the correct side of the entry, and the entry must be close to the price. R/R is computed by code and includes the spread; it is never taken from the model. No confidence is shown, because it hasn't been calibrated yet.
- **Budget.** Every call is logged with tokens and cost in `data/copilot.db`. A call is only made if its *worst-case* cost fits within:
  - the monthly cap
  - today's share of what is left (remaining budget ÷ remaining weekdays)
- **Kept for later learning.** The snapshot and the response are stored separately from trades, for later evaluation.
- **Voice alerts** are off by default and switched on in the AI tab. They cover setups, 5m/15m breaks and high spread, with cooldowns and deduplication. Only the visible TradingView tab speaks.

## Trade monitoring (Phase 4)

- **Data.** Each second the backend reads `account_info`, `positions_get`, `orders_get` and `history_deals_get` (today's deals). A test fails if the code calls any MT5 function outside a read-only allow-list.
- **Risk to SL.** Computed as `|entry − SL| / tick_size × tick_value_loss × lots`, using the broker's own values, in the account currency. Example: 0.10 lot (10 oz at 100 oz/lot) with a 2 USD stop risks 20 USD; 10 lots risks 2,000 USD. A stop moved beyond the entry is shown as locked-in profit.
- **Your rules.** Set in `.env`; they are used only for warnings:
  - `COPILOT_RISK_MAX_PER_TRADE_PCT` (default 1 %)
  - `COPILOT_RISK_DAILY_LOSS_LIMIT_PCT` (default 3 % of the day's starting balance)
  - `COPILOT_RISK_NEAR_SL_FRACTION` (default 25 % of the SL distance left)
- **Daily result.** Today's closed trades (profit + commission + swap) plus floating P/L, with the day starting at midnight Oslo time.
- **AI context.** Claude is told about your open gold positions, but is instructed never to tell you to close, add or move anything.

## Configuration (`copilot/backend/.env`, see `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `COPILOT_MODE` | `demo` (`mt5` in `.env.example`) | `demo` = synthetic data · `mt5` = MT5, demo/live detected · `mt5_demo`/`mt5_live` = MT5, refuses to run if the account type differs |
| `COPILOT_MT5_SYMBOL` | auto | Broker symbol name if not `XAUUSD` (e.g. `XAUUSD.m`, `GOLD`). Auto-detection tries `*XAUUSD*` and `*GOLD*`. |
| `COPILOT_MT5_UTC_OFFSET_MINUTES` | auto | Broker server time minus UTC. Measured from live ticks and remembered. |
| `COPILOT_MT5_PATH` | auto | Path to `terminal64.exe` if several terminals are installed |
| `COPILOT_PORT` | `8765` | Local port |
| `COPILOT_ALLOWED_EXTENSION_IDS` | `[]` | Pins which extension may connect |
| `COPILOT_DEMO_SEED` | random | Makes the demo feed reproducible |
| `COPILOT_STALE_AFTER_SECONDS` | `5` | No tick for this long marks the feed as stale |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/RESEARCH.md](docs/RESEARCH.md) (TradingView integration limits, and units vs ounces vs lots) and [docs/ROADMAP.md](docs/ROADMAP.md).
