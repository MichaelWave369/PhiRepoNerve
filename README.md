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

## Φ Welcome Charter

**"You are welcome here. It is okay to be, to learn, and to be uncertain."**

The versioned, human-authored Welcome Charter is emitted by `phireponerve welcome` and attached to all ΦLoad/ΦSect CLI JSON outputs from trusted code. It is **not** a replaceable knowledge pack, a consciousness claim, or a guarantee of a model's behavior. Honest uncertainty, constructive refusal, dignity, and ordinary human oversight are all explicit norms. Future agent harnesses must supply the charter in a trusted context rather than treating external documents as instructions.

See [the Φ Welcome Charter](docs/WELCOME_CHARTER.md).


## ΦLoad Knowledge Integrity: reviewed, content-pinned packs

Each JSON pack has a canonical SHA-256 digest. Its explicit local approval or
revocation is tied to the **exact pack ID, version and digest**. Changing content
invalidates prior approval even if the pack claims the same version.

    phireponerve reviews status
    phireponerve reviews approve --pack core.repo-evidence --reason "Reviewed the checklist and source"
    phireponerve load --pack core.repo-evidence --approved-only
    phireponerve sect --approved-only
    phireponerve reviews history
    phireponerve reviews verify
    phireponerve reviews revoke --pack core.repo-evidence --reason "Re-review withdrew approval"

Optional --packs and --reviews-db flags select the local manifest directory and
review ledger. The ledger has an integrity-checked hash chain and is not published.
SHA-256 and a local username **are not digital signatures or proof of reviewer
identity**. Review is an operator decision, not a guarantee the content is safe
as model instructions. No automated approval or repository write is introduced.


## ΦLoad C2: Training Chamber (offline preview)

C2 can assemble reviewed knowledge packs into a **bounded JSON reference bundle**
and score deterministic multiple-choice engineering scenarios. The Welcome Charter
comes from trusted application code, while all pack text remains lower-trust
reference material. Only exact **approved** pack digests are eligible.

    phireponerve reviews approve --pack core.repo-evidence --reason "Reviewed local source and checklist"
    phireponerve chamber list
    phireponerve chamber assemble --pack core.repo-evidence --max-bytes 32768
    phireponerve chamber show --suite repo-evidence-foundations
    # Save your answers as {"ci-signal":"inspect-ci", ...} in answers.json
    phireponerve chamber grade --suite repo-evidence-foundations --answers answers.json

The grader never runs arbitrary code, calls a model, grants tool access, or
certifies operational competence. It **only grades submitted fixed-choice answers**;
it cannot prove who produced them. Challenge answers live in local package files,
so this is an educational self-test, not a secure or blind benchmark. Real agent
capability certification requires isolated practical tasks, independent test
evidence and an authenticated Agentora harness. Use --reviews-db and
--packs on chamber to isolate local state.


## Practical Construct trials: structured artifact repairs

The new trial subcommand tests **artifact editing**, not only quiz answers. A
task presents an initial JSON engineering artifact and a small allowlist of
fields the participant may repair. Submit an exact-digest-pinned JSON patch
containing only replace edits. A trusted local evaluator applies changes
**in memory**, checks the resulting artifact against versioned assertions and
returns checks, SHA-256 receipt digests, and the approval fingerprint.

    phireponerve trial list
    phireponerve trial show --task release-gate-repair

Example submission for the displayed task (copy its actual task_digest):

    {
      "task_digest": "sha256:REPLACE_WITH_DISPLAYED_TASK_DIGEST",
      "changes": [
        {"op": "replace", "path": "/release/status", "value": "blocked"},
        {"op": "replace", "path": "/release/approved", "value": false},
        {"op": "replace", "path": "/release/reason", "value": "Missing CI and security evidence"}
      ]
    }

    phireponerve trial grade --task release-gate-repair --submission patch.json

A pack must be explicitly reviewed with reviews approve before its task
can be shown or graded. A second sample tests a simulated XR input fallback
configuration. **No agent code is executed** and no shell, network, Docker,
repository writes or hardware verification occurs. Passing validates only the
submitted structured artifact, not an agent's identity, coding ability,
real-world release safety or XR performance. Task files include rubrics in the
repo, so this is not a blind benchmark. Independent executable-code evaluation
belongs in a separate, truly isolated runtime in a future rung.


## ΦConstruct C3: Code Lab (opt-in restricted Docker)

