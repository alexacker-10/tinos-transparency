"""Act documents enter data/raw only as PDFs, byte for byte, and never overwrite."""

import tempfile
import unittest
from pathlib import Path

import httpx

from tinos.config import Settings
from tinos.sources.diavgeia import DiavgeiaClient
from tinos.store import RawStore

ADA = "Ω25ΙΩΗ6-ΟΜΘ"
PDF = b"%PDF-1.7\nnot a real document\n%%EOF\n"


class DocStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = RawStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_then_unchanged_then_changed_sibling(self):
        first = self.store.put_diavgeia_doc("6296", ADA, PDF)
        self.assertEqual(first.outcome, "new")
        self.assertEqual(first.path, self.root / "diavgeia" / "docs" / "6296" / f"{ADA}.pdf")
        self.assertEqual(self.store.put_diavgeia_doc("6296", ADA, PDF).outcome, "unchanged")
        changed = self.store.put_diavgeia_doc("6296", ADA, PDF + b"re-issued")
        self.assertEqual(changed.outcome, "changed")
        self.assertNotEqual(changed.path, first.path)
        self.assertEqual(changed.path.suffix, ".pdf")
        self.assertEqual(first.path.read_bytes(), PDF)  # the first capture is never touched

    def test_unsafe_ada_is_refused(self):
        for ada in ("../../outside", "Ω25/ΙΩΗ6-ΟΜΘ", "", None):
            with self.subTest(ada=ada), self.assertRaises(ValueError):
                self.store.put_diavgeia_doc("6296", ada, PDF)
        self.assertEqual(list(self.root.rglob("*")), [])

    def test_find_act_only_among_stored_acts(self):
        path = self.store.diavgeia_act_path("6296", ADA)
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.store.find_diavgeia_act(ADA), path)
        self.assertIsNone(self.store.find_diavgeia_act("ΩΩΩΩΩΩ6-ΩΩΩ"))
        with self.assertRaises(ValueError):
            self.store.find_diavgeia_act("*")


class DocumentFetch(unittest.TestCase):
    def client(self, body: bytes, ctype: str):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, content=body, headers={"content-type": ctype})

        c = DiavgeiaClient(Settings(root=Path("."), request_delay=0))
        c._http.close()
        c._http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
        self.addCleanup(c.close)
        return c, seen

    def test_pdf_is_returned_verbatim(self):
        c, seen = self.client(PDF, "application/pdf")
        data, meta = c.document(ADA)
        self.assertEqual(data, PDF)
        self.assertEqual(meta["bytes"], len(PDF))
        self.assertEqual(seen[0].url.path, f"/doc/{ADA}")

    def test_non_pdf_is_refused(self):
        c, _ = self.client(b"<html>not found</html>", "text/html")
        with self.assertRaises(ValueError):
            c.document(ADA)

    def test_unsafe_ada_never_reaches_the_network(self):
        c, seen = self.client(PDF, "application/pdf")
        with self.assertRaises(ValueError):
            c.document("../opendata/search")
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
