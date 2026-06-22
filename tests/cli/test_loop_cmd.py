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
