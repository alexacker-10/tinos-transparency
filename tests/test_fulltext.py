"""Full-text search: nothing is trusted without counts, nothing about a person is kept."""

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

import httpx

from tinos.config import Settings
from tinos.sources.fulltext import (CONTROL_TERM, FulltextClient, GuardViolation, SearchRequest, check_control,
                                    check_page, check_year, issue_day, redact_page, whitelist_reason, year_windows)
from tinos.store import RawStore

REQ = SearchRequest("ΤΗΝΟΥ", "100054492", date(2024, 11, 1), date(2024, 11, 10))
KAP = "Απόδοση εσόδων από τους Κεντρικούς Αυτοτελείς Πόρους έτους 2024, σε όλους τους Δήμους της Χώρας"
CITIZEN = "Απόκτηση ελληνικής ιθαγένειας (ν. 3284/2004) από τον ΕΠΩΝΥΜΟ ΟΝΟΜΑ"


def rec(ada="ΡΟ0946ΜΤΛ6-ΣΚ8", org="100054492", issued="04/11/2024 02:00:00", subject=KAP, dtype="2.4.7.1", co=None):
    return {"ada": ada, "issueDate": issued, "status": "PUBLISHED", "subject": subject,
            "decisionType": {"uid": dtype, "label": "..."}, "organization": {"uid": org, "label": "ΥΠΟΥΡΓΕΙΟ"},
            "cooperatingOrganizations": [{"uid": u} for u in co] if co else None, "documentUrl": f"https://x/{ada}"}


def page(records, total=None, number=0, size=100, query=None, highlighting=None):
    return {"decisions": records, "facets": [],
            "highlighting": highlighting if highlighting is not None else {r["ada"]: {"documentText": ["<pre>ΤΗΝΟΥ</pre>"]}
                                                                          for r in records},
            "info": {"query": query, "page": number, "size": size, "actualSize": len(records),
                     "total": len(records) if total is None else total, "order": None}}


