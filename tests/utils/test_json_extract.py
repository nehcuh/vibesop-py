"""Tests for the balanced-brace JSON extraction helper."""

from vibesop.utils.json_extract import extract_first_json_object


def test_flat_object():
    assert extract_first_json_object('{"a": 1}') == '{"a": 1}'


def test_nested_object_not_truncated():
    """Regression for F-48: ``\\{[^{}]*\\}`` returned only the inner ``{"a": 1}``."""
    text = '{"name": "x", "steps": {"a": 1}}'
    assert extract_first_json_object(text) == text


def test_array_of_objects():
    text = '{"tasks": [{"intent": "a"}, {"intent": "b"}]}'
    assert extract_first_json_object(text) == text


def test_markdown_fence_json():
    text = 'Here you go:\n```json\n{"name": "x", "steps": {"a": 1}}\n```\n'
    assert extract_first_json_object(text) == '{"name": "x", "steps": {"a": 1}}'


def test_markdown_fence_bare():
    text = '```\n{"a": 1}\n```'
    assert extract_first_json_object(text) == '{"a": 1}'


def test_object_surrounded_by_prose():
    text = 'Sure! {"skill": "code-review", "confidence": 0.9} Hope that helps.'
    assert extract_first_json_object(text) == '{"skill": "code-review", "confidence": 0.9}'


def test_first_of_multiple_objects():
    text = '{"first": 1} and then {"second": 2}'
    assert extract_first_json_object(text) == '{"first": 1}'


def test_no_braces_returns_none():
    assert extract_first_json_object("no json here") is None


def test_unbalanced_returns_none():
    assert extract_first_json_object('{"a": 1') is None


def test_close_brace_inside_string_value():
    """Regression (Kimi review): a `}` inside a JSON string must not end the object.

    The naive depth tracker returned `{"name": "}` for this input (truncated).
    """
    text = '{"name": "}", "steps": {"a": 1}}'
    assert extract_first_json_object(text) == text


def test_open_brace_inside_string_value():
    """Symmetric to the above: `{` inside a string must not inflate depth."""
    text = '{"prompt": "if (x) { return; }", "ok": true}'
    assert extract_first_json_object(text) == text


def test_escaped_quote_inside_string():
    """An escaped `\"` does not terminate the string."""
    text = '{"msg": "she said \\"hi}\\""}'
    assert extract_first_json_object(text) == text
