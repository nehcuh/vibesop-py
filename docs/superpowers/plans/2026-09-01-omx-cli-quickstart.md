# OMX CLI Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the omx skill pack is installed (via `vibe install omx` or an opt-in quickstart question), also best-effort install the `oh-my-codex` CLI so agents stop reporting “no omx command”, without failing the pack or the wizard if Node/npm is missing.

**Architecture:** One helper `ensure_omx_cli()` in `src/vibesop/installer/omx_cli.py`. Call it from `PackInstaller.install_pack` on every successful omx install, and from `cli/commands/install.py` `_install_pack` on the already-installed skip path (that path never enters `PackInstaller`). Quickstart adds `install_omx: bool = False` and a default-No prompt; Yes reuses `_install_integration("omx")`. Never run `omx setup`. Never enable npm allowScripts.

**Tech Stack:** Python 3.12+, pytest, unittest.mock, `shutil.which` + `subprocess.run` (no network in tests). Run tests with `HF_HUB_OFFLINE=1 uv run pytest …`.

**Spec:** `docs/superpowers/specs/2026-09-01-omx-cli-quickstart-design.md`

---

## File map

| File | Role |
|---|---|
| Create `src/vibesop/installer/omx_cli.py` | `is_omx_pack`, `OmxCliResult`, `ensure_omx_cli` |
| Create `tests/installer/test_omx_cli.py` | Unit tests for helper (all which/subprocess mocked) |
| Modify `src/vibesop/installer/pack_installer.py` | After successful omx install, append CLI detail to msg |
| Modify `tests/installer/test_pack_installer.py` | omx success calls helper; other packs do not; already-installed omx still does |
| Modify `src/vibesop/cli/commands/install.py` | Skip-already-installed branch still ensures CLI for omx |
| Modify `tests/cli/test_install_command.py` | omx skip calls helper; auto-skip mocks helper (prevents real npm) |
| Modify `src/vibesop/installer/quickstart_runner.py` | `install_omx` field, prompt, summary, execute |
| Modify `tests/installer/test_quickstart.py` | Extra input for OMX prompt; Yes installs omx; force stays False |
| Modify `docs/OMX_GUIDE.md`, `knowledge/vibesop/vibesop-install-quickstart.md`, `CHANGELOG.md` | User-facing contract |

Do not add `ensure_omx_cli` to `installer/__init__.py` (keep the public installer surface unchanged).

---

### Task 1: `ensure_omx_cli` helper

**Files:**
- Create: `tests/installer/test_omx_cli.py`
- Create: `src/vibesop/installer/omx_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for best-effort oh-my-codex CLI companion."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from vibesop.constants import TRUSTED_PACKS
from vibesop.installer.omx_cli import OmxCliResult, ensure_omx_cli, is_omx_pack


class TestIsOmxPack:
    def test_name_omx(self) -> None:
        assert is_omx_pack("omx") is True

    def test_name_superpowers(self) -> None:
        assert is_omx_pack("superpowers") is False

    def test_trusted_url(self) -> None:
        assert is_omx_pack("other", TRUSTED_PACKS["omx"]) is True

    def test_unrelated_url(self) -> None:
        assert is_omx_pack("other", "https://example.com/skills") is False


class TestEnsureOmxCli:
    def test_present_skips_npm(self) -> None:
        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=["/usr/bin/omx"]),
            patch("vibesop.installer.omx_cli.subprocess.run") as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "present"
        assert result.omx_path == "/usr/bin/omx"
        assert "already" in result.detail.lower()
        mock_run.assert_not_called()

    def test_no_npm_skips(self) -> None:
        with (
            patch("vibesop.installer.omx_cli.shutil.which", return_value=None),
            patch("vibesop.installer.omx_cli.subprocess.run") as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "skipped_no_npm"
        assert "npm install -g oh-my-codex" in result.detail
        mock_run.assert_not_called()

    def test_npm_success_installs(self) -> None:
        which_values = [None, "/usr/local/bin/npm", "/usr/local/bin/omx"]

        def _which(name: str) -> str | None:
            if name == "omx":
                return which_values.pop(0) if which_values[0] is None or name == "omx" else None

        calls: list[str] = []

        def _which2(name: str) -> str | None:
            calls.append(name)
            if name == "omx":
                return "/usr/local/bin/omx" if calls.count("omx") > 1 else None
            if name == "npm":
                return "/usr/local/bin/npm"
            return None

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "added 1 package"
        completed.stderr = ""
        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which2),
            patch("vibesop.installer.omx_cli.subprocess.run", return_value=completed) as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "installed"
        assert result.omx_path == "/usr/local/bin/omx"
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0][:3] == ["/usr/local/bin/npm", "install", "-g"]
        assert "oh-my-codex" in mock_run.call_args.args[0]
        assert mock_run.call_args.kwargs["timeout"] == 180.0

    def test_npm_nonzero_fails_without_raising(self) -> None:
        completed = MagicMock()
        completed.returncode = 1
        completed.stdout = ""
        completed.stderr = "EACCES\npermission denied\n"

        def _which(name: str) -> str | None:
            return None if name == "omx" else "/usr/bin/npm"

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch("vibesop.installer.omx_cli.subprocess.run", return_value=completed),
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert "npm install -g oh-my-codex" in result.detail
        assert "permission denied" in result.detail

    def test_timeout_fails_without_raising(self) -> None:
        def _which(name: str) -> str | None:
            return None if name == "omx" else "/usr/bin/npm"

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch(
                "vibesop.installer.omx_cli.subprocess.run",
                side_effect=subprocess.TimeoutExpired("npm", 180),
            ),
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert "timed out" in result.detail.lower()
        assert "npm install -g oh-my-codex" in result.detail
```

