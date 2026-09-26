"""Grant decisions: an amount for Tinos counts only when the document's own totals confirm it."""

import unittest

from tinos.extract.grants import (CATEGORY_OF_FAMILY, budget_year, family_of, parse_allocation, read_decision,
                                  revenue_category, tinos_lines, words_to_cents)

# A monthly ΚΑΠ table: gross, withholdings, net; the ΣΥΝΟΛΑ line closes it.
KAP = """\
  1     50102   ΑΓΡΙΝΙΟΥ            ΑΙΤΩΛ/ΝΙΑΣ     1.187.818,76             0,00          52.377,90     1.135.440,86
                ΙΕΡΑΣ ΠΟΛΗΣ
  2     50117   ΜΕΣΟΛΟΓΓΙΟΥ         ΑΙΤΩΛ/ΝΙΑΣ      518.568,43              0,00          18.467,92       500.100,51
  3     58216   ΤΗΝΟΥ              ΚΥΚΛΑΔΩΝ       197.677,98             0,00           0,00           197.677,98
                              ΣΥΝΟΛΑ                1.904.065,17             0,00          70.845,82     1.833.219,35
"""


class Tables(unittest.TestCase):
    def test_net_layout_reads_the_gross_and_validates_every_column(self):
        tables, _ = parse_allocation(KAP)
        self.assertEqual(len(tables), 1)
        self.assertEqual((tables[0].layout, tables[0].validation), ("net", "column_totals"))
        (line,) = tinos_lines(tables)
        self.assertEqual((line.amount, line.net, line.validation, line.n_rows), (19767798, 19767798, "column_totals", 3))

    def test_a_missed_row_leaves_the_table_unvalidated(self):
        broken = KAP.replace("  2     50117   ΜΕΣΟΛΟΓΓΙΟΥ", "  2     ΜΕΣΟΛΟΓΓΙΟΥ")
        (line,) = tinos_lines(parse_allocation(broken)[0])
        self.assertIsNone(line.validation)

    def test_components_then_total(self):
        text = """\
  1  50102  ΑΓΡΙΝΙΟΥ   ΑΙΤΩΛ/ΝΙΑΣ   100,00   50,00   150,00
  2  58216  ΤΗΝΟΥ      ΚΥΚΛΑΔΩΝ     121.570,34   115.031,59   236.601,93
          ΣΥΝΟΛΟ                121.670,34   115.081,59   236.751,93
"""
        (line,) = tinos_lines(parse_allocation(text)[0])
        self.assertEqual((line.layout, line.amount, line.validation), ("sum", 23660193, "column_totals"))

    def test_a_breakdown_column_enters_no_net(self):
        # Nov 2025: one column (art. 115) is neither withheld nor added for the row it concerns.
        text = """\
  1  50102  ΑΓΡΙΝΙΟΥ   Α   1.000,00   10,00   0,00     990,00
  2  59423  ΗΡΑΚΛΕΙΟΥ  Β   2.000,00   20,00   5,00   1.980,00
  3  58216  ΤΗΝΟΥ      Γ     500,00    0,00   0,00     500,00
       ΣΥΝΟΛΟ              3.500,00   30,00   5,00   3.470,00
"""
        tables, _ = parse_allocation(text)
        self.assertEqual((tables[0].layout, tables[0].signs), ("net", (-1, 0)))

    def test_rounding_in_the_source_is_tolerated_and_recorded(self):
        text = "  1  50102  Α  Β  33,33\n  2  58216  ΤΗΝΟΥ  Γ  66,66\n  ΣΥΝΟΛΟ  100,00\n"
        tables, _ = parse_allocation(text)
        self.assertEqual(tables[0].validation, "column_totals")
        self.assertIn("rounding", tables[0].note)

    def test_blank_cells_and_wrapped_rows(self):
        text = """\
  1  50102  ΑΓΡΙΝΙΟΥ    Α   1.000,00         5,00        995,00
  2  50117  ΜΕΣΟΛΟΓΓΙΟΥ Β   2.000,00                   2.000,00
                ΝΑΞΟΥ ΚΑΙ ΜΙΚΡΩΝ
  3  58212
                ΚΥΚΛΑΔΩΝ    Γ     300,00         0,00        300,00
  4  58216  ΤΗΝΟΥ       Δ     400,00         0,00        400,00
        ΣΥΝΟΛΟ              3.700,00         5,00      3.695,00
"""
        tables, _ = parse_allocation(text)
        self.assertEqual(len(tables[0].rows), 4)
        self.assertEqual(tables[0].validation, "column_totals")
        self.assertEqual(tables[0].rows[1].amounts, (200000, 0, 200000))

    def test_math_symbol_delta_and_whole_euro_tables(self):
        text = "  1  55203  ∆ΟΞΑΤΟΥ  ∆ΡΑΜΑΣ  100,00\n  2  58216  ΤΗΝΟΥ  ΚΥΚΛΑΔΩΝ  200,00\n  ΣΥΝΟΛΟ  300,00\n"
        self.assertEqual(parse_allocation(text)[0][0].validation, "column_totals")
        whole = "206   Δ. ΣΥΡΟΥ   ΚΥΚΛΑΔΩΝ   47.900\n207   Δ. ΤΗΝΟΥ   ΚΥΚΛΑΔΩΝ   29.700\n  ΣΥΝΟΛΟ ΟΤΑ  77.600\n"
        (line,) = tinos_lines(parse_allocation(whole)[0])
        self.assertEqual((line.amount, line.validation), (2970000, "column_totals"))


