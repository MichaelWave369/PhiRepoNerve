"""Explicit local ΦLoad review ledger, separate from read-only fleet observation.

Digest pinning detects content changes; the hash chain detects accidental ledger
edits. Neither establishes reviewer identity or withstands a hostile local admin.
"""
import getpass
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .load import pack_digest

ZERO_HASH = "0" * 64


class ReviewError(ValueError):
    """An invalid review action or inconsistent ledger."""


def entry_hash(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ReviewStore:
    """Human-reviewed states for exact (pack ID, semantic version, SHA256 digest)."""

    def __init__(self, path=None):
        self.path = Path(path).expanduser() if path else (
            Path.home() / ".phireponerve" / "pack_reviews.sqlite3"
        )

    def _connect(self, create=False):
        if not create and not self.path.is_file():
            return None
        if create:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        if create:
            db.execute("""
              CREATE TABLE IF NOT EXISTS pack_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id TEXT NOT NULL, pack_version TEXT NOT NULL,
                digest TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('approved', 'revoked')),
                reviewer TEXT NOT NULL, reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
              )
            """)
            db.commit()
        return db

    @staticmethod
    def _read_checked(db):
        if db is None:
            return [], ZERO_HASH
        try:
            records = [dict(row) for row in db.execute(
                "SELECT * FROM pack_reviews ORDER BY id ASC"
            )]
        except sqlite3.DatabaseError as exc:
            raise ReviewError("Review ledger cannot be read") from exc
        head = ZERO_HASH
        last_id = 0
        for row in records:
            fields = {k: row[k] for k in (
                "pack_id", "pack_version", "digest", "decision",
                "reviewer", "reason", "created_at", "previous_hash"
            )}
            if (row["id"] != last_id + 1
                    or fields["decision"] not in ("approved", "revoked")
                    or fields["previous_hash"] != head
                    or entry_hash(fields) != row["entry_hash"]):
                raise ReviewError("Review ledger integrity validation failed")
            head = row["entry_hash"]
            last_id = row["id"]
        return records, head

    def verify(self):
        db = self._connect()
        if db is None:
            return {"valid": True, "entries": 0, "head": ZERO_HASH}
        try:
            records, head = self._read_checked(db)
            return {"valid": True, "entries": len(records), "head": head}
        finally:
            db.close()

    def status_map(self, packs):
        db = self._connect()
        if db is None:
            return {p["id"]: "unreviewed" for p in packs}
        try:
            records, _ = self._read_checked(db)
        finally:
            db.close()
        latest = {
            (r["pack_id"], r["pack_version"], r["digest"]): r["decision"]
            for r in records
        }
        return {
            p["id"]: latest.get(
                (p["id"], p["version"], pack_digest(p)), "unreviewed"
            ) for p in packs
        }

    def history(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ReviewError("History limit must be 1-200")
        db = self._connect()
        if db is None:
            return []
        try:
            rows, _ = self._read_checked(db)
            return list(reversed(rows))[:limit]
        finally:
            db.close()

    def record(self, pack, decision, reason):
        """Only explicit review invocations append an entry; no auto-promotion."""
        if decision not in ("approved", "revoked"):
            raise ReviewError("Invalid review decision")
        if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 300:
            raise ReviewError("Review reason must be between 8 and 300 characters")
        digest = pack_digest(pack)
        db = self._connect(create=True)
        try:
            db.execute("BEGIN IMMEDIATE")
            _, last = self._read_checked(db)
            payload = {
                "pack_id": pack["id"], "pack_version": pack["version"],
                "digest": digest, "decision": decision,
                "reviewer": "local:" + getpass.getuser()[:100],
                "reason": reason.strip(),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "previous_hash": last,
            }
            rowhash = entry_hash(payload)
            cur = db.execute("""
              INSERT INTO pack_reviews
              (pack_id, pack_version, digest, decision, reviewer,
               reason, created_at, previous_hash, entry_hash)
              VALUES (:pack_id, :pack_version, :digest, :decision, :reviewer,
                      :reason, :created_at, :previous_hash, :entry_hash)
            """, {**payload, "entry_hash": rowhash})
            db.commit()
            return {"id": cur.lastrowid, **payload, "entry_hash": rowhash}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
