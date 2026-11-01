"""Claude API list prices (USD per million tokens), used for cost tracking.

Prices change; the ledger records token counts too, so costs can be
recomputed. Unknown models are priced at the most expensive known rate so the
budget guard errs on the safe side.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float  # 5-minute cache write = 1.25x input


def _p(inp: float, out: float, cache_read: float | None = None) -> Price:
    return Price(inp, out, cache_read if cache_read is not None else inp * 0.1, inp * 1.25)


PRICES: dict[str, Price] = {
    "claude-fable-5-1": _p(10.0, 50.0, 0.25),
    "claude-opus-5-5": _p(4.0, 20.0, 0.20),
    "claude-opus-5": _p(5.0, 25.0),
    "claude-opus-4-8": _p(5.0, 25.0),
    "claude-sonnet-5-5": _p(2.0, 10.0, 0.20),
    "claude-sonnet-5": _p(2.0, 10.0),
    "claude-haiku-5-5": _p(0.10, 0.50),
    "claude-haiku-4-5": _p(1.0, 5.0),
}
FALLBACK = PRICES["claude-fable-5-1"]


def price_for(model: str) -> Price:
    for key, price in PRICES.items():
        if model == key or model.startswith(key + "-"):
            return price
    return FALLBACK


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    p = price_for(model)
    return (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * p.cache_write
    ) / 1_000_000


def worst_case_cost_usd(model: str, input_tokens: int, max_tokens: int) -> float:
    """Upper bound for one call: every allowed output token used."""
    return cost_usd(model, input_tokens, max_tokens)
