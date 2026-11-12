"""Offline paired-replication screen for Φ tiny-model research.

Read-only evaluation of operator-supplied PhiStream + RepoNerve evidence.
No training, subprocesses, network access, statistical significance claims,
automatic model selection, or deployment authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path, PurePosixPath

from . import neural_lab

SCHEMA = "PHI_NEURAL_REPLICATION_BUNDLE_R1"
REPORT_SCHEMA = "PHI_NEURAL_REPLICATION_REPORT_R1"
MAX_BUNDLE_BYTES = 65536
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_DATASET_BYTES = 1024 * 1024
MIN_PAIRS, MAX_PAIRS = 3, 12
SOURCE_REF = "PhiStream:phistream/neural_tiny.py"
TUNABLE = frozenset({"lr", "dim", "heads", "layers", "batch"})
CONFIG_KEYS = frozenset({"context", "dim", "heads", "layers", "batch", "steps", "lr",
                         "seconds", "vram_mb", "seed", "device", "study_id", "run_id"})
TOKENIZER_SPEC = (
    "phi-byte-v1; UTF-8 byte tokens 0..255; no BOS/EOS; "
    "contiguous last-20-percent holdout; shifted causal windows; "
    "fixed 8 evenly-spaced evaluation windows; log2 bits-per-byte"
)


class ReplicationHeld(ValueError):
    """Insufficiently bounded, incompatible, or altered research evidence."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ReplicationHeld(reason)


def _read_bytes(path: Path, limit: int) -> bytes:
    need(path.is_file() and not path.is_symlink(), "EVIDENCE_MISSING_OR_SYMLINKED")
    need(0 < path.stat().st_size <= limit, "EVIDENCE_SIZE_INVALID")
    data = path.read_bytes()
    need(0 < len(data) <= limit, "EVIDENCE_SIZE_CHANGED")
    return data