Fix `test_npm_success_installs`: the `_which` first draft is messy. Use this exact implementation in the test file (replace the class method body above):

```python
    def test_npm_success_installs(self) -> None:
        omx_hits = {"n": 0}

        def _which(name: str) -> str | None:
            if name == "npm":
                return "/usr/local/bin/npm"
            if name == "omx":
                omx_hits["n"] += 1
                return "/usr/local/bin/omx" if omx_hits["n"] > 1 else None
            return None

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "added 1 package"
        completed.stderr = ""
        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch("vibesop.installer.omx_cli.subprocess.run", return_value=completed) as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "installed"
        assert result.omx_path == "/usr/local/bin/omx"
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "/usr/local/bin/npm"
        assert cmd[1:3] == ["install", "-g"]
        assert "oh-my-codex" in cmd
        assert mock_run.call_args.kwargs["timeout"] == 180.0
```

Do **not** leave the broken `_which_values` draft in the file.

- [ ] **Step 2: Run tests to verify they fail**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_omx_cli.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vibesop.installer.omx_cli'` (or import error for `ensure_omx_cli`).

- [ ] **Step 3: Write minimal implementation**

Create `src/vibesop/installer/omx_cli.py`:

```python
"""Best-effort oh-my-codex CLI companion for the omx skill pack."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

from vibesop.constants import TRUSTED_PACKS

__all__ = ["OmxCliResult", "ensure_omx_cli", "is_omx_pack"]

OMX_NPM_PACKAGE = "oh-my-codex"
OMX_CLI_TIMEOUT_S = 180.0
_MANUAL = "npm install -g oh-my-codex"


@dataclass(frozen=True)
class OmxCliResult:
    status: Literal["present", "installed", "skipped_no_npm", "failed"]
    detail: str
    omx_path: str | None = None


def is_omx_pack(pack_name: str, pack_url: str | None = None) -> bool:
    """True for the trusted omx pack name or its TRUSTED_PACKS URL."""
    if pack_name == "omx":
        return True
    if not pack_url:
        return False
    return pack_url.rstrip("/") == TRUSTED_PACKS["omx"].rstrip("/")


def _stderr_tail(text: str, n: int = 8) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def _prefix_bin_hint(npm: str) -> str:
    try:
        completed = subprocess.run(
            [npm, "prefix", "-g"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    prefix = (completed.stdout or "").strip()
    if not prefix:
        return ""
    return f" Add `{prefix}/bin` to PATH (npm prefix -g)."


def ensure_omx_cli(*, timeout_s: float = OMX_CLI_TIMEOUT_S) -> OmxCliResult:
    """Install `oh-my-codex` globally if needed. Never raises to the caller."""
    existing = shutil.which("omx")
    if existing:
        return OmxCliResult("present", f"omx CLI already on PATH ({existing})", existing)

    npm = shutil.which("npm")
    if not npm:
        return OmxCliResult(
            "skipped_no_npm",
            f"omx CLI skipped (npm not found). Install Node, then: {_MANUAL}",
        )

    try:
        completed = subprocess.run(
            [npm, "install", "-g", OMX_NPM_PACKAGE],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return OmxCliResult(
            "failed",
            f"omx CLI install timed out after {int(timeout_s)}s. Install manually: {_MANUAL}",
        )
    except OSError as exc:
        return OmxCliResult(
            "failed",
            f"omx CLI install failed ({exc}). Install manually: {_MANUAL}",
        )

    if completed.returncode != 0:
        tail = _stderr_tail(completed.stderr)
        extra = f" {tail}" if tail else ""
        return OmxCliResult(
            "failed",
            f"omx CLI install failed.{extra} Install manually: {_MANUAL}",
        )

    omx_path = shutil.which("omx")
    if omx_path:
        return OmxCliResult("installed", f"omx CLI installed ({omx_path})", omx_path)

    hint = _prefix_bin_hint(npm)
    return OmxCliResult(
        "failed",
        f"npm installed {OMX_NPM_PACKAGE} but `omx` is not on PATH.{hint} "
        f"Install manually: {_MANUAL}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_omx_cli.py -q
```

Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/installer/omx_cli.py tests/installer/test_omx_cli.py
git commit -m "$(cat <<'EOF'
feat(installer): add best-effort oh-my-codex CLI helper

