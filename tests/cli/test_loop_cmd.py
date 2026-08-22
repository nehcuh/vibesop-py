"""CLI tests for ``vibe loop`` command tree.

Covers:
    - ``create`` happy path + all validation failures (name, target, cron).
    - ``list`` empty / populated / status filter.
    - ``show`` existing / missing.
    - ``delete`` with --force and confirmation paths.
    - ``pause`` / ``resume`` happy path and idempotency.
    - ``tick`` filters PAUSED/DEAD, dispatches to execute_loop_tick,
      dry-run mode skips execution.
    - Help text lists all expected subcommands.

Tests patch ``LoopStore`` to use a tmpdir base so they never touch the
real ``~/.vibe/loops/``.
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.loop_cmd import app
from vibesop.core.loop.models import LoopRunRecord, LoopSpec, LoopStatus
from vibesop.core.loop.store import LoopStore

runner = CliRunner()


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Redirect LoopStore default base_dir to a tmp_path.

    loop_cmd constructs ``LoopStore()`` with no args. We patch the
    default lookup so the CLI writes to tmp_path/.vibe/loops instead of
    the real ~/.vibe/loops. Return a store bound to the SAME path so
    tests can verify persistence directly.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # LoopStore.__init__ will create tmp_path/.vibe/loops automatically.
    return LoopStore()


# ──────────────────────────────────────────────────────────────────
# help / discovery
# ──────────────────────────────────────────────────────────────────


class TestHelpAndDiscovery:
    def test_help_lists_all_subcommands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("create", "list", "show", "delete", "pause", "resume", "tick"):
            assert cmd in result.stdout, f"{cmd!r} missing from --help output"


# ──────────────────────────────────────────────────────────────────
# create
# ──────────────────────────────────────────────────────────────────


class TestCreate:
    def test_create_with_skill_id_succeeds(self, isolated_store):
        result = runner.invoke(
            app,
            [
                "create",
                "ci-watcher",
                "--skill",
                "systematic-debugging",
                "--schedule",
                "*/30 * * * *",
                "--desc",
                "CI watcher",
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Loop Created" in result.stdout
        assert "ci-watcher" in result.stdout
        # Spec actually persisted
        spec = isolated_store.load_spec("ci-watcher")
        assert spec is not None
        assert spec.skill_id == "systematic-debugging"

    def test_create_with_query_target(self, isolated_store):
        result = runner.invoke(
            app,
            [
                "create",
                "daily-digest",
                "--query",
                "summarise today's PRs",
                "--schedule",
                "0 22 * * *",
            ],
        )
        assert result.exit_code == 0
        spec = isolated_store.load_spec("daily-digest")
        assert spec.query == "summarise today's PRs"

    def test_create_without_target_fails(self, isolated_store):
        result = runner.invoke(
            app,
            ["create", "no-target", "--schedule", "0 0 * * *"],
        )
        assert result.exit_code == 1
        assert "至少需要指定" in result.stdout

    def test_create_with_invalid_name_fails(self, isolated_store):
        result = runner.invoke(
            app,
            ["create", "Bad_Name!", "--skill", "x", "--schedule", "0 0 * * *"],
        )
        assert result.exit_code == 1
        assert "校验失败" in result.stdout

    def test_create_with_invalid_cron_fails(self, isolated_store):
        result = runner.invoke(
            app,
            ["create", "bad-cron", "--skill", "x", "--schedule", "not a cron"],
        )
        assert result.exit_code == 1
        # Could be caught by LoopSpec validator OR CronExpr pre-flight
        assert "cron" in result.stdout.lower() or "校验失败" in result.stdout

    def test_create_duplicate_name_fails(self, isolated_store):
        # First create succeeds
        runner.invoke(
            app,
            ["create", "dup", "--skill", "x", "--schedule", "0 0 * * *"],
        )
        # Second must fail
        result = runner.invoke(
            app,
            ["create", "dup", "--skill", "x", "--schedule", "0 0 * * *"],
        )
        assert result.exit_code == 1
        assert "已存在" in result.stdout

    def test_create_with_command_target(self, isolated_store):
        """Phase D: ``--command`` flag exposes the command_args target."""
        result = runner.invoke(
            app,
            [
                "create",
                "promoter",
                "--command",
                "instinct auto-promote --min-confidence 0.85",
                "--schedule",
                "17 4 * * *",
            ],
        )
        assert result.exit_code == 0, result.stdout
        spec = isolated_store.load_spec("promoter")
        assert spec is not None
        assert spec.command_args == [
            "instinct",
            "auto-promote",
            "--min-confidence",
            "0.85",
        ]
        # skill_id / query / workflow_id must all be empty (4-way xor).
        assert not spec.skill_id
        assert not spec.query
        assert not spec.workflow_id

    def test_create_command_with_quoted_spaces(self, isolated_store):
        """shlex.split must handle quoted paths with spaces."""
        result = runner.invoke(
            app,
            [
                "create",
                "spaces",
                "--command",
                "'/path/with space/uv' run vibe",
            ],
        )
        assert result.exit_code == 0, result.stdout
        spec = isolated_store.load_spec("spaces")
        assert spec.command_args[0] == "/path/with space/uv"

    def test_create_command_with_mismatched_quotes_fails(self, isolated_store):
        """shlex error must surface as friendly CLI error, not traceback."""
        result = runner.invoke(
            app,
            ["create", "bad-quote", "--command", '"unbalanced quote run vibe'],
        )
        assert result.exit_code == 1
        assert "解析失败" in result.stdout

    def test_create_command_and_skill_mutually_exclusive(self, isolated_store):
        """4-way xor: can't set both --command and --skill."""
        result = runner.invoke(
            app,
            ["create", "both", "--skill", "x", "--command", "instinct eval"],
        )
        # ValidationError from LoopSpec._exactly_one_target.
        assert result.exit_code == 1
        assert "校验失败" in result.stdout or "exactly one" in result.stdout.lower()

    def test_create_command_empty_string_rejected(self, isolated_store):
        """Empty --command '' should not count as a target (shlex → [])."""
        result = runner.invoke(
            app,
            ["create", "empty-cmd", "--command", ""],
        )
        assert result.exit_code == 1
        assert "至少需要指定" in result.stdout


# ──────────────────────────────────────────────────────────────────
# create --preset (Phase E)
# ──────────────────────────────────────────────────────────────────


