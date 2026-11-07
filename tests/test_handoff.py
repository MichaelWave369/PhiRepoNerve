"""Contract tests for optional Agentora handoff. Never run agents, Docker, or GitHub."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from phireponerve.cli import main
from phireponerve.handoff import (
    HandoffError, create, inspect_report, load_json_file, task_by_mode,
    validate_handoff,
)
from phireponerve.load import read_packs
from phireponerve.review import ReviewStore
from phireponerve import sandbox, trial
from phireponerve.welcome import welcome_charter


class AgentoraHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review_db = self.root / "reviews.sqlite3"
        self.packs = read_packs()
        self.store = ReviewStore(self.review_db)
        self.code_task = task_by_mode("code-lab", "retry-backoff-code")
        self.artifact_task = task_by_mode("artifact-repair", "release-gate-repair")

    def tearDown(self):
        self.temp.cleanup()

    def statuses(self):
        return self.store.status_map(self.packs)

    def approve(self):
        item = next(p for p in self.packs if p["id"] == "core.repo-evidence")
        self.store.record(item, "approved", "Reviewed and approved exact pack digest")
        return self.statuses()

    def handoff(self, mode="code-lab"):
        task = self.code_task if mode == "code-lab" else self.artifact_task
        return create(mode, task, self.packs, self.statuses(),
                      "request-001", "agent-alpha")

    def test_approval_required_for_both_training_modes(self):
        for mode, task in (("code-lab", self.code_task),
                           ("artifact-repair", self.artifact_task)):
            with self.assertRaises(HandoffError):
                create(mode, task, self.packs, self.statuses(),
                       "request-001", "agent-alpha")
        self.assertFalse(self.review_db.exists())

    def test_created_handoff_has_no_authority_and_remains_reconstructable(self):
        self.approve()
        h = self.handoff()
        self.assertEqual(h["charter"], welcome_charter())
        self.assertEqual(h["handoff_state"], "HELD_FOR_AGENTORA_OPERATOR_REVIEW")
        self.assertFalse(h["task_execution_authorized"])
        self.assertFalse(h["merge_authorized"])
        self.assertFalse(h["deployment_authorized"])
        self.assertFalse(h["agent_identity_verified"])
        self.assertFalse(h["worker_lease_issued"])
        self.assertEqual(h["task"]["digest"], sandbox.task_digest(self.code_task))
        self.assertEqual(validate_handoff(h, self.packs, self.statuses())[0], self.code_task)

    def test_tampering_and_authority_escalation_rejected(self):
        self.approve()
        h = self.handoff()
        for changes in (
            {"merge_authorized": True},
            {"agent_identity_verified": True},
            {"handoff_digest": "sha256:" + "0" * 64},
            {"task": {**h["task"], "digest": "sha256:" + "0" * 64}},
            {"elevated_token": "TOKEN"},
        ):
            modified = {**h, **changes}
            with self.assertRaises(HandoffError):
                validate_handoff(modified, self.packs, self.statuses())

    def test_revocation_or_drift_fails_closed(self):
        self.approve()
        h = self.handoff()
        item = next(p for p in self.packs if p["id"] == "core.repo-evidence")
        self.store.record(item, "revoked", "Explicit withdrawal of local approval")
        with self.assertRaises(HandoffError):
            validate_handoff(h, self.packs, self.statuses())
        self.store.record(item, "approved", "Reapproval of the same reviewed content")
        changed = {**item, "knowledge": [*item["knowledge"], "Unauthorized addition"]}
        packs = [changed if x["id"] == item["id"] else x for x in self.packs]
        with self.assertRaises(HandoffError):
            validate_handoff(h, packs, self.store.status_map(packs))

    def test_code_preview_is_held_not_run(self):
        self.approve()
        h = self.handoff()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         dir=self.root, encoding="utf-8") as source:
            source.write("def retry_delay(n): return 1\n")
            source.flush()
            report = sandbox.run(
                self.code_task, self.packs, self.statuses(),
                source.name, "python:3.12-alpine@sha256:" + "a" * 64,
                execute=False,
            )
        result = inspect_report(h, report, self.packs, self.statuses())
        self.assertEqual(result["candidate_claim"], "not_run")
        self.assertFalse(result["independent_evidence_verified"])
        self.assertEqual(result["state"], "HELD_AWAITING_INDEPENDENT_ATTESTATION")

    def test_fake_pass_report_cannot_promote_to_verified(self):
        self.approve()
        h = self.handoff()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         dir=self.root, encoding="utf-8") as source:
            source.write("def retry_delay(n): return 1\n")
            source.flush()
            report = sandbox.run(
                self.code_task, self.packs, self.statuses(), source.name,
                "python:3.12-alpine@sha256:" + "a" * 64, execute=False,
            )
        report.pop("limits")
        report.update({
            "container_executed": True, "passed": 7, "total": 7,
            "checks": [True] * 7, "exit_code": 0,
            "status": "artifact_function_checks_passed",
        })
        result = inspect_report(h, report, self.packs, self.statuses())
        self.assertEqual(result["candidate_claim"], "reported_pass")
        self.assertFalse(result["receipt_source_authenticated"])
        self.assertFalse(result["agent_identity_verified"])
        self.assertFalse(result["execution_authorized"])

    def test_forged_claim_or_unpinned_image_rejected(self):
        self.approve()
        h = self.handoff()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         dir=self.root, encoding="utf-8") as source:
            source.write("def retry_delay(n): return 1\n")
            source.flush()
            report = sandbox.run(self.code_task, self.packs, self.statuses(),
                                 source.name, "python:3.12-alpine@sha256:" + "a"*64)
        report["agent_identity_verified"] = True
        with self.assertRaises(HandoffError):
            inspect_report(h, report, self.packs, self.statuses())
        report["agent_identity_verified"] = False
        report["image"] = "python:latest"
        with self.assertRaises(HandoffError):
            inspect_report(h, report, self.packs, self.statuses())

    def test_artifact_repair_receipt_only_provides_unattested_observation(self):
        self.approve()
        h = self.handoff("artifact-repair")
        submission = {
            "task_digest": trial.digest(self.artifact_task),
            "changes": [
                {"op": "replace", "path": assertion["path"],
                 "value": assertion["equals"]}
                for assertion in self.artifact_task["assertions"]
            ],
        }
        report = trial.grade_task(
            self.artifact_task, submission, self.packs, self.statuses()
        )
        result = inspect_report(h, report, self.packs, self.statuses())
        self.assertEqual(result["candidate_claim"], "reported_pass")
        self.assertFalse(result["independent_evidence_verified"])
        self.assertFalse(result["merge_authorized"])

    def test_untrusted_files_are_bounded_regular_json_only(self):
        path = self.root / "input.json"
        with self.assertRaises(HandoffError):
            load_json_file(path)
        path.write_text("not-json", encoding="utf-8")
        with self.assertRaises(HandoffError):
            load_json_file(path)
        path.write_bytes(b"x" * 65537)
        with self.assertRaises(HandoffError):
            load_json_file(path)
        path.unlink()
        path.symlink_to(self.root / "missing")
        with self.assertRaises(HandoffError):
            load_json_file(path)

    def test_cli_round_trip_without_agent_execution(self):
        self.approve()
        def call(args):
            with contextlib.redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(args), 0)
            return json.loads(stream.getvalue())
        args = ["handoff", "--reviews-db", str(self.review_db)]
        request = call(args + [
            "create", "--mode", "code-lab", "--task", "retry-backoff-code",
            "--request-id", "request-001", "--agent-label", "agent-alpha",
        ])
        self.assertEqual(request["handoff_state"], "HELD_FOR_AGENTORA_OPERATOR_REVIEW")
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         dir=self.root, encoding="utf-8") as source:
            source.write("def retry_delay(n): return 1\n")
            source.flush()
            report = sandbox.run(
                self.code_task, self.packs, self.statuses(), source.name,
                "python:3.12-alpine@sha256:" + "a" * 64,
            )
        report_path = self.root / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        result = call(args + [
            "inspect", "--request", str(request_path), "--report", str(report_path),
        ])
        self.assertEqual(result["candidate_claim"], "not_run")
        self.assertFalse(result["dispatch_authorized"])


if __name__ == "__main__":
    unittest.main()
