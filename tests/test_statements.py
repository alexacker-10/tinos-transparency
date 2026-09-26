"""Execution statements are read exactly or not at all."""

import shutil
import subprocess
import unittest
from datetime import date
from pathlib import Path

from tinos.curated import is_execution_statement
from tinos.extract.statements import AMOUNT, StatementError, cents, parse_statement

ROOT = Path(__file__).resolve().parents[1]
DEC_2024 = ROOT / "data" / "raw" / "diavgeia" / "docs" / "6296" / "6ΝΠΘΩΗ6-Β64.pdf"

STANDARD = """\
                                  Στοιχεία Εκτέλεσης Προϋπολογισμού
                                        Περίοδος: Δεκέμβριος 2024
                                                   ΕΣΟΔΑ
0111     Μισθώματα από αστικά ακίνητα                  11.700,00      13.866,43      11.907,90
0129     Λοιπά έσοδα από ακίνητα                       21.900,00      21.809,28      21.809,28
         ΣΥΝΟΛΟ ΕΣΟΔΩΝ                                 33.600,00      35.675,71      33.717,18
                                                   ΕΞΟΔΑ
6011     Τακτικές αποδοχές                          1.439.392,00   1.373.622,77   1.299.000,00
8211     Απόδοση εισφ. υπέρ Δημοσίου                  245.000,00     217.858,34     217.858,34
         ΣΥΝΟΛΟ ΕΞΟΔΩΝ                              1.684.392,00   1.591.481,11   1.516.858,34
"""

NEW_2025 = """\
                ΚΑΤΑΣΤΑΣΗ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ ΕΣΟΔΩΝ ΕΩΣ 31/12/2025
0111       Μισθώματα από αστικά ακίνητα                            14.000,00          15.000,00         13.000,00
3123       Αναπτυξιακά - Επενδυτικά δάνεια Πρόγραμμα «Αντώνης Τρίτσης»
                                                                6.809.033,51
                                            παρ. 5 του άρ.4.329.159,47
                                                       130 του ν. 4635/2019,4.329.159,47
                                        ΓΕΝΙΚΟ ΣΥΝΟΛΟ:       6.823.033,51    4.344.159,47     4.342.159,47
                                                                                   Σελίδα 3 από 13
             ΚΑΤΑΣΤΑΣΗ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ ΔΑΠΑΝΩΝ ΕΩΣ 31/12/2025
00-6031                                                              67.916,00
          Αποδοχές (άρθρα 230,242 ΚΔΚ)                                             67.351,33         67.351,33
00-6723   Κράτηση 0,50% υπέρ λογαριασμού                            34.889,73              0,00              0,00
9111      Αποθεματικό                                                 9.953,68              0,00              0,00
          ΓΕΝΙΚΟ ΣΥΝΟΛΟ:   112.759,41   67.351,33      67.351,33
"""


class Amounts(unittest.TestCase):
    def test_cents(self):
        self.assertEqual(cents("1.234.567,89"), 123456789)
        self.assertEqual(cents("0,50"), 50)
        self.assertEqual(cents("-12,00"), -1200)

    def test_numbers_inside_descriptions_are_not_amounts(self):
        self.assertEqual(AMOUNT.findall("άρθρα 230,242 και κράτηση 0,50% υπέρ"), [])

    def test_wrapped_amounts_glued_to_text_are_amounts(self):
        self.assertEqual(AMOUNT.findall("από τους118.970,00 άρ.4.329.159,47 2019,4.329.159,47"),
                         ["118.970,00", "4.329.159,47", "4.329.159,47"])


class Standard(unittest.TestCase):
    def test_parses_and_validates(self):
        st = parse_statement(STANDARD)
        self.assertEqual((st.layout, st.period_end), ("standard", date(2024, 12, 31)))
        self.assertEqual([(ln.side, ln.kae) for ln in st.lines],
                         [("revenue", "0111"), ("revenue", "0129"), ("spending", "6011"), ("spending", "8211")])
        self.assertEqual(st.totals["spending"][2], 151685834)
        self.assertEqual(st.lines[0].description, "Μισθώματα από αστικά ακίνητα")

    def test_symbols_standing_for_greek_letters(self):
        # «∆» (increment) and «µ» (micro) as the port authority's 2016-2017 statements print them.
        text = STANDARD.replace("Προϋπολογισμού", "Προϋπολογισ\u00b5ού").replace("Δεκέμβριος", "\u2206εκέ\u00b5βριος")
        self.assertEqual(parse_statement(text).period_end, date(2024, 12, 31))

    def test_totals_that_do_not_add_up_are_refused(self):
        with self.assertRaises(StatementError):
            parse_statement(STANDARD.replace("1.516.858,34", "1.516.858,35"))

    def test_a_missed_row_is_refused(self):
        with self.assertRaises(StatementError):
            parse_statement(STANDARD.replace("8211     Απόδοση", "Απόδοση"))


