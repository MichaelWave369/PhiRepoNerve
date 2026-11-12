# Φ Neural Lab: PhiStream tiny-model intake R1.1

**Scope: schema compatibility and fair-comparison guard only.**

The existing `PHI_NEURAL_PLAN_R1` and `PHI_NEURAL_LAB_R1` receipt formats now recognize `engine: "phi_tiny"` in addition to `autoresearch`. No agent or training subprocess is added to RepoNerve. The same `val_bpb`/training-time strict log parser and byte-level file integrity receipts remain in place.

## Important fairness rules

- `engine` remains a required equal comparison field: never compare autoresearch and phi_tiny runs.
- Dataset/evaluator/tokenizer SHA values, declared hardware ID, training budget, metric and study ID must match. PhiStream additionally hashes the fixed evaluator source **including context length** to avoid comparing different window sizes.
- For `phi_tiny`, `num_steps` is required to be a positive integer and **must match** between candidates. Autoresearch remains time-budget based and does not gain this extra fixed-step rule.
- A CPU `peak_vram_mb: 0` is accepted as not applicable; negative VRAM is rejected for all engines. This is not CPU RAM instrumentation.
- Resource-limit, integrity, synthetic-data, self-report, and human-review restrictions are unchanged.

## Local checks

```bash
python -m unittest discover -s tests -p test_neural_lab.py -v
python -m phireponerve.neural_lab catalog
```

Run the PhiStream CPU pilot before trying hardware-specific experiments. On the operator's machine, use `python -m phireponerve.neural_lab record --plan ... --log ... --code ... --out ...` against real local artifacts. Neither a green CI check nor an attractive loss curve is a training authenticity attestation or a deployable Φ model.
