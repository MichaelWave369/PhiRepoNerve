"""Offline invariant checks for the Φ Neural Lab experiment receipt adapter."""
import tempfile
import unittest
from pathlib import Path

from phireponerve.neural_lab import (
    LabError, compare, export_wiki, parse_autoresearch_log, record, verify,
)

H = "a" * 64
LOG = """step 42\n---\nval_bpb: 1.234567\ntraining_seconds: 300.1\ntotal_seconds: 315.4\npeak_vram_mb: 4250.5\nnum_steps: 720\n"""


def plan(run_id="baseline"):
    return {"schema": "PHI_NEURAL_PLAN_R1", "study_id": "toy5070", "run_id": run_id,
            "engine": "autoresearch", "metric": "val_bpb", "direction": "min",
            "dataset_sha256": H, "evaluator_sha256": "b"*64,
            "tokenizer_sha256": "c"*64, "hardware_id": "rtx5070-12gb",
            "training_budget_seconds": 300, "max_peak_vram_mb": 11000,
            "source_ref": "local-autoresearch-snapshot"}


class NeuralLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "run.log"
        self.code = Path(self.tmp.name) / "train.py"
        self.log.write_text(LOG)
        self.code.write_text("# toy model fixture\n")

    def receipt(self, id="baseline"):
        return record(plan(id), self.log, self.code)

    def test_valid_record_can_be_verified(self):
        r = self.receipt()
        self.assertTrue(r["admissible"])
        self.assertTrue(verify(r, self.log, self.code)["verified"])

    def test_tampered_code_is_detected(self):
        r = self.receipt()
        self.code.write_text("# altered\n")
        with self.assertRaises(LabError):
            verify(r, self.log, self.code)

    def test_tampered_receipt_is_detected(self):
        r = self.receipt()
        r["metrics"]["val_bpb"] = 0.01
        with self.assertRaises(LabError):
            compare(r, self.receipt("candidate"))

    def test_duplicate_metric_is_rejected(self):
        with self.assertRaises(LabError):
            parse_autoresearch_log(LOG + "\nval_bpb: 0.01\n")

    def test_missing_metric_is_rejected(self):
        with self.assertRaises(LabError):
            parse_autoresearch_log("val_bpb: 0.5\n")

    def test_nan_not_accepted(self):
        with self.assertRaises(LabError):
            parse_autoresearch_log(LOG.replace("1.234567", "nan"))

    def test_true_improvement(self):
        baseline = self.receipt()
        self.log.write_text(LOG.replace("1.234567", "1.200000"))
        candidate = self.receipt("candidate")
        self.assertTrue(compare(baseline, candidate)["improved"])

    def test_changed_evaluator_not_comparable(self):
        before = self.receipt()
        p = plan("candidate"); p["evaluator_sha256"] = "f"*64
        after = record(p, self.log, self.code)
        with self.assertRaisesRegex(LabError, "evaluator_sha256"):
            compare(before, after)

    def test_changed_hardware_not_comparable(self):
        before = self.receipt()
        p = plan("candidate"); p["hardware_id"] = "h100"
        after = record(p, self.log, self.code)
        with self.assertRaisesRegex(LabError, "hardware_id"):
            compare(before, after)

    def test_vram_oversubscription_ineligible(self):
        p = plan(); p["max_peak_vram_mb"] = 2000
        r = record(p, self.log, self.code)
        self.assertFalse(r["admissible"])
        with self.assertRaisesRegex(LabError, "Ineligible"):
            compare(r, self.receipt("candidate"))

    def test_budget_overrun_ineligible(self):
        self.log.write_text(LOG.replace("300.1", "400.0").replace("315.4", "410.0"))
        r = self.receipt()
        self.assertIn("training_budget_exceeded", r["reasons"])

    def test_wiki_is_source_linked(self):
        text = export_wiki([self.receipt()])
        self.assertIn("karpathy/autoresearch", text)
        self.assertIn("toy5070/baseline", text)

    def test_no_overwrite_new_receipt(self):
        from phireponerve.neural_lab import _save_new
        out = Path(self.tmp.name) / "out.json"
        _save_new(out, "once")
        with self.assertRaises(FileExistsError):
            _save_new(out, "twice")

    def test_symlinked_input_refused(self):
        link = Path(self.tmp.name) / "link.log"
        try:
            link.symlink_to(self.log)
        except OSError:
            self.skipTest("Symlinks not available on this host")
        with self.assertRaises(LabError):
            record(plan(), link, self.code)


if __name__ == "__main__":
    unittest.main()