class Requests(unittest.TestCase):
    def test_params_quote_the_term_and_bound_whole_days(self):
        self.assertEqual(REQ.params(), [
            ("q", '"ΤΗΝΟΥ"'), ("fq", 'organizationUid:"100054492"'),
            ("fq", "issueDate:[DT(2024-11-01T00:00:00) TO DT(2024-11-10T23:59:59)]"), ("page", "0"), ("size", "100")])

    def test_bad_terms_orgs_and_sizes_are_refused(self):
        for kwargs in ({"term": "Τήνου"}, {"term": "ΤΗΝΟΥ ΚΥΚΛΑΔΩΝ"}, {"term": '"x'}, {"term": "../A"},
                       {"org": "ypes"}, {"size": 101}, {"size": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SearchRequest(**{"term": "ΤΗΝΟΥ", "org": "100054492", "date_from": date(2024, 1, 1),
                                 "date_to": date(2024, 1, 2), **kwargs})
        with self.assertRaises(ValueError):
            SearchRequest("ΤΗΝΟΥ", "1", date(2024, 1, 2), date(2024, 1, 1))

    def test_issue_date_is_the_athens_civil_date(self):
        self.assertEqual(issue_day("04/11/2024 02:00:00"), date(2024, 11, 4))  # UTC midnight, winter
        self.assertEqual(issue_day("30/06/2016 03:00:00"), date(2016, 6, 30))  # UTC midnight, summer
        self.assertEqual(issue_day("31/12/2013 00:00:00"), date(2013, 12, 31))  # pre-2014 local midnight
        for bad in ("2024-11-04", "", None, "4/11/2024 02:00:00"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                issue_day(bad)

    def test_half_years_tile_each_year(self):
        spans = list(year_windows(date(2015, 1, 1), date(2025, 12, 31)))
        self.assertEqual(len(spans), 11)
        days = []
        for (y0, y1), windows in spans:
            self.assertEqual((windows[0][0], windows[-1][1]), (y0, y1))
            for a, b in windows:
                days += [a + timedelta(n) for n in range((b - a).days + 1)]
        self.assertEqual(len(days), len(set(days)))  # no overlap
        self.assertEqual(len(days), (date(2025, 12, 31) - date(2015, 1, 1)).days + 1)  # no gap

    def test_partial_range(self):
        spans = list(year_windows(date(2019, 8, 15), date(2020, 3, 1)))
        self.assertEqual(spans, [((date(2019, 8, 15), date(2019, 12, 31)), [(date(2019, 8, 15), date(2019, 12, 31))]),
                                 ((date(2020, 1, 1), date(2020, 3, 1)), [(date(2020, 1, 1), date(2020, 3, 1))])])


class Guard(unittest.TestCase):
    def test_matching_page_passes(self):
        check_page(REQ, page([rec()]))

    def test_co_issued_act_passes(self):
        check_page(REQ, page([rec(org="100015990", co=["100054492", "15"])]))

    def test_other_issuer_fails(self):
        # What a dropped organisation filter looks like from here.
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec(org="6296")]))

    def test_act_outside_window_fails(self):
        for issued in ("31/10/2024 02:00:00", "11/11/2024 02:00:00"):
            with self.subTest(issued=issued), self.assertRaises(GuardViolation):
                check_page(REQ, page([rec(issued=issued)]))

    def test_capped_page_size_fails(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec()], size=10))

    def test_wrong_page_or_count_fails(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec()], number=1))
        broken = page([rec()])
        broken["info"]["actualSize"] = 2
        with self.assertRaises(GuardViolation):
            check_page(REQ, broken)

    def test_an_echo_appearing_is_contract_drift(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec()], query='q:"ΤΗΝΟΥ"'))

    def test_unsafe_ada_and_stray_highlight_fail(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec(ada="../x")], highlighting={}))
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec()], highlighting={"ΑΛΛΟ46ΜΤΛ6-ΑΑΑ": {}}))

    def test_non_page_fails(self):
        for raw in ({"errors": []}, [], {"info": {"total": "3"}, "decisions": []}):
            with self.subTest(raw=raw), self.assertRaises(GuardViolation):
                check_page(REQ, raw)

    def test_the_term_must_change_the_count(self):
        check_control(REQ, 2, 150)
        check_control(REQ, 0, 0)
        check_control(REQ, 17, 1)  # before Nov 2015 only subjects are indexed: the letterhead word is rare
        for total, control in ((150, 150), (3, 3)):  # what an ignored q looks like
            with self.subTest(total=total), self.assertRaises(GuardViolation):
                check_control(REQ, total, control)

    def test_a_year_must_hold_what_its_windows_held(self):
        check_year("1", "ΤΗΝΟΥ", date(2024, 1, 1), date(2024, 12, 31), 64, [25, 39])
        with self.assertRaises(GuardViolation):
            check_year("1", "ΤΗΝΟΥ", date(2024, 1, 1), date(2024, 12, 31), 60, [25, 39])


