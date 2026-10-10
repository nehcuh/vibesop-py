"""CLI companion tests: no real npm installation or lifecycle execution."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from vibesop.constants import TRUSTED_PACKS
from vibesop.installer import omx_cli


@pytest.fixture(autouse=True)
def default_posix(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name != "test_native_windows_node_shim_executes_without_network":
        monkeypatch.setattr(omx_cli, "_WINDOWS", False)


@pytest.mark.parametrize(
    ("name", "url", "expected"),
    [
        ("omx", None, True),
        ("other", None, False),
        ("oh-my-codex", TRUSTED_PACKS["omx"], True),
        ("omx", "https://github.com/unrelated-owner/omx", False),
        ("omx", TRUSTED_PACKS["omx"] + "/", False),
    ],
)
def test_trusted_source_identity(name: str, url: str | None, expected: bool) -> None:
    assert omx_cli.is_omx_pack(name, url) is expected


def test_present_cli_does_not_install() -> None:
    with (
        patch.object(omx_cli.shutil, "which", return_value="/bin/omx"),
        patch.object(omx_cli.subprocess, "run") as run,
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "present"
    assert result.omx_path == "/bin/omx"
    run.assert_not_called()


def test_missing_npm_does_not_spawn() -> None:
    with (
        patch.object(omx_cli.shutil, "which", return_value=None),
        patch.object(omx_cli.subprocess, "run") as run,
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "skipped_no_npm"
    assert "Node >=20" in result.detail
    assert "--ignore-scripts" in result.detail
    run.assert_not_called()


def test_install_disables_scripts_and_shell() -> None:
    with (
        patch.object(omx_cli.shutil, "which", side_effect=[None, "/bin/npm", "/bin/omx"]),
        patch.object(
            omx_cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")
        ) as run,
    ):
        result = omx_cli.ensure_omx_cli(timeout_s=23)
    assert result.status == "installed"
    assert result.omx_path == "/bin/omx"
    assert run.call_args.args[0] == ["/bin/npm", "install", "-g", "oh-my-codex", "--ignore-scripts"]
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == 23
    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired("npm", 180),
        OSError("npm unavailable"),
        RuntimeError("unexpected npm error"),
        KeyboardInterrupt(),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
    ],
)
def test_install_failures_do_not_raise(error: BaseException) -> None:
    with (
        patch.object(omx_cli.shutil, "which", side_effect=[None, "/bin/npm"]),
        patch.object(omx_cli.subprocess, "run", side_effect=error),
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert "npm install -g oh-my-codex --ignore-scripts" in result.detail


def test_path_discovery_error_is_best_effort() -> None:
    with patch.object(omx_cli.shutil, "which", side_effect=OSError("bad PATH")):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"


def test_nonzero_install_preserves_diagnostic_tail() -> None:
    completed = subprocess.CompletedProcess([], 1, "", "permission denied [broken-tag]")
    with (
        patch.object(omx_cli.shutil, "which", side_effect=[None, "/bin/npm"]),
        patch.object(omx_cli.subprocess, "run", return_value=completed),
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert "permission denied [broken-tag]" in result.detail


@pytest.mark.parametrize("prefix_error", [False, True])
def test_prefix_failure_cannot_escape(prefix_error: bool) -> None:
    probe = (
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        if prefix_error
        else subprocess.CompletedProcess([], 1, "/ignored-prefix", "prefix failed")
    )
    with (
        patch.object(omx_cli.shutil, "which", side_effect=[None, "/bin/npm", None]),
        patch.object(
            omx_cli.subprocess,
            "run",
            side_effect=[subprocess.CompletedProcess([], 0, "", ""), probe],
        ) as run,
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert "not on PATH" in result.detail
    assert "ignored-prefix" not in result.detail
    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"


def test_posix_prefix_bin_hint() -> None:
    with (
        patch.object(omx_cli.shutil, "which", side_effect=[None, "/bin/npm", None]),
        patch.object(
            omx_cli.subprocess,
            "run",
            side_effect=[
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "/opt/npm-global\n", ""),
            ],
        ),
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert str(Path("/opt/npm-global") / "bin") in result.detail


def test_windows_node_executes_actual_adjacent_npm_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omx_cli, "_WINDOWS", True)
    shim = tmp_path / "Node With Spaces" / "npm.cmd"
    npm_script = shim.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    npm_script.parent.mkdir(parents=True)
    npm_script.write_text("// fixture only", encoding="utf-8")
    node = str(shim.parent / "node.exe")
    paths = {"npm": str(shim), "node.exe": node}
    prefix = r"C:\Users\alice\AppData\Roaming\npm"
    with (
        patch.object(omx_cli.shutil, "which", side_effect=paths.get),
        patch.object(
            omx_cli.subprocess,
            "run",
            side_effect=[
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, prefix + "\n", ""),
            ],
        ) as run,
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert f"`{prefix}`" in result.detail
    assert prefix + "/bin" not in result.detail
    assert run.call_args_list[0].args[0] == [
        node,
        str(npm_script),
        "install",
        "-g",
        "oh-my-codex",
        "--ignore-scripts",
    ]
    assert run.call_args_list[1].args[0] == [node, str(npm_script), "prefix", "-g"]
    assert all(call.kwargs["shell"] is False for call in run.call_args_list)
    assert all(str(shim) not in call.args[0] for call in run.call_args_list)


@pytest.mark.parametrize("missing", ["node", "npm_cli"])
def test_windows_unresolved_runtime_does_not_execute_cmd(
    missing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omx_cli, "_WINDOWS", True)
    shim = tmp_path / "npm.cmd"
    npm_script = tmp_path / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if missing != "npm_cli":
        npm_script.parent.mkdir(parents=True)
        npm_script.write_text("// fixture only", encoding="utf-8")
    paths = {"npm": str(shim)}
    if missing != "node":
        paths["node.exe"] = str(tmp_path / "node.exe")
    with (
        patch.object(omx_cli.shutil, "which", side_effect=paths.get),
        patch.object(omx_cli.subprocess, "run") as run,
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert "cannot safely resolve" in result.detail
    assert "--ignore-scripts" in result.detail
    run.assert_not_called()


def test_windows_adjacent_node_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(omx_cli, "_WINDOWS", True)
    node = tmp_path / "node.exe"
    node.write_bytes(b"fixture, not executed")
    npm_script = tmp_path / "node_modules" / "npm" / "bin" / "npm-cli.js"
    npm_script.parent.mkdir(parents=True)
    npm_script.write_text("// fixture only", encoding="utf-8")
    with (
        patch.object(omx_cli.shutil, "which", side_effect={"npm": str(tmp_path / "npm.cmd")}.get),
        patch.object(
            omx_cli.subprocess,
            "run",
            side_effect=[
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, str(tmp_path), ""),
            ],
        ) as run,
    ):
        result = omx_cli.ensure_omx_cli()
    assert result.status == "failed"
    assert run.call_args_list[0].args[0][:2] == [str(node), str(npm_script)]
    assert run.call_args_list[0].kwargs["shell"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows Node execution")
def test_native_windows_node_shim_executes_without_network(tmp_path: Path) -> None:
    """Execute real Node through the Windows resolver, with only scratch writes."""
    real_which = shutil.which
    assert real_which("node.exe") is not None, "native Windows verification requires Node.js"
    shim_dir = tmp_path / "Native Node With Spaces"
    npm_cmd = shim_dir / "npm.cmd"
    npm_script = shim_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    npm_script.parent.mkdir(parents=True)
    npm_cmd.write_text("@echo off\nexit /b 77\n", encoding="utf-8")
    invocation_file = shim_dir / "invocation.json"
    omx_cmd = shim_dir / "omx.cmd"
    npm_script.write_text(
        'const fs = require("node:fs");\n'
        'const path = require("node:path");\n'
        'const root = path.resolve(__dirname, "../../..");\n'
        'fs.writeFileSync(path.join(root, "invocation.json"), '
        "JSON.stringify(process.argv.slice(2)));\n"
        'fs.writeFileSync(path.join(root, "omx.cmd"), "@echo off\\r\\nexit /b 0\\r\\n");\n',
        encoding="utf-8",
    )

    def controlled_which(name: str) -> str | None:
        if name == "npm":
            return str(npm_cmd)
        if name == "omx":
            return str(omx_cmd) if omx_cmd.is_file() else None
        return real_which(name)

    with patch.object(omx_cli.shutil, "which", side_effect=controlled_which):
        result = omx_cli.ensure_omx_cli(timeout_s=30)
    assert result.status == "installed", result.detail
    assert result.omx_path == str(omx_cmd)
    assert json.loads(invocation_file.read_text(encoding="utf-8")) == [
        "install",
        "-g",
        "oh-my-codex",
        "--ignore-scripts",
    ]
