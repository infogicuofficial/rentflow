"""Invoice PDF generation (ReportLab) + invoice e-mailing."""
import logging
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .models import Invoice

logger = logging.getLogger("rentflow")

NAVY = colors.HexColor("#16305c")
ORANGE = colors.HexColor("#e46f2e")
GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f3f4f6")


def next_invoice_number() -> str:
    today = date.today()
    prefix = f"INV-{today.year}-{today.month:02d}-"
    last = (
        Invoice.objects.filter(number__startswith=prefix)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def build_invoice_pdf(invoice, payments) -> bytes:
    occupancy = payments[0].occupancy
    occupant = occupancy.occupant
    flat = occupancy.flat
    company = settings.RENTFLOW_COMPANY

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Header band
    c.setFillColor(NAVY)
    c.rect(0, h - 34 * mm, w, 34 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(18 * mm, h - 16 * mm, "RentFlow")
    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, h - 22 * mm, company["name"])
    c.drawString(18 * mm, h - 26.5 * mm, company["address"])
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(w - 18 * mm, h - 16 * mm, "RENT INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 18 * mm, h - 22 * mm, invoice.number)
    c.drawRightString(w - 18 * mm, h - 27 * mm,
                      timezone.localtime(invoice.generated_at or timezone.now()).strftime("%d %B %Y"))

    y = h - 48 * mm

    # Billed to / property blocks
    c.setFillColor(GREY)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(18 * mm, y, "BILLED TO")
    c.drawString(105 * mm, y, "PROPERTY")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y - 6 * mm, occupant.full_name)
    c.drawString(105 * mm, y - 6 * mm, f"Flat {flat.number}, Level {flat.level.number}")
    c.setFont("Helvetica", 9.5)
    c.drawString(18 * mm, y - 11 * mm, f"ID: {occupant.occupant_id}   NID: {occupant.nid or '—'}")
    c.drawString(18 * mm, y - 15.5 * mm, occupant.email)
    c.drawString(18 * mm, y - 20 * mm, occupant.phone)
    c.drawString(105 * mm, y - 11 * mm, f"Building {flat.building.number} — {flat.building.name}")
    c.drawString(105 * mm, y - 15.5 * mm, flat.building.address)
    c.drawString(105 * mm, y - 20 * mm,
                 f"Tenancy start: {occupancy.start_date:%d %b %Y} (post-paid billing)")

    # Table header
    y -= 32 * mm
    c.setFillColor(LIGHT)
    c.rect(18 * mm, y - 3 * mm, w - 36 * mm, 9 * mm, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(20 * mm, y, "Rent period")
    c.drawString(70 * mm, y, "Payable window")
    c.drawString(118 * mm, y, "Method")
    c.drawRightString(w - 20 * mm, y, "Amount (BDT)")
    y -= 9 * mm

    c.setFont("Helvetica", 9.5)
    total = Decimal("0")
    for p in payments:
        c.setFillColor(colors.black)
        c.drawString(20 * mm, y, p.period_month.strftime("%B %Y"))
        c.setFillColor(GREY)
        window = f"{p.period_month.strftime('%b')} rent — paid {p.payment_date:%d %b %Y}"
        c.drawString(70 * mm, y, window)
        method = p.get_method_display()
        if p.method == "deposit" and p.topup_amount:
            method += f" + {p.get_topup_method_display()} top-up"
        c.drawString(118 * mm, y, method)
        c.setFillColor(colors.black)
        c.drawRightString(w - 20 * mm, y, f"{p.amount:,.2f}")
        total += p.amount
        y -= 6.5 * mm
        if p.method == "deposit":
            c.setFillColor(GREY)
            c.setFont("Helvetica-Oblique", 8.5)
            note = f"   Settled from security deposit: {p.deposit_applied:,.2f}"
            if p.topup_amount:
                note += (f"  ·  Rent-increase top-up paid separately: "
                         f"{p.topup_amount:,.2f}")
            c.drawString(20 * mm, y, note)
            c.setFont("Helvetica", 9.5)
            y -= 6.5 * mm

    # Total
    y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.line(18 * mm, y + 4 * mm, w - 18 * mm, y + 4 * mm)
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(NAVY)
    c.drawString(20 * mm, y - 3 * mm, "TOTAL RECEIVED")
    c.setFillColor(ORANGE)
    c.drawRightString(w - 20 * mm, y - 3 * mm, f"BDT {total:,.2f}")

    # Payment details box
    y -= 18 * mm
    p0 = payments[0]
    c.setFillColor(LIGHT)
    c.rect(18 * mm, y - 22 * mm, w - 36 * mm, 26 * mm, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(21 * mm, y - 2 * mm, "PAYMENT DETAILS")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    line_y = y - 8 * mm
    for k, v in (p0.details or {}).items():
        if not v:
            continue
        c.drawString(21 * mm, line_y, f"{k.replace('_', ' ').title()}: {v}")
        line_y -= 4.5 * mm
        if line_y < y - 20 * mm:
            break

    # Footer
    c.setFillColor(GREY)
    c.setFont("Helvetica", 8)
    c.drawString(18 * mm, 22 * mm,
                 "Billing is post-paid: rent for a month is payable between the 1st and "
                 f"{settings.RENT_DUE_DAY}th of the following month.")
    c.drawString(18 * mm, 17 * mm, f"Bank: {company['bank']}")
    c.drawString(18 * mm, 12 * mm,
                 f"{company['name']} · {company['phone']} · {company['email']}")
    c.setStrokeColor(ORANGE)
    c.setLineWidth(2)
    c.line(0, 6 * mm, w, 6 * mm)

    c.showPage()
    c.save()
    return buf.getvalue()


def create_invoice_for_payments(payments) -> Invoice:
    invoice = Invoice.objects.create(number=next_invoice_number())
    for p in payments:
        p.invoice = invoice
        p.save(update_fields=["invoice"])
    pdf_bytes = build_invoice_pdf(invoice, payments)
    invoice.pdf.save(f"{invoice.number}.pdf", ContentFile(pdf_bytes), save=True)
    logger.info("Generated invoice %s (%d payment(s))", invoice.number, len(payments))
    return invoice


def send_invoice_email(invoice, to_email: str) -> bool:
    payments = list(invoice.payments.select_related(
        "occupancy__occupant", "occupancy__flat__level__building"
    ))
    if not payments:
        return False
    occupant = payments[0].occupancy.occupant
    ctx = {
        "invoice": invoice,
        "payments": payments,
        "occupant": occupant,
        "company": settings.RENTFLOW_COMPANY,
        "total": sum(p.amount for p in payments),
    }
    html = render_to_string("payments/emails/invoice_email.html", ctx)
    msg = EmailMessage(
        subject=f"Rent invoice {invoice.number} — RentFlow",
        body=html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.content_subtype = "html"
    if invoice.pdf:
        invoice.pdf.open("rb")
        msg.attach(f"{invoice.number}.pdf", invoice.pdf.read(), "application/pdf")
        invoice.pdf.close()
    try:
        msg.send(fail_silently=False)
        invoice.email_sent = True
        invoice.emailed_to = to_email
        invoice.save(update_fields=["email_sent", "emailed_to"])
        logger.info("Invoice %s emailed to %s", invoice.number, to_email)
        return True
    except Exception:
        logger.exception("Failed to email invoice %s", invoice.number)
        return False
