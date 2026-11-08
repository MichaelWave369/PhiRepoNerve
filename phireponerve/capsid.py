"""ΦCAPSID v0.1: locally signed, reviewed, context-only capability capsules.

This module NEVER installs tools, changes model weights, invokes an agent, or
grants execution authority. A capsule is low-trust reference data selected
for an operator-configured agent label, not a verified identity.
"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .chamber import assemble
from .load import IDENTIFIER, VERSION, get_pack, pack_digest
from .welcome import with_charter

SCHEMA = "phi.capsid.manifest.v1"
ENVELOPE_SCHEMA = "phi.capsid.envelope.v1"
PROFILE_SCHEMA = "phi.capsid.agent-profile.v1"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
SIGNATURE = re.compile(r"hmac-sha256:[0-9a-f]{64}\Z")
KEY_ID = re.compile(r"[a-z][a-z0-9_.-]{2,31}\Z")
ALLOWED_CAPABILITIES = frozenset({"reference.read"})
MAX_JSON_BYTES = 65536


class CapsidError(ValueError):
    """Reject malformed, unauthorized, stale, or inapplicable capsules."""


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(ok, reason):
    if not ok:
        raise CapsidError(reason)


def _identifier(value):
    return type(value) is str and IDENTIFIER.fullmatch(value) is not None


def _texts(value, max_items=12):
    return (type(value) is list and len(value) <= max_items
            and all(_identifier(item) for item in value)
            and len(set(value)) == len(value))


def validate_manifest(manifest):
    _require(type(manifest) is dict and set(manifest) == {
        "schema", "id", "version", "title", "description", "target",
        "capabilities", "pack", "provenance",
    }, "Invalid capsule manifest fields")
    _require(manifest["schema"] == SCHEMA, "Unsupported capsule schema")
    _require(_identifier(manifest["id"]), "Invalid capsule ID")
    _require(type(manifest["version"]) is str and
             VERSION.fullmatch(manifest["version"]) is not None,
             "Invalid capsule version")
    for field, limit in (("title", 100), ("description", 350), ("provenance", 300)):
        value = manifest[field]
        _require(type(value) is str and 0 < len(value.strip()) <= limit
                 and "\x00" not in value, "Invalid capsule " + field)
    target = manifest["target"]
    _require(type(target) is dict and set(target) == {
        "roles", "repo_contains", "required_tags"
    }, "Invalid target selector")
    _require(all(_texts(target[field]) for field in target),
             "Invalid target selector values")
    _require(bool(target["roles"] or target["repo_contains"]),
             "Capsules must be scoped to a role or repository")
    capabilities = manifest["capabilities"]
    _require(_texts(capabilities) and capabilities and
             set(capabilities) <= ALLOWED_CAPABILITIES,
             "Unknown or unbounded capability")
    pack = manifest["pack"]
    _require(type(pack) is dict and set(pack) == {"id", "digest"} and
             _identifier(pack["id"]) and type(pack["digest"]) is str and
             DIGEST.fullmatch(pack["digest"]) is not None,
             "Invalid pinned knowledge pack")
    _require(len(_canonical(manifest)) <= MAX_JSON_BYTES,
             "Capsule manifest exceeds size limit")
    return manifest


def validate_profile(profile):
    _require(type(profile) is dict and set(profile) == {
        "schema", "agent_id", "role", "repository", "tags",
        "allowed_capabilities"
    }, "Invalid operator agent profile fields")
    _require(profile["schema"] == PROFILE_SCHEMA and
             _identifier(profile["agent_id"]) and _identifier(profile["role"]),
             "Invalid agent profile")
    repo = profile["repository"]
    _require(type(repo) is str and 3 <= len(repo) <= 160 and
             re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is not None,
             "Invalid repository selector value")
    _require(_texts(profile["tags"]) and _texts(profile["allowed_capabilities"])
             and set(profile["allowed_capabilities"]) <= ALLOWED_CAPABILITIES,
             "Invalid agent tags/capability policy")
    return profile


def _key(secret=None):
    raw = secret if secret is not None else os.environ.get("PHICAPSID_HMAC_KEY", "")
    _require(type(raw) is str and re.fullmatch("[0-9a-fA-F]{64}", raw) is not None,
             "Set PHICAPSID_HMAC_KEY to 32 random bytes encoded as 64 hex characters")
    return bytes.fromhex(raw)


def manifest_digest(manifest):
    return "sha256:" + hashlib.sha256(_canonical(validate_manifest(manifest))).hexdigest()


def _mac(manifest, key_id, key):
    message = b"phi.capsid.v1\x00" + key_id.encode("ascii") + b"\x00" + _canonical(manifest)
    return "hmac-sha256:" + hmac.new(key, message, hashlib.sha256).hexdigest()


def sign_manifest(manifest, key_id="local-v1", secret=None):
    validate_manifest(manifest)
    _require(type(key_id) is str and KEY_ID.fullmatch(key_id) is not None,
             "Invalid signing key ID")
    return {"schema": ENVELOPE_SCHEMA, "key_id": key_id,
            "manifest": manifest, "signature": _mac(manifest, key_id, _key(secret))}


def verify_envelope(envelope, secret=None):
    _require(type(envelope) is dict and set(envelope) == {
        "schema", "key_id", "manifest", "signature"
    }, "Invalid capsule envelope fields")
    _require(envelope["schema"] == ENVELOPE_SCHEMA and
             type(envelope["key_id"]) is str and
             KEY_ID.fullmatch(envelope["key_id"]) is not None,
             "Invalid capsule envelope version/key ID")
    validate_manifest(envelope["manifest"])
    sig = envelope["signature"]
    _require(type(sig) is str and SIGNATURE.fullmatch(sig) is not None,
             "Malformed capsule signature")
    _require(hmac.compare_digest(sig, _mac(envelope["manifest"], envelope["key_id"],
                                           _key(secret))), "Capsule signature failed")
    return envelope["manifest"]


def eligible(envelope, profile, packs, statuses, secret=None):
    """Re-evaluate at stage, activation and context export; fail on revocation."""
    manifest = verify_envelope(envelope, secret)
    validate_profile(profile)
    target = manifest["target"]
    _require(not target["roles"] or profile["role"] in target["roles"],
             "Target role mismatch")
    _require(not target["repo_contains"] or any(
        marker.casefold() in profile["repository"].casefold()
        for marker in target["repo_contains"]), "Target repository mismatch")
    _require(set(target["required_tags"]) <= set(profile["tags"]),
             "Agent lacks required tags")
    _require(set(manifest["capabilities"]) <= set(profile["allowed_capabilities"]),
             "Capability not permitted by local agent profile")
    try:
        pack = get_pack(packs, manifest["pack"]["id"])
    except ValueError as exc:
        raise CapsidError(str(exc)) from exc
    _require(pack_digest(pack) == manifest["pack"]["digest"],
             "Knowledge-pack digest changed")
    _require(statuses.get(pack["id"]) == "approved", "Knowledge pack is not approved")
    return manifest, pack


def read_json(path):
    file = Path(path)
    _require(file.is_file() and not file.is_symlink() and
             0 < file.stat().st_size <= MAX_JSON_BYTES,
             "JSON must be a regular non-empty file under 64 KiB")
    try:
        return json.loads(file.read_text(encoding="utf-8"),
                          parse_constant=lambda n: (_ for _ in ()).throw(ValueError(n)),
                          object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CapsidError("Invalid JSON input") from exc


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON field")
        obj[key] = value
    return obj


class CapsidStore:
    """Private local staging ledger; no cross-host identity or execution grants."""

    def __init__(self, path=None):
        self.path = Path(path).expanduser() if path else (
            Path.home() / ".phireponerve" / "capsid.sqlite3")

    def _connect(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("""
            CREATE TABLE IF NOT EXISTS capsules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                envelope TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN
                    ('staged','active','superseded','rolled_back')),
                created_at TEXT NOT NULL,
                changed_at TEXT NOT NULL
            )
        """)
        db.commit()
        return db

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def stage(self, envelope, profile, packs, statuses, secret=None):
        manifest, _ = eligible(envelope, profile, packs, statuses, secret)
        now = self._now()
        db = self._connect()
        try:
            with db:
                cur = db.execute("""
                    INSERT INTO capsules(agent_id,digest,envelope,state,created_at,changed_at)
                    VALUES (?,?,?,?,?,?)
                """, (profile["agent_id"], manifest_digest(manifest),
                      _canonical(envelope).decode("utf-8"), "staged", now, now))
            return {"stage_id": cur.lastrowid, "agent_id": profile["agent_id"],
                    "capsule": manifest["id"], "state": "staged",
                    "execution_authorized": False}
        finally:
            db.close()

    def activate(self, stage_id, profile, packs, statuses, secret=None):
        validate_profile(profile)
        _require(type(stage_id) is int and stage_id > 0, "Invalid stage ID")
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM capsules WHERE id=?", (stage_id,)).fetchone()
            _require(row is not None and row["agent_id"] == profile["agent_id"] and
                     row["state"] == "staged", "Stage not available for this agent")
            manifest, _ = eligible(json.loads(row["envelope"]), profile, packs,
                                   statuses, secret)
            _require(row["digest"] == manifest_digest(manifest), "Staged capsule drift")
            now = self._now()
            db.execute("""UPDATE capsules SET state='superseded', changed_at=?
                          WHERE agent_id=? AND state='active'""",
                       (now, profile["agent_id"]))
            db.execute("UPDATE capsules SET state='active', changed_at=? WHERE id=?",
                       (now, stage_id))
            db.commit()
            return {"stage_id": stage_id, "agent_id": profile["agent_id"],
                    "capsule": manifest["id"], "state": "active_context_only",
                    "execution_authorized": False}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def rollback(self, agent_id):
        _require(_identifier(agent_id), "Invalid agent ID")
        db = self._connect()
        try:
            with db:
                changed = db.execute("""
                    UPDATE capsules SET state='rolled_back', changed_at=?
                    WHERE agent_id=? AND state='active'
                """, (self._now(), agent_id)).rowcount
            return {"agent_id": agent_id, "rolled_back": changed == 1,
                    "state": "baseline_no_capsule",
                    "restored_prior_version": False}
        finally:
            db.close()

    def history(self, agent_id):
        _require(_identifier(agent_id), "Invalid agent ID")
        db = self._connect()
        try:
            return [{k: row[k] for k in (
                "id", "agent_id", "digest", "state", "created_at", "changed_at"
            )} for row in db.execute("""
                SELECT id,agent_id,digest,state,created_at,changed_at
                FROM capsules WHERE agent_id=? ORDER BY id DESC LIMIT 100
            """, (agent_id,))]
        finally:
            db.close()

    def context(self, profile, packs, statuses, secret=None):
        validate_profile(profile)
        db = self._connect()
        try:
            rows = db.execute("""
                SELECT * FROM capsules WHERE agent_id=? AND state='active'
            """, (profile["agent_id"],)).fetchall()
        finally:
            db.close()
        _require(len(rows) == 1, "Expected exactly one active capsule")
        row = rows[0]
        manifest, pack = eligible(json.loads(row["envelope"]), profile,
                                  packs, statuses, secret)
        _require(row["digest"] == manifest_digest(manifest), "Active capsule drift")
        # The existing Chamber supplies the application-authored Welcome Charter.
        bundle = assemble(packs, statuses, [pack["id"]])
        return {**bundle, "capsid": {
            "id": manifest["id"], "version": manifest["version"],
            "manifest_digest": row["digest"], "stage_id": row["id"],
            "agent_label": profile["agent_id"], "target_repo": profile["repository"],
            "declared_capabilities": list(manifest["capabilities"]),
            "source_authenticated": False, "agent_identity_verified": False,
            "tool_permissions_granted": False, "model_weights_modified": False,
            "execution_authorized": False, "dispatch_authorized": False,
            "merge_authorized": False, "deployment_authorized": False,
        }}
