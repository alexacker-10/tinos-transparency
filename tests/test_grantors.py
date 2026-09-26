"""The grantors found from the municipality's own acceptances: each document checks its own amount, and the money is
counted once, at the document that moves it."""

import unittest
from datetime import date

from tinos.curated_grants import _mark_paid_through
from tinos.extract.grantors import read_eot, read_green_fund, read_pde, read_ped, read_rows, read_shipping

# The Regional Union's payment order (synthetic; the layout of ΨΒ6ΘΟΚΔΠ-80Β).
PED_ORDER = """\
               ΧΡΗΜΑΤΙΚΟ ΕΝΤΑΛΜΑ ΠΛΗΡΩΜΗΣ
ΠΛΗΡΩΤΕΟ ΑΠΟ :                  Π.Ε.Δ. Ν.ΑΙΓΑΙΟΥ
ΔΙΚΑΙΟΥΧΟΣ........:             ΔΗΜΟΣ ΤΗΝΟΥ
                                Α.Φ.Μ. : 800302968
           ΑΙΤΙΑ       ΠΛΗΡΩΜΗΣ                        Κ.Α. Εξόδων               Ποσό
ΧΡΗΜΑΤΟΔΟΤΗΣΗ ΤΟΥ ΔΗΜΟΥ ΤΗΝΟΥ ΓΙΑ ΑΘΛΗΤΙΚΗ      10-6472.                    8.680,00
                                                                                            ΣΥΝΟΛΟ :        8.680,00
ΑΠΟΦΑΣΗ Δ.Σ. ΜΕ ΑΔΑ: 9ΑΑΑΟΚΔΠ-ΑΑΑ
                                             ΚΑΘΑΡ. ΔΙΚΑΙΟΥΧΟ:               8.680,00
Σύμφωνα με τα παραπάνω ο αρμόδιος Ταμίας να Πληρώσει το Συνολικό Ποσό που είναι
                                   ### Οκτώ Χιλ. Εξακόσια Ογδόντα (8.680,00) ευρώ ###
"""

PED_BOARD = """\
ΘΕΜΑ : «Αίτημα Δήμων για χρηματοδότηση αθλητικής διοργάνωσης»
                     Α Π Ο Φ Α Σ Ι Ζ Ε Ι       Ο Μ Ο Φ Ω Ν Α
 1. Αποδέχεται το αίτημα των Δημάρχων Τήνου, Άνδρου, Νάξου και Πάρου, για χρηματοδότηση από την ΠΕΔ Νοτίου
 Αιγαίου της διοργάνωσης, με την κάλυψη της δαπάνης των 34.720,00 ευρώ (8.680,00 ευρώ χ 4 Δήμοι διεξαγωγής).
 2. Εγκρίνει τη διάθεση πίστωσης ποσού 34.720,00€ του προϋπολογισμού της ΠΕΔ οικ. έτους 2022.
"""

GF_PAYMENT = """\
                                           ΑΠΟΦΑΣΙΖΟΥΜΕ
 Εγκρίνουμε τη δαπάνη ποσού (Τριάντα εννιά χιλιάδες τριακόσια σαράντα επτά Ευρώ και εβδομήντα οκτώ
 Λεπτά) «39.347,78€» για την πληρωμή ισόποσης δαπάνης σε βάρος του ΚΑΕ 2279 και δικαιούχο τον ΔΗΜΟ ΤΗΝΟΥ
 με Α.Φ.Μ. 800302968.
"""

GF_ESCROW = """\
 Η υπηρεσία εκπονείται με προϋπολογισμού 29.512,00 € συμπεριλαμβανομένου Φ.Π.Α.
               κατόπιν των ανωτέρω τα μέλη του ΔΣ ομόφωνα αποφασίζουν
 2. Να δοθεί εντολή προς το Ταμείο Παρακαταθηκών και Δανείων να εκταμιεύσει από τον δεσμευμένο λογαριασμό
    το ποσό των 10.200,00 € για την πληρωμή μέρους του λογαριασμού της υπηρεσίας του Δήμου ΤΗΝΟΥ.
 3. Να δοθεί εντολή σύστασης παρακαταθήκης υπέρ του Δήμου ΤΗΝΟΥ ποσού ύψους 19.312,00 €.
 4. Να δοθεί εντολή εξόφλησης της ως άνω παρακαταθήκης υπέρ του Δήμου ΤΗΝΟΥ ποσού ύψους 19.312,00 €.
"""

