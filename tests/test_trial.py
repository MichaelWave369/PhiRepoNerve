"""Φ Construct structured artifact trials; offline, deterministic, no code execution."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from phireponerve.cli import main
from phireponerve.load import read_packs
from phireponerve.review import ReviewStore
from phireponerve.trial import (
    TrialError, digest, get_task, grade_task, read_submission,
    read_tasks, show_task, task_catalogue, validate_task,
)
from phireponerve.welcome import welcome_charter


class PracticalTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review_db = self.root / "reviews.sqlite3"
        self.store = ReviewStore(self.review_db)
        self.packs = read_packs()
        self.tasks = read_tasks()
        self.task = get_task(self.tasks, "release-gate-repair")

    def tearDown(self):
        self.temp.cleanup()

    def approve(self, task=None):
        item = task or self.task
        pack = next(p for p in self.packs if p["id"] == item["pack_id"])
        self.store.record(pack, "approved", "Reviewed and approved exact reference digest")
        return self.store.status_map(self.packs)

    def solution(self, task=None):
        task = task or self.task
        return {
            "task_digest": digest(task),
            "changes": [
                {"op": "replace", "path": rule["path"], "value": rule["equals"]}
                for rule in task["assertions"]
            ],
        }

    def test_list_includes_two_practical_tasks(self):
        self.assertGreaterEqual(len(self.tasks), 2)
        names = {item["id"] for item in task_catalogue(self.tasks)}
        self.assertIn("release-gate-repair", names)
        self.assertIn("xr-input-fallback-repair", names)
        self.assertFalse(self.review_db.exists())

    def test_task_display_does_not_leak_test_assertions(self):
        approved = self.approve()
        shown = show_task(self.task, self.packs, approved)
        self.assertEqual(shown["charter"], welcome_charter())
        self.assertNotIn("assertions", shown)
        self.assertEqual(shown["task"]["digest"], digest(self.task))
        self.assertEqual(shown["execution_authority"], "none")

    def test_not_approved_fails_closed(self):
        with self.assertRaises(TrialError):
            show_task(self.task, self.packs, self.store.status_map(self.packs))
        with self.assertRaises(TrialError):
            grade_task(self.task, self.solution(), self.packs, self.store.status_map(self.packs))

    def test_valid_patch_repairs_real_json_artifact(self):
        approved = self.approve()
        result = grade_task(self.task, self.solution(), self.packs, approved)
        self.assertTrue(result["artifact_passed"])
        self.assertEqual(result["passed_checks"], result["total_checks"])
        self.assertNotEqual(result["result_artifact_digest"], digest(self.task["initial"]))
        self.assertEqual(result["approved_pack"]["review_status"], "approved")
        self.assertEqual(result["charter"], welcome_charter())
        self.assertFalse(result["agent_identity_verified"])
        self.assertFalse(result["general_competence_verified"])
        self.assertFalse(result["model_executed"])

    def test_wrong_patch_scores_failure_without_execution(self):
        states = self.approve()
        submission = {
            "task_digest": digest(self.task),
            "changes": [{"op": "replace", "path": "/release/status", "value": "blocked"}],
        }
        result = grade_task(self.task, submission, self.packs, states)
        self.assertFalse(result["artifact_passed"])
        self.assertEqual(result["passed_checks"], 1)
        self.assertEqual(result["status"], "artifact_checks_failed")

    def test_unauthorized_patch_and_duplicate_edit_rejected(self):
        states = self.approve()
        bad = self.solution()
        bad["changes"][0]["path"] = "/audit/ticket"
        with self.assertRaises(TrialError):
            grade_task(self.task, bad, self.packs, states)
        bad = self.solution()
        bad["changes"].append(bad["changes"][0])
        with self.assertRaises(TrialError):
            grade_task(self.task, bad, self.packs, states)
        bad = self.solution()
        bad["changes"][0]["op"] = "remove"
        with self.assertRaises(TrialError):
            grade_task(self.task, bad, self.packs, states)

    def test_type_confusion_and_task_drift_fail_closed(self):
        states = self.approve()
        bad = self.solution()
        bad["changes"][1]["value"] = 0
        with self.assertRaises(TrialError):
            grade_task(self.task, bad, self.packs, states)
        bad = self.solution()
        bad["task_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(TrialError):
            grade_task(self.task, bad, self.packs, states)

    def test_modified_pack_invalidates_training_authority(self):
        self.approve()
        changed = dict(next(p for p in self.packs if p["id"] == self.task["pack_id"]))
        changed["knowledge"] = [*changed["knowledge"], "New unreviewed text"]
        packs = [changed if p["id"] == changed["id"] else p for p in self.packs]
        states = self.store.status_map(packs)
        self.assertEqual(states[changed["id"]], "unreviewed")
        with self.assertRaises(TrialError):
            grade_task(self.task, self.solution(), packs, states)

    def test_missing_or_invalid_submission_file_rejected(self):
        target = self.root / "submission.json"
        with self.assertRaises(TrialError):
            read_submission(target)
        target.write_text("{ broken }", encoding="utf-8")
        with self.assertRaises(TrialError):
            read_submission(target)
        target.write_bytes(b"x" * 4097)
        with self.assertRaises(TrialError):
            read_submission(target)

    def test_task_schema_rejects_extra_and_invalid_fields(self):
        bad = dict(self.task)
        bad["shell"] = "rm -rf /"
        with self.assertRaises(TrialError):
            validate_task(bad)
        bad = dict(self.task)
        bad["allowed_paths"] = ["/audit/ticket"]
        with self.assertRaises(TrialError):
            validate_task(bad)
        bad = dict(self.task)
        bad["assertions"] = [{"path": "/release/status", "equals": True}]
        with self.assertRaises(TrialError):
            validate_task(bad)

    def test_xr_trial_passes_without_runtime_or_hardware_claims(self):
        task = get_task(self.tasks, "xr-input-fallback-repair")
        result = grade_task(task, self.solution(task), self.packs, self.approve(task))
        self.assertTrue(result["artifact_passed"])
        self.assertFalse(result["general_competence_verified"])
        self.assertFalse(result["model_executed"])

    def test_cli_list_show_grade(self):
        def call(args):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(args), 0)
            return json.loads(stdout.getvalue())

        common = ["trial", "--reviews-db", str(self.review_db)]
        listed = call(common + ["list"])
        self.assertEqual(listed["tasks"][0]["pack_review_status"], "unreviewed")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                call(common + ["show", "--task", self.task["id"]])
        self.approve()
        shown = call(common + ["show", "--task", self.task["id"]])
        self.assertEqual(shown["task"]["digest"], digest(self.task))
        submission = self.root / "patch.json"
        submission.write_text(json.dumps(self.solution()), encoding="utf-8")
        graded = call(common + ["grade", "--task", self.task["id"],
                                "--submission", str(submission)])
        self.assertTrue(graded["artifact_passed"])
        self.assertEqual(graded["charter"], welcome_charter())


if __name__ == "__main__":
    unittest.main()
