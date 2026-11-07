"""C3 container Code Lab tests: fake Docker executor; never execute candidate code."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from phireponerve.cli import main
from phireponerve.load import read_packs
from phireponerve.review import ReviewStore
from phireponerve.sandbox import (
    SandboxError, _GRADER, _docker_args, catalogue, get_task, read_tasks,
    read_source, run, show, task_digest, validate_task,
)
from phireponerve.welcome import welcome_charter

IMAGE = "python:3.12-alpine@sha256:" + "a" * 64


class FakeDocker:
    """Tests command and output handling without creating containers."""
    def __init__(self, mode="pass"):
        self.calls = []
        self.mode = mode

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[1:3] == ["image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="local-image", stderr="")
        if argv[1] == "run":
            count = 7
            payload = {
                "kind": "code_lab_result",
                "checks": [True] * count if self.mode == "pass" else [False] * count,
            }
            output = "__PHI_CODE_LAB_RESULT__" + json.dumps(payload)
            if self.mode == "malformed":
                output = "not a grader report"
            return SimpleNamespace(
                returncode=0 if self.mode != "fail" else 2,
                stdout=output, stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review_path = self.root / "review.sqlite3"
        self.packs = read_packs()
        self.tasks = read_tasks()
        self.task = get_task(self.tasks, "retry-backoff-code")
        self.src = self.root / "candidate.py"
        self.src.write_text(
            "def retry_delay(attempt):\\n    return min(16, 2 ** max(0, attempt))\\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def approve(self, task=None):
        task = task or self.task
        p = next(p for p in self.packs if p["id"] == task["pack_id"])
        ReviewStore(self.review_path).record(
            p, "approved", "Reviewed source and approved exact digest"
        )
        return ReviewStore(self.review_path).status_map(self.packs)

    def test_listing_and_versioned_fingerprints(self):
        self.assertEqual(len(self.tasks), 2)
        self.assertEqual(validate_task(self.task), self.task)
        self.assertEqual(len(catalogue(self.tasks)), 2)
        self.assertTrue(task_digest(self.task).startswith("sha256:"))

    def test_approval_required_and_hidden_test_cases(self):
        status = ReviewStore(self.review_path).status_map(self.packs)
        with self.assertRaises(SandboxError):
            show(self.task, self.packs, status)
        with self.assertRaises(SandboxError):
            run(self.task, self.packs, status, self.src, IMAGE)
        shown = show(self.task, self.packs, self.approve())
        self.assertNotIn("cases", shown["task"])
        self.assertEqual(shown["charter"], welcome_charter())
        self.assertEqual(shown["execution_authority"], "none_without_explicit_execute_flag")

    def test_preview_does_not_invoke_docker(self):
        fake = FakeDocker()
        report = run(self.task, self.packs, self.approve(), self.src,
                     IMAGE, runner=fake)
        self.assertFalse(report["container_executed"])
        self.assertEqual(report["status"], "preview_not_executed")
        self.assertEqual(fake.calls, [])
        self.assertEqual(report["limits"]["memory_mb"], 128)

    def test_docker_command_is_restricted(self):
        cmd = _docker_args(IMAGE, Path("/isolated/temp"), Path("/isolated/temp/cid"))
        self.assertIn("--network=none", cmd)
        self.assertIn("--read-only", cmd)
        self.assertIn("--pull=never", cmd)
        self.assertIn("--cap-drop=ALL", cmd)
        self.assertIn("--security-opt=no-new-privileges", cmd)
        self.assertIn("--user=65534:65534", cmd)
        self.assertTrue(any(x.startswith("--mount=type=bind") and "readonly" in x for x in cmd))
        self.assertEqual(cmd[0], "docker")
        self.assertNotIn("/var/run/docker.sock", " ".join(cmd))

    def test_fake_container_success_is_not_general_certification(self):
        fake = FakeDocker()
        report = run(self.task, self.packs, self.approve(), self.src,
                     IMAGE, execute=True, runner=fake)
        self.assertTrue(report["container_executed"])
        self.assertEqual(report["status"], "artifact_function_checks_passed")
        self.assertEqual(report["passed"], 7)
        self.assertFalse(report["general_competence_verified"])
        self.assertFalse(report["agent_identity_verified"])
        self.assertFalse(report["host_execution"])
        self.assertEqual(report["charter"], welcome_charter())
        self.assertEqual(len(fake.calls), 2)

    def test_invalid_report_fails_closed(self):
        result = run(self.task, self.packs, self.approve(), self.src,
                     IMAGE, execute=True, runner=FakeDocker("malformed"))
        self.assertEqual(result["status"], "artifact_function_checks_failed")
        self.assertEqual(result["passed"], 0)

    def test_drift_rejected_even_if_local_review_once_approved(self):
        self.approve()
        altered = dict(next(p for p in self.packs if p["id"] == self.task["pack_id"]))
        altered["knowledge"] = [*altered["knowledge"], "New unreviewed line"]
        packs = [altered if x["id"] == altered["id"] else x for x in self.packs]
        states = ReviewStore(self.review_path).status_map(packs)
        with self.assertRaises(SandboxError):
            run(self.task, packs, states, self.src, IMAGE, execute=True, runner=FakeDocker())

    def test_unsafe_images_and_files_rejected(self):
        states = self.approve()
        with self.assertRaises(SandboxError):
            run(self.task, self.packs, states, self.src, "python:latest")
        with self.assertRaises(SandboxError):
            run(self.task, self.packs, states, self.src, "-x@sha256:" + "a" * 64)
        self.src.unlink()
        self.src.write_bytes(b"x" * 8193)
        with self.assertRaises(SandboxError):
            read_source(self.src)
        self.src.unlink()
        self.src.symlink_to(self.root / "other.py")
        with self.assertRaises(SandboxError):
            read_source(self.src)

    def test_malformed_task_rejected(self):
        bad = dict(self.task)
        bad["shell"] = "evil"
        with self.assertRaises(SandboxError):
            validate_task(bad)
        bad = dict(self.task)
        bad["cases"] = [{"args": [0], "expected": {"command": "nope"}}]
        with self.assertRaises(SandboxError):
            validate_task(bad)

    def test_grader_script_is_syntactically_valid_without_execution(self):
        compile(_GRADER, "<trusted-grader-fixture>", "exec")

    def test_cli_list_show_preview(self):
        def call(args):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(args), 0)
            return json.loads(out.getvalue())
        common = ["code", "--reviews-db", str(self.review_path)]
        self.assertEqual(len(call(common + ["list"])["code_tasks"]), 2)
        self.approve()
        shown = call(common + ["show", "--task", self.task["id"]])
        self.assertEqual(shown["task"]["id"], self.task["id"])
        preview = call(common + ["run", "--task", self.task["id"],
                                 "--submission", str(self.src), "--image", IMAGE])
        self.assertEqual(preview["status"], "preview_not_executed")


if __name__ == "__main__":
    unittest.main()
