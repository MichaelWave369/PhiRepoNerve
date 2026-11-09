"""Explicit, local-only public handoff for FieldConstellation.

The exported file contains public GitHub IDs and two bounded observations only.
No names, URLs, descriptions, events, tokens, private counts or raw SQLite rows.
This is a last-scan observation, NOT live availability, CI or deployment evidence.
"""

from datetime import datetime, timezone


SCHEMA_VERSION = 1
OWNER = "MichaelWave369"


class PublicHandoffError(ValueError):
    """A public export cannot safely be derived from the current ledger."""


def _valid_timestamp(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


def public_handoff(store, owner=OWNER):
    """Project only the last COMPLETE owner's public, currently-visible IDs.

    The repository table can contain multiple owners over time, so both the
    latest scan owner and each repository's full_name prefix are constrained.
    A newer failed scan blocks export until a fresh complete observation.
    """
    if owner != OWNER:
        raise PublicHandoffError("Only the explicitly supported public owner may be exported")
    with store.connection() as conn:
        last = conn.execute(
            "SELECT id,owner,observed_at,status FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not last or last["status"] != "complete" or last["owner"] != owner:
            raise PublicHandoffError("A latest complete scan for this owner is required")
        if not _valid_timestamp(last["observed_at"]):
            raise PublicHandoffError("Last scan timestamp is invalid")

        rows = conn.execute(
            """SELECT github_id,pushed_at,archived FROM repos
               WHERE present=1 AND private=0 AND substr(full_name,1,?)=?
               ORDER BY github_id""",
            (len(owner) + 1, owner + "/"),
        ).fetchall()
        repositories = []
        for row in rows:
            github_id = row["github_id"]
            if not isinstance(github_id, int) or github_id <= 0:
                raise PublicHandoffError("Invalid public repository identity")
            pushed_at = row["pushed_at"] or None
            if pushed_at is not None and not _valid_timestamp(pushed_at):
                raise PublicHandoffError("Invalid public push observation timestamp")
            repositories.append({
                "id": str(github_id),
                "pushedAt": pushed_at,
                "archived": bool(row["archived"]),
            })
        if len(repositories) > 10000:
            raise PublicHandoffError("Unbounded public inventory refused")

        return {
            "schemaVersion": SCHEMA_VERSION,
            "source": "PhiRepoNerve",
            "scope": "public-ids-only",
            "owner": owner,
            "observedAt": last["observed_at"],
            "repositories": repositories,
        }