class Whitelist(unittest.TestCase):
    def test_grants_are_kept(self):
        for subject, dtype in (
                (KAP, "2.4.7.1"),
                ("Κατανομή ποσού ύψους 54.664.484,00 € σε Δήμους της Χώρας για την κάλυψη δαπάνης μισθοδοσίας "
                 "προσωπικού καθαριότητας σχολικών μονάδων", "Α.2"),
                ("Επιχορήγηση των Δήμων της χώρας για λειτουργικές δαπάνες, με βάση τον υπολογισμό του ν. 3852", "Α.2"),
                ("172η κατανομή χρηματοδότησης ΣΑΕ 055 έτους 2020", "Β.1.1"),
                ("Υποβολή πρότασης κατάρτισης Π.Δ.Ε. Υπουργείου Εσωτερικών", "Β.1.1"),
                ("ΕΝΤΑΞΗ ΠΡΑΞΗΣ ΤΟΥ ΔΗΜΟΥ ΤΗΝΟΥ ΣΤΟ ΠΡΟΓΡΑΜΜΑ «ΦΙΛΟΔΗΜΟΣ ΙΙ»", "Β.1.1"),
                ("AΠOΔOΣH EΣOΔΩN AΠO TOYΣ KAΠ", "Α.2")):  # Latin look-alike capitals
            with self.subTest(subject=subject[:40]):
                self.assertIsNone(whitelist_reason(rec(subject=subject, dtype=dtype)))

    def test_acts_about_people_are_dropped(self):
        for subject in (CITIZEN, "Κατανομή προσωπικού", "Περιλήψεις μετάταξης υπαλλήλων",
                        "Διορισμός συγγενούς αποβιώσαντος", "Ορισμός υπολόγου – διαχειριστή για το έργο 2001ΣΕ05500002",
                        "Διαταγή συγκρότησης επιτροπής", "ΒΕΒΑΙΩΣΗ ΠΛΗΡΩΜΗΣ ΤΗΣ ΔΡΑΣΗΣ «ΕΝΑΡΜΟΝΙΣΗ ΟΙΚΟΓΕΝΕΙΑΚΗΣ ΖΩΗΣ»",
                        "Έγκριση δαπάνης τροφοδοσίας κρατουμένων αλλοδαπών", "Κατανομή πιστώσεων για πλήρωση θέσεων"):
            with self.subTest(subject=subject[:40]):
                self.assertEqual(whitelist_reason(rec(subject=subject, dtype="Β.1.1")), "personal")

    def test_a_ministrys_own_purchases_are_not_grants(self):
        self.assertEqual(whitelist_reason(rec(subject="ΑΠΟΦΑΣΗ ΑΝΑΛΗΨΗΣ ΥΠΟΧΡΕΩΣΗΣ", dtype="Β.1.3")), "not_a_grant")
        self.assertEqual(whitelist_reason(rec(subject="Προμήθεια καυσίμων του Α.Τ. Τήνου", dtype="Δ.1")), "not_a_grant")

    def test_redaction_keeps_only_what_the_guard_checks(self):
        kept, dropped = rec(), rec(ada="ΨΨΨΨ46ΜΤΛ6-ΑΒΓ", subject=CITIZEN)
        raw = page([kept, dropped], highlighting={kept["ada"]: {"documentText": ["230 58216 <pre>ΤΗΝΟΥ</pre> 1,00"]},
                                                  dropped["ada"]: {"documentText": ["ΕΠΩΝΥΜΟ ΟΝΟΜΑ <pre>Τήνου</pre>"]}})
        red = redact_page(raw, {kept["ada"]})
        self.assertEqual(red["decisions"][0], kept)
        self.assertEqual(set(red["decisions"][1]), {"ada", "issueDate", "status", "organization",
                                                    "cooperatingOrganizations", "redacted"})
        self.assertEqual(list(red["highlighting"]), [kept["ada"]])
        text = json.dumps(red, ensure_ascii=False)
        self.assertNotIn("ΕΠΩΝΥΜΟ", text)
        self.assertNotIn("ιθαγένειας", text)
        check_page(REQ, red)  # the stored page still passes the guard