class Layout2025(unittest.TestCase):
    def test_parses_wrapped_rows_and_the_unprefixed_reserve(self):
        st = parse_statement(NEW_2025)
        self.assertEqual((st.layout, st.period_end), ("2025", date(2025, 12, 31)))
        self.assertEqual([(ln.side, ln.service, ln.kae, ln.collected_or_paid) for ln in st.lines], [
            ("revenue", None, "0111", 1300000), ("revenue", None, "3123", 432915947),
            ("spending", "00", "6031", 6735133), ("spending", "00", "6723", 0), ("spending", None, "9111", 0)])
        # The name is the row's own text, or the next line's when the row has none.
        self.assertEqual([ln.description for ln in st.lines], [
            "Μισθώματα από αστικά ακίνητα", "Αναπτυξιακά - Επενδυτικά δάνεια Πρόγραμμα «Αντώνης Τρίτσης»",
            "Αποδοχές (άρθρα 230,242 ΚΔΚ)", "Κράτηση 0,50% υπέρ λογαριασμού", "Αποθεματικό"])

    def test_row_with_a_missing_amount_is_refused(self):
        broken = NEW_2025.replace("67.351,33         67.351,33", "67.351,33", 1)
        self.assertNotEqual(broken, NEW_2025)
        with self.assertRaises(StatementError):
            parse_statement(broken)


APOLOGISTIKA = """ΑΠΟΛΟΓΙΣΤΙΚΑ ΣΤΟΙΧΕΙΑ
                                                 Περίοδος: Φεβρουάριος 2015
                                                              ΕΣΟΔΑ
Κωδικός        Περιγραφή                                                               Διαμορφωθέν      Βεβαιωθέντα     Εισπραχθέντα
0              ΤΑΚΤΙΚΑ ΕΣΟΔΑ                                                               2.835.331,31      216.440,45      202.445,60
011            Μισθώματα                                                                       5.180,00       17.407,19        3.412,34
0111           Μισθώματα από αστικά ακίνητα (άρθρο 192 ΚΔΚ)                                    5.180,00       17.407,19        3.412,34
0111.0001      Μισθώματα από αστικά ακίνητα (άρθ.192 ΚΔΚ)                                      5.000,00       16.824,63        3.316,24
2119           Τακτικά έσοδα από λοιπά έσοδα                                                 225.120,00       38.200,48       38.200,48
2119.0002      Εισφορά (10% επί των ακαθαρίστων) Π.Ι.Ι.Ε.ΤΗΝΟΥ παρελθόντων ετών          220.000,00            0,00            0,00
-              ΓΕΝΙΚΟ ΣΥΝΟΛΟ                                                                230.300,00       55.607,67       41.612,82
                                                              ΕΞΟΔΑ
               ΓΕΝΙΚΕΣ ΥΠΗΡΕΣΙΕΣ                                                           1.167.164,99      245.173,15      233.806,65
6056           Ετήσια εισφορά στο ΤΑΔΚΥ (άρθρα 3ν. 1726/44, 30 Ν. 2262/52 100 νδ              95.170,69       23.700,00       23.700,00
               4260/61 και 33 νδ 5441/66)
6056.0001      Ετήσια εισφορά για το ΤΕΑΔΥ                                                   71.378,02        17.775,00       17.775,00
               ΥΠΗΡΕΣΙΕΣ ΚΑΘΑΡΙΟΤΗΤΑΣ
6056           Ετήσια εισφορά στο ΤΑΔΚΥ (άρθρα 3ν. 1726/44, 30 Ν. 2262/52 100 νδ               4.829,31        1.300,00        1.300,00
9111           Αποθεματικό                                                                    83.573,72            0,00            0,00
-              ΓΕΝΙΚΟ ΣΥΝΟΛΟ                                                                183.573,72       25.000,00       25.000,00
"""


class Apologistika(unittest.TestCase):
    def test_four_digit_rows_only_summed_per_kae(self):
        st = parse_statement(APOLOGISTIKA)
        self.assertEqual((st.layout, st.period_end.isoformat()), ("apologistika", "2015-02-28"))
        got = {(l.side, l.kae): (l.budgeted, l.collected_or_paid) for l in st.lines}
        self.assertEqual(got, {("revenue", "0111"): (518_000, 341_234), ("revenue", "2119"): (22_512_000, 3_820_048),
                               ("spending", "6056"): (10_000_000, 2_500_000), ("spending", "9111"): (8_357_372, 0)})

    def test_a_missed_row_is_refused(self):
        with self.assertRaises(StatementError):
            parse_statement(APOLOGISTIKA.replace("9111           Αποθεματικό", "91110          Αποθεματικό"))


