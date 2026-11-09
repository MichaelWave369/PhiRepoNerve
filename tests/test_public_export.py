"""Privacy and completeness gates for the explicitly requested public handoff."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from phireponerve.cli import main
from phireponerve.public_export import PublicHandoffError, public_handoff
from phireponerve.store import FleetStore


def record(github_id, name, private=False):
    return {
        "github_id": github_id,
        "full_name": name,
        "private": private,
        "archived": False,
        "default_branch": "main",
        "pushed_at": "2026-11-08T20:00:00Z",
        "description": "SENSITIVE DESCRIPTION NEVER EXPORTED",
        "html_url": "https://github.com/" + name,
    }


class PublicExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite3"
        self.store = FleetStore(self.path)

    def test_private_repositories_and_names_never_leak(self):
        self.store.record_complete("MichaelWave369", [
            record(101, "MichaelWave369/PublicOne"),
            record(102, "MichaelWave369/SecretProject", private=True),
            record(103, "AnotherOwner/OtherPublic"),
        ])
        payload = public_handoff(self.store)
        self.assertEqual([x["id"] for x in payload["repositories"]], ["101"])
        serialized = json.dumps(payload)
        for private_value in ("SecretProject", "102", "PublicOne", "SENSITIVE DESCRIPTION",
                              "AnotherOwner", "OtherPublic", "html_url"):
            self.assertNotIn(private_value, serialized)

    def test_missing_or_failed_latest_scan_blocks_export(self):
        with self.assertRaises(PublicHandoffError):
            public_handoff(self.store)
        self.store.record_complete("MichaelWave369", [record(101, "MichaelWave369/Open")])
        self.store.record_failure("MichaelWave369", "network failed")
        with self.assertRaises(PublicHandoffError):
            public_handoff(self.store)

    def test_other_owner_or_last_scan_owner_is_refused(self):
        self.store.record_complete("OtherOwner", [record(101, "OtherOwner/Project")])
        with self.assertRaises(PublicHandoffError):
            public_handoff(self.store)
        with self.assertRaises(PublicHandoffError):
            public_handoff(self.store, owner="OtherOwner")

    def test_cli_writes_private_mode_and_rejects_existing_file(self):
        self.store.record_complete("MichaelWave369", [
            record(101, "MichaelWave369/PublicOne"),
            record(102, "MichaelWave369/Hidden", private=True)
        ])
        output = Path(self.temp.name) / "public-handoff.json"
        self.assertEqual(main(["--db", str(self.path), "export-public", "--out", str(output)]), 0)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual([r["id"] for r in payload["repositories"]], ["101"])
        if os.name != "nt":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            main(["--db", str(self.path), "export-public", "--out", str(output)])


if __name__ == "__main__":
    unittest.main()
