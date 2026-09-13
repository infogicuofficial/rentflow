"""
Post-paid rent month logic.

RentFlow bills rent IN ARREARS (post-paid):

  * A tenancy starting 1 August owes rent FOR August, but that rent only
    becomes payable in September (1–20 Sept by default).
  * In October the tenant pays September's rent, and so on.
  * The current (in-progress) month is never billable — it isn't finished yet.

Definitions used below (all months are normalised to the 1st):

  billable months   = every full month from the tenancy start month up to and
                      including LAST month (today's month − 1).
  payable month M   = billable and unpaid.
  overdue month M   = payable and today is past the due date
                      (RENT_DUE_DAY of month M+1).
  due-soon month M  = payable, we're inside M+1 but not yet past the due day.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings


def month_floor(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    return month_floor(d) + relativedelta(months=n)


def due_date_for(period_month: date) -> date:
    """Rent for `period_month` is due on RENT_DUE_DAY of the following month."""
    nxt = add_months(period_month, 1)
    return nxt.replace(day=min(settings.RENT_DUE_DAY, 28))


def payable_from(period_month: date) -> date:
    """Rent for `period_month` can be paid from the 1st of the next month."""
    return add_months(period_month, 1)


@dataclass
class DueMonth:
    month: date
    rent: Decimal
    due_date: date
    payable_from: date
    status: str            # 'overdue' | 'due' | 'upcoming'
    days_overdue: int = 0
    base_rent: Decimal = Decimal("0")
    increase: Decimal = Decimal("0")   # rent - initial contract rent

    @property
    def label(self):
        return self.month.strftime("%B %Y")

    @property
    def key(self):
        return self.month.strftime("%Y-%m")


@dataclass
class DueSummary:
    occupancy_id: int
    months: list = field(default_factory=list)

    @property
    def overdue(self):
        return [m for m in self.months if m.status == "overdue"]

    @property
    def due(self):
        return [m for m in self.months if m.status == "due"]

    @property
    def payable(self):
        return [m for m in self.months if m.status in ("overdue", "due")]

    @property
    def total_payable(self):
        return sum((m.rent for m in self.payable), Decimal("0"))

    @property
    def next_upcoming(self):
        ups = [m for m in self.months if m.status == "upcoming"]
        return ups[0] if ups else None


def billable_months(occupancy, today: date | None = None) -> list[date]:
    """Every full month owed so far: start month .. last month (post-paid)."""
    today = today or date.today()
    first = month_floor(occupancy.start_date)
    last_billable = add_months(month_floor(today), -1)
    if occupancy.end_date:
        last_billable = min(last_billable, month_floor(occupancy.end_date))
    months, m = [], first
    while m <= last_billable:
        months.append(m)
        m = add_months(m, 1)
    return months


def compute_due_summary(occupancy, today: date | None = None) -> DueSummary:
    """
    Full post-paid picture for one tenancy: which finished months are unpaid,
    which of those are overdue, and what next month's (upcoming) rent will be.
    """
    today = today or date.today()
    paid = set(
        occupancy.payments.filter(status="paid").values_list("period_month", flat=True)
    )
    summary = DueSummary(occupancy_id=occupancy.pk)

    for m in billable_months(occupancy, today):
        if m in paid:
            continue
        rent = occupancy.rent_for_month(m)
        due = due_date_for(m)
        if today > due:
            status, days = "overdue", (today - due).days
        else:
            status, days = "due", 0
        summary.months.append(DueMonth(
            month=m, rent=rent, due_date=due, payable_from=payable_from(m),
            status=status, days_overdue=days,
            base_rent=occupancy.rent_amount,
            increase=rent - occupancy.rent_amount,
        ))

    # The current month (in progress) — payable next month, shown as upcoming.
    cur = month_floor(today)
    if cur >= month_floor(occupancy.start_date) and cur not in paid and (
        not occupancy.end_date or cur <= month_floor(occupancy.end_date)
    ):
        rent = occupancy.rent_for_month(cur)
        summary.months.append(DueMonth(
            month=cur, rent=rent, due_date=due_date_for(cur),
            payable_from=payable_from(cur), status="upcoming",
            base_rent=occupancy.rent_amount,
            increase=rent - occupancy.rent_amount,
        ))
    return summary


def occupancy_payment_state(occupancy, today: date | None = None) -> str:
    """'paid' | 'due' | 'overdue' — colour coding for overview cards."""
    s = compute_due_summary(occupancy, today)
    if s.overdue:
        return "overdue"
    if s.due:
        return "due"
    return "paid"
