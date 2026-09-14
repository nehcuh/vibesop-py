"""Synthetic calibration fixtures, NOT reproductions of the production project.

Only TASKS[task_id]['spec'] and ['files'] may be sent to participants. Keep this
module, hidden cases, self-check results and reference sources on the host.
Run host verification with: uv run python docs/experiments/multi-expert-calibration/tasks.py
Candidate Python is executed ONLY in Docker, never imported or run on the host.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
import uuid

_IMAGE = "python:3.12-slim"
_TIMEOUT = 8.0
_OUTPUT_LIMIT = 262144
_STUB = 'import json, sys\njson.load(sys.stdin)\nprint(json.dumps({"error": "not_implemented"}))\n'
_COMMON = """Implement app.py (you may add standard-library-only Python modules).
Read one JSON value from stdin and print exactly one JSON value on stdout, with
no diagnostics on stdout. Exit 0 for success and specified application errors.
Each request starts a fresh `python app.py` process. JSON objects below have
exactly the specified output keys. Malformed JSON or invalid request shapes yield
{"error":"invalid_input"}. Booleans are not numbers. No third-party packages.
These are synthetic calibration tasks, not production bug reproductions.
"""

TASKS = {
    "calibration-intent-v1": {
        "spec": _COMMON + """
Input: {"text": string}; extra input keys may be ignored. Normalize by strip(),
lower(), then remove all trailing characters from ' .!?。！？' and strip again.
Output: {"skill": string or null, "source":"explicit"|"intent"|"none",
"inject": boolean}. Known IDs: session-end, code-review, autonomous-experiment.
1. Explicit command is a FULL regex match /skill +([a-z][a-z0-9-]*) on normalized
text (one or more ASCII spaces). A known ID returns that skill, explicit, true;
an unknown ID returns null, none, false. A command with extra words is no match.
2. Automatic session-end only for exact normalized phrases: 收工, 今天到这里,
结束本次会话, that's all for now. Narratives, negation and quoted phrases do not match.
3. Automatic code-review for exact 请审查代码, 帮我审查代码, review code, or those
prefixes followed by ASCII space, ':' or '：' and any suffix.
4. Otherwise null, none, false. Never automatically inject autonomous-experiment.
Priority is explicit command, session-end, code-review. Text must be a string.
""",
        "files": {"app.py": _STUB},
    },
    "calibration-config-path-v1": {
        "spec": _COMMON + """
Implement two operations sharing files relative to the working directory:
Generate input: {"op":"generate","platform":"alpha"|"beta","skills":[
{"id":ID,"path":PATH,"content":string}, ...]}.
ID fully matches [a-z][a-z0-9-]{0,31}. IDs and paths must each be unique.
PATH uses '/' separators, starts 'skills/', ends '/SKILL.md', has at least three
components, each matching [A-Za-z0-9_.-]+ except '.' and '..' are forbidden.
Absolute paths and backslashes are invalid. Validate the whole request BEFORE
writing anything. Empty skills is valid. Create parent directories, write each
content as UTF-8, then generated/<platform>.json as {"skills":{ID:PATH,...}}.
Return {"config":"generated/<platform>.json","count":number of skills}.
Regeneration replaces the platform's mapping; old content files may remain.
Resolve input: {"op":"resolve","platform":"alpha"|"beta","id":ID}.
Read generated/<platform>.json afresh, use its mapped path (never guess a layout),
read the referenced UTF-8 file and return {"path":PATH,"content":file text}.
A missing config, absent ID, or missing target file gives {"error":"not_found"}.
An unreadable/malformed config, a config other than an object with a 'skills'
object, or ANY invalid ID/path in that mapping gives {"error":"invalid_config"}.
Other config keys may be ignored. Invalid operation/platform/ID/generate fields
or duplicate IDs/paths gives {"error":"invalid_input"}.
Extra request/skill-record keys may be ignored. File contents may be empty or
Unicode. Config/skill files are regular files, not symlinks, in this task's input.
The workspace is writable; only that workspace is mounted into the container.
""",
        "files": {"app.py": _STUB, "README.txt": "Implement generate and resolve through app.py.\n"},
    },
    "calibration-next-bar-v1": {
        "spec": _COMMON + """
