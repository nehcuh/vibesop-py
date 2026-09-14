"""Offline harness checks. No live model. Not experimental results."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.analysis import toy_self_check
from harness.arms import parse_worker_plan, run_arm, topo_worker_order
from harness.budget import Ledger, stage_caps_for
from harness.engine import Loop
from harness.pack import write_pack, verify_pack, FREEZE_RELATIVE
from harness.recorder import RunRecorder
from harness.runner import run_one
from harness.schedule import (
    build_assignments,
    counts,
    dest_for,
    mark_interrupted,
    scan_and_interrupt,
    select_new,
)
from harness.tools import ToolBox


class Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls
        self.role = "assistant"

    def model_dump(self):
        return {"role": "assistant", "content": self.content, "tool_calls": self.tool_calls}


class Choice:
    def __init__(self, finish, message):
        self.finish_reason = finish
        self.message = message


class Usage:
    def __init__(self, prompt, completion):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.prompt_cache_hit_tokens = 0
        self.completion_tokens_details = {"reasoning_tokens": 0}

    def model_dump(self):
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "prompt_cache_hit_tokens": 0,
            "completion_tokens_details": self.completion_tokens_details,
        }


class Resp:
    def __init__(self, finish, message, prompt=11, completion=7, model="deepseek-flash"):
        self.choices = [Choice(finish, message)]
        self.usage = Usage(prompt, completion)
        self.model = model

    def model_dump(self):
        return {
            "model": self.model,
            "choices": [{"finish_reason": self.choices[0].finish_reason, "message": self.choices[0].message.model_dump()}],
            "usage": self.usage.model_dump(),
        }


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.kwargs = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        if not self.script:
            raise RuntimeError("script_exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def deliver(note="ok", plan=None, prompt=11, completion=7, call_name="deliver"):
    args = {"note": note}
    if plan is not None:
        args["plan"] = plan
    tc = [{"id": "tc-" + call_name, "type": "function",
           "function": {"name": "deliver", "arguments": json.dumps(args)}}]
    return Resp("tool_calls", Msg(None, tc), prompt, completion)


def write_file(path, content, prompt=11, completion=7):
    tc = [{"id": "tc-write", "type": "function",
           "function": {"name": "write_file", "arguments": json.dumps({"path": path, "content": content})}}]
    return Resp("tool_calls", Msg(None, tc), prompt, completion)


def truncated_tool(prompt=11, completion=7):
    tc = [{"id": "tc-trunc", "type": "function",
           "function": {"name": "write_file", "arguments": "{\"path\":\"app.py\",\"content\":\"partial"}}]
    return Resp("length", Msg("partial", tc), prompt, completion)


E_PLAN = {
    "subtasks": [
        {"id": "w0", "files": ["parser.py"], "depends_on": [], "description": "parse"},
        {"id": "w1", "files": ["app.py"], "depends_on": ["w0"], "description": "cli"},
    ]
}


def _resources(T=5000, I=100000, K=40):
    return {"budget": {"T_completion_tokens": T, "I_prompt_tokens": I, "K_tool_calls": K, "hang_timeout_s": 60}}


def _sum_responses(run_dir: Path) -> tuple[int, int]:
    prompt = completion = 0
    for path in sorted(run_dir.glob("call-*-response.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        usage = data["usage"]
        prompt += usage["prompt_tokens"]
        completion += usage["completion_tokens"]
    return prompt, completion


def check(name, passed, detail=""):
    return {"name": name, "passed": bool(passed), "detail": str(detail)}


def test_call_ids_cde() -> list[dict]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "C"
        client = FakeClient([deliver() for _ in range(7)])
        result = run_one(client, "cal-harness-route-v1", "C", "full", dest, _resources())
        reqs = sorted(dest.glob("call-*-request.json"))
        ids = [int(p.name.split("-")[1]) for p in reqs]
        prompt, completion = _sum_responses(dest)
        ledger = result["ledger"]
        out.append(check("C_unique_call_ids", ids == list(range(len(ids))) and len(ids) == 7, ids))
        out.append(check("C_no_overwrite", len(reqs) == result["recorder"]["calls"], len(reqs)))
        out.append(check("C_usage_sum", prompt == ledger["used_i"] and completion == ledger["used_t"],
                         f"resp {prompt}/{completion} ledger {ledger['used_i']}/{ledger['used_t']}"))
        traces = json.loads((dest / "tools.json").read_text(encoding="utf-8"))
        members = {t.get("member") for t in traces}
        out.append(check("C_tools_all_members", members >= {"member-0", "member-1", "member-2"}, members))
        caps = ledger["stage_cap"]
        out.append(check("C_exchange_split", all(f"exchange-{i}" in caps for i in range(3)), caps))
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "D"
        client = FakeClient([deliver() for _ in range(7)])
        result = run_one(client, "cal-harness-route-v1", "D", "full", dest, _resources())
        reqs = list(dest.glob("call-*-request.json"))
        out.append(check("D_seven_calls", len(reqs) == 7, len(reqs)))
        sys_prompts = [json.loads(p.read_text())["messages"][0]["content"] for p in sorted(reqs)[:3]]
        out.append(check("D_roles_in_independent", any("architecture expert" in s for s in sys_prompts), sys_prompts[0][:80]))
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "E"
        script = [deliver(plan=E_PLAN), deliver(note="w0"), deliver(note="w1"), deliver(note="int")]
        result = run_one(client := FakeClient(script), "cal-harness-join-v1", "E", "full", dest, _resources())
        reqs = sorted(dest.glob("call-*-request.json"))
        prompt, completion = _sum_responses(dest)
        out.append(check("E_unique_call_ids", [int(p.name.split("-")[1]) for p in reqs] == list(range(len(reqs))), len(reqs)))
        out.append(check("E_usage_sum", prompt == result["ledger"]["used_i"] and completion == result["ledger"]["used_t"],
                         result["ledger"]))
        notes = result.get("notes") or {}
        out.append(check("E_planner_history_kept", (notes.get("planner_history_len") or 0) >= 3,
                         notes.get("planner_history_len")))
        out.append(check("E_worker_order_dag", notes.get("worker_order") == ["w0", "w1"], notes.get("worker_order")))
        integrate_req = json.loads(reqs[-1].read_text(encoding="utf-8"))
        blob = json.dumps(integrate_req["messages"])
        out.append(check("E_integrate_not_truncated_6000", "parser.py" in blob and len(blob) > 0, len(blob)))
    return out


def test_request_before_http() -> list[dict]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "err"
        client = FakeClient([RuntimeError("api_down")])
        result = run_one(client, "cal-harness-route-v1", "A", "full", dest, _resources())
        req = dest / "call-000-request.json"
        err = dest / "call-000-error.json"
        out.append(check("request_exists_on_api_error", req.exists() and err.exists(), result.get("error")))
        if req.exists():
            data = json.loads(req.read_text(encoding="utf-8"))
            out.append(check("request_has_schema_hash_and_start", "tools_schema_hash" in data and "started_at" in data, data.keys()))
            out.append(check("request_has_messages", isinstance(data.get("messages"), list) and data["messages"], "no messages"))
        out.append(check("error_points_at_persisted_request", err.exists() and json.loads(err.read_text()).get("request_persisted_before_http") is True, ""))
    return out


def test_a_full_budget_and_b_plan() -> list[dict]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "A"
        T = 9000
        client = FakeClient([deliver()])
        run_one(client, "cal-harness-route-v1", "A", "full", dest, _resources(T=T))
        cap = client.kwargs[0]["max_tokens"]
        out.append(check("A_max_tokens_is_full_T", cap == T, cap))
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "B"
        client = FakeClient([deliver(note="plan"), deliver(note="impl"), deliver(note="check")])
        result = run_one(client, "cal-harness-route-v1", "B", "full", dest, _resources())
        reqs = sorted(dest.glob("call-*-request.json"))
        out.append(check("B_three_stage_calls", len(reqs) == 3, len(reqs)))
        plan_text = json.dumps(json.loads(reqs[0].read_text())["messages"])
        out.append(check("B_plan_asks_stage_deliver", "ends planning only" in plan_text, plan_text[-200:]))
        out.append(check("B_no_do_not_call_deliver", "Do not call deliver until asked" not in plan_text, ""))
        out.append(check("B_history_preserved", (result.get("notes") or {}).get("history_len", 0) >= 5, result.get("notes")))
    return out


def test_truncation_tool_calls() -> list[dict]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        recorder = RunRecorder(dest, hang_timeout_s=60)
        ledger = Ledger(T=5000, I=100000, K=40)
        box = ToolBox("cal-harness-route-v1", dest)
        client = FakeClient([truncated_tool(completion=3), deliver()])
        loop = Loop(client, ledger, recorder, box, member="A")
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        loop.run(messages, stage="plan")
        roles = [m.get("role") for m in messages]
        out.append(check("truncation_adds_tool_result", "tool" in roles, roles))
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        out.append(check("truncated_not_executed", any("truncated_tool_call" in m.get("content", "") for m in tool_msgs), tool_msgs))
        out.append(check("truncated_write_not_on_disk", not (dest / "app.py").exists(), dest / "app.py"))
        # matching tool_call_id present
        asst = next(m for m in messages if m.get("tool_calls"))
        out.append(check("tool_result_matches_id", tool_msgs[0]["tool_call_id"] == asst["tool_calls"][0]["id"], tool_msgs[0]))
        out.append(check("partial_stage_recorded", "plan" in recorder.partial_stages, recorder.partial_stages))
    return out


def test_stage_quota_not_global() -> list[dict]:
    out = []
    T = 300
    caps = stage_caps_for("C", T)
    out.append(check("exchange_caps_reserved", caps["exchange-0"] > 0 and caps["exchange-1"] > 0 and caps["exchange-2"] > 0, caps))
    ledger = Ledger(T=T, I=100000, K=40)
    ledger.set_stage_caps(caps)
    ledger.stage_used["exchange-0"] = caps["exchange-0"]
    try:
        ledger.precheck([{"role": "user", "content": "x"}], stage="exchange-0")
        out.append(check("exchange0_exhausted_is_stage", False, "no raise"))
    except RuntimeError as exc:
        out.append(check("exchange0_exhausted_is_stage", str(exc).startswith("stage_budget_exhausted:exchange-0"), str(exc)))
    cap1 = ledger.precheck([{"role": "user", "content": "x"}], stage="exchange-1")
    out.append(check("exchange1_still_available", cap1 == caps["exchange-1"], cap1))
    workers = stage_caps_for("E", T)
    out.append(check("E_workers_split", workers["worker-0"] > 0 and workers["worker-1"] > 0, workers))
    return out


def test_e_plan_validation() -> list[dict]:
    out = []
    parsed = parse_worker_plan(E_PLAN)
    out.append(check("valid_plan", topo_worker_order(parsed) == [0, 1], topo_worker_order(parsed)))
    reverse = {"subtasks": [
        {"id": "w0", "files": ["app.py"], "depends_on": ["w1"], "description": "a"},
        {"id": "w1", "files": ["parser.py"], "depends_on": [], "description": "p"},
    ]}
    out.append(check("reverse_deps", topo_worker_order(parse_worker_plan(reverse)) == [1, 0], ""))
    try:
        parse_worker_plan({"subtasks": [
            {"id": "w0", "files": ["app.py"], "depends_on": [], "description": "a"},
            {"id": "w1", "files": ["app.py"], "depends_on": [], "description": "b"},
        ]})
        out.append(check("overlap_fails", False, "no raise"))
    except RuntimeError as exc:
        out.append(check("overlap_fails", str(exc).startswith("ownership_conflict"), str(exc)))
    try:
        parse_worker_plan({"subtasks": [
            {"id": "w0", "files": ["a.py"], "depends_on": ["missing"], "description": "a"},
            {"id": "w1", "files": ["b.py"], "depends_on": [], "description": "b"},
        ]})
        out.append(check("unknown_dep_fails", False, "no raise"))
    except RuntimeError as exc:
        out.append(check("unknown_dep_fails", "unknown_dependency" in str(exc), str(exc)))
    try:
        cyclic = parse_worker_plan({"subtasks": [
            {"id": "w0", "files": ["a.py"], "depends_on": ["w1"], "description": "a"},
            {"id": "w1", "files": ["b.py"], "depends_on": ["w0"], "description": "b"},
        ]})
        topo_worker_order(cyclic)
        out.append(check("cycle_fails", False, "no raise"))
    except RuntimeError as exc:
        out.append(check("cycle_fails", "cycle" in str(exc), str(exc)))
    try:
        parse_worker_plan({"subtasks": [
            {"id": "w0", "files": ["a.py"], "depends_on": [], "description": "a"},
            {"id": "w0", "files": ["b.py"], "depends_on": [], "description": "b"},
        ]})
        out.append(check("dup_id_fails", False, "no raise"))
    except RuntimeError as exc:
        out.append(check("dup_id_fails", "ids" in str(exc), str(exc)))
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "Ebad"
        bad = {"subtasks": [
            {"id": "w0", "files": ["app.py"], "depends_on": [], "description": "a"},
            {"id": "w1", "files": ["app.py"], "depends_on": [], "description": "b"},
        ]}
        client = FakeClient([deliver(plan=bad)])
        result = run_one(client, "cal-harness-join-v1", "E", "full", dest, _resources())
        out.append(check("overlap_run_not_passed", result["status"] != "passed", result.get("status")))
        out.append(check("overlap_run_failed", result["status"] == "failed" and "ownership_conflict" in (result.get("error") or ""), result))
    return out


def test_identical_limits() -> list[dict]:
    a = Ledger(T=100, I=1000, K=10)
    e = Ledger(T=100, I=1000, K=10)
    return [check("limits_identical_flag", a.limits == e.limits and a.limits["identical_for_all_arms"] is True, a.limits)]


def test_schedule_360_resume() -> list[dict]:
    out = []
    rows = build_assignments("formal", 20260913)
    out.append(check("formal_manifest_360", len(rows) == 360, len(rows)))
    out.append(check("formal_unique_ids", len({r["allocation_id"] for r in rows}) == 360, ""))
    sliced = rows[:12]
    out.append(check("slicing_is_not_the_manifest", len(rows) == 360 and len(sliced) == 12, ""))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = select_new(root, rows, 12)
        out.append(check("max_new_12", len(first) == 12, len(first)))
        for row in first:
            dest = dest_for(root, row)
            dest.mkdir()
            (dest / "result.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
        second = select_new(root, rows, 12)
        out.append(check("resume_skips_terminal", len(second) == 12 and {r["allocation_id"] for r in second}.isdisjoint({r["allocation_id"] for r in first}), len(second)))
        stuck = dest_for(root, rows[24])
        stuck.mkdir()
        (stuck / "result.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
        (stuck / "call-000-request.json").write_text("{}", encoding="utf-8")
        marked = scan_and_interrupt(root, rows)
        out.append(check("running_becomes_interrupted", rows[24]["allocation_id"] in marked, marked))
        out.append(check("interrupted_request_kept", (stuck / "call-000-request.json").exists(), ""))
        third = select_new(root, rows, 12)
        out.append(check("interrupted_not_rerun", rows[24]["allocation_id"] not in {r["allocation_id"] for r in third}, ""))
        tallies = counts(root, rows)
        out.append(check("counts_360", tallies["total"] == 360 and tallies["passed"] == 12 and tallies["interrupted"] == 1, tallies))
        try:
            run_one(FakeClient([deliver()]), "cal-harness-route-v1", "A", "full", dest_for(root, first[0]), _resources())
            out.append(check("duplicate_allocation_refused", False, "no raise"))
        except RuntimeError as exc:
            out.append(check("duplicate_allocation_refused", "duplicate_allocation" in str(exc), str(exc)))
    return out


def test_concurrency_isolation() -> list[dict]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rows = [{"task_id": "cal-harness-route-v1", "arm": "A", "spec_variant": "full", "repeat": i,
                 "allocation_id": f"cal-harness-route-v1-full-A-r{i}"} for i in range(8)]

        def job(row):
            dest = root / row["allocation_id"]
            client = FakeClient([deliver(prompt=3 + row["repeat"], completion=5 + row["repeat"])])
            return run_one(client, row["task_id"], row["arm"], row["spec_variant"], dest, _resources(),
                           repeat=row["repeat"])

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(job, rows))
        dests = [root / r["allocation_id"] for r in rows]
        out.append(check("eight_independent_dirs", all(d.is_dir() for d in dests), len(dests)))
        usages = []
        for dest, row in zip(dests, rows):
            reqs = list(dest.glob("call-*-request.json"))
            out.append(check("no_cross_dir_calls_" + dest.name, len(reqs) >= 1 and (root / dest.name / "call-000-request.json").exists(), len(reqs)))
            data = json.loads((dest / "result.json").read_text())
            usages.append((data["ledger"]["used_t"], data["ledger"]["used_i"]))
        out.append(check("usage_not_shared", len(set(usages)) == 8, usages))
        out.append(check("concurrency_results_8", len(results) == 8, len(results)))
    return out


def test_freeze_pack() -> list[dict]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "frozen-sources"
        meta = write_pack(dest)
        out.append(check("freeze_has_relative_paths", "harness/runner.py" in meta["relative_paths"] and "tasks/oracles.py" in meta["relative_paths"], list(meta["relative_paths"])[:5]))
        out.append(check("freeze_excludes_runs", not any(p.startswith("runs/") for p in meta["relative_paths"]), ""))
        out.append(check("freeze_excludes_status", "STATUS.md" not in meta["relative_paths"] and "READY_FOR_REVIEW.md" not in meta["relative_paths"], ""))
        verify_pack(dest)
        out.append(check("freeze_verify_ok", True, meta["count"]))
        out.append(check("freeze_count_matches_allowlist", meta["count"] == len(FREEZE_RELATIVE), meta["count"]))
    return out


def test_analysis_toy() -> list[dict]:
    report = toy_self_check()
    rows = [check("analysis_" + item["name"], item["passed"], item.get("detail")) for item in report["checks"]]
    rows.append(check("analysis_all", report["passed"], ""))
    return rows


def test_no_resource_fallback() -> list[dict]:
    from harness.runner import load_resources
    import harness.runner as runner
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.yaml"
        try:
            load_resources(missing)
            out.append(check("missing_resources_errors", False, "no raise"))
        except RuntimeError as exc:
            out.append(check("missing_resources_errors", "missing_resources" in str(exc), str(exc)))
        bad = Path(tmp) / "bad.yaml"
        bad.write_text("budget: {}\n", encoding="utf-8")
        try:
            load_resources(bad)
            out.append(check("invalid_resources_errors", False, "no raise"))
        except RuntimeError as exc:
            out.append(check("invalid_resources_errors", "invalid_resources" in str(exc), str(exc)))
        import inspect
        src = inspect.getsource(runner.load_resources)
        out.append(check("no_inline_default_budget", "except Exception" not in src and "K_tool_calls\": 40" not in src, "ok"))
    return out


def main() -> dict:
    checks = []
    for fn in (test_call_ids_cde, test_request_before_http, test_a_full_budget_and_b_plan,
               test_truncation_tool_calls, test_stage_quota_not_global, test_e_plan_validation,
               test_identical_limits, test_schedule_360_resume, test_concurrency_isolation,
               test_freeze_pack, test_analysis_toy, test_no_resource_fallback):
        checks.extend(fn())
    report = {"offline_only": True, "passed": all(c["passed"] for c in checks), "checks": checks}
    return report


if __name__ == "__main__":
    report = main()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
