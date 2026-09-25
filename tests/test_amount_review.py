"""amount_review.yaml flags exactly the euro a human checked, and fails loudly if it moved."""

import unittest
from pathlib import Path

from tinos.curated import RawAct, payment_rows

ADA = "6Ξ6ΖΩΗ6-26Β"
STAMP = {"derived_at": None, "pipeline_version": "test"}
LINES = [("00.8229.0006", 2783.97), ("00.8221", 13491.65), ("00.8211", 2023213.00), ("00.8222", 754.66)]


def act(lines=LINES) -> RawAct:
    sponsors = [{"expenseAmount": {"amount": amt, "currency": "EUR"}, "kae": kae,
                 "sponsorAFMName": {"afm": "090000000", "afmType": "EL", "name": "ΕΛΛΗΝΙΚΟ ΔΗΜΟΣΙΟ"}}
                for kae, amt in lines]
    doc = {"ada": ADA, "organizationId": "6296", "decisionTypeId": "Β.2.2", "status": "PUBLISHED",
           "issueDate": 1709071200000, "subject": "Κατάσταση Κρατήσεων Φεβρουαρίου 2024",
           "extraFieldValues": {"sponsor": sponsors}}
    return RawAct(Path("x.json"), "0" * 64, doc)


def flagged(review) -> list[int]:
    return [r["line_no"] for r in payment_rows(act(), STAMP, frozenset(), review) if r["amount_suspect"]]


class AmountReview(unittest.TestCase):
    def test_line_entry_flags_that_line_only(self):
        entry = {"ada": ADA, "line_no": 2, "kae": "00.8211", "metadata_amount": 2023213.00}
        self.assertEqual(flagged({ADA: entry}), [2])

    def test_whole_act_entry_flags_every_line(self):
        self.assertEqual(flagged({ADA: {"ada": ADA, "metadata_amount": 2023213.00}}), [0, 1, 2, 3])

    def test_no_entry_flags_nothing(self):
        self.assertEqual(flagged({}), [])

    def test_moved_amount_fails_the_build(self):
        entry = {"ada": ADA, "line_no": 1, "metadata_amount": 2023213.00}
        with self.assertRaises(ValueError):
            flagged({ADA: entry})

    def test_wrong_kae_fails_the_build(self):
        entry = {"ada": ADA, "line_no": 2, "kae": "00.8221", "metadata_amount": 2023213.00}
        with self.assertRaises(ValueError):
            flagged({ADA: entry})

    def test_missing_line_fails_the_build(self):
        entry = {"ada": ADA, "line_no": 9, "metadata_amount": 2023213.00}
        with self.assertRaises(ValueError):
            flagged({ADA: entry})


class DuplicatePostings(unittest.TestCase):
    def rows(self, review=None, duplicates=None):
        return payment_rows(act(), STAMP, frozenset(), review or {}, duplicates or {})

    def test_duplicate_flags_every_line(self):
        rows = self.rows(duplicates={ADA: {"ada": ADA, "duplicate_of": "ΑΛΛΗ6-ΑΔΑ"}})
        self.assertEqual([(r["amount_suspect"], r["suspect_reason"]) for r in rows],
                         [(True, "duplicate_posting")] * len(LINES))

    def test_mismatch_reason_wins_on_its_line(self):
        rows = self.rows(review={ADA: {"ada": ADA, "line_no": 2, "metadata_amount": 2023213.00}},
                         duplicates={ADA: {"ada": ADA, "duplicate_of": "ΑΛΛΗ6-ΑΔΑ"}})
        self.assertEqual([r["suspect_reason"] for r in rows],
                         ["duplicate_posting", "duplicate_posting", "document_mismatch", "duplicate_posting"])

    def test_other_acts_are_untouched(self):
        rows = self.rows(duplicates={"ΑΛΛΗ6-ΑΔΑ": {"ada": "ΑΛΛΗ6-ΑΔΑ", "duplicate_of": ADA}})
        self.assertFalse(any(r["amount_suspect"] for r in rows))


if __name__ == "__main__":
    unittest.main()
