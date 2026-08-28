"""M2: verify route_hook_command — lenient classify + full unsafe rules.

Matrix updated 2026-08-28 after probing Claude Code 2.1.220 live: hooks
spawn via ``bash -c`` with the session CWD, so config-relative
``hooks/<name>.sh`` (the S51 canonical form) 127s from any other
directory. The healthy win32 form is now the same as Unix:
``bash <posix-abs-path>``. Quoted POSIX stays rejected (pre-2.1 hosts
path-join configDir onto it).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from vibesop.cli.commands.verify import PLATFORM_CONFIGS, _check_platform

HEALTHY_MAC_ROUTE = "bash /Users/h/.claude/hooks/vibesop-route.sh"
HEALTHY_WIN_ROUTE = "bash C:/Users/h/.claude/hooks/vibesop-route.sh"
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


def test_win32_absolute_posix_bash_passes(tmp_path, monkeypatch) -> None:
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_WIN_ROUTE, USER_POWERSHELL],
        "win32",
    )
    assert result["pass"], result["detail"]


def test_win32_config_relative_fails(tmp_path, monkeypatch) -> None:
    """S51 canonical form resolves against the session CWD on 2.1.220."""
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ["hooks/vibesop-route.sh", USER_POWERSHELL],
        "win32",
    )
    assert not result["pass"], result["detail"]
    assert "CWD" in result["detail"]


def test_win32_bare_script_fails(tmp_path, monkeypatch) -> None:
    """A bare absolute script (no bash prefix) relies on shebang handling
    that older hosts lack — keep requiring the bash prefix."""
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ["C:/Users/h/.claude/hooks/vibesop-route.sh", USER_POWERSHELL],
        "win32",
    )
    assert not result["pass"], result["detail"]


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


def test_nonwin32_config_relative_form_surfaces(tmp_path, monkeypatch) -> None:
    """The S51 config-relative form is surfaced as a Windows-form command
    on non-win32 hosts too (it cannot work there either)."""
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        [HEALTHY_MAC_ROUTE, "hooks/vibesop-tool-seq.sh"],
        "darwin",
    )
    assert not result["pass"], result["detail"]


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