OMX skills invoke `omx state` / `omx doctor`. This helper installs the
npm CLI when missing and degrades to a warning when Node/npm is absent.
EOF
)"
```

---

### Task 2: Call helper from `PackInstaller.install_pack`

**Files:**
- Modify: `src/vibesop/installer/pack_installer.py`
- Test: `tests/installer/test_pack_installer.py`

There are two successful returns in `install_pack`:

1. Already-installed early return (`return True, msg` around the `already_installed=True` branch).
2. Fresh install `return True, msg` after lock write.

Both must run the helper when `is_omx_pack(pack_name, pack_url)`. Failed returns must not.

- [ ] **Step 1: Write the failing tests**

Add to `tests/installer/test_pack_installer.py` (imports: add `from vibesop.installer.omx_cli import OmxCliResult`):

```python
class TestOmxCliCompanion:
    """Successful omx installs must ensure the CLI; other packs must not."""

    def test_omx_fresh_install_appends_cli_detail(self) -> None:
        cli = OmxCliResult("installed", "omx CLI installed (/usr/bin/omx)", "/usr/bin/omx")
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/autopilot/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = True
                mock_cls.return_value = mock_analyzer
                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "omx"
                    planner_cls.return_value.plan.return_value = mock_plan
                    with patch(
                        "vibesop.installer.pack_installer.ensure_omx_cli",
                        return_value=cli,
                    ) as mock_cli:
                        success, msg = installer.install_pack(
                            "omx", "https://github.com/Yeachan-Heo/oh-my-codex"
                        )
        assert success is True
        mock_cli.assert_called_once()
        assert "omx CLI installed (/usr/bin/omx)" in msg

    def test_non_omx_pack_does_not_ensure_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/test/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = True
                mock_cls.return_value = mock_analyzer
                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "test-pack"
                    planner_cls.return_value.plan.return_value = mock_plan
                    with patch("vibesop.installer.pack_installer.ensure_omx_cli") as mock_cli:
                        success, _msg = installer.install_pack(
                            "test-pack", "https://example.com/test-pack"
                        )
        assert success is True
        mock_cli.assert_not_called()

    def test_omx_already_installed_still_ensures_cli(self) -> None:
        cli = OmxCliResult("present", "omx CLI already on PATH (/usr/bin/omx)", "/usr/bin/omx")
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "omx"
            target.mkdir()
            (target / "SKILL.md").write_text("# omx\n", encoding="utf-8")
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target / "SKILL.md"],
                )
                mock_cls.return_value = mock_analyzer
                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target
                    planner_cls.return_value.plan.return_value = mock_plan
                    with patch(
                        "vibesop.installer.pack_installer.ensure_omx_cli",
                        return_value=cli,
                    ) as mock_cli:
                        success, msg = installer.install_pack(
                            "omx", "https://github.com/Yeachan-Heo/oh-my-codex"
                        )
        assert success is True
        mock_cli.assert_called_once()
        assert "Already installed" in msg
        assert "omx CLI already on PATH" in msg
```

Place this class after `TestPackInstaller` (before `TestSkillSymlinks` is fine).

- [ ] **Step 2: Run tests to verify they fail**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_pack_installer.py::TestOmxCliCompanion -q
```

