"""Tool-using conversation loop with preserved history and pre-request limits."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .budget import Ledger
from .llm import MODEL, TEMPERATURE, THINKING, complete, usage_dict
from .recorder import SCHEMA_HASH, RunRecorder, dump
from .tools import SCHEMA, ToolBox

SYSTEM = (
    "You are participating in a coding experiment. Follow the supplied task. "
    "Use only the provided tools. Python standard library only. "
    "Write files with write_file. Run visible tests or the CLI to check work. "
    "Hidden tests are not available. Call deliver when THIS STAGE is complete. "
    "deliver ends the current stage, not necessarily the whole run. "
    "Do not assume host files, secrets, or prior memory."
)

FINAL_STAGES = {"main", "check", "integrate"}


def _message_dict(message) -> dict:
    if hasattr(message, "model_dump"):
        data = message.model_dump()
    elif isinstance(message, dict):
        data = dict(message)
    else:
        data = {"role": getattr(message, "role", "assistant"), "content": getattr(message, "content", None)}
    data.pop("reasoning_content", None)
    return data


class Loop:
    def __init__(self, client, ledger: Ledger, recorder: RunRecorder, toolbox: ToolBox, *,
                 member: str | None = None, soft_internal: bool = False):
        self.client = client
        self.ledger = ledger
        self.recorder = recorder
        self.toolbox = toolbox
        self.member = member
        self.soft_internal = soft_internal

    def _soft_close(self, stage: str, reason: str, messages: list) -> None:
        event = {
            "type": "soft_close",
            "stage": stage,
            "member": self.member,
            "reason": reason,
            "delivered": bool(self.toolbox.delivered),
            "messages": len(messages),
        }
        if not hasattr(self.recorder, "soft_closes"):
            self.recorder.soft_closes = []
        self.recorder.soft_closes.append(event)
        self.recorder.events = getattr(self.recorder, "events", [])
        if hasattr(self.ledger, "events"):
            self.ledger.events.append(event)

    def _allow_soft(self, stage: str, exc: BaseException) -> bool:
        if not self.soft_internal:
            return False
        msg = str(exc)
        if not msg.startswith("stage_budget_exhausted:"):
            return False
        return stage.startswith("independent-") or stage.startswith("exchange-")

    def run(self, messages: list, *, stage: str, stop_on_deliver: bool = True) -> list:
        tools = SCHEMA
        while True:
            self.recorder.check_hang()
            try:
                cap = self.ledger.precheck(messages, stage=stage, tools=tools)
            except RuntimeError as exc:
                if self._allow_soft(stage, exc):
                    self._soft_close(stage, str(exc), messages)
                    return messages
                raise
            n = self.recorder.allocate_call()
            started = datetime.now(timezone.utc).isoformat()
            request = {
                "call_id": n,
                "stage": stage,
                "member": self.member,
                "model": MODEL,
                "temperature": TEMPERATURE,
                "thinking": THINKING,
                "max_tokens": cap,
                "sdk_max_retries": 0,
                "started_at": started,
                "messages": messages,
                "tools_schema_hash": SCHEMA_HASH,
                "tool_names": [t["function"]["name"] for t in tools],
            }
            self.recorder.write_request(n, request)
            try:
                response = complete(self.client, messages, max_tokens=cap, tools=tools)
            except Exception as exc:
                dump(self.recorder.error_path(n), {
                    "call_id": n,
                    "type": type(exc).__name__,
                    "message": str(exc)[:1500],
                    "stage": stage,
                    "member": self.member,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "request_persisted_before_http": True,
                })
                raise
            data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
            dump(self.recorder.response_path(n), data)
            usage = usage_dict(response)
            request.update({
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "returned_model": getattr(response, "model", None),
            })
            dump(self.recorder.request_path(n), request)
            self.ledger.record_usage(usage, stage=stage)
            choice = response.choices[0]
            finish = choice.finish_reason
            message = _message_dict(choice.message)
            tool_calls = list(message.get("tool_calls") or [])
            if finish == "length":
                self.recorder.partial_stages.append(stage)
                if tool_calls:
                    messages.append(message)
                    for call in tool_calls:
                        cid = call.get("id") or "truncated"
                        payload = {"error": "truncated_tool_call", "executed": False, "call_id": n}
                        messages.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(payload)})
                        self.recorder.record_tool({
                            "call_id": n,
                            "stage": stage,
                            "member": self.member,
                            "tool": (call.get("function") or {}).get("name"),
                            "executed": False,
                            "reason": "truncated_tool_call",
                        })
                else:
                    messages.append(message)
                if stage in FINAL_STAGES:
                    raise RuntimeError("incomplete_final_response")
                messages.append({
                    "role": "user",
                    "content": "Your previous model message was truncated. Matching tool results were filled as truncated_tool_call and were NOT executed. Continue. Internal truncation is allowed; the final delivery must be complete.",
                })
                continue
            if finish not in {"stop", "tool_calls"}:
                raise RuntimeError("incomplete_response:" + str(finish))
            messages.append(message)
            if tool_calls:
                for call in tool_calls:
                    fn = call.get("function") or {}
                    name = fn.get("name") or ""
                    raw = fn.get("arguments") or "{}"
                    try:
                        arguments = json.loads(raw) if isinstance(raw, str) else raw
                    except json.JSONDecodeError:
                        arguments = {"_parse_error": raw[:500]}
                    self.ledger.consume_tool()
                    result = self.toolbox.execute(
                        name, arguments, call_id=n, stage=stage, member=self.member, recorder=self.recorder,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "content": result[:16000],
                    })
                    if name == "deliver" and stop_on_deliver:
                        return messages
                continue
            if stop_on_deliver and not self.toolbox.delivered:
                messages.append({
                    "role": "user",
                    "content": "No tool call was made. Use write_file/read_file/run_visible_tests/run_cli/ask_clarification as needed, then call deliver to end this stage.",
                })
                continue
            return messages
