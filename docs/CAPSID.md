# ΦCAPSID v0.1 · Selective agent context capsules

**Implemented:** local signed manifests, explicit reviewed-pack pinning, deterministic
role/repository/tag matching, staged context activation, safe baseline rollback,
and a read-only context export built on the existing ΦLoad Chamber.

**Not implemented:** an agent runtime, remote installation, model-weight training,
unattended agent modification, tool grants, independent publisher identity, remote
Agentora consumption, release certification, or automatic rollback from outcomes.

Biological inspiration: tissue-targeted delivery suggests selecting *which* agent
receives a particular knowledge resource. The analogy is not a claim that this
software edits neural-network weights or performs biological reprogramming.

## Safety and trust boundaries

- A capsule contains **no executable code**. In v0.1 the only declared capability
  is `reference.read`. Unknown capabilities and unknown JSON fields fail closed.
- A capsule is scoped to at least one role or repository substring. All supplied
  role, repository, and tag gates must match the locally supplied profile.
- The operator profile is configuration, **not** authenticated proof of a worker's
  identity. A caller who controls both profile and local state can impersonate a
  label. Agentora must independently authenticate real workers.
- Capsule envelopes use **HMAC-SHA256** with an out-of-band local shared secret.
  HMAC authenticates data to holders of that key, not a distinct publisher.
  SHA-256 digest pinning detects drift but neither primitive proves the quality of
  knowledge. This is not public-key supply-chain signing or a trust registry.
- Review decisions come from ΦLoad's existing digest-pinned ReviewStore. A revoked
  or changed pack makes **stage, activate, and context export** fail closed.
- Activation changes a private local SQLite **context selection record only**.
  It does not invoke an agent, install a tool, execute a payload, dispatch, merge,
  deploy, alter model weights, or grant any extra authority.
- Rollback disables the current active capsule and returns the agent label to a
  **no-capsule baseline**. Superseded versions are intentionally not restored.
- Agent knowledge is exported as reviewed reference *data*, not trusted
  instructions. The Welcome Charter comes from application code.
- The ledger and key are local, not designed to resist a malicious local admin,
  hostile system process, or stolen secret. Keep them off GitHub and GitHub Pages.

## Local end-to-end example

Using the included XR pack and BTM agent as an example:

```bash
# 1. Explicitly review the pack's contents; approval is local and digest-pinned.
phireponerve reviews approve --pack create.xr-input-triage --reason "Reviewed XR checklist and its scope"

# 2. Create a draft manifest with the exact CURRENT reviewed pack digest.
phireponerve capsid compose --pack create.xr-input-triage \
  --id capsid.xr-input-triage --title "BTM XR input reference" \
  --role xr-steward --repo-marker btm --tag webxr > manifest.json

# 3. Generate a fresh 32-byte local secret, store it privately outside the repo.
# In a POSIX shell:
umask 077
export PHICAPSID_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
# Persist it in your secret manager if later activation must survive the shell.
# NEVER commit or echo the key.

# 4. Sign the reviewed draft. Signing is not pack approval.
phireponerve capsid sign --manifest manifest.json > capsule.json
```

Place this **operator-owned local profile** in `btm-agent.json`:

```json
{
  "schema": "phi.capsid.agent-profile.v1",
  "agent_id": "btm-steward",
  "role": "xr-steward",
  "repository": "MichaelWave369/BTM",
  "tags": ["webxr"],
  "allowed_capabilities": ["reference.read"]
}
```

Then:

```bash
# 5. No execution occurs. The staging record can be reviewed first.
phireponerve capsid stage --envelope capsule.json --profile btm-agent.json

# 6. Replace 1 with the returned stage_id.
phireponerve capsid activate --stage-id 1 --profile btm-agent.json

# 7. Reference bundle: trusted charter + low-trust reviewed knowledge + flags.
phireponerve capsid context --profile btm-agent.json

# 8. View local lifecycle records or return to the baseline.
phireponerve capsid history --agent-id btm-steward
phireponerve capsid rollback --agent-id btm-steward
```

**Windows PowerShell example** for generating a session key:

```powershell
$env:PHICAPSID_HMAC_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit generated `manifest.json`, `capsule.json`, `btm-agent.json`,
the HMAC key, or local SQLite databases if they contain sensitive internal
context. Keep this work in a private operator-controlled directory.

## Contract details

Manifest schema: `phi.capsid.manifest.v1`; envelope schema:
`phi.capsid.envelope.v1`; local agent configuration schema:
`phi.capsid.agent-profile.v1`.

Each capsule pins one existing ΦLoad pack by canonical digest. The envelope's
HMAC covers manifest bytes **and** the key ID using a domain-separated input.
Unknown capabilities fail by allowlist. A local activation ledger records
`staged`, `active`, `superseded`, and `rolled_back`.

The `context` command re-verifies the signed envelope, profile, pack digest,
and current local review decision every time before emitting the reference
bundle. Exporting context is not a claim of independent worker authentication
or evidence that any downstream agent actually consumed it.

## Future rungs

1. **Agentora integration:** caller authentication, operator-controlled profile
   registry, per-worker lease, nonce, expiry, replay protection and validated
   source HEAD; hold until independent agent identity and mission policy checks.
2. **Scoped capabilities:** separate permission policy engine for real tool
   adapters, least privilege, sandboxing, telemetry, and outcome evidence.
   No authority should be inferred from a capsule manifest alone.
3. **Canary and evaluation:** baseline measurement, shadow testing, strict
   promotion rules, automated disable on measured regressions, audit trails.
4. **Model adaptation:** optional, explicitly approved training of separately
   versioned adapters; rollback and regression evaluations for model changes.
   Never confuse loading reference text with weight updates.

Run `python -m unittest discover -s tests -v` for the offline failure cases.
