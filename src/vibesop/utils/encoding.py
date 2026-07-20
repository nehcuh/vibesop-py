"""Encoding helpers for reading user-managed config files.

User-managed files (e.g. ``~/.vibe/config.toml``) may have been edited on
Windows with an editor that saves in the locale encoding (GBK on zh-CN)
instead of UTF-8. These helpers try strict UTF-8 first and fall back to
the locale-preferred encoding with a warning, so such files keep loading
instead of failing with ``UnicodeDecodeError``.

Project-owned files should NOT use these helpers — they are always written
as UTF-8 and should be read with an explicit ``encoding="utf-8"``.
"""

from __future__ import annotations

import locale
import logging
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _strip_bom(text: str) -> str:
    """Strip a leading UTF-8 BOM (``\\ufeff``) if present.

    Windows editors (Notepad, some PowerShell redirections) often insert a BOM
    at the start of UTF-8 files.  Stripping it here keeps downstream parsers
    (``tomllib``, ``yaml.safe_load``) from rejecting the content.
    """
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def read_text_with_fallback(path: Path) -> str:
    """Read a text file as UTF-8, falling back to the locale encoding.

    A leading UTF-8 BOM is stripped automatically so that downstream
    consumers (TOML / YAML parsers) do not see invalid leading bytes.

    Args:
        path: Path to the text file

    Returns:
        Decoded file content (BOM-stripped)

    Raises:
        OSError: If the file cannot be read
        UnicodeDecodeError: If the file decodes as neither UTF-8 nor the
            locale-preferred encoding
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fallback = locale.getpreferredencoding()
        logger.warning(
            "%s is not UTF-8 encoded; decoded with locale encoding %r. "
            "Consider converting the file to UTF-8.",
            path,
            fallback,
        )
        text = raw.decode(fallback)
    return _strip_bom(text)


def load_toml_with_fallback(path: Path) -> dict[str, Any]:
    """Load a TOML file as UTF-8, falling back to the locale encoding.

    Strips a leading UTF-8 BOM (``\\ufeff``) if present — Windows editors
    (Notepad, some PowerShell redirections) often insert one, and
    ``tomllib`` rejects it as invalid syntax at line 1 column 1.

    Args:
        path: Path to the TOML file

    Returns:
        Parsed TOML data

    Raises:
        OSError: If the file cannot be read
        UnicodeDecodeError: If the file decodes as neither UTF-8 nor the
            locale-preferred encoding
        tomllib.TOMLDecodeError: If the content is not valid TOML
    """
    text = read_text_with_fallback(path)
    # Strip UTF-8 BOM — common on Windows when editors save as "UTF-8 with BOM"
    if text.startswith("\ufeff"):
        text = text[1:]
    return tomllib.loads(text)
