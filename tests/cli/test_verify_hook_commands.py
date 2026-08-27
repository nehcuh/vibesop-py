"""M2: verify route_hook_command — lenient classify + full unsafe rules.

Matrix from the pull-20260827 fix plan (v4.1): route existence uses
token basenames (not whole-command substrings), the unsafe scan covers
only vibesop commands, win32 accepts canonical 1-token forms (including
spaced usernames), and non-win32 surfaces Windows-form commands instead
of ignoring them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from vibesop.cli.commands.verify import PLATFORM_CONFIGS, _check_platform

HEALTHY_MAC_ROUTE = "bash /Users/h/.claude/hooks/vibesop-route.sh"
HEALTHY_WIN_ROUTE = "hooks/vibesop-route.sh"
USER_POWERSHELL = r"powershell.exe -File C:\Users\x\hook.ps1"


def _route_hook_result(
    tmp_path: Path, monkeypatch: Any, commands: list[str], platform: str
) -> dict[str, Any]:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setitem(PLATFORM_CONFIGS["claude-code"], "config_dir", tmp_path)
    hooks = {
        "UserPromptSubmit": [
            {"matcher": "", "hooks": [{"type": "command", "command": c}]} for c in commands
        ]
    }
    (tmp_path / "settings.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    results = _check_platform("claude-code")
    return next(r for r in results if r["id"] == "route_hook_command")


def test_user_powershell_backslash_plus_healthy_route_passes(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path, monkeypatch, [USER_POWERSHELL, HEALTHY_MAC_ROUTE], "darwin"
    )
    assert result["pass"], result["detail"]


def test_user_command_mentioning_basename_is_not_route(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ["bash /abs/my-vibesop-route.sh", HEALTHY_MAC_ROUTE],
        "darwin",
    )
    assert result["pass"], result["detail"]


def test_win32_canonical_relative_passes(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_WIN_ROUTE, USER_POWERSHELL],
        "win32",
    )
    assert result["pass"], result["detail"]


def test_win32_quoted_posix_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ['"C:/Users/h/.claude/hooks/vibesop-route.sh"', USER_POWERSHELL],
        "win32",
    )
    assert not result["pass"], result["detail"]


def test_win32_quoted_spaced_username_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ['"C:/Users/First Last/.claude/hooks/vibesop-route.sh"', USER_POWERSHELL],
        "win32",
    )
    assert not result["pass"], result["detail"]


def test_win32_bash_prefix_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(tmp_path, monkeypatch, ["bash C:/x/vibesop-route.sh"], "win32")
    assert not result["pass"]


def test_win32_tab_bash_prefix_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(tmp_path, monkeypatch, ["bash\tC:/x/vibesop-route.sh"], "win32")
    assert not result["pass"]


def test_nonwin32_backslash_tool_seq_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_MAC_ROUTE, r"bash C:\Users\h\.claude\hooks\vibesop-tool-seq.sh"],
        "darwin",
    )
    assert not result["pass"]


def test_nonwin32_drive_token_without_backslash_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_MAC_ROUTE, "bash C:/x/vibesop-tool-seq.sh"],
        "darwin",
    )
    assert not result["pass"]
    assert "drive" in result["detail"].lower()


def test_nonwin32_quoted_spaced_drive_token_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_MAC_ROUTE, '"C:/Users/First Last/.claude/hooks/vibesop-tool-seq.sh"'],
        "darwin",
    )
    assert not result["pass"], result["detail"]


def test_nonwin32_uppercase_backslash_variant_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_MAC_ROUTE, r"bash C:\Users\h\.claude\hooks\VIBESOP-TOOL-SEQ.SH"],
        "darwin",
    )
    assert not result["pass"], result["detail"]


def test_missing_route_fails(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ["bash /Users/h/.claude/hooks/vibesop-tool-seq.sh"],
        "darwin",
    )
    assert not result["pass"]
    assert "no vibesop-route.sh" in result["detail"]


def test_short_tokens_do_not_crash(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(tmp_path, monkeypatch, ["a C: " + HEALTHY_MAC_ROUTE], "darwin")
    assert result["pass"], result["detail"]


def test_url_token_no_false_drive(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_MAC_ROUTE + " https://example.com/x"],
        "darwin",
    )
    assert result["pass"], result["detail"]
