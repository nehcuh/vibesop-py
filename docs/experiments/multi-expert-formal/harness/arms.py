"""Five organizational arms. Tools, totals and task input are identical."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tasks.catalog import TASKS, spec_for
from tasks.qa_bank import clarification_block

from .budget import Ledger
from .engine import SYSTEM, Loop
from .recorder import RunRecorder
from .tools import ToolBox

ROLES = [
    ("architecture", "architecture, interfaces and invariants"),
    ("implementation", "implementation details and file layout"),
    ("quality", "acceptance, error contracts and regressions"),
]


def _seed_workspace(task_id: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, content in TASKS[task_id]["files"].items():
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _user_prompt(task_id: str, spec_variant: str) -> str:
    spec = spec_for(task_id, spec_variant)
    files = json.dumps(TASKS[task_id]["files"], ensure_ascii=False)
    return (
        spec
        + "\n\n"
        + clarification_block(task_id)
        + "\nInitial files:\n"
        + files
        + "\nVisible tests are in visible.json and via run_visible_tests."
        + " Hidden acceptance runs only after the final deliver."
        + " Question id `contract` returns the complete normative spec."
    )


def _identity(arm: str, index: int) -> str:
    if arm != "D":
        return "Analyze independently without an assigned expert role. You have the same tools as every other participant."
    name, focus = ROLES[index]
    return f"You are the {name} expert; focus on {focus}. Role is the only difference from the unlabelled committee."


def _copy_ws(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _safe_rel(path: str) -> bool:
    p = Path(path)
    return isinstance(path, str) and path != "" and not p.is_absolute() and ".." not in p.parts


def parse_worker_plan(plan: object) -> list[dict]:
    if not isinstance(plan, dict):
        raise RuntimeError("invalid_decomposition:not_object")
    subtasks = plan.get("subtasks")
    if not isinstance(subtasks, list) or len(subtasks) != 2:
        raise RuntimeError("invalid_decomposition:count")
    parsed = []
    for row in subtasks:
        if not isinstance(row, dict) or not isinstance(row.get("files"), list):
            raise RuntimeError("invalid_decomposition:row")
        wid = row.get("id")
        if not isinstance(wid, str) or wid.strip() == "":
            raise RuntimeError("invalid_decomposition:ids")
        files = [str(x) for x in row["files"]]
        if not files or not all(_safe_rel(f) for f in files):
            raise RuntimeError("invalid_decomposition:files")
        deps = [str(x) for x in (row.get("depends_on") or [])]
        parsed.append({
            "id": wid,
            "files": files,
            "depends_on": deps,
            "description": str(row.get("description") or ""),
        })
    ids = [p["id"] for p in parsed]
    if len(set(ids)) != len(ids):
        raise RuntimeError("invalid_decomposition:ids")
    id_set = set(ids)
    for p in parsed:
        for dep in p["depends_on"]:
            if dep not in id_set:
                raise RuntimeError("invalid_decomposition:unknown_dependency")
    overlap = sorted(set(parsed[0]["files"]) & set(parsed[1]["files"]))
    if overlap:
        raise RuntimeError("ownership_conflict:" + ",".join(overlap))
    return parsed


def topo_worker_order(parsed: list[dict]) -> list[int]:
    index = {p["id"]: i for i, p in enumerate(parsed)}
    incoming = {p["id"]: 0 for p in parsed}
    edges = {p["id"]: [] for p in parsed}
    for p in parsed:
        for dep in p["depends_on"]:
            if dep == p["id"]:
                raise RuntimeError("invalid_decomposition:cycle")
            edges[dep].append(p["id"])
            incoming[p["id"]] += 1
    ready = sorted(i for i, p in enumerate(parsed) if incoming[p["id"]] == 0)
    order: list[int] = []
    while ready:
        i = ready.pop(0)
        order.append(i)
        for nxt in edges[parsed[i]["id"]]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                ready.append(index[nxt])
                ready.sort()
    if len(order) != len(parsed):
        raise RuntimeError("invalid_decomposition:cycle")
    return order


def _collect(notes: dict, recorder: RunRecorder, extra: dict) -> dict:
    notes.update(extra)
    notes["partial"] = list(recorder.partial_stages)
    notes["all_tool_traces"] = list(recorder.tool_events)
    notes["calls"] = recorder.call_id
    return notes


def run_arm(client, ledger: Ledger, recorder: RunRecorder, run_dir: Path,
            task_id: str, arm: str, spec_variant: str) -> dict:
    workspace = run_dir / "workspace"
    _seed_workspace(task_id, workspace)
    prompt = _user_prompt(task_id, spec_variant)
    notes: dict = {"arm": arm, "conflicts": [], "reports": []}
    if arm == "A":
        box = ToolBox(task_id, workspace)
        loop = Loop(client, ledger, recorder, box, member="A")
        loop.run([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], stage="main")
        return _collect(notes, recorder, {
            "violations": box.violations,
            "member_traces": {"A": box.traces},
            "delivered": box.delivered,
        })
    if arm == "B":
        box = ToolBox(task_id, workspace)
        loop = Loop(client, ledger, recorder, box, member="B")
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt + "\nStage: PLAN. Write a stage-completion plan report. "
             "When the plan is ready, call deliver with note=your plan. That ends planning only; "
             "implementation and checks follow in this same conversation. Do not implement yet."},
        ]
        loop.run(messages, stage="plan", stop_on_deliver=True)
        box.delivered = False
        messages.append({"role": "user", "content": "Stage: IMPLEMENT. The plan stage is closed. Write files, run visible tests, then call deliver when implementation is ready."})
        loop.run(messages, stage="implement", stop_on_deliver=True)
        box.delivered = False
        messages.append({"role": "user", "content": "Stage: CHECK. Re-read the spec, fix issues, run visible tests, then call deliver with the final artifact on disk."})
        loop.run(messages, stage="check", stop_on_deliver=True)
        return _collect(notes, recorder, {
            "violations": box.violations,
            "member_traces": {"B": box.traces},
            "delivered": box.delivered,
            "history_len": len(messages),
        })
    if arm in {"C", "D"}:
        reports = []
        histories = []
        member_traces: dict[str, list] = {}
        member_violations = []
        for i in range(3):
            private = run_dir / f"member-{i}-workspace"
            _copy_ws(workspace, private)
            box = ToolBox(task_id, private)
            loop = Loop(client, ledger, recorder, box, member=f"member-{i}")
            messages = [
                {"role": "system", "content": SYSTEM + "\n" + _identity(arm, i)},
                {"role": "user", "content": prompt + "\nIndependent analysis. You may use tools on your private copy. "
                 "Call deliver with a note containing your analysis. Your files are not the official artifact."},
            ]
            loop.run(messages, stage=f"independent-{i}", stop_on_deliver=True)
            report = (box.deliver_payload or {}).get("note") or ""
            reports.append(report)
            histories.append(messages)
            member_traces[f"independent-{i}"] = list(box.traces)
            member_violations.append(box.violations)
        frozen = json.dumps(reports, ensure_ascii=False)
        exchange = []
        for i in range(3):
            box = ToolBox(task_id, run_dir / f"member-{i}-workspace")
            loop = Loop(client, ledger, recorder, box, member=f"member-{i}")
            messages = list(histories[i]) + [{
                "role": "user",
                "content": "One synchronous exchange. All initial reports (frozen):\n"
                + frozen
                + "\nYour original report:\n"
                + reports[i]
                + "\nGive a short correction or agreement based on evidence. Call deliver with that note.",
            }]
            box.delivered = False
            loop.run(messages, stage=f"exchange-{i}", stop_on_deliver=True)
            exchange.append((box.deliver_payload or {}).get("note") or "")
            histories[i] = messages
            member_traces[f"exchange-{i}"] = list(box.traces)
        for src in [f"independent-{i}" for i in range(3)] + [f"exchange-{i}" for i in range(3)]:
            ledger.transfer_unused(src, "integrate")
        box = ToolBox(task_id, workspace)
        loop = Loop(client, ledger, recorder, box, member="member-0")
        integrator = list(histories[0]) + [{
            "role": "user",
            "content": "You are the designated integrator (member 0). Official workspace is a fresh copy of the initial files, not the private analysis copies. Exchange notes:\n"
            + json.dumps(exchange, ensure_ascii=False)
            + "\nImplement, test with visible tools, and deliver the official artifact.",
        }]
        loop.run(integrator, stage="integrate", stop_on_deliver=True)
        member_traces["integrate"] = list(box.traces)
        return _collect(notes, recorder, {
            "reports": reports,
            "exchange": exchange,
            "violations": box.violations,
            "member_violations": member_violations,
            "member_traces": member_traces,
            "delivered": box.delivered,
        })
    if arm == "E":
        box = ToolBox(task_id, workspace)
        loop = Loop(client, ledger, recorder, box, member="planner")
        plan_messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt + "\nStage: decompose into EXACTLY two subtasks. Call deliver with "
             "plan={\"subtasks\":[{\"id\":\"w0\",\"files\":[\"relative paths this worker may write\"],"
             "\"depends_on\":[],\"description\":\"...\"}, {\"id\":\"w1\",...}]}. "
             "Worker ids must be unique. depends_on must name the other worker or be empty. "
             "No cycles. File lists must be disjoint; overlapping files fail the run."},
        ]
        loop.run(plan_messages, stage="plan", stop_on_deliver=True)
        parsed = parse_worker_plan((box.deliver_payload or {}).get("plan"))
        order = topo_worker_order(parsed)
        notes["plan"] = parsed
        notes["worker_order"] = [parsed[i]["id"] for i in order]
        ledger.transfer_unused_split("plan", ["worker-0", "worker-1"])
        worker_traces = []
        member_traces = {"planner": list(box.traces)}
        for idx in order:
            owned = set(parsed[idx]["files"])
            stage_name = f"worker-{idx}"
            wbox = ToolBox(task_id, workspace, owned_files=owned)
            wloop = Loop(client, ledger, recorder, wbox, member=parsed[idx]["id"])
            wmessages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt + "\nShared plan:\n" + json.dumps(parsed, ensure_ascii=False)
                 + f"\nYou are worker {parsed[idx]['id']}. You may write ONLY {sorted(owned)}. "
                 + "Dependencies must already be on disk if listed. Implement your files, then deliver."},
            ]
            wloop.run(wmessages, stage=stage_name, stop_on_deliver=True)
            worker_traces.append({
                "id": parsed[idx]["id"],
                "index": idx,
                "violations": wbox.violations,
                "traces": wbox.traces,
                "messages": wmessages,
            })
            member_traces[stage_name] = list(wbox.traces)
            notes["conflicts"].extend(wbox.violations)
        for src in ("worker-0", "worker-1"):
            ledger.transfer_unused(src, "integrate")
        ibox = ToolBox(task_id, workspace)
        iloop = Loop(client, ledger, recorder, ibox, member="integrator")
        # Keep the planner conversation; attach full worker traces (not truncated).
        plan_messages.append({
            "role": "user",
            "content": "Workers finished in DAG order "
            + json.dumps(notes["worker_order"])
            + ". Full worker traces and their complete messages follow. Integrate and repair on the real workspace, then deliver.\n"
            + json.dumps(
                [{"id": w["id"], "violations": w["violations"], "traces": w["traces"], "messages": w["messages"]}
                 for w in worker_traces],
                ensure_ascii=False,
                default=str,
            ),
        })
        iloop.run(plan_messages, stage="integrate", stop_on_deliver=True)
        member_traces["integrate"] = list(ibox.traces)
        return _collect(notes, recorder, {
            "violations": ibox.violations,
            "member_traces": member_traces,
            "worker_traces": [{"id": w["id"], "violations": w["violations"], "traces": w["traces"]} for w in worker_traces],
            "delivered": ibox.delivered,
            "planner_history_len": len(plan_messages),
        })
    raise ValueError("unknown arm")
