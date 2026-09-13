from datetime import date

from django.db import models
from django.urls import reverse


class Building(models.Model):
    number = models.CharField("Building No", max_length=20, unique=True)
    name = models.CharField("Building Name", max_length=120)
    address = models.CharField(max_length=255)
    photo = models.ImageField(upload_to="buildings/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Building {self.number} — {self.name}"


class Level(models.Model):
    building = models.ForeignKey(Building, related_name="levels", on_delete=models.CASCADE)
    number = models.PositiveIntegerField("Level No")
    name = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["building", "number"]
        unique_together = [("building", "number")]

    def __str__(self):
        return f"{self.building.number} / Level {self.number}"


class Flat(models.Model):
    class UnitType(models.TextChoices):
        FLAT = "flat", "Flat"
        SHOP = "shop", "Shop"
        COTTAGE = "cottage", "Cottage"

    level = models.ForeignKey(Level, related_name="flats", on_delete=models.CASCADE)
    number = models.CharField("Flat No", max_length=20)
    unit_type = models.CharField(max_length=10, choices=UnitType.choices, default=UnitType.FLAT)
    size_sqft = models.PositiveIntegerField("Size (sqft)", default=0)
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=0)
    amenities = models.TextField(blank=True, help_text="Comma separated amenities")
    base_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["level__building__number", "level__number", "number"]
        unique_together = [("level", "number")]

    def __str__(self):
        return f"{self.level.building.number}-{self.number}"

    @property
    def building(self):
        return self.level.building

    def get_absolute_url(self):
        return reverse("properties:flat_detail", args=[self.pk])

    @property
    def current_occupancy(self):
        return self.occupancies.filter(is_active=True).select_related("occupant").first()

    @property
    def amenity_list(self):
        return [a.strip() for a in self.amenities.split(",") if a.strip()]


class Occupant(models.Model):
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    nid = models.CharField("NID No", max_length=40, blank=True)
    occupant_id = models.CharField(
        "Occupant ID", max_length=20, unique=True,
        help_text="Internal reference, e.g. OCC-0001",
    )
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    photo = models.ImageField(upload_to="profiles/", blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse("properties:client_info", args=[self.pk])

    @property
    def current_occupancy(self):
        return self.occupancies.filter(is_active=True).select_related(
            "flat__level__building"
        ).first()


class Occupancy(models.Model):
    """
    A tenancy contract. Rent is POST-PAID:
    the rent for month M becomes payable from the 1st of month M+1 and is
    due by the RENT_DUE_DAY (default 20th) of month M+1.
    """
    flat = models.ForeignKey(Flat, related_name="occupancies", on_delete=models.CASCADE)
    occupant = models.ForeignKey(Occupant, related_name="occupancies", on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    rent_amount = models.DecimalField(
        "Initial monthly rent", max_digits=12, decimal_places=2,
        help_text="Rent agreed at the start of the tenancy. "
                  "Later increases are recorded as rent revisions.",
    )
    security_deposit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Deposit taken at move-in. Can be applied to final months' "
                  "rent when the occupant leaves.",
    )
    deposit_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Remaining unused deposit.",
    )
    is_active = models.BooleanField(default=True)
    notice_given = models.BooleanField(
        default=False,
        help_text="Occupant has given notice to leave — unlocks payment from "
                  "the security deposit.",
    )
    agreement_reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name_plural = "Occupancies"

    def __str__(self):
        return f"{self.occupant} @ {self.flat} (from {self.start_date})"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.deposit_balance:
            self.deposit_balance = self.security_deposit
        super().save(*args, **kwargs)

    def rent_for_month(self, month: date):
        """Effective rent for a given month, honouring rent revisions."""
        rent = self.rent_amount
        for rev in self.revisions.filter(effective_from__lte=month).order_by("effective_from"):
            rent = rev.new_rent
        return rent

    @property
    def current_rent(self):
        return self.rent_for_month(date.today().replace(day=1))

    @property
    def rent_increase_since_start(self):
        return self.current_rent - self.rent_amount


class RentRevision(models.Model):
    """A rent increase (or decrease) taking effect from a given month."""
    occupancy = models.ForeignKey(Occupancy, related_name="revisions", on_delete=models.CASCADE)
    effective_from = models.DateField(help_text="First month the new rent applies to.")
    new_rent = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["effective_from"]

    def save(self, *args, **kwargs):
        self.effective_from = self.effective_from.replace(day=1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.occupancy} → {self.new_rent} from {self.effective_from:%b %Y}"


class Document(models.Model):
    class DocType(models.TextChoices):
        NID = "nid", "NID"
        ID = "id", "ID Card"
        AGREEMENT = "agreement", "Agreement"
        LEGAL = "legal", "Legal Proof"
        OTHER = "other", "Other"

    occupant = models.ForeignKey(Occupant, related_name="documents", on_delete=models.CASCADE)
    doc_type = models.CharField(max_length=12, choices=DocType.choices, default=DocType.OTHER)
    title = models.CharField(max_length=120)
    file = models.FileField(upload_to="documents/occupants/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.occupant}"
