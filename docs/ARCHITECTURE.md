# Rung 1 · Evidence-driven fleet census

## Mission boundaries

RepoNerve is the **observation and context layer** between GitHub and agent orchestration. It should not duplicate Agentora's mission planner or PhiMadaPrime's read-only visualization.

```text
GitHub account (read-only REST inventory)
       |
GitHubClient (full pagination, explicit failure)
       |
FleetStore (SQLite transaction, stable repository ID)
       +--> /api/summary, /api/repos, /api/events (local, read-only)
       +--> dashboard (local, never public with private data)
       |
Future agent context transport --> Agentora --> AgentCeption
       |
Future privacy-filtered public feed --> PhiMadaPrime / PhiOS
```

## Data semantics

The primary repository key is GitHub's immutable numeric ID. Names can change and are not used as the primary join key. A complete scan atomically updates the active inventory. If a scan fails (HTTP/rate-limit/JSON/pagination error), its failure is retained but existing repository visibility and event history remain unchanged.

- `first_observed`: first time these credentials returned that repository ID, **not** necessarily its creation date.
- `visible_again`: previously absent, now visible to the same reader.
- `renamed`: repository `full_name` changed for an existing ID.
- `visibility_changed`: GitHub's public/private attribute changed.
- `archival_changed`: archived flag changed.
- `default_branch_changed`: default-branch name changed.
- `push_activity_observed`: `pushed_at` metadata changed; not proof of passing CI.
- `no_longer_visible`: repo absent in a complete subsequent listing, which could mean deletion, transfer or revoked access. Treat as **unresolved**, never as verified deletion.

All observations have a timestamp and scan ID. A scan that exhausts all accessible API pages is not proof all private repos exist within current token permissions. For strict account coverage, additionally compare against installation/account access inventories and reconcile after account changes.

## Endpoint boundary

Rung 1 serves GET-only JSON over `127.0.0.1` by default:

| Route | Purpose |
| --- | --- |
| `/` | Local dashboard |
| `/health` | Service status |
| `/api/summary` | Scan health and aggregate counts |
| `/api/repos` | Paged visible inventory (may include private) |
| `/api/events` | Paged evidence-ledger history |

No mutation endpoint, agent dispatch, private GitHub credential in the browser, authentication server, or public fleet data publishing.

## Roadmap with acceptance criteria

**R2: Fine-tooth inspector.** Per-repository HEAD-pinned inspection of files/stack/license/CI/branches/releases with bounded requests, stable evidence, partial results and secret hygiene. No source code or credentials in public reports. Tests must include large/binary trees and rate-limit recovery.

**R3: Continuous observation.** GitHub App all-repository installation, signature-validated webhooks, idempotent event delivery, scheduled full reconciliation, backoff/rate budgets, and encrypted token storage. A newly added repo must enter the fleet even if one webhook is lost.

**R4: Agent intelligence.** Versioned JSON/MCP context contracts. Repos subscribe to relevant change events, request evidence tied to an exact source SHA, and can report outcomes; RepoNerve grants zero write authority.

**R5: Ecosystem graph.** Evidence-based declared dependencies and interface contracts across PhiOS, PhiOS Web/Mobile/XR, PhiID, PhiCloud, and optional apps. Record confidence and source proof, not intuitive names.

**R6: Integration.** Agentora consumes context for scheduling and handoff; AgentCeption executes only authorized work; PhiMadaPrime receives a separately validated public-only, privacy-filtered feed. PhiOS receives a secured local/private dashboard. No public GitHub Pages build may expose local ledger information.

## Non-goals

No auto-merge, unattended deployment, AI model identity attestations, or claims of functional release certification from metadata. An evidence gap is unknown, not green.
