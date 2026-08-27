"""Shared hook-command parsing for adapters and the verify CLI.

Lenient basename classification keeps every vibesop hook command visible
to verify (any platform, any quoting); the strict parser only feeds the
legacy rewrite, where uncertainty means "leave the command untouched".
"""

from __future__ import annotations

import shlex
import string
import sys

__all__ = [
    "VIBESOP_HOOK_SCRIPT_BASENAMES",
    "classify_vibesop_hook_command",
    "command_basenames",
    "parse_hook_script_command",
    "unwrap_token",
]

VIBESOP_HOOK_SCRIPT_BASENAMES = frozenset(
    {
        "vibesop-route.sh",
        "vibesop-tool-seq.sh",
        "vibesop-track.sh",
        "vibesop-mirror-prompt.sh",
        "vibesop-mirror-session-end.sh",
    }
)

# Allowlist: a denylist kept missing injection characters (backtick, %, ^)
# and accepted Unicode drive letters. Windows drive letters are A-Z only.
_PATH_ALLOWED = frozenset(string.ascii_letters + string.digits + "._/+-:")


def unwrap_token(tok: str) -> str:
    """Strip a paired double quote; other edge quotes are left to ``strip``."""
    if len(tok) >= 2 and tok[0] == tok[-1] == '"':
        return tok[1:-1]
    return tok


def command_basenames(cmd: str) -> set[str]:
    """Lowercased basenames of all whitespace tokens, over-stripping edge quotes.

    Over-stripping and case-folding are fail-safe: they can only pull extra
    commands into the unsafe scan, never hide one. ``split()`` + ``strip()``
    handles double- and single-quoted spaced paths (win32 "First Last"
    homes); ``shlex`` with ``posix=False`` keeps quote characters, so the
    basename of a quoted spaced path would keep its trailing quote and miss
    the basename whitelist.
    """
    return {
        unwrap_token(t).strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
        for t in cmd.split()
    }


def classify_vibesop_hook_command(cmd: str) -> bool:
    """True when any token basename is a vibesop hook script (platform-agnostic)."""
    return bool(command_basenames(cmd) & VIBESOP_HOOK_SCRIPT_BASENAMES)


def _is_double_quoted(tok: str) -> bool:
    return len(tok) >= 2 and tok[0] == tok[-1] == '"'


def _normalize_script_token(raw: str, *, quoted: bool) -> str | None:
    """Normalize a vibesop hook script token, or None if confidence is low."""
    norm = raw.replace("\\", "/")
    allowed = _PATH_ALLOWED | ({" "} if quoted else set())
    if not norm.lower().endswith(".sh"):
        return None
    if not norm or any(ch not in allowed for ch in norm):
        return None
    basename = norm.rsplit("/", 1)[-1]
    if basename not in VIBESOP_HOOK_SCRIPT_BASENAMES:
        return None
    win_abs = (
        len(norm) >= 3 and norm[0] in string.ascii_letters and norm[1] == ":" and norm[2] == "/"
    )
    posix_abs = norm.startswith("/")
    relative_hooks = norm.startswith("hooks/") and "/" not in norm[6:]
    if relative_hooks:
        return norm
    if not (posix_abs or win_abs):
        return None
    if sys.platform != "win32" and win_abs:
        return None
    if sys.platform == "win32" and posix_abs and not win_abs:
        return None
    return norm


def parse_hook_script_command(cmd: str) -> str | None:
    """Parse a vibesop hook command into a normalized POSIX script path.

    Accepts ``<bash> <script>`` (legacy) and a single script token (quoted
    absolute, unquoted absolute, or config-relative ``hooks/<name>.sh``).

    Returns None whenever confidence is low: wrong token count, non-bash
    interpreter, characters outside the allowlist, non-absolute or
    foreign-platform path forms, or a script outside the vibesop allowlist.
    Callers must treat None as "do not rewrite".
    """
    try:
        raw_tokens = shlex.split(cmd, posix=False)
    except ValueError:
        return None
    tokens = [unwrap_token(t) for t in raw_tokens]
    if len(tokens) == 1:
        return _normalize_script_token(tokens[0], quoted=_is_double_quoted(raw_tokens[0]))
    if len(tokens) != 2:
        return None
    interp, raw = tokens
    interp_n = interp.replace("\\", "/").lower()
    if interp_n not in ("bash", "bash.exe") and not interp_n.endswith("/bash.exe"):
        return None
    if sys.platform != "win32" and interp_n != "bash":
        return None
    return _normalize_script_token(raw, quoted=_is_double_quoted(raw_tokens[1]))
