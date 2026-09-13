import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from properties.models import Building, Flat, Occupancy

from .models import Invoice, Payment
from .services import create_invoice_for_payments, send_invoice_email
from .utils import compute_due_summary, due_date_for, month_floor


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@login_required
def payment_main(request):
    today = date.today()
    month_start = today.replace(day=1)
    stats = {
        "this_month": Payment.objects.filter(
            payment_date__gte=month_start, status="paid"
        ).aggregate(t=Sum("amount"))["t"] or 0,
        "count_this_month": Payment.objects.filter(payment_date__gte=month_start).count(),
    }
    overdue_rows, due_rows = [], []
    for occ in Occupancy.objects.filter(is_active=True).select_related(
        "occupant", "flat__level__building"
    ):
        s = compute_due_summary(occ)
        for m in s.overdue:
            overdue_rows.append({"occ": occ, "m": m})
        for m in s.due:
            due_rows.append({"occ": occ, "m": m})
    overdue_rows.sort(key=lambda r: -r["m"].days_overdue)
    return render(request, "payments/payment_main.html", {
        "stats": stats,
        "overdue_rows": overdue_rows[:8],
        "due_rows": due_rows[:8],
        "overdue_count": len(overdue_rows),
        "due_count": len(due_rows),
    })


@login_required
def make_payment(request):
    buildings = Building.objects.all()
    preselect_flat = request.GET.get("flat", "")
    return render(request, "payments/make_payment.html", {
        "buildings": buildings,
        "preselect_flat": preselect_flat,
        "today": date.today(),
    })


@login_required
def manage_payments(request):
    qs = Payment.objects.select_related(
        "occupancy__occupant", "occupancy__flat__level__building", "invoice"
    )
    f_building = request.GET.get("building", "")
    f_status = request.GET.get("status", "")
    f_method = request.GET.get("method", "")
    f_from = request.GET.get("from", "")
    f_to = request.GET.get("to", "")
    q = request.GET.get("q", "").strip()

    if f_building:
        qs = qs.filter(occupancy__flat__level__building_id=f_building)
    if f_status:
        qs = qs.filter(status=f_status)
    if f_method:
        qs = qs.filter(Q(method=f_method) | Q(topup_method=f_method))
    if f_from:
        qs = qs.filter(payment_date__gte=f_from)
    if f_to:
        qs = qs.filter(payment_date__lte=f_to)
    if q:
        qs = qs.filter(
            Q(occupancy__occupant__full_name__icontains=q)
            | Q(occupancy__flat__number__icontains=q)
            | Q(occupancy__occupant__occupant_id__icontains=q)
            | Q(invoice__number__icontains=q)
        )

    agg = qs.filter(status="paid").aggregate(
        total=Sum("amount"), n=Count("id"), avg=Avg("amount")
    )
    total_expected = Payment.objects.count()
    collection_rate = (
        round(100 * Payment.objects.filter(status="paid").count() / total_expected)
        if total_expected else 0
    )
    return render(request, "payments/manage_payments.html", {
        "payments": qs[:200],
        "buildings": Building.objects.all(),
        "agg": agg,
        "collection_rate": collection_rate,
        "filters": {
            "building": f_building, "status": f_status, "method": f_method,
            "from": f_from, "to": f_to, "q": q,
        },
    })


