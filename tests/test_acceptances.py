"""The municipality's acceptances of other bodies' money, read from their titles alone (FINDINGS F12)."""

import unittest

from tinos.extract.acceptances import classify


class Acceptances(unittest.TestCase):
    def test_grantor_amount_and_kind_from_the_title(self):
        for subject, expected in (
                ("Αποδοχή χρηματοδότησης ποσού 8.680,00€ από την Περιφερειακή Ένωση Δήμων Νοτίου Αιγαίου για την κάλυψη "
                 "δαπάνης αθλητικής διοργάνωσης", ("ped", "acceptance", 868000)),
                ("Αποδοχή χρηματοδότησης ποσού 9.920,00 € από την ΠΕΔ Ν. Αιγαίου για χρηματοδότηση καμπάνιας",
                 ("ped", "acceptance", 992000)),
                ("Αποδοχή χρηματοδότησης από το Πράσινο Ταμείο ποσού 35.000,00 € για την εκπόνηση Σχεδίου",
                 ("green_fund", "acceptance", 3500000)),
                ("Έγκριση 3ης αναμόρφωσης οικ. Έτους 2024 για αποδοχή χρηματοδότησης ποσού 12.400,00€ από την Περιφέρεια "
                 "Ν. Αιγαίου για την υλοποίηση του έργου", ("region", "amendment", 1240000)),
                ("Εισήγηση για αποδοχή χρηματοδότησης ποσού 34.200,00 € από το ΥΠΕΣ προς κάλυψη έκτακτων αναγκών",
                 ("interior", "proposal", 3420000)),
                ("Αποδοχή χρηματοδότησης ποσού 120.000,00€ από το Ναυτιλίας και Νησιωτικής Πολιτικής για τη μίσθωση",
                 ("shipping", "acceptance", 12000000)),
                ("Αποδοχή χρηματοδότησης ποσού 4.695,53 €, για την υλοποίηση προγράμματος Κοινωνικής Προστασίας.",
                 ("unknown", "acceptance", 469553))):
            with self.subTest(subject=subject[:40]):
                got = classify(subject)
                self.assertEqual((got["grantor"], got["kind"], got["amount_stated"]), expected)

    def test_acts_that_move_no_money_are_not_acceptances(self):
        for subject in ("Αποδοχή παραίτησης Δημοτικού Συμβούλου",
                        "Αποδοχή των Όρων Συμμετοχής στο Πρόγραμμα «ΑΝΤΩΝΗΣ ΤΡΙΤΣΗΣ» και υποβολή της πρότασης",
                        "Περί αποδοχής όρων για τη λήψη επενδυτικού τοκοχρεολυτικού δανείου από το Ταμείο Παρ/κων",
                        "Αποδοχή ένταξης της πράξης «Βελτίωση Υποδομών Ύδρευσης» στο «ΤΠΑ Υπουργείου Εσωτερικών»",
                        "Χορήγηση αντιγράφου πράξης αποδοχής κληρονομιάς",
                        "Αποδοχή κινητών πραγμάτων (χαρακτικών έργων)",
                        "Αποδοχή της πρότασης του κ. Επωνύμου περί τμηματικής καταβολής οφειλόμενου ποσού"):
            with self.subTest(subject=subject[:40]):
                self.assertIsNone(classify(subject))

    def test_a_donation_of_money_is_an_acceptance(self):
        got = classify("Αποδοχή δωρεάς του Σωματείου «Οι φίλοι της Τήνου», ποσού 1.000,00 €")
        self.assertEqual((got["grantor"], got["amount_stated"]), ("private", 100000))
