import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from payments.models import Payment
from payments.utils import add_months, compute_due_summary, month_floor
from properties.models import Flat, Occupancy, Occupant


@login_required
def home(request):
    today = date.today()
    month_start = today.replace(day=1)

    occupancies = list(
        Occupancy.objects.filter(is_active=True).select_related(
            "occupant", "flat__level__building"
        )
    )
    total_flats = Flat.objects.count()
    occupied = len(occupancies)
    vacant = total_flats - occupied

    # Post-paid: this month we collect LAST month's rent.
    target_month = add_months(month_floor(today), -1)
    collection_target = Decimal("0")
    overdue_rows, due_rows, upcoming_rows = [], [], []
    outstanding_total = Decimal("0")

    for occ in occupancies:
        s = compute_due_summary(occ)
        if month_floor(occ.start_date) <= target_month:
            collection_target += occ.rent_for_month(target_month)
        for m in s.overdue:
            overdue_rows.append({"occ": occ, "m": m})
            outstanding_total += m.rent
        for m in s.due:
            due_rows.append({"occ": occ, "m": m})
            outstanding_total += m.rent
            if m.due_date <= today + timedelta(days=7):
                upcoming_rows.append({"occ": occ, "m": m})

    overdue_rows.sort(key=lambda r: -r["m"].days_overdue)

    received_month = Payment.objects.filter(
        payment_date__gte=month_start, status="paid"
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    # Charts -----------------------------------------------------------------
    paid_count = sum(
        1 for occ in occupancies if not compute_due_summary(occ).payable
    )
    due_count = len({r["occ"].pk for r in due_rows})
    overdue_count = len({r["occ"].pk for r in overdue_rows})

    bar_labels, bar_values = [], []
    for i in range(5, -1, -1):
        m = add_months(month_floor(today), -i)
        nxt = add_months(m, 1)
        total = Payment.objects.filter(
            payment_date__gte=m, payment_date__lt=nxt, status="paid"
        ).aggregate(t=Sum("amount"))["t"] or 0
        bar_labels.append(m.strftime("%b %Y"))
        bar_values.append(float(total))

    line_labels, line_values = [], []
    for i in range(11, -1, -1):
        m = add_months(month_floor(today), -i)
        total = Payment.objects.filter(
            period_month=m, status="paid"
        ).aggregate(t=Sum("amount"))["t"] or 0
        line_labels.append(m.strftime("%b"))
        line_values.append(float(total))

    recent_payments = Payment.objects.select_related(
        "occupancy__occupant", "occupancy__flat__level__building", "invoice"
    ).order_by("-created_at")[:5]

    new_occupants = Occupant.objects.order_by("-created_at")[:4]

    occupancy_rate = round(100 * occupied / total_flats) if total_flats else 0

    chart_data = json.dumps({
        "status": {"paid": paid_count, "due": due_count, "overdue": overdue_count},
        "bar": {"labels": bar_labels, "values": bar_values},
        "line": {"labels": line_labels, "values": line_values},
        "occupancy_rate": occupancy_rate,
    })

    return render(request, "dashboard/home.html", {
        "cards": {
            "occupants": Occupant.objects.count(),
            "occupied": occupied,
            "vacant": vacant,
            "collection_target": collection_target,
            "received_month": received_month,
            "outstanding": outstanding_total,
        },
        "target_month": target_month,
        "occupancy_rate": occupancy_rate,
        "overdue_rows": overdue_rows[:6],
        "upcoming_rows": upcoming_rows[:6],
        "recent_payments": recent_payments,
        "new_occupants": new_occupants,
        "chart_data": chart_data,
        "today": today,
    })
