"""ΚΗΜΔΗΣ records reach the curated layer without officials, emails or addresses (PRIVACY.md Q6)."""

import tempfile
import unittest
from pathlib import Path

from tinos.curated_khmdhs import MASK, procurement_rows
from tinos.store import RawStore

STAMP = {"derived_at": None, "pipeline_version": "test"}
# Made-up people; the ΑΦΜ fails the check digit, so no real person has it.
PERSON, PERSON_AFM = "ΔΟΚΙΜΑΚΗΣ ΤΕΣΤΟΣ", "012345678"
OFFICIAL, EMAIL, STREET = "ΥΠΑΛΛΗΛΟΥ ΠΑΡΑΔΕΙΓΜΑ", "someone@example.invalid", "ΟΔΟΣ ΔΟΚΙΜΗΣ 12"

CONTRACT = {
    "referenceNumber": "24SYMV000000001", "organization": {"key": "6296", "value": "ΔΗΜΟΣ ΤΗΝΟΥ"},
    "submissionDate": "2024-03-05T10:00:00.000", "contractSignedDate": "2024-03-04", "cancelled": False,
    "title": "Προμήθεια υλικών", "procedureType": {"key": "6", "value": "Απευθείας ανάθεση (αρ.118/αρ. 328)"},
    "contractType": {"key": "1", "value": "Προμήθειες"}, "totalCostWithoutVAT": 1000.0, "totalCostWithVAT": 1240.0,
    "diavgeiaADA": None, "contractRelatedADA": {"number1": None, "number2": None, "number3": "92Π4ΩΗ6-9ΒΚ"},
    "authorEmail": EMAIL,
    "objectDetailsList": [{"cpvs": [{"key": "44113100-6", "value": "Υλικά"}], "costWithoutVAT": 1000}],
    "contractingDataDetails": {
        "contractingMembersDataList": [
            {"vatNumber": "800123456", "greekVatNumber": True, "name": "ΑΛΦΑ ΤΕΧΝΙΚΗ ΑΕ", "country": "GR"},
            {"vatNumber": PERSON_AFM, "greekVatNumber": True, "name": PERSON, "country": "GR"}],
        "signers": {"key": "1", "value": OFFICIAL}, "unitsOperator": {"key": "2", "value": OFFICIAL}},
}

PAYMENT = {
    "referenceNumber": "24PAY000000002", "organization": {"key": "6296", "value": "ΔΗΜΟΣ ΤΗΝΟΥ"},
    "submissionDate": "2024-04-10T09:00:00.000", "signedDate": "2024-04-09", "cancelled": False,
    "title": "Πληρωμή", "totalCostWithoutVAT": 1000.0, "totalCostWithVAT": 1240.0, "contractRefNo": None,
    "paymentRelatedAda": None, "authorEmail": EMAIL,
    "contractingData": {"signers": {"key": "1", "value": OFFICIAL}},
    "objectDetails": [
        {"vatNo": "800123456", "greekVatNo": True, "name": "ΑΛΦΑ ΤΕΧΝΙΚΗ ΑΕ", "costWithoutVAT": 600,
         "addressForDelivery": STREET, "streetNumber": "12", "postalCode": "84200", "city": "ΤΗΝΟΣ", "cpvs": []},
        {"vatNo": PERSON_AFM, "greekVatNo": True, "name": PERSON, "costWithoutVAT": 400,
         "addressForDelivery": STREET, "streetNumber": "12", "postalCode": "84200", "city": "ΤΗΝΟΣ", "cpvs": []}],
}


class Procurement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)
        store = RawStore(self.raw)
        store.put_khmdhs_record("contract", "6296", CONTRACT)
        store.put_khmdhs_record("payment", "6296", PAYMENT)
        self.records, self.parties = procurement_rows(self.raw, STAMP)

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_row_per_record(self):
        self.assertEqual([(r["endpoint"], r["record_type"], r["year"]) for r in self.records],
                         [("contract", "SYMV", 2024), ("payment", "PAY", 2024)])
        contract = self.records[0]
        self.assertEqual(contract["procedure_type"], "Απευθείας ανάθεση (αρ.118/αρ. 328)")
        self.assertEqual(contract["diavgeia_adas"], ["92Π4ΩΗ6-9ΒΚ"])
        self.assertEqual(contract["cpv"], ["44113100-6"])
        self.assertEqual(contract["contract_refs"], ["24SYMV000000001"])

    def test_natural_persons_are_masked(self):
        shown = {(p["endpoint"], p["afm"]): p["display_name"] for p in self.parties}
        self.assertEqual(shown[("contract", "800123456")], "ΑΛΦΑ ΤΕΧΝΙΚΗ ΑΕ")
        self.assertEqual(shown[("contract", PERSON_AFM)], MASK)
        self.assertEqual(shown[("payment", PERSON_AFM)], MASK)

    def test_payment_split_between_payees_by_line_value(self):
        payees = {p["afm"]: p["amount_with_vat"] for p in self.parties if p["role"] == "payee"}
        self.assertEqual(payees, {"800123456": 744.0, PERSON_AFM: 496.0})

    def test_no_official_email_or_address_reaches_any_row(self):
        values = [str(v) for row in self.records + self.parties for v in row.values()]
        for secret in (EMAIL, OFFICIAL, STREET, "84200"):
            with self.subTest(secret=secret):
                self.assertFalse(any(secret in v for v in values))

    def test_a_later_capture_is_not_read_twice(self):
        RawStore(self.raw).put_khmdhs_record("contract", "6296", {**CONTRACT, "title": "edited"})
        records, _ = procurement_rows(self.raw, STAMP)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["title"], "Προμήθεια υλικών")


if __name__ == "__main__":
    unittest.main()
