"""Safety net: the first version must never be able to trade."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
FORBIDDEN = re.compile(
    r"\b(order_send|order_check|order_calc_margin|positions_close|Close|TRADE_ACTION_\w+)\s*\("
)


def test_no_trading_calls_in_backend():
    offenders = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"order_send|order_check|TRADE_ACTION_", text):
            line = text[: m.start()].count("\n") + 1
            src_line = text.splitlines()[line - 1]
            if not src_line.lstrip().startswith(("#", '"', "'", "``")) and "never calls" not in src_line:
                offenders.append(f"{path.name}:{line}: {src_line.strip()}")
        offenders += [f"{path.name}: {m.group(0)}" for m in FORBIDDEN.finditer(text)]
    assert offenders == []


def test_mt5_calls_are_read_only():
    """Every MetaTrader5 function the app calls must be on the read-only allow-list."""
    allowed = {
        "initialize", "shutdown", "last_error", "account_info", "terminal_info", "symbol_info", "symbols_get",
        "symbol_select", "symbol_info_tick", "copy_rates_from_pos", "copy_ticks_from", "positions_get",
        "orders_get", "history_deals_get", "history_orders_get", "copy_rates_from", "copy_rates_range",
        "copy_ticks_range",
    }
    text = (APP / "market" / "mt5_source.py").read_text(encoding="utf-8")
    called = set(re.findall(r"\bmt5\.([a-z_]+)\(", text)) | set(re.findall(r"self\._mt5\.([a-z_]+)\(", text))
    assert called and called <= allowed, called - allowed
