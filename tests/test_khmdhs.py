"""The ΚΗΜΔΗΣ client never trusts a page it cannot tie to the query it sent."""

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import httpx

from tinos.config import Settings
from tinos.sources.khmdhs import GuardViolation, KhmdhsClient, SearchRequest, check_page, iter_windows
from tinos.store import RawStore

REQ = SearchRequest("contract", "6296", date(2024, 3, 1), date(2024, 3, 31))


def rec(ref="24SYMV014483573", org="6296", sub="2024-03-05T10:00:00.000"):
    return {"referenceNumber": ref, "organization": {"key": org, "value": "ΔΗΜΟΣ ΤΗΝΟΥ"}, "submissionDate": sub}


def page(records, total=None, number=0, pages=1):
    return {"content": records, "totalElements": len(records) if total is None else total,
            "totalPages": pages, "number": number, "size": 50}


class Requests(unittest.TestCase):
    def test_window_over_180_days_is_refused_before_any_call(self):
        with self.assertRaises(ValueError):
            SearchRequest("contract", "6296", date(2024, 1, 1), date(2024, 12, 31))

    def test_unknown_endpoint_is_refused(self):
        with self.assertRaises(ValueError):
            SearchRequest("contracts", "6296", date(2024, 1, 1), date(2024, 1, 31))

    def test_windows_tile_the_range_exactly(self):
        start, end = date(2017, 1, 1), date(2026, 9, 25)
        wins = list(iter_windows(start, end, 150))
        self.assertEqual(wins[0][0], start)
        self.assertEqual(wins[-1][1], end)
        for (a, b), (c, _) in zip(wins, wins[1:]):
            self.assertEqual(c, b + timedelta(days=1))  # no gap, no overlap
        self.assertTrue(all((b - a).days <= 150 for a, b in wins))


class Guard(unittest.TestCase):
    def test_matching_page_passes(self):
        check_page(REQ, page([rec()]))

    def test_other_organisation_fails(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec(org="99999")]))

    def test_record_outside_window_fails(self):
        # What a silently truncated or ignored date filter looks like from here.
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec(sub="2024-04-01T09:00:00")]))

    def test_record_without_reference_fails(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec(ref=None)]))

    def test_wrong_page_number_fails(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, page([rec()], number=1))

    def test_non_page_fails(self):
        with self.assertRaises(GuardViolation):
            check_page(REQ, {"message": "error"})


class Client(unittest.TestCase):
    def client(self, responses):
        """A client whose server answers from ``responses`` in order."""
        queue = list(responses)
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            status, body = queue.pop(0)
            return httpx.Response(status, json=body)

        c = KhmdhsClient(Settings(root=Path("."), khmdhs_delay=0, khmdhs_backoff=0))
        c._http.close()
        c._http = httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler))
        self.addCleanup(c.close)
        return c, seen

    def test_request_body_names_org_and_both_dates(self):
        c, seen = self.client([(200, page([rec()]))])
        c.search_page(REQ)
        self.assertEqual(seen[0], {"organizations": ["6296"], "dateFrom": "2024-03-01", "dateTo": "2024-03-31"})

    def test_not_found_is_an_empty_page(self):
        c, _ = self.client([(404, {"message": "No contracts found for the given criteria", "status": 404})])
        p = c.search_page(REQ)
        self.assertEqual((p.total, p.records), (0, []))

    def test_other_404_is_an_error(self):
        c, _ = self.client([(404, {"message": "Not Found"})])
        with self.assertRaises(httpx.HTTPStatusError):
            c.search_page(REQ)

    def test_throttling_is_retried(self):
        c, _ = self.client([(429, {}), (200, page([rec()]))])
        self.assertEqual(c.search_page(REQ).total, 1)
        self.assertEqual((c.calls, c.throttled), (2, 1))

    def test_all_pages_are_fetched(self):
        a, b = rec("24SYMV000000001"), rec("24SYMV000000002")
        c, seen = self.client([(200, page([a], total=2, pages=2)), (200, page([b], total=2, number=1, pages=2))])
        self.assertEqual([len(p.records) for p in c.search_all(REQ)], [1, 1])
        self.assertEqual(len(seen), 2)

    def test_unstable_paging_fails(self):
        a = rec("24SYMV000000001")
        c, _ = self.client([(200, page([a], total=2, pages=2)), (200, page([a], total=2, number=1, pages=2))])
        with self.assertRaises(GuardViolation):
            list(c.search_all(REQ))


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RawStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_is_keyed_by_reference(self):
        r = rec()
        first = self.store.put_khmdhs_record("contract", "6296", r)
        self.assertEqual(first.path, Path(self.tmp.name) / "khmdhs" / "records" / "contract" / "6296" / "24SYMV014483573.json")
        self.assertEqual(self.store.put_khmdhs_record("contract", "6296", r).outcome, "unchanged")
        self.assertEqual(self.store.put_khmdhs_record("contract", "6296", {**r, "title": "edited"}).outcome, "changed")

    def test_unsafe_parts_are_refused(self):
        for ep, org, ref in (("contract", "6296", "../x"), ("contract", "6296", "24symv1"), ("../contract", "6296", "24SYMV1234"),
                             ("contract", "62/96", "24SYMV1234"), ("contract", "6296", None)):
            with self.subTest(ep=ep, org=org, ref=ref), self.assertRaises(ValueError):
                self.store.put_khmdhs_record(ep, org, rec(ref=ref))
        self.assertEqual(list(Path(self.tmp.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
