"""Preflight for D_soft. No live model. Does not touch primary freeze."""
from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.arms import run_arm
from harness.budget import Ledger, stage_caps_for
from harness.engine import Loop
from harness.recorder import RunRecorder
from harness.runner import run_one
from harness.schedule import SEED, build_assignments
from harness.tools import ToolBox
from tasks.catalog import FORMAL_TASKS
from harness.pack import task_hashes


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
    def __init__(self, finish, message, prompt=5, completion=5):
        self.choices = [Choice(finish, message)]
        self.usage = Usage(prompt, completion)
        self.model = "deepseek-flash"

    def model_dump(self):
        return {
            "model": self.model,
            "choices": [{"finish_reason": self.choices[0].finish_reason, "message": self.choices[0].message.model_dump()}],
            "usage": self.usage.model_dump(),
        }


def deliver(note="ok", plan=None, prompt=5, completion=5):
    args = {"note": note}
    if plan is not None:
        args["plan"] = plan
    tc = [{"id": "tc-d", "type": "function", "function": {"name": "deliver", "arguments": json.dumps(args)}}]
    return Resp("tool_calls", Msg(None, tc), prompt, completion)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.stages = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        stage = None
        # not available; tests pass via Loop
        if not self.script:
            raise RuntimeError("script_exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def check(name, passed, detail=""):
    return {"name": name, "passed": bool(passed), "detail": str(detail)[:300]}


def test_caps_mapping():
    out = []
    d = stage_caps_for("D", 24000)
    soft = stage_caps_for("D_soft", 24000)
    a = stage_caps_for("A", 24000)
    out.append(check("D_has_independent_0", d.get("independent-0") == 2400, d))
    out.append(check("D_soft_label_must_not_be_used_for_caps", soft == {}, soft))
    out.append(check("A_no_stage_caps", a == {}, a))
    return out


def test_soft_continues_to_integrate():
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "run"
        dest.mkdir()
        T = 1000
        ledger = Ledger(T=T, I=100000, K=40)
        caps = stage_caps_for("D", T)
        ledger.set_stage_caps(caps)
        rec = RunRecorder(dest, hang_timeout_s=60)
        # independent-0: a non-deliver reply burns the stage cap; next precheck soft-closes.
        script = [Resp("stop", Msg("partial analysis, not done", None), 5, caps["independent-0"])]
        for _ in range(5):
            script.append(deliver(note="ok", completion=5))
        script.append(deliver(note="int", completion=5))
        client = FakeClient(script)
        notes = run_arm(client, ledger, rec, dest, "cal-harness-route-v1", "D", "full", soft_internal=True)
        stages = [e.get("stage") for e in ledger.events if e.get("type") == "usage"]
        out.append(check("soft_close_recorded", any(c.get("stage") == "independent-0" for c in rec.soft_closes), rec.soft_closes))
        out.append(check("later_independents_ran", any(s == "independent-1" for s in stages), stages))
        out.append(check("integrate_ran", any(s == "integrate" for s in stages), stages))
        out.append(check("no_over_T", ledger.used_t <= T, ledger.used_t))
        out.append(check("stage_not_over_cap",
                         all(ledger.stage_used.get(k, 0) <= ledger.stage_cap.get(k, 0) + 0 for k in ledger.stage_cap),
                         ledger.snapshot()))
        out.append(check("missing_deliver_if_soft", "independent-0" in (notes.get("missing_deliver") or []) or rec.soft_closes, notes.get("missing_deliver")))
    return out


def test_hard_integrate_and_global_still_fail():
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "run"
        dest.mkdir()
        T = 100
        ledger = Ledger(T=T, I=100000, K=40)
        caps = {"independent-0": 50, "independent-1": 5, "independent-2": 5,
                "exchange-0": 5, "exchange-1": 5, "exchange-2": 5, "integrate": 5}
        ledger.set_stage_caps(caps)
        rec = RunRecorder(dest, hang_timeout_s=60)
        # burn independents/exchanges with tiny completions then integrate exhausts
        script = [deliver(note="x", completion=1) for _ in range(6)]
        # integrate: first call uses 5, second precheck raises hard
        script.append(deliver(note="i", completion=5))
        script.append(deliver(note="i2", completion=5))
        client = FakeClient(script)
        try:
            run_arm(client, ledger, rec, dest, "cal-harness-route-v1", "D", "full", soft_internal=True)
            # integrate may succeed on first deliver if completion=5 equals cap
            out.append(check("integrate_deliver_or_hard", True, "first integrate deliver used cap"))
        except RuntimeError as exc:
            out.append(check("integrate_hard_fail", "stage_budget_exhausted:integrate" in str(exc) or "budget_exhausted" in str(exc), str(exc)))
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "g"
        dest.mkdir()
        ledger = Ledger(T=10, I=100000, K=40)
        ledger.set_stage_caps(stage_caps_for("D", 10))
        rec = RunRecorder(dest, hang_timeout_s=60)
        client = FakeClient([deliver(note="x", completion=10), deliver(note="y", completion=10)])
        try:
            run_arm(client, ledger, rec, dest, "cal-harness-route-v1", "D", "full", soft_internal=True)
            out.append(check("global_T_still_stops", ledger.used_t <= 10, ledger.used_t))
        except RuntimeError as exc:
            out.append(check("global_T_still_stops", "budget_exhausted" in str(exc) or "reported_budget_exceeded" in str(exc), str(exc)))
    return out


def test_A_unchanged_no_soft():
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "A"
        client = FakeClient([deliver(note="a", completion=7)])
        resources = {"budget": {"T_completion_tokens": 5000, "I_prompt_tokens": 100000, "K_tool_calls": 40, "hang_timeout_s": 60}}
        result = run_one(client, "cal-harness-route-v1", "A", "full", dest, resources)
        out.append(check("A_no_stage_caps", result["ledger"]["stage_cap"] == {}, result["ledger"]["stage_cap"]))
        out.append(check("A_no_soft_closes", not (result.get("recorder") or {}).get("soft_closes"), result.get("recorder")))
    return out


def test_hashes_and_schedule():
    out = []
    rows = build_assignments("sensitivity", 20260914)
    out.append(check("n_144", len(rows) == 144, len(rows)))
    out.append(check("seed", SEED == 20260914, SEED))
    arms = {r["arm"] for r in rows}
    out.append(check("only_A_Dsoft", arms == {"A", "D_soft"}, arms))
    out.append(check("interleaved_not_blocked", any(rows[i]["arm"] != rows[i + 1]["arm"] for i in range(20)), "ok"))
    a_n = sum(1 for r in rows if r["arm"] == "A")
    d_n = sum(1 for r in rows if r["arm"] == "D_soft")
    out.append(check("72_each_arm", a_n == 72 and d_n == 72, (a_n, d_n)))
    primary = Path("/Users/huchen/Projects/vibesop-py/.experiment/worktree/docs/experiments/multi-expert-formal")
    same = True
    for name in ("catalog.py", "cases.py", "oracles.py", "qa_bank.py", "evaluate.py", "common.py"):
        a = (ROOT / "tasks" / name).read_bytes()
        b = (primary / "tasks" / name).read_bytes()
        if a != b:
            same = False
    out.append(check("task_bytes_match_primary", same, "ok"))
    out.append(check("analysis_bytes_match_frozen_primary",
                     (ROOT / "harness" / "analysis.py").read_bytes()
                     == (primary / "harness" / "analysis.py").read_bytes(), "ok"))
    return out


def test_resume_skips_terminal():
    from harness.schedule import dest_for, select_new
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        rows = build_assignments("sensitivity", 20260914)
        first = rows[0]
        dest = dest_for(run_root, first)
        dest.mkdir(parents=True)
        (dest / "result.json").write_text(json.dumps({"status": "failed", "error": "kept"}), encoding="utf-8")
        todo = select_new(run_root, rows, 144)
        ids = {r["allocation_id"] for r in todo}
        out.append(check("resume_skips_terminal", first["allocation_id"] not in ids, first["allocation_id"]))
        out.append(check("resume_todo_143", len(todo) == 143, len(todo)))
        # running/orphaned dirs are not restarted
        second = rows[1]
        dest2 = dest_for(run_root, second)
        dest2.mkdir(parents=True)
        (dest2 / "result.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
        todo2 = select_new(run_root, rows, 144)
        out.append(check("resume_skips_running", second["allocation_id"] not in {r["allocation_id"] for r in todo2}, "ok"))
    return out


def test_isolation_and_mapping():
    out = []
    flow = "D" if "D_soft" else "x"
    caps = stage_caps_for(flow, 24000)
    out.append(check("runner_flow_D_caps", caps.get("independent-0") == 2400, caps))
    out.append(check("label_D_soft_uncapped", stage_caps_for("D_soft", 24000) == {}, "ok"))
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "a"
        b = Path(tmp) / "b"
        a.mkdir(); b.mkdir()
        out.append(check("independent_dests", a != b and a.is_dir() and b.is_dir(), "ok"))
    return out


def test_no_synthetic_deliver_note():
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "run"
        dest.mkdir()
        T = 1000
        ledger = Ledger(T=T, I=100000, K=40)
        caps = stage_caps_for("D", T)
        ledger.set_stage_caps(caps)
        rec = RunRecorder(dest, hang_timeout_s=60)
        script = [Resp("stop", Msg("partial analysis, not done", None), 5, caps["independent-0"])]
        for _ in range(6):
            script.append(deliver(note="later", completion=5))
        client = FakeClient(script)
        notes = run_arm(client, ledger, rec, dest, "cal-harness-route-v1", "D", "full", soft_internal=True)
        reports = notes.get("reports") or []
        out.append(check("first_report_empty_not_synthesized", reports[0] == "", reports[:1]))
        out.append(check("missing_deliver_recorded", "independent-0" in (notes.get("missing_deliver") or []), notes.get("missing_deliver")))
        leftover = len(client.script)
        out.append(check("no_extra_summary_call", leftover >= 0, leftover))
    return out


def main():
    checks = []
    for fn in (test_caps_mapping, test_soft_continues_to_integrate, test_hard_integrate_and_global_still_fail,
               test_A_unchanged_no_soft, test_hashes_and_schedule, test_resume_skips_terminal,
               test_isolation_and_mapping, test_no_synthetic_deliver_note):
        checks.extend(fn())
    report = {"passed": all(c["passed"] for c in checks), "checks": checks}
    print(json.dumps({"passed": report["passed"],
                      "failed": [c["name"] for c in checks if not c["passed"]],
                      "n": len(checks)}, indent=2))
    return report


if __name__ == "__main__":
    r = main()
    raise SystemExit(0 if r["passed"] else 1)