class Client(unittest.TestCase):
    def client(self, responses):
        queue = list(responses)
        seen = []

        def handler(request):
            seen.append(parse_qsl(request.url.query.decode()))
            status, body = queue.pop(0)
            return httpx.Response(status, json=body)

        c = FulltextClient(Settings(root=Path("."), fulltext_delay=0, fulltext_backoff=0))
        c._http.close()
        c._http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(c.close)
        return c, seen

    def test_query_carries_the_term_org_and_window(self):
        c, seen = self.client([(200, page([rec()]))])
        p = c.search_page(REQ)
        self.assertEqual(seen[0], REQ.params())
        self.assertEqual(len(p.received_sha256), 64)

    def test_all_pages_are_fetched(self):
        a, b = rec("ΑΑΑΑ46ΜΤΛ6-ΑΑΑ"), rec("ΒΒΒΒ46ΜΤΛ6-ΒΒΒ")
        small = SearchRequest("ΤΗΝΟΥ", "100054492", date(2024, 11, 1), date(2024, 11, 10), size=1)
        c, seen = self.client([(200, page([a], total=2, size=1)), (200, page([b], total=2, number=1, size=1))])
        self.assertEqual([len(p.decisions) for p in c.search_all(small)], [1, 1])
        self.assertEqual([dict(q)["page"] for q in seen], ["0", "1"])

    def test_unstable_paging_fails(self):
        a = rec("ΑΑΑΑ46ΜΤΛ6-ΑΑΑ")
        small = SearchRequest("ΤΗΝΟΥ", "100054492", date(2024, 11, 1), date(2024, 11, 10), size=1)
        c, _ = self.client([(200, page([a], total=2, size=1)), (200, page([a], total=2, number=1, size=1))])
        with self.assertRaises(GuardViolation):
            list(c.search_all(small))

    def test_control_count_uses_the_control_term(self):
        c, seen = self.client([(200, page([rec()], total=9230, size=1))])
        self.assertEqual(c.count(REQ, CONTROL_TERM).total, 9230)
        self.assertEqual(dict(seen[0])["q"], f'"{CONTROL_TERM}"')
        self.assertEqual(dict(seen[0])["size"], "1")

    def test_throttling_is_retried_and_errors_raise(self):
        c, _ = self.client([(429, {}), (200, page([rec()]))])
        self.assertEqual(c.search_page(REQ).total, 1)
        self.assertEqual((c.calls, c.retried), (2, 1))
        c, _ = self.client([(400, {"errors": [{"errorCode": "SEARCH-001"}]})])
        with self.assertRaises(httpx.HTTPStatusError):
            c.search_page(REQ)

    def test_index_unavailable_is_retried_other_500s_are_not(self):
        c, _ = self.client([(500, {"errors": [{"errorCode": "SEARCH-006"}]}), (200, page([rec()]))])
        self.assertEqual(c.search_page(REQ).total, 1)
        c, _ = self.client([(500, {"errors": [{"errorCode": "SEARCH-999"}]})])
        with self.assertRaises(httpx.HTTPStatusError):
            c.search_page(REQ)
        self.assertEqual(c.calls, 1)


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = RawStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_decision_is_filed_under_its_own_issuer(self):
        r = rec(org="100015990", co=["100054492"])
        res = self.store.put_fulltext_decision(r)
        self.assertEqual(res.path, self.root / "diavgeia" / "fulltext" / "decisions" / "100015990" / f"{r['ada']}.json")
        self.assertEqual(self.store.find_fulltext_decision(r["ada"]), res.path)
        self.assertEqual(self.store.put_fulltext_decision(r).outcome, "unchanged")
        self.assertEqual(self.store.put_fulltext_decision({**r, "subject": "edited"}).outcome, "changed")
        self.assertEqual(self.store.iter_fulltext_decisions(), [res.path])  # the sibling is a later capture

    def test_page_path_and_unsafe_parts(self):
        res = self.store.put_fulltext_page("100054492", "ΤΗΝΟΥ", "2024-01-01", "2024-06-30", 0, page([rec()]))
        self.assertEqual(res.path.parent, self.root / "diavgeia" / "fulltext" / "search" / "100054492" / "ΤΗΝΟΥ")
        for org, term in (("../x", "ΤΗΝΟΥ"), ("100054492", "../ΤΗΝΟΥ"), ("100054492", "τηνου")):
            with self.subTest(org=org, term=term), self.assertRaises(ValueError):
                self.store.put_fulltext_page(org, term, "2024-01-01", "2024-06-30", 0, {})
        with self.assertRaises(ValueError):
            self.store.put_fulltext_decision(rec(ada="../../etc"))


if __name__ == "__main__":
    unittest.main()
