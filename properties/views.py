from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from payments.utils import compute_due_summary, occupancy_payment_state

from .forms import DocumentForm, OccupantForm, RentRevisionForm
from .models import Building, Document, Flat, Occupancy, Occupant, RentRevision


@login_required
def rental_overview(request):
    flats = Flat.objects.select_related("level__building").prefetch_related(
        "occupancies__occupant"
    )
    f_building = request.GET.get("building", "")
    f_level = request.GET.get("level", "")
    f_status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()

    if f_building:
        flats = flats.filter(level__building_id=f_building)
    if f_level:
        flats = flats.filter(level__number=f_level)
    if q:
        flats = flats.filter(
            Q(number__icontains=q)
            | Q(level__building__number__icontains=q)
            | Q(occupancies__occupant__full_name__icontains=q, occupancies__is_active=True)
        ).distinct()

    rows = []
    for flat in flats:
        occ = flat.current_occupancy
        state = occupancy_payment_state(occ) if occ else "vacant"
        if f_status == "occupied" and not occ:
            continue
        if f_status == "vacant" and occ:
            continue
        rows.append({"flat": flat, "occ": occ, "state": state})

    return render(request, "properties/rental_overview.html", {
        "rows": rows,
        "buildings": Building.objects.all(),
        "levels": sorted({l for l in range(1, 12)}),
        "filters": {"building": f_building, "level": f_level, "status": f_status, "q": q},
        "counts": {
            "total": len(rows),
            "occupied": sum(1 for r in rows if r["occ"]),
            "vacant": sum(1 for r in rows if not r["occ"]),
            "overdue": sum(1 for r in rows if r["state"] == "overdue"),
        },
        "view_mode": request.GET.get("view", "grid"),
    })


@login_required
def flat_detail(request, pk):
    flat = get_object_or_404(Flat.objects.select_related("level__building"), pk=pk)
    occ = flat.current_occupancy
    summary = compute_due_summary(occ) if occ else None
    payments = (
        occ.payments.select_related("invoice").order_by("-period_month")[:12] if occ else []
    )
    history = flat.occupancies.select_related("occupant").order_by("-start_date")
    template = {
        "shop": "properties/shop_detail.html",
        "cottage": "properties/cottage_flats.html",
    }.get(flat.unit_type, "properties/flat_detail.html")
    return render(request, template, {
        "flat": flat,
        "occ": occ,
        "summary": summary,
        "payments": payments,
        "history": history,
        "revision_form": RentRevisionForm(),
        "today": date.today(),
    })


@login_required
def client_info(request, pk):
    occupant = get_object_or_404(Occupant, pk=pk)
    occ = occupant.current_occupancy
    summary = compute_due_summary(occ) if occ else None
    payments = occupant.occupancies.exists() and [
        p for o in occupant.occupancies.all()
        for p in o.payments.select_related("invoice").order_by("-period_month")
    ] or []
    if request.method == "POST" and "upload_document" in request.POST:
        doc_form = DocumentForm(request.POST, request.FILES)
        if doc_form.is_valid():
            doc = doc_form.save(commit=False)
            doc.occupant = occupant
            doc.save()
            messages.success(request, f"Document “{doc.title}” uploaded.")
            return redirect("properties:client_info", pk=pk)
    else:
        doc_form = DocumentForm()
    return render(request, "properties/client_info.html", {
        "occupant": occupant,
        "occ": occ,
        "summary": summary,
        "payments": payments,
        "documents": occupant.documents.all(),
        "doc_form": doc_form,
    })


@login_required
def occupant_list(request):
    q = request.GET.get("q", "").strip()
    occupants = Occupant.objects.all()
    if q:
        occupants = occupants.filter(
            Q(full_name__icontains=q) | Q(occupant_id__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
        )
    return render(request, "properties/occupant_list.html", {
        "occupants": occupants, "q": q,
    })


@login_required
def occupant_edit(request, pk=None):
    occupant = get_object_or_404(Occupant, pk=pk) if pk else None
    if request.method == "POST":
        form = OccupantForm(request.POST, request.FILES, instance=occupant)
        if form.is_valid():
            occupant = form.save()
            messages.success(request, f"Occupant “{occupant.full_name}” saved.")
            return redirect("properties:client_info", pk=occupant.pk)
    else:
        form = OccupantForm(instance=occupant)
    return render(request, "properties/occupant_form.html", {
        "form": form, "occupant": occupant,
    })


@login_required
@require_POST
def add_rent_revision(request, occupancy_id):
    occ = get_object_or_404(Occupancy, pk=occupancy_id)
    form = RentRevisionForm(request.POST)
    if form.is_valid():
        rev = form.save(commit=False)
        rev.occupancy = occ
        rev.save()
        messages.success(
            request,
            f"Rent revised to {rev.new_rent} from {rev.effective_from:%B %Y}. "
            "Deposit payments will require the increase to be topped up separately.",
        )
    else:
        messages.error(request, "Could not save the rent revision — check the fields.")
    return redirect(request.META.get("HTTP_REFERER", "/properties/"))


@login_required
@require_POST
def toggle_notice(request, occupancy_id):
    occ = get_object_or_404(Occupancy, pk=occupancy_id)
    occ.notice_given = not occ.notice_given
    occ.save(update_fields=["notice_given"])
    if occ.notice_given:
        messages.success(
            request,
            f"Notice recorded for {occ.occupant}. The security deposit "
            f"({occ.deposit_balance} remaining) can now settle final months' rent — "
            "any rent increase above the original contract rent must still be paid separately.",
        )
    else:
        messages.info(request, "Notice cancelled. Deposit is locked again.")
    return redirect(request.META.get("HTTP_REFERER", "/properties/"))
