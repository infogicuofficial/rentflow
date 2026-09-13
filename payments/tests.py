"""Tests for the post-paid billing rules and deposit handling."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from properties.models import Building, Flat, Level, Occupancy, Occupant, RentRevision

from .utils import billable_months, compute_due_summary, due_date_for


def make_occupancy(start, rent=20000, deposit=40000, **kw):
    b = Building.objects.create(number="T-1", name="Test", address="x")
    lvl = Level.objects.create(building=b, number=1)
    flat = Flat.objects.create(level=lvl, number="101", base_rent=rent)
    occ_person = Occupant.objects.create(
        full_name="Tester", email="t@example.com", phone="0", occupant_id="OCC-T1"
    )
    return Occupancy.objects.create(
        flat=flat, occupant=occ_person, start_date=start,
        rent_amount=Decimal(rent), security_deposit=Decimal(deposit), **kw
    )


class PostPaidLogicTests(TestCase):
    def test_start_month_not_billable_in_same_month(self):
        """Tenant starts 1 Aug — during August NOTHING is payable (post-paid)."""
        occ = make_occupancy(date(2026, 8, 1))
        s = compute_due_summary(occ, today=date(2026, 8, 15))
        self.assertEqual(s.payable, [])
        up = s.next_upcoming
        self.assertIsNotNone(up)
        self.assertEqual(up.month, date(2026, 8, 1))

    def test_august_rent_payable_in_september(self):
        """In September (1–20), August's rent is due but not overdue."""
        occ = make_occupancy(date(2026, 8, 1))
        s = compute_due_summary(occ, today=date(2026, 9, 10))
        self.assertEqual(len(s.due), 1)
        self.assertEqual(s.due[0].month, date(2026, 8, 1))
        self.assertEqual(s.overdue, [])
        self.assertEqual(s.due[0].due_date, date(2026, 9, 20))

    def test_august_rent_overdue_after_sept_20(self):
        occ = make_occupancy(date(2026, 8, 1))
        s = compute_due_summary(occ, today=date(2026, 9, 25))
        self.assertEqual(len(s.overdue), 1)
        self.assertEqual(s.overdue[0].days_overdue, 5)

    def test_multiple_months_accumulate(self):
        """By mid-October with nothing paid: Aug overdue, Sept due."""
        occ = make_occupancy(date(2026, 8, 1))
        s = compute_due_summary(occ, today=date(2026, 10, 10))
        # Aug due date was 20 Sep → overdue; Sep due 20 Oct → still due
        statuses = {m.month: m.status for m in s.months}
        self.assertEqual(statuses[date(2026, 8, 1)], "overdue")
        self.assertEqual(statuses[date(2026, 9, 1)], "due")

    def test_billable_months_range(self):
        occ = make_occupancy(date(2026, 8, 1))
        months = billable_months(occ, today=date(2026, 11, 5))
        self.assertEqual(months, [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)])

    def test_rent_revision_applies_from_effective_month(self):
        occ = make_occupancy(date(2026, 1, 1), rent=20000)
        RentRevision.objects.create(
            occupancy=occ, effective_from=date(2026, 6, 1), new_rent=Decimal(23000)
        )
        self.assertEqual(occ.rent_for_month(date(2026, 5, 1)), Decimal(20000))
        self.assertEqual(occ.rent_for_month(date(2026, 6, 1)), Decimal(23000))

    def test_due_date_is_20th_of_next_month(self):
        self.assertEqual(due_date_for(date(2026, 3, 1)), date(2026, 4, 20))


class DepositApiTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user("staff", password="pw")
        self.client.force_login(self.user)

    def _occ(self, notice=True):
        occ = make_occupancy(date(2025, 1, 1), rent=20000, deposit=40000,
                             notice_given=notice)
        RentRevision.objects.create(
            occupancy=occ, effective_from=date(2025, 6, 1), new_rent=Decimal(22000)
        )
        return occ

    def test_deposit_locked_without_notice(self):
        occ = self._occ(notice=False)
        s = compute_due_summary(occ, today=date(2025, 3, 5))
        r = self.client.post("/payments/api/verify/", {
            "occupancy_id": occ.pk,
            "months": [s.payable[0].key],
            "method": "deposit", "details": {}, "amount": "0",
        }, content_type="application/json")
        d = r.json()
        self.assertFalse(d["ok"])
        self.assertTrue(any("notice" in e for e in d["errors"]))

    def test_deposit_with_increase_requires_topup(self):
        """Rent rose 20000→22000; deposit covers 20000, top-up of 2000 required."""
        occ = self._occ(notice=True)
        # pick a month after the increase: June 2025 (payable in July)
        s = compute_due_summary(occ, today=date(2025, 7, 10))
        june = next(m for m in s.payable if m.month == date(2025, 6, 1))
        self.assertEqual(june.increase, Decimal(2000))

        r = self.client.post("/payments/api/verify/", {
            "occupancy_id": occ.pk,
            "months": [m.key for m in s.payable],  # must pay oldest-first
            "method": "deposit", "details": {}, "amount": "0",
        }, content_type="application/json")
        d = r.json()
        self.assertFalse(d["ok"])
        self.assertTrue(any("top-up" in e or "increase" in e.lower() for e in d["errors"]))

    def test_generate_deposit_payment_with_topup(self):
        occ = make_occupancy(date(2025, 1, 1), rent=20000, deposit=40000,
                             notice_given=True)
        RentRevision.objects.create(
            occupancy=occ, effective_from=date(2025, 2, 1), new_rent=Decimal(21500)
        )
        s = compute_due_summary(occ, today=date(2025, 3, 5))
        keys = [m.key for m in s.payable]  # Jan (20000) + Feb (21500)
        r = self.client.post("/payments/api/generate-invoice/", {
            "occupancy_id": occ.pk,
            "months": keys,
            "method": "deposit",
            "topup_method": "cash",
            "topup_details": {"received_by": "Manager", "received_date": "2025-03-05"},
            "details": {}, "amount": "0",
            "payment_date": "2025-03-05",
            "send_email": False,
        }, content_type="application/json")
        d = r.json()
        self.assertTrue(d["ok"], d)
        occ.refresh_from_db()
        # deposit used: 20000 (Jan) + 20000 base of Feb = 40000 → balance 0
        self.assertEqual(occ.deposit_balance, Decimal(0))
        feb = occ.payments.get(period_month=date(2025, 2, 1))
        self.assertEqual(feb.deposit_applied, Decimal(20000))
        self.assertEqual(feb.topup_amount, Decimal(1500))
        self.assertEqual(feb.topup_method, "cash")

    def test_cannot_skip_older_month(self):
        occ = make_occupancy(date(2025, 1, 1), rent=20000, notice_given=False)
        s = compute_due_summary(occ, today=date(2025, 4, 5))
        newest = s.payable[-1].key
        r = self.client.post("/payments/api/verify/", {
            "occupancy_id": occ.pk, "months": [newest],
            "method": "cash",
            "details": {"received_by": "X", "received_date": "2025-04-05"},
            "amount": "20000",
        }, content_type="application/json")
        d = r.json()
        self.assertFalse(d["ok"])
        self.assertTrue(any("oldest-first" in e for e in d["errors"]))

    def test_current_month_rejected(self):
        occ = make_occupancy(date(2025, 1, 1))
        today = date(2025, 2, 10)
        r = self.client.post("/payments/api/verify/", {
            "occupancy_id": occ.pk, "months": [today.strftime("%Y-%m")],
            "method": "cash",
            "details": {"received_by": "X", "received_date": "2025-02-10"},
            "amount": "20000",
        }, content_type="application/json")
        d = r.json()
        self.assertFalse(d["ok"])
