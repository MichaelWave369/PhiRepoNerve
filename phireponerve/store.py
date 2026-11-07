"""SQLite fleet ledger. Only a complete enumeration may change visible inventory."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

FIELDS = {
    "full_name": "renamed",
    "private": "visibility_changed",
    "archived": "archival_changed",
    "default_branch": "default_branch_changed",
    "pushed_at": "push_activity_observed",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FleetStore:
    def __init__(self, path):
        self.path = str(Path(path).expanduser())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('complete','failed')),
                    repo_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS repos (
                    github_id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    private INTEGER NOT NULL,
                    archived INTEGER NOT NULL,
                    default_branch TEXT NOT NULL,
                    pushed_at TEXT NOT NULL,
                    description TEXT NOT NULL,
                    html_url TEXT NOT NULL,
                    present INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER NOT NULL REFERENCES scans(id),
                    github_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    before_value TEXT,
                    after_value TEXT,
                    observed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_recent ON events(id DESC);
                CREATE INDEX IF NOT EXISTS idx_repos_present ON repos(present, full_name);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_failure(self, owner, reason):
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO scans (owner,observed_at,status,repo_count,error) VALUES (?,?,?,?,?)",
                (owner, utc_now(), "failed", 0, str(reason)[:300]),
            )

    def record_complete(self, owner, records):
        when = utc_now()
        new_by_id = {record["github_id"]: record for record in records}
        if len(new_by_id) != len(records):
            raise ValueError("Input inventory contains duplicate repository IDs")
        with self.connection() as conn:
            previous = {
                row["github_id"]: dict(row)
                for row in conn.execute("SELECT * FROM repos").fetchall()
            }
            cur = conn.execute(
                "INSERT INTO scans (owner,observed_at,status,repo_count) VALUES (?,?,?,?)",
                (owner, when, "complete", len(records)),
            )
            scan_id = cur.lastrowid
            changes = 0

            def event(repo_id, name, kind, before=None, after=None):
                nonlocal changes
                conn.execute(
                    """INSERT INTO events
                       (scan_id,github_id,full_name,event_type,before_value,after_value,observed_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (scan_id, repo_id, name, kind,
                     None if before is None else str(before),
                     None if after is None else str(after), when),
                )
                changes += 1

            for record in records:
                repo_id = record["github_id"]
                before = previous.get(repo_id)
                if before is None:
                    event(repo_id, record["full_name"], "first_observed")
                elif not before["present"]:
                    event(repo_id, record["full_name"], "visible_again")
                if before and before["present"]:
                    for field, kind in FIELDS.items():
                        old_value = before[field]
                        new_value = int(record[field]) if field in ("private", "archived") else record[field]
                        if old_value != new_value:
                            event(repo_id, record["full_name"], kind, old_value, new_value)

                conn.execute(
                    """INSERT INTO repos
                       (github_id,full_name,private,archived,default_branch,pushed_at,
                        description,html_url,present,first_seen_at,last_seen_at)
                       VALUES (?,?,?,?,?,?,?,?,1,?,?)
                       ON CONFLICT(github_id) DO UPDATE SET
                         full_name=excluded.full_name, private=excluded.private,
                         archived=excluded.archived, default_branch=excluded.default_branch,
                         pushed_at=excluded.pushed_at, description=excluded.description,
                         html_url=excluded.html_url, present=1,
                         last_seen_at=excluded.last_seen_at""",
                    (repo_id, record["full_name"], int(record["private"]), int(record["archived"]),
                     record["default_branch"], record["pushed_at"], record["description"],
                     record["html_url"], when, when),
                )

            for repo_id, old in previous.items():
                if old["present"] and repo_id not in new_by_id:
                    event(repo_id, old["full_name"], "no_longer_visible")
                    conn.execute("UPDATE repos SET present=0 WHERE github_id=?", (repo_id,))
        return {"scan_id": scan_id, "repo_count": len(records), "new_events": changes,
                "observed_at": when, "status": "complete"}

    def summary(self):
        with self.connection() as conn:
            query = lambda sql: conn.execute(sql).fetchone()[0]
            latest = conn.execute(
                "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
            complete = conn.execute(
                "SELECT * FROM scans WHERE status='complete' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return {
                "active_repositories": query("SELECT COUNT(*) FROM repos WHERE present=1"),
                "private_repositories": query("SELECT COUNT(*) FROM repos WHERE present=1 AND private=1"),
                "archived_repositories": query("SELECT COUNT(*) FROM repos WHERE present=1 AND archived=1"),
                "no_longer_visible": query("SELECT COUNT(*) FROM repos WHERE present=0"),
                "recorded_events": query("SELECT COUNT(*) FROM events"),
                "latest_attempt": dict(latest) if latest else None,
                "latest_complete": dict(complete) if complete else None,
            }

    def repositories(self, limit=100, offset=0, query=""):
        with self.connection() as conn:
            sql = "SELECT * FROM repos WHERE present=1"
            args = []
            if query:
                sql += " AND (full_name LIKE ? OR description LIKE ?)"
                args.extend(["%" + query + "%", "%" + query + "%"])
            sql += " ORDER BY full_name COLLATE NOCASE LIMIT ? OFFSET ?"
            args.extend([limit, offset])
            return [dict(row) for row in conn.execute(sql, args).fetchall()]

    def events(self, limit=100, offset=0):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()]
