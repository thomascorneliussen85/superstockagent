# Implementation plan

| Phase | Content | Status |
|---|---|---|
| 1. Foundation | MV3 extension, TradingView panel (drag, resize, collapse, persistence), FastAPI backend, auth and origin checks, WebSocket hub, candle builder, synthetic feed, tests and CI | ✅ Done |
| 2. Live market data | `Mt5MarketSource` (dedicated thread, `symbol_info_tick` polling, broker→UTC offset), real contract spec, history backfill (`copy_rates_from_pos`), indicators (RSI, Supertrend, EMA 9/20/50/200, ATR) with tests against reference values, market structure, S/R, multi-timeframe state | Next |
| 3. AI | Event detector (new closed candle, structure break, level touch, spread spike) → compact JSON state → LLM (Claude/OpenAI, configurable) → Norwegian commentary. Rate-limited, with cost tracking per call. Signal objects with entry, invalidation, target, R/R and supporting/conflicting evidence. Voice alerts (Web Speech API, nb-NO) with cooldown and deduplication. | |
| 4. Trade monitoring | Read-only `positions_get`, `account_info`. Risk % per position and in total, distance to SL, correlated exposure, daily risk limit, spread alerts. | |
| 5. Journal | `history_deals_get` → round-trip trades (idempotent on deal ticket), SQLite (SQLAlchemy, ready for Postgres), raw data kept separate from AI evaluations, analytics dashboard (equity curve, drawdown, by hour/weekday/session/setup). | |
| 6. Coach | Market context captured at entry, statistical tests with minimum sample sizes and confidence intervals (bootstrap / Wilson), daily and weekly reviews. | |
| 7. Replay | Tick replay with a virtual clock, look-ahead protection enforced on the backend, Lightweight Charts, simulated orders and hotkeys, realistic spread and commission. | |
| 8. Test & optimisation | Load testing, long-running stability, walk-forward evaluation of strategies, signal calibration (reliability diagrams, Brier score). | |

## Learning system (across Phases 5–8)

- **Memory is data, not model training.** The language model does not retrain itself. "Learning" means a growing, versioned knowledge base: trades, context, recommendations and outcomes, plus statistics computed from it. Any fine-tuning would be a separate, explicitly evaluated process.
- Recommendations are logged with `followed / ignored / rejected` and evaluated without assuming that following them caused the result.
- Strategies are only promoted after walk-forward / out-of-sample validation. Drift detection flags strategies that stop working.
- Rules, prompts and models are versioned with rollback. The learning system can **never** change risk limits or trade.