Expected: FAIL — `ensure_omx_cli` not defined on the pack_installer module, or `assert_called_once` fails because it was never invoked.

- [ ] **Step 3: Write minimal implementation**

In `src/vibesop/installer/pack_installer.py`:

Add import next to the other `vibesop.installer` imports:

```python
from vibesop.installer.omx_cli import ensure_omx_cli, is_omx_pack
```

Add this method on `PackInstaller` (near `_build_install_msg`):

```python
    def _with_omx_cli(self, pack_name: str, pack_url: str | None, msg: str) -> str:
        if not is_omx_pack(pack_name, pack_url):
            return msg
        result = ensure_omx_cli()
        return f"{msg}\n{result.detail}"
```

Change the already-installed success return from `return True, msg` to:

```python
                        if scope == "global":
                            self._rebuild_global_index(pack_name)
                        return True, self._with_omx_cli(pack_name, pack_url, msg)
```

Change the fresh-install success return (after lock write, currently `return True, msg`) to:

```python
            return True, self._with_omx_cli(pack_name, pack_url, msg)
```

Do not call `_with_omx_cli` on failure returns.

- [ ] **Step 4: Run tests to verify they pass**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_pack_installer.py::TestOmxCliCompanion tests/installer/test_pack_installer.py::TestPackInstaller::test_install_pack_with_url tests/installer/test_pack_installer.py::TestPackInstaller::test_install_unknown_pack -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/installer/pack_installer.py tests/installer/test_pack_installer.py
git commit -m "$(cat <<'EOF'
feat(installer): ensure omx CLI after successful omx pack install

Fresh and already-installed PackInstaller paths both run ensure_omx_cli
and append the one-liner to the install message. Other packs are unchanged.
EOF
)"
```

---

### Task 3: CLI skip path for already-installed `vibe install omx`

**Files:**
- Modify: `src/vibesop/cli/commands/install.py`
- Modify: `tests/cli/test_install_command.py`

`_install_pack` returns `"skipped"` when the global pack is already installed **without** calling `PackInstaller.install_pack`. That is the path this machine already hit. Must still call `ensure_omx_cli()` for omx.

Existing `test_install_auto_skips_installed` includes omx as installed. After this change it will call `ensure_omx_cli` for real unless mocked — patch it there so CI never hits npm.

- [ ] **Step 1: Write the failing tests**

Add to `tests/cli/test_install_command.py`:

```python
    @patch("vibesop.cli.commands.install.ensure_omx_cli")
    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_omx_already_installed_still_ensures_cli(
        self, mock_loader_cls: Any, mock_installer_cls: Any, mock_cli: Any
    ) -> None:
        from vibesop.installer.omx_cli import OmxCliResult

        mock_cli.return_value = OmxCliResult(
            "installed", "omx CLI installed (/usr/bin/omx)", "/usr/bin/omx"
        )
        mock_installer_cls.return_value = MagicMock()
        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {"omx": {"installed": True}}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "omx"])
        assert result.exit_code == 0
        assert "already installed" in result.output
        mock_installer_cls.return_value.install_pack.assert_not_called()
        mock_cli.assert_called_once()
        assert "omx CLI installed" in result.output

    @patch("vibesop.cli.commands.install.ensure_omx_cli")
    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_already_installed_non_omx_does_not_ensure_cli(
        self, mock_loader_cls: Any, mock_installer_cls: Any, mock_cli: Any
    ) -> None:
        mock_installer_cls.return_value = MagicMock()
        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {"superpowers": {"installed": True}}
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "superpowers"])
        assert result.exit_code == 0
        mock_cli.assert_not_called()
```

Update `test_install_auto_skips_installed` to patch `ensure_omx_cli` so `--auto` skipping omx does not talk to npm:

```python
    @patch("vibesop.cli.commands.install.ensure_omx_cli")
    @patch("vibesop.cli.commands.install.PackInstaller")
    @patch("vibesop.cli.commands.install.ExternalSkillLoader")
    def test_install_auto_skips_installed(
        self, mock_loader_cls: Any, mock_installer_cls: Any, mock_cli: Any
    ) -> None:
        from vibesop.installer.omx_cli import OmxCliResult

        mock_cli.return_value = OmxCliResult("present", "omx CLI already on PATH", "/bin/omx")
        mock_installer = MagicMock()
        mock_installer_cls.return_value = mock_installer

        mock_loader = MagicMock()
        mock_loader.get_supported_packs.return_value = {
            "gstack": {"installed": True},
            "superpowers": {"installed": True},
            "omx": {"installed": True},
            "mattpocock": {"installed": True},
        }
        mock_loader_cls.return_value = mock_loader

        result = runner.invoke(app, ["install", "--auto"])
        assert result.exit_code == 0
        assert "already installed, skipping" in result.output
        mock_installer.install_pack.assert_not_called()
        mock_cli.assert_called_once()
