# Research findings and constraints

These findings drive the design. Items marked **(verify)** depend on your TradingView plan or broker. Check them in your own account before we rely on them.

## 1. TradingView integration

- TradingView provides **no public API** for browser extensions to read chart state, indicators or drawings, to place orders, or to control Bar Replay. Its official developer products are the *Charting Library* and *Trading Platform* (licensed, for embedding charts on your own website), *Lightweight Charts* (open source, Apache-2.0), broker integration (for brokers), and webhooks from alerts.
- Reading the chart by scraping TradingView's DOM or canvas would break on every UI update, and it may violate the Terms of Service. **Decision:** the extension only *adds* a panel. All market data comes from MT5 through our backend.
- **Pine Script alerts with webhooks** are a supported way to send signals from TradingView. They need a public HTTPS endpoint and a paid plan **(verify)**. They are optional and not needed when MT5 supplies the data.

## 2. Hotkey order entry

- TradingView's own order hotkeys and one-click trading only work with **brokers connected to TradingView's Trading Panel**. MT5 itself is not a TradingView broker. Some MT5 brokers also offer a separate TradingView integration **(verify for your broker)**.
- Extensions cannot use TradingView's order ticket through a supported API. Automating its UI to submit real orders is fragile and unsafe. **We will not do that.**
- **Planned design (after the read-only phases, and only with your explicit opt-in):**
  1. A hotkey is captured by the extension and opens **our own** order ticket in the panel. It does not use TradingView's.
  2. The backend calculates entry from the *current ask (BUY) or bid (SELL)*, SL = entry ∓ 2.00 USD, TP = entry ± 4.00 USD (configurable), plus spread, monetary risk and the risk as a percentage of equity.
  3. The user confirms explicitly (click or a second key).
  4. The backend runs MT5 `order_check` and then `order_send`, with an idempotency key so the same order cannot be sent twice. Live trading needs a separate setting and shows a red `LIVE` badge.
- In replay (Phase 7), the same hotkeys place **simulated** orders with SL/TP attached. No confirmation is needed because no money is involved.

## 3. Units, ounces and lots (never assume these are the same)

| Term | Meaning for XAUUSD |
|---|---|
| **Ounce (troy oz)** | The physical quantity. The price is USD per ounce. |
| **Lot** (MT5 `volume`) | The broker's contract unit. **1 lot is often 100 oz, but some brokers use 10 oz or 1 oz.** The authoritative value is MT5 `symbol_info("XAUUSD").trade_contract_size`. |
| **Units** (TradingView paper trading / some brokers) | Usually 1 unit = 1 oz. This depends on the broker **(verify)**. |

Worked example with a 2.00 USD stop distance, assuming contract size = 100 oz/lot:

| Position | Ounces | MT5 volume | Loss at stop (excluding spread and commission) |
|---|---|---|---|
| 10 units (= 10 oz) | 10 | 0.10 lot | **$20** |
| 10 ounces | 10 | 0.10 lot | **$20** |
| 10 lots | 1,000 | 10.00 lots | **$2,000** |

That is a 100× difference. The backend will therefore:
- store sizes internally in **ounces** and in **lots**, always together with the contract size used for the conversion;
- calculate risk as `|entry − SL| × contract_size × lots`, using MT5's `trade_tick_value`/`trade_tick_size` and converting to the account currency (for example NOK or USD);
- round to the broker's `volume_step` and reject anything outside `volume_min`/`volume_max`.

The panel shows the contract size from MT5 (`trade_contract_size`) and what a 1 USD move is worth per 0.10 lot. In demo mode it is marked as a demo value.

## 4. Bar Replay vs our own replay

- TradingView Bar Replay replays bars on the chart. Which intrabar or second-level resolutions are available depends on your plan **(verify)**. There is **no API** to start, stop or read the replay, or to feed it our own ticks, and an extension cannot reliably tell which bar is "now" in the replay.
- So **neither the AI nor our hotkeys can be synchronised safely with TradingView's replay**, and look-ahead bias could not be ruled out.
- **Decision (Phase 7):** build our own replay chart in the extension (or a separate page) with **TradingView Lightweight Charts**. Ticks come from MT5 `copy_ticks_range` for real historical bid/ask. They are fed through the *same* `CandleBuilder` with a virtual clock (1×, 2×, 5×, 10×, 60×, pause, jump). The AI and indicators can only see the data that the virtual clock has released. This is enforced on the backend, not in the UI.
- How much tick history is available depends on the broker. It is often months, not years. Missing periods can fall back to M1 OHLC with a clearly labelled synthetic intrabar path.

## 5. MT5 Python integration

- The `MetaTrader5` package only runs on **Windows**, in the same session as a running terminal that is logged in. That is why the backend runs locally on your PC.
- The calls are blocking and the package is not thread-safe. The connector runs them in one dedicated worker thread and polls `copy_ticks_from` every 100 ms (MT5 has no push API). Each tick is stamped with MT5's `time_msc`, the server time, and converted to UTC using a measured broker UTC offset.
- Read-only means the code base contains no `order_send` until trading is explicitly enabled in a later phase.
