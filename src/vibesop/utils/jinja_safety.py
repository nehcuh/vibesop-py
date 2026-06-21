"""Jinja2 safety filters for rendering shell / Python / shell-variable contexts.

Background: VibeSOP renders .sh hook scripts and inline Python snippets via
Jinja2. If any user-controllable variable (platform name, hook event name,
skill id, version string) is interpolated into an executable context without
escaping, an attacker who can influence the variable gets code execution.

Three filters cover the contexts we actually use:

- ``shellquote``: wraps a value in single quotes with shell escaping via
  :func:`shlex.quote`. Use for shell-script arguments and bash variable
  assignments. Example: ``{{ platform_name|shellquote }}``.

- ``pyquote``: escapes a value for safe interpolation into a Python
  single-quoted string literal. Use when a rendered shell script embeds a
  ``python3 -c "platform='{{ platform|pyquote }}'"`` block. Newlines and
  carriage returns are rejected because they break out of the one-line
  literal. Example: ``{{ platform|pyquote }}``.

- ``shellvar``: reduces a value to ``[A-Za-z0-9_-]`` only — the strictest
  filter, suitable for shell variable names, identifiers, version strings,
  and filesystem path components where no quoting is acceptable. Example:
  ``{{ version|shellvar }}``.

- ``safe_text``: strips shell-breaking characters (``; & | $ ` > <``) and
  control chars (newline, CR, NUL) but keeps spaces, dots, and other
  punctuation. Use for display contexts where readability matters and the
  value never reaches an executable position (comments, log headers, banner
  strings). Example: ``{{ platform_name|safe_text }}``.

Usage::

    from vibesop.utils.jinja_safety import make_shell_safe_env

    env = make_shell_safe_env(
        loader=FileSystemLoader(template_dir),
        trim_blocks=True,
    )

The factory preserves any kwargs the caller passes (loader, trim_blocks,
lstrip_blocks, etc.) and only adds the three filters and a ``finalize``
hook that converts ``None`` to empty string.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from jinja2 import Environment

__all__ = [
    "make_shell_safe_env",
    "pyquote",
    "safe_text",
    "shellquote",
    "shellvar",
]


# Matches anything that is not a shell-safe identifier character. Used by
# ``shellvar`` to strip everything else. Underscore and hyphen are allowed
# because real platform identifiers ("claude-code", "kimi-cli") use them.
_SHELLVAR_INVALID = re.compile(r"[^A-Za-z0-9_-]+")


# Shell-breaking chars + control chars stripped by ``safe_text``. Newlines
# and CR are included because a newline in a comment would terminate the
# comment and expose any following text to shell parsing. NUL is included
# because it terminates C strings unexpectedly. The metacharacters
# ``; & | $ ` > < "`` would allow an attacker who controls the value to
# inject commands even inside a "comment" or double-quoted echo argument
# if the surrounding context were ever promoted to an executable line by
# future refactoring. Double-quote is included so the filter is safe inside
# ``echo "[{{ x|safe_text }}]"`` without further escaping.
_SAFE_TEXT_INVALID = re.compile(r"[;&|$\x60<>\"\n\r\x00]")


def shellquote(value: Any) -> str:
    """Quote ``value`` for safe interpolation into a shell context.

    Equivalent to :func:`shlex.quote`. Empty string becomes ``''`` rather
    than the empty output that an unquoted ``{{ var }}`` would produce —
    the latter silently breaks ``cmd $ARG`` semantics.

    Args:
        value: Any value coercible to ``str``.

    Returns:
        Shell-quoted string safe for use as a single shell token.
    """
    return shlex.quote(str(value) if value is not None else "")


def pyquote(value: Any) -> str:
    """Escape ``value`` for safe interpolation into a Python single-quoted
    string literal.

    Backslash and single quote are escaped. Newlines, carriage returns,
    and NUL bytes are rejected with :class:`ValueError` because they
    break out of a single-line ``'...'`` literal in the rendered Python.

    Args:
        value: Any value coercible to ``str``.

    Returns:
        String safe to embed between a pair of single quotes in Python
        source code (the quotes themselves are NOT added).
    """
    if value is None:
        return ""
    text = str(value)
    # Reject characters that break out of the literal. Use the C0 control
    # range minus tab (0x09) which is sometimes legitimate; LF / CR / NUL
    # are always hostile here.
    for hostile in ("\n", "\r", "\x00"):
        if hostile in text:
            raise ValueError(
                f"pyquote: value contains {hostive_name(hostile)!r} — "
                "cannot safely embed in Python single-quoted literal"
            )
    # Order matters: escape backslash first, then single quote.
    return text.replace("\\", "\\\\").replace("'", "\\'")


def shellvar(value: Any) -> str:
    """Reduce ``value`` to ``[A-Za-z0-9_-]+`` only.

    Use for variables that must be safe as shell identifiers, version
    strings, or filesystem path components where no quoting is acceptable.
    Empty input becomes ``"_"`` to avoid producing an empty token.
    """
    if value is None:
        return "_"
    text = str(value)
    cleaned = _SHELLVAR_INVALID.sub("_", text)
    return cleaned or "_"


def safe_text(value: Any) -> str:
    """Strip shell-breaking and control characters from ``value``.

    Use for display contexts where the value never reaches an executable
    position (comments, log headers, banner strings). Unlike ``shellquote``
    (which adds wrapping quotes) and ``shellvar`` (which mangles to
    identifier-only), ``safe_text`` preserves spaces, dots, and ordinary
    punctuation — only the genuinely hostile characters are stripped.

    Args:
        value: Any value coercible to ``str``.

    Returns:
        Value with ``; & | $ ` > <`` and control chars (newline, CR, NUL)
        removed. Empty input returns empty string.
    """
    if value is None:
        return ""
    return _SAFE_TEXT_INVALID.sub("", str(value))


def hostive_name(char: str) -> str:
    """Human-readable name for a control character used in error messages."""
    return {
        "\n": "newline",
        "\r": "carriage return",
        "\x00": "NUL byte",
    }.get(char, repr(char))


def make_shell_safe_env(**kwargs: Any) -> Environment:
    """Build a Jinja2 ``Environment`` with shellquote / pyquote / shellvar
    filters registered.

    Args:
        **kwargs: Forwarded to :class:`jinja2.Environment`. Common kwargs:
            ``loader``, ``trim_blocks``, ``lstrip_blocks``, ``autoescape``.

    Returns:
        Configured Jinja2 environment. ``None`` values rendered by
        ``{{ var }}`` are converted to empty string (the conventional
        behavior for shell / config templates).
    """
    # finalize converts None → "" so {{ missing_var }} does not render
    # the literal string "None" into a shell script.
    kwargs.setdefault("finalize", lambda v: "" if v is None else v)
    env = Environment(**kwargs)
    env.filters["shellquote"] = shellquote
    env.filters["pyquote"] = pyquote
    env.filters["shellvar"] = shellvar
    env.filters["safe_text"] = safe_text
    return env
