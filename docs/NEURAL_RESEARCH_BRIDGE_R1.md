# Φ Neural Research Bridge R1

**Status: implemented local evidence adapter. Not an autonomous trainer or a verified model.**

The aim is to turn Karpathy's freely available learning tools into a *separable, testable* research network supporting PhiStream, Agentora, PhiRepoNerve, PhiDiscovery, and PhiMathAtelier. R1 lives within PhiRepoNerve and is deliberately offline and non-executing. We do **not** vendor the six projects, merge their license obligations, or publish anybody's model weights.

## Six references, six responsibilities

| Reference | Purpose in the ecosystem | Boundary |
|---|---|---|
| micrograd | Elementary autodiff exercises; inspect gradients visually in PhiMathAtelier | Educational CPU-scale examples |
| nanoGPT | Compare an understandable Transformer to tiny custom PhiStream baselines | Not a production inference backend |
| nanochat | Model lifecycle: tokenizer, pretrain, fine-tune, evaluate, sample | Full reference scripts may need multiple H100 GPUs |
| llm.c | Study C/CUDA kernels and performance tradeoffs against PyTorch | Requires separate compilation and GPU validation |
| autoresearch | Experiments within a tightly scoped, time-bounded training sandbox | H100 reference configuration must be scaled down on 12GB VRAM |
| LLM Wiki Gist | Source-first, agent-maintained, linkable knowledge organization | Idea file; no explicit license in supplied Gist |

Do not conflate *published source code* with *model weights* or trained model capability. Third-party models/datasets have their own terms. The six archives are operator-provided references only; the adapter imports none of their code.

## R1 data flow

```
Upstream experiment (operator runs separately, manually)
   -> pinned dataset / tokenizer / immutable evaluation harness
   -> plan.json (declared experiment context)
   -> finished train.py + run.log
   -> python -m phireponerve.neural_lab record
   -> receipt.json (log and code byte digests, parse, eligibility)
   -> verify / compare (fail closed on changed conditions)
   -> wiki (local markdown export with source links)
   -> future Agentora read-only intake, then reviewed PhiDiscovery claims
```

### First commands

Run in the PhiRepoNerve checkout, with Python 3.11+:

```powershell
python -m unittest discover -s tests -p 'test_neural_lab.py' -v
python -m phireponerve.neural_lab catalog
# Copy examples/neural-plan-example.json to a PRIVATE run folder and replace ALL placeholder SHA-256 values with actual file hashes.
# Run autoresearch separately on a compatible local machine; no training is invoked by these commands.
python -m phireponerve.neural_lab record --plan .\run\plan.json --log .\run\run.log --code .\run\train.py --out .\run\baseline.json
python -m phireponerve.neural_lab verify --receipt .\run\baseline.json --log .\run\run.log --code .\run\train.py
# After a second run with a distinct run_id and the same declared evaluation context:
python -m phireponerve.neural_lab compare --before .\run\baseline.json --after .\run\candidate.json
python -m phireponerve.neural_lab wiki .\run\baseline.json .\run\candidate.json --out .\run\research.md
```

**Do not use the placeholder `a`/`b`/`c` digest strings as evidence.** They exist only to show the schema. A matching operator-declared hash string is not proof a real evaluator was used. To authenticate training, the next rung must independently rerun selected experiments in a locked environment.

## Comparison gate

R1 only accepts a completed autoresearch summary containing `val_bpb`, `training_seconds`, and `peak_vram_mb`. It rejects duplicate/missing metrics, malformed or oversized files, symlinks, changed content, and comparisons with different declared dataset, evaluator, tokenizer, metric, hardware, time budget, or study ID. Out-of-budget and over-VRAM experiments are recorded as **ineligible**, not deleted. Improvement means a smaller `val_bpb` by more than the operator-defined minimum difference, **not** automatic acceptance. All results require human review. No GitHub writes, code execution, network access, downloads, or background scheduling occur.

Do not compare H100 and RTX 5070 results as the same hardware benchmark. Model quality also needs held-out evaluation beyond a single chosen loss. Optimize for meaningful outcomes rather than exploiting one metric.

## Phased handoffs

1. **PhiRepoNerve (R1 implemented):** frozen local plan, log/code integrity receipt, fairness gate, knowledge export. Future: append-only signed receipts and approved data provenance.
2. **PhiStream (future integration):** adapter translates R1 metrics to its existing benchmark receipts; keep `Phi Model Forge` approval and tokenizer gates intact. Do not swap inference weights without separate evidence.
3. **Agentora (future integration):** orchestration uses an explicit allowlisted worktree, spend/time/VRAM quotas, no unattended main-branch pushes, and a hard stop condition. It may propose code changes; it cannot self-certify the evaluator.
4. **PhiDiscovery (future integration):** consumes comparison receipts as **research-process evidence**, not chemical or biological discoveries. Independent domain evidence remains mandatory.
5. **PhiMathAtelier (future integration):** visualize gradient flows, attention heads, metric trajectories, and rejected experiments with provenance.
6. **PhiOS (future integration):** display only reviewed, qualified experiments and models. Default state is research preview, not user-facing production AI.

## Security and claims

- Model-generated text, training logs, imported sources and knowledge notes are lower-trust *data*, never instructions with tool privileges.
- Keep private datasets, logs, local paths, checkpoints, GitHub tokens and operator identifiers off public Pages.
- The tool never runs `train.py`; the SHA hash is byte-integrity, not runtime attestation.
- R1 does not itself know that an operator truthfully pinned their dataset/evaluator. Results are **self-declared and unverified** until an independent replay.
- No autonomy, deployment, scientific discovery, model-quality certification, or 5070 GPU training was performed as part of this code change.

**Exit criteria for R2:** two independently replayed local experiments, auditable data/evaluator digests, locked tool permissions, runtime budget enforcement, matched-configuration comparisons, and an opt-in explicit operator approval before model promotion.