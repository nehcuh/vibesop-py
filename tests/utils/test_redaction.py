"""Tests for utils/redaction.py — PII / secret redaction before persistence."""

import json

from vibesop.utils.redaction import contains_sensitive, redact_sensitive


def test_redacts_email() -> None:
    out = redact_sensitive("contact alice@corp.com for details")
    assert "alice@corp.com" not in out
    assert "[REDACTED_EMAIL]" in out


def test_redacts_sk_key() -> None:
    out = redact_sensitive("my openai key is sk-" + "a" * 24 + " done")
    assert "sk-" + "a" * 24 not in out
    assert "[REDACTED_KEY]" in out
    assert "done" in out  # surrounding text preserved


def test_redacts_github_token() -> None:
    token = "ghp_" + "0" * 36
    out = redact_sensitive(f"GH token: {token}")
    assert token not in out
    assert "[REDACTED_TOKEN]" in out


def test_redacts_secret_assignment_keeps_label() -> None:
    """`api_key=VALUE` → label preserved, only VALUE redacted.

    (VALUE is deliberately not sk-/gh-prefixed so the SECRET pattern — not KEY —
    handles it, exercising the value-only redaction path.)
    """
    out = redact_sensitive('config: api_key = "livekey1234567890ab"')
    assert "livekey1234567890ab" not in out
    assert "[REDACTED_SECRET]" in out
    assert "api_key" in out  # the label is retained for readability


def test_redacts_bearer_authorization_header() -> None:
    out = redact_sensitive("Authorization: Bearer abcdef1234567890123")
    assert "abcdef1234567890123" not in out
    assert "[REDACTED_SECRET]" in out
    assert "Bearer" in out  # the scheme name is retained


def test_redacts_home_path_unix() -> None:
    out = redact_sensitive("check /Users/bob/secret/file and /home/alice/.ssh")
    assert "/Users/bob" not in out
    assert "/home/alice" not in out
    # The tail of the path must not leak either — only the placeholder remains.
    assert "/secret/file" not in out
    assert ".ssh" not in out
    assert "[REDACTED_PATH]" in out


def test_redacts_home_path_windows() -> None:
    """T2-a (Kimi review): Windows home paths are redacted too."""
    out = redact_sensitive(r"check C:\Users\bob\secrets\file")
    assert r"C:\Users\bob" not in out
    assert "secrets" not in out
    assert "[REDACTED_PATH]" in out


def test_redacts_base64_bearer_token() -> None:
    """T2-a (Kimi review): base64 bearer tokens (containing +/=) are redacted."""
    out = redact_sensitive("Authorization: Bearer dXNlcjpwYXNzd29yZA==")
    assert "dXNlcjpwYXNzd29yZA==" not in out
    assert "[REDACTED_SECRET]" in out


def test_combined_redaction_in_realistic_query() -> None:
    q = (
        "Email support@acme.io — my key sk-ABCDEFGHIJKLMNOPQRSTUVWX123 is in "
        "/Users/me/.config/creds and the CI token is ghp_" + "a" * 36
    )
    out = redact_sensitive(q)
    assert "support@acme.io" not in out
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX123" not in out
    assert "/Users/me" not in out
    assert "ghp_" + "a" * 36 not in out
    # Structural words preserved
    assert "Email" in out
    assert "CI token" in out


def test_non_sensitive_text_unchanged() -> None:
    msg = "how do I test my python code for the auth module"
    assert redact_sensitive(msg) == msg


def test_empty_and_none_safe() -> None:
    assert redact_sensitive("") == ""


def test_contains_sensitive_detects_without_modifying() -> None:
    assert contains_sensitive("reach me at alice@corp.com") is True
    assert contains_sensitive("how do I test my code") is False
    assert contains_sensitive("") is False


def test_does_not_false_positive_on_short_hex() -> None:
    """A short hex string (e.g. a uuid prefix) must not be flagged as a key."""
    # 12-char hex is not an sk-/gh-/email/path — should be left alone.
    short = "commit abc123def456"
    assert redact_sensitive(short) == short


# --- gate41 项 2: narrowed PATH regex must not corrupt JSON-serialised text ---


def test_json_path_at_value_end_does_not_swallow_closing_quote() -> None:
    """Path as the last chars of a JSON string value: the closing quote survives."""
    text = json.dumps({"cmd": "cd /home/bob/project"}, ensure_ascii=False)
    out = redact_sensitive(text)
    assert "/home/bob" not in out
    assert json.loads(out) == {"cmd": "cd [REDACTED_PATH]"}


def test_json_path_mid_value_does_not_swallow_quote_or_comma() -> None:
    """Path mid-string with following keys: quote, comma and next key survive."""
    text = json.dumps({"a": "/Users/alice/x", "k": 1}, ensure_ascii=False)
    out = redact_sensitive(text)
    assert "/Users/alice" not in out
    assert json.loads(out) == {"a": "[REDACTED_PATH]", "k": 1}


def test_cmspark_escaped_quote_pair_after_path_stays_parseable() -> None:
    """cmspark live shape: path followed by a \\" escaped-quote pair inside JSON."""
    text = json.dumps({"query": 'WF="/Users/huchen/Projects/x" done'}, ensure_ascii=False)
    assert '\\"' in text  # the escaped-quote pair the old \\S* used to swallow
    out = redact_sensitive(text)
    assert "/Users/huchen" not in out
    assert json.loads(out) == {"query": 'WF="[REDACTED_PATH]" done'}


def test_windows_raw_text_path_still_redacted() -> None:
    """Narrowing must not regress raw-text Windows paths."""
    out = redact_sensitive(r"open C:\Users\bob\Desktop now")
    assert r"C:\Users\bob" not in out
    assert "Desktop" not in out
    assert "[REDACTED_PATH]" in out
    assert " now" in out


def test_secret_key_in_serialised_json_still_matched() -> None:
    """`"api_key": "sk-…16+"` inside serialised JSON is redacted, JSON stays valid."""
    key = "sk-" + "a" * 20
    text = json.dumps({"api_key": key}, ensure_ascii=False)
    out = redact_sensitive(text)
    assert key not in out
    assert "[REDACTED_KEY]" in out
    parsed = json.loads(out)
    assert parsed["api_key"] == "[REDACTED_KEY]"


def test_secret_non_prefixed_value_needs_json_context() -> None:
    """gate41 pi N3: a SECRET value WITHOUT the sk- prefix only matches via the
    `"api_key": "…"` JSON context — this is the case the post-serialisation
    pass (layer c) uniquely covers; the KEY pattern cannot see it."""
    value = "some16charvaluenotsk"
    text = json.dumps({"api_key": value}, ensure_ascii=False)
    out = redact_sensitive(text)
    assert value not in out
    assert "[REDACTED_SECRET]" in out
    parsed = json.loads(out)
    assert parsed["api_key"] == "[REDACTED_SECRET]"