```

Decorator order: `@patch` closest to the function is the last arg. Keep `ensure_omx_cli` as the top decorator so it is the last parameter.

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/cli/test_install_command.py::TestInstallCommand::test_install_omx_already_installed_still_ensures_cli tests/cli/test_install_command.py::TestInstallCommand::test_install_already_installed_non_omx_does_not_ensure_cli -q
```

Expected: FAIL — cannot patch `vibesop.cli.commands.install.ensure_omx_cli` (not imported yet) and/or helper not called.

- [ ] **Step 3: Write minimal implementation**

In `src/vibesop/cli/commands/install.py`, add to the existing installer imports (top of file, next to `PackInstaller` import around line 41):

```python
from vibesop.installer.omx_cli import ensure_omx_cli, is_omx_pack
```

Replace the skip branch inside `_install_pack` (the block that prints “already installed” and `return "skipped"`) with:

```python
    if not force and pack_url is None and scope == "global":
        supported = loader.get_supported_packs()
        if supported.get(pack_name, {}).get("installed"):
            if not quiet:
                console.print(
                    f"[yellow]⚠ {pack_name} is already installed[/yellow]\n"
                    "[dim]Use --force to reinstall[/dim]\n"
                )
            if is_omx_pack(pack_name, pack_url):
                cli = ensure_omx_cli()
                style = "green" if cli.status in ("present", "installed") else "yellow"
                console.print(f"[{style}]{cli.detail}[/{style}]\n")
            return "skipped"
```

Always print the CLI one-liner on this path, including `--auto` quiet skips, so a missing npm is visible.

- [ ] **Step 4: Run tests to verify they pass**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/cli/test_install_command.py -q
```

Expected: PASS (entire file, including updated auto-skip).

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/cli/commands/install.py tests/cli/test_install_command.py
git commit -m "$(cat <<'EOF'
fix(cli): ensure omx CLI when vibe install omx is already installed

The skip-already-installed branch never entered PackInstaller, so a
machine with omx skills but no `omx` binary stayed broken. Run the
helper on that path; non-omx skips are unchanged.
EOF
)"
```

---

### Task 4: Quickstart opt-in OMX question

**Files:**
- Modify: `src/vibesop/installer/quickstart_runner.py`
- Modify: `tests/installer/test_quickstart.py`

`install_omx: bool = False` at the **end** of `QuickstartConfig` so existing constructors keep working.

Interactive flow today (global): install type → platform → (integrations skipped because False) → (hooks skipped because True) → confirm.

After this task: … → OMX question → confirm.

Tests that drive `run()` with `input` must gain one extra answer:

| Test | Current inputs | New inputs |
|---|---|---|
| `test_run_uses_provided_platform` | `["1", "n"]` | `["1", "", "n"]` (type, OMX default No, cancel) |
| `test_run_cancelled_at_confirm` | `["1", "1", "n"]` | `["1", "1", "", "n"]` (type, platform, OMX default No, cancel) |

`--force` must still never call `input()` and must keep `install_omx is False`.

- [ ] **Step 1: Write the failing tests**

Update the two `input` sequences above first so they fail for the right reason after the prompt is added (StopIteration if the prompt is added without updating inputs — update tests in the same task as the prompt).

Add:

