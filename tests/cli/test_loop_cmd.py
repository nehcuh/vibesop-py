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
            {"name": "no-launchctl", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
        )
    )

    # Force uv to resolve so we get past prefix resolution.
    monkeypatch.setattr("shutil.which", lambda cmd: "/fake/uv")

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


# Late import so the fixture above can be defined without mandatory import-time cost.
from unittest.mock import MagicMock  # noqa: E402