class Letters(unittest.TestCase):
    def test_words_are_the_letters_own_check(self):
        for words, cents in (("τριάντα τεσσάρων χιλιάδων εκατόν πενήντα επτά ευρώ & τεσσάρων λεπτών", 3415704),
                             ("σαράντα τεσσάρων χιλιάδων τριακοσίων δέκα τριών ευρώ & ογδόντα οκτώ λεπτών", 4431388),
                             ("πέντε χιλιάδων δώδεκα ΕΥΡΩ και 44 λεπτών", 501244),
                             ("δύο εκατομμυρίων τριακοσίων χιλιάδων ευρώ", 230000000)):
            with self.subTest(words=words):
                self.assertEqual(words_to_cents(words), cents)
        self.assertIsNone(words_to_cents("για την αντιμετώπιση της λειψυδρίας"))

    def test_transfer_letter_for_tinos(self):
        text = ("Σας παρακαλούμε να χρεώσετε τη ΣΑΕ 055/2023 με το ποσό των τριάντα τεσσάρων χιλιάδων εκατόν "
                "πενήντα επτά ευρώ & τεσσάρων λεπτών (34.157,04€) και να πιστώσετε τον λογαριασμό.\n"
                "Διαχειριστής του πιο πάνω ποσού είναι ο Δήμος Τήνου, Ν. Κυκλάδων (Α.Φ.Μ.: 800302968).\n")
        amounts, status = read_decision(text, "4059η κατανομή χρηματοδότησης ΣΑΕ 055 έτους 2023, Δήμου Τήνου.")
        self.assertEqual(status, "read")
        self.assertEqual([(a.amount, a.validation) for a in amounts], [(3415704, "words_and_figures")])

    def test_words_that_disagree_do_not_validate(self):
        text = ("με το ποσό των τριάντα χιλιάδων ευρώ (34.157,04€). "
                "Διαχειριστής του πιο πάνω ποσού είναι ο Δήμος Τήνου.")
        (amount,), _ = read_decision(text, None)
        self.assertIsNone(amount.validation)

    def test_a_validated_table_without_tinos_is_an_absence(self):
        text = "  1  50102  ΑΓΡΙΝΙΟΥ  Α  100,00\n  2  58206  ΕΡΜΟΥΠΟΛΗΣ  Β  50,00\n  ΣΥΝΟΛΟ  150,00\n"
        self.assertEqual(read_decision(text, None), ([], "absent"))


