"""Offline deterministic regression tests. Tests never call live GitHub."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from phireponerve.cli import scan_once
from phireponerve.github import GitHubClient, InventoryError
from phireponerve.store import FleetStore


def repo(number, name=None, private=False, archived=False, pushed="2026-11-07T10:00:00Z"):
    slug = name or "repo-" + str(number)
    return {
        "id": number,
        "name": slug,
        "full_name": "MichaelWave369/" + slug,
        "owner": {"login": "MichaelWave369"},
        "private": private,
        "archived": archived,
        "default_branch": "main",
        "pushed_at": pushed,
        "description": "Test project",
        "html_url": "https://github.com/MichaelWave369/" + slug,
    }


class Response(io.BytesIO):
    def __init__(self, value, link=""):
        super().__init__(json.dumps(value).encode("utf-8"))
        self.status = 200
        self.headers = {"Link": link}


class FakeGitHub:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, req, timeout):
        self.calls.append(req.full_url)
        parsed = urlparse(req.full_url)
        index = int(parse_qs(parsed.query).get("page", [1])[0])
        return Response(self.pages.get(index, []))


class InventoryTests(unittest.TestCase):
    def test_full_page_requires_next_page_even_without_link_header(self):
        opener = FakeGitHub({1: [repo(n) for n in range(100)], 2: [repo(100), repo(101)]})
        items = GitHubClient(token="", opener=opener).inventory("MichaelWave369")
        self.assertEqual(len(items), 102)
        self.assertEqual(len(opener.calls), 2)
        self.assertIn("/users/MichaelWave369/repos", opener.calls[0])

    def test_auth_inventory_includes_private_repo(self):
        opener = FakeGitHub({1: [repo(1, private=True)]})
        items = GitHubClient(token="sample-not-a-real-token", opener=opener).inventory("MichaelWave369")
        self.assertTrue(items[0]["private"])
        self.assertIn("/user/repos", opener.calls[0])

    def test_duplicate_id_refuses_inconsistent_listing(self):
        first = [repo(n) for n in range(100)]
        opener = FakeGitHub({1: first, 2: [repo(1)]})
        with self.assertRaisesRegex(InventoryError, "Duplicate"):
            GitHubClient(token="", opener=opener).inventory("MichaelWave369")

    def test_http_failure_is_never_silent_partial_success(self):
        def broken(req, timeout):
            raise HTTPError(req.full_url, 403, "rate limited", {}, None)
        with self.assertRaisesRegex(InventoryError, "403"):
            GitHubClient(token="", opener=broken).inventory("MichaelWave369")

    def test_foreign_pagination_link_is_rejected(self):
        def foreign(req, timeout):
            return Response([repo(1)], '<https://attacker.example/steal>; rel="next"')
        with self.assertRaisesRegex(InventoryError, "Unsafe pagination"):
            GitHubClient(token="secret", opener=foreign).inventory("MichaelWave369")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "fleet.sqlite3")
        self.store = FleetStore(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_initial_idempotence_and_rename(self):
        data = [GitHubClient._normalize(repo(1), "MichaelWave369")]
        self.assertEqual(self.store.record_complete("MichaelWave369", data)["new_events"], 1)
        self.assertEqual(self.store.record_complete("MichaelWave369", data)["new_events"], 0)
        updated = [GitHubClient._normalize(repo(1, "renamed-repo", archived=True), "MichaelWave369")]
        self.assertEqual(self.store.record_complete("MichaelWave369", updated)["new_events"], 2)
        kinds = {event["event_type"] for event in self.store.events()}
        self.assertEqual(kinds, {"first_observed", "renamed", "archival_changed"})
        self.assertEqual(self.store.repositories()[0]["full_name"], "MichaelWave369/renamed-repo")

    def test_failure_preserves_inventory_and_no_false_deletions(self):
        data = [GitHubClient._normalize(repo(1), "MichaelWave369")]
        self.store.record_complete("MichaelWave369", data)
        self.store.record_failure("MichaelWave369", "HTTP 403")
        self.assertEqual(self.store.summary()["active_repositories"], 1)
        self.assertEqual(self.store.summary()["latest_attempt"]["status"], "failed")
        self.assertEqual(self.store.summary()["latest_complete"]["status"], "complete")
        self.assertFalse(any(e["event_type"] == "no_longer_visible" for e in self.store.events()))

    def test_reappearance_does_not_claim_deletion(self):
        data = [GitHubClient._normalize(repo(1), "MichaelWave369")]
        self.store.record_complete("MichaelWave369", data)
        self.store.record_complete("MichaelWave369", [])
        self.assertEqual(self.store.summary()["no_longer_visible"], 1)
        self.store.record_complete("MichaelWave369", data)
        kinds = [e["event_type"] for e in self.store.events()]
        self.assertIn("no_longer_visible", kinds)
        self.assertIn("visible_again", kinds)
        self.assertEqual(self.store.summary()["active_repositories"], 1)

    def test_scan_once_records_failure_without_touching_existing_repos(self):
        self.store.record_complete("MichaelWave369",
                                   [GitHubClient._normalize(repo(1), "MichaelWave369")])

        class BrokenClient:
            def inventory(self, owner):
                raise InventoryError("HTTP 500")

        with self.assertRaises(InventoryError):
            scan_once("MichaelWave369", self.db, client=BrokenClient())
        self.assertEqual(self.store.summary()["active_repositories"], 1)
        self.assertEqual(self.store.summary()["latest_attempt"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
