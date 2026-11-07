"""Offline ΦLoad/ΦSect contract tests; no model calls and no network access."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from phireponerve.cli import main
from phireponerve.load import PackError, catalogue, get_pack, read_packs, validate_pack
from phireponerve.sect import build_flashes, matches
from phireponerve.store import FleetStore


def pack(identifier="core.triage"):
    return {
        "schema_version": 1, "id": identifier, "version": "0.1.0",
        "title": "Evidence triage", "description": "Check evidence before making claims",
        "events": ["push_activity_observed", "first_observed"],
        "repo_contains": ["PhiOS"], "knowledge": ["A push is not proof of a passing build."],
        "provenance": "docs/ARCHITECTURE.md",
    }


def event(name="MichaelWave369/PhiOS"):
    return {
        "id": 23, "scan_id": 9, "github_id": 369, "full_name": name,
        "event_type": "push_activity_observed", "observed_at": "2026-11-07T12:00:00Z",
    }


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name="one.json", value=None):
        path = self.root / name
        path.write_text(json.dumps(value or pack()), encoding="utf-8")
        return path

    def test_builtin_pack_catalogue_is_available(self):
        items = read_packs()
        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(len(catalogue(items)), len(items))
        self.assertNotIn("knowledge", catalogue(items)[0])
        self.assertTrue(get_pack(items, items[0]["id"])["knowledge"])

    def test_valid_catalogue_explicit_load(self):
        self.write()
        items = read_packs(self.root)
        self.assertEqual(items[0]["id"], "core.triage")
        self.assertEqual(get_pack(items, "core.triage")["version"], "0.1.0")
        with self.assertRaises(PackError):
            get_pack(items, "missing")

    def test_schema_and_triggers_rejected(self):
        bad = pack()
        bad["events"] = ["unknown_event"]
        with self.assertRaises(PackError):
            validate_pack(bad)
        bad = pack()
        bad["schema_version"] = True
        with self.assertRaises(PackError):
            validate_pack(bad)
        bad = pack()
        bad["knowledge"] = []
        with self.assertRaises(PackError):
            validate_pack(bad)

    def test_oversized_duplicate_and_symlink_rejected(self):
        self.write()
        self.write("two.json")
        with self.assertRaisesRegex(PackError, "Duplicate"):
            read_packs(self.root)
        (self.root / "two.json").unlink()
        (self.root / "large.json").write_bytes(b"x" * 65537)
        with self.assertRaisesRegex(PackError, "Oversized"):
            read_packs(self.root)
        (self.root / "large.json").unlink()
        try:
            (self.root / "link.json").symlink_to(self.root / "one.json")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported")
        with self.assertRaisesRegex(PackError, "symlink"):
            read_packs(self.root)


class SectTests(unittest.TestCase):
    def test_match_uses_declared_event_and_repository_name(self):
        p = pack()
        self.assertTrue(matches(event(), p))
        self.assertFalse(matches(event("MichaelWave369/Other"), p))
        self.assertFalse(matches({**event(), "event_type": "no_longer_visible"}, p))

    def test_flash_is_grounded_candidate_and_not_execution(self):
        result = build_flashes([event()], [pack()])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["evidence"]["event_id"], 23)
        self.assertEqual(result[0]["status"], "candidate_unverified")
        self.assertFalse(result[0]["automatic_action"])
        self.assertNotIn("knowledge", result[0]["pack"])

    def test_limit_is_bounded(self):
        flashes = build_flashes([event(), {**event(), "id": 24}], [pack()], limit=1)
        self.assertEqual(len(flashes), 1)
        with self.assertRaises(ValueError):
            build_flashes([], [], limit=0)

    def test_cli_load_and_sect_against_local_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.json").write_text(json.dumps(pack()), encoding="utf-8")
            db = root / "fleet.sqlite3"
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(["load", "--packs", str(root), "--pack", "core.triage"]), 0)
            self.assertEqual(json.loads(stdout.getvalue())["id"], "core.triage")
            store = FleetStore(db)
            store.record_complete("MichaelWave369", [{
                "github_id": 369, "full_name": "MichaelWave369/PhiOS",
                "private": False, "archived": False, "default_branch": "main",
                "pushed_at": "2026-11-07T12:00:00Z", "description": "",
                "html_url": "https://github.com/MichaelWave369/PhiOS",
            }])
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(["--db", str(db), "sect", "--packs", str(root)]), 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(len(result["flashes"]), 1)
            self.assertEqual(result["flashes"][0]["evidence"]["event_type"], "first_observed")


if __name__ == "__main__":
    unittest.main()
