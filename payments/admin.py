from django.contrib import admin

from .models import Invoice, Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("occupancy", "period_month", "amount", "method",
                    "deposit_applied", "topup_amount", "status", "payment_date")
    list_filter = ("method", "status")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "generated_at", "email_sent", "emailed_to")
