# Φ Neural Research: Paired Replication R1

**Status: implemented evidence-only replication screen, not an autonomous training runner.**

This adds a CPU-testable, standard-library-only, read-only analysis module to **PhiRepoNerve**. It evaluates *operator-provided* PhiStream `neural_tiny` runs and the existing RepoNerve `PHI_NEURAL_LAB_R1` receipts. The goal is to stop a single lucky number from being described as reliable model improvement.

## What is now checked

- At least **three**, at most twelve **paired baseline/candidate** experiments. Within each pair, the *declared* random seed is the same; the seed must differ across pairs. This is a reproducibility screen, **not** an independence or significance proof.
- The original dataset file and independent fixed evaluator source are provided and hashed anew. The byte tokenizer specification and the evaluator's context-bound digest are recomputed, not merely compared as strings.
- Each run's original `run-meta.json`, `metrics.log`, exact `neural_tiny.py` source, and RepoNerve receipt are included. The receipts are independently recomputed against their byte-level evidence. Metadata, plan, step count, final `val_bpb`, source SHA, and declared budget are cross-checked.
- **All runs must use the same trainer source bytes**, same declared hardware, tokenizer, dataset, evaluator, context, training step count and resource limits. Within each pair exactly **one** of `lr`, `dim`, `heads`, `layers`, or `batch` may differ, and the same before/after configurations must recur for every seed.
- Aggregate returns per-pair changes, median and mean paired delta (baseline minus candidate), and a strict consistency screen requiring **every** pair to clear the user-declared minimum improvement. It never returns a p-value, model acceptance, promotion permission, or automated agent authority.
- Paths are relative to the local manifest, limited to regular files, never followed through symlinks, with bounded file sizes. It does not run the supplied training code.

## Prepare on your actual RTX 5070

1. Check out the **merged** PhiStream and RepoNerve repositories, update both, and use a dedicated Python environment with a CUDA-capable PyTorch build.
2. From PhiStream, run a **read-only** check of the exact reviewed text file:

```powershell
python -m phistream.neural_tiny preflight --data C:\phi-neural\dataset.txt --context 16
```

3. Deliberately run baseline/candidate for seeds **369, 370, and 371**, with a unique `--run-id` and unique `--out-dir` each time. Use **identical** data, device, context, heads, layers, dim, batch, steps, time and VRAM caps, except for the **single intended change** (example: `--lr` from `0.003` to `0.0025`). Use `--device cuda --approve-training` only if you explicitly approve that local GPU work. Example one run (repeat with matching candidate and two more seeds):

```powershell
python -m phistream.neural_tiny train --data C:\phi-neural\dataset.txt --out-dir C:\phi-neural\baseline369 --device cuda --approve-training --context 16 --dim 32 --heads 2 --layers 1 --batch 4 --steps 12 --lr 0.003 --seconds 120 --vram-mb 10240 --seed 369 --study-id phi-r5 --run-id baseline369
```

4. Record each run from your local RepoNerve checkout:

```powershell
python -m phireponerve.neural_lab record --plan C:\phi-neural\baseline369\plan.json --log C:\phi-neural\baseline369\metrics.log --code C:\src\PhiStream\phistream\neural_tiny.py --out C:\phi-neural\baseline369\receipt.json
```

5. Copy the **exact** trainer source used for that run into its private run directory as `trainer.py`. The generated receipt will be checked against those bytes. Do not update your PhiStream checkout between paired runs unless restarting the entire study. Also copy the exact `phistream/neural_protocol.py` used to score the runs to `C:\phi-neural\neural_protocol.py`.
6. Adapt `examples/neural-replication-bundle-template.json` as `C:\phi-neural\bundle.json`, with relative file paths and the same dataset/evaluator for all runs. Then:

```powershell
python -m phireponerve.neural_replication --bundle C:\phi-neural\bundle.json --out C:\phi-neural\replication-report.json
```

Output is an immutable, local JSON report. No web service, GitHub write, model invocation, or GPU activity is initiated by `neural_replication`.

## Claims and limits

- A completed receipt says **local supplied bytes agree**. It is not cryptographic proof of GPU execution, a trusted machine measurement, or independent evaluator authenticity. A dishonest operator could fabricate internally consistent records.
- Three positive paired results are a **consistency signal**, not a statistically significant result. Small, repeatedly tuned holdouts can be overfit. Use preregistered hypotheses, more seeds, negative controls, fresh independent data, and independent replay before advancing confidence.
- PhiStream's peak allocated CUDA memory omits driver/runtime overhead and is **not** total VRAM; time caps are best effort at step boundaries.
- No scientific discovery is inferred from a language-model benchmark. Do not pass model improvement into PhiDiscovery as chemical evidence.
- This does not save weights or generate a ChatGPT-class model. No private training logs, datasets, or paths should be published to PhiOS Pages.
- Agentora can eventually read this report as *lower-trust evidence*. It cannot accept the candidate, rewrite the evaluator, auto-merge, or authorize deployment.

## Test

```powershell
python -m unittest discover -s tests -p test_neural_replication.py -v
python -m phireponerve.neural_replication --help
```

**Next rung:** on-device, owner-approved RTX 5070 experiment captures with independent replay and a private read-only Observatory view of paired deltas. Keep QA separate from proposing agents.
