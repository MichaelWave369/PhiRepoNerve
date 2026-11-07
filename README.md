# Φ RepoNerve

**A living, evidence-grounded inventory and event feed for the Φ software ecosystem.**

RepoNerve Rung 1 is a **read-only GitHub fleet observer**. It enumerates GitHub repositories accessible to its credentials, writes successful snapshots to a private local SQLite database, detects changes against the previous complete inventory, and exposes a local read-only dashboard and JSON API. It **does not** run agents, change other repositories, merge PRs, claim a release works, or publish private inventory data.

## Start in five minutes

Python 3.11+ is recommended.

```bash
python -m pip install -e ".[server]"
# Optionally set GITHUB_TOKEN in your environment for repos your credentials can read.
phireponerve scan --owner MichaelWave369
phireponerve serve
```

Open **http://127.0.0.1:8765** for the fleet dashboard. No token means public repositories only. With a suitable user token, the scanner uses GitHub's authenticated owner-repository listing, which may include private repositories your token can access. Keep the database and API local.

For continuous observation, run the following in a **separate terminal or supervised local service**:

```bash
phireponerve watch --owner MichaelWave369 --interval 600
```

The watch process must remain running. A refresh of the dashboard does not itself scan GitHub. Webhooks and a deployable service are planned for subsequent rungs.

## What Rung 1 observes

- Fully paginated repository **metadata inventory** with stable GitHub IDs, including new repositories, renames, archival changes, branch-name changes, visibility changes, and pushed-at metadata changes.
- A transactional, local snapshot ledger: failed or incomplete scans cannot erase a previously successful inventory or produce spurious "missing" events.
- Read-only HTTP routes: `/health`, `/api/summary`, `/api/repos?limit=100&offset=0&q=...`, and `/api/events?limit=100&offset=0`.
- Browser dashboard with search, status, and the latest observation history. Its numbers come from the locally observed evidence, not demo fixtures.

**Evidence boundaries:** A repo missing from a complete scan is marked **no longer visible**, not necessarily deleted. A changed `pushed_at` timestamp does not prove tests passed. Enumeration completion means pages were exhausted without an observed API failure; it cannot prove your token was granted access to every private repository. Missing webhook delivery and changing inventory during pagination can also require reconciliation.

## Security

RepoNerve is local-first and the server binds to `127.0.0.1` by default. The API deliberately has no authentication layer in Rung 1, so **never expose it to the public internet**. The token is read from `GITHUB_TOKEN` (or `GH_TOKEN`), never printed, stored in SQLite, shipped to a browser, or committed. GitHub requests use GET only.

The database defaults to `~/.phireponerve/fleet.sqlite3`; override with `--db PATH`. **Do not publish that database or any derived private-repo snapshots on GitHub Pages.** No GitHub Pages deployment is included in this rung.

## Test

```bash
python -m unittest discover -s tests -v
python -m compileall -q phireponerve
```

See [architecture and next rungs](docs/ARCHITECTURE.md) for data semantics and the Agentora / PhiMadaPrime handoff plan.

**One ecosystem. Evidence first. Agents second.**


## ΦLoad + ΦSect (Construct preview)

Two **independent, read-only modules inside RepoNerve**:

- **ΦLoad** reads versioned local JSON knowledge packs. It validates a small v1 manifest schema, limits file size/count, rejects symlink packs and duplicate IDs, and **never executes pack contents**. The default packs are curated checklists, not universal model training or proof of competency.
- **ΦSect** compares already-recorded fleet events to declared pack triggers and repository-name filters. Each **FLASH** is an unverified suggestion that includes the originating event ID and scan ID, never a claim of root cause or permission to change code.

```bash
phireponerve load                        # list available packs, no full content
phireponerve load --pack core.repo-evidence  # explicitly retrieve a pack
phireponerve --db ~/.phireponerve/fleet.sqlite3 sect --limit 20
phireponerve load --packs ./my-local-packs
```

These commands run locally, make **no model calls**, and do not touch remote repositories. Custom packs are **untrusted data**: validate their authorship and provenance before putting their contents in an agent context. A pack's successful schema validation is not proof that its advice is accurate or safe.

Rung 1's API and dashboard are unchanged. Future Agentora integration should use permission-scoped contracts, cited source revisions, and a human-reviewed promotion process for agent-generated packs. Read [the Construct design](docs/CONSTRUCT.md) for boundaries and next steps.