SHIP_ORDER = """\
Θέμα: Εντολή κατανομής εξουσιοδοτήσεως πληρωμής της ΣΑΝΑ 233.
ΣΧΕΤ.: 1) Η απόφαση του Γενικού Διευθυντή (ΑΔΑ:61ΑΑ4653ΠΩ-ΑΑΑ)
Παρακαλούμε να χρεώσετε τον λογαριασμό της ΣΑΝΑ 233 με το ποσό των τεσσάρων χιλιάδων εννιακοσίων ογδόντα έξι
ευρώ και σαράντα έξι λεπτών (4.986,46 €) και να πιστώσετε ισόποσα τον λογαριασμό του έργου.
Ο λογαριασμός του έργου θα τηρηθεί στην Τράπεζα της Ελλάδος, με υπόλογο διαχειριστή το Δήμο Τήνου
(ΑΦΜ 800302968).
"""

# A ΠΔΕ transfer table (the layout of the 2016 ΕΣΠΑ orders): «8,000.00», a negative «-.54», one section per ΣΑ.
EN_TABLE = """\
 1 2011ΕΠ06780019   ΠΕΡΙΒΑΛΛΟΝΤΙΚΗ     2271/2711606780019013 ΔΗΜΟΣ ΚΩ        997918919           -.54
                    ΑΠΟΚΑΤΑΣΤΑΣΗ
 2 2013ΕΠ06780000   ΕΠΕΚΤΑΣΗ ΚΤΗΡΙΟΥ   2341/2713606780000013 ΔΗΜΟΣ ΤΗΝΟΥ     800302968       1,500.00
                    ΣΧΟΛΕΙΟΥ ΤΗΝΟΥ
 3 2013ΕΠ06780015   ΑΠΟΚΑΤΑΣΤΑΣΗ ΚΑΙ   2271/2713606780015013 ΔΗΜΟΣ ΚΩ        997918919      60,000.00
ΣΥΝΟΛΟ ΣΑ                                                                                   61,499.46
"""


class RegionalUnion(unittest.TestCase):
    def test_a_payment_order_to_the_municipality(self):
        (a,), status, family = read_ped(PED_ORDER, "ped_payment")
        self.assertEqual((a.amount, a.net, a.validation, status), (868000, 868000, "words_and_figures", "read"))

    def test_a_payment_order_to_anyone_else_is_absent(self):
        amounts, status, _ = read_ped(PED_ORDER.replace("800302968", "998226218"), "ped_payment")
        self.assertEqual((amounts, status), ([], "absent"))

    def test_a_joint_grant_gives_the_municipality_its_share(self):
        (a,), status, _ = read_ped(PED_BOARD, "ped_grant")
        self.assertEqual((a.amount, a.validation), (868000, "stated_amount"))
        (a,), _, _ = read_ped(PED_BOARD.replace("(8.680,00 ευρώ χ 4", "(8.600,00 ευρώ χ 4"), "ped_grant")
        self.assertIsNone(a.validation)  # 4 x 8.600,00 is not the stated 34.720,00

    def test_an_event_it_organises_itself_is_its_own_spending(self):
        amounts, status, family = read_ped(PED_BOARD, "ped_grant", "Αίτημα Δήμου Τήνου για τη συνδιοργάνωση εκδήλωσης")
        self.assertEqual((amounts, status, family), ([], "listed", "ped_own_spending"))


class GreenFund(unittest.TestCase):
    def test_a_payment_to_the_municipality_in_words_and_figures(self):
        (a,), status, _ = read_green_fund(GF_PAYMENT, "green_fund_payment")
        self.assertEqual((a.amount, a.validation), (3934778, "words_and_figures"))

    def test_a_payment_to_a_contractor_is_absent(self):
        text = GF_PAYMENT.replace("τον ΔΗΜΟ ΤΗΝΟΥ", "τον ανάδοχο της μελέτης").replace("800302968", "012345678")
        self.assertEqual(read_green_fund(text, "green_fund_payment")[:2], ([], "absent"))

    def test_the_municipality_named_with_a_wrong_afm_is_still_the_payee(self):
        (a,), status, _ = read_green_fund(GF_PAYMENT.replace("800302968", "998292246"), "green_fund_payment")
        self.assertEqual((a.amount, status), (3934778, "read"))
        self.assertIn("998292246", a.detail)

    def test_an_escrow_release_and_deposit_add_up_to_the_service_budget(self):
        amounts, status, _ = read_green_fund(GF_ESCROW, "green_fund_payment")
        self.assertEqual([(a.amount, a.method, a.validation) for a in amounts],
                         [(1020000, "escrow_release", "stated_amount"), (1931200, "escrow_deposit", "stated_amount")])


