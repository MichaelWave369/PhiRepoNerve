# Phi Inference Fabric R17: PhiRepoNerve Inference Evidence Ledger

**Read-only, local-only, review-task planning.** This rung consumes up to eight
existing, operator-saved PhiServe R15 advice JSON files and creates a private
static report.json and index.html. It connects the observation flow from
PhiStream to PhiServe to RepoNerve without making an execution scheduler.

## Workflow

Collect local PhiStream hardware observations, run measured GGUF
benchmarks in PhiServe R13, and create the offline R15 capacity advisory.
Then from PhiRepoNerve:

~~~powershell
python -m pip install -e .
python -m phireponerve.inference_ledger --advice "D:\PrivatePhi\advice-main.json" --out-dir "D:\PrivatePhi\inference-review-01"
start "D:\PrivatePhi\inference-review-01\index.html"
~~~

Use the --advice flag repeatedly for up to eight existing reports.
No automatic scans, live GPU polling, daemon connection, remote sync,
database writes or GitHub queries occur. Files must be regular non-symlink
files of no more than 256 KiB each. Outputs must be new local directories
outside a Git checkout to reduce the risk of accidentally publishing
private hardware/model metadata.

Each R15 report undergoes strict source schema and field validation:
- all execution, routing, attestation, certification and quality claims false
- RAM and CUDA memory budget arithmetic recomputed from saved counters
- GGUF file-size floor booleans recomputed from actual report bytes
- classifications crosschecked against snapshot and benchmark evidence states
- bounded finite p50/p95 wall times and unique GPU-layer profiles
- SHA-256-shaped hashes, explicitly not treated as producer authentication
- duplicate JSON keys and nonfinite JSON fields rejected

**Original PhiStream hardware snapshot and PhiServe benchmark JSON files are
not reopened by this rung.** A structurally consistent R15 report does not
prove that its source observations existed or came from the same physical
machine. PhiMadaPrime R46 can optionally match local source bytes against
reported hashes, still without independent hardware attestation.

## Planning tasks

A hardware snapshot older than 300 seconds gets
RECAPTURE_HARDWARE_SNAPSHOT. A benchmark older than seven days gets
REMEASURE_GGUF_BENCHMARKS, when the snapshot is otherwise recent.
A GPU-layer profile lacking CUDA counters gets COLLECT_CUDA_COUNTERS.
Dates in the future produce HOLD_CLOCK_OR_FUTURE_TIMESTAMP.
Other source holds become REVIEW_HELD_SOURCE_EVIDENCE. With basic
checks clear, the sole state is HUMAN_CAPACITY_REVIEW_REQUIRED.

The ledger recalculates ages at the current review time; it never treats
an earlier R15 review classification as a present hardware clearance.
Tasks are not run, queued, approved or dispatched.

Multiple R15 summaries are presented side-by-side, **not ranked**:
R15 does not independently prove identical physical hardware,
standardized workload across separate advisories, model-quality parity,
thermal conditions, or measured end-to-end cost. File-size floors
do not measure a model working set or viability of hybrid offload.
Reported p50/p95 are full HTTP request times, not isolated decode speed.

## Privacy and trust boundaries

The static HTML contains escaped model aliases, source digests, metrics
and review tasks, without raw file paths, model weights, prompts or text
generations. It has no JavaScript, network, forms, storage or telemetry.

The JSON still includes identifying aliases and hashes, so do not publish
private exports or include them in GitHub Pages. Local hash consistency
is not a digital signature or source-origin proof.

No new PhiServe runtime dependency, daemon control, queue modification,
Agentora scheduling, machine selection, model execution or remote service
is introduced.

## Test

~~~powershell
python -m unittest discover -s tests -v
python -m compileall -q phireponerve
~~~

Automated checks use synthetic R15 receipts and cover stale/future
observations, missing CUDA counters, bad memory math, forged authority
claims, duplicate files, symlink inputs and escaped HTML. These are not
physical RTX 5070 or RTX 3060 benchmark runs.

Real licensed GGUF field measurements are still required before a future
separately governed routing scheduler can be considered.
