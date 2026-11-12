"""Local, read-only Φ Neural Observatory for byte-verified research receipts.

No scripts, HTML imports, dynamic network requests, model execution, or unattended
promotion. Source bytes are operator supplied: integrity is NOT authenticity.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath

from . import neural_lab

SCHEMA = "PHI_NEURAL_OBSERVATORY_BUNDLE_R1"
OUTPUT_SCHEMA = "PHI_NEURAL_OBSERVATORY_REPORT_R1"
MAX_BUNDLE_BYTES = 65536
MAX_RUNS = 32
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


class ObservatoryHeld(ValueError):
    """Fail closed on untrusted or incompatible research inputs."""


def _require(ok, reason):
    if not ok:
        raise ObservatoryHeld(reason)


def _json_file(path: Path, max_size: int):
    _require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= max_size,
             "INPUT_MISSING_OR_OVERSIZED")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ObservatoryHeld("INPUT_JSON_INVALID") from exc


def _safe_relative(root: Path, user_path: str) -> Path:
    """Accept only bounded POSIX-style paths, with no symlink in any component."""
    _require(isinstance(user_path, str) and 1 <= len(user_path) <= 240
             and "\\" not in user_path and ":" not in user_path and "\x00" not in user_path,
             "EVIDENCE_PATH_UNSAFE")
    p = PurePosixPath(user_path)
    _require(not p.is_absolute() and not user_path.startswith("/")
             and all(part not in ("", ".", "..") for part in user_path.split("/"))
             and len(p.parts) <= 12, "EVIDENCE_PATH_UNSAFE")
    cur = root
    for item in p.parts:
        cur = cur / item
        _require(not cur.is_symlink(), "EVIDENCE_SYMLINK_DISALLOWED")
    _require(cur.is_file(), "EVIDENCE_FILE_MISSING")
    return cur


def _load_bundle(bundle_path: Path):
    path = Path(bundle_path).expanduser()
    _require(not path.is_symlink(), "BUNDLE_SYMLINK_DISALLOWED")
    data = _json_file(path, MAX_BUNDLE_BYTES)
    root = path.parent.resolve()
    _require(isinstance(data, dict) and set(data) ==
             {"schema", "study_id", "baseline_run_id", "min_delta_val_bpb", "runs"}
             and data["schema"] == SCHEMA, "BUNDLE_SCHEMA_INVALID")
    for field in ("study_id", "baseline_run_id"):
        _require(isinstance(data[field], str) and NAME.fullmatch(data[field]),
                 "BUNDLE_ID_INVALID")
    threshold = data["min_delta_val_bpb"]
    _require(type(threshold) in (int, float) and math.isfinite(threshold) and
             0 <= threshold <= 10, "BUNDLE_THRESHOLD_INVALID")
    runs = data["runs"]
    _require(isinstance(runs, list) and 1 <= len(runs) <= MAX_RUNS, "BUNDLE_RUN_COUNT_INVALID")
    found = {}
    for row in runs:
        _require(isinstance(row, dict) and set(row) == {"receipt", "log", "code"},
                 "BUNDLE_RUN_ENTRY_INVALID")
        files = {k: _safe_relative(root, row[k]) for k in ("receipt", "log", "code")}
        receipt = _json_file(files["receipt"], neural_lab.MAX_BYTES)
        try:
            check = neural_lab.verify(receipt, files["log"], files["code"])
        except (neural_lab.LabError, OSError, ValueError) as exc:
            raise ObservatoryHeld("RUN_INTEGRITY_VERIFICATION_FAILED") from exc
        _require(check.get("verified") is True and check.get("scope") == "integrity_not_authenticity",
                 "RUN_INTEGRITY_VERIFICATION_FAILED")
        plan = receipt["plan"]
        _require(plan["study_id"] == data["study_id"], "STUDY_ID_MISMATCH")
        run_id = plan["run_id"]
        _require(run_id not in found, "DUPLICATE_RUN_ID")
        found[run_id] = receipt
    _require(data["baseline_run_id"] in found, "BASELINE_NOT_PRESENT")
    return data, found


def analyze(bundle_path: Path) -> dict:
    """Inspect real local evidence files, never execute their source code."""
    bundle, receipts = _load_bundle(bundle_path)
    baseline_id = bundle["baseline_run_id"]
    baseline = receipts[baseline_id]
    records = []
    for run_id in [baseline_id] + sorted(k for k in receipts if k != baseline_id):
        r = receipts[run_id]
        entry = {
            "run_id": run_id,
            "role": "baseline" if run_id == baseline_id else "candidate",
            "val_bpb": r["metrics"]["val_bpb"],
            "training_seconds": r["metrics"]["training_seconds"],
            "peak_vram_mb": r["metrics"]["peak_vram_mb"],
            "num_steps": r["metrics"].get("num_steps"),
            "admissible": r["admissible"],
            "receipt_sha256": r["receipt_sha256"],
            "integrity_check": "local_bytes_match",
            "training_authenticated": False,
            "decision": "reference_only" if run_id == baseline_id else "comparison_held",
            "delta_val_bpb": None,
        }
        if run_id != baseline_id:
            try:
                result = neural_lab.compare(baseline, r,
                                            min_delta=float(bundle["min_delta_val_bpb"]))
                entry["decision"] = result["decision"]
                entry["delta_val_bpb"] = result["delta_val_bpb"]
            except (neural_lab.LabError, ValueError):
                # Avoid exposing arbitrary source metadata or claiming comparability.
                entry["decision"] = "comparison_held"
        records.append(entry)
    return {
        "schema": OUTPUT_SCHEMA, "study_id": bundle["study_id"],
        "baseline_run_id": baseline_id, "min_delta_val_bpb": float(bundle["min_delta_val_bpb"]),
        "runs": records,
        "assurance": "operator_supplied_local_file_integrity_not_training_authenticity",
        "all_training_authenticated": False, "model_quality_proven": False,
        "production_authorized": False, "sources_or_model_weights_published": False,
    }


def render_html(report: dict) -> str:
    """Fully static, dependency-free HTML. No user source code or raw text embedded."""
    rows = report["runs"]
    largest = max(r["val_bpb"] for r in rows)
    escape = lambda x: html.escape(str(x), quote=True)
    def card(row):
        pct = max(2.0, min(100.0, float(row["val_bpb"]) / largest * 100))
        state = row["decision"]
        labels = {
            "reference_only": "Baseline",
            "comparison_held": "Not comparable / held",
            "no_measured_improvement": "No qualifying improvement",
            "candidate_for_human_review": "Lower loss · review needed",
        }
        label = labels.get(state, "Held")
        delta = ("Not comparable" if row["delta_val_bpb"] is None
                 else f"{row['delta_val_bpb']:+.6f} bits/byte vs baseline")
        return f'''<article class="record"><div class="record-title"><h3>{escape(row['run_id'])}</h3><span class="tag {escape(state)}">{escape(label)}</span></div>
<div class="bar-track" role="img" aria-label="Held-out loss: {row['val_bpb']:.6f} bits per byte"><div class="bar" style="width:{pct:.3f}%"></div></div>
<div class="score"><strong>{row['val_bpb']:.6f}</strong> <small>held-out bits/byte · lower is better</small></div>
<dl><div><dt>Comparison</dt><dd>{escape(delta)}</dd></div><div><dt>Train time</dt><dd>{row['training_seconds']:.2f}s</dd></div>
<div><dt>Peak allocated VRAM</dt><dd>{row['peak_vram_mb']:.1f} MiB</dd></div><div><dt>Local file integrity</dt><dd>Matched</dd></div></dl>
<p class="hash">Receipt SHA-256: {escape(row['receipt_sha256'])}</p></article>'''
    body = "\n".join(card(r) for r in rows)
    count = sum(r["decision"] == "candidate_for_human_review" for r in rows)
    held = sum(r["decision"] == "comparison_held" for r in rows)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'">
<title>Φ Neural Research Observatory</title><style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;background:#0b1120;color:#e7eefc}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1150px;margin:0 auto;padding:48px 24px 80px}}
.eyebrow{{letter-spacing:.19em;color:#84c7f9;text-transform:uppercase;font-size:11px;font-weight:750}}
h1{{font-size:clamp(30px,5vw,52px);margin:12px 0;line-height:1.1}}.lead{{max-width:780px;line-height:1.7;color:#b4c4db}}
.summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:32px 0}}
.stat{{background:#15223a;border:1px solid #253a57;border-radius:14px;padding:21px}}
.stat b{{font-size:27px;display:block}}.stat span{{font-size:12px;color:#a7b9d2}}
.records{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:16px}}
.record{{border:1px solid #273c58;background:#131e31;border-radius:18px;padding:23px;min-width:0}}
.record-title{{display:flex;justify-content:space-between;align-items:start;gap:12px;flex-wrap:wrap}}h3{{margin:0 0 18px;font-size:18px}}
.tag{{font-size:11px;padding:6px 9px;border-radius:8px;background:#283951;color:#d9e8f8}}
.candidate_for_human_review{{background:#163e3d;color:#98e5d0}}
.comparison_held{{background:#4b302e;color:#f6c0b4}}
.bar-track{{height:10px;background:#2b3b50;border-radius:9px;overflow:hidden}}
.bar{{height:100%;background:linear-gradient(90deg,#49b8ed,#9caafc);border-radius:9px}}
.score{{margin:11px 0 22px}}.score strong{{font-size:22px}}small,dt{{color:#adbed3}}
dl{{display:grid;grid-template-columns:1fr 1fr;gap:16px 8px;margin:0}}dt{{font-size:11px}}dd{{margin:5px 0 0;font-size:13px}}.hash{{font-size:10px;line-height:1.6;word-break:break-all;color:#8299b9;margin-top:20px}}
.warning{{margin-top:28px;border-left:3px solid #72b9f1;background:#14263a;padding:20px 24px;line-height:1.7;color:#c4d3e5}}
.footer{{font-size:12px;margin-top:34px;color:#91a5be}}
@media(max-width:600px){{.summary{{grid-template-columns:1fr}}main{{padding:32px 16px}}}}
</style></head><body><main><p class="eyebrow">Phi369 Labs · Local research evidence</p>
<h1>Φ Neural Research Observatory</h1><p class="lead">Study <b>{escape(report['study_id'])}</b> · Baseline <b>{escape(report['baseline_run_id'])}</b>. Fixed-protocol experiment comparisons based on operator-supplied files. No model training occurs here.</p>
<div class="summary"><div class="stat"><b>{len(rows)}</b><span>Locally checked runs</span></div><div class="stat"><b>{count}</b><span>Measured lower loss; human review required</span></div><div class="stat"><b>{held}</b><span>Comparisons held</span></div></div>
<section class="records" aria-label="Experiments">{body}</section>
<section class="warning"><strong>Evidence boundaries.</strong> Local SHA-256 receipts and log/code-file checks verify the supplied bytes, not that hardware executed the training, that the dataset was ethically sourced, or that a model improved in real-world performance. A single measured decrease is not statistically established. This report grants no training, deployment, or merge authority. Keep private artifacts off public sites.</section>
<p class="footer">Offline export · no JavaScript · no external assets · no telemetry</p></main></body></html>'''


def write_report(bundle_path: Path, output_dir: Path) -> dict:
    report = analyze(bundle_path)
    target = Path(output_dir).expanduser()
    _require(not target.exists() and not target.is_symlink(), "OUTPUT_ALREADY_EXISTS")
    # Do not create a directory in any existing checkout, so private evidence
    # cannot accidentally become part of the repo or a GitHub Pages deployment.
    resolved = target.resolve()
    _require(not any((ancestor / ".git").exists() for ancestor in (resolved, *resolved.parents)),
             "OUTPUT_INSIDE_GIT_CHECKOUT")
    _require(target.parent.exists() and target.parent.is_dir() and not target.parent.is_symlink(),
             "OUTPUT_PARENT_INVALID")
    target.mkdir(mode=0o700)
    (target / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (target / "index.html").write_text(render_html(report), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Φ Neural Observatory: offline static research report")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = write_report(args.bundle, args.out_dir)
        print(json.dumps({"status": "LOCAL_INTEGRITY_CHECKS_PASSED", "runs": len(report["runs"]),
                          "output_created": True, "training_authenticated": False}, sort_keys=True))
        return 0
    except (ObservatoryHeld, neural_lab.LabError, OSError, ValueError) as exc:
        print("neural-observatory held: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
