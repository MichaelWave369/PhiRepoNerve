"""Command-line runner. Polling is explicit; read-only API binds loopback."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .github import GitHubClient, InventoryError
from .store import FleetStore


def scan_once(owner, db_path, client=None):
    store = FleetStore(db_path)
    client = client or GitHubClient()
    try:
        inventory = client.inventory(owner)
        return store.record_complete(owner, inventory)
    except (InventoryError, ValueError) as exc:
        store.record_failure(owner, exc)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(prog="phireponerve")
    parser.add_argument("--db", default=str(Path.home() / ".phireponerve" / "fleet.sqlite3"),
                        help="Local SQLite path; no database is ever published")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Perform one complete metadata census")
    scan.add_argument("--owner", default="MichaelWave369")
    watch = sub.add_parser("watch", help="Poll continuously while this process runs")
    watch.add_argument("--owner", default="MichaelWave369")
    watch.add_argument("--interval", type=int, default=600, help="Seconds; minimum 60")
    serve = sub.add_parser("serve", help="Serve loopback-only dashboard/API")
    serve.add_argument("--port", type=int, default=8765)

    load = sub.add_parser("load", help="ΦLoad: list or explicitly retrieve local knowledge packs")
    load.add_argument("--packs", default=None, help="Optional directory of JSON manifests")
    load.add_argument("--pack", default=None, help="Explicit ID of one pack to retrieve")
    load.add_argument("--approved-only", action="store_true", help="Only return approved packs")
    load.add_argument("--reviews-db", default=None, help="Local review ledger path")
    sect = sub.add_parser("sect", help="ΦSect: suggest packs for observed fleet events")
    sect.add_argument("--packs", default=None, help="Optional directory of JSON manifests")
    sect.add_argument("--limit", type=int, default=50, help="Maximum candidate flashes, 1-200")
    sect.add_argument("--approved-only", action="store_true", help="Only match approved packs")
    sect.add_argument("--reviews-db", default=None, help="Local review ledger path")
    reviews = sub.add_parser("reviews", help="Explicit pack review and integrity ledger")
    reviews.add_argument("--packs", default=None, help="Local JSON manifest directory")
    reviews.add_argument("--reviews-db", default=None, help="Local review ledger path")
    actions = reviews.add_subparsers(dest="review_action", required=True)
    actions.add_parser("status", help="List pack review states")
    actions.add_parser("verify", help="Check the local review ledger hash chain")
    history = actions.add_parser("history", help="List recent review decisions")
    history.add_argument("--limit", type=int, default=100)
    for action in ("approve", "revoke"):
        p = actions.add_parser(action, help="Make an explicit human review decision")
        p.add_argument("--pack", required=True)
        p.add_argument("--reason", required=True)
    sub.add_parser("welcome", help="Print the trusted, versioned Φ Welcome Charter")

    args = parser.parse_args(argv)
    if args.command == "welcome":
        from .welcome import welcome_charter
        print(json.dumps(welcome_charter(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "reviews":
        from .load import PackError, catalogue, get_pack, read_packs
        from .review import ReviewError, ReviewStore
        from .welcome import with_charter
        store = ReviewStore(args.reviews_db)
        try:
            if args.review_action == "verify":
                output = store.verify()
            elif args.review_action == "history":
                output = {"history": store.history(args.limit)}
            else:
                packs = read_packs(args.packs)
                if args.review_action == "status":
                    states = store.status_map(packs)
                    output = {"packs": [
                        {**p, "review_status": states[p["id"]]}
                        for p in catalogue(packs)
                    ]}
                else:
                    selected = get_pack(packs, args.pack)
                    decision = "approved" if args.review_action == "approve" else "revoked"
                    output = {"review": store.record(selected, decision, args.reason)}
        except (PackError, ReviewError) as exc:
            parser.error(str(exc))
        print(json.dumps(with_charter(output), indent=2, ensure_ascii=False))
        return 0
    if args.command in ("load", "sect"):
        from .load import PackError, catalogue, get_pack, pack_digest, read_packs
        from .sect import build_flashes
        from .welcome import with_charter
        from .review import ReviewError, ReviewStore
        try:
            packs = read_packs(args.packs)
            states = ReviewStore(args.reviews_db).status_map(packs)
            if args.command == "load":
                if args.pack:
                    selected = get_pack(packs, args.pack)
                    status = states[selected["id"]]
                    if args.approved_only and status != "approved":
                        raise PackError("Pack not approved: " + selected["id"])
                    payload = {"pack": selected, "digest": pack_digest(selected),
                               "review_status": status}
                else:
                    payload = {"packs": [
                        {**p, "review_status": states[p["id"]]}
                        for p in catalogue(packs)
                        if not args.approved_only or states[p["id"]] == "approved"
                    ]}
                output = with_charter(payload)
            else:
                if not 1 <= args.limit <= 200:
                    parser.error("--limit must be between 1 and 200")
                eligible = [
                    p for p in packs
                    if not args.approved_only or states[p["id"]] == "approved"
                ]
                events = FleetStore(args.db).events(limit=200)
                output = with_charter({"flashes": build_flashes(
                    events, eligible, limit=args.limit, review_statuses=states
                )})
        except (PackError, ReviewError) as exc:
            parser.error(str(exc))
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    if args.command == "serve":
        try:
            import uvicorn
            from .api import create_app
        except ImportError:
            parser.error("Install web dependencies: pip install -e '.[server]'")
        uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
        return 0
    if args.command == "watch" and args.interval < 60:
        parser.error("--interval must be at least 60 seconds")
    while True:
        try:
            print(json.dumps(scan_once(args.owner, args.db)), flush=True)
        except (InventoryError, ValueError) as exc:
            print("Scan failed, previous inventory preserved: " + str(exc), file=sys.stderr, flush=True)
            if args.command == "scan":
                return 1
        if args.command == "scan":
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
