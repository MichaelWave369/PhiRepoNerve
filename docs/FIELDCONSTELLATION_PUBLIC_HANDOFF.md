# FieldConstellation public-only handoff (R1)

RepoNerve remains a **private, loopback-only observer**. The Field Gateway never connects to its API or database. This is an **explicit local-file** exchange of a minimal allowlisted projection from the **latest complete scan**.

Run locally where the RepoNerve SQLite inventory exists:

    phireponerve scan --owner MichaelWave369
    phireponerve export-public --owner MichaelWave369 --out public-handoff.json

If RepoNerve is not installed locally, this optional bridge remains unavailable; the Field Gateway's public metadata, source-reviewed relationships and dated destination checks still work.

- An export is created **only on command**; mode `0600` where available; never overwrites an existing file.
- Failed or incomplete latest scans block export.
- Only present, public owner-matched GitHub IDs appear; names, URLs, descriptions, tokens, private counts and events are excluded.
- The Gateway rejects unknown/private IDs, unexpected fields, duplicate IDs and malformed dates. Imported observations stay in browser memory until reload or Clear. It never posts or caches the file.
- Do not commit this filtered export or publish it. Visibility can change after a scan, and the gateway's independent public inventory is the second identity/visibility gate.

The versioned contract has precisely these keys: `schemaVersion:1`, `source:"PhiRepoNerve"`, `scope:"public-ids-only"`, `owner:"MichaelWave369"`, `observedAt` (ISO timestamp), and `repositories` (entries with `id` as numeric string, `pushedAt` as ISO timestamp or null, and `archived` as boolean).

An observed push timestamp is **not** CI status, deployment status, successful build evidence, a working integration, or authorization. The imported data is operator-provided and not cryptographically authenticated.
