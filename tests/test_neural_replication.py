"""Bounded, adversarial, CPU-only tests for paired replication intake."""
import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from phireponerve import neural_lab, neural_replication as r


class PairedReplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "dataset.txt"
        self.data.write_bytes((b"A tiny synthetic text for training, not genuine research. " * 10))
        self.eval = self.root / "neural_protocol.py"
        self.eval.write_bytes(b"# fixed educational evaluator fixture\n")
        self.bundle = {
            "schema": r.SCHEMA, "study_id": "paired-study", "device": "cpu",
            "min_delta_val_bpb": .002, "dataset": "dataset.txt",
            "evaluator": "neural_protocol.py", "pairs": [],
        }
        for i, seed in enumerate([369, 370, 371], 1):
            self.bundle["pairs"].append({
                "baseline": self.make_run(i, "baseline", seed, .003, 8.2 + i*.001),
                "candidate": self.make_run(i, "candidate", seed, .0025, 8.1 + i*.001),
            })
        self.save()

    def save(self):
        self.manifest = self.root / "bundle.json"
        self.manifest.write_text(json.dumps(self.bundle), encoding="utf-8")

    def make_run(self, i, role, seed, lr, bpb):
        label = f"{role}{i}"
        d = self.root / label
        d.mkdir()
        code = d / "trainer.py"
        code.write_text("# frozen original educational trainer code\n")
        log = d / "metrics.log"
        log.write_text(f"val_bpb: {bpb:.9f}\ntraining_seconds: 4.0\n"
                       "total_seconds: 5.0\npeak_vram_mb: 0.0\n"
                       "num_steps: 12\nnum_params_M: 0.25\n")
        plan = {"schema": neural_lab.PLAN_SCHEMA, "study_id": "paired-study",
                "run_id": label, "engine": "phi_tiny", "metric": "val_bpb",
                "direction": "min", "dataset_sha256": r._sha(self.data.read_bytes()),
                "evaluator_sha256": r._sha(self.eval.read_bytes() + b"\ncontext=16;windows=8"),
                "tokenizer_sha256": r._sha(r.TOKENIZER_SPEC.encode()),
                "hardware_id": "cpu-education-test-fixture", "training_budget_seconds": 120,
                "max_peak_vram_mb": 10240, "source_ref": r.SOURCE_REF}
        receipt = neural_lab.record(plan, log, code)
        (d / "receipt.json").write_text(json.dumps(receipt))
        config = {"context": 16, "dim": 32, "heads": 2, "layers": 1,
                  "batch": 4, "steps": 12, "lr": lr, "seconds": 120,
                  "vram_mb": 10240, "seed": seed, "device": "cpu",
                  "study_id": "paired-study", "run_id": label}
        meta = {"schema": "PHI_TINY_TRAIN_R1",
                "status": "LOCAL_TRAINING_COMPLETED_UNVERIFIED", "plan": plan,
                "config": config, "steps": 12, "final_val_bpb": bpb,
                "train_code_sha256": r._sha(code.read_bytes()),
                "evaluator_is_fixed": True, "training_proven_authentic": False,
                "quality_improvement_proven": False, "production_authorized": False,
                "checkpoint_saved": False, "network_used": False}
        (d / "run-meta.json").write_text(json.dumps(meta))
        return {k: f"{label}/{name}" for k, name in
                (("meta", "run-meta.json"), ("receipt", "receipt.json"),
                 ("code", "trainer.py"), ("log", "metrics.log"))}

    def rewrite_run(self, i=0, role="candidate", *, cfg=None, meta=None, plan=None, log=None):
        desc = self.bundle["pairs"][i][role]
        mpath = self.root / desc["meta"]
        recpath = self.root / desc["receipt"]
        m = json.loads(mpath.read_text())
        rr = json.loads(recpath.read_text())
        if cfg:
            m["config"].update(cfg)
        if meta:
            m.update(meta)
        if plan:
            m["plan"].update(plan)
            rr["plan"].update(plan)
        if log is not None:
            (self.root / desc["log"]).write_text(log)
            rr = neural_lab.record(rr["plan"], self.root / desc["log"],
                                    self.root / desc["code"])
        if plan and log is None:
            rr = neural_lab.record(rr["plan"], self.root / desc["log"],
                                    self.root / desc["code"])
        mpath.write_text(json.dumps(m))
        recpath.write_text(json.dumps(rr))
        self.save()

    def test_valid_three_pairs_not_significance(self):
        out = r.analyze(self.manifest)
        self.assertEqual(out["pair_count"], 3)
        self.assertEqual(out["pairs_clearing_threshold"], 3)
        self.assertEqual(out["controlled_parameter"], "lr")
        self.assertEqual(out["screen"], "consistent_declared_signal_human_review_required")
        self.assertFalse(out["statistically_significant"])
        self.assertFalse(out["production_authorized"])
        self.assertFalse(out["training_authenticated"])
        self.assertEqual(len(out["pair_results"]), 3)
        self.assertNotIn("dataset", json.dumps(out))

    def test_one_loss_worsens_changes_screen(self):
        self.rewrite_run(2, "candidate", meta={"final_val_bpb": 8.5},
                         log="val_bpb: 8.5\ntraining_seconds: 4\ntotal_seconds: 5\npeak_vram_mb: 0\nnum_steps: 12\n")
        out = r.analyze(self.manifest)
        self.assertEqual(out["pairs_clearing_threshold"], 2)
        self.assertEqual(out["screen"], "inconsistent_or_insufficient_declared_signal")

    def test_two_pairs_are_not_accepted(self):
        self.bundle["pairs"].pop()
        self.save()
        with self.assertRaisesRegex(r.ReplicationHeld, "3_TO_12"):
            r.analyze(self.manifest)

    def test_reuse_seed_rejected(self):
        self.rewrite_run(1, "baseline", cfg={"seed": 369})
        self.rewrite_run(1, "candidate", cfg={"seed": 369})
        with self.assertRaisesRegex(r.ReplicationHeld, "REUSED_RANDOM_SEED"):
            r.analyze(self.manifest)

    def test_pair_seed_mismatch_rejected(self):
        self.rewrite_run(0, "candidate", cfg={"seed": 400})
        with self.assertRaisesRegex(r.ReplicationHeld, "SEEDS_NOT_MATCHED"):
            r.analyze(self.manifest)

    def test_two_hyperparameter_changes_rejected(self):
        self.rewrite_run(0, "candidate", cfg={"dim": 48})
        with self.assertRaisesRegex(r.ReplicationHeld, "EXACTLY_ONE"):
            r.analyze(self.manifest)

    def test_change_tunable_across_pairs_rejected(self):
        self.rewrite_run(1, "candidate", cfg={"lr": .0026})
        with self.assertRaisesRegex(r.ReplicationHeld, "CANDIDATE_CONFIGURATION_DRIFT"):
            r.analyze(self.manifest)

    def test_step_count_change_rejected(self):
        self.rewrite_run(0, "candidate", cfg={"steps": 20})
        with self.assertRaisesRegex(r.ReplicationHeld, "METRIC|ONE_TUNABLE"):
            r.analyze(self.manifest)

    def test_source_drift_even_with_new_valid_receipts_rejected(self):
        descriptor = self.bundle["pairs"][0]["candidate"]
        code = self.root / descriptor["code"]
        code.write_text("# alternative valid training implementation\n")
        log = self.root / descriptor["log"]
        old = json.loads((self.root / descriptor["receipt"]).read_text())
        newer = neural_lab.record(old["plan"], log, code)
        (self.root / descriptor["receipt"]).write_text(json.dumps(newer))
        meta = self.root / descriptor["meta"]
        value = json.loads(meta.read_text())
        value["train_code_sha256"] = r._sha(code.read_bytes())
        meta.write_text(json.dumps(value))
        with self.assertRaisesRegex(r.ReplicationHeld, "TRAINER_SOURCE_DRIFT"):
            r.analyze(self.manifest)

    def test_log_tampering_rejected(self):
        desc = self.bundle["pairs"][0]["candidate"]
        (self.root / desc["log"]).write_text("val_bpb: 0\n")
        with self.assertRaisesRegex(r.ReplicationHeld, "RECEIPT_VERIFICATION_FAILED"):
            r.analyze(self.manifest)

    def test_code_tampering_rejected(self):
        desc = self.bundle["pairs"][0]["baseline"]
        (self.root / desc["code"]).write_text("# now different\n")
        with self.assertRaisesRegex(r.ReplicationHeld, "RECEIPT_VERIFICATION_FAILED"):
            r.analyze(self.manifest)

    def test_metadata_claims_cannot_promote(self):
        self.rewrite_run(meta={"production_authorized": True})
        with self.assertRaisesRegex(r.ReplicationHeld, "AUTHORITY"):
            r.analyze(self.manifest)

    def test_missing_true_dataset_rejected(self):
        self.data.write_text("altered data after running")
        with self.assertRaisesRegex(r.ReplicationHeld, "DATASET_OR"):
            r.analyze(self.manifest)

    def test_changed_evaluator_rejected(self):
        self.eval.write_text("changed evaluator code")
        with self.assertRaisesRegex(r.ReplicationHeld, "DATASET_OR"):
            r.analyze(self.manifest)

    def test_no_path_escape(self):
        self.bundle["pairs"][0]["baseline"]["log"] = "../secret.log"
        self.save()
        with self.assertRaisesRegex(r.ReplicationHeld, "UNSAFE_RELATIVE_PATH"):
            r.analyze(self.manifest)

    def test_symlinked_evidence_rejected(self):
        path = self.root / self.bundle["pairs"][0]["candidate"]["code"]
        target = path.with_suffix(".real")
        path.rename(target)
        try:
            path.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(r.ReplicationHeld, "SYMLINKED"):
            r.analyze(self.manifest)

    def test_duplicate_run_id_rejected(self):
        self.rewrite_run(1, "baseline", plan={"run_id": "baseline1"}, cfg={"run_id": "baseline1"})
        with self.assertRaisesRegex(r.ReplicationHeld, "REUSED_RUN_ID_OR_RECEIPT"):
            r.analyze(self.manifest)

    def test_training_budget_exceeded_rejected(self):
        desc = self.bundle["pairs"][0]["candidate"]
        p = json.loads((self.root / desc["receipt"]).read_text())["plan"]
        self.rewrite_run(0, "candidate", meta={"final_val_bpb": 8.101},
                         log="val_bpb: 8.101\ntraining_seconds: 180\ntotal_seconds: 185\npeak_vram_mb: 0\nnum_steps: 12\n")
        with self.assertRaisesRegex(r.ReplicationHeld, "INADMISSIBLE"):
            r.analyze(self.manifest)

    def test_metadata_plan_not_bound(self):
        self.rewrite_run(meta={"plan": {"fake": True}})
        with self.assertRaisesRegex(r.ReplicationHeld, "UNBOUND"):
            r.analyze(self.manifest)

    def test_non_cuda_cannot_forge_cuda_bundle(self):
        self.bundle["device"] = "cuda"
        self.save()
        with self.assertRaisesRegex(r.ReplicationHeld, "RUN_DEVICE_MISMATCH"):
            r.analyze(self.manifest)

    def test_report_output_exclusive(self):
        out = self.root / "report.json"
        self.assertEqual(r.main(["--bundle", str(self.manifest), "--out", str(out)]), 0)
        self.assertTrue(out.is_file())
        self.assertEqual(r.main(["--bundle", str(self.manifest), "--out", str(out)]), 2)


if __name__ == "__main__":
    unittest.main()
