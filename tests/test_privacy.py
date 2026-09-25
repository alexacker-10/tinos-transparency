"""Nothing the public repository carries may name or identify a natural person.

PRIVACY.md Q1. Standard library only: ``python -m unittest discover -s tests``.
"""

import unittest
from pathlib import Path

from tinos.publish.privacy import Markers, find_leaks, load_markers, name_keys, scan_files, tracked_files
from tinos.publish.summary import _cell

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "releases" / "tinos.duckdb"

# A made-up person. The comma pair is assembled at runtime so that this file
# does not itself contain the pattern the guard looks for.
SURNAME, NAME, FATHER = "ΔΟΚΙΜΑΚΗΣ", "ΤΕΣΤΟΣ", "ΠΑΡΑΔΕΙΓΜΑΣ"
PERSON_FORM = SURNAME + ",," + NAME + "," + FATHER
AFM = "012345678"  # fails the ΑΦΜ check digit, so no real person has it
MARKERS = Markers(frozenset(name_keys(PERSON_FORM)), frozenset({AFM}))


class FindLeaks(unittest.TestCase):
    def kinds(self, text, markers=MARKERS):
        return sorted({leak.kind for leak in find_leaks(text, markers)})

    def test_person_form_needs_no_database(self):
        self.assertEqual(self.kinds(f"| 6296 | {PERSON_FORM} |", None), ["person_form"])

    def test_documented_placeholder_is_not_a_person(self):
        self.assertEqual(self.kinds("Diavgeia writes individuals as `SURNAME,,NAME,FATHER`.", None), [])

    def test_name_in_prose_in_either_order_with_accents(self):
        self.assertEqual(self.kinds("πληρώθηκε ο Τέστος Δοκιμάκης"), ["name"])
        self.assertEqual(self.kinds("ΔΟΚΙΜΑΚΗΣ ΤΕΣΤΟΣ του ΠΑΡΑΔΕΙΓΜΑ"), ["name"])

    def test_latin_look_alike_capitals_are_folded(self):
        self.assertEqual(self.kinds("ΔOKIMAKHΣ TEΣTOΣ"), ["name"])

    def test_afm_alone_but_not_inside_a_longer_token(self):
        self.assertEqual(self.kinds(f"ΑΦΜ {AFM}"), ["afm"])
        self.assertEqual(self.kinds(f"sha256 ab{AFM}cd, 1{AFM}"), [])

    def test_masked_row_is_clean(self):
        self.assertEqual(self.kinds("| 6296 | 2015-08-17 | Ω25ΙΩΗ6-ΟΜΘ | 281,880.00 | φυσικό πρόσωπο | Προμήθεια |"), [])

    def test_surname_alone_is_not_enough(self):
        self.assertEqual(self.kinds(f"οικογένεια {SURNAME}"), [])

    def test_partnership_named_after_its_partner_is_a_company_name(self):
        firm = Markers(MARKERS.name_keys, MARKERS.afms, frozenset({(SURNAME, NAME, "ΚΑΙ", "ΣΙΑ", "ΟΕ")}))
        self.assertEqual(self.kinds(f"| 800000000 | {SURNAME} {NAME} ΚΑΙ ΣΙΑ ΟΕ | 345,213.66 |", firm), [])
        self.assertEqual(self.kinds(f"| {SURNAME} {NAME} ΚΑΙ Σ |", firm), [], "a table cut the name short")
        self.assertEqual(self.kinds(f"| {SURNAME} {NAME} | φυσικό πρόσωπο |", firm), ["name"])


class TableCells(unittest.TestCase):
    def test_source_text_cannot_break_or_inject_markdown(self):
        self.assertEqual(_cell("α | β\nγ <img src=x>"), "α \\| β γ &lt;img src=x>")
        self.assertEqual(_cell(None), "")


class TrackedFiles(unittest.TestCase):
    def test_no_tracked_file_uses_the_person_form(self):
        leaks = scan_files(tracked_files(ROOT), None, ROOT)
        self.assertEqual([], leaks, "\n".join(map(str, leaks)))

    @unittest.skipUnless(DB.is_file(), "needs releases/tinos.duckdb for the names and ΑΦΜ")
    def test_no_tracked_file_names_or_identifies_a_natural_person(self):
        leaks = scan_files(tracked_files(ROOT), load_markers(DB), ROOT)
        self.assertEqual([], leaks, "\n".join(map(str, leaks)))


if __name__ == "__main__":
    unittest.main()
