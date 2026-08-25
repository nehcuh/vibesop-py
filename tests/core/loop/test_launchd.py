"""Tests for launchd plist generation (Phase C).

Covers:
    - cron → StartInterval / StartCalendarInterval conversion
    - plist XML structure (Label, ProgramArguments, schedule)
    - path-with-spaces handling (E.1 must-fix: plistlib handles XML escaping)
    - env_overrides propagation
    - argv injection safety (ProgramArguments is an array, no shell)
    - bootstrap/bootout command shape (modern launchctl, E.3 must-fix)
"""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from vibesop.core.loop.launchd import (
    LAUNCHD_LABEL_PREFIX,
    bootout_command,
    bootstrap_command,
    cron_to_start_calendar,
    cron_to_start_interval_seconds,
    default_plist_path,
    plist_filename,
    plist_label,
    render_plist,
    schedule_for_cron,
)
from vibesop.core.loop.models import LoopSpec
from vibesop.core.loop.scheduler import CronExpr

# ─── cron → launchd schedule conversion ────────────────────────────


class TestCronConversion:
    def test_every_15_min_becomes_start_interval(self) -> None:
        assert cron_to_start_interval_seconds("*/15 * * * *") == 900

    def test_every_5_min_becomes_start_interval(self) -> None:
        assert cron_to_start_interval_seconds("*/5 * * * *") == 300

    def test_every_30_min_becomes_start_interval(self) -> None:
        assert cron_to_start_interval_seconds("*/30 * * * *") == 1800

    def test_every_7_min_not_clean_divisor_returns_none(self) -> None:
        # 60 % 7 != 0 — not a clean divisor, fall back to StartCalendarInterval.
        assert cron_to_start_interval_seconds("*/7 * * * *") is None

    def test_every_31_min_out_of_range_returns_none(self) -> None:
        # > 30 — too sparse, fall back to StartCalendarInterval.
        assert cron_to_start_interval_seconds("*/31 * * * *") is None

    def test_non_step_pattern_returns_none(self) -> None:
        assert cron_to_start_interval_seconds("0,15,30,45 * * * *") is None
        assert cron_to_start_interval_seconds("0 4 * * *") is None

    def test_step_with_other_field_constrained_returns_none(self) -> None:
        # Hour fixed → not "every N minutes around the clock"
        assert cron_to_start_interval_seconds("*/15 4 * * *") is None

    def test_daily_at_4_17_becomes_calendar(self) -> None:
        cron = CronExpr("17 4 * * *")
        cal = cron_to_start_calendar(cron)
        assert cal == {"Minute": [17], "Hour": [4]}

    def test_weekly_on_sunday_becomes_calendar(self) -> None:
        # Cron Sunday = 0; launchd accepts 0 or 7 but 7 is unambiguous —
        # deep-diagnosis-2026-07-24 P1-1: emit 7 to satisfy strict consumers.
        cron = CronExpr("0 2 * * 0")
        cal = cron_to_start_calendar(cron)
        assert cal == {"Minute": [0], "Hour": [2], "Weekday": [7]}

    def test_dow_7_normalises_to_0(self) -> None:
        # POSIX allows 7 = Sunday; CronExpr normalises 7→0 internally,
        # then launchd converter re-emits as 7 (see test_weekly_on_sunday).
        cron = CronExpr("0 2 * * 7")
        cal = cron_to_start_calendar(cron)
        assert cal == {"Minute": [0], "Hour": [2], "Weekday": [7]}

    def test_dow_weekday_range_preserves_mon_to_sat(self) -> None:
        """Mon-Sat cron (1-6) must pass through unchanged — only Sunday (0)
        gets remapped to 7."""
        cron = CronExpr("0 2 * * 1-6")
        cal = cron_to_start_calendar(cron)
        assert cal == {"Minute": [0], "Hour": [2], "Weekday": [1, 2, 3, 4, 5, 6]}

    def test_step_in_minute_expands_to_array(self) -> None:
        # */7 not clean divisor → falls through to CronExpr, expands to array
        cron = CronExpr("*/7 * * * *")
        cal = cron_to_start_calendar(cron)
        assert cal is not None
        assert cal["Minute"] == [0, 7, 14, 21, 28, 35, 42, 49, 56]

    def test_every_minute_wildcard_returns_none(self) -> None:
        # `* * * * *` → all fields wildcard → caller falls back to StartInterval=60
        cron = CronExpr("* * * * *")
        assert cron_to_start_calendar(cron) is None

    def test_schedule_for_cron_prefers_start_interval_when_clean(self) -> None:
        s = schedule_for_cron("*/15 * * * *")
        assert s.key == "StartInterval"
        assert s.value == 900

    def test_schedule_for_cron_falls_back_to_calendar(self) -> None:
        s = schedule_for_cron("17 4 * * *")
        assert s.key == "StartCalendarInterval"
        assert s.value == {"Minute": [17], "Hour": [4]}

    def test_schedule_for_cron_every_minute_uses_interval_60(self) -> None:
        # `* * * * *` → no StartCalendarInterval (all wildcard), fall back to 60s
        s = schedule_for_cron("* * * * *")
        assert s.key == "StartInterval"
        assert s.value == 60