class Shipping(unittest.TestCase):
    def test_a_transfer_to_the_project_account_the_municipality_holds(self):
        (a,), status, _ = read_shipping(SHIP_ORDER, "pde_authorisation")
        self.assertEqual((a.amount, a.validation), (498646, "words_and_figures"))

    def test_the_transfer_is_counted_and_the_approval_it_cites_is_not(self):
        def dec(ada, family, day, cites=()):
            return {"ada": ada, "issuer": "100015969", "family": family, "date": day, "duplicate_of": None,
                    "_cites": set(cites)}
        decisions = [dec("61ΑΑ4653ΠΩ-ΑΑΑ", "shipping_payment", date(2023, 12, 1)),
                     dec("6ΓΓΓ4653ΠΩ-ΓΓΓ", "pde_authorisation", date(2023, 12, 14), ["61ΑΑ4653ΠΩ-ΑΑΑ"]),
                     dec("ΨΨΨΨ4653ΠΩ-ΨΨΨ", "shipping_payment", date(2025, 6, 30))]
        lines = [{"ada": d["ada"], "amount": 4986.46, "validation": "words_and_figures", "category": "investment_programmes",
                  "detail": ""} for d in decisions]
        _mark_paid_through(decisions, lines)
        self.assertEqual([d["paid_by"] for d in decisions], ["6ΓΓΓ4653ΠΩ-ΓΓΓ", None, None])
        self.assertEqual([l["category"] for l in lines], [None, "investment_programmes", "investment_programmes"])


class RegionalUnionPairing(unittest.TestCase):
    def dec(self, ada, family, day, cites=()):
        return {"ada": ada, "issuer": "53992", "family": family, "date": day, "duplicate_of": None, "_cites": set(cites)}

    def test_grants_paid_or_replaced_are_listed_the_rest_counted(self):
        decisions = [
            self.dec("ΓΡ1ΑΟΚΔΠ-ΑΑΑ", "ped_grant", date(2021, 3, 22)),             # paid by the order citing it
            self.dec("ΠΛ1ΑΟΚΔΠ-ΑΑΑ", "ped_payment", date(2021, 7, 16), ["ΓΡ1ΑΟΚΔΠ-ΑΑΑ"]),
            self.dec("ΓΡ2ΑΟΚΔΠ-ΑΑΑ", "ped_grant", date(2023, 7, 10)),             # replaced by a later decision
            self.dec("ΓΡ3ΑΟΚΔΠ-ΑΑΑ", "ped_grant", date(2024, 4, 5), ["ΓΡ2ΑΟΚΔΠ-ΑΑΑ"]),
            self.dec("ΠΛ3ΑΟΚΔΠ-ΑΑΑ", "ped_payment", date(2024, 8, 5)),           # same amount, cites nothing of it
            self.dec("ΓΡ4ΑΟΚΔΠ-ΑΑΑ", "ped_grant", date(2022, 12, 15)),            # no payment order: counted
        ]
        amounts = {"ΓΡ1ΑΟΚΔΠ-ΑΑΑ": 5000.0, "ΠΛ1ΑΟΚΔΠ-ΑΑΑ": 5000.0, "ΓΡ2ΑΟΚΔΠ-ΑΑΑ": 9920.0,
                   "ΓΡ3ΑΟΚΔΠ-ΑΑΑ": 8680.0, "ΠΛ3ΑΟΚΔΠ-ΑΑΑ": 8680.0, "ΓΡ4ΑΟΚΔΠ-ΑΑΑ": 10000.0}
        lines = [{"ada": a, "amount": v, "validation": "stated_amount", "category": "state_grants", "detail": ""}
                 for a, v in amounts.items()]
        _mark_paid_through(decisions, lines)
        paid = {d["ada"]: d["paid_by"] for d in decisions}
        self.assertEqual(paid, {"ΓΡ1ΑΟΚΔΠ-ΑΑΑ": "ΠΛ1ΑΟΚΔΠ-ΑΑΑ", "ΠΛ1ΑΟΚΔΠ-ΑΑΑ": None,
                                "ΓΡ2ΑΟΚΔΠ-ΑΑΑ": "ΓΡ3ΑΟΚΔΠ-ΑΑΑ", "ΓΡ3ΑΟΚΔΠ-ΑΑΑ": "ΠΛ3ΑΟΚΔΠ-ΑΑΑ",
                                "ΠΛ3ΑΟΚΔΠ-ΑΑΑ": None, "ΓΡ4ΑΟΚΔΠ-ΑΑΑ": None})
        counted = sorted(l["amount"] for l in lines if l["category"])
        self.assertEqual(counted, [5000.0, 8680.0, 10000.0])