def _json(path: Path, limit: int) -> dict:
    try:
        item = json.loads(_read_bytes(path, limit).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReplicationHeld("EVIDENCE_JSON_INVALID") from exc
    need(type(item) is dict, "EVIDENCE_OBJECT_REQUIRED")
    return item


def _safe_path(root: Path, value: str, limit: int) -> Path:
    need(type(value) is str and 1 <= len(value) <= 240 and
         "\\" not in value and ":" not in value and "\x00" not in value,
         "UNSAFE_RELATIVE_PATH")
    pure = PurePosixPath(value)
    need(not pure.is_absolute() and len(pure.parts) <= 12 and
         all(part not in ("", ".", "..") for part in value.split("/")),
         "UNSAFE_RELATIVE_PATH")
    current = root
    for part in pure.parts:
        current = current / part
        need(not current.is_symlink(), "EVIDENCE_SYMLINKED")
    _read_bytes(current, limit)
    return current


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _metric_close(a, b, tolerance=1e-7):
    return (type(a) in (float, int) and type(b) in (float, int) and
            math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tolerance)


def _validate_meta(meta: dict, receipt: dict, data: bytes,
                   evaluator: bytes, trainer: bytes) -> dict:
    plan = receipt["plan"]
    need(meta.get("schema") == "PHI_TINY_TRAIN_R1" and
         meta.get("status") == "LOCAL_TRAINING_COMPLETED_UNVERIFIED" and
         meta.get("plan") == plan, "RUN_METADATA_INVALID_OR_UNBOUND")
    cfg = meta.get("config")
    need(type(cfg) is dict and set(cfg) == CONFIG_KEYS, "CONFIG_FIELDS_INVALID")
    need(type(cfg["seed"]) is int and 0 < cfg["seed"] < 2**31 and
         type(cfg["steps"]) is int and 1 <= cfg["steps"] <= 1000 and
         type(cfg["context"]) is int and 4 <= cfg["context"] <= 128 and
         cfg["device"] in ("cpu", "cuda"), "CONFIG_INVALID")
    need(cfg["run_id"] == plan["run_id"] and
         cfg["study_id"] == plan["study_id"] and
         plan["engine"] == "phi_tiny" and
         plan["source_ref"] == SOURCE_REF and
         plan["hardware_id"].startswith(cfg["device"] + "-"),
         "RUN_CONTEXT_MISMATCH")
    need(_metric_close(cfg["seconds"], plan["training_budget_seconds"]) and
         _metric_close(cfg["vram_mb"], plan["max_peak_vram_mb"]),
         "RUN_BUDGET_MISMATCH")
    need(_sha(data) == plan["dataset_sha256"] and
         _sha(evaluator + f"\ncontext={cfg['context']};windows=8".encode("ascii")) == plan["evaluator_sha256"] and
         _sha(TOKENIZER_SPEC.encode("utf-8")) == plan["tokenizer_sha256"],
         "DATASET_OR_FROZEN_EVALUATOR_MISMATCH")
    need(_sha(trainer) == receipt["code_sha256"] == meta.get("train_code_sha256"),
         "TRAINER_CODE_DIGEST_MISMATCH")
    need(_metric_close(receipt["metrics"].get("num_steps"), cfg["steps"], 1e-9) and
         meta.get("steps") == cfg["steps"] and
         _metric_close(meta.get("final_val_bpb"), receipt["metrics"]["val_bpb"]),
         "RECEIPT_METADATA_METRIC_MISMATCH")
    need(meta.get("evaluator_is_fixed") is True and
         meta.get("training_proven_authentic") is False and
         meta.get("quality_improvement_proven") is False and
         meta.get("production_authorized") is False and
         meta.get("checkpoint_saved") is False and
         meta.get("network_used") is False, "META_AUTHORITY_CLAIMS_INVALID")
    need(receipt["admissible"] is True, "INADMISSIBLE_RUN")
    return cfg


def _read_run(root: Path, descriptor: dict, data: bytes,
              evaluator: bytes, limit: int):
    need(type(descriptor) is dict and set(descriptor) == {"meta", "receipt", "log", "code"},
         "RUN_DESCRIPTOR_INVALID")
    paths = {k: _safe_path(root, v, limit) for k, v in descriptor.items()}
    need(len(set(paths.values())) == 4, "EVIDENCE_PATHS_MUST_BE_DISTINCT")
    receipt = _json(paths["receipt"], limit)
    metadata = _json(paths["meta"], limit)
    try:
        check = neural_lab.verify(receipt, paths["log"], paths["code"])
    except (ValueError, OSError, neural_lab.LabError) as exc:
        raise ReplicationHeld("RECEIPT_VERIFICATION_FAILED") from exc
    need(check.get("verified") is True and check.get("scope") == "integrity_not_authenticity",
         "RECEIPT_VERIFICATION_SCOPE_INVALID")
    cfg = _validate_meta(metadata, receipt, data, evaluator,
                         _read_bytes(paths["code"], limit))
    return {"receipt": receipt, "config": cfg}


def analyze(bundle_path: Path) -> dict:
    """Strictly compare 3..12 independently seeded *declared* paired trials."""
    bundle_path = Path(bundle_path).expanduser()
    need(not bundle_path.is_symlink(), "BUNDLE_SYMLINKED")
    bundle = _json(bundle_path, MAX_BUNDLE_BYTES)
    need(set(bundle) == {"schema", "study_id", "device", "min_delta_val_bpb",
                         "dataset", "evaluator", "pairs"} and bundle["schema"] == SCHEMA,
         "BUNDLE_SCHEMA_INVALID")
    need(type(bundle["study_id"]) is str and 1 <= len(bundle["study_id"]) <= 80 and
         bundle["device"] in ("cpu", "cuda"), "STUDY_OR_DEVICE_INVALID")
    delta_floor = bundle["min_delta_val_bpb"]
    need(type(delta_floor) in (int, float) and math.isfinite(delta_floor) and
         0 <= delta_floor <= 1, "INVALID_MIN_DELTA")
    pairs = bundle["pairs"]
    need(type(pairs) is list and MIN_PAIRS <= len(pairs) <= MAX_PAIRS,
         "REPLICATION_REQUIRES_3_TO_12_PAIRS")
    root = bundle_path.parent.resolve()
    data = _read_bytes(_safe_path(root, bundle["dataset"], MAX_DATASET_BYTES), MAX_DATASET_BYTES)
    evaluator = _read_bytes(_safe_path(root, bundle["evaluator"], MAX_EVIDENCE_BYTES), MAX_EVIDENCE_BYTES)
    seen_seeds, seen_runs, seen_receipts = set(), set(), set()
    baseline_signature = candidate_signature = None
    base_plan = None
    frozen_trainer_sha = None
    changed_parameter = None
    details = []
    for index, item in enumerate(pairs, start=1):
        need(type(item) is dict and set(item) == {"baseline", "candidate"},
             "PAIR_DESCRIPTOR_INVALID")
        before = _read_run(root, item["baseline"], data, evaluator, MAX_EVIDENCE_BYTES)
        after = _read_run(root, item["candidate"], data, evaluator, MAX_EVIDENCE_BYTES)
        bc, cc = before["config"], after["config"]
        need(bc["seed"] == cc["seed"], "PAIR_SEEDS_NOT_MATCHED")
        need(bc["seed"] not in seen_seeds, "REUSED_RANDOM_SEED")
        seen_seeds.add(bc["seed"])
        need(bc["device"] == cc["device"] == bundle["device"], "RUN_DEVICE_MISMATCH")
        different = [key for key in CONFIG_KEYS - {"run_id"} if bc[key] != cc[key]]
        need(len(different) == 1 and different[0] in TUNABLE,
             "EXACTLY_ONE_TUNABLE_CHANGE_REQUIRED")
        need(changed_parameter in (None, different[0]), "TUNABLE_DIFFERS_ACROSS_PAIRS")
        changed_parameter = different[0]
        bsig = {k: v for k, v in bc.items() if k not in ("seed", "run_id")}
        csig = {k: v for k, v in cc.items() if k not in ("seed", "run_id")}
        need(baseline_signature is None or bsig == baseline_signature,
             "BASELINE_CONFIGURATION_DRIFT")
        need(candidate_signature is None or csig == candidate_signature,
             "CANDIDATE_CONFIGURATION_DRIFT")
        baseline_signature, candidate_signature = bsig, csig
        for run in (before, after):
            digest = run["receipt"]["code_sha256"]
            need(frozen_trainer_sha is None or digest == frozen_trainer_sha,
                 "TRAINER_SOURCE_DRIFT_ACROSS_RUNS")
            frozen_trainer_sha = digest
        bp, cp = before["receipt"]["plan"], after["receipt"]["plan"]
        need(bp["study_id"] == cp["study_id"] == bundle["study_id"],
             "STUDY_MISMATCH")
        need(base_plan is None or all(bp[k] == base_plan[k] for k in neural_lab.COMPARE_KEYS),
             "CROSS_PAIR_PLAN_DRIFT")
        base_plan = bp
        for run in (before, after):
            rec = run["receipt"]
            name, fingerprint = rec["plan"]["run_id"], rec["receipt_sha256"]
            need(name not in seen_runs and fingerprint not in seen_receipts,
                 "REUSED_RUN_ID_OR_RECEIPT")
            seen_runs.add(name)
            seen_receipts.add(fingerprint)
        try:
            comparison = neural_lab.compare(before["receipt"], after["receipt"],
                                            min_delta=float(delta_floor))
        except (ValueError, neural_lab.LabError) as exc:
            raise ReplicationHeld("PAIR_COMPARISON_HELD") from exc
        details.append({
            "pair": index,
            "seed": bc["seed"],
            "baseline_run_id": bp["run_id"],
            "candidate_run_id": cp["run_id"],
            "baseline_receipt_sha256": before["receipt"]["receipt_sha256"],
            "candidate_receipt_sha256": after["receipt"]["receipt_sha256"],
            "baseline_val_bpb": before["receipt"]["metrics"]["val_bpb"],
            "candidate_val_bpb": after["receipt"]["metrics"]["val_bpb"],
            "delta_val_bpb": comparison["delta_val_bpb"],
            "cleared_threshold": bool(comparison["improved"]),
        })
    deltas = [x["delta_val_bpb"] for x in details]
    passed = sum(x["cleared_threshold"] for x in details)
    return {
        "schema": REPORT_SCHEMA,
        "study_id": bundle["study_id"], "device_declared": bundle["device"],
        "pair_count": len(details), "pairs_clearing_threshold": passed,
        "controlled_parameter": changed_parameter,
        "baseline_value": baseline_signature[changed_parameter],
        "candidate_value": candidate_signature[changed_parameter],
        "min_delta_val_bpb": float(delta_floor),
        "median_delta_val_bpb": round(statistics.median(deltas), 10),
        "mean_delta_val_bpb": round(statistics.fmean(deltas), 10),
        "pair_results": details,
        "screen": ("consistent_declared_signal_human_review_required"
                   if passed == len(details) else "inconsistent_or_insufficient_declared_signal"),
        "assurance": "operator_declared_local_byte_integrity_not_independent_training_attestation",
        "statistically_significant": False,
        "training_authenticated": False,
        "model_quality_proven": False,
        "production_authorized": False,
        "automatic_agent_decision_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline paired Φ tiny experiment replication screen")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Optional new JSON report, never overwritten")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.bundle)
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.out is not None:
            out = args.out.expanduser()
            need(not out.is_symlink(), "REPORT_SYMLINK_DISALLOWED")
            # No automatic upload, and never put private metadata into the checkout.
            need(not any((parent / ".git").exists() for parent in
                         (out.resolve(), *out.resolve().parents)), "REPORT_INSIDE_GIT_CHECKOUT")
            with out.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        print(payload, end="")
        return 0
    except (ReplicationHeld, OSError, neural_lab.LabError) as exc:
        print("neural-replication held: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
