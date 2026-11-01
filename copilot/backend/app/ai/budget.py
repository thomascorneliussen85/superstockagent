"""Hard monthly spending limit with even pacing across the month.

* A call is only allowed if its *worst-case* cost fits in what is left.
* Daily allowance = remaining monthly budget / remaining weekdays (incl.
  today), so an early busy day cannot use up the whole month.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime

from .ledger import Ledger, day_start_ms, month_bounds_ms


def weekdays_left(now: datetime) -> int:
    days = calendar.monthrange(now.year, now.month)[1]
    count = 0
    for d in range(now.day, days + 1):
        if (now.replace(day=d)).weekday() < 5:
            count += 1
    return max(1, count)


@dataclass
class BudgetStatus:
    monthly_cap_usd: float
    month_spent_usd: float
    day_spent_usd: float
    day_allowance_usd: float
    calls_today: int

    @property
    def month_left_usd(self) -> float:
        return max(0.0, self.monthly_cap_usd - self.month_spent_usd)

    def to_wire(self, usd_nok: float) -> dict:
        return {
            "monthCapNok": round(self.monthly_cap_usd * usd_nok, 2),
            "monthSpentNok": round(self.month_spent_usd * usd_nok, 2),
            "daySpentNok": round(self.day_spent_usd * usd_nok, 2),
            "dayAllowanceNok": round(self.day_allowance_usd * usd_nok, 2),
            "callsToday": self.calls_today,
        }


class BudgetGuard:
    def __init__(self, ledger: Ledger, monthly_budget_nok: float, usd_nok: float) -> None:
        self.ledger = ledger
        self.usd_nok = usd_nok
        self.monthly_cap_usd = max(0.0, monthly_budget_nok / usd_nok)

    def status(self, now: datetime) -> BudgetStatus:
        m0, _ = month_bounds_ms(now)
        d0 = day_start_ms(now)
        month_spent = self.ledger.spent_usd(m0)
        day_spent = self.ledger.spent_usd(d0)
        before_today = month_spent - day_spent
        left_at_day_start = max(0.0, self.monthly_cap_usd - before_today)
        allowance = left_at_day_start / weekdays_left(now)
        return BudgetStatus(
            self.monthly_cap_usd, month_spent, day_spent, allowance, self.ledger.calls_since(d0)
        )

    def check(self, now: datetime, worst_case_usd: float) -> str | None:
        """None if allowed, otherwise a Norwegian reason."""
        st = self.status(now)
        if st.month_spent_usd + worst_case_usd > st.monthly_cap_usd:
            return "Månedsbudsjettet for AI er brukt opp."
        if st.day_spent_usd + worst_case_usd > st.day_allowance_usd:
            return "Dagens andel av AI-budsjettet er brukt opp (fordeles jevnt over måneden)."
        return None
