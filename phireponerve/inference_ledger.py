"""PhiRepoNerve inference evidence ledger R1: offline planning, NEVER routing.

Consumes operator-supplied PhiServe R15 advisory *summaries*. Does not re-open
R15's referenced source files or attest physical GPU/model execution. Keeps
inputs out of repo and exports only bounded, path-free review tasks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

SCHEMA = "PHIREPONERVE_INFERENCE_EVIDENCE_LEDGER_R1"
INPUT_SCHEMA = "PHISERVE_HARDWARE_ADVICE_R15_V1"
MAX_BYTES = 262144
MAX_REPORTS = 8
HEX = re.compile(r"[0-9a-f]{64}\Z")
STATES = {"RECENT_OPERATOR_ASSERTED", "HOLD_STALE_EVIDENCE", "HOLD_FUTURE_TIMESTAMP"}
CLASSIFICATIONS = {
    "REVIEW_REQUIRED_CAPACITY_NOT_CONFIRMED",
    "HOLD_HARDWARE_OBSERVATION_STALE_OR_FUTURE",
    "HOLD_BENCHMARK_EVIDENCE_STALE_OR_FUTURE",
    "HOLD_CUDA_COUNTERS_MISSING",
}
ASSURANCES = {
    "inference_started", "automatic_model_route", "execution_authorized",
    "gpu_execution_verified", "physical_hardware_attested",
    "performance_improvement_certified", "model_quality_evaluated",
    "remote_upload_performed",
}
PROFILE_KEYS = {
    "gpu_layers_requested", "source_receipt_sha256", "source_age_seconds",
    "source_status", "wall_p50_ms", "wall_p95_ms", "startup_ms",
    "completion_tps_p50_reported", "reported_token_count_trials",
    "full_gpu_weight_file_floor_met", "gpu_execution_independently_verified",
}


class InferenceHeld(ValueError):
    """Unsupported, inconsistent or unsafe claimed inference evidence."""


def require(test: bool, reason: str) -> None:
    if not test:
        raise InferenceHeld(reason)


def exact(value, keys, reason):
    require(type(value) is dict and set(value) == set(keys), reason)


def integer(value, low=0, high=2**62):
    return type(value) is int and low <= value <= high


def finite(value, low=0, high=1e15):
    return type(value) in (float, int) and math.isfinite(value) and low <= value <= high


def utc(value):
    require(type(value) is str and 20 <= len(value) <= 48, "TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InferenceHeld("TIMESTAMP_INVALID") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
            "TIMESTAMP_NOT_UTC")
    return parsed.astimezone(timezone.utc)


def read_json(path: Path):
    path = Path(path).expanduser()
    require(path.is_file() and not path.is_symlink(), "INPUT_MISSING_OR_SYMLINK")
    stat = path.stat()
    require(0 < stat.st_size <= MAX_BYTES, "INPUT_OVERSIZED")
    raw = path.read_bytes()
    require(len(raw) == stat.st_size, "INPUT_CHANGED")
    def no_duplicates(items):
        out = {}
        for key, value in items:
            require(key not in out, "JSON_DUPLICATE_KEY")
            out[key] = value
        return out
    def no_constant(value):
        raise InferenceHeld("JSON_NONFINITE")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                           parse_constant=no_constant)
    except (UnicodeError, ValueError) as exc:
        raise InferenceHeld("INPUT_JSON_INVALID") from exc
    return value, hashlib.sha256(raw).hexdigest()


def validate(value):
    """Re-derive R15 arithmetic and classification; never trust its flags alone."""
    exact(value, {"schema", "status", "evaluated_utc", "classification",
                  "source", "capacity_floor", "benchmark_profiles",
                  "comparison_limits", "assurances"}, "ADVISORY_FIELDS_INVALID")
    require(value["schema"] == INPUT_SCHEMA and
            value["status"] == "REVIEW_ONLY_NOT_ROUTING_AUTHORITY" and
            value["classification"] in CLASSIFICATIONS, "ADVISORY_SCHEMA_INVALID")
    evaluated = utc(value["evaluated_utc"])
    a = value["assurances"]
    exact(a, ASSURANCES, "ASSURANCE_FIELDS_INVALID")
    require(all(a[k] is False for k in ASSURANCES), "FALSE_AUTHORITY_CLAIM")
    s = value["source"]
    exact(s, {"hardware_snapshot_schema", "hardware_snapshot_file_sha256",
              "hardware_snapshot_age_seconds", "hardware_snapshot_status",
              "model_alias", "local_gguf_sha256", "local_gguf_file_bytes"},
          "SOURCE_FIELDS_INVALID")
    require(s["hardware_snapshot_schema"] == "PHISTREAM_HARDWARE_SNAPSHOT_V1" and
            type(s["hardware_snapshot_file_sha256"]) is str and
            HEX.fullmatch(s["hardware_snapshot_file_sha256"]) and
            type(s["local_gguf_sha256"]) is str and HEX.fullmatch(s["local_gguf_sha256"]) and
            type(s["model_alias"]) is str and 1 <= len(s["model_alias"]) <= 128 and
            not any(ord(ch) < 32 for ch in s["model_alias"]) and
            integer(s["local_gguf_file_bytes"], 4) and
            finite(s["hardware_snapshot_age_seconds"], -60, 1e10) and
            s["hardware_snapshot_status"] in STATES,
            "SOURCE_METADATA_INVALID")
    c = value["capacity_floor"]
    exact(c, {"ram_available_bytes_observed", "ram_reserve_bytes_selected",
              "ram_budget_bytes", "gpu_free_bytes_observed",
              "gpu_reserve_bytes_selected", "gpu_budget_bytes",
              "full_cpu_weight_file_floor_met", "full_gpu_weight_file_floor_met",
              "actual_model_working_set_estimated", "actual_model_fit_verified",
              "hybrid_offload_fit_evaluated"}, "CAPACITY_FIELDS_INVALID")
    for key in ("ram_available_bytes_observed", "ram_reserve_bytes_selected",
                "ram_budget_bytes", "gpu_reserve_bytes_selected"):
        require(integer(c[key]), "RAM_COUNTER_INVALID")
    require(c["ram_budget_bytes"] ==
            max(0, c["ram_available_bytes_observed"] - c["ram_reserve_bytes_selected"]) and
            c["full_cpu_weight_file_floor_met"] is
            (s["local_gguf_file_bytes"] <= c["ram_budget_bytes"]),
            "RAM_FLOOR_INCONSISTENT")
    require(c["actual_model_working_set_estimated"] is False and
            c["actual_model_fit_verified"] is False and
            c["hybrid_offload_fit_evaluated"] is False, "MODEL_FIT_FALSE_CLAIM")
    if c["gpu_free_bytes_observed"] is None:
        require(c["gpu_budget_bytes"] is None and
                c["full_gpu_weight_file_floor_met"] is None, "CUDA_MISSING_CONTRADICTION")
    else:
        require(integer(c["gpu_free_bytes_observed"]) and
                integer(c["gpu_budget_bytes"]) and
                c["gpu_budget_bytes"] ==
                max(0, c["gpu_free_bytes_observed"] - c["gpu_reserve_bytes_selected"]) and
                c["full_gpu_weight_file_floor_met"] is
                (s["local_gguf_file_bytes"] <= c["gpu_budget_bytes"]),
                "GPU_FLOOR_INCONSISTENT")
    limits = value["comparison_limits"]
    require(type(limits) is list and 1 <= len(limits) <= 20 and
            all(type(item) is str and len(item) <= 1000 for item in limits),
            "LIMITATIONS_INVALID")
    profiles = value["benchmark_profiles"]
    require(type(profiles) is list and 1 <= len(profiles) <= 8,
            "BENCHMARK_COUNT_INVALID")
    seen = set()
    for p in profiles:
        exact(p, PROFILE_KEYS, "PROFILE_FIELDS_INVALID")
        layers = p["gpu_layers_requested"]
        require(integer(layers, 0, 1024) and layers not in seen, "DUPLICATE_GPU_PROFILE")
        seen.add(layers)
        require(type(p["source_receipt_sha256"]) is str and
                HEX.fullmatch(p["source_receipt_sha256"]) and
                finite(p["source_age_seconds"], -60, 1e10) and
                p["source_status"] in STATES and
                finite(p["wall_p50_ms"]) and finite(p["wall_p95_ms"]) and
                p["wall_p95_ms"] >= p["wall_p50_ms"] and
                finite(p["startup_ms"]) and
                (p["completion_tps_p50_reported"] is None or
                 finite(p["completion_tps_p50_reported"])) and
                integer(p["reported_token_count_trials"], 0, 30) and
                (p["completion_tps_p50_reported"] is None or
                 p["reported_token_count_trials"] > 0) and
                (p["completion_tps_p50_reported"] is not None or
                 p["reported_token_count_trials"] == 0) and
                p["full_gpu_weight_file_floor_met"] is
                c["full_gpu_weight_file_floor_met"] and
                p["gpu_execution_independently_verified"] is False,
                "PROFILE_METRICS_INCONSISTENT")
    expected = ("HOLD_HARDWARE_OBSERVATION_STALE_OR_FUTURE"
                if s["hardware_snapshot_status"] != "RECENT_OPERATOR_ASSERTED"
                else "HOLD_BENCHMARK_EVIDENCE_STALE_OR_FUTURE"
                if any(p["source_status"] != "RECENT_OPERATOR_ASSERTED" for p in profiles)
                else "HOLD_CUDA_COUNTERS_MISSING"
                if c["gpu_free_bytes_observed"] is None and
                any(p["gpu_layers_requested"] > 0 for p in profiles)
                else "REVIEW_REQUIRED_CAPACITY_NOT_CONFIRMED")
    require(value["classification"] == expected, "CLASSIFICATION_INCONSISTENT")
    return evaluated


def analyze(paths, *, now=None):
    """Derived review tasks, not model/host rankings or live admission advice."""
    require(type(paths) in (list, tuple) and 1 <= len(paths) <= MAX_REPORTS,
            "REPORT_COUNT_INVALID")
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None, "CURRENT_TIME_INVALID")
    now = now.astimezone(timezone.utc)
    resolved = [Path(x).expanduser().resolve(strict=True) for x in paths]
    require(len(set(resolved)) == len(resolved), "DUPLICATE_EVIDENCE_FILES")
    reports = []
    for path in paths:
        r, raw_sha = read_json(path)
        observed_at = validate(r)
        drift = (now - observed_at).total_seconds()
        s, c, profiles = r["source"], r["capacity_floor"], r["benchmark_profiles"]
        snapshot_age = s["hardware_snapshot_age_seconds"] + drift
        bench_ages = [p["source_age_seconds"] + drift for p in profiles]
        if snapshot_age < -60 or any(age < -60 for age in bench_ages) or drift < -60:
            action = "HOLD_CLOCK_OR_FUTURE_TIMESTAMP"
        elif snapshot_age > 300:
            action = "RECAPTURE_HARDWARE_SNAPSHOT"
        elif any(age > 7 * 86400 for age in bench_ages):
            action = "REMEASURE_GGUF_BENCHMARKS"
        elif r["classification"] == "HOLD_CUDA_COUNTERS_MISSING":
            action = "COLLECT_CUDA_COUNTERS"
        elif r["classification"] != "REVIEW_REQUIRED_CAPACITY_NOT_CONFIRMED":
            action = "REVIEW_HELD_SOURCE_EVIDENCE"
        else:
            action = "HUMAN_CAPACITY_REVIEW_REQUIRED"
        reports.append({
            "model_alias": s["model_alias"],
            "local_gguf_sha256": s["local_gguf_sha256"],
            "advice_file_sha256": raw_sha,
            "evaluated_utc": observed_at.isoformat(),
            "r15_reported_classification": r["classification"],
            "review_action": action,
            "reported_file_bytes": s["local_gguf_file_bytes"],
            "cpu_file_size_floor": c["full_cpu_weight_file_floor_met"],
            "gpu_file_size_floor": c["full_gpu_weight_file_floor_met"],
            "snapshot_age_at_review_seconds": round(snapshot_age, 3),
            "snapshot_source_hash": s["hardware_snapshot_file_sha256"],
            "profiles": [{
                "gpu_layers_requested": p["gpu_layers_requested"],
                "p50_wall_ms": p["wall_p50_ms"],
                "p95_wall_ms": p["wall_p95_ms"],
                "startup_ms": p["startup_ms"],
                "end_to_end_tokens_per_second": p["completion_tps_p50_reported"],
                "benchmark_age_at_review_seconds":
                    round(p["source_age_seconds"] + drift, 3),
                "source_receipt_sha256": p["source_receipt_sha256"],
            } for p in profiles],
            "machine_identity_authenticated": False,
            "source_json_replayed": False,
            "runtime_fit_verified": False,
            "deployment_authorized": False,
        })
    # Stable reproducible order only; latency comparison across hosts is NOT supported.
    reports.sort(key=lambda p: (p["model_alias"], p["local_gguf_sha256"],
                                p["advice_file_sha256"]))
    return {
        "schema": SCHEMA,
        "created_utc": now.isoformat(),
        "status": "LOCAL_UNSIGNED_REVIEW_TASKS_ONLY",
        "reports": reports,
        "review_tasks": [{"advice_file_sha256": r["advice_file_sha256"],
                          "model_alias": r["model_alias"], "action": r["review_action"]}
                         for r in reports],
        "claim_limits": [
            "R15 inputs are unsigned operator-supplied summaries; original PhiStream/R13 source bytes were not replayed.",
            "Source file hashes, hardware readings, model identity and wall times are NOT independently authenticated.",
            "Comparisons across advisories/hosts are descriptive and NOT controlled speed rankings.",
            "GGUF file-size budgets do not prove working-set fit or hybrid GPU offload.",
            "Recheck live RAM/VRAM, quality, queue pressure and operator permissions before any separate execution approval.",
        ],
        "all_machine_identities_authenticated": False,
        "all_source_evidence_replayed": False,
        "best_device_selected": False,
        "inference_dispatched": False,
        "automatic_model_routing": False,
        "execution_authorized": False,
        "model_quality_verified": False,
        "published": False,
    }


def render_html(report):
    """Static HTML with no scripts/network and escaped operator-supplied labels."""
    esc = lambda value: html.escape(str(value), quote=True)
    sections = []
    for r in report["reports"]:
        trials = "".join(
            "<tr><th scope='row'>{layers}</th><td>{p50:.1f} ms</td>"
            "<td>{p95:.1f} ms</td><td>{startup:.1f} ms</td>"
            "<td>{tps}</td></tr>".format(
                layers=p["gpu_layers_requested"], p50=p["p50_wall_ms"],
                p95=p["p95_wall_ms"], startup=p["startup_ms"],
                tps=("Not reported" if p["end_to_end_tokens_per_second"] is None
                     else f'{p["end_to_end_tokens_per_second"]:.1f} tok/s'))
            for p in r["profiles"])
        sections.append(
            "<article><small>REVIEW ONLY · UNSIGNED SOURCE SUMMARY</small>"
            f"<h2>{esc(r['model_alias'])}</h2>"
            f"<p class='action'>{esc(r['review_action'].replace('_', ' '))}</p>"
            f"<p>R15 status: {esc(r['r15_reported_classification'])}. "
            f"CPU file floor: {r['cpu_file_size_floor']}; "
            f"GPU file floor: {r['gpu_file_size_floor']}.</p>"
            f"<p>GGUF digest (claimed): <code>{esc(r['local_gguf_sha256'])}</code></p>"
            "<div class='scroll'><table><thead><tr><th>GPU layers requested</th>"
            "<th>p50 full request</th><th>p95 full request</th><th>Startup</th>"
            f"<th>Reported end-to-end TPS</th></tr></thead><tbody>{trials}</tbody></table></div>"
            "<p class='disclaimer'>No source-byte replay, verified machine, model-fit proof, "
            "GPU attestation or routing authorization.</p></article>"
        )
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'">
<title>PhiRepoNerve Inference Evidence Ledger</title><style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color-scheme:dark;
background:#111320;color:#e7e7f2}*{box-sizing:border-box}body{margin:0}
main{max-width:1080px;margin:auto;padding:32px 20px 70px}
h1{font-size:clamp(28px,5vw,44px)}.lead{color:#c6c7d6;line-height:1.6}
.summary{padding:17px;border:1px solid #6e6279;background:#27233b;border-radius:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:14px;margin:26px 0}
article{min-width:0;padding:20px;border:1px solid #554960;background:#242033;border-radius:12px}
article small{color:#ceb29a}h2{overflow-wrap:anywhere}code{word-break:break-all;font-size:11px}
.action{color:#f5d293;font-weight:700}.scroll{overflow:auto}table{border-collapse:collapse;min-width:480px;width:100%;font-size:12px}
td,th{padding:9px;border-bottom:1px solid #554960;text-align:left}th{color:#eacaa8}
.disclaimer{font-size:12px;color:#c2bdd0;line-height:1.5}
</style></head><body><main><small>Φ RepoNerve · R17 / OFFLINE EVIDENCE ONLY</small>
<h1>Inference Evidence Ledger</h1>
<p class="lead">Operator-selected PhiServe R15 advisory reports, structurally checked
and converted into non-executable review tasks. No models or GPU processes were run.</p>
<section class="summary"><strong>""" + str(len(report["reports"])) + """ untrusted local summaries</strong>
<p>Source file digests do not authenticate hardware. No optimization winner,
deployment approval, workload routing, dispatch or public publishing.</p></section>
<section class="grid">""" + "\n".join(sections) + """</section>
<p class="disclaimer">Local static HTML · no JavaScript · no external assets · no telemetry.
Do not publish private reports or assume a green test means physical inference.</p>
</main></body></html>"""


