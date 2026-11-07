"""ΦConstruct Agentora training bridge: local, read-only, NON-authorizing contracts.

These JSON envelopes only pin a reviewed pack and diagnostic task; imported
reports are NOT authenticated or independently verified. No agent is dispatched.
"""
import hashlib
import json
from pathlib import Path
import re

from .chamber import ChamberError, ensure_approved_pack
from .load import pack_digest
from .welcome import welcome_charter, with_charter
from . import sandbox, trial

SCHEMA = "phi.construct.training-handoff.v0.1"
RECEIPT_SCHEMA = "phi.construct.training-report-intake.v0.1"
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}\Z")
SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_FILE_BYTES = 65536


class HandoffError(ValueError):
    """Untrusted or inconsistent handoff/receipt. No permission is granted."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value):
    try:
        return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()
    except (TypeError, ValueError, RecursionError) as exc:
        raise HandoffError("Cannot fingerprint JSON value") from exc


def load_json_file(path):
    """Local regular JSON file only, limited size; do not follow symlinks."""
    file = Path(path)
    if file.is_symlink() or not file.is_file() or not 0 < file.stat().st_size <= MAX_FILE_BYTES:
        raise HandoffError("Input must be a regular non-empty JSON file under 64KiB")
    try:
        return json.loads(file.read_text(encoding="utf-8"),
                          parse_constant=lambda n: (_ for _ in ()).throw(ValueError(n)))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise HandoffError("Cannot parse input JSON") from exc


def task_by_mode(mode, identifier, code_tasks=None, trial_tasks=None):
    if mode == "code-lab":
        try:
            return sandbox.get_task(sandbox.read_tasks(code_tasks), identifier)
        except sandbox.SandboxError as exc:
            raise HandoffError(str(exc)) from exc
    if mode == "artifact-repair":
        try:
            return trial.get_task(trial.read_tasks(trial_tasks), identifier)
        except trial.TrialError as exc:
            raise HandoffError(str(exc)) from exc
    raise HandoffError("Unsupported training mode")


def _task_digest(mode, task):
    if mode == "code-lab":
        return sandbox.task_digest(task)
    if mode == "artifact-repair":
        return trial.digest(task)
    raise HandoffError("Unsupported training mode")


def create(mode, task, packs, statuses, request_id, agent_label):
    """Export an advisory mission, NEVER a token, lease or execution authority."""
    for value, field in ((request_id, "request_id"), (agent_label, "agent_label")):
        if not isinstance(value, str) or not LABEL.fullmatch(value):
            raise HandoffError("Invalid " + field)
    try:
        proof = ensure_approved_pack({"pack_id": task["pack_id"]}, packs, statuses)
    except ChamberError as exc:
        raise HandoffError(str(exc)) from exc
    payload = with_charter({
        "schema": SCHEMA,
        "request_id": request_id,
        "agent_label": agent_label,
        "agent_identity_verified": False,
        "mode": mode,
        "task": {
            "id": task["id"], "version": task["version"],
            "digest": _task_digest(mode, task),
        },
        "approved_pack": proof,
        "knowledge_is_reference_data": True,
        "task_execution_authorized": False,
        "worker_lease_issued": False,
        "source_head_verified": False,
        "dispatch_authorized": False,
        "merge_authorized": False,
        "deployment_authorized": False,
        "independent_evidence_verified": False,
        "handoff_state": "HELD_FOR_AGENTORA_OPERATOR_REVIEW",
    })
    return {**payload, "handoff_digest": fingerprint(payload)}


def _require(condition, reason):
    if not condition:
        raise HandoffError(reason)


def validate_handoff(raw, packs, statuses, *, code_tasks=None, trial_tasks=None):
    """Rebuild from current approved task+pack. Reject drift, extras and flags."""
    _require(type(raw) is dict, "Handoff must be an object")
    _require(raw.get("schema") == SCHEMA, "Unknown handoff schema")
    mode = raw.get("mode")
    task_fields = raw.get("task")
    _require(type(task_fields) is dict and type(task_fields.get("id")) is str,
             "Invalid handoff task")
    task = task_by_mode(mode, task_fields["id"], code_tasks, trial_tasks)
    expected = create(mode, task, packs, statuses,
                      raw.get("request_id"), raw.get("agent_label"))
    _require(raw == expected, "Handoff differs from pinned approved local contract")
    return task, expected


def _same_receipt_core(handoff, report):
    _require(type(report) is dict and report.get("charter") == welcome_charter(),
             "Report lacks unchanged Welcome Charter")
    _require(report.get("task") == handoff["task"], "Task ID, version or digest differs")
    _require(report.get("approved_pack") == handoff["approved_pack"],
             "Review proof or pack digest differs")
    _require(report.get("agent_identity_verified") is False,
             "Agent identity claim not permitted")
    _require(report.get("general_competence_verified") is False,
             "General competence claim not permitted")
    _require(type(report.get("submission_digest")) is str and
             SHA.fullmatch(report["submission_digest"]) is not None,
             "Submission fingerprint invalid")


def _validate_trial(report):
    fields = {
        "charter", "kind", "task", "approved_pack", "submission_digest",
        "result_artifact_digest", "submitted_change_paths", "passed_checks",
        "total_checks", "checks", "artifact_passed", "status",
        "agent_identity_verified", "general_competence_verified",
        "model_executed", "execution_authority", "notes",
    }
    _require(set(report) == fields and report["kind"] == "practical_artifact_evaluation",
             "Unsupported artifact-repair receipt")
    _require(report["execution_authority"] == "none" and
             report["model_executed"] is False, "Receipt authority or execution flag invalid")
    passed = report["artifact_passed"]
    checks = report["checks"]
    total = report["total_checks"]
    count = report["passed_checks"]
    _require(type(passed) is bool and type(total) is int and 1 <= total <= 16 and
             type(count) is int and 0 <= count <= total and
             type(checks) is list and len(checks) == total,
             "Artifact result counts invalid")
    _require(all(type(c) is dict and set(c) == {"path", "passed"}
                 and type(c["path"]) is str and type(c["passed"]) is bool for c in checks),
             "Artifact check entries invalid")
    actual_passed = sum(c["passed"] for c in checks)
    _require(actual_passed == count and (count == total) is passed,
             "Inconsistent artifact check results")
    _require(report["status"] == (
        "artifact_checks_passed" if passed else "artifact_checks_failed"
    ), "Artifact check status does not match")
    _require(type(report["result_artifact_digest"]) is str and
             SHA.fullmatch(report["result_artifact_digest"]) is not None and
             type(report["submitted_change_paths"]) is list and
             len(report["submitted_change_paths"]) <= 16 and
             all(type(p) is str and len(p) <= 100 for p in report["submitted_change_paths"]),
             "Artifact evidence fingerprint or paths invalid")
    return "reported_pass" if passed else "reported_fail"


def _validate_code(report):
    common = {
        "charter", "kind", "task", "approved_pack", "submission_digest",
        "image", "host_execution", "network_access", "execution_authority",
        "agent_identity_verified", "general_competence_verified",
        "status", "container_executed", "notes",
    }
    _require(report.get("kind") == "code_lab_execution", "Unsupported Code Lab receipt")
    _require(report.get("host_execution") is False and
             report.get("network_access") is False and
             report.get("execution_authority") == "isolated_trial_only",
             "Code Lab authority or execution flags invalid")
    _require(type(report.get("image")) is str and
             sandbox.IMAGE.fullmatch(report["image"]) is not None,
             "Code Lab image is not digest-pinned")
    if report.get("status") == "preview_not_executed":
        _require(set(report) == common | {"limits"} and
                 report.get("container_executed") is False and
                 type(report.get("limits")) is dict,
                 "Malformed Code Lab preview")
        return "not_run"
    _require(set(report) == common | {"passed", "total", "checks", "exit_code"} and
             report.get("container_executed") is True,
             "Malformed Code Lab execution receipt")
    total, count, checks = report["total"], report["passed"], report["checks"]
    _require(type(total) is int and 1 <= total <= 12 and
             type(count) is int and 0 <= count <= total and
             type(checks) is list and len(checks) == total and
             all(type(v) is bool for v in checks) and sum(checks) == count and
             type(report["exit_code"]) is int, "Code Lab checks invalid")
    expected = (count == total and report["exit_code"] == 0)
    _require(report["status"] == (
        "artifact_function_checks_passed" if expected
        else "artifact_function_checks_failed"
    ), "Code Lab status does not match checks")
    return "reported_pass" if expected else "reported_fail"


def inspect_report(handoff, report, packs, statuses, *,
                   code_tasks=None, trial_tasks=None):
    """Cross-check shape and local pinning, never attest a caller-supplied report."""
    _, matched = validate_handoff(
        handoff, packs, statuses, code_tasks=code_tasks, trial_tasks=trial_tasks,
    )
    _same_receipt_core(matched, report)
    if matched["mode"] == "code-lab":
        claimed = _validate_code(report)
    else:
        claimed = _validate_trial(report)
    return with_charter({
        "schema": RECEIPT_SCHEMA,
        "request_id": matched["request_id"],
        "handoff_digest": matched["handoff_digest"],
        "report_digest": fingerprint(report),
        "mode": matched["mode"],
        "task": matched["task"],
        "approved_pack": matched["approved_pack"],
        "candidate_claim": claimed,
        "state": "HELD_AWAITING_INDEPENDENT_ATTESTATION",
        "receipt_source_authenticated": False,
        "agent_identity_verified": False,
        "independent_evidence_verified": False,
        "worker_lease_verified": False,
        "current_source_head_verified": False,
        "execution_authorized": False,
        "dispatch_authorized": False,
        "merge_authorized": False,
        "deployment_authorized": False,
        "notes": (
            "Only JSON structure and currently approved digests were checked. "
            "This result is untrusted until Agentora independently verifies "
            "worker identity, source, lease, and execution evidence."
        ),
    })
