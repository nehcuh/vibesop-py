"""Shared Docker CLI invoke and JSON helpers for formal tasks.

Candidate Python runs only in an isolated container. This module, hidden
cases, references, and mutants stay on the host and are never mounted.
"""
from __future__ import annotations

import json
import math
import os
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

IMAGE = "python:3.12-slim"
TIMEOUT = 8.0
OUTPUT_LIMIT = 262144
STUB = (
    "import json, sys\n"
    "json.load(sys.stdin)\n"
    'print(json.dumps({"error": "not_implemented"}))\n'
)

COMMON_RULES = """Implement the required Python CLI using the standard library only.
Read one JSON value from stdin and print exactly one JSON value on stdout.
No diagnostics on stdout. Exit 0 for success and for specified application errors.
Each request starts a fresh process. Malformed JSON or invalid request shapes yield
{"error":"invalid_input"} unless a task names a more specific error. Booleans are
not numbers. These are synthetic tasks, not production bug reproductions.
"""


def check(name: str, passed: bool, detail: object) -> dict:
    return {"name": name, "passed": bool(passed), "detail": str(detail)}


def strict_json(text: str):
    def constant(value):
        raise ValueError("non-finite JSON constant: " + value)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(text, parse_constant=constant, object_pairs_hook=pairs)


def same(actual, expected) -> bool:
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (float, int)):
        return (
            type(actual) in (float, int)
            and math.isfinite(actual)
            and abs(actual - expected) <= 1e-8
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(same(a, e) for a, e in zip(actual, expected))
        )
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(same(actual[k], v) for k, v in expected.items())
        )
    return False


def copy_workspace(source: Path, target: Path) -> None:
    total = 0
    count = 0
    for root, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            item = Path(root) / name
            mode = item.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError("workspace contains non-regular entry")
        for name in files:
            item = Path(root) / name
            count += 1
            total += item.stat().st_size
            if total > 8 * 1024 * 1024 or count > 256:
                raise ValueError("workspace exceeds 8 MiB / 256 files")
            dest = target / item.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, dest)


def invoke(
    workspace: Path,
    payload,
    *,
    entry: str = "app.py",
    writable: bool = False,
    timeout: float = TIMEOUT,
    env: dict[str, str] | None = None,
    extra_tmpfs: tuple[str, ...] = (),
    volumes: tuple[tuple[str, str, str], ...] = (),
) -> dict:
    """Run a fixed argv in a network-free, secret-free container."""
    name = "formal-" + uuid.uuid4().hex
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--pids-limit",
        "64",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=32m",
        "-i",
        "-v",
        f"{workspace}:/work:{'rw' if writable else 'ro'}",
        "-w",
        "/work",
    ]
    for mount in extra_tmpfs:
        command.extend(["--tmpfs", mount])
    for host, dest, mode in volumes:
        host_path = Path(host).resolve()
        if not host_path.exists() or ".." in Path(dest).parts:
            raise ValueError("invalid extra volume")
        command.extend(["-v", f"{host_path}:{dest}:{mode}"])
    for key, value in (env or {}).items():
        if key in {"PATH", "API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
            raise ValueError("refusing to pass host secrets or PATH into container")
        command.extend(["-e", f"{key}={value}"])
    command.extend([IMAGE, "python", entry])
    proc = None
    result = None
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        assert proc.stdin is not None
        proc.stdin.write(raw.encode("utf-8"))
        proc.stdin.close()
        output = bytearray()
        errors = bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            assert proc.stdout is not None and proc.stderr is not None
            selector.register(proc.stdout, selectors.EVENT_READ, output)
            selector.register(proc.stderr, selectors.EVENT_READ, errors)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("container execution timed out")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        key.data.extend(chunk)
                        if len(output) + len(errors) > OUTPUT_LIMIT:
                            raise ValueError("container output limit exceeded")
        code = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        if code != 0:
            err = errors.decode("utf-8", "replace")[:500]
            raise ValueError(f"container exit {code}: {err}")
        result = {"ok": True, "value": strict_json(output.decode("utf-8")), "detail": "valid JSON"}
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired, UnicodeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        if proc is not None:
            try:
                cleanup = subprocess.run(
                    ["docker", "rm", "-f", name],
                    shell=False,
                    capture_output=True,
                    timeout=5,
                )
                if cleanup.returncode and b"No such container" not in cleanup.stderr:
                    result = {
                        "ok": False,
                        "detail": "container cleanup failed: "
                        + cleanup.stderr.decode("utf-8", "replace")[:300],
                    }
            except (OSError, subprocess.TimeoutExpired) as exc:
                result = {"ok": False, "detail": f"container cleanup failed: {exc}"}
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
    return result


def disk_value(root: Path, relative: str, expected) -> bool:
    path = root / relative
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("generated symlink")
    if expected is None:
        return not path.exists()
    if not path.is_file() or path.stat().st_size > OUTPUT_LIMIT:
        return False
    value = path.read_text(encoding="utf-8")
    if isinstance(expected, dict) or isinstance(expected, list):
        return same(strict_json(value), expected)
    return value == expected


def step(name: str, request, expected, *, disk=None, entry="app.py", env=None, extra=None):
    return {
        "name": name,
        "request": request,
        "expected": expected,
        "disk": disk or {},
        "entry": entry,
        "env": env or {},
        "extra": extra or {},
    }


def write_tree(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        if path.is_absolute() or ".." in Path(name).parts:
            raise ValueError("unsafe path: " + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def fresh_copy(src: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="formal-ws-"))
    copy_workspace(src, tmp)
    return tmp
