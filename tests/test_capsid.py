"""Offline ΦCAPSID tests: targeted review-gated reference delivery, no agent calls."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from phireponerve.capsid import (
    CapsidError, CapsidStore, eligible, manifest_digest, read_json,
    sign_manifest, validate_manifest, verify_envelope,
)
from phireponerve.load import pack_digest, validate_pack
from phireponerve.review import ReviewStore


class CapsidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = CapsidStore(self.root / "capsid.sqlite3")
        self.reviews = ReviewStore(self.root / "reviews.sqlite3")
        self.secret = "ab" * 32
        self.pack = {
            "schema_version": 1, "id": "create.xr-input-triage", "version": "0.1.0",
            "title": "XR triage", "description": "A debugging reference for XR input",
            "events": ["first_observed"], "repo_contains": ["BTM"],
            "knowledge": ["Record device input state first."],
            "provenance": "Operator-curated engineering reference",
        }
        validate_pack(self.pack)
        self.packs = [self.pack]
        self.reviews.record(self.pack, "approved", "Reviewed reference and scope")
        self.manifest = {
            "schema": "phi.capsid.manifest.v1",
            "id": "capsid.xr-input-triage",
            "version": "0.1.0",
            "title": "XR input context",
            "description": "Provide a reviewed input-triage checklist",
            "target": {
                "roles": ["xr-steward"], "repo_contains": ["btm"],
                "required_tags": ["webxr"],
            },
            "capabilities": ["reference.read"],
            "pack": {"id": self.pack["id"], "digest": pack_digest(self.pack)},
            "provenance": "Locally authored capsule, not a verified worker identity",
        }
        self.envelope = sign_manifest(self.manifest, secret=self.secret)
        self.profile = {
            "schema": "phi.capsid.agent-profile.v1", "agent_id": "btm-steward",
            "role": "xr-steward", "repository": "MichaelWave369/BTM",
            "tags": ["webxr"], "allowed_capabilities": ["reference.read"],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def states(self):
        return self.reviews.status_map(self.packs)

    def stage(self, envelope=None, profile=None, states=None):
        return self.store.stage(envelope if envelope is not None else self.envelope,
                                profile if profile is not None else self.profile,
                                self.packs, states if states is not None else self.states(),
                                secret=self.secret)

    def test_stage_activate_context_rollback(self):
        self.assertEqual(verify_envelope(self.envelope, self.secret), self.manifest)
        staged = self.stage()
        self.assertEqual(staged["state"], "staged")
        self.assertFalse(staged["execution_authorized"])
        activated = self.store.activate(staged["stage_id"], self.profile, self.packs,
                                        self.states(), secret=self.secret)
        self.assertEqual(activated["state"], "active_context_only")
        bundle = self.store.context(self.profile, self.packs, self.states(),
                                    secret=self.secret)
        self.assertEqual(bundle["selected_packs"][0]["knowledge"],
                         self.pack["knowledge"])
        self.assertEqual(bundle["capsid"]["target_repo"], "MichaelWave369/BTM")
        self.assertFalse(bundle["capsid"]["tool_permissions_granted"])
        self.assertFalse(bundle["capsid"]["model_weights_modified"])
        self.assertIn("charter", bundle)
        self.assertTrue(self.store.rollback("btm-steward")["rolled_back"])
        with self.assertRaisesRegex(CapsidError, "active"):
            self.store.context(self.profile, self.packs, self.states(),
                               secret=self.secret)
        self.assertFalse(self.store.rollback("btm-steward")["rolled_back"])

    def test_signature_and_key_id_tamper_fail_closed(self):
        for field in ("manifest", "key_id", "signature"):
            tampered = copy.deepcopy(self.envelope)
            if field == "manifest":
                tampered[field]["description"] = "changed without signing"
            elif field == "key_id":
                tampered[field] = "other-key"
            else:
                tampered[field] = "hmac-sha256:" + ("0" * 64)
            with self.subTest(field=field):
                with self.assertRaisesRegex(CapsidError, "signature"):
                    self.stage(envelope=tampered)
        self.assertFalse((self.root / "capsid.sqlite3").exists())

    def test_agent_target_role_repository_tags_and_permissions(self):
        for field, value in (
            ("role", "web-steward"),
            ("repository", "MichaelWave369/Other"),
            ("tags", []),
            ("allowed_capabilities", []),
        ):
            profile = copy.deepcopy(self.profile)
            profile[field] = value
            with self.subTest(field=field):
                with self.assertRaises(CapsidError):
                    self.stage(profile=profile)

    def test_unapproved_pack_and_revocation(self):
        with self.assertRaisesRegex(CapsidError, "not approved"):
            self.stage(states={self.pack["id"]: "unreviewed"})
        staged = self.stage()
        self.store.activate(staged["stage_id"], self.profile, self.packs,
                            self.states(), secret=self.secret)
        self.reviews.record(self.pack, "revoked", "Reference has been withdrawn")
        with self.assertRaisesRegex(CapsidError, "not approved"):
            self.store.context(self.profile, self.packs, self.states(),
                               secret=self.secret)

    def test_changed_pack_digest_rejected_at_activation(self):
        staged = self.stage()
        self.pack["knowledge"].append("Content unexpectedly changed.")
        with self.assertRaisesRegex(CapsidError, "digest changed"):
            self.store.activate(staged["stage_id"], self.profile, self.packs,
                                self.states(), secret=self.secret)
        self.assertEqual(self.store.history("btm-steward")[0]["state"], "staged")

    def test_supersession_is_local_and_rollback_means_baseline(self):
        first = self.stage()
        self.store.activate(first["stage_id"], self.profile, self.packs,
                            self.states(), secret=self.secret)
        second = self.stage()
        self.store.activate(second["stage_id"], self.profile, self.packs,
                            self.states(), secret=self.secret)
        statuses = [v["state"] for v in self.store.history("btm-steward")]
        self.assertEqual(statuses, ["active", "superseded"])
        result = self.store.rollback("btm-steward")
        self.assertFalse(result["restored_prior_version"])
        self.assertEqual([v["state"] for v in self.store.history("btm-steward")],
                         ["rolled_back", "superseded"])

    def test_unapproved_capsule_cannot_bypass_by_forging_status(self):
        staged = self.stage()
        self.assertFalse(hasattr(self.store, "dispatch"))
        changed = copy.deepcopy(self.envelope)
        changed["extra_authority"] = True
        with self.assertRaisesRegex(CapsidError, "envelope"):
            self.stage(envelope=changed)
        self.assertEqual(self.store.history("btm-steward")[0]["id"],
                         staged["stage_id"])

    def test_unknown_capabilities_and_broad_target_rejected(self):
        for mutation in ("unknown", "broad", "extra"):
            manifest = copy.deepcopy(self.manifest)
            if mutation == "unknown":
                manifest["capabilities"] = ["shell.execute"]
            elif mutation == "broad":
                manifest["target"] = {
                    "roles": [], "repo_contains": [], "required_tags": []
                }
            else:
                manifest["execution_authorized"] = True
            with self.subTest(mutation=mutation):
                with self.assertRaises(CapsidError):
                    validate_manifest(manifest)

    def test_cross_agent_activation_rejected_without_state_change(self):
        staged = self.stage()
        profile = copy.deepcopy(self.profile)
        profile["agent_id"] = "another-steward"
        with self.assertRaisesRegex(CapsidError, "Stage not available"):
            self.store.activate(staged["stage_id"], profile, self.packs,
                                self.states(), secret=self.secret)
        self.assertEqual(self.store.history("btm-steward")[0]["state"], "staged")

    def test_pins_and_duplicate_json_keys(self):
        self.assertEqual(manifest_digest(self.manifest),
                         "sha256:" + __import__("hashlib").sha256(
                             json.dumps(self.manifest, sort_keys=True,
                                        separators=(",", ":"), ensure_ascii=False
                                        ).encode("utf-8")).hexdigest())
        file = self.root / "duplicate.json"
        file.write_text('{"id":"one","id":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(CapsidError, "Invalid JSON"):
            read_json(file)


if __name__ == "__main__":
    unittest.main()
