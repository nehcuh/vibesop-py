"""SpanWriter three-layer redact — gate41 项 2.

End-to-end: write a span whose input_data/output_data/metadata carry paths
and secrets, read the JSONL back line by line, and verify every line (and
the re-parsed payload strings) is valid JSON with the sensitive substrings
redacted. Regression target: the pre-gate41 PATH regex (``\\S*``) swallowed
closing quotes in serialised JSON, making whole span lines unparseable.
"""

from __future__ import annotations

import json
from pathlib import Path

from vibesop.core.observability.models import Span
from vibesop.core.observability.span_writer import SpanWriter, _redact_structure


def _make_span(**overrides: object) -> Span:
    fields: dict = {
        "id": "test-span",
        "trace_id": "test-trace",
        "name": "redact-test",
        "span_kind": "task",
        "agent_id": "test-agent",
        "status": "ok",
    }
    fields.update(overrides)
    return Span(**fields)


def _read_lines(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestRedactStructure:
    def test_redacts_str_leaves_in_dicts_and_lists(self) -> None:
        value = {
            "cmd": "cd /Users/bob/proj",
            "nested": {"win": r"C:\Users\bob\Desktop"},
            "items": ["/home/alice/.ssh", 1, None, True],
        }
        out = _redact_structure(value)
        assert out == {
            "cmd": "cd [REDACTED_PATH]",
            "nested": {"win": "[REDACTED_PATH]"},
            "items": ["[REDACTED_PATH]", 1, None, True],
        }

    def test_non_container_types_pass_through_unchanged(self) -> None:
        assert _redact_structure(42) == 42
        assert _redact_structure(3.14) == 3.14
        assert _redact_structure(None) is None
        assert _redact_structure(True) is True

    def test_path_in_dict_key_is_redacted(self) -> None:
        """gate41 pi N1: paths in keys must not survive — layer (c) cannot
        match the doubled-backslash serialised form of a Windows key."""
        out = _redact_structure({r"C:\Users\bob\secretfile": "v", "/Users/bob/k": "w"})
        assert out == {"[REDACTED_PATH]": "w"}

    def test_semantic_dict_keys_survive(self) -> None:
        """Well-formed metadata keys never match the redaction patterns."""
        value = {"query": "q", "skill_id": "s", "has_match": True, "confidence": 0.8}
        out = _redact_structure(value)
        assert set(out) == {"query", "skill_id", "has_match", "confidence"}


class TestWriteSpanRedaction:
    def test_metadata_paths_redacted_and_line_parseable(self, tmp_path: Path) -> None:
        writer = SpanWriter(storage_path=tmp_path / "spans.jsonl")
        span = _make_span(
            metadata={
                "cmd": "cd /Users/huchen/Projects/x",
                "win": r"C:\Users\bob\Desktop",
                "n": 42,
            }
        )
        writer.write_span(span)

        (record,) = _read_lines(writer._path)
        metadata = json.loads(record["metadata"])
        assert metadata == {
            "cmd": "cd [REDACTED_PATH]",
            "win": "[REDACTED_PATH]",
            "n": 42,
        }

    def test_cmspark_shape_escaped_quote_pair_stays_parseable(self, tmp_path: Path) -> None:
        """Live cmspark shape: query holds a WF=\"/Users/huchen/…\" escaped pair."""
        writer = SpanWriter(storage_path=tmp_path / "spans.jsonl")
        span = _make_span(metadata={"query": 'WF="/Users/huchen/Projects/vibesop-py" fix'})
        writer.write_span(span)

        (record,) = _read_lines(writer._path)
        metadata = json.loads(record["metadata"])
        assert metadata == {"query": 'WF="[REDACTED_PATH]" fix'}

    def test_input_output_data_secret_redacted_and_parseable(self, tmp_path: Path) -> None:
        key = "sk-" + "a" * 20
        writer = SpanWriter(storage_path=tmp_path / "spans.jsonl")
        span = _make_span(
            input_data={"query": "open /home/bob/file"},
            output_data={"api_key": key, "result": "ok"},
        )
        writer.write_span(span)

        (record,) = _read_lines(writer._path)
        input_data = json.loads(record["input_data"])
        output_data = json.loads(record["output_data"])
        assert input_data == {"query": "open [REDACTED_PATH]"}
        assert key not in record["output_data"]
        assert output_data["api_key"] == "[REDACTED_KEY]"
        assert output_data["result"] == "ok"

    def test_multiple_spans_all_lines_parseable(self, tmp_path: Path) -> None:
        writer = SpanWriter(storage_path=tmp_path / "spans.jsonl")
        writer.write_span(_make_span(id="s1", metadata={"p": "/Users/a/b"}))
        writer.write_span(_make_span(id="s2", metadata={"p": r"C:\Users\c\d"}))

        records = _read_lines(writer._path)
        assert [r["id"] for r in records] == ["s1", "s2"]
        for record in records:
            assert json.loads(record["metadata"]) == {"p": "[REDACTED_PATH]"}
