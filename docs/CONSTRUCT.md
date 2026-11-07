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
