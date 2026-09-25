"""The raw store never lets API-supplied identifiers steer a path out of data/raw."""

import tempfile
import unittest
from pathlib import Path

from tinos.store import RawStore


class PathComponents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RawStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_ada_maps_under_raw(self):
        p = self.store.diavgeia_act_path("6296", "Ω25ΙΩΗ6-ΟΜΘ")
        self.assertEqual(p, Path(self.tmp.name) / "diavgeia" / "acts" / "6296" / "Ω25ΙΩΗ6-ΟΜΘ.json")

    def test_unsafe_ada_is_refused(self):
        for ada in ("../../outside", "Ω25/ΙΩΗ6-ΟΜΘ", "Ω25ΙΩΗ6-ΟΜΘ\n", "", None, "ω25ιωη6-ομθ"):
            with self.subTest(ada=ada), self.assertRaises(ValueError):
                self.store.put_diavgeia_act("6296", {"ada": ada})

    def test_unsafe_org_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.diavgeia_act_path("../6296", "Ω25ΙΩΗ6-ΟΜΘ")
        with self.assertRaises(ValueError):
            self.store.diavgeia_page_path("6296/..", "2024-01-01", "2024-05-30", 0, "0" * 64)

    def test_nothing_is_written_for_a_refused_act(self):
        with self.assertRaises(ValueError):
            self.store.put_diavgeia_act("6296", {"ada": "../escape"})
        self.assertEqual(list(Path(self.tmp.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