```python
    def test_ask_install_type_global_omx_defaults_false(self) -> None:
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="1"):
            config = runner._ask_install_type(Path("/tmp/project"))
        assert config.install_omx is False

    def test_execute_installation_omx_yes_installs_omx_pack(self, tmp_path: Path) -> None:
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=tmp_path,
            global_install=True,
            install_omx=True,
        )
        with (
            patch("vibesop.installer.init_support._ensure_global_config"),
            patch("vibesop.installer.quickstart_runner.VibeSOPInstaller") as inst_cls,
            patch("vibesop.core.skills.indexer.SkillIndexer") as idx_cls,
            patch.object(runner, "_install_integration") as mock_omx,
            patch.object(runner, "_sync_platform_symlinks") as mock_sync,
        ):
            inst_cls.return_value.install.return_value = {
                "success": True,
                "hooks_installed": [],
                "files_created": [],
                "errors": [],
            }
            idx = MagicMock()
            idx.global_index_path.exists.return_value = True
            idx.build_index.return_value = MagicMock(success=True)
            idx_cls.return_value = idx
            assert runner._execute_installation(config) is True
        mock_omx.assert_called_once_with("omx", "opencode")
        mock_sync.assert_called()

    def test_execute_installation_omx_no_skips_pack(self, tmp_path: Path) -> None:
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=tmp_path,
            global_install=True,
            install_omx=False,
        )
        with (
            patch("vibesop.installer.init_support._ensure_global_config"),
            patch("vibesop.installer.quickstart_runner.VibeSOPInstaller") as inst_cls,
            patch("vibesop.core.skills.indexer.SkillIndexer") as idx_cls,
            patch.object(runner, "_install_integration") as mock_omx,
        ):
            inst_cls.return_value.install.return_value = {
                "success": True,
                "hooks_installed": [],
                "files_created": [],
                "errors": [],
            }
            idx = MagicMock()
            idx.global_index_path.exists.return_value = True
            idx.build_index.return_value = MagicMock(success=True)
            idx_cls.return_value = idx
            assert runner._execute_installation(config) is True
        mock_omx.assert_not_called()
```

In `TestForceMode.test_force_never_calls_input`, after existing asserts add:

```python
        assert config.install_omx is False
```

Add an interactive test that Yes sets the flag (cancel before execute so we do not need a full installer mock):

```python
    def test_run_omx_yes_sets_config(self, tmp_path: Path) -> None:
        runner = QuickstartRunner()
        # type=global, platform=1, omx=y, proceed=n
        with patch.object(builtins, "input", side_effect=["1", "1", "y", "n"]):
            result = runner.run(project_path=tmp_path)
        assert result["success"] is False
        assert result["config"] is not None
        assert result["config"].install_omx is True
```

- [ ] **Step 2: Run tests to verify new ones fail**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_quickstart.py::TestQuickstartRunner::test_ask_install_type_global_omx_defaults_false tests/installer/test_quickstart.py::TestQuickstartRunner::test_execute_installation_omx_yes_installs_omx_pack tests/installer/test_quickstart.py::TestQuickstartRunner::test_run_omx_yes_sets_config tests/installer/test_quickstart.py::TestForceMode::test_force_never_calls_input -q
```

Expected: FAIL — `QuickstartConfig` has no `install_omx`, or `test_run_omx_yes_sets_config` gets StopIteration / `install_omx is False`.

- [ ] **Step 3: Write minimal implementation**

`QuickstartConfig`:

```python
@dataclass
class QuickstartConfig:
    platform: str
    install_integrations: bool | None
    install_hooks: bool | None
    project_path: Path
    global_install: bool
    install_omx: bool = False
```

In `run()` force branch, pass `install_omx=False` explicitly on the `QuickstartConfig(...)`.

In `_ask_install_type`, both return values get `install_omx=False`.

In the interactive branch of `run()`, after the hooks question block and before `_show_summary`:

```python
                config.install_omx = self._ask_yes_no(
                    "Install OMX (oh-my-codex skills + CLI)?",
                    default=False,
                )
                console.print()
```

In `_show_summary`, after the Hooks line:

```python
        console.print(f"│ OMX: {'Yes' if config.install_omx else 'No':<20} │")
```

In `_execute_installation`, after the `if config.install_integrations:` block (do not fold OMX into that flag):

```python
            if config.install_omx:
                self._install_integration("omx", config.platform)
                self._sync_platform_symlinks(config.platform)
```

Update `test_run_uses_provided_platform` inputs to `["1", "", "n"]` and `test_run_cancelled_at_confirm` inputs to `["1", "1", "", "n"]`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_quickstart.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/installer/quickstart_runner.py tests/installer/test_quickstart.py
git commit -m "$(cat <<'EOF'
feat(quickstart): opt-in OMX skills + CLI install

Adds a default-No prompt so cold start stays builtin-only, while Yes
reuses pack install (and therefore ensure_omx_cli). --force never asks.
EOF
)"
```

---

### Task 5: Docs and changelog