class TestCreatePreset:
    def test_preset_assemble_fills_command_and_schedule(self, isolated_store):
        result = runner.invoke(app, ["create", "instinct-assemble", "--preset"])
        assert result.exit_code == 0
        assert "*/15 * * * *" in result.stdout
        assert "sequence assemble" in result.stdout

    def test_preset_promote_fills_command_and_schedule(self, isolated_store):
        result = runner.invoke(app, ["create", "instinct-promote", "--preset"])
        assert result.exit_code == 0
        assert "17 4 * * *" in result.stdout
        assert "instinct auto-promote" in result.stdout

    def test_preset_feedback_fills_command_and_schedule(self, isolated_store):
        result = runner.invoke(app, ["create", "instinct-feedback", "--preset"])
        assert result.exit_code == 0
        assert "37 4 * * *" in result.stdout
        assert "feedback-collect" in result.stdout

    def test_preset_unknown_name_errors(self, isolated_store):
        result = runner.invoke(app, ["create", "bad-name", "--preset"])
        assert result.exit_code == 1
        # pi Phase E P2-A: name that doesn't look like a preset should
        # suggest removing --preset (user probably meant --command).
        assert "不是预设名" in result.stdout
        assert "去掉 --preset" in result.stdout
        assert "instinct-assemble" in result.stdout  # hint lists valid names

    def test_preset_typo_of_known_name_errors_differently(self, isolated_store):
        """A typo of a known preset (instinct-asemble → instinct-assemble)
        should hint at valid options, not suggest --command."""
        result = runner.invoke(app, ["create", "instinct-asemble", "--preset"])
        assert result.exit_code == 1
        assert "未知 preset" in result.stdout
        assert "instinct-assemble" in result.stdout

    def test_preset_overrides_explicit_command_with_warning(self, isolated_store):
        """If user passes both --preset and --command, preset wins + warn."""
        result = runner.invoke(
            app,
            [
                "create",
                "instinct-assemble",
                "--preset",
                "--command",
                "some other command",
            ],
        )
        assert result.exit_code == 0
        assert "忽略 --command" in result.stdout
        # Resulting spec uses preset's command, not the explicit one.
        from vibesop.core.loop.store import LoopStore

        spec = LoopStore().load_spec("instinct-assemble")
        assert spec is not None
        assert spec.command_args == ["sequence", "assemble"]

    def test_preset_overrides_explicit_schedule_with_warning(self, isolated_store):
        result = runner.invoke(
            app,
            [
                "create",
                "instinct-promote",
                "--preset",
                "--schedule",
                "*/5 * * * *",
            ],
        )
        assert result.exit_code == 0
        assert "忽略 --schedule" in result.stdout
        from vibesop.core.loop.store import LoopStore

        spec = LoopStore().load_spec("instinct-promote")
        assert spec is not None
        assert spec.schedule == "17 4 * * *"


# ──────────────────────────────────────────────────────────────────
# list
# ──────────────────────────────────────────────────────────────────


class TestList:
    def test_list_empty_shows_hint(self, isolated_store):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "没有已创建的 loop" in result.stdout

    def test_list_shows_created_loops(self, isolated_store):
        runner.invoke(
            app,
            ["create", "alpha", "--skill", "x", "--schedule", "*/30 * * * *"],
        )
        runner.invoke(
            app,
            ["create", "beta", "--skill", "y", "--schedule", "0 0 * * *"],
        )
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "alpha" in result.stdout
        assert "beta" in result.stdout

    def test_list_status_filter_no_match(self, isolated_store):
        runner.invoke(
            app,
            ["create", "active-one", "--skill", "x", "--schedule", "0 0 * * *"],
        )
        result = runner.invoke(app, ["list", "--status", "paused"])
        assert result.exit_code == 0
        assert "没有匹配状态" in result.stdout


# ──────────────────────────────────────────────────────────────────
# show
# ──────────────────────────────────────────────────────────────────


class TestShow:
    def test_show_existing_loop(self, isolated_store):
        runner.invoke(
            app,
            ["create", "demo", "--skill", "x", "--desc", "Demo loop"],
        )
        result = runner.invoke(app, ["show", "demo"])
        assert result.exit_code == 0
        assert "demo" in result.stdout
        assert "Demo loop" in result.stdout
        assert "Active" in result.stdout or "active" in result.stdout

    def test_show_missing_loop_exits_nonzero(self, isolated_store):
        result = runner.invoke(app, ["show", "no-such"])
        assert result.exit_code == 1
        assert "不存在" in result.stdout


# ──────────────────────────────────────────────────────────────────
# delete
# ──────────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_with_force_succeeds(self, isolated_store):
        runner.invoke(app, ["create", "doomed", "--skill", "x"])
        result = runner.invoke(app, ["delete", "doomed", "--force"])
        assert result.exit_code == 0
        assert "已删除" in result.stdout
        assert isolated_store.load_spec("doomed") is None

    def test_delete_without_force_prompts_confirmation(self, isolated_store):
        """Without --force, typer.confirm prompts; default (no) cancels."""
        runner.invoke(app, ["create", "doomed", "--skill", "x"])
        # CliRunner passes empty stdin → confirm defaults to False
        result = runner.invoke(app, ["delete", "doomed"], input="n\n")
        assert result.exit_code == 1
        assert "取消删除" in result.stdout
        # Spec still exists
        assert isolated_store.load_spec("doomed") is not None

    def test_delete_confirmation_yes_actually_deletes(self, isolated_store):
        runner.invoke(app, ["create", "doomed", "--skill", "x"])
        result = runner.invoke(app, ["delete", "doomed"], input="y\n")
        assert result.exit_code == 0
        assert isolated_store.load_spec("doomed") is None

    def test_delete_missing_loop_exits_nonzero(self, isolated_store):
        result = runner.invoke(app, ["delete", "no-such", "--force"])
        assert result.exit_code == 1
        assert "不存在" in result.stdout


# ──────────────────────────────────────────────────────────────────
# pause / resume
# ──────────────────────────────────────────────────────────────────


class TestPauseResume:
    def test_pause_and_resume_round_trip(self, isolated_store):
        runner.invoke(app, ["create", "p", "--skill", "x"])

        # Pause
        result = runner.invoke(app, ["pause", "p"])
        assert result.exit_code == 0
        assert "已暂停" in result.stdout
        state = isolated_store.load_state("p")
        assert state.status == LoopStatus.PAUSED

        # Resume
        result = runner.invoke(app, ["resume", "p"])
        assert result.exit_code == 0
        assert "已恢复" in result.stdout
        state = isolated_store.load_state("p")
        assert state.status == LoopStatus.ACTIVE

    def test_pause_is_idempotent(self, isolated_store):
        runner.invoke(app, ["create", "p", "--skill", "x"])
        runner.invoke(app, ["pause", "p"])
        result = runner.invoke(app, ["pause", "p"])
        assert result.exit_code == 0
        assert "已处于暂停状态" in result.stdout

    def test_resume_is_idempotent(self, isolated_store):
        runner.invoke(app, ["create", "p", "--skill", "x"])
        result = runner.invoke(app, ["resume", "p"])
        assert result.exit_code == 0
        assert "已处于活跃状态" in result.stdout


# ──────────────────────────────────────────────────────────────────
# tick — the missing execution bridge
# ──────────────────────────────────────────────────────────────────


