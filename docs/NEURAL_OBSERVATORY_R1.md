# Φ Neural Research Observatory R1

**Status:** offline, local-first, read-only static report generator. Not a trainer, website deployment, autonomous agent, trusted GPU witness, or production-quality certification.

## Why it exists

PhiStream emits tiny training artifacts. PhiRepoNerve produces R1 receipts that bind reported metrics to locally supplied log/code bytes. Agentora proposes controlled changes. This observatory gives human reviewers a clean visual overview **without letting models or agents self-approve their results**.

## Input contract

Use the [example bundle](../examples/observatory-bundle-template.json) and replace its paths with real local artifacts. Keep the bundle, `receipt.json`, `metrics.log`, and the exact training source file inside a common private local folder. Paths use forward slashes, even on Windows; they must be relative to the bundle folder, with no `..`, drive letters, backslashes, or symlinks.

In a PhiRepoNerve checkout (Python 3.11+, no other dependencies required):

```powershell
python -m unittest discover -s tests -p test_neural_observatory.py -v
python -m phireponerve.neural_observatory --bundle C:\phi-lab\study\bundle.json --out-dir C:\phi-lab\study-report-01
start C:\phi-lab\study-report-01\index.html
```

**Do not run these commands until the referenced receipts exist and you have copied the files into your private study directory.** Report output must be a new directory outside any Git checkout. No network calls, external fonts/images, JS, model code execution or automatic uploads occur.

## Report boundaries

- Recomputes RepoNerve receipts against the exact local log and code bytes; invalid evidence fails the whole report before writing output.
- Enforces matching study ID and unique run IDs. An explicit baseline is compared against candidates through the existing `neural_lab.compare` fairness gate (dataset, tokenizer, evaluator, hardware, time budget and fixed steps for `phi_tiny`).
- A candidate with unmatched conditions or budget violation is visibly HELD. A lower measured loss becomes `candidate_for_human_review`, not a verified model improvement or deployment permission.
- `report.json` intentionally contains only bounded ID/metric/receipt hashes and false assurance/authorization flags; private code/text/path/log contents are not rendered.
- The responsive `index.html` is entirely static and contains a CSP denying networks, scripts, embeds and forms. Do not upload private runs or reports publicly by default.
- A locally matching hash does **not** prove a genuine training run, an independently sourced dataset, statistical significance, research novelty, or actual GPU execution. Hardware and evaluation contexts are still self-declared until independently reproduced.

## Integration sequence

1. R1 PhiStream: local training writes `plan.json` / `metrics.log`, no weights or pretrained model.
2. R1 PhiRepoNerve: `record` writes `receipt.json` with file hashes.
3. Agentora: proposes allowed parameter changes and separate review handoffs.
4. **Observatory R1:** renders locally checked experiment comparisons and blocked conditions.
5. Next: human-approved RTX 5070 CUDA field runs, repeat trials and uncertainty estimates, then an opt-in PhiMathAtelier/PhiOS front-end using only explicitly redacted static exports.

All six Karpathy resources remain educational references only, not runtime dependencies or copied third-party code. Their licenses and source-specific terms remain independent.
