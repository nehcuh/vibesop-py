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
            encoding="utf-8",
            errors="replace",
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
    except KeyboardInterrupt:
        return OmxCliResult(
            "failed",
            f"omx CLI install interrupted. Install manually: {_MANUAL}",
        )
    except Exception as exc:
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