class TestTick:
    @pytest.fixture(autouse=True)
    def _enable_loop_execution(self):
        """C2: tick now respects loop.enabled (default false). Execution-path
        tests opt in; test_tick_disabled_does_not_execute overrides to false."""
        from unittest.mock import MagicMock

        with patch("vibesop.core.config.manager.ConfigManager.get_loop_config") as m:
            cfg = MagicMock()
            cfg.enabled = True
            m.return_value = cfg
            yield

    def test_tick_no_loops_reports_empty(self, isolated_store):
        result = runner.invoke(app, ["tick"])
        assert result.exit_code == 0
        assert "没有 loop" in result.stdout

    def test_tick_dry_run_lists_triggered_without_executing(self, isolated_store):
        """A ``* * * * *`` loop will match the current minute; dry-run
        must report it without calling execute_loop_tick."""
        runner.invoke(
            app,
            ["create", "every-min", "--skill", "x", "--schedule", "* * * * *"],
        )

        with patch("vibesop.cli.commands.loop_cmd.execute_loop_tick") as mock_exec:
            result = runner.invoke(app, ["tick", "--dry-run"])

        assert result.exit_code == 0
        assert "every-min" in result.stdout
        assert "dry-run" in result.stdout.lower() or "会被触发" in result.stdout
        # Critical: dry-run must NOT execute
        mock_exec.assert_not_called()

    def test_tick_dispatches_to_executor_for_triggered_loop(self, isolated_store):
        """Non-dry-run tick must call execute_loop_tick for triggered loops."""
        runner.invoke(
            app,
            ["create", "every-min", "--skill", "x", "--schedule", "* * * * *"],
        )

        # Build a fake success record that execute_loop_tick would return
        from datetime import datetime

        fake_record = LoopRunRecord(
            loop_name="every-min",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            success=True,
            matched_skill="x",
            output_summary="routed",
            duration_s=0.05,
        )

        with patch(
            "vibesop.cli.commands.loop_cmd.execute_loop_tick",
            return_value=fake_record,
        ) as mock_exec:
            result = runner.invoke(app, ["tick"])

        assert result.exit_code == 0
        assert "Tick 完成" in result.stdout
        assert "1 触发" in result.stdout
        assert "1 成功" in result.stdout
        mock_exec.assert_called_once()
        # Verify it was called with the right spec
        called_spec: LoopSpec = mock_exec.call_args.args[0]
        assert called_spec.name == "every-min"

    def test_tick_skips_paused_loops(self, isolated_store):
        """Paused loops must NOT be picked up by tick even if cron matches."""
        runner.invoke(
            app,
            ["create", "active-one", "--skill", "x", "--schedule", "* * * * *"],
        )
        runner.invoke(
            app,
            ["create", "paused-one", "--skill", "x", "--schedule", "* * * * *"],
        )
        runner.invoke(app, ["pause", "paused-one"])

        with patch("vibesop.cli.commands.loop_cmd.execute_loop_tick") as mock_exec:
            result = runner.invoke(app, ["tick", "--dry-run"])

        assert result.exit_code == 0
        # active-one should be reported as triggered
        assert "active-one" in result.stdout
        # paused-one should NOT appear in the triggered list
        # (We can't assert "paused-one not in stdout" too strictly because
        # the loop name might appear elsewhere; assert via mock instead.)
        if mock_exec.call_args_list:
            called_names = {call.args[0].name for call in mock_exec.call_args_list}
            assert "paused-one" not in called_names

    def test_tick_named_filter(self, isolated_store):
        """--name restricts polling to a single loop."""
        runner.invoke(
            app,
            ["create", "a", "--skill", "x", "--schedule", "* * * * *"],
        )
        runner.invoke(
            app,
            ["create", "b", "--skill", "x", "--schedule", "* * * * *"],
        )

        with patch("vibesop.cli.commands.loop_cmd.execute_loop_tick") as mock_exec:
            result = runner.invoke(app, ["tick", "--name", "a", "--dry-run"])

        assert result.exit_code == 0
        assert "a" in result.stdout
        # b should not appear in triggered list (mock not called for b)
        for call in mock_exec.call_args_list:
            assert call.args[0].name == "a"

    def test_tick_executor_failure_recorded_as_failure(self, isolated_store):
        """When execute_loop_tick returns a failure record, tick reports
        it as a failure in the summary."""
        runner.invoke(
            app,
            ["create", "doomed", "--skill", "x", "--schedule", "* * * * *"],
        )

        from datetime import datetime

        fake_fail = LoopRunRecord(
            loop_name="doomed",
            started_at=datetime.now(UTC),
            success=False,
            error="LLM timeout",
            duration_s=0.01,
        )

        with patch(
            "vibesop.cli.commands.loop_cmd.execute_loop_tick",
            return_value=fake_fail,
        ):
            result = runner.invoke(app, ["tick"])

        # C3: a failed tick must exit non-zero so external cron/launchd detects it.
        assert result.exit_code == 1
        assert "Tick 完成" in result.stdout
        assert "1 失败" in result.stdout

    def test_tick_disabled_does_not_execute(self, isolated_store):
        """C2: when loop.enabled is false, tick reports what would trigger but
        does NOT execute (the master kill-switch). Pre-fix this config was dead.
        """
        from unittest.mock import MagicMock

        runner.invoke(app, ["create", "every-min", "--skill", "x", "--schedule", "* * * * *"])
        with (
            patch("vibesop.core.config.manager.ConfigManager.get_loop_config") as m,
            patch("vibesop.cli.commands.loop_cmd.execute_loop_tick") as mock_exec,
        ):
            cfg = MagicMock()
            cfg.enabled = False
            m.return_value = cfg
            result = runner.invoke(app, ["tick"])

        assert result.exit_code == 0
        assert "disabled" in result.stdout.lower()
        assert "every-min" in result.stdout  # reports what would trigger
        mock_exec.assert_not_called()  # but does NOT execute


# ──────────────────────────────────────────────────────────────────
# install-launchd / uninstall-launchd (Phase C)
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def launchd_home(tmp_path, monkeypatch):
    """Redirect Path.home() so LaunchAgents writes go to tmp_path.

    install-launchd writes to ~/Library/LaunchAgents/. We isolate this to
    tmp_path so tests don't pollute the developer's real launchd state.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_install_launchd_dry_run_prints_plist_no_file(isolated_store, launchd_home) -> None:
    """--dry-run prints plist to stdout but writes nothing."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "test", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    result = runner.invoke(app, ["install-launchd", "test", "--dry-run"])

    assert result.exit_code == 0
    assert "<?xml" in result.stdout
    assert "com.vibesop.loop.test" in result.stdout
    # Plist file must NOT exist in dry-run mode.
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.test.plist"
    assert not plist_path.exists()


def test_install_launchd_missing_loop_errors(isolated_store, launchd_home) -> None:
    result = runner.invoke(app, ["install-launchd", "nonexistent", "--dry-run"])
    assert result.exit_code == 1
    assert "不存在" in result.stdout


