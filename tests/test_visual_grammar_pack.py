"""The PhiAtelier knowledge pack is curated input, never implicit authorization."""
import unittest

from phireponerve.load import get_pack, read_packs, validate_pack
from phireponerve.review import ReviewStore
import tempfile
from pathlib import Path


class VisualGrammarPackTests(unittest.TestCase):
    def test_builtin_pack_passes_schema_and_keeps_provenance(self):
        pack = get_pack(read_packs(), "create.visual-grammar")
        self.assertEqual(validate_pack(pack)["id"], "create.visual-grammar")
        self.assertIn("mfa.org", pack["provenance"])
        self.assertIn("thedali.org", pack["provenance"])
        self.assertIn("moma.org", pack["provenance"])
        self.assertGreaterEqual(len(pack["knowledge"]), 8)

    def test_new_pack_is_unreviewed_by_default(self):
        pack = get_pack(read_packs(), "create.visual-grammar")
        with tempfile.TemporaryDirectory() as path:
            store = ReviewStore(Path(path) / "reviews.sqlite3")
            self.assertEqual(store.status_map([pack])[pack["id"]], "unreviewed")
            self.assertFalse((Path(path) / "reviews.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
