• Let me read the files. I'll read the brief, launchd.py, loop_cmd.py diff, and tests. The brief might be long; let me read in parallel.

• 我先读取 brief、新代码和测试文件。

• Now read the loop_cmd.py diff and tests. Let me run git diff for loop_cmd.py and read test files.

• 再看 CLI 改动 diff 和测试。diff --git a/src/vibesop/cli/commands/loop_cmd.py b/src/vibesop/cli/commands/loop_cmd.py
index 55ee30e..150eab4 100644
--- a/src/vibesop/cli/commands/loop_cmd.py
+++ b/src/vibesop/cli/commands/loop_cmd.py
@@ -29,7 +29,9 @@ from __future__ import annotations
 
 import logging
 import os
+import sys
 from datetime import UTC, datetime
+from pathlib import Path
 from typing import Any
 
 import typer
@@ -350,8 +352,42 @@ def delete(
             console.print("[yellow]取消删除[/yellow]")
             raise typer.Exit(1)
 
+    # Phase C (pi plan v2 新增 + 对抗 review FLAW #5): if a launchd plist
+    # exists, best-effort bootout and delete it too — otherwise the orphaned
+    # plist keeps firing tick on a spec that no longer exists, producing noise
+    # in the log every minute. If bootout fails for a real reason (not "could
+    # not find"), do NOT unlink the plist — keep it as a recovery artifact so
+    # the user can re-run uninstall-launchd. Warn loudly that the launchd
+    # label may still be active even though the spec is gone.
+    plist_cleanup_failed = False
+    if _is_macos():
+        from vibesop.core.loop.launchd import default_plist_path
+
+        plist_path = default_plist_path(name)
+        if plist_path.exists():
+            console.print("[dim]检测到 launchd plist，先注销…[/dim]")
+            bootout_ok = _bootout_launchd(name, console=console, missing_ok=True)
+            if bootout_ok:
+                try:
+                    plist_path.unlink()
+                except OSError as e:
+                    logger.warning("Failed to remove plist %s: %s", plist_path, e)
+            else:
+                plist_cleanup_failed = True
+                console.print(
+                    f"[yellow]⚠️  bootout 失败 — 保留 plist {plist_path}[/yellow]\n"
+                    f"[yellow]   launchd label 可能仍活跃，请手工运行 "
+                    f"'vibe loop uninstall-launchd {name}'[/yellow]"
+                )
+
     store.delete_spec(name)
-    console.print(f"[green]✅ Loop '{name}' 已删除[/green]")
+    if plist_cleanup_failed:
+        console.print(
+            f"[green]✅ Loop '{name}' 已删除[/green] "
+            f"[yellow](但 launchd 清理未完成，见上)[/yellow]"
+        )
+    else:
+        console.print(f"[green]✅ Loop '{name}' 已删除[/green]")
 
 
 # ──────────────────────────────────────────────────────────────────
@@ -584,4 +620,200 @@ def tick(
         raise typer.Exit(code=1)
 
 
+# ──────────────────────────────────────────────────────────────────
+# install-launchd / uninstall-launchd (Phase C)
+# ──────────────────────────────────────────────────────────────────
+
+
+def _bootstrap_launchd(plist_path: Path, *, console: Console, loop_name: str) -> bool:
+    """Run ``launchctl bootstrap`` and report. Returns True on success.
+
+    Refresh handling: if the label is already bootstrapped (returncode 125 or
+    stderr contains "already bootstrapped"), launchd has cached the OLD plist
+    and will NOT re-read the file. We detect this and do an automatic
+    bootout-then-bootstrap so the new schedule/env_overrides actually take
+    effect (adversarial review Phase C FLAW #2).
+
+    Args:
+        plist_path: Path to the plist file to bootstrap.
+        console: Rich console for status output.
+        loop_name: Bare loop name (without label prefix) — used to construct
+            the bootout command on the refresh path, and to print accurate
+            recovery hints (FLAW #3: don't print the prefixed stem).
+    """
+    import subprocess
+
+    from vibesop.core.loop.launchd import bootstrap_command
+
+    cmd = bootstrap_command(plist_path)
+    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
+    if result.returncode == 0:
+        return True
+
+    already = result.returncode == 125 or "already bootstrapped" in (result.stderr or "").lower()
+    if already:
+        # Refresh path: bootout the stale entry, then re-bootstrap. The plist
+        # on disk is already the new one (caller wrote it before invoking us).
+        console.print("[dim]已注册，重新加载（bootout → bootstrap）…[/dim]")
+        if not _bootout_launchd(loop_name, console=console, missing_ok=True):
+            return False
+        result2 = subprocess.run(cmd, capture_output=True, text=True, check=False)
+        if result2.returncode == 0:
+            return True
+        console.print(f"[red]❌ refresh 后 bootstrap 仍失败 (exit {result2.returncode})[/red]")
+        if result2.stderr:
+            console.print(f"[dim]{result2.stderr.strip()}[/dim]")
+        return False
+
+    console.print(f"[red]❌ launchctl bootstrap 失败 (exit {result.returncode})[/red]")
+    if result.stderr:
+        console.print(f"[dim]{result.stderr.strip()}[/dim]")
+    return False
+
+
+def _bootout_launchd(loop_name: str, *, console: Console, missing_ok: bool = False) -> bool:
+    """Run ``launchctl bootout`` for ``loop_name``. Returns True on success.
+
+    ``missing_ok=True`` treats "not bootstrapped" as success (used by ``delete``
+    so a loop whose plist was already removed doesn't fail teardown).
+    """
+    import subprocess
+
+    from vibesop.core.loop.launchd import bootout_command, plist_label
+
+    cmd = bootout_command(loop_name)
+    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
+    if result.returncode == 0:
+        return True
+    stderr_lower = (result.stderr or "").lower()
+    # launchctl prints "Could not find ..." when the label was never bootstrapped
+    # (or was already booted out). Non-fatal for delete / uninstall idempotency.
+    if missing_ok and ("could not find" in stderr_lower or "no such" in stderr_lower):
+        return True
+    console.print(f"[red]❌ launchctl bootout 失败 (exit {result.returncode})[/red]")
+    if result.stderr:
+        console.print(f"[dim]{result.stderr.strip()}[/dim]")
+    console.print(f"[dim]label: {plist_label(loop_name)}[/dim]")
+    return False
+
+
+def _is_macos() -> bool:
+    return sys.platform == "darwin"
+
+
+@app.command("install-launchd")
+def install_launchd(
+    name: str = typer.Argument(..., help="loop 名称"),
+    vibe_prefix: str = typer.Option(
+        None,
+        "--vibe-prefix",
+        envvar="VIBESOP_RUN_PREFIX",
+        help="vibe CLI 调用前缀（默认 'uv run vibe'）。带空格的路径需加引号。",
+    ),
+    dry_run: bool = typer.Option(False, "--dry-run", help="只打印 plist，不写盘、不 bootstrap"),
+) -> None:
+    """生成 launchd plist 并注册到 ~/Library/LaunchAgents/（仅 macOS）。
+
+    流程：
+        1. 加载 LoopSpec
+        2. 渲染 plist XML（ProgramArguments = prefix + ['loop','tick','--name',NAME]）
+        3. 写到 ~/Library/LaunchAgents/com.vibesop.loop.<name>.plist
+        4. 调 ``launchctl bootstrap gui/$(id -u) <plist>`` 注册
+
+    ProgramArguments 调用通用的 ``vibe loop tick``，所以同一 plist 模板适用
+    于 skill / query / workflow / command_args 四种 target。Target dispatch
+    和 PAUSED/DEAD/RETIRED 过滤由 tick 内部处理。
+
+    注：``vibe loop create`` 暂未暴露 ``--command`` flag（Phase D 补），所以
+    command_args loop 需手工编辑 spec.json 或通过 ``--dry-run`` 检查后再用。
+    """
+    if not _is_macos():
+        console.print("[red]❌ install-launchd 仅支持 macOS（其他平台请用 cron 或 systemd）[/red]")
+        raise typer.Exit(1)
+
+    from vibesop.core.loop.launchd import (
+        DEFAULT_VIBE_PREFIX,
+        default_plist_path,
+        render_plist,
+    )
+
+    store = LoopStore()
+    spec = store.load_spec(name)
+    if spec is None:
+        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
+        raise typer.Exit(1)
+
+    prefix = vibe_prefix or DEFAULT_VIBE_PREFIX
+    project_root = Path.cwd()
+    try:
+        plist_bytes = render_plist(spec, project_root=project_root, vibe_prefix=prefix)
+    except ValueError as e:
+        # shlex.split raises ValueError on mismatched quotes — fail loud at
+        # install time rather than silently producing a broken plist that
+        # launchd would reject every tick (adversarial review Phase C FLAW #4).
+        console.print(f"[red]❌ VIBESOP_RUN_PREFIX / --vibe-prefix 解析失败: {e}[/red]")
+        raise typer.Exit(1) from e
+
+    if dry_run:
+        console.print(Panel(plist_bytes.decode(), title=f"[bold]DRY RUN: {name}[/bold]"))
+        return
+
+    plist_path = default_plist_path(spec.name)
+    plist_path.parent.mkdir(parents=True, exist_ok=True)
+    plist_path.write_bytes(plist_bytes)
+
+    console.print(f"[green]✅ plist 已写入: {plist_path}[/green]")
+    console.print(f"[dim]ProgramArguments: {prefix} loop tick --name {name}[/dim]")
+    console.print(f"[dim]WorkingDirectory: {project_root}[/dim]")
+
+    if not _bootstrap_launchd(plist_path, console=console, loop_name=spec.name):
+        # Clean up the orphaned plist so we don't leave a half-installed state
+        # (adversarial review Phase C FLAW #1). The user can re-run after fixing
+        # whatever blocked bootstrap.
+        try:
+            plist_path.unlink()
+        except OSError as e2:
+            logger.warning("Failed to clean up plist after bootstrap failure: %s", e2)
+        raise typer.Exit(1)
+
+    console.print(
+        f"\n[bold]下一步[/bold]: launchd 已注册。查看状态:\n"
+        f"  [dim]launchctl print gui/$(id -u)/com.vibesop.loop.{name}[/dim]\n"
+        f"  [dim]tail -f {project_root}/.vibe/loops/{name}/out.log[/dim]"
+    )
+
+
+@app.command("uninstall-launchd")
+def uninstall_launchd(
+    name: str = typer.Argument(..., help="loop 名称"),
+    keep_plist: bool = typer.Option(
+        False, "--keep-plist", help="保留 plist 文件（仅 bootout）"
+    ),
+) -> None:
+    """从 launchd 注销 loop（``launchctl bootout``）并删除 plist。
+
+    幂等：loop 未注册时也返回成功。
+    """
+    if not _is_macos():
+        console.print("[red]❌ uninstall-launchd 仅支持 macOS[/red]")
+        raise typer.Exit(1)
+
+    from vibesop.core.loop.launchd import default_plist_path
+
+    plist_path = default_plist_path(name)
+    bootout_ok = _bootout_launchd(name, console=console, missing_ok=True)
+    if not bootout_ok:
+        raise typer.Exit(1)
+
+    if keep_plist:
+        console.print(f"[green]✅ 已 bootout（保留 plist: {plist_path}）[/green]")
+        return
+
+    if plist_path.exists():
+        plist_path.unlink()
+        console.print(f"[green]✅ 已删除 plist: {plist_path}[/green]")
+    else:
+        console.print("[green]✅ 已 bootout（plist 本来就不存在）[/green]")
+
+
 __all__ = ["app"]
diff --git a/tests/cli/test_loop_cmd.py b/tests/cli/test_loop_cmd.py
index 7766af1..9415248 100644
--- a/tests/cli/test_loop_cmd.py
+++ b/tests/cli/test_loop_cmd.py
@@ -440,3 +440,318 @@ class TestTick:
         assert "disabled" in result.stdout.lower()
         assert "every-min" in result.stdout  # reports what would trigger
         mock_exec.assert_not_called()  # but does NOT execute
+
+
+# ──────────────────────────────────────────────────────────────────
+# install-launchd / uninstall-launchd (Phase C)
+# ──────────────────────────────────────────────────────────────────
+
+
+@pytest.fixture
+def launchd_home(tmp_path, monkeypatch):
+    """Redirect Path.home() so LaunchAgents writes go to tmp_path.
+
+    install-launchd writes to ~/Library/LaunchAgents/. We isolate this to
+    tmp_path so tests don't pollute the developer's real launchd state.
+    """
+    monkeypatch.setattr(Path, "home", lambda: tmp_path)
+    return tmp_path
+
+
+def test_install_launchd_dry_run_prints_plist_no_file(isolated_store, launchd_home) -> None:
+    """--dry-run prints plist to stdout but writes nothing."""
+    isolated_store.save_spec(
+        LoopSpec.model_validate(
+            {"name": "test", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+        )
+    )
+    result = runner.invoke(app, ["install-launchd", "test", "--dry-run"])
+
+    assert result.exit_code == 0
+    assert "<?xml" in result.stdout
+    assert "com.vibesop.loop.test" in result.stdout
+    # Plist file must NOT exist in dry-run mode.
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.test.plist"
+    assert not plist_path.exists()
+
+
+def test_install_launchd_missing_loop_errors(isolated_store, launchd_home) -> None:
+    result = runner.invoke(app, ["install-launchd", "nonexistent", "--dry-run"])
+    assert result.exit_code == 1
+    assert "不存在" in result.stdout
+
+
+def test_install_launchd_writes_plist_and_bootstraps(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """Real (non-dry-run) install writes the plist file and invokes launchctl."""
+    isolated_store.save_spec(
+        LoopSpec.model_validate(
+            {"name": "real", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+        )
+    )
+
+    # Stub subprocess.run so we don't actually invoke launchctl.
+    captured_runs: list[list[str]] = []
+
+    def fake_run(cmd, *args, **kwargs):
+        captured_runs.append(list(cmd))
+        result = MagicMock()
+        result.returncode = 0
+        result.stdout = ""
+        result.stderr = ""
+        return result
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+
+    result = runner.invoke(app, ["install-launchd", "real"])
+
+    assert result.exit_code == 0, result.stdout
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.real.plist"
+    assert plist_path.exists()
+    # Bootstrap was called with the modern gui/<uid> form.
+    assert any(
+        "launchctl" in cmd and "bootstrap" in cmd and "gui/" in " ".join(cmd)
+        for cmd in captured_runs
+    )
+
+
+def test_install_launchd_already_bootstrapped_refreshes(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """If launchctl says already bootstrapped (125 / stderr), the refresh path
+    boots out the stale entry and re-bootstraps. This is critical because
+    launchd caches the parsed plist at bootstrap time — without refresh, the
+    new schedule/env_overrides would be silently ignored (adversarial review
+    Phase C FLAW #2)."""
+    isolated_store.save_spec(
+        LoopSpec.model_validate(
+            {"name": "idem", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+        )
+    )
+
+    # Sequence of subprocess.run calls the install will make:
+    #   1. bootstrap → 125 ("already bootstrapped")
+    #   2. bootout (refresh) → 0
+    #   3. bootstrap retry → 0
+    call_sequence: list[list[str]] = []
+
+    def fake_run(cmd, *args, **kwargs):
+        call_sequence.append(list(cmd))
+        is_bootstrap = "bootstrap" in cmd
+        is_bootout = "bootout" in cmd
+        result = MagicMock()
+        if is_bootstrap and len(call_sequence) == 1:
+            result.returncode = 125
+            result.stderr = "Service is already bootstrapped"
+        elif is_bootout:
+            result.returncode = 0
+            result.stderr = ""
+        elif is_bootstrap:
+            # Retry after bootout succeeds.
+            result.returncode = 0
+            result.stderr = ""
+        else:
+            result.returncode = 0
+            result.stderr = ""
+        result.stdout = ""
+        return result
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+    result = runner.invoke(app, ["install-launchd", "idem"])
+    assert result.exit_code == 0, result.stdout
+    # Verify the refresh path actually fired.
+    actions = ["bootstrap" if "bootstrap" in c else "bootout" for c in call_sequence]
+    assert actions == ["bootstrap", "bootout", "bootstrap"]
+
+
+def test_install_launchd_real_failure_cleans_up_plist(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """FLAW #1 regression test: if bootstrap returns a real (non-125) error,
+    the orphaned plist must be cleaned up so we don't leave a half-installed
+    state that launchd might pick up at next login."""
+    isolated_store.save_spec(
+        LoopSpec.model_validate(
+            {"name": "fail", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+        )
+    )
+
+    def fake_run(cmd, *args, **kwargs):
+        result = MagicMock()
+        result.returncode = 1  # generic failure, not 125
+        result.stderr = "Bootstrap failed: 1536"
+        result.stdout = ""
+        return result
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+    result = runner.invoke(app, ["install-launchd", "fail"])
+    assert result.exit_code == 1
+    assert "失败" in result.stdout
+    # Plist must NOT exist (cleaned up).
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.fail.plist"
+    assert not plist_path.exists()
+
+
+def test_install_launchd_malformed_vibe_prefix_fails(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """FLAW #4 regression test: shlex error on mismatched quotes must surface
+    to the user, not silently fall back to whitespace split (which would
+    produce a broken plist that launchd rejects every tick)."""
+    isolated_store.save_spec(
+        LoopSpec.model_validate(
+            {"name": "bad-prefix", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+        )
+    )
+
+    result = runner.invoke(
+        app,
+        ["install-launchd", "bad-prefix", "--vibe-prefix", '"unbalanced quote run vibe'],
+    )
+    assert result.exit_code == 1
+    assert "解析失败" in result.stdout
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.bad-prefix.plist"
+    assert not plist_path.exists()
+
+
+def test_uninstall_launchd_bootouts_and_deletes_plist(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """uninstall-launchd invokes bootout (tolerates not-loaded) and unlinks plist."""
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.x.plist"
+    plist_path.parent.mkdir(parents=True, exist_ok=True)
+    plist_path.write_bytes(b"<plist/>")
+
+    captured_runs: list[list[str]] = []
+
+    def fake_run(cmd, *args, **kwargs):
+        captured_runs.append(list(cmd))
+        result = MagicMock()
+        result.returncode = 0
+        result.stdout = ""
+        result.stderr = ""
+        return result
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+
+    result = runner.invoke(app, ["uninstall-launchd", "x"])
+    assert result.exit_code == 0, result.stdout
+    assert not plist_path.exists()
+    assert any("bootout" in " ".join(cmd) for cmd in captured_runs)
+
+
+def test_uninstall_launchd_keep_plist(isolated_store, launchd_home, monkeypatch) -> None:
+    """--keep-plist preserves the file; only bootouts."""
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.x.plist"
+    plist_path.parent.mkdir(parents=True, exist_ok=True)
+    plist_path.write_bytes(b"<plist/>")
+
+    monkeypatch.setattr(
+        "subprocess.run",
+        lambda *a, **k: MagicMock(returncode=0, stdout="", stderr=""),
+    )
+
+    result = runner.invoke(app, ["uninstall-launchd", "x", "--keep-plist"])
+    assert result.exit_code == 0
+    assert plist_path.exists()
+
+
+def test_uninstall_launchd_already_uninstalled_is_idempotent(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """If launchctl says 'Could not find', treat as success (already gone)."""
+    monkeypatch.setattr(
+        "subprocess.run",
+        lambda *a, **k: MagicMock(
+            returncode=1, stdout="", stderr="Could not find com.vibesop.loop.x"
+        ),
+    )
+    result = runner.invoke(app, ["uninstall-launchd", "x"])
+    assert result.exit_code == 0
+
+
+def test_delete_also_uninstalls_plist(isolated_store, launchd_home, monkeypatch) -> None:
+    """delete on a loop with a plist must bootout + unlink before removing spec
+    (pi plan v2 must-fix)."""
+    spec = LoopSpec.model_validate(
+        {"name": "doomed", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+    )
+    isolated_store.save_spec(spec)
+    # Drop a fake plist as if install-launchd had been run.
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.doomed.plist"
+    plist_path.parent.mkdir(parents=True, exist_ok=True)
+    plist_path.write_bytes(b"<plist/>")
+
+    captured_runs: list[list[str]] = []
+
+    def fake_run(cmd, *args, **kwargs):
+        captured_runs.append(list(cmd))
+        return MagicMock(returncode=0, stdout="", stderr="")
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+
+    result = runner.invoke(app, ["delete", "doomed", "--force"])
+    assert result.exit_code == 0, result.stdout
+    assert not plist_path.exists()
+    # launchctl bootout was attempted.
+    assert any("bootout" in " ".join(cmd) for cmd in captured_runs)
+    # Spec is gone.
+    assert isolated_store.load_spec("doomed") is None
+
+
+def test_delete_without_plist_is_normal(isolated_store, launchd_home, monkeypatch) -> None:
+    """delete on a loop without a launchd plist should not attempt bootout."""
+    isolated_store.save_spec(
+        LoopSpec.model_validate(
+            {"name": "plain", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+        )
+    )
+    captured_runs: list[list[str]] = []
+
+    def fake_run(cmd, *args, **kwargs):
+        captured_runs.append(list(cmd))
+        return MagicMock(returncode=0, stdout="", stderr="")
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+
+    result = runner.invoke(app, ["delete", "plain", "--force"])
+    assert result.exit_code == 0, result.stdout
+    # No launchctl calls when no plist exists.
+    assert not captured_runs
+
+
+def test_delete_with_bootout_failure_keeps_plist_and_warns(
+    isolated_store, launchd_home, monkeypatch
+) -> None:
+    """FLAW #5 regression test: if bootout fails for a real reason (not "could
+    not find"), the plist must NOT be unlinked — keep it as a recovery
+    artifact. The spec is still deleted (user wants the loop gone) but the
+    warning tells them the launchd label may still be active.
+    """
+    spec = LoopSpec.model_validate(
+        {"name": "stuck", "description": "d", "schedule": "*/15 * * * *", "skill_id": "x"}
+    )
+    isolated_store.save_spec(spec)
+    plist_path = launchd_home / "Library" / "LaunchAgents" / "com.vibesop.loop.stuck.plist"
+    plist_path.parent.mkdir(parents=True, exist_ok=True)
+    plist_path.write_bytes(b"<plist/>")
+
+    # bootout returns a real failure (not "Could not find").
+    def fake_run(cmd, *args, **kwargs):
+        return MagicMock(returncode=1, stdout="", stderr="Bootout failed: 36")
+
+    monkeypatch.setattr("subprocess.run", fake_run)
+
+    result = runner.invoke(app, ["delete", "stuck", "--force"])
+    assert result.exit_code == 0  # delete itself succeeds
+    assert "bootout 失败" in result.stdout
+    assert "launchd label 可能仍活跃" in result.stdout
+    # Plist preserved for manual recovery.
+    assert plist_path.exists()
+    # Spec still gone.
+    assert isolated_store.load_spec("stuck") is None
+
+
+# Late import so the fixture above can be defined without mandatory import-time cost.
+from unittest.mock import MagicMock  # noqa: E402


• Now I should look at supporting context: CronExpr (to check weekday semantics, dow range — cron 7 vs launchd 0-7? Actually launchd Weekday: 0 and 7 both Sunday, POSIX also), LoopSpec name validation, tick lock behavior. Also check whether `_is_macos` is monkeypatchable in tests — tests don't test non-macOS. Let me look at the scheduler CronExpr and tick code quickly, plus LoopSpec model. Also check `delete` — `_bootout_launchd` defined after `delete` in the file? `delete` at line ~350, `_bootout_launchd` defined at line ~640. Since it's called at runtime, fine.

  Key things to verify:
  1. CronExpr dow semantics — does it allow 7 and normalize to 0? Test says yes.
  2. launchd Weekday semantics vs cron Day+Dow OR semantics — brief says verified.
  3. Tick lock for dedup — check executor/scheduler for same-minute dedup. Brief says "tick's per-loop lock 保证同分钟去重". Is that actually true? StartInterval fires every N*60 seconds from bootstrap time, so drift accumulates relative to minute boundaries. Also multiple launchd fires while a previous tick still running → launchd won't start a new instance if one is running (launchd won't run job if already running — it skips). Actually launchd does not run a second instance if the job is still running. But manual tick + launchd tick concurrently → does tick have a file lock? Phase B added 文件锁 for instinct learner. Need to check tick code for a per-loop lock.

  Let me read scheduler.py and the tick command / executor to verify the dedup claim and lock. Also models.py for name validation.

  Potential flaws I already notice:

  1. **P1: `_bootstrap_launchd` refresh detection with `result.returncode == 125`** — exit 125 from launchctl bootstrap isn't a stable documented code? Actually bootstrap returns 125? The brief asserts verified. But the fallback stderr string "already bootstrapped" — localization: launchd errors come from launchd daemon, which is not localized (system daemon messages are English). Acceptable but fragile.

  2. **P1: bootout before delete when plist exists but label was bootstrapped under a *different* plist path or gui domain mismatch** — minor.

  3. **FileNotFoundError: launchctl not in PATH** — `subprocess.run` raises FileNotFoundError, uncaught → traceback to user. Q7 mentions it. Should be P2/must-fix? It's a crash on non-mac... but _is_macos guards, launchctl always present on macOS. Practically low risk; P2.

  4. **P1: plist write is not atomic** — write_bytes direct; if interrupted, partial plist. Minor. Also refresh path: writes new plist, bootouts, bootstraps — fine.

  5. **P1?: install-launchd doesn't verify the rendered plist roundtrip with plutil** — Q7.3; plistlib.dumps always produces valid plist; plutil validation redundant. Acceptable to defer.

  6. **delete uses `missing_ok=True` bootout — but if bootout fails with "Could not find" that's treated as success and plist is deleted. But wait: if label exists under a different service path... fine.

  7. **Important potential flaw**: In `delete`, the bootout happens only `if plist_path.exists()`. But a label could be bootstrapped while the plist file was manually deleted — then delete leaves zombie label. Edge case; bootout missing_ok covers. Minor, acceptable, could mention P2.

  8. **Real flaw candidate**: `install_launchd` writes plist *before* bootstrap; refresh path bootouts old and re-bootstraps new — good. But on refresh failure (result2 fails), install cleans up the plist (unlink) and exits 1 — leaving the label booted-out and no plist: fine actually.

  9. **Concurrency race between manual tick and launchd tick**: does tick hold a per-loop lock? Need to check. Brief claims "tick 的 per-loop lock 保证同分钟去重". Verify in code. Also StartInterval drift: StartInterval counts from job load, not wall-clock aligned — so `*/15` may fire at :07, :22, ... and tick dedup within same minute is not about alignment but duplicate runs. Actually the "same minute dedup" claim — tick records last_run? Let me check tick command code and LoopState.

  10. **Q1**: paused loop still in launchd — acceptable.

  11. **Q2**: refresh automatic vs --refresh flag — auto refresh is fine; bootout+bootstrap is idempotent-ish. Acceptable.

  12. **Q3**: delete retains plist on bootout failure — acceptable trade-off, but alternative (abort delete) arguably safer. Judge acceptable.

  13. **Q4**: log path conflicts across project roots — LoopSpec store: is it per-project (.vibe/loops in project) or global? LoopStore() — check where specs are stored. If per-project store, then same name in two different projects → two loops with the SAME label `com.vibesop.loop.<name>` and same plist path! Install from project B would refresh/overwrite project A's plist (WorkingDirectory changes). That's a real cross-project collision. brief's Q4 says "LoopSpec 是 name-unique 的（store 层校验）" — but that's per-store. If store is project-local, two projects can have same name → label collision. This is a significant new flaw (P1 or P2). Need to check LoopStore location: LoopStore() with no args — check code.

  Let me read loop_cmd.py head and LoopStore, models, scheduler quickly.__init__.py
__pycache__
executor.py
launchd.py
models.py
scheduler.py
store.py
      41 src/vibesop/core/loop/__init__.py
     421 src/vibesop/core/loop/executor.py
     237 src/vibesop/core/loop/launchd.py
     405 src/vibesop/core/loop/models.py
     296 src/vibesop/core/loop/scheduler.py
     197 src/vibesop/core/loop/store.py
    1597 total
Big finding: LoopStore is GLOBAL at `~/.vibe/loops/`, but `render_plist` writes logs to `<project_root>/.vibe/loops/<name>/` — a project-local directory! So the spec/state live in `~/.vibe/loops/<name>/` but the plist's stdout/stderr go to `<cwd>/.vibe/loops/<name>/`. That directory may not exist → launchd failing to open log file? launchd creates the file but parent dirs must exist. If `<project_root>/.vibe/loops/<name>/` doesn't exist, launchd fails to redirect stdout → job fails to launch? Actually launchd fails with "Service could not initialize" if the log path directory doesn't exist. This is a P1 flaw: log path points into cwd's .vibe which likely doesn't exist for the global store layout. Also Q4's premise "LoopSpec 是 name-unique 的" — true globally since store is global (~/.vibe/loops). So name collision across projects can't happen. But then the log path is wrong relative to the store.

  Wait — check tick: does tick create `<project_root>/.vibe/loops`? Tick uses LoopStore() = ~/.vibe/loops. So logs go to a directory that nothing creates. install_launchd could mkdir the loop_dir before bootstrap. Check: does install create it? No — it only mkdirs plist parent. So on first tick, launchd can't open StandardOutPath → job spawn fails? Actually if launchd can't open the stdout path, the job fails to spawn (error in launchd log). This is a real P1.

  Also WorkingDirectory = Path.cwd() at install time; if the project dir is later moved/deleted, job fails. Acceptable/documented.

  Next: check scheduler/tick dedup claim and lock. Read scheduler.py CronExpr and executor tick lock. Also models name validation.Confirmed: LoopStore is global at `~/.vibe/loops/`. But `render_plist` writes log paths to `<project_root>/.vibe/loops/<name>/`. That's inconsistent — the actual loop state lives in `~/.vibe/loops/<name>/` while plist logs go to the cwd's `.vibe/loops/<name>/` which likely doesn't exist. launchd fails to spawn job when StandardOutPath's parent dir doesn't exist (it logs "Service could not initialize" and won't run). So this is a P1 (arguably P0 for usability): install-launchd writes logs to a directory that nothing creates, and WorkingDirectory=Path.cwd() combined with global store means `vibe loop tick --name X` run from project root — does tick use LoopStore() default global? Yes. So tick works regardless of cwd, but logs go to cwd/.vibe/loops/name which doesn't exist → job spawn failure. Unless... does `uv run vibe` in WorkingDirectory matter? WorkingDirectory needed for `uv run` to find pyproject. So cwd is needed for uv, but logs point into cwd/.vibe which likely never created.

  Actually wait — maybe tick itself creates `<cwd>/.vibe`? Tick uses LoopStore() → `~/.vibe/loops`. The `.vibe` in the project (I saw `.vibe/` directory in the project listing!) — hmm, the working dir listing shows `.vibe/` exists in this project. Let me check what's in `.vibe/` — maybe the loop state actually lives per-project? But store.py default is `Path.home() / ".vibe" / "loops"`. The project's `.vibe/` dir may be something else (vibe config). So log path `project_root/.vibe/loops/<name>` is project-local while state is home-global — mismatch. In this repo `.vibe` exists but `loops` subdir probably not.

  P1 flaw: log directory is never created. Fix: `render_plist`/install should `mkdir -p` the log dir, or default log paths to `~/.vibe/loops/<name>/` (the store dir, which exists).

  Also this answers Q4 differently: since store is GLOBAL, name uniqueness is global — Q4's stated premise (two loops same name from different dirs) can't happen at the store level. But Q4's answer in brief says "LoopSpec 是 name-unique 的（store 层校验）" — true globally. However the WorkingDirectory/log-path ties the launchd job to a specific project dir; moving/deleting the project breaks the job. That's a documentation point.

  Now check tick: does tick have a per-loop lock for dedup? Check executor.py and tick command. The brief claims "tick 的 per-loop lock 保证同分钟去重" and StartInterval drift is handled. Let me check the tick implementation in loop_cmd.py (lines ~500-620) and executor.

• 再看 tick 命令实现和 executor 的锁机制，验证"同分钟去重"的说法。    tick_lock = _acquire_tick_lock(store, name, blocking=True)
    try:
        state = store.load_state(name) or LoopState(spec=spec)
        if state.status == LoopStatus.ACTIVE:
            console.print(f"[yellow]Loop '{name}' 已处于活跃状态[/yellow]")
            return

        if state.status == LoopStatus.DEAD:
            console.print(
                f"[yellow]Loop '{name}' 处于 DEAD 状态。使用 "
                f"[bold]vibe loop reset {name}[/bold] 清除失败计数并重新激活。[/yellow]"
            )
            raise typer.Exit(1)

        if not validate_transition(state.status, LoopStatus.ACTIVE):
            console.print(
                f"[red]❌ 无法从 {state.status.value} 恢复 —— "
                f"{state.status.value} 为终态，resume 仅用于 PAUSED/FAILING。[/red]"
            )
            raise typer.Exit(1)

        state.status = LoopStatus.ACTIVE
        state.consecutive_failures = 0
        store.save_state(state)
    finally:
        _release_tick_lock(tick_lock)
    console.print(f"[green]▶️ Loop '{name}' 已恢复[/green]")


@app.command()
def reset(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """重置 DEAD loop 回 ACTIVE（清除连续失败计数）。

    DEAD 是终态，普通 ``resume`` 不会复活它；``reset`` 是唯一的恢复路径。
    """
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    # Hold the per-loop lock across load→mutate→save (kimi HIGH).
    tick_lock = _acquire_tick_lock(store, name, blocking=True)
    try:
        state = store.load_state(name) or LoopState(spec=spec)
        if state.status != LoopStatus.DEAD:
            console.print(
                f"[yellow]Loop '{name}' 当前状态为 {state.status.value}，非 DEAD。"
                f"reset 仅用于 DEAD loop。[/yellow]"
            )
            raise typer.Exit(1)

        state.status = LoopStatus.ACTIVE
        state.consecutive_failures = 0
        store.save_state(state)
    finally:
        _release_tick_lock(tick_lock)
    console.print(f"[green]♻️ Loop '{name}' 已重置为 ACTIVE（连续失败计数已清零）[/green]")


# ──────────────────────────────────────────────────────────────────
# tick — single polling cycle (the missing execution bridge)
# ──────────────────────────────────────────────────────────────────


@app.command()
def tick(
    name: str = typer.Option(
        "",
        "--name",
        "-n",
        help="只检查指定 loop（默认检查全部）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="只显示哪些会被触发，不实际执行",
    ),
) -> None:
    """执行一次轮询：检查所有 ACTIVE/FAILING loops 的 cron，匹配则执行。

    典型用法：外部 cron 每分钟调用 ``vibe loop tick`` 一次。
    """
    store = LoopStore()
    specs = store.list_specs()

    if not specs:
        console.print("[dim]没有 loop。使用 `vibe loop create` 创建。[/dim]")
        return

    # Filter by --name and by status (skip PAUSED/DEAD/RETIRED).
    eligible: list[LoopSpec] = []
    skipped: list[tuple[str, LoopStatus]] = []
    for spec in specs:
        if name and spec.name != name:
            continue
        state = store.load_state(spec.name) or LoopState(spec=spec)
        if state.status in _SKIP_STATUSES:
            skipped.append((spec.name, state.status))
        else:
            eligible.append(spec)

    if skipped and not eligible:
        console.print(
            f"[yellow]没有可执行的 loop — {len(skipped)} 个被跳过（PAUSED/DEAD/RETIRED）。[/yellow]"
        )
        return

    # Polling: which eligible specs match the current minute?
    daemon = CronDaemon()
    triggered = daemon.run_once(eligible)

    if not triggered:
        console.print(
            f"[dim]本轮无可触发 loop（{len(eligible)} eligible, {len(skipped)} skipped）。[/dim]"
        )
        return

    # Master kill-switch (C2): when loop.enabled is false, report what WOULD
    # trigger but do not execute (per LoopConfig docstring). Pre-fix this config
    # was dead — tick executed regardless of the switch.
    from vibesop.core.config.manager import ConfigManager

    if not ConfigManager().get_loop_config().enabled:
        console.print(
            f"[yellow]Loop execution disabled (loop.enabled=false) — "
            f"{len(triggered)} loop(s) would trigger:[/yellow]"
        )
        for spec in triggered:
            console.print(f"  • {spec.name} — {_target_str(spec, truncate=40)}")
        console.print("[dim]Set loop.enabled=true to execute.[/dim]")
        return

    # Dry-run: report and stop.
    if dry_run:
        console.print(f"[bold cyan]{len(triggered)}[/bold cyan] 个 loop 会被触发 (dry-run):")
        for spec in triggered:
            console.print(f"  • {spec.name} — {_target_str(spec, truncate=40)}")
        return

    # Execute each triggered loop. AgentRuntime is imported here (the CLI layer
    # may depend on agent) and injected into core/loop's executor, so core/loop
    # no longer imports the agent layer (Core->Agent inversion fix).
    from vibesop.agent.runtime.agent_runtime import AgentRuntime

    runtime = AgentRuntime()
    success_count = 0
    failure_count = 0
    for spec in triggered:
        tick_lock = _acquire_tick_lock(store, spec.name)
        if tick_lock is None:
            console.print(
                f"[yellow]⏭️  {spec.name}: 另一个 tick 正在进行 —— 跳过以避免并发写冲突[/yellow]"
            )
            continue
        try:
            console.print(f"[cyan]▶[/cyan] Ticking [bold]{spec.name}[/bold]...")
            record = execute_loop_tick(spec, runtime=runtime, store=store)
            if record.success:
                success_count += 1
                console.print(f"  [green]✅[/green] {record.matched_skill} ({record.duration_s}s)")
            else:
                failure_count += 1
                category = (
                    record.failure_info.category.value if record.failure_info else "unclassified"
                )
                console.print(f"  [red]❌[/red] {record.error[:80]} [dim]({category})[/dim]")
        finally:
            _release_tick_lock(tick_lock)  # releases fcntl lock + unlinks on Windows

    total = success_count + failure_count
    console.print(
        f"\n[bold]Tick 完成[/bold]: {total} 触发, "
        f"[green]{success_count} 成功[/green], "
        f"[red]{failure_count} 失败[/red]"
    )
    # Non-zero exit when any loop failed so external cron/launchd can detect it
    # (C3). Pre-fix tick always exited 0, masking total failure from the only
    # documented deployment (external cron every minute).
    if failure_count:
        raise typer.Exit(code=1)


# ──────────────────────────────────────────────────────────────────
# install-launchd / uninstall-launchd (Phase C)


• Tick lock exists: `_acquire_tick_lock(store, spec.name)` — non-blocking, skips if another tick running. Good: concurrent manual+launchd tick is handled by lock (the second skips). But note: the lock only prevents concurrent execution, NOT duplicate execution within the same minute sequentially. Claim in brief: "tick 的 per-loop lock 保证同分钟去重" — that's wrong! The lock prevents concurrent overlap, but two sequential ticks in the same minute (e.g. StartInterval drift causing fire at :30.2 and again at :59? no — StartInterval fires every N*60 seconds so can't fire twice in the same minute for N>=1... For StartInterval=900 it fires every 900s, so once per 15 min — no same-minute dup. For `* * * * *` StartInterval=60, fires every 60s — can't fire twice in same minute either, roughly. Actually StartInterval=60 fires every 60 seconds, so at most once per minute boundary? Every 60 seconds means it can fire at :00.5, :01.5 etc. — one fire per minute wall-clock minute? 60s spacing means consecutive fires are 60s apart; two fires in the same calendar minute requires spacing < 60s, impossible. So same-minute dup from a single launchd job is impossible for N>=60s. But manual tick + launchd tick in same minute → both would execute the loop sequentially (lock serializes, second one waits? No — non-blocking, second skips). Actually `_acquire_tick_lock(store, spec.name)` non-blocking → concurrent one skips. But sequential manual tick right after launchd tick completes → both execute in the same minute; no dedup by last_run timestamp. Does execute_loop_tick record last_run and check? CronDaemon.should_run matches the whole minute, so a second tick in the same minute will match again and execute again. Is there last_run dedup in executor? Grep showed no "last_run" match... wait, grep pattern included last_run and no matches in executor. Check models for last_run field. Let me check quickly.

  Also, launchd won't run a second instance while one is running (it skips). So the tick lock is for manual-vs-launchd concurrency. OK.

  Missing dedup: two ticks in same minute (manual + launchd, or two manual runs) both execute the loop. This pre-exists Phase C (tick existed before), but the plist makes it more likely (StartInterval fires at non-minute-aligned times). Actually for manual runs in cron-minutes + launchd StartInterval drifted, both could fire in the same minute. Is that a Phase C concern? The brief claims the lock dedups same-minute; that's inaccurate — the lock only dedups concurrent. Worth noting as P2 (documentation/correctness nuance), or P1 if duplicate execution is harmful (double instinct assemble). Let me check if there's a last_run check in execute_loop_tick. Let me look at executor execute_loop_tick quickly.        return

    stdout_tail = (result.stdout or "")[-2000:]
    stderr_tail = (result.stderr or "")[-2000:]

    if result.returncode == 0:
        record.success = True
        record.matched_skill = ""  # command targets have no skill
        record.output_summary = (stdout_tail or stderr_tail)[:200]
        record.error = ""
        record.failure_info = None
        return

    record.success = False
    record.error = f"command exited {result.returncode}: {stderr_tail}"
    record.failure_info = _classify_command_failure(stderr_tail, result.returncode)


def execute_loop_tick(
    spec: LoopSpec,
    runtime: LoopRunner,
    store: LoopStore | None = None,
) -> LoopRunRecord:
    """Execute one loop tick and persist the result.

    Args:
        spec: Loop definition. Caller is responsible for skipping
            ``PAUSED`` / ``DEAD`` loops — this function will execute
            whatever it's given.
        runtime: A ``LoopRunner`` (e.g. ``AgentRuntime``) that executes the
            routed query. Injected by the caller (CLI) so core/loop does not
            import the agent layer (Core->Agent inversion fix).
        store: LoopStore instance. ``None`` creates a default instance
            rooted at ``~/.vibe/loops/``.

    Returns:
        ``LoopRunRecord`` describing this tick. The record has already
        been appended to the loop's persisted ``LoopState``.
    """
    store = store or LoopStore()

    started_at = datetime.now(UTC)
    start_wall = time.monotonic()
    record = LoopRunRecord(loop_name=spec.name, started_at=started_at)

    # Load state up-front so cross-run history can be injected into the query.
    state = store.load_state(spec.name) or LoopState(spec=spec)
    history = RunHistory(
        recent_runs=list(state.recent_runs),
        progress_notes=list(state.progress_notes),
    )

    attempt = 0
    attempt_errors: list[str] = []  # accumulated across retries for debugging
    failure: FailureInfo | None = None  # initialised defensively (kimi latent-risk)
    while True:
        err = ""
        try:
            if spec.command_args:
                # Command-target path: no routing query, no AgentRuntime —
                # direct subprocess invocation. Reuses the same record/state
                # machine as routing so DEAD/FAILING transitions still fire.
                _run_command_target(spec, record)
                if record.success:
                    break
                err = record.error or "command failed"
                failure = record.failure_info or _classify_command_failure(err, return_code=None)
            else:
                query = _build_query(spec, history=history)
                # explain=True populates result.decision_message so output_summary
                # captures routing context for post-mortem debugging.
                result = runtime.handle_query(query, platform="generic", explain=True)

                if result.success and result.has_match:
                    record.success = True
                    record.matched_skill = result.skill_id or spec.skill_id
                    record.output_summary = (result.decision_message or "")[:200]
                    record.error = ""
                    record.failure_info = None
                    break

                if result.errors:
                    err = "; ".join(result.errors)
                elif not result.has_match:
                    err = "no matching skill found"
                else:
                    err = "routing completed without success"
                failure = _classify_failure(err)
        except Exception as e:
            # AgentRuntime.handle_query already swallows its own exceptions
            # into result.errors. This outer guard is for _build_query
            # (defensive — LoopSpec validation should prevent) and for
            # catastrophic runtime failures (e.g. import errors).
            err = f"executor exception: {e}"
            logger.exception("Loop tick raised unexpectedly [%s]", spec.name)
            failure = _classify_failure(err)

        assert failure is not None  # defensive: every path above assigns it

        # Retry only TRANSIENT failures, up to spec.max_retries (default 0 = off).
        # The retry stays inside the persistence boundary so a transient blip
        # does NOT advance the DEAD failure counter — only the final outcome
        # of the tick is recorded once.
        if failure.category == FailureCategory.TRANSIENT and attempt < spec.max_retries:
            attempt += 1
            attempt_errors.append(f"attempt {attempt}: {err}")
            delay = min(2 ** (attempt - 1) * spec.retry_delay_base, 300)
            time.sleep(delay)
            continue

        # Final failure — commit to record. If retries happened, prepend
        # earlier attempts' errors so post-mortem debugging isn't blind to
        # the first failure (adversarial review §2).
        record.success = False
        if attempt_errors:
            record.error = " | ".join([*attempt_errors, f"final: {err}"])
        else:
            record.error = err
        record.failure_info = failure
        break

    record.duration_s = round(time.monotonic() - start_wall, 2)
    record.finished_at = datetime.now(UTC)

    # Persist state — even on failure, so the failure counter advances.
    # Resilient: a save failure (disk full / IO) must not crash the tick or
    # mask the outcome — log loudly and still return the record. (kimi HIGH:
    # save_state was outside any try/except, so a failed save lost the
    # failure-counter advance AND propagated.)
    state.record_run(record)
    try:
        store.save_state(state)
    except Exception:
        logger.exception(
            "Failed to persist loop state for [%s] — failure counter may not advance",
            spec.name,
        )

    return record


__all__ = ["execute_loop_tick"]
Confirmed: LoopState has `last_run_at` but tick does NOT use it for same-minute dedup. So:

  - **Same-minute double execution**: manual tick + launchd StartInterval tick in the same minute → sequential executions both run the loop (lock is non-blocking so only prevents *concurrent* overlap; sequential runs both pass `should_run` since it matches the whole minute). The brief's claim "tick 的 per-loop lock 保证同分钟去重" is inaccurate — the lock dedups only concurrent ticks. With StartInterval=60 (from `* * * * *`), launchd fires every 60s so can't double-fire within one minute. But StartInterval drift vs manual runs can. Realistic risk: user runs `vibe loop tick` manually right after a launchd tick in same minute → double run. P2, fix: compare `state.last_run_at` truncated to minute with now, skip if equal. Pre-existing gap though (tick existed before Phase C); but launchd makes it more likely. Classify P2.

  Key P1 flaw: **log directory mismatch**. Store is global `~/.vibe/loops/`; plist logs to `<cwd>/.vibe/loops/<name>/`. Two problems:
    a) That directory is never created → launchd fails to spawn the job (StandardOutPath parent missing). Actually, does launchd create the file? launchd creates the log file but not intermediate directories; if the directory doesn't exist, job spawn fails. So every tick silently fails unless user happened to run `vibe loop` commands from that project dir which create `.vibe`? LoopStore creates `~/.vibe/loops` not project one. So `<cwd>/.vibe/loops/<name>` almost certainly doesn't exist → broken installs. This is a real P1 (arguably P0 — the feature doesn't work out of the box).
    b) Semantic mismatch with Q4: brief claims logs co-located with per-loop state dir — false, state is in ~/.vibe/loops.

  Fix suggestion: default log paths to `~/.vibe/loops/<name>/` (store dir, guaranteed to exist), or `mkdir -p` the loop_dir at install time. Also note WorkingDirectory=Path.cwd() is fine for `uv run` but ties job to that project.

  Second check: **plist_label from spec.name vs CLI name arg**: install uses spec.name for plist; uninstall/delete use the CLI-provided name. Names are kebab-case validated, fine.

  Third: **`_bootout_launchd` in `delete` runs before `store.delete_spec`** — but bootout uses name; ok.

  Fourth: **`uninstall_launchd` bootouts even when plist doesn't exist and loop name invalid** — fine.

  Fifth: **install-launchd refresh when plist exists but label bootstrapped from a DIFFERENT plist path** — bootout by label works regardless of path, fine.

  Sixth: **exit 125**: `launchctl bootstrap` exit codes are not formally documented/stable across macOS versions; 125 is observed. The stderr fallback helps. Localization: launchd daemon strings aren't localized (system frameworks generally return English for these), low risk. Acceptable with a note; but also note `125` could theoretically be returned for other reasons? Rare. Acceptable.

  Seventh: **FileNotFoundError when launchctl missing** — on macOS launchctl always exists at /usr/bin/launchctl and PATH for subprocess inherits user's shell PATH via CLI; basically always present. But if PATH is broken, `subprocess.run` raises FileNotFoundError → ugly traceback. P2: catch and report.

  Eighth: **plist write not atomic** (write_bytes direct). If interrupted mid-write, corrupt plist could be bootstrapped or picked up at next login. P2: use atomic write (tmp+replace), consistent with store's _atomic_write.

  Ninth: **delete order**: bootout happens before `store.delete_spec`. If bootout succeeds and unlink fails (OSError logged only), plist remains but label is booted out — benign. OK.

  Tenth: **`delete` on non-macOS skips plist check entirely** — plist only exists on macOS; but a user could move from mac to... edge, ignore.

  Eleventh: **install_launchd: `plist_path.write_bytes` before bootstrap; if render used cwd that later changes, plist stale.** Documentation issue, P2.

  Twelfth: **`_bootstrap_launchd` refresh: bootout missing_ok=True — if bootout fails with "Could not find" it's success, then bootstrap retry.** But scenario: label bootstrapped under a different domain (e.g. user bootstrapped into `gui/501` vs current uid)? Edge.

  Thirteenth: **Weekday 7 → 0 normalization for launchd**: launchd accepts 0-7 with 0 and 7 = Sunday; CronExpr normalizes 7→0, and `_is_wildcard(cron.dow, set(range(0,7)))` — if dow = {0,...,6} full it's wildcard. Fine. But subtle: launchd `Weekday` key when both Day and Weekday restricted — launchd StartCalendarInterval semantics for Day+Weekday: launchd uses AND? Actually launchd treats StartCalendarInterval like cron: if both Day and Weekday are specified... Apple docs say it follows cron semantics? Hmm. The brief says "CronExpr Day+Dow 都是 OR 语义（POSIX 和 launchd 一致）" — marked verified by previous reviewer. Actually this is a known subtlety: launchd does NOT implement the POSIX OR rule? Let me think. launchd.plist(5): StartCalendarInterval "This semantics is similar to that of cron(8)". Many sources say launchd implements cron semantics including the dom/dow OR. There are reports launchd treats them with OR like cron. I'll trust the prior verification but flag low-confidence? The previous adversarial reviewer verified it; I won't re-litigate beyond a note.

  Another: **`cron_to_start_interval_seconds` rejects `*/31` (>30) but `*/45`?** 60%45 != 0 → None, fine. `*/1` → 60. OK.

  Another: **schedule with seconds? no.**

  **StartCalendarInterval with sparse months e.g. `0 0 29 2 *`** — Feb 29 only in leap years; launchd handles. fine.

  **Test blind spots**: plutil validation — plistlib.dumps output is by construction valid; testing with plutil adds little. FileNotFoundError test — worth adding (P2). Concurrent manual+launchd — covered partially by lock tests? tick lock test exists? Not my concern deeply.

  **One more real check**: `install_launchd` uses `store.load_spec(name)` — store is `~/.vibe/loops`. And `render_plist` writes logs under cwd. Also WorkingDirectory=cwd but the user might install from any directory — `uv run vibe` requires pyproject in cwd or parents; if user installs from home dir, `uv run vibe` fails (no project). That's a UX pitfall but documented ("assumes ... pyproject.toml in project_root or its parents").

  **Also: install doesn't check whether name contains uppercase etc.** validated kebab.

  **Environment variables**: launchd job PATH is minimal (`/usr/bin:/bin:/usr/sbin:/sbin`), so `uv run vibe` will fail if uv is in /opt/homebrew/bin — ProgramArguments uses bare `uv` relying on PATH! launchd's default PATH does NOT include /opt/homebrew/bin. So default prefix `uv run vibe` likely fails on most Macs with Homebrew uv. That's a significant real-world P1! The docstring says "assumes uv on PATH" but launchd PATH ≠ user shell PATH. This will break in practice. Suggested fix: resolve absolute path of uv at install time (shutil.which) and bake it into the plist, or set EnvironmentVariables PATH including user's PATH. That's a genuine new P1 the adversarial review missed.

  Also `EnvironmentVariables` from env_overrides could include PATH — user can work around. But default broken = P1.

  **launchctl bootout in `delete` uses name arg not spec name** — fine.

  **Q1**: paused loop stays in launchd, tick skips — acceptable; document.

  **Q2**: auto-refresh vs --refresh: acceptable; bootout+bootstrap is safe & idempotent; making it explicit adds friction. Note: refresh does bootout even when the currently-bootstrapped plist differs → fine.

  **Q3**: delete keeps plist on bootout failure — acceptable trade-off; abort-delete alternative would block deletion for a recoverable issue; the warning covers it. But one wrinkle: delete proceeds and spec removed; label still firing tick every minute → tick finds no spec → prints "没有 loop" → exit 0? Actually tick with no specs returns 0. Wait, plist fires `tick --name X`; specs list empty → "没有 loop" exit 0 — no error noise, just wasted runs. So zombie label is mostly benign except noise in logs. Acceptable.

  **Q4**: premise partially wrong — store is global so name-unique globally; real issue is logs tie to install-time cwd and dir never created (my P1). Judgment: acceptable in principle (name uniqueness holds globally), but the log-path design needs fix.

  **Q5**: command_args not exposed in create — defer to Phase D acceptable; install-launchd works generically.

  **Q6**: exit 125 + stderr fallback — acceptable; launchd errors not localized (CFError domains are English); add note to prefer returncode-first logic which they do. One improvement: also match "service already loaded"? Minor.

  **Q7**: coverage gaps — FileNotFoundError worth a test (P2); plutil redundant (plistlib guarantees); concurrent tick partially covered by lock tests (check exists? there is `_acquire_tick_lock` tests presumably from Phase A). Acceptable with small additions.

  One more: **`_bootstrap_launchd` runs `subprocess.run` with no timeout** — launchctl could hang (rare; e.g. launchd stuck). P2: add timeout=30. Same in bootout.

  Another: **install writes plist with default permissions**; LaunchAgents plists fine.

  Another subtle: **refresh path bootout then bootstrap — if bootstrap retry fails, install unlinks plist and exits 1 — but now label is booted out AND plist gone: previously-working install destroyed**. Scenario: user edits spec schedule, re-runs install-launchd to refresh; bootstrap retry fails transiently → old working agent removed. Minor robustness note, P2: could keep old plist backup. Eh, mention as P2.

  Also **`test_delete_without_plist` asserts no launchctl calls — good.**

  **delete: bootout before confirmation?** It's after confirmation. OK.

  Also `_is_macos` guard in `delete` — fine.

  Now check: does anything create `<cwd>/.vibe/loops`? grep quickly? The loop dir for logs — check if executor or CLI creates project .vibe. LoopStore base is home. I'll do a quick grep for `.vibe` in src to see if project-local .vibe used elsewhere.src/vibesop/core/loop/launchd.py:169:            (assumes uv on PATH and a pyproject.toml in ``project_root`` or
ai_triage_log.jsonl
analytics.jsonl
cache
clear_epoch
config.toml
conversations
core
dist
execution_plans.jsonl
instincts
instincts.jsonl
instincts.jsonl.bak
instincts.jsonl.lock
memory
miss_counter.json
miss_salt
observability
optimization-plan-auto-opt.md
optimization-plan-p1.md
optimization-plan-p2.md
optimization-plan.md
plans
preferences.json
preferences.lock
PROJECT_CONTEXT.md
prompts
roadmap.md
routing_counter.json
rules
sequences.jsonl
sequences.jsonl.bak
sequences.jsonl.lock
session
skill-index.json
skill-routing.yaml
skills
snapshots
workflows
no .vibe/loops in project


error: failed to run prompt: provider.api_error: 403 You've reached your usage limit for this billing cycle. Your quota will be refreshed in the next cycle. To continue now, purchase extra usage or upgrade your plan: https://www.kimi.com/code/#pricing
See log: /Users/huchen/.kimi-code/logs/kimi-code.log
