"""Identical tool set for every arm. Hidden tests and host secrets stay out."""
from __future__ import annotations

import json
from pathlib import Path

from tasks.catalog import TASKS
from tasks.common import invoke
from tasks.evaluate import evaluate_visible
from tasks.qa_bank import answer, published_questions

SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 file from the workspace.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a UTF-8 file under the workspace. Path must be relative.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List relative files in the workspace.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_visible_tests",
            "description": "Run the visible tests shipped in the workspace. Hidden tests are not available.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cli",
            "description": "Run python <entry> in isolated Docker with JSON stdin. Default entry app.py.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "string"},
                    "entry": {"type": "string"},
                },
                "required": ["payload"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "Ask a published clarification question by id. All arms receive the same answer.",
            "parameters": {
                "type": "object",
                "properties": {"question_id": {"type": "string"}},
                "required": ["question_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deliver",
            "description": "End this stage or the run. Files already written are the artifact.",
            "parameters": {
                "type": "object",
                "properties": {"note": {"type": "string"}, "plan": {"type": "object"}},
            },
        },
    },
]


def _safe(workspace: Path, rel: str) -> Path:
    if not isinstance(rel, str) or rel == "" or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError("invalid_path")
    path = (workspace / rel).resolve()
    if workspace.resolve() not in path.parents and path != workspace.resolve():
        raise ValueError("path_escapes_workspace")
    return path


class ToolBox:
    def __init__(self, task_id: str, workspace: Path, *, owned_files: set[str] | None = None):
        self.task_id = task_id
        self.workspace = Path(workspace)
        self.owned_files = owned_files
        self.violations: list[dict] = []
        self.traces: list[dict] = []
        self.delivered = False
        self.deliver_payload: dict = {}
        self.task = TASKS[task_id]

    def execute(self, name: str, arguments: dict, *, call_id: int | None = None,
                stage: str | None = None, member: str | None = None, recorder=None) -> str:
        record = {"tool": name, "arguments": arguments, "call_id": call_id, "stage": stage, "member": member}
        try:
            result = self._dispatch(name, arguments or {})
            record["ok"] = True
            record["result"] = result
            self.traces.append(record)
            if recorder is not None:
                recorder.record_tool(record)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            record["ok"] = False
            record["error"] = f"{type(exc).__name__}: {exc}"
            self.traces.append(record)
            if recorder is not None:
                recorder.record_tool(record)
            return json.dumps({"error": record["error"]})

    def _dispatch(self, name: str, arguments: dict):
        if name == "read_file":
            path = _safe(self.workspace, arguments.get("path"))
            if not path.is_file():
                return {"error": "not_found"}
            return {"path": arguments["path"], "content": path.read_text(encoding="utf-8")}
        if name == "write_file":
            rel = arguments.get("path")
            content = arguments.get("content")
            if not isinstance(content, str):
                return {"error": "content_must_be_string"}
            if self.owned_files is not None and rel not in self.owned_files:
                self.violations.append({"type": "ownership", "path": rel, "owned": sorted(self.owned_files)})
                return {"error": "ownership_violation", "path": rel, "owned": sorted(self.owned_files)}
            path = _safe(self.workspace, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"ok": True, "path": rel, "bytes": len(content.encode("utf-8"))}
        if name == "list_files":
            rows = []
            for item in sorted(self.workspace.rglob("*")):
                if item.is_file():
                    rows.append(str(item.relative_to(self.workspace)))
            return {"files": rows}
        if name == "run_visible_tests":
            report = evaluate_visible(self.task_id, self.workspace)
            return {
                "passed": report["passed"],
                "checks": [{"name": c["name"], "passed": c["passed"], "detail": c["detail"][:300]} for c in report["checks"]],
            }
        if name == "run_cli":
            entry = arguments.get("entry") or "app.py"
            if entry not in set(self.task.get("entries") or ["app.py"]):
                if entry != "app.py":
                    return {"error": "entry_not_allowed"}
            env = dict(self.task.get("env") or {})
            volumes = []
            extra = tuple(self.task.get("extra_tmpfs") or ())
            home = None
            if self.task.get("home_task"):
                home = self.workspace / ".isolated-home"
                home.mkdir(exist_ok=True)
                env["VIBE_HOME"] = "/tmp/vibe-home"
                volumes = [(str(home), "/tmp/vibe-home", "rw")]
                extra = ()
            result = invoke(
                self.workspace,
                arguments.get("payload"),
                entry=entry,
                writable=bool(self.task.get("writable")),
                env=env or None,
                extra_tmpfs=extra,
                volumes=tuple(volumes),
            )
            return result
        if name == "ask_clarification":
            qid = arguments.get("question_id")
            known = {row["id"] for row in published_questions(self.task_id)}
            if qid not in known:
                return {"error": "unknown_question_id", "known": sorted(known)}
            return {"question_id": qid, "answer": answer(self.task_id, qid)}
        if name == "deliver":
            self.delivered = True
            self.deliver_payload = arguments or {}
            return {"ok": True, "delivered": True}
        return {"error": "unknown_tool"}
