"""PII / secret redaction for persisted, user-derived text.

VibeSOP persists user-derived data (analytics, traces, preferences, instincts)
to local disk by default. Queries routinely contain PII (emails, usernames,
file paths) and occasionally secrets (pasted API keys / tokens). This module
redacts common sensitive substrings from text *before* it is written to disk,
so a query like::

    "email me at alice@corp.com, my key is sk-abc..., auth: Bearer xyz"

is persisted with the sensitive substrings replaced by ``[REDACTED_<LABEL>]``.

This is intentionally a conservative, regex-based redactor (no ML, no network) —
the goal is to keep obviously-sensitive substrings out of plaintext state
files, not to guarantee complete PII scrubbing. Callers needing stronger
guarantees should layer additional controls.
"""

from __future__ import annotations

import re

# Each entry: (label, compiled pattern). A named ``value`` group marks the
# substring to redact (keeping the surrounding label readable); otherwise the
# whole match is redacted. Order: most-specific secrets first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # API keys with well-known prefixes (OpenAI / Anthropic / Stripe).
    ("KEY", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    # GitHub personal-access / app tokens (ghp_ / gho_ / ghu_ / ghs_ / ghr_).
    ("TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    # `api_key=...`, `token: ...`, `secret=...`, `password: ...` → redact value.
    (
        "SECRET",
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password)\b"
            r"['\"\s]*[:=]\s*['\"]?(?P<value>[A-Za-z0-9_.+/=\-]{12,})"
        ),
    ),
    # `Bearer <token>` / `Authorization: Bearer <token>` → redact the token.
    (
        "SECRET",
        re.compile(r"(?i)\bbearer\s+(?P<value>[A-Za-z0-9_.+/=\-]{16,})"),
    ),
    # Email addresses.
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Home-directory paths (contain the OS username). The entire path segment
    # is redacted — not just the user component — so no tail filenames leak.
    ("PATH", re.compile(r"(?:/Users/|/home/)\S*|C:\\Users\\\S*")),
]


def redact_sensitive(text: str) -> str:
    """Return *text* with common PII / secret patterns replaced by placeholders.

    Conservative regex-based redaction. Empty input is returned as-is. Each
    match is replaced with ``[REDACTED_<LABEL>]`` (the label indicates the kind
    of value redacted, for debuggability, without exposing it).
    """
    if not text:
        return text
    redacted = text
    for label, pattern in _PATTERNS:
        placeholder = f"[REDACTED_{label}]"

        def _replace(m: re.Match[str], ph: str = placeholder) -> str:
            # If the pattern captured a named ``value`` group, redact only that
            # group (keeps the surrounding label like "api_key=" / "Bearer ").
            # Use slice positions (not str.replace) so a value that recurs in
            # the label can't be mis-redacted.
            if "value" in m.groupdict():
                start = m.start("value") - m.start()
                end = m.end("value") - m.start()
                return m.group()[:start] + ph + m.group()[end:]
            return ph

        redacted = pattern.sub(_replace, redacted)
    return redacted


def contains_sensitive(text: str) -> bool:
    """True if *text* matches any redaction pattern (without modifying it).

    Useful as a cheap gate (e.g. warn when a persisted record carries
    redactable material).
    """
    if not text:
        return False
    return any(pattern.search(text) for _label, pattern in _PATTERNS)
