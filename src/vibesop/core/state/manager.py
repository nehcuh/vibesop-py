"""Unified state management for all VibeSOP modes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class StateManager:
    """Unified state manager for all modes."""

    def __init__(self, state_root: str | Path = ".vibe/state"):
        self.state_root = Path(state_root).resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)

    def write(self, mode: str, scope: str, data: dict[str, Any]) -> Path:
        state_dir = self.state_root / mode / scope
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"

        existing: dict[str, Any] = {}
        if state_file.exists():
            try:
                with state_file.open("r") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}

        now = datetime.now().isoformat()
        merged = {
            "mode": mode,
            "scope": scope,
            "active": True,
            "updated_at": now,
            **existing,
            **data,
        }
        if "created_at" not in merged:
            merged["created_at"] = now

        tmp_file = state_file.with_suffix(".tmp")
        with tmp_file.open("w") as f:
            json.dump(merged, f, indent=2, default=str)
        tmp_file.rename(state_file)
        return state_file

    def read(self, mode: str, scope: str) -> dict[str, Any] | None:
        state_file = self.state_root / mode / scope / "state.json"
        if not state_file.exists():
            return None
        try:
            with state_file.open("r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self, mode: str, scope: str) -> bool:
        state_dir = self.state_root / mode / scope
        if not state_dir.exists():
            return False
        state_file = state_dir / "state.json"
        if state_file.exists():
            data = self.read(mode, scope)
            if data:
                data["active"] = False
                data["updated_at"] = datetime.now().isoformat()
                self.write(mode, scope, data)
            return True
        return False

    def list_active(self) -> list[dict[str, Any]]:
        active_states = []
        if not self.state_root.exists():
            return active_states
        for mode_dir in self.state_root.iterdir():
            if not mode_dir.is_dir():
                continue
            for scope_dir in mode_dir.iterdir():
                if not scope_dir.is_dir():
                    continue
                state_file = scope_dir / "state.json"
                if state_file.exists():
                    try:
                        with state_file.open("r") as f:
                            data = json.load(f)
                        if data.get("active", False):
                            active_states.append(data)
                    except (json.JSONDecodeError, OSError):
                        continue
        return active_states

    def list_active_states(self) -> list[dict[str, Any]]:
        """Alias for list_active for API compatibility."""
        return self.list_active()

    def get_state_path(self, mode: str, scope: str) -> Path:
        return self.state_root / mode / scope / "state.json"
