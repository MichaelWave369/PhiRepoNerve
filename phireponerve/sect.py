"""ΦSect: deterministic evidence-linked candidate flashes, no autonomous execution."""

from .load import KNOWN_EVENTS, pack_digest


def matches(event, pack):
    """Event metadata can suggest a pack; it cannot prove a repair or capability."""
    kind = event.get("event_type")
    name = event.get("full_name")
    if kind not in KNOWN_EVENTS or kind not in pack["events"] or not isinstance(name, str):
        return False
    markers = pack["repo_contains"]
    return not markers or any(marker.casefold() in name.casefold() for marker in markers)


def build_flashes(events, packs, limit=100, review_statuses=None):
    """Make bounded, non-executable suggestions tied to recorded event IDs."""
    if not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("Flash limit must be between 1 and 200")
    result = []
    review_statuses = review_statuses or {}
    for event in events:
        for pack in packs:
            if not matches(event, pack):
                continue
            result.append({
                "kind": "knowledge_match",
                "status": "candidate_unverified",
                "automatic_action": False,
                "flash_id": str(event.get("id")) + ":" + pack["id"] + "@" + pack["version"],
                "evidence": {
                    "event_id": event.get("id"),
                    "scan_id": event.get("scan_id"),
                    "github_id": event.get("github_id"),
                    "repo": event.get("full_name"),
                    "event_type": event.get("event_type"),
                    "observed_at": event.get("observed_at"),
                },
                "pack": {
                    "id": pack["id"],
                    "version": pack["version"],
                    "digest": pack_digest(pack),
                    "review_status": review_statuses.get(pack["id"], "unreviewed"),
                    "provenance": pack["provenance"],
                },
                "reason": "Declared event trigger and repository-name filter matched",
                "next_step": "Review evidence and explicitly load the pack before agent use",
            })
            if len(result) >= limit:
                return result
    return result
