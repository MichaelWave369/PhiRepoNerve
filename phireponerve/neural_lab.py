"""Φ Neural Lab R1: offline, read-only verification of LLM research run claims.

No external code execution, model loading, network, dependencies, or automatic promotion.
Receipts establish file-byte integrity and *declared* experiment comparability,
not training authenticity or scientific validity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA = "PHI_NEURAL_LAB_R1"
PLAN_SCHEMA = "PHI_NEURAL_PLAN_R1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}\Z")
LINE = re.compile(r"^(val_bpb|training_seconds|total_seconds|peak_vram_mb|num_steps|num_params_M):\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*$")
MAX_BYTES = 4 * 1024 * 1024
COMPARE_KEYS = (
    "engine", "metric", "direction", "dataset_sha256", "evaluator_sha256",
    "tokenizer_sha256", "hardware_id", "training_budget_seconds",
)
REQUIRED_PLAN = {"schema", "study_id", "run_id", *COMPARE_KEYS, "source_ref", "max_peak_vram_mb"}
REFERENCE_CATALOG = (
    ("micrograd", "https://github.com/karpathy/micrograd", "Autodiff educational baseline", "MIT"),
    ("nanoGPT", "https://github.com/karpathy/nanoGPT", "Transformer reference", "MIT"),
    ("nanochat", "https://github.com/karpathy/nanochat", "LLM lifecycle reference", "MIT"),
    ("llm.c", "https://github.com/karpathy/llm.c", "C/CUDA implementation reference", "MIT"),
    ("autoresearch", "https://github.com/karpathy/autoresearch", "Bounded experiment-loop reference", "README states MIT"),
    ("llm-wiki", "https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f", "Knowledge organization reference", "No explicit license in supplied Gist"),
)


class LabError(ValueError):
    """Malformed or incompatible local experiment evidence."""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha_bytes(data: bytes):
    return hashlib.sha256(data).hexdigest()


def _sha_file(path):
    p = Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size > MAX_BYTES:
        raise LabError("Evidence file missing, symlinked, or too large")
    return _sha_bytes(p.read_bytes())


def _read_json(path):
    p = Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size > MAX_BYTES:
        raise LabError("JSON file missing, symlinked, or too large")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LabError("Invalid JSON") from exc


def _number(value, name, *, positive=True):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise LabError("Invalid " + name)
    return float(value)


def _id(value, name):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise LabError("Invalid " + name)
    return value


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != REQUIRED_PLAN or plan["schema"] != PLAN_SCHEMA:
        raise LabError("Plan must use the exact PHI_NEURAL_PLAN_R1 schema")
    for field in ("study_id", "run_id", "engine", "hardware_id"):
        _id(plan[field], field)
    if plan["metric"] != "val_bpb" or plan["direction"] != "min":
        raise LabError("R1 supports only minimizing autoresearch val_bpb")
    if plan["engine"] != "autoresearch":
        raise LabError("R1 supports only autoresearch log ingestion")
    for key in ("dataset_sha256", "evaluator_sha256", "tokenizer_sha256"):
        if not isinstance(plan[key], str) or not HASH.fullmatch(plan[key]):
            raise LabError("Invalid " + key)
    _number(plan["training_budget_seconds"], "training_budget_seconds")
    _number(plan["max_peak_vram_mb"], "max_peak_vram_mb")
    ref = plan["source_ref"]
    if not isinstance(ref, str) or not (1 <= len(ref) <= 200) or any(ord(c) < 32 for c in ref):
        raise LabError("Invalid source_ref")
    return plan


def parse_autoresearch_log(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise LabError("Training log too large")
    found = {}
    for line in text.splitlines():
        match = LINE.fullmatch(line.strip())
        if match:
            key, raw = match.groups()
            if key in found:
                raise LabError("Duplicate metric: " + key)
            found[key] = _number(float(raw), key)
    required = {"val_bpb", "training_seconds", "peak_vram_mb"}
    if not required.issubset(found):
        raise LabError("Missing final autoresearch metric(s): " + ", ".join(sorted(required - found.keys())))
    if "total_seconds" in found and found["total_seconds"] + 1e-6 < found["training_seconds"]:
        raise LabError("Total seconds shorter than training seconds")
    return found


def _receipt_payload(receipt):
    return {key: val for key, val in receipt.items() if key != "receipt_sha256"}


def _check_receipt(receipt):
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise LabError("Invalid receipt schema")
    supplied = receipt.get("receipt_sha256")
    expected = _sha_bytes(_json(_receipt_payload(receipt)).encode("utf-8"))
    if supplied != expected:
        raise LabError("Receipt hash does not match contents")
    validate_plan(receipt.get("plan"))
    if not isinstance(receipt.get("metrics"), dict) or not isinstance(receipt.get("admissible"), bool):
        raise LabError("Receipt structure invalid")
    for field in ("log_sha256", "code_sha256"):
        if not isinstance(receipt.get(field), str) or not HASH.fullmatch(receipt[field]):
            raise LabError("Missing or invalid " + field)
    return receipt


def record(plan, log_path, code_path):
    plan = validate_plan(plan)
    log_sha = _sha_file(log_path)
    code_sha = _sha_file(code_path)
    try:
        metrics = parse_autoresearch_log(Path(log_path).read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise LabError("Log is not UTF-8") from exc
    reasons = []
    if metrics["training_seconds"] > plan["training_budget_seconds"] * 1.05:
        reasons.append("training_budget_exceeded")
    if metrics["peak_vram_mb"] > plan["max_peak_vram_mb"]:
        reasons.append("vram_cap_exceeded")
    receipt = {
        "schema": SCHEMA, "plan": plan.copy(), "metrics": metrics,
        "log_sha256": log_sha, "code_sha256": code_sha,
        "admissible": not reasons, "reasons": reasons,
        "assurance": "self_declared_context_and_byte_integrity_only",
        "promotion": "human_review_required",
    }
    receipt["receipt_sha256"] = _sha_bytes(_json(receipt).encode("utf-8"))
    return receipt


def verify(receipt, log_path, code_path):
    receipt = _check_receipt(receipt)
    recomputed = record(receipt["plan"], log_path, code_path)
    if receipt != recomputed:
        raise LabError("Receipt no longer matches evidence files")
    return {"verified": True, "receipt_sha256": receipt["receipt_sha256"],
            "scope": "integrity_not_authenticity"}


def compare(before, after, *, min_delta=0.0):
    before, after = _check_receipt(before), _check_receipt(after)
    _number(min_delta, "min_delta", positive=False)
    if min_delta < 0:
        raise LabError("min_delta cannot be negative")
    if before["plan"]["study_id"] != after["plan"]["study_id"]:
        raise LabError("Different study IDs")
    changed = [key for key in COMPARE_KEYS if before["plan"][key] != after["plan"][key]]
    if changed:
        raise LabError("Incomparable experiments; changed: " + ", ".join(changed))
    if before["plan"]["run_id"] == after["plan"]["run_id"]:
        raise LabError("Comparison requires two distinct run IDs")
    if not (before["admissible"] and after["admissible"]):
        raise LabError("Ineligible experiment cannot be ranked")
    delta = before["metrics"]["val_bpb"] - after["metrics"]["val_bpb"]
    return {"schema": "PHI_NEURAL_COMPARISON_R1", "study_id": before["plan"]["study_id"],
            "baseline": before["plan"]["run_id"], "candidate": after["plan"]["run_id"],
            "delta_val_bpb": round(delta, 10), "improved": delta > min_delta,
            "decision": "candidate_for_human_review" if delta > min_delta else "no_measured_improvement",
            "limits": "Declares matching evaluation context; does not authenticate it or authorize merging"}


def export_wiki(receipts):
    validated = [_check_receipt(r) for r in receipts]
    lines = ["# Φ Neural Research Ledger", "", "Local, operator-supplied evidence only. No training claims are authenticated.",
             "", "## Sources", ""]
    for name, url, role, license_note in REFERENCE_CATALOG:
        lines.append(f"- [{name}]({url}): {role}. License: {license_note}.")
    lines.extend(["", "## Recorded experiments", ""])
    for r in sorted(validated, key=lambda x: (x["plan"]["study_id"], x["plan"]["run_id"])):
        p, m = r["plan"], r["metrics"]
        lines.append(f"- `{p['study_id']}/{p['run_id']}`: val_bpb={m['val_bpb']:.6f}, "
                     f"peak_vram_mb={m['peak_vram_mb']:.1f}, "
                     f"eligible={'yes' if r['admissible'] else 'no'}, "
                     f"receipt SHA-256 `{r['receipt_sha256']}`")
    lines.extend(["", "Do not interpret model benchmarks as evidence for downstream scientific hypotheses.", ""])
    return "\n".join(lines)


def _save_new(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f:
        f.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline Φ Neural Lab evidence bridge (no model execution)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="List upstream learning references")
    rec = commands.add_parser("record", help="Hash files and parse a completed autoresearch run")
    rec.add_argument("--plan", required=True); rec.add_argument("--log", required=True)
    rec.add_argument("--code", required=True); rec.add_argument("--out", required=True)
    ver = commands.add_parser("verify", help="Recompute a receipt from exact local evidence bytes")
    ver.add_argument("--receipt", required=True); ver.add_argument("--log", required=True); ver.add_argument("--code", required=True)
    cmp = commands.add_parser("compare", help="Compare verified-format receipts under same declared conditions")
    cmp.add_argument("--before", required=True); cmp.add_argument("--after", required=True)
    cmp.add_argument("--min-delta", type=float, default=0.0)
    wiki = commands.add_parser("wiki", help="Export local receipts to source-linked Markdown")
    wiki.add_argument("receipts", nargs="*"); wiki.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            print(json.dumps([dict(name=n, url=u, role=r, license=l) for n, u, r, l in REFERENCE_CATALOG], indent=2))
        elif args.command == "record":
            receipt = record(_read_json(args.plan), args.log, args.code)
            _save_new(args.out, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"saved": args.out, "admissible": receipt["admissible"], "sha256": receipt["receipt_sha256"]}))
        elif args.command == "verify":
            print(json.dumps(verify(_read_json(args.receipt), args.log, args.code), indent=2))
        elif args.command == "compare":
            print(json.dumps(compare(_read_json(args.before), _read_json(args.after), min_delta=args.min_delta), indent=2))
        elif args.command == "wiki":
            _save_new(args.out, export_wiki([_read_json(p) for p in args.receipts]))
            print(json.dumps({"saved": args.out, "receipts": len(args.receipts)}))
    except (LabError, OSError) as exc:
        parser.exit(2, "neural-lab: " + str(exc) + "\n")


if __name__ == "__main__":
    main()