@login_required
def payment_confirmation(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    payments = invoice.payments.select_related(
        "occupancy__occupant", "occupancy__flat__level__building"
    )
    return render(request, "payments/payment_confirmation.html", {
        "invoice": invoice,
        "payments": payments,
        "first": payments.first(),
    })


# ---------------------------------------------------------------------------
# JSON API for the payment portal
# ---------------------------------------------------------------------------

@login_required
def api_flats(request):
    building_id = request.GET.get("building")
    flats = Flat.objects.filter(level__building_id=building_id).select_related("level")
    data = [
        {
            "id": f.pk,
            "label": f"Flat {f.number} · Level {f.level.number}"
            + ("" if f.current_occupancy else " (vacant)"),
            "occupied": bool(f.current_occupancy),
        }
        for f in flats
    ]
    return JsonResponse({"flats": data})


@login_required
def api_flat_context(request):
    """Everything the portal needs once a flat is chosen: occupant + due months."""
    flat = get_object_or_404(Flat, pk=request.GET.get("flat"))
    occ = flat.current_occupancy
    if not occ:
        return JsonResponse({"occupied": False})

    summary = compute_due_summary(occ)
    months = [
        {
            "key": m.key,
            "label": m.label,
            "rent": str(m.rent),
            "base_rent": str(m.base_rent),
            "increase": str(m.increase),
            "due_date": m.due_date.strftime("%d %b %Y"),
            "status": m.status,
            "days_overdue": m.days_overdue,
        }
        for m in summary.months
    ]
    return JsonResponse({
        "occupied": True,
        "occupancy_id": occ.pk,
        "occupant": {
            "name": occ.occupant.full_name,
            "occupant_id": occ.occupant.occupant_id,
            "nid": occ.occupant.nid,
            "email": occ.occupant.email,
            "phone": occ.occupant.phone,
        },
        "current_rent": str(occ.current_rent),
        "start_date": occ.start_date.strftime("%d %b %Y"),
        "months": months,
        "deposit": {
            "total": str(occ.security_deposit),
            "balance": str(occ.deposit_balance),
            "notice_given": occ.notice_given,
            "can_use": occ.notice_given and occ.deposit_balance > 0,
        },
        "billing_note": (
            "Post-paid billing: rent for a month is collected the following "
            "month. The current month is never billed in advance."
        ),
    })


def _parse_months(occ, keys):
    """Validate submitted month keys against the actual payable months."""
    summary = compute_due_summary(occ)
    payable = {m.key: m for m in summary.payable}
    chosen = []
    for k in keys:
        if k not in payable:
            raise ValueError(
                f"{k} is not currently payable. Post-paid billing only allows "
                "finished, unpaid months."
            )
        chosen.append(payable[k])
    if not chosen:
        raise ValueError("Select at least one due month.")
    chosen.sort(key=lambda m: m.month)
    # enforce oldest-first payment (can't skip an older due month)
    all_payable = sorted(payable.values(), key=lambda m: m.month)
    for i, m in enumerate(chosen):
        if all_payable[i].key != m.key:
            raise ValueError("Months must be paid oldest-first — you can't skip "
                             f"{all_payable[i].label}.")
    return chosen


@login_required
@require_POST
def api_verify(request):
    """Auto-check: validates the whole submission before invoice generation."""
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "errors": ["Invalid request."]})

    errors, warnings = [], []
    occ = Occupancy.objects.filter(pk=payload.get("occupancy_id"), is_active=True).first()
    if not occ:
        return JsonResponse({"ok": False, "errors": ["No active occupancy for this flat."]})

    try:
        months = _parse_months(occ, payload.get("months", []))
    except ValueError as e:
        return JsonResponse({"ok": False, "errors": [str(e)]})

    method = payload.get("method")
    details = payload.get("details", {}) or {}
    required = {
        "cash": ["received_by", "received_date"],
        "bank": ["sender_bank", "receiving_bank", "reference_no", "transfer_date"],
        "bkash": ["bkash_txn_id", "sender_bkash_no", "txn_datetime"],
        "deposit": [],
    }
    if method not in required:
        errors.append("Choose a payment method.")
    else:
        for f in required[method]:
            if not str(details.get(f, "")).strip():
                errors.append(f"Missing field: {f.replace('_', ' ')}.")

    total_rent = sum(m.rent for m in months)
    topup_total = Decimal("0")

    if method == "deposit":
        if not occ.notice_given:
            errors.append(
                "Security deposit can only be used after the occupant has given "
                "notice to leave. Mark 'notice given' on the occupancy first."
            )
        base_total = sum(min(m.rent, m.base_rent) for m in months)
        topup_total = sum(max(m.increase, Decimal("0")) for m in months)
        if occ.deposit_balance < base_total:
            errors.append(
                f"Deposit balance ({occ.deposit_balance}) does not cover the "
                f"base rent portion ({base_total}) for the selected months."
            )
        if topup_total > 0:
            tm = payload.get("topup_method")
            if tm not in ("cash", "bank", "bkash"):
                errors.append(
                    f"Rent has increased since move-in. The increase of {topup_total} "
                    "must be paid separately — choose a top-up method (cash/bank/bkash)."
                )
            else:
                for f in required[tm]:
                    if not str((payload.get("topup_details") or {}).get(f, "")).strip():
                        errors.append(f"Top-up: missing {f.replace('_', ' ')}.")
            warnings.append(
                f"Deposit covers the original rent only. The tenant still pays the "
                f"increased portion of {topup_total} on top."
            )

    try:
        amount = Decimal(str(payload.get("amount", "0")))
    except InvalidOperation:
        amount = Decimal("0")
    if method != "deposit" and amount != total_rent:
        errors.append(
            f"Amount entered ({amount}) does not match the rent for the selected "
            f"month(s) ({total_rent})."
        )

    return JsonResponse({
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "total_rent": str(total_rent),
        "topup_total": str(topup_total),
        "months": [m.label for m in months],
        "occupant_confirmed": True,
    })