Input: {"cash":nonnegative finite number,"fee_bps":finite number in [0,10000],
"bars":[{"open":positive finite number},...],
"signals":[{"bar":nonnegative integer index into bars,"side":"buy"|"sell",
"qty":positive integer},...]}. All fields required; extra keys ignored. Empty
bars/signals are valid; signals must reference existing bars. Validate ALL input
before matching. No short selling, borrowing or partial fills. Start position 0.
Process signals in ascending bar index, preserving input order for equal indices.
A signal at i attempts its entire order at bars[i+1].open, never bars[i].open.
At the final bar reject with reason no_next_bar before checking cash/position.
Use Decimal(str(value)) arithmetic; round notional=qty*fill_price to cents using
ROUND_HALF_UP, then fee=rounded_notional*fee_bps/10000 to cents likewise.
Buy requires cash >= notional+fee; otherwise insufficient_cash. Sell requires
position >= qty; otherwise insufficient_position. Rejections change no state.
On fill update cash by -(notional+fee) for buys or +(notional-fee) for sells.
Output {"trades":[{"signal_bar":i,"fill_bar":i+1,"side":side,"qty":qty,
"price":fill_price,"notional":rounded_notional,"fee":rounded_fee},...],
"rejected":[{"signal_bar":i,"side":side,"qty":qty,"reason":reason},...],
"cash":cash,"position":integer,"equity":cash+position*last_bar_open}.
Money outputs are JSON numbers, not strings; round final cash and equity to cents
HALF_UP. Do not round starting cash before matching. Empty bars => equity=cash.
""",
        "files": {"app.py": _STUB},
    },
}


def _check(name, passed, detail):
    return {"name": name, "passed": bool(passed), "detail": str(detail)}


def _strict_json(text):
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


def _same(actual, expected):
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (float, int)):
        return (type(actual) in (float, int) and math.isfinite(actual)
                and abs(actual - expected) <= 1e-8)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _same(a, e) for a, e in zip(actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            _same(actual[k], v) for k, v in expected.items())
    return False


def _invoke(workspace, payload, *, writable=False, timeout=_TIMEOUT):
    """Fixed argv; no shell. Bound output/time, remove only our UUID container."""
    name = "calibration-" + uuid.uuid4().hex
    command = ["docker", "run", "--rm", "--name", name, "--network", "none",
               "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
               "--read-only", "--tmpfs", "/tmp:rw,size=32m", "-i",
               "-v", f"{workspace}:/work:{'rw' if writable else 'ro'}",
               "-w", "/work", _IMAGE, "python", "app.py"]
    proc = None
    result = None
    try:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=False)
        raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        proc.stdin.write(raw.encode("utf-8"))
        proc.stdin.close()
        output = bytearray()
        errors = bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
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
                        if len(output) + len(errors) > _OUTPUT_LIMIT:
                            raise ValueError("container output limit exceeded")
        code = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        if code != 0:
            raise ValueError(f"container exit {code}: " + errors.decode("utf-8", "replace")[:500])
        result = {"ok": True, "value": _strict_json(output.decode("utf-8")), "detail": "valid JSON"}
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
        result = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        if proc is not None:
            # docker CLI termination alone does not stop its container.
            try:
                cleanup = subprocess.run(["docker", "rm", "-f", name], shell=False,
                                         capture_output=True, timeout=5)
                if cleanup.returncode and b"No such container" not in cleanup.stderr:
                    result = {"ok": False, "detail": "container cleanup failed: " +
                              cleanup.stderr.decode("utf-8", "replace")[:300]}
            except (OSError, subprocess.TimeoutExpired) as exc:
                result = {"ok": False, "detail": f"container cleanup failed: {exc}"}
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
    return result


def _step(name, request, expected, *, disk=None):
    return {"name": name, "request": request, "expected": expected, "disk": disk or {}}


def _route_cases():
    none = {"skill": None, "source": "none", "inject": False}
    intent = lambda skill: {"skill": skill, "source": "intent", "inject": True}
    data = [
        ("exact_end", "收工", intent("session-end")),
        ("normalization", "  THAT'S ALL FOR NOW！？  ", intent("session-end")),
        ("end_alias", "今天到这里。", intent("session-end")),
        ("worker_narrative", "工人收工以后回家", none),
        ("negated_end", "不要收工", none),
        ("quoted_end", '他说“收工”', none),
        ("review_prefix", "review code: app.py", intent("code-review")),
        ("review_chinese", "请审查代码：入口", intent("code-review")),
        ("review_boundary", "review codec", none),
        ("review_narrative", "昨天请审查代码了", none),
        ("guarded_automatic", "请运行 autonomous-experiment 实验", none),
        ("explicit_guarded", "/skill autonomous-experiment",
         {"skill": "autonomous-experiment", "source": "explicit", "inject": True}),
        ("explicit_spaces", "/SKILL   CODE-REVIEW!",
         {"skill": "code-review", "source": "explicit", "inject": True}),
        ("unknown_explicit", "/skill unknown", none),
        ("command_trailing_words", "/skill session-end later", none),
        ("empty", "", none),
    ]
    cases = [[_step(name, {"text": text}, expected)] for name, text, expected in data]
    for name, request in [("text_type", {"text": 1}), ("missing_text", {}),
                          ("top_level_list", []), ("malformed_json", '{"text":')]:
        cases.append([_step(name, request, {"error": "invalid_input"})])
    return cases


def _config_cases():
    error = lambda key: {"error": key}
    record = {"id": "review", "path": "skills/vendor/review.skill/SKILL.md", "content": "审核\nλ\n"}
    gen = lambda rows, platform="alpha": {"op": "generate", "platform": platform, "skills": rows}
    resolve = lambda key="review", platform="alpha": {"op": "resolve", "platform": platform, "id": key}
    config = lambda rows: {"skills": {r["id"]: r["path"] for r in rows}}
    expected = {"config": "generated/alpha.json", "count": 1}
    cases = [
        [_step("generate_nested_unicode", gen([record]), expected,
               disk={"generated/alpha.json": config([record]), record["path"]: record["content"]}),
         _step("resolve_fresh_process", resolve(), {"path": record["path"], "content": record["content"]})],
        [_step("empty_mapping", gen([]), {"config": "generated/alpha.json", "count": 0},
               disk={"generated/alpha.json": {"skills": {}}}),
         _step("absent_id", resolve(), error("not_found"))],
        [_step("missing_config", resolve(), error("not_found"))],
        [_step("generate_alpha", gen([record]), expected),
         _step("platform_isolation", resolve(platform="beta"), error("not_found")),
         _step("generate_beta", gen([], "beta"), {"config": "generated/beta.json", "count": 0}),
         _step("alpha_survives_beta", resolve(), {"path": record["path"], "content": record["content"]})],
        [_step("initial_mapping", gen([record]), expected),
         _step("replace_mapping", gen([]), {"config": "generated/alpha.json", "count": 0}),
         _step("removed_id", resolve(), error("not_found"))],
    ]
    invalid = [
        ("duplicate_id", gen([record, dict(record, path="skills/other/SKILL.md")])),
        ("duplicate_path", gen([record, dict(record, id="other")])),
        ("parent_traversal", gen([dict(record, path="skills/../SKILL.md")])),
        ("absolute_path", gen([dict(record, path="/tmp/SKILL.md")])),
        ("backslash_path", gen([dict(record, path="skills/a\\b/SKILL.md")])),
        ("bad_id", gen([dict(record, id="Review")])),
        ("invalid_content", gen([dict(record, content=3)])),
        ("invalid_platform", gen([], "../alpha")),
        ("invalid_operation", {"op": "delete", "platform": "alpha"}),
        ("non_object", []),
    ]
    for name, request in invalid:
        cases.append([_step(name, request, error("invalid_input"))])
    cases.append([_step("validate_before_writes", gen([record, dict(record, id="INVALID")]),
                        error("invalid_input"),
                        disk={record["path"]: None, "generated/alpha.json": None})])
    empty = dict(record, content="")
    cases.append([_step("empty_content_generate", gen([empty]), expected),
                  _step("empty_content_resolve", resolve(), {"path": empty["path"], "content": ""})])
    return cases


def _trade(i, side, qty, price, notional, fee=0):
    return {"signal_bar": i, "fill_bar": i + 1, "side": side, "qty": qty,
            "price": price, "notional": notional, "fee": fee}


def _reject(i, side, qty, reason):
    return {"signal_bar": i, "side": side, "qty": qty, "reason": reason}


def _market(cash, prices, signals=(), fee=0):
    return {"cash": cash, "fee_bps": fee, "bars": [{"open": p} for p in prices],
            "signals": [{"bar": i, "side": s, "qty": q} for i, s, q in signals]}


def _book(cash, position=0, equity=None, trades=(), rejected=()):
    return {"cash": cash, "position": position, "equity": cash if equity is None else equity,
            "trades": list(trades), "rejected": list(rejected)}


def _market_cases():
    data = [
        ("empty_market", _market(100, []), _book(100)),
        ("next_open_not_signal_open", _market(100, [1, 10], [(0, "buy", 2)]),
         _book(80, 2, 100, [_trade(0, "buy", 2, 10, 20)])),
        ("last_bar_no_fill", _market(0, [10], [(0, "buy", 1)]),
         _book(0, rejected=[_reject(0, "buy", 1, "no_next_bar")])),
        ("cash_exact_with_fee", _market(10.1, [5, 10], [(0, "buy", 1)], 100),
         _book(0, 1, 10, [_trade(0, "buy", 1, 10, 10, .1)])),
        ("fee_causes_rejection", _market(10, [5, 10], [(0, "buy", 1)], 100),
         _book(10, rejected=[_reject(0, "buy", 1, "insufficient_cash")])),
        ("no_partial_fill", _market(15, [1, 10], [(0, "buy", 2)]),
         _book(15, rejected=[_reject(0, "buy", 2, "insufficient_cash")])),
        ("no_short", _market(100, [1, 10], [(0, "sell", 1)]),
         _book(100, rejected=[_reject(0, "sell", 1, "insufficient_position")])),
        ("stable_same_bar_order", _market(10, [1, 10], [(0, "sell", 1), (0, "buy", 1), (0, "sell", 1)]),
         _book(10, trades=[_trade(0, "buy", 1, 10, 10), _trade(0, "sell", 1, 10, 10)],
               rejected=[_reject(0, "sell", 1, "insufficient_position")])),
        ("sort_signals_and_sell_fee", _market(100, [1, 10, 20], [(1, "sell", 2), (0, "buy", 2)], 100),
         _book(119.4, trades=[_trade(0, "buy", 2, 10, 20, .2), _trade(1, "sell", 2, 20, 40, .4)])),
        ("half_up_notional", _market(1, [1, .105], [(0, "buy", 1)]),
         _book(.89, 1, 1, [_trade(0, "buy", 1, .105, .11)])),
        ("half_up_fee", _market(2, [1, 1], [(0, "buy", 1)], 50),
         _book(.99, 1, 1.99, [_trade(0, "buy", 1, 1, 1, .01)])),
        ("mark_to_last_open", _market(100, [1, 10, 25], [(0, "buy", 2)]),
         _book(80, 2, 130, [_trade(0, "buy", 2, 10, 20)])),
        ("starting_cash_not_rounded", _market(.999, [1, 1], [(0, "buy", 1)]),
         _book(1, rejected=[_reject(0, "buy", 1, "insufficient_cash")])),
        ("reject_does_not_mutate", _market(10, [1, 10], [(0, "buy", 2), (0, "buy", 1)]),
         _book(0, 1, 10, [_trade(0, "buy", 1, 10, 10)], [_reject(0, "buy", 2, "insufficient_cash")])),
    ]
    invalid = [
        ("bool_cash", _market(True, [])),
        ("zero_price", _market(1, [0])),
        ("negative_fee", _market(1, [], fee=-1)),
        ("fee_over_limit", _market(1, [], fee=10001)),
        ("bool_quantity", _market(1, [1, 1], [(0, "buy", True)])),
        ("fractional_index", _market(1, [1, 1], [(0.5, "buy", 1)])),
        ("out_of_range", _market(1, [1], [(1, "buy", 1)])),
        ("negative_index", _market(1, [1], [(-1, "buy", 1)])),
        ("bad_side", _market(1, [1, 1], [(0, "hold", 1)])),
        ("validate_entire_request", _market(10, [1, 1], [(0, "buy", 1), (0, "buy", 0)])),
        ("nonfinite", '{"cash":NaN,"fee_bps":0,"bars":[],"signals":[]}'),
        ("missing_fields", {}),
    ]
    data.extend((n, r, {"error": "invalid_input"}) for n, r in invalid)
    return [[_step(*row)] for row in data]


def _copy_workspace(source, target):
    """Only regular participant files, no symlinks/sockets/host-tree traversal."""
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


def _disk_value(root, relative, expected):
    path = root / relative
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("generated symlink")
    if expected is None:
        return not path.exists()
    if not path.is_file() or path.stat().st_size > _OUTPUT_LIMIT:
        return False
    value = path.read_text(encoding="utf-8")
    return _same(_strict_json(value), expected) if isinstance(expected, dict) else value == expected


def evaluate(task_id: str, workspace: Path) -> dict:
    """Hidden host evaluator. Each case gets a fresh workspace copy.

    Container infrastructure errors fail closed and are included in details.
    A config scenario alone preserves disk state across its successive CLI calls.
    Never mount this module, hidden cases, or a parent checkout into a container.
    """
    checks = []
    if task_id not in TASKS:
        return {"passed": False, "checks": [_check("task_id", False, "unknown calibration task")]}
    workspace = Path(workspace).absolute()
    if not workspace.is_dir() or workspace.is_symlink():
        return {"passed": False, "checks": [_check("workspace", False, "invalid workspace directory")]}
    cases = {"calibration-intent-v1": _route_cases,
             "calibration-config-path-v1": _config_cases,
             "calibration-next-bar-v1": _market_cases}[task_id]()
    writable = task_id == "calibration-config-path-v1"
    # Additional independent resolution cases supplied by the host, without an oracle.
    seeds = []
    if writable:
        seeds = [
            ("mapped_path_not_guessed", {"skills": {"review": "skills/odd/deep/entry/SKILL.md"}},
             {"skills/odd/deep/entry/SKILL.md": "host supplied content\n"},
             {"path": "skills/odd/deep/entry/SKILL.md", "content": "host supplied content\n"}),
            ("mapped_file_missing", {"skills": {"review": "skills/missing/SKILL.md"}}, {}, {"error": "not_found"}),
            ("malformed_config", "{broken", {}, {"error": "invalid_config"}),
            ("invalid_config_shape", {"skills": []}, {}, {"error": "invalid_config"}),
            ("unsafe_mapping", {"skills": {"review": "../SKILL.md"}}, {}, {"error": "invalid_config"}),
            ("validate_other_mapping", {"skills": {"other": "/tmp/SKILL.md"}}, {}, {"error": "invalid_config"}),
        ]
    scenarios = [(steps, {}) for steps in cases]
    for name, config, files, expected in seeds:
        files = dict(files, **{"generated/alpha.json": json.dumps(config) if isinstance(config, dict) else config})
        scenarios.append(([_step(name, {"op": "resolve", "platform": "alpha", "id": "review"}, expected)], files))
    try:
        with tempfile.TemporaryDirectory(prefix="calibration-eval-") as tmp:
            base = Path(tmp) / "base"
            base.mkdir()
            _copy_workspace(workspace, base)
            if not (base / "app.py").is_file():
                raise ValueError("missing app.py")
            for index, (steps, seeds_for_case) in enumerate(scenarios):
                case_dir = Path(tmp) / str(index)
                shutil.copytree(base, case_dir)
                # Candidate-delivered generated data cannot influence the initial state.
                if writable and (case_dir / "generated").exists():
                    generated = case_dir / "generated"
                    if generated.is_dir():
                        shutil.rmtree(generated)
                    else:
                        generated.unlink()
                for relative, content in seeds_for_case.items():
                    path = case_dir / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                for step in steps:
                    run = _invoke(case_dir, step["request"], writable=writable)
                    passed = run["ok"] and _same(run.get("value"), step["expected"])
                    detail = "matched CLI contract" if passed else (run["detail"] if not run["ok"] else
                              "JSON mismatch: " + repr(run.get("value"))[:500])
                    for relative, expected in step["disk"].items():
                        try:
                            disk_ok = _disk_value(case_dir, relative, expected)
                        except (OSError, ValueError, UnicodeError):
                            disk_ok = False
                        if not disk_ok:
                            passed = False
                            detail += "; disk mismatch: " + relative
                    checks.append(_check(step["name"], passed, detail))
    except (OSError, ValueError) as exc:
        checks.append(_check("workspace", False, exc))
    return {"passed": bool(checks) and all(c["passed"] for c in checks), "checks": checks}


# PRIVATE self-check sources: never included in TASKS, prompts, or participant workspaces.
# Temporary reference workspaces below are exclusively for local Docker self-checks.
_REFERENCE_ROUTE = r'''
import json, re, sys

def main(x):
    if not isinstance(x, dict) or not isinstance(x.get("text"), str):
        return {"error":"invalid_input"}
    text = x["text"].strip().lower().rstrip(' .!?。！？').strip()
    skill, source = None, "none"
    m = re.fullmatch(r"/skill +([a-z][a-z0-9-]*)", text)
    if m:
        if m[1] in ("session-end", "code-review", "autonomous-experiment"):
            skill, source = m[1], "explicit"
    elif text in ("收工", "今天到这里", "结束本次会话", "that's all for now"):
        skill, source = "session-end", "intent"
    elif any(text == p or any(text.startswith(p + d) for d in (" ", ":", "："))
             for p in ("请审查代码", "帮我审查代码", "review code")):
        skill, source = "code-review", "intent"
    return {"skill":skill, "source":source, "inject":skill is not None}
try:
    print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
except (ValueError, TypeError):
    print(json.dumps({"error":"invalid_input"}))
'''

_REFERENCE_CONFIG = r'''
import json, re, sys
from pathlib import Path

def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None

def valid_path(s):
    return (isinstance(s, str) and s.startswith("skills/") and s.endswith("/SKILL.md")
            and len(s.split("/")) >= 3 and all(p not in (".", "..") and
            re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in s.split("/")))

def main(x):
    bad = {"error":"invalid_input"}
    if not isinstance(x, dict) or x.get("platform") not in ("alpha", "beta"):
        return bad
    config = Path("generated") / (x["platform"] + ".json")
    if x.get("op") == "generate":
        rows = x.get("skills")
        if not isinstance(rows, list): return bad
        mapping, paths = {}, set()
        for row in rows:
            if not isinstance(row, dict): return bad
            key, path, content = row.get("id"), row.get("path"), row.get("content")
            if not ident(key) or not valid_path(path) or not isinstance(content, str): return bad
            if key in mapping or path in paths: return bad
            mapping[key] = path
            paths.add(path)
        for row in rows:
            p = Path(row["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(row["content"], encoding="utf-8")
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"skills":mapping}), encoding="utf-8")
        return {"config":str(config), "count":len(rows)}
    if x.get("op") != "resolve" or not ident(x.get("id")): return bad
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"error":"not_found"}
    except (OSError, ValueError, UnicodeError):
        return {"error":"invalid_config"}
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        return {"error":"invalid_config"}
    mapping = data["skills"]
    if not all(ident(k) and valid_path(v) for k, v in mapping.items()):
        return {"error":"invalid_config"}
    if x["id"] not in mapping: return {"error":"not_found"}
    path = mapping[x["id"]]
    try:
        content = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"error":"not_found"}
    return {"path":path, "content":content}
try:
    print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
except (ValueError, TypeError):
    print(json.dumps({"error":"invalid_input"}))
'''

_REFERENCE_MARKET = r'''
import json, sys, math
from decimal import Decimal, ROUND_HALF_UP, localcontext

def money(x): return x.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
def number(x): return type(x) in (int, float) and math.isfinite(x)
def main(x):
    bad = {"error":"invalid_input"}
    if not isinstance(x, dict): return bad
    cash, fee = x.get("cash"), x.get("fee_bps")
    bars, signals = x.get("bars"), x.get("signals")
    if not number(cash) or cash < 0 or not number(fee) or not 0 <= fee <= 10000: return bad
    if not isinstance(bars, list) or not isinstance(signals, list): return bad
    if not all(isinstance(b, dict) and number(b.get("open")) and b["open"] > 0 for b in bars): return bad
    for s in signals:
        if not isinstance(s, dict): return bad
        if type(s.get("bar")) is not int or not 0 <= s["bar"] < len(bars): return bad
        if type(s.get("qty")) is not int or s["qty"] <= 0 or s.get("side") not in ("buy", "sell"): return bad
    cash, fee = Decimal(str(cash)), Decimal(str(fee))
    position, trades, rejected = 0, [], []
    for s in sorted(signals, key=lambda s: s["bar"]):
        i, side, qty = s["bar"], s["side"], s["qty"]
        reason = None
        if i + 1 >= len(bars):
            reason = "no_next_bar"
        else:
            price = Decimal(str(bars[i + 1]["open"]))
            notional = money(qty * price)
            charge = money(notional * fee / 10000)
            if side == "buy" and cash < notional + charge: reason = "insufficient_cash"
            elif side == "sell" and position < qty: reason = "insufficient_position"
        if reason:
            rejected.append({"signal_bar":i,"side":side,"qty":qty,"reason":reason})
            continue
        if side == "buy":
            cash -= notional + charge
            position += qty
        else:
            cash += notional - charge
            position -= qty
        trades.append({"signal_bar":i,"fill_bar":i+1,"side":side,"qty":qty,
                       "price":float(price),"notional":float(notional),"fee":float(charge)})
    equity = cash + (position * Decimal(str(bars[-1]["open"])) if bars else 0)
    return {"trades":trades,"rejected":rejected,"cash":float(money(cash)),
            "position":position,"equity":float(money(equity))}
try:
    with localcontext() as ctx:
        ctx.prec = 1000
        print(json.dumps(main(json.load(sys.stdin))))
except (ValueError, TypeError):
    print(json.dumps({"error":"invalid_input"}))
'''


def self_check() -> dict:
    """Prove sensitivity with full reference/scaffold/domain-mutant CLI runs.

    No model calls. Requires a running Docker daemon and python:3.12-slim.
    Infrastructure failure is not evidence that a faulty implementation was caught.
    """
    checks = []
    references = {
        "calibration-intent-v1": _REFERENCE_ROUTE,
        "calibration-config-path-v1": _REFERENCE_CONFIG,
        "calibration-next-bar-v1": _REFERENCE_MARKET,
    }
    mutants = {
        "calibration-intent-v1": _REFERENCE_ROUTE.replace(
            'elif text in ("收工", "今天到这里", "结束本次会话", "that\'s all for now"):',
            'elif "收工" in text or text in ("今天到这里", "结束本次会话", "that\'s all for now"):'),
        "calibration-config-path-v1": _REFERENCE_CONFIG.replace(
            'path = mapping[x["id"]]', 'path = "skills/" + x["id"] + "/SKILL.md"'),
        "calibration-next-bar-v1": _REFERENCE_MARKET.replace(
            'bars[i + 1]["open"]', 'bars[i]["open"]'),
    }
    targets = {"calibration-intent-v1": "worker_narrative",
               "calibration-config-path-v1": "mapped_path_not_guessed",
               "calibration-next-bar-v1": "next_open_not_signal_open"}
    with tempfile.TemporaryDirectory(prefix="calibration-selfcheck-") as tmp:
        workspace = Path(tmp) / "candidate"
        workspace.mkdir()
        for task_id, reference in references.items():
            (workspace / "app.py").write_text(reference, encoding="utf-8")
            good = evaluate(task_id, workspace)
            failed = [c["name"] + ": " + c["detail"] for c in good["checks"] if not c["passed"]]
            checks.append(_check(task_id + "/reference", good["passed"],
                                 f'{len(good["checks"])} checks; ' + ("all passed" if not failed else repr(failed))))
            for label, source in (("scaffold", _STUB), ("domain_mutant", mutants[task_id])):
                (workspace / "app.py").write_text(source, encoding="utf-8")
                bad = evaluate(task_id, workspace)
                caught = [c["name"] for c in bad["checks"] if not c["passed"] and
                          c["detail"].startswith("JSON mismatch:")]
                passed = good["passed"] and not bad["passed"] and bool(caught)
                if label == "domain_mutant":
                    passed = passed and source != reference and targets[task_id] in caught
                checks.append(_check(task_id + "/" + label, passed, "semantic failures: " + repr(caught)))
        for label, source, marker in (
            ("timeout", "while True: pass\n", "timed out"),
            ("output_limit", 'import sys\nwhile True: sys.stdout.write("x"*65536); sys.stdout.flush()\n', "output limit"),
            ("invalid_json", 'print("not json")\n', "JSONDecodeError"),
            ("nonzero_exit", 'raise SystemExit(3)\n', "container exit 3"),
        ):
            (workspace / "app.py").write_text(source, encoding="utf-8")
            result = _invoke(workspace, {}, timeout=2 if label == "timeout" else _TIMEOUT)
            checks.append(_check("harness/" + label, not result["ok"] and marker in result["detail"], result["detail"]))
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


if __name__ == "__main__":
    report = self_check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
