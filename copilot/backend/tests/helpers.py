from app.market.models import Candle, Timeframe

T0 = 1_700_000_040_000


def bars(closes, spread=0.5, tf=Timeframe.M1, start=T0, last_open=False, ticks=100):
    """Candles with open = previous close, high/low = max/min(o, c) +/- spread."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(
            Candle("XAUUSD", tf, start + i * tf.ms, o, max(o, c) + spread, min(o, c) - spread, c,
                   tick_count=ticks, closed=not (last_open and i == len(closes) - 1))
        )
        prev = c
    return out


def candle(o, h, l, c, i=0, closed=True, tf=Timeframe.M1):  # noqa: E741
    return Candle("XAUUSD", tf, T0 + i * tf.ms, o, h, l, c, closed=closed)