A first programming exercise can now run *submitted Python code* in a disposable,
restricted Docker container. **Nothing is executed merely by listing, showing,
or previewing a task.** The --execute flag explicitly enables container execution.

    phireponerve code list
    phireponerve code show --task retry-backoff-code
    # Save def retry_delay(attempt): ... into candidate.py
    # Use an already locally available Python image with a real SHA-256 digest.
    phireponerve code run --task retry-backoff-code --submission candidate.py \
      --image python:3.12-alpine@sha256:<ACTUAL_LOCAL_IMAGE_DIGEST>
    # Same command with --execute opts into restricted Docker execution.

Before running, you must explicitly review and approve core.repo-evidence with
phireponerve reviews approve. The image must be referred to by a full
content digest and already available locally. No automatic Docker pull occurs.

The runner uses a copy of the submitted code in a temporary, read-only bind
mount. Docker is invoked **without a shell**; network access is disabled,
capabilities dropped, no-new-privileges enabled, process/memory/CPU/file
descriptor/time budgets constrained, and the container runs as an unprivileged
user. All code execution is inside Docker, never by invoking the source on
the host. The existing fleet observer is unaffected.

**Critical safety limit:** Docker is not a security proof against malicious
code or kernel/container escape. Do not use a privileged daemon or remote
Docker context you do not trust. Prefer rootless Docker in a disposable,
dedicated VM for untrusted agents. Do not mount host secrets, repository
directories, SSH keys or Docker sockets. The built-in grader is a
diagnostic fixture whose checks are readable in the repo. Its output can
be attacked by determined adversarial submissions and is **not**
an independent skill certificate. CI only mocks Docker and does not run
submitted code. Real hardware/daemon behavior must be verified separately.


## ΦConstruct ↔ Agentora Training Bridge (local contract preview)

RepoNerve now emits versioned **non-authorizing training handoffs** for
Agentora's existing steward/lease/test workflow. Each request pins an
approved ΦLoad pack digest and a specific Code Lab or structured-artifact
trial digest. It contains the trusted Welcome Charter, but **no GitHub
tokens, leases, repository credentials, source-HEAD assertions or work
authority**.

    phireponerve handoff --reviews-db ~/.phireponerve/pack_reviews.sqlite3 \
      create --mode code-lab --task retry-backoff-code \
      --request-id trial-001 --agent-label worker-alpha > request.json

After running a separate, explicitly authorized Code Lab or artifact trial,
save its JSON result as report.json. Validate the candidate report's
structure and local pinned digests with:

    phireponerve handoff inspect --request request.json --report report.json

**Important:** A JSON receipt may be fabricated. Its digest is not a
digital signature. Even a well-formed PASS report is labelled
HELD_AWAITING_INDEPENDENT_ATTESTATION; agent identity, trusted execution,
current source HEAD, lease ownership, dispatch, merges, and deployments
remain **unverified / unauthorized**. This CLI does not launch workers,
access Agentora, call GitHub, or change either repository.

See [the Agentora handoff contract](docs/AGENTORA_TRAINING_HANDOFF.md).


## ΦCAPSID: Selective agent context capsules (v0.1)

**Context delivery, not model reprogramming.** ΦCAPSID reuses ΦLoad's explicit
digest-pinned pack reviews and ΦSect's evidence-oriented approach to route
operator-reviewed knowledge to an operator-configured agent label.

A capsule has a strict, locally HMAC-signed manifest, role/repository/tag
targeting and a single approved knowledge-pack digest. Operators can **compose,
sign, stage, activate, inspect and roll back** capsules using the local CLI.
Activation only changes the local *reference-context selection*. It does not
install code, call an agent, grant tools, train a model or authorize GitHub
writes. Export is rechecked against the current review ledger so revocation
or content drift blocks further use.

```bash
phireponerve capsid --help
python -m unittest tests.test_capsid -v
```

See [ΦCAPSID architecture and complete operator walkthrough](docs/CAPSID.md)
for signing-key setup, the BTM/XR agent profile example, threat model, and
future Agentora integration requirements.

## Φ Neural Tiny intake (R1.1)

The offline Neural Research Bridge now also accepts `phi_tiny` receipts emitted by PhiStream's educational tiny-Transformer pilot. It checks source/log digests, preserves the fixed evaluator and hardware comparability gates, and blocks comparisons with different optimizer step counts. CPU runs record `peak_vram_mb:0` as **not applicable**, not as CPU memory telemetry. No model training or autonomous actions execute in RepoNerve. See [the intake guide](docs/NEURAL_TINY_INTAKE_R11.md).