# ─── plist rendering ───────────────────────────────────────────────


def _spec(**overrides: object) -> LoopSpec:
    base: dict[str, object] = {
        "name": "test-loop",
        "schedule": "*/15 * * * *",
        "skill_id": "some-skill",
    }
    base.update(overrides)
    return LoopSpec.model_validate(base)


class TestRenderPlist:
    def test_label_and_filename_match(self) -> None:
        assert plist_label("instinct-assemble") == f"{LAUNCHD_LABEL_PREFIX}.instinct-assemble"
        assert (
            plist_filename("instinct-assemble") == f"{LAUNCHD_LABEL_PREFIX}.instinct-assemble.plist"
        )

    def test_default_plist_path_in_home_launchagents(self) -> None:
        p = default_plist_path("foo")
        assert p.parent == Path.home() / "Library" / "LaunchAgents"
        assert p.name == "com.vibesop.loop.foo.plist"

    def test_render_produces_valid_xml(self, tmp_path: Path) -> None:
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["Label"] == plist_label("test-loop")

    def test_program_arguments_invoke_vibe_loop_tick(self, tmp_path: Path) -> None:
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        # Default prefix "uv run vibe" + tick args.
        assert parsed["ProgramArguments"] == [
            "uv",
            "run",
            "vibe",
            "loop",
            "tick",
            "--name",
            "test-loop",
        ]

    def test_custom_prefix_with_spaces_kept_whole(self, tmp_path: Path) -> None:
        """E.1 must-fix: paths with spaces must survive as a single argv
        element. plistlib handles XML escaping; we just need to feed it the
        pre-split argv (which shlex.split does)."""
        spec = _spec()
        plist_bytes = render_plist(
            spec,
            project_root=tmp_path,
            vibe_prefix='"/path/with space/uv" run vibe',
        )
        parsed = plistlib.loads(plist_bytes)
        argv = parsed["ProgramArguments"]
        assert argv[0] == "/path/with space/uv"  # path kept whole
        assert argv[1:3] == ["run", "vibe"]
        assert argv[3:] == ["loop", "tick", "--name", "test-loop"]

    def test_working_directory_is_project_root(self, tmp_path: Path) -> None:
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["WorkingDirectory"] == str(tmp_path)

    def test_env_overrides_propagate(self, tmp_path: Path) -> None:
        spec = _spec(env_overrides={"VIBE_TEST_VAR": "abc", "PYTHONPATH": "/x"})
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["EnvironmentVariables"] == {"VIBE_TEST_VAR": "abc", "PYTHONPATH": "/x"}

    def test_no_env_overrides_no_key(self, tmp_path: Path) -> None:
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert "EnvironmentVariables" not in parsed

    def test_start_interval_used_for_every_15(self, tmp_path: Path) -> None:
        spec = _spec(schedule="*/15 * * * *")
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["StartInterval"] == 900
        assert "StartCalendarInterval" not in parsed

    def test_start_calendar_used_for_absolute_schedule(self, tmp_path: Path) -> None:
        spec = _spec(schedule="17 4 * * *")
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["StartCalendarInterval"] == {"Minute": [17], "Hour": [4]}
        assert "StartInterval" not in parsed

    def test_run_at_load_false(self, tmp_path: Path) -> None:
        """Critical: we don't want ticks firing immediately on login."""
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["RunAtLoad"] is False

    def test_logs_under_loop_dir(self, tmp_path: Path, monkeypatch) -> None:
        """K-P1-1 regression: logs must live under ``~/.vibe/loops/<name>/``
        (the LoopStore location), NOT under ``project_root/.vibe/loops/``.
        The project-local dir is never created, so launchd would refuse to
        spawn the job (StandardOutPath parent missing)."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["StandardOutPath"] == str(
            tmp_path / ".vibe" / "loops" / "test-loop" / "out.log"
        )
        assert parsed["StandardErrorPath"] == str(
            tmp_path / ".vibe" / "loops" / "test-loop" / "err.log"
        )

    def test_logs_do_not_use_project_root(self, tmp_path: Path, monkeypatch) -> None:
        """K-P1-1 negative: logs must NOT point into project_root even when
        project_root differs from home. If they did, the directory likely
        wouldn't exist and launchd would fail to spawn the job."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        project_root = tmp_path / "project"
        project_root.mkdir()
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=project_root)
        parsed = plistlib.loads(plist_bytes)
        # WorkingDirectory is still project_root (for `uv run`).
        assert parsed["WorkingDirectory"] == str(project_root)
        # But logs go to home, NOT project_root.
        assert "/project/.vibe/loops/" not in parsed["StandardOutPath"]
        assert parsed["StandardOutPath"].startswith(str(tmp_path / "home"))

    def test_custom_log_paths_respected(self, tmp_path: Path) -> None:
        spec = _spec()
        out = tmp_path / "out.log"
        err = tmp_path / "err.log"
        plist_bytes = render_plist(spec, project_root=tmp_path, stdout_path=out, stderr_path=err)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["StandardOutPath"] == str(out)
        assert parsed["StandardErrorPath"] == str(err)

    def test_loop_base_dir_drives_log_paths(self, tmp_path: Path) -> None:
        """deep-diagnosis-2026-07-24 P1-6: when LoopStore is configured with a
        custom base_dir, plist log paths must follow it — otherwise logs end
        up under the default ``~/.vibe/loops`` while tick state lives under
        the custom dir, decoupling logs from the data they describe."""
        custom_base = tmp_path / "custom-loops"
        spec = _spec()
        plist_bytes = render_plist(spec, project_root=tmp_path, loop_base_dir=custom_base)
        parsed = plistlib.loads(plist_bytes)
        assert parsed["StandardOutPath"] == str(custom_base / "test-loop" / "out.log")
        assert parsed["StandardErrorPath"] == str(custom_base / "test-loop" / "err.log")

    def test_shell_injection_in_name_is_safe(self, tmp_path: Path) -> None:
        """ProgramArguments is an array — no shell interpretation. Even if a
        malicious spec name contained shell metacharacters, they would be
        passed to vibe as a literal --name argument.

        LoopSpec validation already restricts name to kebab-case, so this
        test documents the defense-in-depth: even if validation were
        bypassed, the plist itself is safe.
        """
        # Inject a hypothetical malicious name (bypassing validation via
        # object.__setattr__ for the test).
        spec = _spec()
        object.__setattr__(spec, "name", "foo; rm -rf /")
        plist_bytes = render_plist(spec, project_root=tmp_path)
        parsed = plistlib.loads(plist_bytes)
        # The argv is a list of strings; launchd runs the binary directly,
        # no shell. The semicolons are literal characters in argv[6].
        assert parsed["ProgramArguments"][-1] == "foo; rm -rf /"
        assert parsed["Label"] == f"{LAUNCHD_LABEL_PREFIX}.foo; rm -rf /"


