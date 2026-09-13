import json

from django.db import models

from properties.models import Occupancy


class Invoice(models.Model):
    """One invoice per transaction; may cover several rent months."""
    number = models.CharField(max_length=30, unique=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    pdf = models.FileField(upload_to="invoices/", blank=True, null=True)
    email_sent = models.BooleanField(default=False)
    emailed_to = models.EmailField(blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return self.number

    @property
    def total_amount(self):
        return sum(p.amount for p in self.payments.all())


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank Transfer"
        BKASH = "bkash", "Bkash"
        DEPOSIT = "deposit", "Security Deposit"

    class Status(models.TextChoices):
        PAID = "paid", "Paid"
        PENDING = "pending", "Pending"
        OVERDUE = "overdue", "Overdue"

    occupancy = models.ForeignKey(Occupancy, related_name="payments", on_delete=models.CASCADE)
    invoice = models.ForeignKey(
        Invoice, related_name="payments", on_delete=models.SET_NULL, blank=True, null=True
    )
    period_month = models.DateField(help_text="First day of the rent month this payment covers.")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_applied = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Portion of this month's rent settled from the security deposit.",
    )
    topup_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Rent-increase portion that had to be paid in cash/bank/bkash "
                  "on top of the deposit.",
    )
    payment_date = models.DateField()
    due_date = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices)
    topup_method = models.CharField(
        max_length=10, choices=Method.choices, blank=True,
        help_text="Method used for the rent-increase top-up when paying from deposit.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PAID)
    details = models.JSONField(default=dict, blank=True)
    screenshot = models.ImageField(upload_to="payments/screenshots/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]
        unique_together = [("occupancy", "period_month")]

    def __str__(self):
        return f"{self.occupancy.occupant} — {self.period_month:%B %Y} — {self.amount}"

    @property
    def period_label(self):
        return self.period_month.strftime("%B %Y")

    @property
    def details_json(self):
        """JSON-safe string for embedding in single-quoted HTML attributes."""
        return json.dumps(self.details or {}).replace("'", "\\u0027")
