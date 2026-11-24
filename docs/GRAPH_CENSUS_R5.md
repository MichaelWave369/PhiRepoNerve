# R5.0 · Offline evidence graph census

This first convergence rung implements the R5 roadmap in [architecture](ARCHITECTURE.md) without replacing FieldConstellation's reviewed relationship ledger or PhiOS's App Platform.

Use the existing latest-complete public export and a locally saved, reviewed FieldConstellation `src/relationships.json` from a pinned commit:

```sh
phireponerve scan --owner MichaelWave369
phireponerve export-public --owner MichaelWave369 --out public-handoff.json
python -m phireponerve.graph_census --inventory public-handoff.json --relationships relationships.json
python -m unittest discover -s tests -p 'test_graph_census.py' -v
```

The census itself is offline, dependency-free and read-only. It outputs aggregate counts to stdout, not IDs, names, source excerpts, tokens or private inventory. Keep the inputs local. The operator must independently verify source pins and current public visibility; the validator checks input shape and pin syntax, not authenticity. Unknown endpoints fail closed rather than silently deleting edges.

## Metrics

- Relationship records and distinct unordered node pairs are counted separately: two reciprocal navigation links count as one unordered pair.
- Pair density is recorded unordered pairs divided by n(n-1)/2, or null if undefined.
- Weak components ignore edge direction and mix all recorded kinds. They do not represent executable paths or transitive dependencies.
- Nodes without recorded edges are **unreviewed by this ledger**, not necessarily isolated in real life.
- Reported source-review grades and relationship kinds remain separate; a shared library or navigation link is not a runtime dependency.

No claims of complete dependency discovery, live interoperability, installation, execution or routing authority. All outputs are advisory and authority NONE.

## Next acceptance gate

Expand the upstream reviewed relationship ledger with commit-pinned source evidence and separate interface, dependency, navigation and runtime-test grades. Preserve negative and missing observations. Measure one bounded Altermath-to-Agentora pilot against ordinary DAG execution before proposing live scheduling. Reuse existing capability and App Platform contracts, and keep private data outside public exports.
