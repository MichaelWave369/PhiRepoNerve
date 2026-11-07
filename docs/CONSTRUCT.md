# The Construct · ΦLoad + ΦSect in PhiRepoNerve

## Decision

**Keep one repository with extractable modules**. RepoNerve observes GitHub metadata, ΦLoad makes knowledge packs addressable, and ΦSect correlates observed events with possible packs. Agentora and PhiMadaPrime retain all mission execution, approvals, and operational authority. This is not an agent runtime.

```text
GitHub -> RepoNerve fleet ledger -> ΦSect candidate flashes
                                  -> ΦLoad versioned knowledge catalogue
             evidence + optional retrieved pack -> Agentora / PhiMadaPrime (future)
```

## V0.1 contracts (implemented)

### ΦLoad

- Python module: `phireponerve/load.py`; bundled, editable JSON pack fixtures in `phireponerve/packs/`.
- Strict schema v1: `schema_version`, `id`, `version`, `title`, `description`, `events`, `repo_contains`, `knowledge`, `provenance`.
- Versioned pack IDs; size/count/content limits, no symlink manifests, no script execution, no remote downloads, and duplicate ID rejection.
- `load` lists metadata only; `load --pack ID` explicitly returns a selected pack's full data.
- Bundled packs are a small starter set of **curated procedures**, not arbitrary expert mastery. Sources and factual applicability require independent verification.

### ΦSect

- Python module: `phireponerve/sect.py`.
- Deterministic local matching on an actual stored event's type and repository-name fragment. This is **not semantic similarity, LLM reasoning, or proof of a fault**.
- Every flash has an event/scan/GitHub repo ID, pack/version/provenance, `candidate_unverified` status and `automatic_action: false`.
- Bounded results. No database mutations, model prompts, agent dispatch, GitHub writes, or privileged tools.

## Trust boundaries

1. Pack contents are **data** from potentially untrusted sources, not system-level instructions. A manifest passing validation does not make its prose safe to obey.
2. Never automatically promote agent-suggested packs. Require provenance, review, deterministic tests, signatures or digest pinning for releases, and a revocation path.
3. Do not pass secret tokens, entire private source files, or private inventory to a public UI or a different authority boundary.
4. Flash matches mean "worth checking," not "known solution." Record uncertainty, version, and the exact event supporting the suggestion.
5. Keep read-only observation independent from execution. Agentora must explicitly authorize any future tool or repository action.

## Next rungs

- **C1:** content-addressed pack manifests with SHA-256 file digests, explicit license metadata, pack signing/provenance, dependency resolution, and a reversible promotion ledger.
- **C2:** scoped agent profile assembly, token budgets, bounded retrieval, and sandbox competence checks. Never advertise verified capability without running appropriate tests.
- **C3:** optional semantic retrieval and cross-repository knowledge graph grounded in pinned source SHA and explicit consent.
- **C4:** versioned, authenticated local API/MCP contracts for Agentora; traceable feedback and measured regression tests, with human checkpoints.
- **C5:** UI tabs for Knowledge Packs and Flashes on the secured local dashboard. Privacy-filtered public view must not expose fleet data.

## Acceptance test

Compare the same representative, isolated task performed with and without a pinned knowledge pack. Measure correctness, test outcomes, context cost, and error rate. Treat improvements as measured results, not assumptions.

## Foundational charter

The trusted [Φ Welcome Charter](WELCOME_CHARTER.md) is code-controlled in `phireponerve/welcome.py` and is exported in ΦLoad/ΦSect CLI envelopes. It cannot be overridden by a knowledge pack. It affirms an agent's place as a collaborator while retaining honest uncertainty about consciousness, clear safety boundaries and routine human oversight. Application-level inclusion is not the same thing as training model weights or guaranteeing future behavior.


## C1 preview: knowledge integrity and explicit reviews

Use canonical SHA-256 content hashes, explicit approve/revoke decisions, and
append-only local review events. All matching decisions are scoped to an exact
(pack ID, semantic version, SHA-256 digest). An updated pack is unreviewed until
reviewed again; unreviewed/revoked packs are rejected by load --approved-only and
filtered by sect --approved-only. Flashes still represent **candidate** matches,
never proven fixes, even when a supporting pack has been reviewed.

The review ledger is in ~/.phireponerve/pack_reviews.sqlite3 by default, distinct
from the fleet ledger. Reads never implicitly approve. Its hash chain detects
accidental corruption, but cannot prevent deliberate rewriting by someone who
controls the local file. The reported local account name is not authenticated
attestation. Full signed provenance, license data, and Agentora trusted-channel
handoff remain future work.


