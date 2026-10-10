"""Explicit, best-effort CLI companion for the trusted OMX skill pack."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vibesop.constants import TRUSTED_PACKS

OMX_NPM_PACKAGE = "oh-my-codex"
OMX_CLI_TIMEOUT_S = 180.0
_MANUAL = "npm install -g oh-my-codex --ignore-scripts"
_WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class OmxCliResult:
    status: Literal["present", "installed", "skipped_no_npm", "failed"]
    detail: str
    omx_path: str | None = None


def is_omx_pack(pack_name: str, pack_url: str | None = None) -> bool:
    """An explicit URL must identify the trusted source, even for name ``omx``."""
    if pack_url is not None:
        return pack_url == TRUSTED_PACKS["omx"]
    return pack_name == "omx"


def _npm_argv(npm: str) -> list[str] | None:
    if not _WINDOWS:
        return [npm]
    # Windows npm.cmd is a batch shim, not an executable for shell=False.
    # Invoke its adjacent npm CLI through Node, without a command shell.
    shim_dir = Path(npm).parent
    npm_cli = shim_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        adjacent_node = shim_dir / "node.exe"
        if adjacent_node.is_file():
            node = str(adjacent_node)
    if node is None or not npm_cli.is_file():
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
        existing = shutil.which("omx")
        if existing:
            return OmxCliResult("present", f"omx CLI already on PATH ({existing})", existing)

        npm = shutil.which("npm")
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
            tail = "\n".join(completed.stderr.splitlines()[-8:])
            return OmxCliResult(
                "failed", f"omx CLI install failed. {tail}\nInstall manually: {_MANUAL}"
            )

        omx_path = shutil.which("omx")
        if omx_path:
            return OmxCliResult("installed", f"omx CLI installed ({omx_path})", omx_path)
        hint = _prefix_bin_hint(npm_argv)
        return OmxCliResult(
            "failed",
            f"npm installed {OMX_NPM_PACKAGE} but `omx` is not on PATH.{hint} "
            f"Install manually: {_MANUAL}",
        )
    except subprocess.TimeoutExpired:
        return OmxCliResult("failed", f"omx CLI install timed out. Install manually: {_MANUAL}")
    except KeyboardInterrupt:
        return OmxCliResult("failed", f"omx CLI install interrupted. Install manually: {_MANUAL}")
    except Exception as exc:
        return OmxCliResult(
            "failed", f"omx CLI install failed ({exc}). Install manually: {_MANUAL}"
        )
