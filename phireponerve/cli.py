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
    sect = sub.add_parser("sect", help="ΦSect: suggest packs for observed fleet events")
    sect.add_argument("--packs", default=None, help="Optional directory of JSON manifests")
    sect.add_argument("--limit", type=int, default=50, help="Maximum candidate flashes, 1-200")

    args = parser.parse_args(argv)
    if args.command in ("load", "sect"):
        from .load import PackError, catalogue, get_pack, read_packs
        from .sect import build_flashes
        try:
            packs = read_packs(args.packs)
            if args.command == "load":
                output = get_pack(packs, args.pack) if args.pack else {"packs": catalogue(packs)}
            else:
                if not 1 <= args.limit <= 200:
                    parser.error("--limit must be between 1 and 200")
                events = FleetStore(args.db).events(limit=200)
                output = {"flashes": build_flashes(events, packs, limit=args.limit)}
        except PackError as exc:
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
