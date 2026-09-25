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


if __name__ == "__main__":
    unittest.main()