class TransferTables(unittest.TestCase):
    def test_english_figures_sections_and_a_row_found_by_its_afm(self):
        (a,) = read_rows(EN_TABLE)
        self.assertEqual((a.amount, a.validation, a.recipient), (150000, "stated_amount", "6296"))

    def test_a_row_is_not_given_the_next_rows_afm(self):
        # row 1 has no ΑΦΜ of its own within its lines; the Tinos ΑΦΜ two lines below belongs to row 2
        text = EN_TABLE.replace("ΔΗΜΟΣ ΚΩ        997918919           -.54", "ΔΗΜΟΣ ΚΩ                            -.54")
        self.assertEqual([a.amount for a in read_rows(text)], [150000])

    def test_payment_lines_against_the_stated_total(self):
        text = ("ΕΡΓΑ ΧΡΗΜΑΤΟΔΟΤΟΥΜΕΝΑ ΑΠΟ ΤΟ ΤΑΜΕΙΟ ΑΝΑΚΑΜΨΗΣ συνολικού ποσού 10.000,00 ευρώ\n"
                "79262223                                         ΔΗΜΟΣ ΤΗΝΟΥ                         4.000,00\n"
                "79262224                                         ΔΗΜΟΣ ΠΑΛΛΗΝΗΣ                      6.000,00\n")
        (a,) = read_rows(text)
        self.assertEqual((a.amount, a.validation), (400000, "stated_amount"))

    def test_a_project_code_names_the_municipality(self):
        text = ("Θέμα: «Κατανομή χρηματοδότησης 160.082,90€ στο έργο με κωδικό 2018ΣΕ36700029»\n"
                "εγκρίνουμε τη χρέωση της ΣΑΕ 367 με το ποσό των πεντακοσίων είκοσι τριών χιλιάδων ευρώ (160.082,90€ €)\n")
        subject = "«Κατανομή χρηματοδότησης 160.082,90€ στο έργο με κωδικό 2018ΣΕ36700029»"
        self.assertEqual(read_pde(text, "pde_financing", subject)[1], "absent")  # no Tinos name, ΑΦΜ or code known
        (a,), status, _ = read_pde(text, "pde_financing", subject, codes={"2018ΣΕ36700029": "6296"})
        # the words spell another amount; the subject states these figures
        self.assertEqual((a.amount, a.validation), (16008290, "stated_amount"))


class TourismOrganisation(unittest.TestCase):
    def test_gross_withheld_and_net(self):
        text = ("ΔΙΚΑΙΟΥΧΟΣ :      ΔΗΜΟΣ ΤΗΝΟΥ ( ΑΦΜ:090188990 )\n"
                "   ΕΝΤΕΛΛΟΜΕΝΟ                                   ΣΥΝΟΛΟ                                            ΠΛΗΡΩΤΕΟ\n"
                "                                 18.000,00                                    540,00          17.460,00\n"
                "    ΣΥΝΟΛΟ ΕΝΤΑΛΜΑΤΟΣ :            Δέκα Οκτώ Χιλιάδες Ευρώ\n")
        (a,), status, _ = read_eot(text, "eot_payment")
        self.assertEqual((a.amount, a.net, a.validation), (1800000, 1746000, "words_and_figures"))


if __name__ == "__main__":
    unittest.main()
