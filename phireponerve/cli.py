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
    public = sub.add_parser("export-public", help="Write minimal public-only FieldConstellation handoff locally")
    public.add_argument("--owner", default="MichaelWave369")
    public.add_argument("--out", required=True, help="New local JSON output path; existing files are never overwritten")

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
    chamber = sub.add_parser("chamber", help="ΦLoad C2: approved context and offline scenario tests")
    chamber.add_argument("--packs", default=None, help="Knowledge-pack directory")
    chamber.add_argument("--reviews-db", default=None, help="Review ledger path")
    chamber.add_argument("--suites", default=None, help="Scenario suite directory")
    chamber_actions = chamber.add_subparsers(dest="chamber_action", required=True)
    chamber_actions.add_parser("list", help="List available scenario suites and approval state")
    assemble = chamber_actions.add_parser("assemble", help="Assemble approved reference material")
    assemble.add_argument("--pack", action="append", required=True, help="Approved pack ID; repeatable")
    assemble.add_argument("--max-bytes", type=int, default=32768)
    show = chamber_actions.add_parser("show", help="Show scenario prompts, never the answer key")
    show.add_argument("--suite", required=True)
    grade = chamber_actions.add_parser("grade", help="Grade JSON choice answers without code execution")
    grade.add_argument("--suite", required=True)
    grade.add_argument("--answers", required=True, help="Path to local JSON answer file")
    trial = sub.add_parser("trial", help="Φ Construct: safe structured engineering artifact trials")
    trial.add_argument("--packs", default=None, help="Local knowledge pack directory")
    trial.add_argument("--reviews-db", default=None, help="Local review ledger path")
    trial.add_argument("--tasks", default=None, help="Local trial fixture directory")
    trial_actions = trial.add_subparsers(dest="trial_action", required=True)
    trial_actions.add_parser("list", help="List structured repair tasks and pack approval")
    trial_show = trial_actions.add_parser("show", help="Show allowed repairs without revealing rubric")
    trial_show.add_argument("--task", required=True, help="Trial task ID")
    trial_grade = trial_actions.add_parser("grade", help="Validate a JSON patch submission")
    trial_grade.add_argument("--task", required=True, help="Trial task ID")
    trial_grade.add_argument("--submission", required=True, help="Local patch JSON file")
    code = sub.add_parser("code", help="ΦConstruct container-only Python Code Lab")
    code.add_argument("--packs", default=None, help="Local pack manifest directory")
    code.add_argument("--reviews-db", default=None, help="Local pack review ledger")
    code.add_argument("--tasks", default=None, help="Code Lab task fixture directory")
    code_cmd = code.add_subparsers(dest="code_action", required=True)
    code_cmd.add_parser("list", help="List available code exercises")
    code_show = code_cmd.add_parser("show", help="Show exercise without its test cases")
    code_show.add_argument("--task", required=True)
    code_run = code_cmd.add_parser("run", help="Preview or explicitly run in Docker")
    code_run.add_argument("--task", required=True)
    code_run.add_argument("--submission", required=True, help="UTF-8 Python source path")
    code_run.add_argument("--image", required=True, help="Locally available image@sha256:digest")
    code_run.add_argument("--execute", action="store_true",
                          help="Explicitly allow restricted Docker execution")
    handoff = sub.add_parser("handoff", help="Construct ↔ Agentora local training contract")
    handoff.add_argument("--packs", default=None, help="Local knowledge-pack directory")
    handoff.add_argument("--reviews-db", default=None, help="Local review ledger")
    handoff.add_argument("--code-tasks", default=None, help="Local Code Lab task fixtures")
    handoff.add_argument("--trial-tasks", default=None, help="Local structured task fixtures")
    handoff_ops = handoff.add_subparsers(dest="handoff_action", required=True)
    issue = handoff_ops.add_parser("create", help="Create a digest-pinned, non-authorizing handoff")
    issue.add_argument("--mode", choices=["code-lab", "artifact-repair"], required=True)
    issue.add_argument("--task", required=True)
    issue.add_argument("--request-id", required=True)
    issue.add_argument("--agent-label", required=True)
    intake = handoff_ops.add_parser("inspect", help="Inspect an untrusted result; hold for verification")
    intake.add_argument("--request", required=True, help="Saved local handoff JSON")
    intake.add_argument("--report", required=True, help="Local Code Lab or trial result JSON")
    capsid = sub.add_parser("capsid", help="ΦCAPSID: reviewed, locally signed context capsules")
    capsid.add_argument("--capsids-db", default=None, help="Private local capsule state DB")
    capsid.add_argument("--packs", default=None, help="Local ΦLoad pack directory")
    capsid.add_argument("--reviews-db", default=None, help="Local pack-review DB")
    capsid_actions = capsid.add_subparsers(dest="capsid_action", required=True)
    capsid_compose = capsid_actions.add_parser("compose", help="Draft a reviewed, digest-pinned manifest")
    capsid_compose.add_argument("--pack", required=True)
    capsid_compose.add_argument("--id", required=True)
    capsid_compose.add_argument("--title", required=True)
    capsid_compose.add_argument("--role", required=True)
    capsid_compose.add_argument("--repo-marker", required=True)
    capsid_compose.add_argument("--tag", action="append", default=[])
    capsid_sign = capsid_actions.add_parser("sign", help="Sign an operator-authored manifest")
    capsid_sign.add_argument("--manifest", required=True)
    capsid_sign.add_argument("--key-id", default="local-v1")
    capsid_stage = capsid_actions.add_parser("stage", help="Validate and stage a signed capsule")
    capsid_stage.add_argument("--envelope", required=True)
    capsid_stage.add_argument("--profile", required=True)
    capsid_activate = capsid_actions.add_parser("activate", help="Activate staged context only")
    capsid_activate.add_argument("--stage-id", required=True, type=int)
    capsid_activate.add_argument("--profile", required=True)
    capsid_context = capsid_actions.add_parser("context", help="Export revalidated reference bundle")
    capsid_context.add_argument("--profile", required=True)
    capsid_rollback = capsid_actions.add_parser("rollback", help="Return an agent to baseline context")
    capsid_rollback.add_argument("--agent-id", required=True)
    capsid_history = capsid_actions.add_parser("history", help="List local capsule lifecycle states")
    capsid_history.add_argument("--agent-id", required=True)

    sub.add_parser("welcome", help="Print the trusted, versioned Φ Welcome Charter")

    args = parser.parse_args(argv)
    if args.command == "export-public":
        from .public_export import PublicHandoffError, public_handoff
        try:
            payload = public_handoff(FleetStore(args.db), owner=args.owner)
        except PublicHandoffError as exc:
            parser.error(str(exc))
        path = Path(args.out).expanduser()
        data = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        print("Wrote " + str(len(payload["repositories"])) +
              " public ID observations to " + str(path) + "; never upload to a public repository")
        return 0
    if args.command == "capsid":
        from .capsid import (
            CapsidError, CapsidStore, read_json, sign_manifest,
        )
        from .chamber import ChamberError
        from .load import PackError, read_packs
        from .review import ReviewError, ReviewStore
        try:
            if args.capsid_action == "sign":
                output = sign_manifest(read_json(args.manifest), key_id=args.key_id)
            elif args.capsid_action == "compose":
                from .load import get_pack, pack_digest
                from .capsid import SCHEMA, validate_manifest
                from .load import read_packs
                packs = read_packs(args.packs)
                pack = get_pack(packs, args.pack)
                if ReviewStore(args.reviews_db).status_map(packs)[pack["id"]] != "approved":
                    raise CapsidError("Knowledge pack is not approved")
                output = validate_manifest({
                    "schema": SCHEMA, "id": args.id, "version": "0.1.0",
                    "title": args.title,
                    "description": "Operator-scoped reference context for " + args.pack,
                    "target": {"roles": [args.role], "repo_contains": [args.repo_marker],
                               "required_tags": args.tag},
                    "capabilities": ["reference.read"],
                    "pack": {"id": pack["id"], "digest": pack_digest(pack)},
                    "provenance": "Operator-authored local manifest; review before signing",
                })
            else:
                store = CapsidStore(args.capsids_db)
                if args.capsid_action == "rollback":
                    output = store.rollback(args.agent_id)
                elif args.capsid_action == "history":
                    output = {"history": store.history(args.agent_id)}
                else:
                    packs = read_packs(args.packs)
                    states = ReviewStore(args.reviews_db).status_map(packs)
                    profile = read_json(args.profile)
                    if args.capsid_action == "stage":
                        output = store.stage(read_json(args.envelope), profile, packs, states)
                    elif args.capsid_action == "activate":
                        output = store.activate(args.stage_id, profile, packs, states)
                    else:
                        output = store.context(profile, packs, states)
        except (CapsidError, PackError, ReviewError, ChamberError) as exc:
            parser.error(str(exc))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if args.command == "welcome":
        from .welcome import welcome_charter
        print(json.dumps(welcome_charter(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "handoff":
        from .handoff import (
            HandoffError, create, inspect_report, load_json_file, task_by_mode,
        )
        from .load import PackError, read_packs
        from .review import ReviewError, ReviewStore
        try:
            packs = read_packs(args.packs)
            statuses = ReviewStore(args.reviews_db).status_map(packs)
            if args.handoff_action == "create":
                task = task_by_mode(
                    args.mode, args.task, args.code_tasks, args.trial_tasks
                )
                output = create(args.mode, task, packs, statuses,
                                args.request_id, args.agent_label)
            else:
                request = load_json_file(args.request)
                report = load_json_file(args.report)
                output = inspect_report(
                    request, report, packs, statuses,
                    code_tasks=args.code_tasks, trial_tasks=args.trial_tasks,
                )
        except (HandoffError, PackError, ReviewError) as exc:
            parser.error(str(exc))
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    if args.command == "code":
        from .sandbox import SandboxError, approved, catalogue, get_task, read_tasks, run, show
        from .load import PackError, read_packs
        from .review import ReviewError, ReviewStore
        from .welcome import with_charter
        try:
            packs = read_packs(args.packs)
            states = ReviewStore(args.reviews_db).status_map(packs)
            tasks = read_tasks(args.tasks)
            if args.code_action == "list":
                output = with_charter({"code_tasks": [
                    {**item, "pack_review_status": states.get(item["pack_id"], "unreviewed")}
                    for item in catalogue(tasks)
                ]})
            else:
                task = get_task(tasks, args.task)
                if args.code_action == "show":
                    output = show(task, packs, states)
                else:
                    output = run(task, packs, states, args.submission,
                                 args.image, execute=args.execute)
        except (SandboxError, PackError, ReviewError) as exc:
            parser.error(str(exc))
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    if args.command == "trial":
        from .load import PackError, read_packs
        from .review import ReviewError, ReviewStore
        from .trial import (
            TrialError, get_task, grade_task, read_submission, read_tasks,
            show_task, task_catalogue,
        )
        from .welcome import with_charter
        try:
            packs = read_packs(args.packs)
            states = ReviewStore(args.reviews_db).status_map(packs)
            tasks = read_tasks(args.tasks)
            if args.trial_action == "list":
                output = with_charter({"tasks": [
                    {**task, "pack_review_status": states.get(task["pack_id"], "unreviewed")}
                    for task in task_catalogue(tasks)
                ]})
            else:
                task = get_task(tasks, args.task)
                if args.trial_action == "show":
                    output = show_task(task, packs, states)
                else:
                    output = grade_task(task, read_submission(args.submission), packs, states)
        except (PackError, ReviewError, TrialError) as exc:
            parser.error(str(exc))
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    if args.command == "chamber":
        from .chamber import (
            ChamberError, assemble, ensure_approved_pack, get_suite,
            grade_suite, read_answers, read_suites, show_suite, suite_catalogue,
        )
        from .load import PackError, read_packs
        from .review import ReviewError, ReviewStore
        from .welcome import with_charter
        try:
            packs = read_packs(args.packs)
            states = ReviewStore(args.reviews_db).status_map(packs)
            if args.chamber_action == "assemble":
                output = assemble(packs, states, args.pack, args.max_bytes)
            else:
                suites = read_suites(args.suites)
                if args.chamber_action == "list":
                    output = with_charter({"suites": [
                        {**item, "pack_review_status": states.get(item["pack_id"], "unreviewed")}
                        for item in suite_catalogue(suites)
                    ]})
                else:
                    suite = get_suite(suites, args.suite)
                    approval = ensure_approved_pack(suite, packs, states)
                    if args.chamber_action == "show":
                        output = show_suite(suite, approval)
                    else:
                        output = grade_suite(suite, read_answers(args.answers), approval)
        except (ChamberError, PackError, ReviewError) as exc:
            parser.error(str(exc))
        print(json.dumps(output, indent=2, ensure_ascii=False))
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
