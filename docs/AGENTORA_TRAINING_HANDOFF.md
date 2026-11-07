# ΦConstruct ↔ Agentora Training Handoff v0.1

**Status: implemented read-only local producer and structural intake in
PhiRepoNerve; Agentora consumption is not implemented by this change.**

## Existing orchestration is authoritative

Agentora already has RepoNerve public observations, persistent logical
repo stewards, local same-host worker leases, independent GitHub HEAD checks,
and a guarded single-workflow dispatch. This handoff does NOT duplicate or
bypass those controls. It carries a bounded teaching/testing task and its
pinned knowledge reference toward that existing operator workflow.

## Create a training request

1. Review a pack locally via phireponerve reviews approve.
2. Generate a handoff: phireponerve handoff create --mode code-lab
   --task retry-backoff-code --request-id trial-001 --agent-label worker-alpha.
3. Save CLI output only in a local, operator-controlled file. Do not
   automatically publish JSON bearing private future mission details.
4. Agentora's **future** consumer should accept this as low-trust mission
   input and issue its own authorized worker assignment and lease.
5. Run code only under the separately gated, opt-in Code Lab, preferably
   in a disposable rootless VM. Do not treat Docker as an adversarially
   proven isolation boundary.

## Handoff shape

- schema: phi.construct.training-handoff.v0.1
- mode: code-lab | artifact-repair
- request_id, agent_label (labels only, not authenticated identities)
- task: {id, version, digest}
- approved_pack: {id, version, digest, review_status}
- Trusted application-authored charter field
- Content fingerprint handoff_digest over the remaining JSON
- Explicit false for all authority, identity, source and evidence flags
- Held state; no queue, lease, grant or service endpoint

The handoff is recomputed and checked against **current local reviewed
content** on inspection. Revoked packs, changed task bytes, and mutated
authority flags fail closed. There is no durable request-ID uniqueness,
expiry, replay prevention, sender authentication or remote registration
in this version. A SHA-256 fingerprint is **not** proof of origin.

## Inspect a result

phireponerve handoff inspect --request request.json --report report.json
checks local task/pack pinning, type constraints and known Code Lab /
structured-artifact result shapes. It does not execute a task, open
repositories, verify GitHub workflow data, or sign anything.

Output schema: phi.construct.training-report-intake.v0.1.
Even when a result says PASS it returns:
HELD_AWAITING_INDEPENDENT_ATTESTATION,
receipt_source_authenticated=false,
independent_evidence_verified=false,
worker_lease_verified=false,
current_source_head_verified=false,
execution_authorized=false,
dispatch_authorized=false,
merge_authorized=false,
deployment_authorized=false.

No offline JSON can prove the claimed worker performed the test.
A later Agentora integration must get evidence directly from a trusted
executor or verified GitHub artifact, and enforce current lease generation
and exact source HEAD at the *time of effect*, following Agentora's
existing Fleet R3-R5 patterns. Keep independent approval and release
policies separate from training reports.

## Privacy and security

Never place private inventory, credentials, local review-ledger contents,
lease tokens, Docker sockets, or authenticating capabilities in these
exports. External knowledge remains lower-trust reference data, and the
Welcome Charter must be placed by the actual Agentora runtime in a
trusted instruction channel, not merely copied into a user prompt.

**This is a contract for integration, not an authenticated connection.**
