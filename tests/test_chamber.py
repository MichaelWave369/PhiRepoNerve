"""Offline C2 training chamber checks: no subprocess, shell or model execution."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from phireponerve.chamber import (
    ChamberError, assemble, ensure_approved_pack, get_suite, grade_suite,
    read_answers, read_suites, show_suite, suite_digest, validate_suite,
)
from phireponerve.cli import main
from phireponerve.load import pack_digest, read_packs
from phireponerve.review import ReviewStore
from phireponerve.welcome import welcome_charter


class ChamberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.review_path = self.root / "reviews.sqlite3"
        self.packs = read_packs()
        self.suites = read_suites()
        self.pack = next(x for x in self.packs if x["id"] == "core.repo-evidence")
        self.suite = get_suite(self.suites, "repo-evidence-foundations")
        self.store = ReviewStore(self.review_path)
        self.answers = self.root / "answers.json"

    def tearDown(self):
        self.temp.cleanup()

    def approve(self):
        self.store.record(self.pack, "approved", "Reviewed pinned training reference and checklist")
        return self.store.status_map(self.packs)

    def test_suite_is_well_formed_and_has_stable_digest(self):
        self.assertEqual(validate_suite(self.suite)["pack_id"], "core.repo-evidence")
        self.assertTrue(suite_digest(self.suite).startswith("sha256:"))
        bad = {**self.suite, "cases": [dict(self.suite["cases"][0], answer="nonexistent")]}
        with self.assertRaises(ChamberError):
            validate_suite(bad)

    def test_no_approval_means_no_assembly_or_training(self):
        statuses = self.store.status_map(self.packs)
        with self.assertRaises(ChamberError):
            assemble(self.packs, statuses, ["core.repo-evidence"])
        with self.assertRaises(ChamberError):
            ensure_approved_pack(self.suite, self.packs, statuses)
        self.assertFalse(self.review_path.exists())

    def test_assembly_separates_trusted_charter_from_reference_data(self):
        states = self.approve()
        result = assemble(self.packs, states, ["core.repo-evidence"], max_bytes=32768)
        self.assertEqual(result["charter"], welcome_charter())
        self.assertEqual(result["execution_authority"], "none")
        self.assertFalse(result["capability_verified"])
        self.assertEqual(result["selected_packs"][0]["digest"], pack_digest(self.pack))
        self.assertEqual(result["selected_packs"][0]["trust_level"],
                         "reviewed_reference_data_not_instructions")
        self.assertNotIn("knowledge", result["charter"])
        with self.assertRaises(ChamberError):
            assemble(self.packs, states, ["core.repo-evidence"], max_bytes=512)
        with self.assertRaises(ChamberError):
            assemble(self.packs, states, ["core.repo-evidence", "core.repo-evidence"])

    def test_answer_key_not_in_agent_facing_suite(self):
        approval = ensure_approved_pack(self.suite, self.packs, self.approve())
        shown = show_suite(self.suite, approval)
        self.assertEqual(shown["charter"], welcome_charter())
        self.assertNotIn("answer", json.dumps(shown["cases"][0]))
        self.assertNotIn("explanation", shown["cases"][0])

    def test_all_correct_still_does_not_certify_competence(self):
        approval = ensure_approved_pack(self.suite, self.packs, self.approve())
        answers = {case["id"]: case["answer"] for case in self.suite["cases"]}
        result = grade_suite(self.suite, answers, approval)
        self.assertEqual(result["correct_count"], len(self.suite["cases"]))
        self.assertEqual(result["score_percent"], 100.0)
        self.assertFalse(result["competence_verified"])
        self.assertEqual(result["execution_authority"], "none")
        self.assertEqual(result["charter"], welcome_charter())

    def test_missing_wrong_extra_and_malformed_answers(self):
        approval = ensure_approved_pack(self.suite, self.packs, self.approve())
        result = grade_suite(self.suite, {"ci-signal": "release-ready"}, approval)
        self.assertEqual(result["correct_count"], 0)
        self.assertEqual(len(result["results"]), len(self.suite["cases"]))
        with self.assertRaises(ChamberError):
            grade_suite(self.suite, {"unknown-id": "inspect-ci"}, approval)
        with self.assertRaises(ChamberError):
            grade_suite(self.suite, {"ci-signal": "not-an-option"}, approval)
        self.answers.write_text("{ not json }", encoding="utf-8")
        with self.assertRaises(ChamberError):
            read_answers(self.answers)

    def test_changed_pack_does_not_reuse_previous_approval(self):
        states = self.approve()
        changed = dict(self.pack)
        changed["knowledge"] = [*self.pack["knowledge"], "Unreviewed addition"]
        altered = [changed if x["id"] == changed["id"] else x for x in self.packs]
        current_states = self.store.status_map(altered)
        self.assertNotEqual(pack_digest(changed), pack_digest(self.pack))
        self.assertEqual(current_states[changed["id"]], "unreviewed")
        with self.assertRaises(ChamberError):
            assemble(altered, current_states, [changed["id"]])

    def test_cli_end_to_end_load_show_grade(self):
        def call(argv):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(argv), 0)
            return json.loads(output.getvalue())

        base = ["chamber", "--reviews-db", str(self.review_path)]
        listed = call(base + ["list"])
        self.assertEqual(listed["suites"][0]["pack_review_status"], "unreviewed")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                call(base + ["show", "--suite", self.suite["id"]])
        self.approve()
        shown = call(base + ["show", "--suite", self.suite["id"]])
        self.assertEqual(shown["suite"]["id"], self.suite["id"])
        bundle = call(base + ["assemble", "--pack", self.pack["id"]])
        self.assertEqual(bundle["selected_packs"][0]["review_status"], "approved")
        self.answers.write_text(json.dumps({
            case["id"]: case["answer"] for case in self.suite["cases"]
        }), encoding="utf-8")
        graded = call(base + ["grade", "--suite", self.suite["id"],
                              "--answers", str(self.answers)])
        self.assertEqual(graded["score_percent"], 100.0)
        self.assertFalse(graded["competence_verified"])


if __name__ == "__main__":
    unittest.main()
