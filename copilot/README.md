# AI Trading Copilot (XAUUSD)

A Chrome extension that adds an AI panel to TradingView, plus a local Python backend that reads data from MetaTrader 5. It is built for manual scalping of gold (XAUUSD) on the 1-minute chart.

> **Status: all eight phases are implemented.**
> 1. Panel in TradingView.
> 2. Live MT5 data and deterministic analysis.
> 3. Claude commentary with a hard budget, plus voice alerts.
> 4. Read-only position and risk monitoring.
> 5. Trading journal with analytics.
> 6. Personal coach and learning system.
> 7. Tick-by-tick replay simulator with simulated orders and hotkeys.
> 8. Simulations, stability and performance tests.
>
> The system is **read-only**. It never places, modifies or closes trades. Nothing in it guarantees profit.

```
copilot/
  backend/     FastAPI server (Python 3.11+): auth, WebSocket hub, candle builder, data sources
  extension/   Chrome MV3 extension (React + TypeScript + Tailwind)
  docs/        Architecture, research findings, roadmap
```

## Install and update (Windows, recommended)

1. Download `copilot/installer.bat` and double-click it. It needs Git for Windows; GitHub Desktop's built-in git is used if found. The installer does four things:
   - clones this repository to `%USERPROFILE%\AITradingCopilot`
   - copies `.env` and `data/` (API key, token, journal) from an old zip installation
   - creates the desktop shortcuts **AI Copilot - start** and **AI Copilot - oppdater** (update)
   - shows the one-time Chrome step: *Load unpacked* → `AITradingCopilot\copilot\extension\dist`
2. **To update later**, double-click **AI Copilot - oppdater**. It runs `git fetch` and a hard reset to the branch; files ignored by git are never touched. Then restart the backend and press ↻ on the extension.

The built extension (`copilot/extension/dist`) is committed, so updating needs no Node.js on the PC. Rebuild with `npm run build` before committing extension changes.

## Quick start (Windows, manual)

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
cd copilot/backend && pytest            # 112 tests (indicators vs. Wilder reference, MT5 via fake terminal,
                                        # read-only guards, AI budget/validation, risk, journal, coach statistics,
                                        # replay look-ahead, simulations, stability and performance)
cd copilot/extension && npm test        # 37 tests: reducer, Norwegian summaries, voice alerts, hotkeys, geometry, WebSocket client
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

## Journal & coach (Phases 5-6)

The page opens from the panel's **Coach** tab via **Journal og coach**.

- **Journal data.**
  - MT5 deals are imported into `deals_raw`. It is insert-only, keyed by deal ticket, so there are no duplicates.
  - Round-trip trades are rebuilt deterministically from those deals. The initial SL/TP comes from the entry order, or from the first live sighting.
  - Entry context is the live analysis, or is rebuilt from bars that had already closed before entry (no look-ahead).
  - Notes, setup tags, tags and screenshots are stored separately, and so are generated evaluations.
- **Statistics.**
  - P/L, win rate with a Wilson interval, profit factor, average win/loss, R, and expectancy with a bootstrap CI.
  - Max drawdown, streaks and costs.
  - Breakdowns by hour, weekday, session, setup and direction.
  - Equity, drawdown, daily and distribution charts.
- **Coach.**
  - **Patterns.** A pattern is only claimed when both groups have at least `COPILOT_COACH_MIN_SAMPLE` trades (default 20) and the 95 % bootstrap CI of the difference excludes 0. It is labelled "foreløpig" (preliminary) below 50 trades.
  - **After every trade.** Feedback, and a link to the AI suggestion that was active when the trade was opened. Following a suggestion is never treated as the cause of the result.
  - **Reviews.** Daily and weekly reviews with an optional AI narrative.
  - **Similar situations.** kNN on entry context.
  - **AI accuracy.** Each AI suggestion is evaluated against the M1 bars that followed it.
  - **Validation.** Candidate rules must pass walk-forward testing, and setups that have stopped working are flagged.
  - **Memory and versions.** A knowledge base with history, and a version registry (prompt rollback via `COPILOT_AI_PROMPT_VERSION`).
- **Not model training.** "Learning" here means persistent data plus statistics. The language model is never retrained, and nothing here can change risk limits or trade.

## Replay simulator (Phase 7)

The page opens from the panel's **Coach** tab via **Replay-trening**.

- **Data.** Real historical bid/ask ticks from MT5 (`copy_ticks_range`) are played back on a virtual clock: 1–60×, pause, jumps. They are fed through the same candle builder and analysis as live, so 1m candles form second by second.
- **Gaps and fallbacks.** Weekends are skipped. When the broker has no tick history that far back, M1 bars are used, and the movement inside each bar is labelled as synthetic.
- **No look-ahead.** Future ticks are held privately and released only as the clock passes them. Analysis, AI questions and fills only see released data (tested).
- **Simulated orders.**
  - BUY fills at the ask, SELL at the bid.
  - SL is a stop filled at market, TP is a limit, and commission is charged per lot.
  - The ticket shows lots → oz and risk in money.
  - Hotkeys are configurable: B, S, X, Space, →, Shift+→, + and −.
  - There is a session summary, plus MFE/MAE per trade.
- **TradingView's own Bar Replay** cannot be controlled or read by an extension, so this is a separate chart.

## Testing & performance (Phase 8)

`pytest` includes:
- a 6-hour strategy simulation that checks the simulated broker's accounting and fill rules
- a long-running test (150k ticks) that checks memory stays bounded
- performance budgets

`python scripts/benchmark.py` prints the timings. Typical numbers:

| Measure | Result |
|---|---|
| Analysis (4 timeframes × 500 bars) | ≈ 6 ms |
| Tick ingest | > 100k ticks/s |
| Replay of 1 market hour | ≈ 0.25 s |
| Coach patterns over 1,000 trades | ≈ 4 s (background thread, every 15 min) |

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
