"""ΦConstruct Code Lab: opt-in, digest-pinned, container-only code exercise.

Never execute submitted Python directly on the host. Docker is only a first
isolation boundary, not a guarantee against container escape. For adversarial
or multi-tenant workloads use a dedicated disposable VM or microVM.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile

from .chamber import ChamberError, ensure_approved_pack
from .welcome import with_charter

ID = re.compile(r"[a-z][a-z0-9_.-]{2,79}\Z")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
IMAGE = re.compile(r"[a-z0-9][a-z0-9._/-]*(?::[a-z0-9._-]+)?@sha256:[0-9a-f]{64}\Z")
MAX_TASKS = 24
MAX_TASK_BYTES = 24576
MAX_SOURCE_BYTES = 8192
RUN_TIMEOUT = 15


class SandboxError(ValueError):
    """A Code Lab input, trust precondition or container invocation failed."""


def _bytes(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(value):
    return "sha256:" + hashlib.sha256(_bytes(value)).hexdigest()


def validate_task(task):
    required = {
        "schema_version", "id", "version", "title", "pack_id",
        "instructions", "function", "signature", "cases",
    }
    if not isinstance(task, dict) or set(task) != required:
        raise SandboxError("Unsupported Code Lab task schema")
    if type(task["schema_version"]) is not int or task["schema_version"] != 1:
        raise SandboxError("Unsupported task schema version")
    for key, maxlen in (("id", 80), ("version", 40), ("title", 120),
                        ("pack_id", 80), ("instructions", 1000),
                        ("function", 80), ("signature", 150)):
        v = task[key]
        if not isinstance(v, str) or not v.strip() or len(v) > maxlen:
            raise SandboxError("Invalid task " + key)
    if (not ID.fullmatch(task["id"]) or not ID.fullmatch(task["pack_id"])
            or not ID.fullmatch(task["function"])
            or not VERSION.fullmatch(task["version"])):
        raise SandboxError("Invalid Code Lab task identifiers")
    cases = task["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 12:
        raise SandboxError("Code Lab requires 1-12 checks")
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"args", "expected"}:
            raise SandboxError("Invalid Code Lab test case")
        args = case["args"]
        expected = case["expected"]
        if (not isinstance(args, list) or not 1 <= len(args) <= 3
                or any(type(arg) not in (str, int, bool) for arg in args)
                or type(expected) not in (str, int, bool)
                or any(type(v) is str and len(v) > 150 for v in args + [expected])):
            raise SandboxError("Unsupported Code Lab case value")
    if len(_bytes(task)) > MAX_TASK_BYTES:
        raise SandboxError("Code Lab task exceeds size limit")
    return task


def task_digest(task):
    validate_task(task)
    return sha256(task)


def read_tasks(directory=None):
    root = Path(directory) if directory else Path(__file__).with_name("code_tasks")
    if not root.is_dir():
        raise SandboxError("Code Lab task directory missing")
    files = sorted(root.iterdir())
    if len(files) > MAX_TASKS:
        raise SandboxError("Too many Code Lab task files")
    tasks = []
    seen = set()
    for path in files:
        if path.suffix != ".json":
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TASK_BYTES:
            raise SandboxError("Code Lab tasks must be small, regular JSON files")
        try:
            raw = path.read_text(encoding="utf-8")
            task = validate_task(json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise SandboxError("Invalid Code Lab fixture: " + path.name) from exc
        if task["id"] in seen:
            raise SandboxError("Duplicate Code Lab task ID")
        seen.add(task["id"])
        tasks.append(task)
    return sorted(tasks, key=lambda x: x["id"])


def catalogue(tasks):
    return [{
        "id": t["id"], "version": t["version"], "title": t["title"],
        "pack_id": t["pack_id"], "digest": task_digest(t),
        "check_count": len(t["cases"]),
    } for t in tasks]


def get_task(tasks, identifier):
    for task in tasks:
        if task["id"] == identifier:
            return task
    raise SandboxError("Unknown Code Lab task: " + str(identifier))


def approved(task, packs, statuses):
    try:
        return ensure_approved_pack(
            {"pack_id": task["pack_id"]}, packs, statuses
        )
    except ChamberError as exc:
        raise SandboxError(str(exc)) from exc


def show(task, packs, statuses):
    proof = approved(task, packs, statuses)
    return with_charter({
        "kind": "container_code_challenge",
        "task": {
            "id": task["id"], "version": task["version"],
            "digest": task_digest(task), "title": task["title"],
            "instructions": task["instructions"],
            "signature": task["signature"],
            "check_count": len(task["cases"]),
        },
        "approved_pack": proof,
        "submission": "UTF-8 Python source (.py), no more than 8192 bytes",
        "execution_authority": "none_without_explicit_execute_flag",
        "notes": "Runs only with opt-in container execution; never on the host.",
    })


def read_source(path):
    p = Path(path)
    if p.suffix != ".py" or p.is_symlink() or not p.is_file():
        raise SandboxError("Submission must be a regular .py file, not a symlink")
    if not 1 <= p.stat().st_size <= MAX_SOURCE_BYTES:
        raise SandboxError("Source must be 1-8192 bytes")
    try:
        source = p.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise SandboxError("Source must be UTF-8") from exc
    if "\x00" in source:
        raise SandboxError("NUL bytes are not allowed")
    return source


_GRADER = r'''import contextlib
import importlib.util
import io
import json
import sys

def evaluate():
    with open("/task/cases.json", "r", encoding="utf-8") as handle:
        task = json.load(handle)
    passed = []
    try:
        # Capture normal print calls by the submitted function without trusting them
        # as the grader's own final report.
        with contextlib.redirect_stdout(io.StringIO()):
            spec = importlib.util.spec_from_file_location("candidate", "/task/submission.py")
            candidate = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(candidate)
            fn = getattr(candidate, task["function"])
            for test in task["cases"]:
                try:
                    actual = fn(*test["args"])
                    passed.append(
                        type(actual) is type(test["expected"])
                        and actual == test["expected"]
                    )
                except BaseException:
                    passed.append(False)
    except BaseException:
        passed = [False] * len(task["cases"])
    return passed

if __name__ == "__main__":
    try:
        checks = evaluate()
    except BaseException:
        checks = []
    print("__PHI_CODE_LAB_RESULT__" + json.dumps({
        "kind": "code_lab_result", "checks": checks
    }, separators=(",", ":")), flush=True)
    sys.exit(0 if checks and all(checks) else 2)
'''


def _docker_args(image, directory, cidfile):
    """Construct argv without shell evaluation, host credentials or writable repo mounts."""
    return [
        "docker", "run", "--rm", "--pull=never",
        "--network=none", "--read-only", "--ipc=none",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--memory-swap=128m",
        "--cpus=0.50", "--ulimit=nofile=64:64",
        "--user=65534:65534", "--workdir=/task",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--env=PYTHONNOUSERSITE=1",
        "--mount=type=bind,source=" + str(directory) + ",target=/task,readonly",
        "--cidfile=" + str(cidfile),
        "--entrypoint=python3",
        image, "-I", "-B", "-S", "/task/grader.py",
    ]


def _run(argv, *, timeout, runner):
    try:
        return runner(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise SandboxError("Docker executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise SandboxError("Container operation timed out") from exc
    except OSError as exc:
        raise SandboxError("Container process could not be started") from exc


def run(task, packs, statuses, source, image, execute=False, runner=None):
    """Explicit opt-in. Docker may still be vulnerable; use a disposable VM for hostile code."""
    proof = approved(task, packs, statuses)
    if not isinstance(image, str) or not IMAGE.fullmatch(image):
        raise SandboxError("Docker image must be pinned as name@sha256:<64 hex>")
    source_text = read_source(source)
    fingerprint = "sha256:" + hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    base = {
        "kind": "code_lab_execution",
        "task": {"id": task["id"], "version": task["version"],
                 "digest": task_digest(task)},
        "approved_pack": proof,
        "submission_digest": fingerprint,
        "image": image,
        "host_execution": False,
        "network_access": False,
        "execution_authority": "isolated_trial_only",
        "agent_identity_verified": False,
        "general_competence_verified": False,
    }
    if not execute:
        return with_charter({
            **base, "status": "preview_not_executed",
            "container_executed": False,
            "limits": {"memory_mb": 128, "cpu": 0.5, "pids": 32,
                       "timeout_seconds": RUN_TIMEOUT, "filesystem": "read_only",
                       "network": "none"},
            "notes": "Explicit --execute required; image must already exist locally.",
        })
    runner = runner or subprocess.run
    inspect = _run(["docker", "image", "inspect", image], timeout=8, runner=runner)
    if inspect.returncode != 0:
        raise SandboxError("Pinned Docker image not available locally; no pulling is allowed")
    with tempfile.TemporaryDirectory(prefix="phi-code-lab-") as staging:
        directory = Path(staging)
        os.chmod(directory, 0o755)
        for filename, payload in (
            ("submission.py", source_text),
            ("grader.py", _GRADER),
            ("cases.json", json.dumps({
                "function": task["function"], "cases": task["cases"]
            }, ensure_ascii=False)),
        ):
            target = directory / filename
            target.write_text(payload, encoding="utf-8")
            os.chmod(target, 0o644)
        cidfile = directory / "container.cid"
        argv = _docker_args(image, directory, cidfile)
        try:
            output = _run(argv, timeout=RUN_TIMEOUT, runner=runner)
        except SandboxError:
            # docker run can outlive a killed CLI process. Try targeted cleanup.
            if cidfile.exists():
                cid = cidfile.read_text(encoding="utf-8").strip()
                if re.fullmatch(r"[0-9a-f]{12,64}", cid):
                    try:
                        _run(["docker", "rm", "-f", cid], timeout=6, runner=runner)
                    except SandboxError:
                        pass
            raise
        # Trust only the grader-shaped final line plus the container exit status.
        lines = output.stdout.splitlines() if isinstance(output.stdout, str) else []
        marker = "__PHI_CODE_LAB_RESULT__"
        report = None
        if lines and lines[-1].startswith(marker):
            try:
                report = json.loads(lines[-1][len(marker):])
            except ValueError:
                pass
        checks = report.get("checks") if isinstance(report, dict) and report.get("kind") == "code_lab_result" else None
        valid = (
            isinstance(checks, list)
            and len(checks) == len(task["cases"])
            and all(type(v) is bool for v in checks)
        )
        results = checks if valid else [False] * len(task["cases"])
        success = (output.returncode == 0 and valid and all(results))
        return with_charter({
            **base,
            "status": "artifact_function_checks_passed" if success else "artifact_function_checks_failed",
            "container_executed": True,
            "passed": sum(results),
            "total": len(task["cases"]),
            "checks": results,
            "exit_code": output.returncode,
            "notes": (
                "A local Docker container evaluated submitted Python against fixed "
                "test cases. This is not an adversarially secure benchmark, verified "
                "agent identity, general competence, or a container-escape guarantee."
            ),
        })
