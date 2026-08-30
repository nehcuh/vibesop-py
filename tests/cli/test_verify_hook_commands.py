"""M2: verify route_hook_command — lenient classify + full unsafe rules.

Matrix updated 2026-08-28 after probing Claude Code 2.1.220 live: hooks
spawn via ``bash -c`` with the session CWD, so config-relative
``hooks/<name>.sh`` (the S51 canonical form) 127s from any other
directory. The healthy win32 form is now the same as Unix:
``bash <posix-abs-path>``, quoted as one bash word when the path contains
whitespace (unquoted spaced paths word-split under ``bash -c`` — the
``C:/Users/First Last/`` class). Bare quoted POSIX (no ``bash`` prefix)
stays rejected: pre-2.1 hosts path-join configDir onto it.
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


def test_win32_unquoted_spaced_path_fails(tmp_path, monkeypatch) -> None:
    """M1 class: `bash -c` word-splits an unquoted spaced path into 127."""
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ["bash C:/Users/First Last/.claude/hooks/vibesop-route.sh", USER_POWERSHELL],
        "win32",
    )
    assert not result["pass"], result["detail"]


def test_win32_quoted_spaced_canonical_passes(tmp_path, monkeypatch) -> None:
    """Generator output for spaced homes: `bash "<posix-abs>"` is one bash word."""
    result = _route_hook_result(
        tmp_path,
        monkeypatch,
        ['bash "C:/Users/First Last/.claude/hooks/vibesop-route.sh"', USER_POWERSHELL],
        "win32",
    )
    assert result["pass"], result["detail"]


def test_bash_prefixed_config_relative_fails_both_platforms(tmp_path, monkeypatch) -> None:
    """The hooks/ check must see through a ``bash `` prefix: word-level, not
    whole-command — ``bash hooks/<name>.sh`` 127s exactly like the bare form."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy, "bash hooks/vibesop-tool-seq.sh"],
            platform,
        )
        assert not result["pass"], (platform, result["detail"])


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


def test_trailing_basename_mention_after_healthy_route_passes(tmp_path, monkeypatch) -> None:
    """`bash <abs> && echo vibesop-route.sh` mentions the basename as an
    echo argument — not a word-split path tail; must not false-positive."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy + " && echo vibesop-route.sh"],
            platform,
        )
        assert result["pass"], (platform, result["detail"])


def test_operator_prefixed_basename_mention_passes(tmp_path, monkeypatch) -> None:
    """A token right after a shell operator starts a new command word; it is
    not the tail of a split path."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy + " && vibesop-route.sh"],
            platform,
        )
        assert result["pass"], (platform, result["detail"])


def test_cwd_relative_script_fails_both_platforms(tmp_path, monkeypatch) -> None:
    """`bash vibesop-track.sh`, `bash ./…`, `bash subdir/…` resolve against
    the session CWD under the host's bash -c spawn — 127 exactly like
    hooks/x.sh, on every platform."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        for cmd in (
            "bash vibesop-track.sh",
            "bash ./vibesop-track.sh",
            "bash subdir/vibesop-track.sh",
        ):
            result = _route_hook_result(tmp_path, monkeypatch, [healthy, cmd], platform)
            assert not result["pass"], (platform, cmd, result["detail"])
            assert "CWD" in result["detail"], (platform, cmd, result["detail"])


def test_nested_hooks_subdir_script_fails_both_platforms(tmp_path, monkeypatch) -> None:
    """`bash hooks/sub/vibesop-route.sh` is not the config-relative
    hooks/<script>.sh form — it resolves against the session CWD too, so
    the hooks/ exemption must cover only the exact single-level shape."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy, "bash hooks/sub/vibesop-route.sh"],
            platform,
        )
        assert not result["pass"], (platform, result["detail"])
        assert "CWD" in result["detail"], (platform, result["detail"])


def test_bash_dash_c_script_fails_both_platforms(tmp_path, monkeypatch) -> None:
    """`bash -c vibesop-route.sh` (quoted or not) runs the script against
    the session CWD — same 127 class as `bash vibesop-route.sh`."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        for cmd in (
            "bash -c vibesop-route.sh",
            'bash -c "vibesop-route.sh"',
        ):
            result = _route_hook_result(tmp_path, monkeypatch, [healthy, cmd], platform)
            assert not result["pass"], (platform, cmd, result["detail"])
            assert "CWD" in result["detail"], (platform, cmd, result["detail"])


def test_bash_dash_c_non_script_command_passes(tmp_path, monkeypatch) -> None:
    """`bash -c "echo hi"` is a command string, not a script path — the
    dash-c check must not flag it."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy, 'bash -c "echo hi"'],
            platform,
        )
        assert result["pass"], (platform, result["detail"])


def test_unquoted_spaced_relative_script_fails_both_platforms(tmp_path, monkeypatch) -> None:
    """`bash My Dir/vibesop-route.sh` (unquoted space in a *relative* path)
    word-splits into 3+ tokens under the host's bash -c spawn — the script
    resolves against the session CWD and 127s exactly like `bash x.sh`."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy, "bash My Dir/vibesop-route.sh"],
            platform,
        )
        assert not result["pass"], (platform, result["detail"])
        assert "CWD" in result["detail"], (platform, result["detail"])


def test_bash_dash_c_mentioning_basename_passes(tmp_path, monkeypatch) -> None:
    """`bash -c "echo hi vibesop-route.sh"` mentions the basename inside a
    command string — tokens[1] == "-c" exempts it from the spaced-split
    check (it never resolves a script path against the CWD)."""
    for platform, healthy in (("win32", HEALTHY_WIN_ROUTE), ("darwin", HEALTHY_MAC_ROUTE)):
        result = _route_hook_result(
            tmp_path,
            monkeypatch,
            [healthy, 'bash -c "echo hi vibesop-route.sh"'],
            platform,
        )
        assert result["pass"], (platform, result["detail"])


def test_tilde_and_home_prefixed_script_passes(tmp_path, monkeypatch) -> None:
    """`bash ~/.claude/hooks/x.sh` / `bash $HOME/.claude/hooks/x.sh` expand
    to absolute paths under the host's bash -c spawn — not CWD-relative."""
    for platform in ("win32", "darwin"):
        for cmd in (
            "bash ~/.claude/hooks/vibesop-route.sh",
            "bash $HOME/.claude/hooks/vibesop-route.sh",
        ):
            result = _route_hook_result(tmp_path, monkeypatch, [cmd], platform)
            assert result["pass"], (platform, cmd, result["detail"])