class Classification(unittest.TestCase):
    def test_families(self):
        for subject, family in (
                ("Απόδοση εσόδων από τους Κεντρικούς Αυτοτελείς Πόρους έτους 2023, σε όλους τους Δήμους της χώρας, "
                 "προς κάλυψη λειτουργικών και λοιπών γενικών δαπανών τους ή/και την υλοποίηση έργων και επενδυτικών "
                 "τους δραστηριοτήτων – Συμπληρωματική επιχορήγηση έτους 2023.", "kap_general"),
                ("Απόδοση εσόδων από τους ΚΑΠ έτους 2024, στους Δήμους της Χώρας, για κάλυψη δαπανών εκτέλεσης έργων "
                 "και επενδυτικών δραστηριοτήτων", "kap_investment"),
                ("Επιχορήγηση των Δήμων της χώρας με συνολικό ποσό ύψους 90.000.000,00€ για την κάλυψη λειτουργικών "
                 "και λοιπών γενικών δαπανών τους", "extraordinary"),
                ("Α΄ Κατανομή ποσού 28.000.000,00€ από τους ΚΑΠ έτους 2024, σε όλους τους Δήμους της Χώρας, για την "
                 "κάλυψη λειτουργικών δαπανών των σχολικών μονάδων", "school_operating"),
                ("Κατανομή ποσού 3.200.000,00€ σε Δήμους από τους ΚΑΠ έτους 2024, προς κάλυψη δαπανών λειτουργίας "
                 "εργοστασίων αφαλάτωσης ύδατος.", "desalination"),
                ("4059η κατανομή χρηματοδότησης ΣΑΕ 055 έτους 2023, Δήμου Τήνου.", "pde_financing"),
                ("Χρηματοδότηση του Δήμου Τήνου, Ν. Κυκλάδων για αντιμετώπιση προβλημάτων λειψυδρίας (ΣΑΕ 055).",
                 "pde_approval"),
                ("Επιχορήγηση των Περιφερειών της χώρας για την Ειδική Εκλογική Αποζημίωση", "to_regions")):
            with self.subTest(subject=subject[:50]):
                self.assertEqual(family_of(subject), family)
        self.assertIsNone(CATEGORY_OF_FAMILY["pde_approval"])  # an approval is not money sent

    def test_revenue_lines_are_matched_by_name_across_chart_changes(self):
        self.assertEqual(revenue_category("1311", "ΚΑΠ επενδυτικών δαπανών των δήμων"), "kap_investment")
        self.assertEqual(revenue_category("0612", "ΚΑΠ επενδυτικών δαπανών των δήμων"), "kap_investment")
        self.assertEqual(revenue_category("0612", "ΚΑΠ για την καταβολή μισθωμάτων ακινήτων προς στέγαση"), "school_rents")
        self.assertEqual(revenue_category("4311", "ΚΑΠ για την κάλυψη των λειτουργικών αναγκών των"), "kap_schools")
        self.assertEqual(revenue_category("1215", "Επιχορηγήσεις για εξόφληση ληξιπρόθεσμων υποχρεώσεων"), "state_grants")
        self.assertIsNone(revenue_category("3215", "Τέλος ακίνητης περιουσίας"))  # a prior-year receivable
        self.assertIsNone(revenue_category("4313", "Επιχορήγηση από ΟΑΕΔ για μακροχρόνια ανέργους"))

    def test_budget_year_comes_from_the_subject(self):
        self.assertEqual(budget_year("Απόδοση εσόδων από τους ΚΑΠ έτους 2016, σε όλους τους Δήμους", 2015), 2016)
        self.assertEqual(budget_year("Κατανομή ποσού εσόδων από το Τέλος Διαφήμισης", 2022), 2022)


if __name__ == "__main__":
    unittest.main()


class DoublePostings(unittest.TestCase):
    def test_same_protocol_date_and_subject_is_one_decision(self):
        from datetime import date

        from tinos.curated_grants import _mark_duplicates
        base = {"issuer": "100025896", "protocol_number": "8888", "date": date(2018, 3, 29),
                "subject": "Απόδοση εσόδων από τους ΚΑΠ έτους 2018 – Γ΄ κατανομή"}
        decisions = [{**base, "ada": "6ΩΥΘ465ΧΘ7-Ω4Η", "submission_ts": "2018-03-30T10:52:42", "n_amounts": 1},
                     {**base, "ada": "6ΠΒΟ465ΧΘ7-64Η", "submission_ts": "2018-03-30T10:44:26", "n_amounts": 1},
                     {**base, "ada": "ΑΛΛΗ465ΧΘ7-ΑΑΑ", "protocol_number": "8889", "submission_ts": "2018-03-30T11:00:00",
                      "n_amounts": 1}]
        lines = [{"ada": d["ada"]} for d in decisions]
        _mark_duplicates(decisions, lines)
        self.assertEqual([d["duplicate_of"] for d in decisions], ["6ΠΒΟ465ΧΘ7-64Η", None, None])
        self.assertEqual([x["duplicate_of"] for x in lines], ["6ΠΒΟ465ΧΘ7-64Η", None, None])

    def test_the_readable_copy_is_kept(self):
        from datetime import date

        from tinos.curated_grants import _mark_duplicates
        base = {"issuer": "100010874", "protocol_number": "27713", "date": date(2016, 9, 7), "subject": "Απόδοση εσόδων"}
        decisions = [{**base, "ada": "7Σ1Ζ465ΦΘΕ-ΞΟΜ", "submission_ts": "2016-09-09T15:19:51", "n_amounts": 0},
                     {**base, "ada": "ΨΥΓΦ465ΦΘΕ-ΞΧΨ", "submission_ts": "2016-09-09T15:28:45", "n_amounts": 1}]
        _mark_duplicates(decisions, [])
        self.assertEqual([d["duplicate_of"] for d in decisions], ["ΨΥΓΦ465ΦΘΕ-ΞΧΨ", None])
