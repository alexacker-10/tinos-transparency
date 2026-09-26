"""Release views that read the monthly statements."""

import unittest

import duckdb

from tinos.curated import statement_body
from tinos.publish.release import VIEWS


class BudgetMonth(unittest.TestCase):
    def test_a_line_a_later_statement_drops_gives_its_money_back(self):
        # 2015: the tourism organisation's 17,460.00 in 1329 in February and March, in 1219 from April
        con = duckdb.connect()
        con.execute("""CREATE TABLE budget_line (entity VARCHAR, side VARCHAR, period_year INT, period_month INT,
                       kae VARCHAR, description VARCHAR, statement_ada VARCHAR, assessed_or_warranted DOUBLE,
                       collected_or_paid DOUBLE)""")
        rows = [("2", "1329", 17460.0), ("3", "1329", 17460.0), ("4", "1219", 17460.0), ("5", "1219", 17460.0)]
        for month, kae, v in rows:
            con.execute("INSERT INTO budget_line VALUES ('6296', 'revenue', 2015, ?, ?, 'x', ?, ?, ?)",
                        [int(month), kae, f"S{month}", v, v])
        for month in (2, 3, 4, 5):  # every statement prints some line
            con.execute("INSERT INTO budget_line VALUES ('6296', 'revenue', 2015, ?, '0311', 'y', ?, 1, 1)",
                        [month, f"S{month}"])
        got = con.execute(f"""SELECT month, kae, collected_in_period, absent FROM ({VIEWS['v_budget_month']})
                              WHERE kae IN ('1219', '1329') ORDER BY kae, month""").fetchall()
        self.assertEqual(got, [(4, "1219", 17460.0, False), (5, "1219", 0.0, False),
                               (2, "1329", 17460.0, False), (3, "1329", 0.0, False),
                               (4, "1329", -17460.0, True), (5, "1329", 0.0, True)])


class Letterhead(unittest.TestCase):
    def test_the_body_a_statement_names(self):
        text = "  ΑΔΑ: Χ\nΕΛΛΗΝΙΚΗ ΔΗΜΟΚΡΑΤΙΑ\nΔΗΜΟΤΙΚΟ ΙΔΡΥΜΑ ΜΟΥΣΕΙΟ ΚΩΣΤΑ ΤΣΟΚΛΗ\n   Στοιχεία Εκτέλεσης Προϋπολογισμού\n"
        self.assertEqual(statement_body(text), "ΔΗΜΟΤΙΚΟ ΙΔΡΥΜΑ ΜΟΥΣΕΙΟ ΚΩΣΤΑ ΤΣΟΚΛΗ")
        self.assertIsNone(statement_body("Στοιχεία Εκτέλεσης Προϋπολογισμού"))


if __name__ == "__main__":
    unittest.main()
