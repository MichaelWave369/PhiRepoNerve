"""ΦLoad: strict, read-only, local knowledge-pack catalogue.

Knowledge is data, not trusted agent instructions or executable code.
"""
import hashlib
import json
import re
from pathlib import Path

MAX_PACKS = 128
MAX_BYTES = 65536
KNOWN_EVENTS = frozenset({
    "first_observed", "visible_again", "renamed", "visibility_changed",
    "archival_changed", "default_branch_changed", "push_activity_observed",
    "no_longer_visible",
})
IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{2,79}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
REQUIRED = {
    "schema_version", "id", "version", "title", "description",
    "events", "repo_contains", "knowledge", "provenance",
}


class PackError(ValueError):
    """A pack is malformed, duplicated, unsafe to load, or absent."""


def _text(value, field, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise PackError("Invalid " + field)
    return value


def _list_of_text(value, field, maximum_count, maximum_chars, allow_empty=False):
    if not isinstance(value, list) or len(value) > maximum_count or (not allow_empty and not value):
        raise PackError("Invalid " + field)
    return [_text(item, field, maximum_chars) for item in value]


def validate_pack(pack):
    if not isinstance(pack, dict) or set(pack) != REQUIRED:
        raise PackError("Pack keys do not match schema v1")
    if type(pack["schema_version"]) is not int or pack["schema_version"] != 1:
        raise PackError("Unsupported pack schema")
    if not IDENTIFIER.fullmatch(_text(pack["id"], "id", 80)):
        raise PackError("Invalid pack identifier")
    if not VERSION.fullmatch(_text(pack["version"], "version", 40)):
        raise PackError("Invalid semantic version")
    _text(pack["title"], "title", 100)
    _text(pack["description"], "description", 350)
    events = _list_of_text(pack["events"], "events", 16, 50)
    if len(set(events)) != len(events) or not set(events).issubset(KNOWN_EVENTS):
        raise PackError("Invalid or duplicate event triggers")
    _list_of_text(pack["repo_contains"], "repo_contains", 16, 80, allow_empty=True)
    _list_of_text(pack["knowledge"], "knowledge", 24, 500)
    _text(pack["provenance"], "provenance", 300)
    return pack


def read_packs(directory=None):
    """Read JSON-only manifests from a single directory, never scripts or subfolders."""
    root = Path(directory) if directory is not None else Path(__file__).with_name("packs")
    if not root.is_dir():
        raise PackError("Knowledge-pack directory does not exist")
    files = sorted(root.iterdir())
    if len(files) > MAX_PACKS:
        raise PackError("Too many files in knowledge-pack directory")
    result = []
    seen = set()
    for path in files:
        if path.suffix != ".json":
            continue
        if path.is_symlink() or not path.is_file():
            raise PackError("Knowledge pack must be a regular, non-symlink JSON file")
        if path.stat().st_size > MAX_BYTES:
            raise PackError("Oversized knowledge pack: " + path.name)
        try:
            pack = validate_pack(json.loads(path.read_text(encoding="utf-8")))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PackError("Unreadable knowledge pack: " + path.name) from exc
        if pack["id"] in seen:
            raise PackError("Duplicate knowledge-pack ID: " + pack["id"])
        seen.add(pack["id"])
        result.append(pack)
    return sorted(result, key=lambda p: p["id"])


def catalogue(packs):
    """Expose metadata, withholding full knowledge until a pack is explicitly loaded."""
    return [{
        "id": p["id"], "version": p["version"], "title": p["title"],
        "description": p["description"], "events": p["events"],
        "repo_contains": p["repo_contains"], "provenance": p["provenance"],
        "digest": pack_digest(p),
    } for p in packs]


def get_pack(packs, identifier):
    for pack in packs:
        if pack["id"] == identifier:
            return pack
    raise PackError("Unknown knowledge pack: " + identifier)


def pack_digest(pack):
    """SHA256 of the validated, canonical JSON manifest, regardless of key order."""
    validate_pack(pack)
    raw = json.dumps(pack, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()
