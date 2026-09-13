"""Seed demo data that exercises the post-paid billing rules."""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from payments.models import Payment
from payments.utils import add_months, due_date_for, month_floor
from properties.models import Building, Flat, Level, Occupancy, Occupant, RentRevision


class Command(BaseCommand):
    help = "Seed demo buildings, occupants and post-paid payment history."

    def handle(self, *args, **opts):
        if Building.objects.exists():
            self.stdout.write("Demo data already present — skipping.")
            return

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@rentflow.local", "rentflow123")
            self.stdout.write("Superuser: admin / rentflow123")

        b1 = Building.objects.create(number="B-01", name="Tulip Court",
                                     address="House 12, Road 4, Gulshan-2, Dhaka")
        b2 = Building.objects.create(number="B-02", name="Orange Residency",
                                     address="Plot 7, Banani C/A, Dhaka")

        flats = {}
        for b, levels in ((b1, 3), (b2, 2)):
            for ln in range(1, levels + 1):
                lvl = Level.objects.create(building=b, number=ln)
                for fx in ("A", "B"):
                    f = Flat.objects.create(
                        level=lvl, number=f"{ln}0{1 if fx == 'A' else 2}",
                        unit_type="flat", size_sqft=950 + ln * 50,
                        bedrooms=2 + (fx == "B"), bathrooms=2,
                        amenities="Balcony, Parking, Lift",
                        base_rent=Decimal(18000 + ln * 1500),
                    )
                    flats[f"{b.number}-{ln}{fx}"] = f
        # one shop
        shop = Flat.objects.create(
            level=Level.objects.filter(building=b2, number=1).first(),
            number="S-01", unit_type="shop", size_sqft=400,
            amenities="Street front", base_rent=Decimal(30000),
        )

        today = date.today()
        m0 = month_floor(today)

        def occupant(i, name, email, phone, nid):
            return Occupant.objects.create(
                full_name=name, email=email, phone=phone, nid=nid,
                occupant_id=f"OCC-{i:04d}",
                emergency_contact_name="Family contact",
                emergency_contact_phone="01700000000",
            )

        # 1) Fully paid-up tenant (started 8 months ago, all billable months paid)
        o1 = occupant(1, "Rahim Uddin", "rahim@example.com", "01711111111", "1990123456")
        oc1 = Occupancy.objects.create(
            flat=flats["B-01-1A"], occupant=o1,
            start_date=add_months(m0, -8), rent_amount=Decimal(19500),
            security_deposit=Decimal(39000),
        )
        self._pay_all(oc1, upto_offset=-1)

        # 2) Tenant with last month due (inside 1–20 window) — like the user's
        #    example: started August 1, in September pays August's rent.
        o2 = occupant(2, "Nusrat Jahan", "nusrat@example.com", "01722222222", "1992345678")
        oc2 = Occupancy.objects.create(
            flat=flats["B-01-2A"], occupant=o2,
            start_date=add_months(m0, -1), rent_amount=Decimal(21000),
            security_deposit=Decimal(42000),
        )
        # no payments yet — last month's rent is currently payable

        # 3) Tenant with 2 overdue months
        o3 = occupant(3, "Kamal Hossain", "kamal@example.com", "01733333333", "1985678901")
        oc3 = Occupancy.objects.create(
            flat=flats["B-01-3B"], occupant=o3,
            start_date=add_months(m0, -6), rent_amount=Decimal(24000),
            security_deposit=Decimal(48000),
        )
        self._pay_all(oc3, upto_offset=-3)  # leaves ~2 unpaid finished months

        # 4) Leaving tenant with notice given + rent increase → deposit + top-up demo
        o4 = occupant(4, "Shirin Akter", "shirin@example.com", "01744444444", "1988901234")
        oc4 = Occupancy.objects.create(
            flat=flats["B-02-1A"], occupant=o4,
            start_date=add_months(m0, -14), rent_amount=Decimal(20000),
            security_deposit=Decimal(40000), notice_given=True,
        )
        RentRevision.objects.create(
            occupancy=oc4, effective_from=add_months(m0, -4),
            new_rent=Decimal(22000), note="Annual increase",
        )
        self._pay_all(oc4, upto_offset=-2)  # last finished month unpaid → pay via deposit

        # 5) Shop tenant, paid up
        o5 = occupant(5, "Hasan Traders", "hasan@example.com", "01755555555", "")
        oc5 = Occupancy.objects.create(
            flat=shop, occupant=o5,
            start_date=add_months(m0, -10), rent_amount=Decimal(30000),
            security_deposit=Decimal(60000),
        )
        self._pay_all(oc5, upto_offset=-1)

        self.stdout.write(self.style.SUCCESS(
            "Demo data seeded. Post-paid rules: current month is never billed; "
            "each finished month is payable the following month."
        ))

    def _pay_all(self, occ, upto_offset):
        """Create paid records from start month up to (current month + upto_offset)."""
        today = date.today()
        m0 = month_floor(today)
        last = add_months(m0, upto_offset)
        m = month_floor(occ.start_date)
        while m <= last:
            rent = occ.rent_for_month(m)
            pay_on = add_months(m, 1).replace(day=min(10, 28))
            Payment.objects.create(
                occupancy=occ, period_month=m, amount=rent,
                payment_date=pay_on, due_date=due_date_for(m),
                method="bank", status="paid",
                details={"sender_bank": "City Bank",
                         "receiving_bank": "City Bank — RentFlow A/C 1401-2233-4455",
                         "reference_no": f"TRX-{m:%Y%m}-{occ.pk}",
                         "transfer_date": pay_on.isoformat()},
            )
            m = add_months(m, 1)
