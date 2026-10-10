"""Explicit, best-effort CLI companion for the trusted OMX skill pack."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from vibesop.constants import TRUSTED_PACKS

OMX_NPM_PACKAGE = "oh-my-codex"
OMX_CLI_TIMEOUT_S = 180.0
_MANUAL = "npm install -g oh-my-codex --ignore-scripts"
_WINDOWS = os.name == "nt"
# npm error output is attacker-influenceable (registry/proxy error pages), so
# strip CSI/OSC sequences and remaining C0/DEL controls before echoing it.
_CONTROL_CHARS = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|[\x00-\x08\x0b-\x1f\x7f]"
)


@dataclass(frozen=True)
class OmxCliResult:
    status: Literal["present", "installed", "installed_off_path", "skipped_no_npm", "failed"]
    detail: str
    omx_path: str | None = None


def is_omx_pack(pack_name: str, pack_url: str | None = None) -> bool:
    """An explicit URL must identify the trusted source, even for name ``omx``."""
    if pack_url is not None:
        return pack_url == TRUSTED_PACKS["omx"]
    return pack_name == "omx"


def _which_trusted(name: str) -> str | None:
    """shutil.which, but never trust an executable sitting in the cwd.

    On Windows, shutil.which prepends the current directory to the search
    (CreateProcess semantics), so a hostile checkout could shadow npm/node/omx
    with attacker files (npm.cmd plus node_modules/npm/bin/npm-cli.js looks
    like an ordinary Node project). Reject non-absolute results and any
    executable whose parent directory is the cwd itself.
    """
    found = shutil.which(name)
    if not found:
        return None
    # Accept either path flavor's absolute form: mocked POSIX paths must stay
    # valid when tests run on a Windows host (and vice versa).
    if not (PureWindowsPath(found).is_absolute() or PurePosixPath(found).is_absolute()):
        return None
    candidate = Path(found)
    try:
        parent = os.path.normcase(os.path.realpath(str(candidate.parent)))
        cwd = os.path.normcase(os.path.realpath(str(Path.cwd())))
    except OSError:
        return None
    if parent == cwd:
        return None
    return found


def _npm_argv(npm: str) -> list[str] | None:
    if not _WINDOWS:
        return [npm]
    # Windows npm.cmd is a batch shim, not an executable for shell=False.
    # Invoke its adjacent npm CLI through Node, without a command shell.
    shim_dir = Path(npm).parent
    npm_cli = shim_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    node = _which_trusted("node.exe") or _which_trusted("node")
    if node is None:
        adjacent_node = shim_dir / "node.exe"
        if adjacent_node.is_file():
            node = str(adjacent_node)
    if node is None or not npm_cli.is_file():
        # A native npm.exe shim (e.g. Volta) has no adjacent node_modules but
        # runs fine with shell=False; only batch shims need the indirection.
        if npm.lower().endswith(".exe") and Path(npm).is_file():
            return [npm]
        return None
    return [node, str(npm_cli)]


def _prefix_bin_hint(npm_argv: list[str]) -> str:
    try:
        completed = subprocess.run(
            [*npm_argv, "prefix", "-g"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            shell=False,
        )
        prefix = completed.stdout.strip()
        if completed.returncode != 0 or not prefix:
            return ""
        bin_dir = prefix if _WINDOWS else str(Path(prefix) / "bin")
        return f" Add `{bin_dir}` to PATH (npm prefix -g)."
    except Exception:
        # A diagnostic probe must never undo a successful skill installation.
        return ""


def ensure_omx_cli(*, timeout_s: float = OMX_CLI_TIMEOUT_S) -> OmxCliResult:
    """Ensure CLI presence without lifecycle scripts; ordinary failures never raise."""
    try:
        existing = _which_trusted("omx")
        if existing:
            return OmxCliResult("present", f"omx CLI already on PATH ({existing})", existing)

        npm = _which_trusted("npm")
        if npm is None:
            return OmxCliResult(
                "skipped_no_npm",
                f"omx CLI skipped (npm not found). Install Node >=20, then: {_MANUAL}",
            )
        npm_argv = _npm_argv(npm)
        if npm_argv is None:
            return OmxCliResult(
                "failed",
                f"omx CLI install skipped (cannot safely resolve Node/npm CLI). "
                f"Install manually: {_MANUAL}",
            )

        completed = subprocess.run(
            [*npm_argv, "install", "-g", OMX_NPM_PACKAGE, "--ignore-scripts"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            tail = _CONTROL_CHARS.sub("", "\n".join(completed.stderr.splitlines()[-8:]))
            return OmxCliResult(
                "failed", f"omx CLI install failed. {tail}\nInstall manually: {_MANUAL}"
            )

        omx_path = _which_trusted("omx")
        if omx_path:
            return OmxCliResult("installed", f"omx CLI installed ({omx_path})", omx_path)
        hint = _prefix_bin_hint(npm_argv)
        return OmxCliResult(
            "installed_off_path",
            f"npm installed {OMX_NPM_PACKAGE} but `omx` is not on PATH.{hint} "
            f"Open a new terminal so PATH updates take effect; manual check: {_MANUAL}",
        )
    except subprocess.TimeoutExpired:
        return OmxCliResult("failed", f"omx CLI install timed out. Install manually: {_MANUAL}")
    except KeyboardInterrupt:
        return OmxCliResult("failed", f"omx CLI install interrupted. Install manually: {_MANUAL}")
    except Exception as exc:
        return OmxCliResult(
            "failed", f"omx CLI install failed ({exc}). Install manually: {_MANUAL}"
        )
