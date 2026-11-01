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