**Files:**
- Modify: `docs/OMX_GUIDE.md` (启用方法)
- Modify: `knowledge/vibesop/vibesop-install-quickstart.md`
- Modify: `CHANGELOG.md` Unreleased Added

- [ ] **Step 1: Update `docs/OMX_GUIDE.md` 启用方法**

Replace the method-1 block so it states the CLI companion:

```markdown
### 方法 1: 自动同步

```bash
# 安装 OMX 技能包（外部技能，需先安装）
# 同时 best-effort 安装 oh-my-codex CLI（`omx state` / `omx doctor`）。
# 没有 Node/npm 时技能包仍成功，并打印手工命令：npm install -g oh-my-codex
vibe install omx

# 同步所有技能（包括已安装的 OMX）到 Claude Code
vibe skills sync claude-code

# 查看已同步的技能
vibe skills list
```

`vibe install omx` **does not** run `omx setup` (that writes Codex `AGENTS.md` / `~/.codex`). Use `omx setup` yourself only if you want the Codex runtime.
```

Keep methods 2 and 3.

- [ ] **Step 2: Update `knowledge/vibesop/vibesop-install-quickstart.md`**

In the “首次使用：三步走” section, after the `vibe quickstart` bullet, add:

```markdown
交互向导默认不装第三方包。可选一步 `Install OMX (oh-my-codex skills + CLI)?`（默认 No）；Yes 会装 omx 技能包并 best-effort 安装 `omx` CLI。`vibe quickstart --force` 跳过这一步。
```

- [ ] **Step 3: Changelog**

Under `## [Unreleased]` → `### Added`, prepend:

```markdown
- **OMX CLI companion on pack install**: `vibe install omx` (and `--auto` / already-installed skip) best-effort runs `npm install -g oh-my-codex` so skill bodies that call `omx state` have a binary. Missing Node/npm or npm failure warns and still exits 0. `vibe quickstart` asks `Install OMX (oh-my-codex skills + CLI)?` default No; `--force` does not. Does not run `omx setup`.
```

- [ ] **Step 4: Lint + targeted tests**

```bash
HF_HUB_OFFLINE=1 uv run pytest tests/installer/test_omx_cli.py tests/installer/test_pack_installer.py::TestOmxCliCompanion tests/cli/test_install_command.py tests/installer/test_quickstart.py -q
uv run ruff check src/vibesop/installer/omx_cli.py src/vibesop/installer/pack_installer.py src/vibesop/cli/commands/install.py src/vibesop/installer/quickstart_runner.py tests/installer/test_omx_cli.py tests/installer/test_pack_installer.py tests/cli/test_install_command.py tests/installer/test_quickstart.py
uv run ruff format --check src/vibesop/installer/omx_cli.py src/vibesop/installer/pack_installer.py src/vibesop/cli/commands/install.py src/vibesop/installer/quickstart_runner.py tests/installer/test_omx_cli.py
```

Expected: pytest all pass; ruff check/format clean. If format fails, run `uv run ruff format` on those paths and re-check.

- [ ] **Step 5: Commit**

```bash
git add docs/OMX_GUIDE.md knowledge/vibesop/vibesop-install-quickstart.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: document omx CLI companion on install and quickstart

Record that vibe install omx best-effort installs the npm CLI, degrades
when Node is missing, and never runs omx setup.
EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|---|---|
| `vibe install omx` fresh → pack then CLI | Task 2 |
| already-installed `vibe install omx` still CLI | Task 2 (PackInstaller) + Task 3 (CLI skip) |
| `--auto` omx skip still CLI | Task 3 (`test_install_auto_skips_installed`) |
| other packs unchanged | Task 2 + Task 3 |
| trusted omx URL / name only | Task 1 `is_omx_pack` |
| quickstart prompt default No, Yes = pack + CLI | Task 4 |
| `--force` no ask no omx | Task 4 |
| no npm / npm fail / timeout → pack success, warn, exit 0 | Task 1 |
| npm ok but `omx` not on PATH → hint | Task 1 `_prefix_bin_hint` |
| `omx` already on PATH → skip npm | Task 1 |
| no `omx setup`, no allowScripts | Task 1 implementation |
| no doctor check | (out of scope, no task) |
| docs + changelog | Task 5 |
| no live npm in CI | all tests mock which/subprocess |

No placeholders remain. Names are consistent: `ensure_omx_cli`, `OmxCliResult.status` ∈ `{present, installed, skipped_no_npm, failed}`, `is_omx_pack`, `install_omx`.