class Refusals(unittest.TestCase):
    def test_2014_layout_is_refused(self):
        with self.assertRaises(StatementError):
            parse_statement("ΔΗΜΟΣ ΤΗΝΟΥ\n ΔΕΚΕΜΒΡΙΟΣ--ΕΣΟΔΑ\n 0 ΤΑΚΤΙΚΑ ΕΣΟΔΑ 2.562.156,50 238.799,71 261.837,13\n")

    def test_statement_acts_are_recognised_through_look_alikes(self):
        # Latin E and O among the Greek capitals, as clerks sometimes type them.
        self.assertTrue(is_execution_statement("Β.3", "ΔΗΜΟΣΙΕΥΣΗ ΣΤΟΙΧΕΙΩΝ EΚΤΕΛΕΣΗΣ ΠΡOΫΠΟΛΟΓΙΣΜΟΥ Μ.ΔΕΚΕΜΒΡΙΟΥ"))
        self.assertTrue(is_execution_statement("Β.3", "ΣΤΟΙΧΕΙΑ ΕΚΤΕΛΕΣΗΣ Π/Υ ΔΙΙΑΤ ΤΗΝΟΥ ΜΗΝΟΣ ΔΕΚΕΜΒΡΙΟΥ"))
        self.assertFalse(is_execution_statement("Β.3", "ΙΣΟΛΟΓΙΣΜΟΣ ΧΡΗΣΗΣ 2021"))
        self.assertFalse(is_execution_statement("Β.2.2", "ΔΗΜΟΣΙΕΥΣΗ ΣΤΟΙΧΕΙΩΝ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ"))


@unittest.skipUnless(DEC_2024.is_file() and shutil.which("pdftotext"), "stored PDF or pdftotext not available")
class RealDocument(unittest.TestCase):
    def test_december_2024_statement(self):
        text = subprocess.run(["pdftotext", "-layout", str(DEC_2024), "-"], capture_output=True, text=True, check=True).stdout
        st = parse_statement(text)
        self.assertEqual(st.period_end, date(2024, 12, 31))
        self.assertEqual(st.totals["spending"], (2366948209, 1115379410, 1113428387))


if __name__ == "__main__":
    unittest.main()


# The 2026 layout (new chart of accounts), cut down from the March 2026 statement ΨΝΟΧΩΗ6-Λ10: 3-digit services, 7-digit
# codes (10 with a spending sub-account), titles wrapped over several lines, and one row whose wrapped title carries the
# paid figure (22.400,37) above the warranted one (32.941,37).
NEW_2026 = """\
                  ΚΑΤΑΣΤΑΣΗ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ ΕΣΟΔΩΝ ΕΩΣ 31/3/2026
010.1310101       ΚΑΠ για την κάλυψη γενικών αναγκών                                            2.552.090,28         621.753,69            621.753,69
025.1310108       ΚΑΠ για λοιπούς σκοπούς                                                         433.025,00                0,00                  0,00
515.1390904       Έσοδα για την αποπληρωμή δανείων από το Ταμείο Παρακαταθηκών και Δανείων 305.444,24
                                                                                           χρηματοδοτούμενων από τον
                                                                                                                 0,00κρατικό προϋπολογισμό
                                                                                                                                     0,00
                                     ΓΕΝΙΚΟ ΣΥΝΟΛΟ:                                       3.290.559,52       621.753,69          621.753,69
                 ΚΑΤΑΣΤΑΣΗ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ ΔΑΠΑΝΩΝ ΕΩΣ 31/3/2026
000.2250905       Εισοδηματικές ενισχύσεις οικογενειών με χαμηλά εισοδήματα                     10.000,00              0,00               0,00
255.2130102001   Αμοιβές προσωπικού με σχέση εργασίας ιδιωτικού δικαίου ορισμένου χρόνου (ΙΔΟΧ)
                                                                                              127.844,00
                                                                                                ενιαίου μισθολογίου (συμπεριλαμβάνεται 22.400,37
                                                                                                                  32.941,37            και το εποχικό
                                     ΓΕΝΙΚΟ ΣΥΝΟΛΟ:                                        137.844,00        32.941,37          22.400,37
"""


class Layout2026(unittest.TestCase):
    def test_new_chart_rows_services_and_column_order(self):
        st = parse_statement(NEW_2026)
        self.assertEqual((st.layout, st.period_end), ("2026", date(2026, 3, 31)))
        by = {(ln.side, ln.service, ln.kae): ln for ln in st.lines}
        kap = by[("revenue", "010", "1310101")]
        self.assertEqual((kap.budgeted, kap.collected_or_paid, kap.description),
                         (255209028, 62175369, "ΚΑΠ για την κάλυψη γενικών αναγκών"))
        loans = by[("revenue", "515", "1390904")]
        self.assertEqual((loans.budgeted, loans.assessed_or_warranted, loans.collected_or_paid), (30544424, 0, 0))
        # the paid figure printed above the warranted one is still the paid column
        pay = by[("spending", "255", "2130102001")]
        self.assertEqual((pay.budgeted, pay.assessed_or_warranted, pay.collected_or_paid), (12784400, 3294137, 2240037))

    def test_both_charts_in_one_statement_is_refused(self):
        mixed = NEW_2026.replace("000.2250905 ", "6031        ", 1)
        with self.assertRaises(StatementError):
            parse_statement(mixed)