@login_required
@require_POST
@transaction.atomic
def api_generate_invoice(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "errors": ["Invalid request."]}, status=400)

    occ = get_object_or_404(
        Occupancy.objects.select_for_update(), pk=payload.get("occupancy_id"), is_active=True
    )
    try:
        months = _parse_months(occ, payload.get("months", []))
    except ValueError as e:
        return JsonResponse({"ok": False, "errors": [str(e)]}, status=400)

    method = payload.get("method")
    details = payload.get("details", {}) or {}
    topup_method = payload.get("topup_method") or ""
    topup_details = payload.get("topup_details") or {}
    pay_date_raw = payload.get("payment_date") or date.today().isoformat()
    try:
        pay_date = datetime.strptime(pay_date_raw, "%Y-%m-%d").date()
    except ValueError:
        pay_date = date.today()

    payments = []
    for m in months:
        deposit_applied = Decimal("0")
        topup = Decimal("0")
        det = dict(details)
        if method == "deposit":
            if not occ.notice_given:
                return JsonResponse(
                    {"ok": False,
                     "errors": ["Deposit payments require notice to be given."]},
                    status=400)
            base_part = min(m.rent, m.base_rent)
            topup = max(m.increase, Decimal("0"))
            if occ.deposit_balance < base_part:
                return JsonResponse(
                    {"ok": False, "errors": ["Insufficient deposit balance."]}, status=400)
            if topup > 0 and topup_method not in ("cash", "bank", "bkash"):
                return JsonResponse(
                    {"ok": False,
                     "errors": ["Rent increase top-up needs its own payment method."]},
                    status=400)
            occ.deposit_balance -= base_part
            deposit_applied = base_part
            det = {"deposit_applied": str(base_part),
                   "deposit_balance_after": str(occ.deposit_balance)}
            if topup > 0:
                det["topup_method"] = topup_method
                det.update({f"topup_{k}": v for k, v in topup_details.items() if v})

        payments.append(Payment(
            occupancy=occ,
            period_month=m.month,
            amount=m.rent,
            deposit_applied=deposit_applied,
            topup_amount=topup,
            payment_date=pay_date,
            due_date=due_date_for(m.month),
            method=method,
            topup_method=topup_method if (method == "deposit" and topup > 0) else "",
            status="paid",
            details=det,
        ))

    for p in payments:
        p.save()
    if method == "deposit":
        occ.save(update_fields=["deposit_balance"])

    invoice = create_invoice_for_payments(payments)

    email_sent = False
    email_to = (payload.get("email") or "").strip()
    if payload.get("send_email") and email_to:
        email_sent = send_invoice_email(invoice, email_to)

    return JsonResponse({
        "ok": True,
        "invoice": {
            "id": invoice.pk,
            "number": invoice.number,
            "pdf_url": invoice.pdf.url if invoice.pdf else "",
            "email_sent": email_sent,
        },
        "redirect": f"/payments/confirmation/{invoice.pk}/",
    })


@login_required
@require_POST
def resend_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    to = request.POST.get("email") or invoice.emailed_to
    if not to:
        p = invoice.payments.first()
        to = p.occupancy.occupant.email if p else ""
    ok = send_invoice_email(invoice, to) if to else False
    if ok:
        messages.success(request, f"Invoice {invoice.number} re-sent to {to}.")
    else:
        messages.error(request, "Could not send the invoice email.")
    return redirect(request.META.get("HTTP_REFERER", "/payments/manage/"))


@login_required
@require_POST
def delete_payment(request, payment_id):
    p = get_object_or_404(Payment, pk=payment_id)
    label = f"{p.occupancy.occupant} — {p.period_label}"
    if p.method == "deposit" and p.deposit_applied:
        occ = p.occupancy
        occ.deposit_balance += p.deposit_applied
        occ.save(update_fields=["deposit_balance"])
    p.delete()
    messages.success(request, f"Payment removed: {label}. Deposit restored if applicable.")
    return redirect("payments:manage")