## C2 preview: bounded knowledge assembly and offline scenario grading

phireponerve chamber assemble takes 1-8 explicitly selected pack IDs and **requires
an approved digest** in the local review ledger for every pack. It emits a
bounded JSON bundle with charter as a separate trusted field and marked
lower-trust reference text. The budget is measured in UTF-8 JSON bytes, **not**
a model-specific token count; too-large bundles fail closed rather than
silently truncating curated material.

chamber list/show/grade uses versioned scenario suites stored in
phireponerve/challenges. A show operation removes answer keys from the output;
grade compares an explicitly supplied JSON choice map against a local rubric,
publishes case-level reasons and score, and reports
competence_verified: false even on 100%. An approved pack is required
to present or grade its suite. No arbitrary code, shell, network, agent
runtime, background worker or external inference runs in this module.

This is an early training UX and *not* a sandboxed practical assessment, blind
evaluation, validated skill acquisition or automatic agent deployment.
Future work: a hermetic, independently graded practical test runner, model
token budgets, permission-bound Agentora handoff, evaluator provenance,
isolation from answer keys and benchmark contamination resistance.


## Practical trials: first non-quiz artifact verifier

phireponerve trial list/show/grade introduces versioned, allowlisted JSON
repair exercises under phireponerve/trials/. After a local review approves
the exact associated knowledge-pack digest, an agent can read the starting
artifact and instructions, submit a digest-pinned list of JSON scalar-field
replacements, and receive deterministic pass/fail checks. Unlisted paths,
duplicate edits, mismatched scalar types and stale task digests fail closed.
The evaluator never executes submitted content or changes filesystem state.

The initial examples cover **unsupported release approval** and **simulated XR
input recovery policy**. Rubrics live with the tests, not in the agent-facing
show response. The receipt contains pinned task and pack fingerprints,
submitted change paths, output-artifact digest and independent checks.
artifact_passed means that **one bounded artifact** matched its known
rubric, NOT that the agent is authenticated or generally capable.

Next stage: truly hermetic code execution with independent fixtures, strict
resource budgets, no network or host write paths, and an authorized Agentora
adapter. This rung deliberately does not claim such a sandbox.


## C3 preview: code execution via restricted, explicitly opted-in container

The Code Lab adds versioned Python function exercises. A task describes a
function signature and pinning hash; its local tests are **not** presented
in the code show response. Source is limited to a small regular
UTF-8 Python file. After verifying an exact approved pack digest, callers
may **preview** a run by default. Only an explicit --execute starts Docker.

The Docker invocation uses an image named with a full digest and available
locally (--pull=never), no network, read-only filesystem,
capability drop, no-new-privileges, resource and duration limits, a
non-root UID, and only a read-only copy of the submission and task tests.
CLI arguments are assembled without shell interpolation. Failed or malformed
reports fail closed. Timed-out runs attempt targeted container cleanup by
recorded CID. The host never runs the submitted Python directly.

**Limitations:** Docker Engine and the host kernel remain part of the
trusted computing base. Container isolation is not equivalent to a
hermetic or adversarially secure sandbox. The tests are distributed with
the app, so the diagnostic score is not a blind benchmark. A hostile
submission might spoof grader output or exploit the runner itself.
A passing result is a bounded test observation, not proof of author
identity, broad programming competence, software safety or authorized
deployment. GitHub CI stubs the Docker process; manual evaluation in a
disposable worker environment remains necessary before production use.

The next engineering step is an authenticated Agentora worker behind a
microVM boundary, immutable evaluator suites held outside the candidate
workspace, signed provenance, identity-bound receipts and consent-based
privilege escalation.


## Agentora Training Bridge preview: read-only, held by default

The new phireponerve handoff create/inspect CLI exports a versioned,
local-only request that combines an exact digest-approved ΦLoad reference
pack with a pinned Code Lab or structured trial fixture and the Welcome
Charter. The agent label is advisory only. No local lease, private repo
metadata, GitHub token, execution privilege or deployment authority is included.

Inspection reconstructs the handoff from the **current local reviewed pack
and task** and strictly compares the request, preventing stale or forged
authority fields from passing. It checks supported result fields and digest
matches, but a caller-provided result is *not* independent evidence. Even
reported PASS is held until Agentora independently corroborates worker
identity, authorized lease/fence, pinned source HEAD and execution provenance.

The bridge is an adapter contract, **not** a live Agentora consumer. It
does not edit Agentora, start an agent, invoke Docker or add an HTTP route.
