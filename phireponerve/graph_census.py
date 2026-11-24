"""Offline aggregate census of the existing public relationship ledger."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from .public_export import OWNER, _valid_timestamp

KINDS = {"code-bridge", "navigation", "shared-library", "documented-integration"}
GRADES = {"verified", "documented"}
ID = re.compile(r"[1-9][0-9]{0,19}")
PIN = re.compile(r"https://github\.com/MichaelWave369/[A-Za-z0-9_.-]+/blob/[0-9a-f]{40}/[^\s?#]+(?:#L[1-9][0-9]*(?:-L[1-9][0-9]*)?)?")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact(value, keys):
    return isinstance(value, dict) and set(value) == set(keys.split())


def census(inventory, ledger):
    """Validate local inputs; produce aggregate observations only, never grants."""
    require(exact(inventory, "schemaVersion source scope owner observedAt repositories")
            and type(inventory["schemaVersion"]) is int and inventory["schemaVersion"] == 1
            and inventory["owner"] == OWNER and inventory["source"] == "PhiRepoNerve"
            and inventory["scope"] == "public-ids-only"
            and _valid_timestamp(inventory["observedAt"]), "Invalid public handoff")
    rows = inventory["repositories"]
    require(isinstance(rows, list) and len(rows) <= 10000, "Invalid inventory size")
    nodes = set()
    for row in rows:
        require(exact(row, "id pushedAt archived") and isinstance(row["id"], str)
                and ID.fullmatch(row["id"]) and type(row["archived"]) is bool
                and (row["pushedAt"] is None or _valid_timestamp(row["pushedAt"])),
                "Invalid public inventory row")
        node = "github:" + row["id"]
        require(node not in nodes, "Duplicate public ID")
        nodes.add(node)

    require(exact(ledger, "schemaVersion owner reviewedAt coverage relationships")
            and type(ledger["schemaVersion"]) is int and ledger["schemaVersion"] == 1
            and ledger["owner"] == OWNER and _valid_timestamp(ledger["reviewedAt"])
            and isinstance(ledger["coverage"], str), "Invalid relationship ledger")
    relationships = ledger["relationships"]
    require(isinstance(relationships, list) and len(relationships) <= 50000,
            "Invalid relationship count")
    record_ids, relation_keys, pairs = set(), set(), set()
    grades, kinds = Counter(), Counter()
    for edge in relationships:
        require(exact(edge, "id from to status kind direction summary scope evidence reviewedAt"),
                "Invalid relationship fields")
        require(all(isinstance(edge[k], str) and edge[k] for k in
                    ("id", "from", "to", "status", "kind", "direction", "summary", "scope"))
                and _valid_timestamp(edge["reviewedAt"]), "Invalid relationship value")
        a, b = edge["from"], edge["to"]
        require(a in nodes and b in nodes and a != b, "Unknown/nonpublic endpoint or self edge")
        require(edge["id"] not in record_ids, "Duplicate relationship ID")
        record_ids.add(edge["id"])
        require(edge["status"] in GRADES and edge["kind"] in KINDS
                and edge["direction"] in {"directed", "undirected"}, "Unknown relationship type")
        pair = tuple(sorted((a, b)))
        key = (pair if edge["direction"] == "undirected" else (a, b),
               edge["kind"], edge["direction"])
        require(key not in relation_keys, "Duplicate relationship")
        relation_keys.add(key)
        evidence = edge["evidence"]
        require(isinstance(evidence, list) and 1 <= len(evidence) <= 64,
                "Missing or excessive evidence")
        for item in evidence:
            require(exact(item, "url claim") and isinstance(item["url"], str)
                    and PIN.fullmatch(item["url"]) and isinstance(item["claim"], str)
                    and bool(item["claim"].strip()), "Unpinned or malformed source evidence")
        pairs.add(pair)
        grades[edge["status"]] += 1
        kinds[edge["kind"]] += 1

    neighbors = {n: set() for n in nodes}
    for a, b in pairs:
        neighbors[a].add(b)
        neighbors[b].add(a)
    unseen = set(nodes)
    components = []
    while unseen:
        root = unseen.pop()
        stack, size = [root], 0
        while stack:
            node = stack.pop()
            size += 1
            fresh = neighbors[node] & unseen
            unseen.difference_update(fresh)
            stack.extend(fresh)
        components.append(size)
    n = len(nodes)
    maximum = n * (n - 1) // 2
    return {
        "schema": "phireponerve.graph-census.v1",
        "authority": "NONE",
        "scope": "LOCAL_PUBLIC_LEDGER_OBSERVATION",
        "inventory_observed_at": inventory["observedAt"],
        "ledger_reviewed_at": ledger["reviewedAt"],
        "nodes": n,
        "relationship_records": len(relationships),
        "unique_undirected_pairs": len(pairs),
        "possible_undirected_pairs": maximum,
        "recorded_pair_density": len(pairs) / maximum if maximum else None,
        "mean_recorded_degree": 2 * len(pairs) / n if n else None,
        "nodes_without_recorded_edges": sum(not v for v in neighbors.values()),
        "weak_component_count": len(components),
        "largest_weak_component": max(components, default=0),
        "by_reported_grade": dict(sorted(grades.items())),
        "by_kind": dict(sorted(kinds.items())),
        "limitations": [
            "Input assertions and commit pin syntax are validated, not independently authenticated.",
            "Missing records mean unknown, not absent dependencies.",
            "Weak connectivity ignores direction and mixes relationship kinds; not runtime reachability.",
            "No execution, installation, integration, or routing authority."
        ],
    }


def read_json(path):
    with Path(path).open("rb") as handle:
        data = handle.read(16 * 1024 * 1024 + 1)
    require(len(data) <= 16 * 1024 * 1024, "Input exceeds size limit")
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=no_duplicates)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--relationships", required=True)
    args = parser.parse_args(argv)
    try:
        report = census(read_json(args.inventory), read_json(args.relationships))
    except (ValueError, OSError, RecursionError) as exc:
        parser.exit(2, "Graph census refused invalid or unreadable input.\n")
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