# ─── launchctl command shape (E.3 modern API) ──────────────────────


class TestLaunchctlCommands:
    """Asserts command SHAPE against a fixed uid (501), not the host's real
    ``os.getuid`` — the latter doesn't exist on Windows and would turn these
    shape assertions into AttributeError (gate44 簇D)."""

    def test_bootstrap_uses_modern_gui_uid_form(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("os.getuid", lambda: 501, raising=False)
        plist_path = tmp_path / "foo.plist"
        cmd = bootstrap_command(plist_path)
        assert cmd[0] == "launchctl"
        assert cmd[1] == "bootstrap"
        assert cmd[2] == "gui/501"
        assert cmd[3] == str(plist_path)

    def test_bootout_uses_modern_gui_uid_label_form(self, monkeypatch) -> None:
        monkeypatch.setattr("os.getuid", lambda: 501, raising=False)
        cmd = bootout_command("instinct-assemble")
        assert cmd[0] == "launchctl"
        assert cmd[1] == "bootout"
        assert cmd[2] == "gui/501/com.vibesop.loop.instinct-assemble"

    def test_commands_do_not_use_deprecated_load_unload(self, tmp_path: Path) -> None:
        # macOS 10.10+ deprecated `launchctl load/unload`. Modern API is
        # `bootstrap/bootout`. (E.3 must-fix.)
        assert "load" not in bootstrap_command(tmp_path / "x.plist")
        assert "load" not in bootout_command("x")

    def test_bootstrap_command_guards_non_posix(self, tmp_path: Path, monkeypatch) -> None:
        """Self-defense (gate44 簇D): a caller that forgets the platform gate
        gets a clear error, not a bare AttributeError on os.getuid-less hosts."""
        import os as _os

        monkeypatch.delattr(_os, "getuid", raising=False)
        with pytest.raises(RuntimeError, match="launchd"):
            bootstrap_command(tmp_path / "x.plist")
        with pytest.raises(RuntimeError, match="launchd"):
            bootout_command("x")
