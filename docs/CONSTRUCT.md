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