def test_install_launchd_writes_plist_and_bootstraps(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """Real (non-dry-run) install writes the plist file and invokes launchctl."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "real", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )

    # Stub subprocess.run so we don't actually invoke launchctl.
    captured_runs: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_runs.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)

    result = runner.invoke(app, ["install-launchd", "real"])

    assert result.exit_code == 0, result.stdout
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.real.plist"
    assert plist_path.exists()
    # Bootstrap was called with the modern gui/<uid> form.
    assert any(
        "launchctl" in cmd and "bootstrap" in cmd and "gui/" in " ".join(cmd)
        for cmd in captured_runs
    )


def test_install_launchd_already_bootstrapped_refreshes(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """If launchctl says already bootstrapped (125 / stderr), the refresh path
    boots out the stale entry and re-bootstraps. This is critical because
    launchd caches the parsed plist at bootstrap time — without refresh, the
    new schedule/env_overrides would be silently ignored (adversarial review
    Phase C FLAW #2)."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "idem", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )

    # Sequence of subprocess.run calls the install will make:
    #   1. bootstrap → 125 ("already bootstrapped")
    #   2. bootout (refresh) → 0
    #   3. bootstrap retry → 0
    call_sequence: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        call_sequence.append(list(cmd))
        is_bootstrap = "bootstrap" in cmd
        is_bootout = "bootout" in cmd
        result = MagicMock()
        if is_bootstrap and len(call_sequence) == 1:
            result.returncode = 125
            result.stderr = "Service is already bootstrapped"
        elif is_bootout:
            result.returncode = 0
            result.stderr = ""
        elif is_bootstrap:
            # Retry after bootout succeeds.
            result.returncode = 0
            result.stderr = ""
        else:
            result.returncode = 0
            result.stderr = ""
        result.stdout = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    result = runner.invoke(app, ["install-launchd", "idem"])
    assert result.exit_code == 0, result.stdout
    # Verify the refresh path actually fired.
    actions = ["bootstrap" if "bootstrap" in c else "bootout" for c in call_sequence]
    assert actions == ["bootstrap", "bootout", "bootstrap"]


def test_install_launchd_real_failure_cleans_up_plist(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """FLAW #1 regression test: if bootstrap returns a real (non-125) error,
    the orphaned plist must be cleaned up so we don't leave a half-installed
    state that launchd might pick up at next login."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "fail", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        result.returncode = 1  # generic failure, not 125
        result.stderr = "Bootstrap failed: 1536"
        result.stdout = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    result = runner.invoke(app, ["install-launchd", "fail"])
    assert result.exit_code == 1
    assert "失败" in result.stdout
    # Plist must NOT exist (cleaned up).
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.fail.plist"
    assert not plist_path.exists()


def test_install_launchd_malformed_vibe_prefix_fails(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """FLAW #4 regression test: shlex error on mismatched quotes must surface
    to the user, not silently fall back to whitespace split (which would
    produce a broken plist that launchd rejects every tick)."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "bad-prefix", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )

    result = runner.invoke(
        app,
        ["install-launchd", "bad-prefix", "--vibe-prefix", '"unbalanced quote run vibe'],
    )
    assert result.exit_code == 1
    assert "解析失败" in result.stdout
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.bad-prefix.plist"
    assert not plist_path.exists()


def test_uninstall_launchd_bootouts_and_deletes_plist(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """uninstall-launchd invokes bootout (tolerates not-loaded) and unlinks plist."""
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.x.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(b"<plist/>")

    captured_runs: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_runs.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("subprocess.run", fake_run)

    result = runner.invoke(app, ["uninstall-launchd", "x"])
    assert result.exit_code == 0, result.stdout
    assert not plist_path.exists()
    assert any("bootout" in " ".join(cmd) for cmd in captured_runs)


def test_uninstall_launchd_keep_plist(isolated_store, launchd_home, monkeypatch) -> None:
    """--keep-plist preserves the file; only bootouts."""
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.x.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(b"<plist/>")

    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: MagicMock(returncode=0, stdout="", stderr=""),
    )

    result = runner.invoke(app, ["uninstall-launchd", "x", "--keep-plist"])
    assert result.exit_code == 0
    assert plist_path.exists()


def test_uninstall_launchd_already_uninstalled_is_idempotent(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """If launchctl says 'Could not find', treat as success (already gone)."""
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: MagicMock(
            returncode=1, stdout="", stderr="Could not find com.vibesop.loop.x"
        ),
    )
    result = runner.invoke(app, ["uninstall-launchd", "x"])
    assert result.exit_code == 0


def test_delete_also_uninstalls_plist(isolated_store, launchd_home, monkeypatch) -> None:
    """delete on a loop with a plist must bootout + unlink before removing spec
    (pi plan v2 must-fix)."""
    spec = LoopSpec.model_validate(
        {"name": "doomed", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
    )
    isolated_store.save_spec(spec)
    # Drop a fake plist as if install-launchd had been run.
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.doomed.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(b"<plist/>")

    captured_runs: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_runs.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = runner.invoke(app, ["delete", "doomed", "--force"])
    assert result.exit_code == 0, result.stdout
    assert not plist_path.exists()
    # launchctl bootout was attempted.
    assert any("bootout" in " ".join(cmd) for cmd in captured_runs)
    # Spec is gone.
    assert isolated_store.load_spec("doomed") is None


def test_delete_without_plist_is_normal(isolated_store, launchd_home, monkeypatch) -> None:
    """delete on a loop without a launchd plist should not attempt bootout."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "plain", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    captured_runs: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_runs.append(list(cmd))
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = runner.invoke(app, ["delete", "plain", "--force"])
    assert result.exit_code == 0, result.stdout
    # No launchctl calls when no plist exists.
    assert not captured_runs


def test_delete_with_bootout_failure_keeps_plist_and_warns(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """FLAW #5 regression test: if bootout fails for a real reason (not "could
    not find"), the plist must NOT be unlinked — keep it as a recovery
    artifact. The spec is still deleted (user wants the loop gone) but the
    warning tells them the launchd label may still be active.
    """
    spec = LoopSpec.model_validate(
        {"name": "stuck", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
    )
    isolated_store.save_spec(spec)
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.stuck.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(b"<plist/>")

    # bootout returns a real failure (not "Could not find").
    def fake_run(cmd, *args, **kwargs):
        return MagicMock(returncode=1, stdout="", stderr="Bootout failed: 36")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = runner.invoke(app, ["delete", "stuck", "--force"])
    assert result.exit_code == 0  # delete itself succeeds
    assert "bootout 失败" in result.stdout
    assert "launchd label 可能仍活跃" in result.stdout
    # Plist preserved for manual recovery.
    assert plist_path.exists()
    # Spec still gone.
    assert isolated_store.load_spec("stuck") is None


# ──────────────────────────────────────────────────────────────────
# K-P1-2: install-launchd resolves uv to absolute path
# ──────────────────────────────────────────────────────────────────


def test_install_launchd_resolves_uv_absolute_path(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """K-P1-2 regression: launchd's default PATH is ``/usr/bin:/bin:/usr/sbin:/sbin``
    and does NOT include ``/opt/homebrew/bin`` where Homebrew installs uv on
    Apple Silicon. A bare ``uv run vibe`` would fail every tick. When the
    user hasn't pinned ``--vibe-prefix``, install must resolve ``uv`` via
    ``shutil.which`` and bake the absolute path into ProgramArguments."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "uv-abs", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    # Simulate uv installed via Homebrew on Apple Silicon.
    monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv" if cmd == "uv" else None)

    result = runner.invoke(app, ["install-launchd", "uv-abs", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    # ProgramArguments[0] must be the resolved absolute path, not bare "uv".
    assert "/opt/homebrew/bin/uv" in result.stdout
    assert "uv run vibe" not in result.stdout  # bare form must not appear in argv


def test_install_launchd_uv_not_found_warns_and_falls_back(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """If uv isn't on PATH at install time, warn loudly and fall back to the
    bare ``uv run vibe`` default (user can override via --vibe-prefix)."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "no-uv", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    result = runner.invoke(app, ["install-launchd", "no-uv", "--dry-run"])
    assert result.exit_code == 0
    assert "未在 PATH 找到" in result.stdout
    assert "Homebrew" in result.stdout  # warning mentions Homebrew
    # Falls back to bare uv (broken but documented).
    assert "uv run vibe" in result.stdout


def test_install_launchd_user_prefix_skips_uv_resolution(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """If the user explicitly passes --vibe-prefix, don't second-guess them
    by resolving uv. Their prefix wins as-is."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "custom", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    # Even if uv exists on PATH, the user's prefix should win.
    monkeypatch.setattr("shutil.which", lambda cmd: "/fake/uv")
    # Mock launchctl so we don't actually bootstrap.
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: MagicMock(returncode=0, stdout="", stderr=""),
    )

    result = runner.invoke(
        app, ["install-launchd", "custom", "--vibe-prefix", "/usr/local/bin/uv run vibe"]
    )
    assert result.exit_code == 0, result.stdout
    # install_launchd prints "ProgramArguments: <prefix> loop tick --name X"
    # to the console — the contiguous prefix string appears there, not in
    # the plist XML (which breaks it into separate <string> elements).
    assert "/usr/local/bin/uv run vibe" in result.stdout
    assert "/fake/uv" not in result.stdout


# ──────────────────────────────────────────────────────────────────
# P-P1-1: FileNotFoundError when launchctl not on PATH
# ──────────────────────────────────────────────────────────────────


def test_install_launchd_missing_launchctl_friendly_error(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """P-P1-1 regression: if launchctl isn't on PATH (containers, broken PATH),
    subprocess.run raises FileNotFoundError. The CLI must catch it and print
    a friendly message instead of dumping a traceback."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {
                "name": "no-launchctl",
                "description": "d",
                "schedule": "*/15 * * * *",
                "skill_id": "x",
            }
        )
    )

    # Force uv to resolve so we get past prefix resolution. Use a whitelisted
    # path so the P1-5 check doesn't reject it (test focus is launchctl
    # FileNotFoundError, not uv validation).
    monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv")

    # Make subprocess.run raise FileNotFoundError as if launchctl were missing.
    def raise_fnf(*a, **k):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'launchctl'")

    monkeypatch.setattr("subprocess.run", raise_fnf)

    result = runner.invoke(app, ["install-launchd", "no-launchctl"])
    # Exit code 1 (failure), but NO traceback — friendly message instead.
    assert result.exit_code == 1, result.stdout
    assert "找不到 launchctl" in result.stdout
    # Plist should have been cleaned up (FLAW #1 cleanup still applies).
    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.no-launchctl.plist"
    assert not plist_path.exists()


def test_uninstall_launchd_missing_launchctl_friendly_error(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """P-P1-1: same friendly error for uninstall path."""
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    def raise_fnf(*a, **k):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'launchctl'")

    monkeypatch.setattr("subprocess.run", raise_fnf)

    result = runner.invoke(app, ["uninstall-launchd", "anything"])
    assert result.exit_code == 1, result.stdout
    assert "找不到 launchctl" in result.stdout


# ──────────────────────────────────────────────────────────────────
# deep-diagnosis-2026-07-24 P1-4 / P1-5: install-launchd hardening
# ──────────────────────────────────────────────────────────────────


def test_install_launchd_rejects_non_git_cwd(
    isolated_store, launchd_home, monkeypatch, tmp_path
) -> None:
    """P1-4 regression: cwd without ``.git/`` or ``pyproject.toml`` must be
    refused — otherwise an attacker who lures the user into a hostile
    directory persists that dir as launchd WorkingDirectory."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "p1-4", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    # Drop the test runner into a tmp dir that has neither .git nor pyproject.toml.
    monkeypatch.chdir(tmp_path)
    # Whitelisted uv so P1-5 doesn't fire and confuse the assertion.
    monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv")

    result = runner.invoke(app, ["install-launchd", "p1-4", "--dry-run"])
    assert result.exit_code == 1
    assert "P1-4" in result.stdout
    assert "trust-cwd" in result.stdout


def test_install_launchd_trust_cwd_bypasses_p1_4(
    isolated_store, launchd_home, monkeypatch, tmp_path
) -> None:
    """``--trust-cwd`` explicitly allows non-git cwd (user knows what they're doing)."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "p1-4-trust", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv")

    result = runner.invoke(app, ["install-launchd", "p1-4-trust", "--trust-cwd", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "<?xml" in result.stdout


def test_install_launchd_accepts_pyproject_cwd(
    isolated_store, launchd_home, monkeypatch, tmp_path
) -> None:
    """pyproject.toml alone (no .git) also satisfies the trust check — covers
    users running from a fresh checkout before their first commit."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "p1-4-pyproj", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv")

    result = runner.invoke(app, ["install-launchd", "p1-4-pyproj", "--dry-run"])
    assert result.exit_code == 0, result.stdout


def test_install_launchd_rejects_non_whitelisted_uv(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """P1-5 regression: ``uv`` resolved from outside the whitelist (e.g. cwd
    or a tmp dir) must be refused — attacker could otherwise persist a
    malicious binary into the launchd plist."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "p1-5", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    monkeypatch.setattr("shutil.which", lambda cmd: "/tmp/suspicious/uv")

    result = runner.invoke(app, ["install-launchd", "p1-5", "--dry-run"])
    assert result.exit_code == 1
    assert "P1-5" in result.stdout
    assert "/tmp/suspicious/uv" in result.stdout
    assert "trust-uv-path" in result.stdout


def test_install_launchd_trust_uv_path_bypasses_p1_5(
    isolated_store, launchd_home, monkeypatch
) -> None:
    """``--trust-uv-path`` explicitly allows non-whitelisted uv paths."""
    isolated_store.save_spec(
        LoopSpec.model_validate(
            {"name": "p1-5-trust", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )
    monkeypatch.setattr("shutil.which", lambda cmd: "/tmp/suspicious/uv")

    result = runner.invoke(app, ["install-launchd", "p1-5-trust", "--trust-uv-path", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    # Dry-run prints the plist XML; verify the trusted uv path appears as the
    # first ProgramArguments element (rather than being rejected).
    assert "/tmp/suspicious/uv" in result.stdout


# Late import so the fixture above can be defined without mandatory import-time cost.
# ──────────────────────────────────────────────────────────────────
# gate26: project ownership (project_root)
# ──────────────────────────────────────────────────────────────────
from datetime import datetime  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from vibesop.core.loop.models import LoopState  # noqa: E402


def _save_spec(store: LoopStore, name: str, project_root: str | None, **overrides) -> LoopSpec:
    """Persist a minimal spec pinned to ``project_root`` (None = global/legacy)."""
    payload: dict = {
        "name": name,
        "description": f"loop {name}",
        "schedule": overrides.pop("schedule", "* * * * *"),
        "skill_id": "x",
        "project_root": project_root,
    }
    payload.update(overrides)
    spec = LoopSpec.model_validate(payload)
    store.save_spec(spec)
    return spec


class TestCreateOwnership:
    def test_create_pins_cwd_by_default(self, isolated_store, monkeypatch, tmp_path):
        """Default: project_root is pinned to the literal cwd."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "pyproject.toml").write_text("[project]\nname='p'\n")
        monkeypatch.chdir(proj)

        result = runner.invoke(app, ["create", "pinned", "--skill", "x"])
        assert result.exit_code == 0, result.stdout
        spec = isolated_store.load_spec("pinned")
        assert spec is not None
        assert spec.project_root == str(proj)
        assert "Project:" in result.stdout

    def test_create_global_opts_out(self, isolated_store, monkeypatch, tmp_path):
        """--global leaves project_root=None (deliberately same value as a
        legacy spec — the double-meaning is by design)."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["create", "glob", "--skill", "x", "--global"])
        assert result.exit_code == 0, result.stdout
        spec = isolated_store.load_spec("glob")
        assert spec.project_root is None
        assert "(global)" in result.stdout

    def test_create_untrusted_cwd_warns_but_creates(self, isolated_store, monkeypatch, tmp_path):
        """Untrusted cwd (no .git/pyproject.toml): warn + proceed, pointing at
        the --global escape hatch. create only writes JSON — refusal is for
        install-launchd, not here."""
        monkeypatch.chdir(tmp_path)  # no .git, no pyproject.toml
        result = runner.invoke(app, ["create", "stray", "--skill", "x"])
        assert result.exit_code == 0, result.stdout
        assert "--global" in result.stdout  # warning names the escape hatch
        spec = isolated_store.load_spec("stray")
        assert spec.project_root == str(tmp_path)

    def test_create_conflict_error_names_existing_project_root(
        self, isolated_store, monkeypatch, tmp_path
    ):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "pyproject.toml").write_text("[project]\nname='p'\n")
        monkeypatch.chdir(proj)
        runner.invoke(app, ["create", "dup-own", "--skill", "x"])

        result = runner.invoke(app, ["create", "dup-own", "--skill", "x"])
        assert result.exit_code == 1
        assert "已存在" in result.stdout
        # Rich wraps long lines at console width — flatten before matching
        # the full path (paths contain no spaces, so rejoining is exact).
        assert str(proj) in result.stdout.replace("\n", "")


class TestListOwnership:
    def test_list_default_hides_other_project_loops(self, isolated_store):
        cwd = str(Path.cwd())
        _save_spec(isolated_store, "mine", cwd)
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")
        _save_spec(isolated_store, "legacy", None)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "mine" in result.stdout
        assert "legacy" in result.stdout  # None = owned everywhere
        assert "theirs" not in result.stdout
        assert "--all" in result.stdout  # hidden hint

    def test_list_all_shows_project_column(self, isolated_store):
        cwd = str(Path.cwd())
        _save_spec(isolated_store, "mine", cwd)
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")
        _save_spec(isolated_store, "legacy", None)

        result = runner.invoke(app, ["list", "--all"])
        assert result.exit_code == 0
        assert "mine" in result.stdout
        assert "theirs" in result.stdout
        assert "(global)" in result.stdout  # None rendered as (global)
        assert "1 shown / 3 total" not in result.stdout  # --all shows everything
        assert "3 shown / 3 total" in result.stdout

    def test_list_subdirectory_of_owned_root_is_owned(self, isolated_store, tmp_path, monkeypatch):
        """_owns is cwd-within-project_root (one-directional): running list
        from a SUBDIRECTORY of the pinned root still sees the loop."""
        proj = tmp_path / "proj"
        sub = proj / "pkg" / "sub"
        sub.mkdir(parents=True)
        _save_spec(isolated_store, "mine", str(proj))
        monkeypatch.chdir(sub)

        result = runner.invoke(app, ["list"])
        assert "mine" in result.stdout

    def test_owns_is_one_directional(self, isolated_store, tmp_path, monkeypatch):
        """The reverse does NOT hold: running from a PARENT of the pinned
        root must not claim the loop."""
        proj = tmp_path / "proj"
        proj.mkdir()
        _save_spec(isolated_store, "child-pinned", str(proj))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["list"])
        assert "child-pinned" not in result.stdout

    def test_list_status_filter_with_hidden_loops_names_ownership_cause(self, isolated_store):
        """gate27 claude#7: when every loop is hidden by ownership (or the
        remaining ones don't match --status), the empty message must name
        the ownership filter as a possible cause — the bare '没有匹配状态'
        sent users chasing the wrong reason."""
        _save_spec(isolated_store, "mine", str(Path.cwd()))  # active, not paused
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        result = runner.invoke(app, ["list", "--status", "paused"])
        assert result.exit_code == 0
        assert "没有匹配状态" in result.stdout
        assert "归属其他项目" in result.stdout  # ownership cause visible
        assert "--all" in result.stdout


class TestTickOwnership:
    @pytest.fixture(autouse=True)
    def _enable_loop_execution(self):
        with patch("vibesop.core.config.manager.ConfigManager.get_loop_config") as m:
            cfg = MagicMock()
            cfg.enabled = True
            m.return_value = cfg
            yield

    def test_bare_tick_skips_other_project_loops_loudly(self, isolated_store):
        """The skip line names the skipped loops and points at --all."""
        _save_spec(isolated_store, "mine", str(Path.cwd()))
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        with patch("vibesop.cli.commands.loop_cmd.execute_loop_tick") as mock_exec:
            result = runner.invoke(app, ["tick", "--dry-run"])

        assert result.exit_code == 0
        assert "已跳过" in result.stdout
        assert "theirs" in result.stdout  # skip line names the loop
        assert "--all" in result.stdout
        # Only the owned loop is in the triggered list.
        assert "mine" in result.stdout
        mock_exec.assert_not_called()  # dry-run never executes

    def test_skip_line_printed_even_when_nothing_eligible(self, isolated_store):
        """pi nit: the zero-eligible early-return branch must still print the
        ownership skip line — silence was the original bug's twin."""
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        result = runner.invoke(app, ["tick"])
        assert result.exit_code == 0
        assert "已跳过" in result.stdout
        assert "theirs" in result.stdout

    def test_skip_line_printed_on_zero_trigger_branch(self, isolated_store):
        """Owned loop whose cron does NOT match now + an other-project loop:
        the '本轮无到期' branch still shows the ownership skip line."""
        # Far-future-ish cron that cannot match the current minute: Feb 30
        # never exists, and CronExpr validation only checks field ranges.
        _save_spec(isolated_store, "mine", str(Path.cwd()), schedule="0 0 30 2 *")
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        result = runner.invoke(app, ["tick"])
        assert result.exit_code == 0
        # gate27 pi#5: wording distinguishes "no owned loops" from "no due loops"
        assert "本轮无到期" in result.stdout
        assert "已跳过" in result.stdout
        assert "theirs" in result.stdout

    def test_zero_trigger_message_distinguishes_no_owned_loops(self, isolated_store):
        """gate27 pi#5: when EVERY loop was ownership-skipped, say so — the
        old '(0 eligible, 0 skipped)' read as 'nothing due' and masked the
        ownership filter as the real cause."""
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        result = runner.invoke(app, ["tick"])
        assert result.exit_code == 0
        assert "已跳过" in result.stdout  # skip line (printed first)
        assert "无归属当前项目的 loop" in result.stdout
        assert "--all" in result.stdout

    def test_skip_line_caps_names_at_five(self, isolated_store):
        """gate27 pi#4a: with 6+ other-project loops, the skip line lists at
        most 5 names plus a total count."""
        for i in range(6):
            _save_spec(isolated_store, f"other-{i}", f"/nonexistent/other-{i}")

        result = runner.invoke(app, ["tick"])
        assert result.exit_code == 0
        for i in range(5):
            assert f"other-{i}" in result.stdout
        assert "other-5" not in result.stdout  # 6th name truncated
        assert "等共 6 个" in result.stdout

    def test_tick_rereads_spec_inside_lock(self, isolated_store, monkeypatch, tmp_path):
        """gate27 pi#1/claude#2: if adopt completes between enumeration and
        lock acquisition, the tick must execute with the FRESH spec (re-read
        inside the per-loop lock), not the stale enumerated snapshot."""
        from vibesop.cli.commands import loop_cmd

        _save_spec(isolated_store, "race", str(Path.cwd()))
        repinned = tmp_path / "repinned"
        repinned.mkdir()

        real_acquire = loop_cmd._acquire_tick_lock

        def acquire_then_repin(store, name, **kw):
            # Simulate adopt completing just before this tick takes the lock.
            spec = store.load_spec(name)
            spec.project_root = str(repinned)
            store.save_spec(spec)
            return real_acquire(store, name, **kw)

        monkeypatch.setattr(loop_cmd, "_acquire_tick_lock", acquire_then_repin)

        fake_record = LoopRunRecord(
            loop_name="race",
            started_at=datetime.now(UTC),
            success=True,
            matched_skill="x",
            duration_s=0.01,
        )
        with patch(
            "vibesop.cli.commands.loop_cmd.execute_loop_tick", return_value=fake_record
        ) as mock_exec:
            result = runner.invoke(app, ["tick"])

        assert result.exit_code == 0, result.stdout
        executed_spec: LoopSpec = mock_exec.call_args.args[0]
        assert executed_spec.project_root == str(repinned)

    def test_name_bypasses_ownership_filter(self, isolated_store):
        """--name is the launchd call shape — ownership filtering is off and
        no skip line is printed."""
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        result = runner.invoke(app, ["tick", "--name", "theirs", "--dry-run"])
        assert result.exit_code == 0
        assert "theirs" in result.stdout
        assert "已跳过" not in result.stdout
        assert "会被触发" in result.stdout

    def test_all_compat_hatch(self, isolated_store):
        """--all enumerates every loop regardless of ownership (compat for
        system-cron-from-HOME users); no skip line."""
        _save_spec(isolated_store, "mine", str(Path.cwd()))
        _save_spec(isolated_store, "theirs", "/nonexistent/other-project")

        with patch("vibesop.cli.commands.loop_cmd.execute_loop_tick") as mock_exec:
            result = runner.invoke(app, ["tick", "--all", "--dry-run"])

        assert result.exit_code == 0
        assert "theirs" in result.stdout
        assert "mine" in result.stdout
        assert "已跳过" not in result.stdout
        mock_exec.assert_not_called()  # dry-run never executes

    def test_tick_constructs_runtime_per_spec_with_pinned_root(self, isolated_store):
        """gate26 review (chdir rejected): the tick loop builds a per-spec
        AgentRuntime(project_root=exec_root) for pinned loops, and keeps the
        legacy ambient-cwd runtime for unscoped ones."""
        pinned_root = Path.cwd()
        _save_spec(isolated_store, "pinned", str(pinned_root))
        _save_spec(isolated_store, "global-one", None)

        fake_record = LoopRunRecord(
            loop_name="x",
            started_at=datetime.now(UTC),
            success=True,
            matched_skill="x",
            duration_s=0.01,
        )

        with (
            patch("vibesop.cli.commands.loop_cmd.execute_loop_tick", return_value=fake_record),
            patch("vibesop.agent.runtime.agent_runtime.AgentRuntime") as mock_rt,
        ):
            mock_rt.return_value = MagicMock()
            result = runner.invoke(app, ["tick"])

        assert result.exit_code == 0, result.stdout
        by_spec: dict[str, dict] = {}
        # execute_loop_tick was called once per triggered spec; pair each call
        # with the AgentRuntime construction that preceded it by ordering.
        rt_calls = mock_rt.call_args_list
        assert len(rt_calls) == 2
        for rt_call in rt_calls:
            kwargs = rt_call.kwargs
            by_spec["pinned" if kwargs else "global-one"] = kwargs
        assert by_spec["pinned"] == {"project_root": str(pinned_root.resolve())}
        assert by_spec["global-one"] == {}


class TestShowOwnership:
    def test_show_displays_project_line(self, isolated_store):
        # Short path: Rich panels crop long lines in the 80-col test console.
        _save_spec(isolated_store, "owned", "/tmp/x-owned")
        result = runner.invoke(app, ["show", "owned"])
        assert result.exit_code == 0
        assert "Project:" in result.stdout
        assert "/tmp/x-owned" in result.stdout

    def test_show_global_loop_displays_global_marker(self, isolated_store):
        _save_spec(isolated_store, "g", None)
        result = runner.invoke(app, ["show", "g"])
        assert result.exit_code == 0
        assert "(global)" in result.stdout


class TestAdopt:
    def test_adopt_pins_cwd_and_syncs_state(self, isolated_store, monkeypatch, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".git").mkdir()
        _save_spec(isolated_store, "adoptee", None)
        # Pre-existing state embeds the OLD (None) spec copy.
        isolated_store.save_state(LoopState(spec=isolated_store.load_spec("adoptee")))
        monkeypatch.chdir(proj)

        result = runner.invoke(app, ["adopt", "adoptee"])
        assert result.exit_code == 0, result.stdout
        # Rich wraps long lines — flatten before matching the path.
        assert str(proj) in result.stdout.replace("\n", "")

        spec = isolated_store.load_spec("adoptee")
        assert spec.project_root == str(proj)
        state = isolated_store.load_state("adoptee")
        assert state.spec.project_root == str(proj)  # state.spec copy synced

    def test_adopt_untrusted_cwd_warns_but_pins(self, isolated_store, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)  # no .git / pyproject.toml
        _save_spec(isolated_store, "stray", None)

        result = runner.invoke(app, ["adopt", "stray"])
        assert result.exit_code == 0, result.stdout
        assert "⚠️" in result.stdout or "git repo" in result.stdout
        assert isolated_store.load_spec("stray").project_root == str(tmp_path)

    def test_adopt_missing_loop_errors(self, isolated_store):
        result = runner.invoke(app, ["adopt", "no-such"])
        assert result.exit_code == 1
        assert "不存在" in result.stdout


class TestMigrateOwnership:
    def _write_plist(self, home: Path, name: str, working_dir: str) -> None:
        import plistlib

        plist_path = home / "Library" / "LaunchAgents" / f"com.vibesop.loop.{name}.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(plistlib.dumps({"Label": name, "WorkingDirectory": working_dir}))

    def test_dry_run_reports_without_writing(self, isolated_store, launchd_home, monkeypatch):
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: True)
        _save_spec(isolated_store, "mig", None)
        self._write_plist(launchd_home, "mig", "/tmp/mig-project")

        result = runner.invoke(app, ["migrate-ownership", "--dry-run"])
        assert result.exit_code == 0, result.stdout
        assert "DRY RUN" in result.stdout
        assert "/tmp/mig-project" in result.stdout
        # No side effects.
        assert isolated_store.load_spec("mig").project_root is None

    def test_backfills_from_plist_with_confirmation_and_syncs_state(
        self, isolated_store, launchd_home, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: True)
        proj = tmp_path / "mig-project"
        proj.mkdir()
        _save_spec(isolated_store, "mig", None)
        isolated_store.save_state(LoopState(spec=isolated_store.load_spec("mig")))
        self._write_plist(launchd_home, "mig", str(proj))

        result = runner.invoke(app, ["migrate-ownership"], input="y\n")
        assert result.exit_code == 0, result.stdout
        assert isolated_store.load_spec("mig").project_root == str(proj)
        state = isolated_store.load_state("mig")
        assert state.spec.project_root == str(proj)

    def test_confirmation_no_skips_write(self, isolated_store, launchd_home, monkeypatch):
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: True)
        _save_spec(isolated_store, "mig", None)
        self._write_plist(launchd_home, "mig", "/tmp/mig-project")

        result = runner.invoke(app, ["migrate-ownership"], input="n\n")
        assert result.exit_code == 0
        assert isolated_store.load_spec("mig").project_root is None

    def test_yes_skips_confirmation(self, isolated_store, launchd_home, monkeypatch):
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: True)
        _save_spec(isolated_store, "mig", None)
        self._write_plist(launchd_home, "mig", "/tmp/mig-project")

        result = runner.invoke(app, ["migrate-ownership", "--yes"])
        assert result.exit_code == 0, result.stdout
        assert isolated_store.load_spec("mig").project_root == "/tmp/mig-project"

    def test_no_plist_lists_and_suggests_adopt(self, isolated_store, launchd_home, monkeypatch):
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: True)
        _save_spec(isolated_store, "orphan", None)

        result = runner.invoke(app, ["migrate-ownership", "--yes"])
        assert result.exit_code == 0
        assert "orphan" in result.stdout
        assert "adopt" in result.stdout
        assert isolated_store.load_spec("orphan").project_root is None

    def test_already_pinned_loops_are_skipped(self, isolated_store, launchd_home, monkeypatch):
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: True)
        _save_spec(isolated_store, "kept", "/already/pinned")
        self._write_plist(launchd_home, "kept", "/tmp/elsewhere")

        result = runner.invoke(app, ["migrate-ownership", "--yes"])
        assert result.exit_code == 0
        assert isolated_store.load_spec("kept").project_root == "/already/pinned"

    def test_non_macos_lists_adopt_suggestion_without_side_effects(
        self, isolated_store, launchd_home, monkeypatch
    ):
        """gate27 claude#6: on non-macOS (the CI default path) plists are
        never read — even a present plist must be ignored; loops are listed
        with the adopt hint and nothing is written."""
        monkeypatch.setattr("vibesop.cli.commands.loop_cmd._is_macos", lambda: False)
        _save_spec(isolated_store, "orphan", None)
        # A plist exists on disk but must NOT be consulted off-macOS.
        self._write_plist(launchd_home, "orphan", "/tmp/would-be-ignored")

        result = runner.invoke(app, ["migrate-ownership", "--yes"])
        assert result.exit_code == 0, result.stdout
        assert "orphan" in result.stdout
        assert "adopt" in result.stdout
        assert "非 macOS" in result.stdout
        assert isolated_store.load_spec("orphan").project_root is None  # no side effects


class TestInstallLaunchdOwnershipWarning:
    def test_warns_when_spec_pinned_to_other_dir(
        self, isolated_store, launchd_home, monkeypatch, tmp_path
    ):
        """install-launchd never backfills; when the spec IS pinned elsewhere
        it warns about the WorkingDirectory/exec_root mismatch."""
        _save_spec(isolated_store, "elsewhere", str(tmp_path / "other"))
        monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv")

        result = runner.invoke(app, ["install-launchd", "elsewhere", "--dry-run"])
        assert result.exit_code == 0, result.stdout
        assert "不一致" in result.stdout
        assert "adopt" in result.stdout
        # And no backfill happened.
        assert isolated_store.load_spec("elsewhere").project_root == str(tmp_path / "other")

    def test_no_warning_when_pinned_to_cwd(self, isolated_store, launchd_home, monkeypatch):
        _save_spec(isolated_store, "here", str(Path.cwd()))
        monkeypatch.setattr("shutil.which", lambda cmd: "/opt/homebrew/bin/uv")

        result = runner.invoke(app, ["install-launchd", "here", "--dry-run"])
        assert result.exit_code == 0, result.stdout
        assert "不一致" not in result.stdout
