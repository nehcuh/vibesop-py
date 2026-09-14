"""Run-level recorder: monotonic call ids, atomic files, full tool log."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .tools import SCHEMA

SCHEMA_BLOB = json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)
SCHEMA_HASH = hashlib.sha256(SCHEMA_BLOB.encode("utf-8")).hexdigest()


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class RunRecorder:
    """Shared by every Loop in a run. Never resets call ids."""

    def __init__(self, run_dir: Path, *, hang_timeout_s: int = 600):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.call_id = 0
        self.tool_events: list[dict] = []
        self.partial_stages: list[str] = []
        self.hang_timeout_s = hang_timeout_s
        self.started_mono = time.monotonic()
        self.schema_hash = SCHEMA_HASH
        schema_path = self.run_dir / "tools-schema.json"
        if schema_path.exists():
            raise RuntimeError("tools_schema_already_exists")
        dump(schema_path, {"hash": SCHEMA_HASH, "schema": SCHEMA})

    def elapsed(self) -> float:
        return time.monotonic() - self.started_mono

    def check_hang(self) -> None:
        if self.elapsed() > self.hang_timeout_s:
            raise RuntimeError("hang_timeout")

    def allocate_call(self) -> int:
        n = self.call_id
        self.call_id += 1
        path = self.request_path(n)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(path, flags)
        except FileExistsError as exc:
            raise RuntimeError("call_log_overwrite_forbidden:" + path.name) from exc
        os.close(fd)
        return n

    def request_path(self, n: int) -> Path:
        return self.run_dir / f"call-{n:03d}-request.json"

    def response_path(self, n: int) -> Path:
        return self.run_dir / f"call-{n:03d}-response.json"

    def error_path(self, n: int) -> Path:
        return self.run_dir / f"call-{n:03d}-error.json"

    def write_request(self, n: int, payload: dict) -> None:
        path = self.request_path(n)
        if not path.exists():
            raise RuntimeError("request_slot_missing:" + path.name)
        dump(path, payload)

    def record_tool(self, event: dict) -> None:
        event = dict(event)
        event.setdefault("at", datetime.now(timezone.utc).isoformat())
        event["seq"] = len(self.tool_events)
        self.tool_events.append(event)
        with (self.run_dir / "tools.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def snapshot(self) -> dict:
        return {
            "calls": self.call_id,
            "tool_events": list(self.tool_events),
            "partial_stages": list(self.partial_stages),
            "tools_schema_hash": self.schema_hash,
            "hang_timeout_s": self.hang_timeout_s,
            "elapsed_s": self.elapsed(),
        }
