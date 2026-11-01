# AI Trading Copilot (XAUUSD)

A Chrome extension that adds an AI panel to TradingView, plus a local Python backend that reads data from MetaTrader 5. It is built for manual scalping of gold (XAUUSD) on the 1-minute chart.

> **Status: Phase 1 (Foundation) is done.** The extension, panel, local backend, security model and live streaming all work. The data is a **synthetic demo feed** for now. Phase 2 connects it to MT5.
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

```powershell
cd copilot\backend
py -3.12 -m venv .venv
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
cd copilot/backend && pytest            # 23 tests: candles, auth/origin, WebSocket flow, hub freshness/reconnect
cd copilot/extension && npm test        # 20 tests: reducer, geometry, WebSocket client (auth/backoff/liveness)
cd copilot/extension && npm run build   # type-check + production build
```

CI runs all of these in `.github/workflows/copilot-ci.yml`.

## Configuration (`copilot/backend/.env`, see `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `COPILOT_MODE` | `demo` | `demo` = synthetic data. `mt5_demo` and `mt5_live` arrive in Phase 2. |
| `COPILOT_PORT` | `8765` | Local port |
| `COPILOT_ALLOWED_EXTENSION_IDS` | `[]` | Pins which extension may connect |
| `COPILOT_DEMO_SEED` | random | Makes the demo feed reproducible |
| `COPILOT_STALE_AFTER_SECONDS` | `5` | No tick for this long marks the feed as stale |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/RESEARCH.md](docs/RESEARCH.md) (TradingView integration limits, and units vs ounces vs lots) and [docs/ROADMAP.md](docs/ROADMAP.md).
