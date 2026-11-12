"""End-to-end evidence and non-execution checks for the Φ Neural Observatory."""
import json
import tempfile
import unittest
from pathlib import Path

from phireponerve import neural_lab as lab
from phireponerve.neural_observatory import (
    ObservatoryHeld, analyze, render_html, write_report, SCHEMA,
)


class ObservatoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.code = self.root / "model.py"
        self.code.write_text("# Synthetic code fixture - never executed\n", encoding="utf-8")

    def make_run(self, rid, score=2.0, steps=8, *, evaluator="b" * 64,
                 log="", admissible=True):
        folder = self.root / rid
        folder.mkdir()
        metrics = folder / "metrics.log"
        metrics.write_text(log or
                           f"val_bpb: {score}\ntraining_seconds: 10.0\npeak_vram_mb: 0.0\nnum_steps: {steps}\n",
                           encoding="utf-8")
        plan = {"schema": "PHI_NEURAL_PLAN_R1", "study_id": "observatory-demo",
                "run_id": rid, "engine": "phi_tiny", "metric": "val_bpb", "direction": "min",
                "dataset_sha256": "a" * 64, "evaluator_sha256": evaluator,
                "tokenizer_sha256": "c" * 64, "hardware_id": "cpu-test",
                "training_budget_seconds": 30.0, "max_peak_vram_mb": 256.0,
                "source_ref": "local-educational-test"}
        receipt = lab.record(plan, metrics, self.code)
        assert receipt["admissible"] == admissible
        (folder / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return {"receipt": f"{rid}/receipt.json", "log": f"{rid}/metrics.log", "code": "model.py"}

    def make_bundle(self, *runs, baseline="baseline", minimum=0.01):
        path = self.root / "bundle.json"
        path.write_text(json.dumps({"schema": SCHEMA, "study_id": "observatory-demo",
                                    "baseline_run_id": baseline, "min_delta_val_bpb": minimum,
                                    "runs": list(runs)}), encoding="utf-8")
        return path

    def test_valid_report_and_html(self):
        a = self.make_run("baseline", score=2.2)
        b = self.make_run("candidate", score=2.1)
        summary = write_report(self.make_bundle(a, b), self.root / "view")
        self.assertEqual(summary["runs"][1]["decision"], "candidate_for_human_review")
        self.assertAlmostEqual(summary["runs"][1]["delta_val_bpb"], 0.1)
        body = (self.root / "view" / "index.html").read_text()
        self.assertIn("Neural Research Observatory", body)
        self.assertIn("no JavaScript", body)
        self.assertNotIn("<script", body)
        self.assertNotIn(str(self.root), body)
        self.assertNotIn("Synthetic code fixture", body)
        self.assertFalse(summary["training_authenticated"] if "training_authenticated" in summary else summary["all_training_authenticated"])

    def test_no_improvement(self):
        a = self.make_run("baseline", score=1.3)
        b = self.make_run("candidate", score=1.31)
        s = analyze(self.make_bundle(a, b))
        self.assertEqual(s["runs"][1]["decision"], "no_measured_improvement")

    def test_evaluator_mismatch_is_held(self):
        a = self.make_run("baseline")
        b = self.make_run("candidate", evaluator="d" * 64)
        s = analyze(self.make_bundle(a, b))
        self.assertEqual(s["runs"][1]["decision"], "comparison_held")

    def test_step_mismatch_is_held(self):
        a = self.make_run("baseline", steps=8)
        b = self.make_run("candidate", steps=9)
        s = analyze(self.make_bundle(a, b))
        self.assertEqual(s["runs"][1]["decision"], "comparison_held")

    def test_code_tampering_rejected_before_output(self):
        a = self.make_run("baseline")
        b = self.make_run("candidate")
        bundle = self.make_bundle(a, b)
        self.code.write_text("# modified after training\n")
        with self.assertRaisesRegex(ObservatoryHeld, "VERIFICATION_FAILED"):
            write_report(bundle, self.root / "view")
        self.assertFalse((self.root / "view").exists())

    def test_log_tampering_rejected(self):
        a = self.make_run("baseline")
        bundle = self.make_bundle(a)
        (self.root / "baseline" / "metrics.log").write_text("val_bpb: 0.001\n")
        with self.assertRaises(ObservatoryHeld):
            analyze(bundle)

    def test_receipt_tampering_rejected(self):
        a = self.make_run("baseline")
        bundle = self.make_bundle(a)
        p = self.root / "baseline" / "receipt.json"
        r = json.loads(p.read_text()); r["metrics"]["val_bpb"] = 0.0001
        p.write_text(json.dumps(r))
        with self.assertRaises(ObservatoryHeld):
            analyze(bundle)

    def test_path_traversal_rejected(self):
        a = self.make_run("baseline")
        a["code"] = "../secret.py"
        with self.assertRaisesRegex(ObservatoryHeld, "PATH_UNSAFE"):
            analyze(self.make_bundle(a))

    def test_windows_absolute_path_rejected(self):
        a = self.make_run("baseline")
        a["code"] = "C:\\Users\\private\\code.py"
        with self.assertRaisesRegex(ObservatoryHeld, "PATH_UNSAFE"):
            analyze(self.make_bundle(a))

    def test_symlinked_input_refused(self):
        a = self.make_run("baseline")
        link = self.root / "link.py"
        try:
            link.symlink_to(self.code)
        except OSError:
            self.skipTest("symlinks unavailable")
        a["code"] = "link.py"
        with self.assertRaisesRegex(ObservatoryHeld, "SYMLINK"):
            analyze(self.make_bundle(a))

    def test_symlinked_parent_refused(self):
        a = self.make_run("baseline")
        link = self.root / "alias"
        try:
            link.symlink_to(self.root / "baseline", target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        a["receipt"] = "alias/receipt.json"
        with self.assertRaisesRegex(ObservatoryHeld, "SYMLINK"):
            analyze(self.make_bundle(a))

    def test_duplicate_run_rejected(self):
        a = self.make_run("baseline")
        with self.assertRaisesRegex(ObservatoryHeld, "DUPLICATE"):
            analyze(self.make_bundle(a, a))

    def test_missing_baseline_rejected(self):
        a = self.make_run("candidate")
        with self.assertRaisesRegex(ObservatoryHeld, "BASELINE_NOT_PRESENT"):
            analyze(self.make_bundle(a))

    def test_existing_output_refused(self):
        a = self.make_run("baseline")
        bundle = self.make_bundle(a)
        out = self.root / "view"
        write_report(bundle, out)
        with self.assertRaisesRegex(ObservatoryHeld, "OUTPUT_ALREADY_EXISTS"):
            write_report(bundle, out)

    def test_invalid_threshold_rejected(self):
        a = self.make_run("baseline")
        with self.assertRaisesRegex(ObservatoryHeld, "THRESHOLD"):
            analyze(self.make_bundle(a, minimum=float("nan")))

    def test_max_runs_enforced(self):
        a = self.make_run("baseline")
        with self.assertRaisesRegex(ObservatoryHeld, "RUN_COUNT"):
            analyze(self.make_bundle(*([a] * 33)))

    def test_empty_or_malformed_bundle_rejected(self):
        path = self.root / "broken.json"
        path.write_text("{}")
        with self.assertRaisesRegex(ObservatoryHeld, "SCHEMA"):
            analyze(path)

    def test_held_experiment_is_not_promoted(self):
        a = self.make_run("baseline", score=2.0)
        b = self.make_run("candidate", score=1.0, log="val_bpb: 1.0\ntraining_seconds: 40.0\npeak_vram_mb: 0.0\nnum_steps: 8\n", admissible=False)
        s = analyze(self.make_bundle(a, b))
        self.assertEqual(s["runs"][1]["decision"], "comparison_held")
        self.assertFalse(s["production_authorized"])


if __name__ == "__main__":
    unittest.main()
