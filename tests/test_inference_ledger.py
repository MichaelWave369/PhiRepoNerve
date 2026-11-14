"""R17 PhiServe R15 evidence ledger tests. Synthetic only; no model/GPU execution."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from phireponerve.inference_ledger import (
    INPUT_SCHEMA, SCHEMA, InferenceHeld, analyze, main, render_html, validate,
    write_report,
)

NOW = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
MIB = 1024 ** 2
GIB = 1024 ** 3


def advice(*, alias="test-local", layers=0, snapshot_age=10,
           benchmark_age=120, gpu_free=8 * GIB):
    reserve = GIB
    size = 4 * GIB
    gpu_budget = max(0, gpu_free - reserve) if gpu_free is not None else None
    status = ("HOLD_HARDWARE_OBSERVATION_STALE_OR_FUTURE"
              if snapshot_age < -60 or snapshot_age > 300 else
              "HOLD_BENCHMARK_EVIDENCE_STALE_OR_FUTURE"
              if benchmark_age < -60 or benchmark_age > 7 * 86400 else
              "HOLD_CUDA_COUNTERS_MISSING" if layers > 0 and gpu_free is None else
              "REVIEW_REQUIRED_CAPACITY_NOT_CONFIRMED")
    return {
        "schema": INPUT_SCHEMA,
        "status": "REVIEW_ONLY_NOT_ROUTING_AUTHORITY",
        "evaluated_utc": NOW.isoformat(),
        "classification": status,
        "source": {
            "hardware_snapshot_schema": "PHISTREAM_HARDWARE_SNAPSHOT_V1",
            "hardware_snapshot_file_sha256": "a" * 64,
            "hardware_snapshot_age_seconds": float(snapshot_age),
            "hardware_snapshot_status":
                ("HOLD_FUTURE_TIMESTAMP" if snapshot_age < -60 else
                 "HOLD_STALE_EVIDENCE" if snapshot_age > 300 else
                 "RECENT_OPERATOR_ASSERTED"),
            "model_alias": alias,
            "local_gguf_sha256": "b" * 64,
            "local_gguf_file_bytes": size,
        },
        "capacity_floor": {
            "ram_available_bytes_observed": 24 * GIB,
            "ram_reserve_bytes_selected": 4 * GIB,
            "ram_budget_bytes": 20 * GIB,
            "gpu_free_bytes_observed": gpu_free,
            "gpu_reserve_bytes_selected": reserve,
            "gpu_budget_bytes": gpu_budget,
            "full_cpu_weight_file_floor_met": True,
            "full_gpu_weight_file_floor_met":
                None if gpu_budget is None else size <= gpu_budget,
            "actual_model_working_set_estimated": False,
            "actual_model_fit_verified": False,
            "hybrid_offload_fit_evaluated": False,
        },
        "benchmark_profiles": [{
            "gpu_layers_requested": layers,
            "source_receipt_sha256": "c" * 64,
            "source_age_seconds": float(benchmark_age),
            "source_status":
                ("HOLD_FUTURE_TIMESTAMP" if benchmark_age < -60 else
                 "HOLD_STALE_EVIDENCE" if benchmark_age > 7 * 86400 else
                 "RECENT_OPERATOR_ASSERTED"),
            "wall_p50_ms": 120.0, "wall_p95_ms": 150.0,
            "startup_ms": 700.0,
            "completion_tps_p50_reported": 40.0,
            "reported_token_count_trials": 3,
            "full_gpu_weight_file_floor_met":
                None if gpu_budget is None else size <= gpu_budget,
            "gpu_execution_independently_verified": False,
        }],
        "comparison_limits": ["Fake input, local and unauthenticated"],
        "assurances": {
            "inference_started": False,
            "automatic_model_route": False,
            "execution_authorized": False,
            "gpu_execution_verified": False,
            "physical_hardware_attested": False,
            "performance_improvement_certified": False,
            "model_quality_evaluated": False,
            "remote_upload_performed": False,
        },
    }


class InferenceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / "advice.json"
        self.output = self.root / "out"
        self.write(advice())

    def write(self, payload, *, path=None):
        p = path or self.first
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return p

    def test_source_contract_is_internal_and_no_claims_promoted(self):
        result = analyze([self.first], now=NOW)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "LOCAL_UNSIGNED_REVIEW_TASKS_ONLY")
        self.assertEqual(result["reports"][0]["review_action"],
                         "HUMAN_CAPACITY_REVIEW_REQUIRED")
        self.assertEqual(len(result["review_tasks"]), 1)
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["best_device_selected"])
        self.assertFalse(result["all_source_evidence_replayed"])
        self.assertFalse(result["reports"][0]["machine_identity_authenticated"])

    def test_time_decay_recaptures_snapshot_without_relabeling_r15(self):
        result = analyze([self.first], now=NOW + timedelta(minutes=10))
        self.assertEqual(result["reports"][0]["review_action"],
                         "RECAPTURE_HARDWARE_SNAPSHOT")
        self.assertEqual(result["reports"][0]["r15_reported_classification"],
                         "REVIEW_REQUIRED_CAPACITY_NOT_CONFIRMED")

    def test_old_benchmark_generates_remeasurement_only_when_snapshot_new(self):
        self.write(advice(benchmark_age=7 * 86400 + 30))
        result = analyze([self.first], now=NOW)
        self.assertEqual(result["reports"][0]["review_action"],
                         "REMEASURE_GGUF_BENCHMARKS")

    def test_missing_gpu_counter_creates_collection_ticket(self):
        self.write(advice(layers=18, gpu_free=None))
        result = analyze([self.first], now=NOW)
        self.assertEqual(result["reports"][0]["review_action"], "COLLECT_CUDA_COUNTERS")
        self.assertIsNone(result["reports"][0]["gpu_file_size_floor"])

    def test_future_evidence_causes_hold(self):
        self.write(advice(snapshot_age=-300))
        result = analyze([self.first], now=NOW)
        self.assertEqual(result["reports"][0]["review_action"],
                         "HOLD_CLOCK_OR_FUTURE_TIMESTAMP")

    def test_held_advice_is_not_upgraded_to_approval(self):
        self.write(advice(snapshot_age=301))
        result = analyze([self.first], now=NOW)
        self.assertEqual(result["reports"][0]["review_action"],
                         "RECAPTURE_HARDWARE_SNAPSHOT")
        self.assertFalse(result["automatic_model_routing"])

    def test_multiple_advisories_are_not_performance_ranked(self):
        a = self.write(advice(alias="zeta", layers=0))
        other = self.write(advice(alias="alpha", layers=20),path=self.root / "b.json")
        result = analyze([a, other], now=NOW)
        self.assertEqual([r["model_alias"] for r in result["reports"]],
                         ["alpha", "zeta"])
        self.assertFalse(result["best_device_selected"])
        self.assertNotIn("best_host", json.dumps(result))

    def test_malicious_alias_html_escaped_and_no_paths_published(self):
        malicious = '<img src=x onerror="alert(1)">'
        self.write(advice(alias=malicious))
        result = write_report([self.first], self.output, now=NOW)
        body = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn("&lt;img", body)
        self.assertNotIn(malicious, body)
        self.assertNotIn("<script", body)
        self.assertIn("default-src 'none'", body)
        self.assertNotIn(str(self.root), body)
        self.assertIn("no JavaScript", body) if False else None
        self.assertFalse(result["published"])

    def test_output_exclusive_and_no_second_write(self):
        write_report([self.first], self.output, now=NOW)
        self.assertTrue((self.output / "report.json").exists())
        with self.assertRaisesRegex(InferenceHeld, "OUTPUT_ALREADY_EXISTS"):
            write_report([self.first], self.output, now=NOW)

    def test_refuse_output_inside_git_checkout(self):
        fake_repo = self.root / "repo"
        fake_repo.mkdir()
        (fake_repo / ".git").mkdir()
        with self.assertRaisesRegex(InferenceHeld, "OUTPUT_INSIDE_GIT_CHECKOUT"):
            write_report([self.first],fake_repo / "private-export",now=NOW)
        self.assertFalse((fake_repo / "private-export").exists())

    def test_forged_authority_flag_rejected_without_artifacts(self):
        data = advice()
        data["assurances"]["automatic_model_route"] = True
        self.write(data)
        with self.assertRaisesRegex(InferenceHeld, "FALSE_AUTHORITY_CLAIM"):
            write_report([self.first],self.output,now=NOW)
        self.assertFalse(self.output.exists())

    def test_false_capacity_math_rejected(self):
        for key,value in [("ram_budget_bytes",42),
                          ("full_cpu_weight_file_floor_met",False),
                          ("gpu_budget_bytes",1),
                          ("actual_model_fit_verified",True)]:
            data=advice()
            data["capacity_floor"][key]=value
            self.write(data)
            with self.assertRaises(InferenceHeld):
                analyze([self.first],now=NOW)

    def test_fake_gpu_attestation_rejected(self):
        data=advice(layers=4)
        data["benchmark_profiles"][0]["gpu_execution_independently_verified"]=True
        self.write(data)
        with self.assertRaises(InferenceHeld):
            analyze([self.first],now=NOW)

    def test_inconsistent_r15_classification_rejected(self):
        data=advice()
        data["classification"]="HOLD_CUDA_COUNTERS_MISSING"
        self.write(data)
        with self.assertRaisesRegex(InferenceHeld,"CLASSIFICATION_INCONSISTENT"):
            analyze([self.first],now=NOW)

    def test_duplicate_gpu_layer_profiles_rejected(self):
        data=advice()
        data["benchmark_profiles"].append(copy.deepcopy(data["benchmark_profiles"][0]))
        self.write(data)
        with self.assertRaisesRegex(InferenceHeld,"DUPLICATE_GPU_PROFILE"):
            analyze([self.first],now=NOW)

    def test_duplicate_input_file_rejected(self):
        with self.assertRaisesRegex(InferenceHeld,"DUPLICATE_EVIDENCE_FILES"):
            analyze([self.first,self.first],now=NOW)

    def test_input_symlink_rejected(self):
        link=self.root / "link.json"
        try:
            link.symlink_to(self.first)
        except OSError:
            self.skipTest("Symlinks not available")
        with self.assertRaisesRegex(InferenceHeld,"SYMLINK"):
            analyze([link],now=NOW)

    def test_duplicate_json_key_and_nonfinite_rejected(self):
        self.first.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(InferenceHeld,"DUPLICATE_KEY"):
            analyze([self.first],now=NOW)
        self.first.write_text('{"value":NaN}')
        with self.assertRaisesRegex(InferenceHeld,"JSON_NONFINITE"):
            analyze([self.first],now=NOW)

    def test_invalid_types_and_missing_profiles_refused(self):
        for field,value in [("local_gguf_file_bytes",True),
                            ("local_gguf_file_bytes",0)]:
            data=advice()
            data["source"][field]=value
            self.write(data)
            with self.assertRaises(InferenceHeld):
                analyze([self.first],now=NOW)
        data=advice()
        data["benchmark_profiles"]=[]
        self.write(data)
        with self.assertRaisesRegex(InferenceHeld,"BENCHMARK_COUNT_INVALID"):
            analyze([self.first],now=NOW)

    def test_bounded_size_and_refuse_missing_file(self):
        self.first.write_bytes(b" " * (262144+1))
        with self.assertRaisesRegex(InferenceHeld,"INPUT_OVERSIZED"):
            analyze([self.first],now=NOW)
        with self.assertRaises((OSError,InferenceHeld)):
            analyze([self.root / "nonexistent.json"],now=NOW)

    def test_cli_help(self):
        with self.assertRaises(SystemExit) as e:
            main(["--help"])
        self.assertEqual(e.exception.code,0)


if __name__ == "__main__":
    unittest.main()