def write_report(paths, out_dir, *, now=None):
    """Fail closed before writing; avoid contaminating tracked repositories."""
    result = analyze(paths, now=now)
    dest = Path(out_dir).expanduser()
    require(not dest.exists() and not dest.is_symlink(), "OUTPUT_ALREADY_EXISTS")
    resolved = dest.resolve()
    require(not any((x / ".git").exists() for x in (resolved, *resolved.parents)),
            "OUTPUT_INSIDE_GIT_CHECKOUT")
    require(dest.parent.is_dir() and not dest.parent.is_symlink(), "OUTPUT_PARENT_INVALID")
    dest.mkdir(mode=0o700)
    (dest / "report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (dest / "index.html").write_text(render_html(result), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="phireponerve-inference-ledger",
                                     description="Offline PhiServe R15 human review task ledger")
    parser.add_argument("--advice", action="append", required=True, type=Path,
                        help="Path to an existing local PhiServe R15 advice JSON (repeat up to eight)")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="New private output directory outside a Git checkout")
    args = parser.parse_args(argv)
    try:
        result = write_report(args.advice, args.out_dir)
    except (InferenceHeld, OSError, ValueError) as exc:
        print("inference ledger held: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "reports": len(result["reports"]),
                      "execution_authorized": False, "output_created": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
