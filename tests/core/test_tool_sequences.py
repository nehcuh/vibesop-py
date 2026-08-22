"""Tests for the P3 tool-sequence capture/assembly module.

Covers ``record_tool_event`` (minimal capture — tool name + timestamp +
session id only, never tool_input), ``assemble_tool_sequences`` (session
grouping, time-window fallback, min-steps threshold, watermark semantics,
fault tolerance), and ``clear_tool_sequences`` (data purge path).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from vibesop.core.instinct import tool_sequences
from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.instinct.tool_sequences import (
    assemble_tool_sequences,
    clear_tool_sequences,
    cursor_path,
    last_capture_path,
    record_tool_event,
    rotated_path,
    sequences_path,
)


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _entry(tool: str, ts: str | None = None, session: str | None = None) -> str:
    return json.dumps({"tool": tool, "ts": ts, "session": session})


class TestRecordToolEvent:
    def test_claude_code_payload_records_minimal_entry(self, tmp_path: Path) -> None:
        payload = {
            "session_id": "sess-1",
            "tool_name": "Read",
            "tool_input": {"file_path": "/secret/prod.pem"},
            "tool_response": {"file": {"content": "TOP SECRET CONTENT"}},
            "hook_event_name": "PostToolUse",
            "cwd": "/tmp",
        }
        assert record_tool_event(payload, tmp_path) is True

        lines = sequences_path(tmp_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["tool"] == "Read"
        assert entry["session"] == "sess-1"
        assert entry["ts"]  # local timestamp generated
        assert set(entry) == {"tool", "ts", "session"}

    def test_tool_input_never_persisted(self, tmp_path: Path) -> None:
        secret = "/secret/prod.pem"
        payload = {"tool_name": "Read", "tool_input": {"file_path": secret}}
        assert record_tool_event(payload, tmp_path) is True
        content = sequences_path(tmp_path).read_text(encoding="utf-8")
        assert secret not in content
        assert "tool_input" not in content

    def test_fallback_tool_key(self, tmp_path: Path) -> None:
        assert record_tool_event({"tool": "Bash"}, tmp_path) is True
        entry = json.loads(sequences_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])
        assert entry["tool"] == "Bash"
        assert entry["session"] is None

    def test_missing_tool_name_dropped(self, tmp_path: Path) -> None:
        assert record_tool_event({"session_id": "s"}, tmp_path) is False
        assert record_tool_event({"tool_name": ""}, tmp_path) is False
        assert record_tool_event({"tool_name": 42}, tmp_path) is False
        assert not sequences_path(tmp_path).exists()

    def test_appends_multiple_events(self, tmp_path: Path) -> None:
        record_tool_event({"tool_name": "Read", "session_id": "s"}, tmp_path)
        record_tool_event({"tool_name": "Edit", "session_id": "s"}, tmp_path)
        assert len(sequences_path(tmp_path).read_text(encoding="utf-8").splitlines()) == 2

    def test_grok_camelcase_payload(self, tmp_path: Path) -> None:
        """gate33 pi BLOCK-1: grok's hook stdin envelope is camelCase
        (toolName/sessionId — grok hooks user guide, "camelCase input");
        before the fix these events were 100% silently dropped."""
        payload = {
            "hookEventName": "post_tool_use",
            "sessionId": "grok-sess",
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "toolName": "run_terminal_command",
            "toolInput": {"command": "npm test"},
            "toolResult": {"output": "secret output"},
        }
        assert record_tool_event(payload, tmp_path) is True
        entry = json.loads(sequences_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])
        assert entry == {
            "tool": "run_terminal_command",
            "ts": entry["ts"],
            "session": "grok-sess",
        }
        assert "secret output" not in sequences_path(tmp_path).read_text(encoding="utf-8")

    def test_success_writes_liveness_heartbeat(self, tmp_path: Path) -> None:
        """gate33 pi MAJOR-2: the pure-CLI path (grok JSON hook) must write
        tool_sequences.last just like the shell-template hooks, or
        ``vibe sequence status`` reports a healthy capture as dead."""
        from vibesop.core.instinct.tool_sequences import last_capture_path

        assert record_tool_event({"tool_name": "Read"}, tmp_path) is True
        heartbeat = last_capture_path(tmp_path)
        assert heartbeat.exists()
        assert heartbeat.read_text(encoding="utf-8").strip().isdigit()

    def test_drop_writes_no_heartbeat(self, tmp_path: Path) -> None:
        from vibesop.core.instinct.tool_sequences import last_capture_path

        assert record_tool_event({"session_id": "s"}, tmp_path) is False
        assert not last_capture_path(tmp_path).exists()


class TestParseTs:
    def test_naive_timestamp_normalized_to_utc(self) -> None:
        """gate16b claude N1: tz-naive capture ts must not crash the bridge."""
        dt = tool_sequences._parse_ts("2026-08-20T10:00:00")
        assert dt is not None and dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)

    def test_aware_timestamp_passthrough(self) -> None:
        dt = tool_sequences._parse_ts("2026-08-20T10:00:00+08:00")
        assert dt is not None and dt.utcoffset() == timedelta(hours=8)

    def test_garbage_returns_none(self) -> None:
        assert tool_sequences._parse_ts("not-a-date") is None
        assert tool_sequences._parse_ts(None) is None
        assert tool_sequences._parse_ts(123) is None


class TestRotation:
    def test_oversized_log_rotates_before_append(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tool_sequences, "MAX_CAPTURE_BYTES", 50)
        _write_lines(  # two ~46-byte lines → over the 50-byte cap
            sequences_path(tmp_path),
            [_entry("Read", session="old"), _entry("Edit", session="old")],
        )

        assert record_tool_event({"tool_name": "Bash", "session_id": "new"}, tmp_path) is True

        rotated = rotated_path(tmp_path).read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["tool"] for line in rotated] == ["Read", "Edit"]
        live = sequences_path(tmp_path).read_text(encoding="utf-8").splitlines()
        assert len(live) == 1
        assert json.loads(live[0])["tool"] == "Bash"

    def test_rotation_overwrites_previous_rotation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tool_sequences, "MAX_CAPTURE_BYTES", 50)
        _write_lines(rotated_path(tmp_path), [_entry("Ancient", session="x")])
        _write_lines(
            sequences_path(tmp_path),
            [_entry("Read", session="old"), _entry("Edit", session="old")],
        )

        assert record_tool_event({"tool_name": "Bash", "session_id": "new"}, tmp_path) is True

        rotated = rotated_path(tmp_path).read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["tool"] for line in rotated] == ["Read", "Edit"]

    def test_under_cap_does_not_rotate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tool_sequences, "MAX_CAPTURE_BYTES", 10**9)
        record_tool_event({"tool_name": "Read", "session_id": "s"}, tmp_path)
        assert not rotated_path(tmp_path).exists()

    def test_rotation_resets_cursor_and_assembly_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        learner = InstinctLearner(storage_path=tmp_path / ".vibe" / "instincts.jsonl")
        _write_lines(
            sequences_path(tmp_path),
            [_entry("Read", session="a"), _entry("Edit", session="a"), _entry("Bash", session="a")],
        )
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1
        assert json.loads(cursor_path(tmp_path).read_text(encoding="utf-8"))["offset"] > 0

        # Live file over the cap → next record rotates it aside and zeroes
        # the watermark so assembly restarts from the fresh file.
        monkeypatch.setattr(tool_sequences, "MAX_CAPTURE_BYTES", 50)
        record_tool_event({"tool_name": "Grep", "session_id": "b"}, tmp_path)
        assert json.loads(cursor_path(tmp_path).read_text(encoding="utf-8"))["offset"] == 0

        # Assembly restarts from the fresh file: the rotated-away "a" entries
        # are not re-fed, and new entries assemble normally.
        with sequences_path(tmp_path).open("a", encoding="utf-8") as f:
            f.write(_entry("Read", session="b") + "\n")
            f.write(_entry("Edit", session="b") + "\n")
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1
        steps_seen = {tuple(p.steps) for p in learner._sequences.values()}
        assert ("Grep", "Read", "Edit") in steps_seen
        pattern_a = next(
            p for p in learner._sequences.values() if tuple(p.steps) == ("Read", "Edit", "Bash")
        )
        assert pattern_a.total_count == 1


class TestStreamingAssembly:
    def test_large_file_assembles_line_by_line(self, tmp_path: Path) -> None:
        # Behavior parity with the previous whole-file read: many sessions
        # sharing one shape fold into a single pattern counted per feed.
        learner = InstinctLearner(storage_path=tmp_path / ".vibe" / "instincts.jsonl")
        lines: list[str] = []
        for i in range(2000):
            lines.extend(_entry(tool, session=f"s-{i}") for tool in ("Read", "Edit", "Bash"))
        _write_lines(sequences_path(tmp_path), lines)

        fed = assemble_tool_sequences(tmp_path, learner=learner)

        assert fed == 2000
        pattern = next(iter(learner._sequences.values()))
        assert pattern.steps == ["Read", "Edit", "Bash"]
        assert pattern.total_count == 2000

    def test_truncated_final_line_skipped(self, tmp_path: Path) -> None:
        learner = InstinctLearner(storage_path=tmp_path / ".vibe" / "instincts.jsonl")
        path = sequences_path(tmp_path)
        _write_lines(
            path,
            [_entry("Read", session="a"), _entry("Edit", session="a"), _entry("Bash", session="a")],
        )
        with path.open("a", encoding="utf-8") as f:
            f.write('{"tool": "Gre')  # crash mid-write: no newline, broken JSON

        assert assemble_tool_sequences(tmp_path, learner=learner) == 1
        # watermark advances past the torn line so it is never retried
        assert json.loads(cursor_path(tmp_path).read_text(encoding="utf-8"))["offset"] > 0


class TestAssembleToolSequences:
    def _learner(self, tmp_path: Path) -> InstinctLearner:
        return InstinctLearner(storage_path=tmp_path / ".vibe" / "instincts.jsonl")

    def test_no_capture_file_returns_zero(self, tmp_path: Path) -> None:
        assert assemble_tool_sequences(tmp_path) == 0
        assert not cursor_path(tmp_path).exists()

    def test_groups_by_session(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        _write_lines(
            sequences_path(tmp_path),
            [
                _entry("Read", session="a"),
                _entry("Write", session="b"),
                _entry("Edit", session="a"),
                _entry("Bash", session="a"),
                _entry("Grep", session="b"),
                _entry("Glob", session="b"),
            ],
        )
        fed = assemble_tool_sequences(tmp_path, learner=learner)
        assert fed == 2
        candidates = learner._sequences
        assert len(candidates) == 2
        steps_seen = {tuple(p.steps) for p in candidates.values()}
        assert ("Read", "Edit", "Bash") in steps_seen
        assert ("Write", "Grep", "Glob") in steps_seen
        # application-only telemetry: never success
        assert all(p.success_count == 0 for p in candidates.values())

    def test_time_window_split_for_sessionless_entries(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        base = "2026-07-18T10:00:00+00:00"
        later = "2026-07-18T10:41:00+00:00"  # >30min after 10:10 → new group
        _write_lines(
            sequences_path(tmp_path),
            [
                _entry("Read", ts=base),
                _entry("Edit", ts="2026-07-18T10:05:00+00:00"),
                _entry("Bash", ts="2026-07-18T10:10:00+00:00"),
                _entry("Grep", ts=later),
                _entry("Glob", ts="2026-07-18T10:45:00+00:00"),
                _entry("Write", ts="2026-07-18T10:50:00+00:00"),
            ],
        )
        fed = assemble_tool_sequences(tmp_path, learner=learner)
        assert fed == 2
        steps_seen = {tuple(p.steps) for p in learner._sequences.values()}
        assert ("Read", "Edit", "Bash") in steps_seen
        assert ("Grep", "Glob", "Write") in steps_seen

    def test_within_window_stays_one_group(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        _write_lines(
            sequences_path(tmp_path),
            [
                _entry("Read", ts="2026-07-18T10:00:00+00:00"),
                _entry("Edit", ts="2026-07-18T10:20:00+00:00"),
                _entry("Bash", ts="2026-07-18T10:29:00+00:00"),
            ],
        )
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1

    def test_min_steps_threshold(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        _write_lines(
            sequences_path(tmp_path),
            [_entry("Read", session="a"), _entry("Edit", session="a")],
        )
        assert assemble_tool_sequences(tmp_path, learner=learner) == 0
        assert learner._sequences == {}
        # watermark still advances past the sub-threshold group
        assert cursor_path(tmp_path).exists()

    def test_watermark_prevents_double_feed(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        path = sequences_path(tmp_path)
        _write_lines(
            path,
            [_entry("Read", session="a"), _entry("Edit", session="a"), _entry("Bash", session="a")],
        )
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1
        # Second run: nothing new → zero fed, total_count stays 1
        assert assemble_tool_sequences(tmp_path, learner=learner) == 0
        pattern = next(iter(learner._sequences.values()))
        assert pattern.total_count == 1
        # New entries after the watermark are picked up
        with path.open("a", encoding="utf-8") as f:
            f.write(_entry("Read", session="a") + "\n")
            f.write(_entry("Edit", session="a") + "\n")
            f.write(_entry("Bash", session="a") + "\n")
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1
        assert pattern.total_count == 2

    def test_bad_lines_skipped(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        _write_lines(
            sequences_path(tmp_path),
            [
                "not json at all",
                json.dumps(["a", "list"]),
                json.dumps({"no_tool": True}),
                _entry("Read", session="a"),
                _entry("Edit", ts="garbage-ts", session="a"),
                _entry("Bash", session="a"),
                "",
            ],
        )
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1

    def test_cursor_beyond_file_size_resets(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        path = sequences_path(tmp_path)
        _write_lines(
            path,
            [_entry("Read", session="a"), _entry("Edit", session="a"), _entry("Bash", session="a")],
        )
        # Stale cursor from before a purge/rotation: larger than the file
        _write_lines(cursor_path(tmp_path), [json.dumps({"offset": 10**9})])
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1

    def test_corrupt_cursor_treated_as_zero(self, tmp_path: Path) -> None:
        learner = self._learner(tmp_path)
        _write_lines(
            sequences_path(tmp_path),
            [_entry("Read", session="a"), _entry("Edit", session="a"), _entry("Bash", session="a")],
        )
        _write_lines(cursor_path(tmp_path), ["{broken"])
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1


class TestClearToolSequences:
    def test_removes_both_files(self, tmp_path: Path) -> None:
        _write_lines(sequences_path(tmp_path), [_entry("Read")])
        _write_lines(cursor_path(tmp_path), [json.dumps({"offset": 1})])
        assert clear_tool_sequences(tmp_path) == 2
        assert not sequences_path(tmp_path).exists()
        assert not cursor_path(tmp_path).exists()

    def test_removes_rotation_file(self, tmp_path: Path) -> None:
        _write_lines(sequences_path(tmp_path), [_entry("Read")])
        _write_lines(rotated_path(tmp_path), [_entry("Old")])
        _write_lines(cursor_path(tmp_path), [json.dumps({"offset": 1})])
        assert clear_tool_sequences(tmp_path) == 3
        assert not sequences_path(tmp_path).exists()
        assert not rotated_path(tmp_path).exists()
        assert not cursor_path(tmp_path).exists()

    def test_missing_files_return_zero(self, tmp_path: Path) -> None:
        assert clear_tool_sequences(tmp_path) == 0

    def test_removes_last_capture_heartbeat(self, tmp_path: Path) -> None:
        # gate16 pi nit: the liveness file is capture state — purge must
        # remove it too, or a post-purge `vibe sequence status` would show
        # a stale "alive" signal.
        _write_lines(sequences_path(tmp_path), [_entry("Read")])
        _write_lines(last_capture_path(tmp_path), ["1792000000"])
        assert clear_tool_sequences(tmp_path) == 2
        assert not last_capture_path(tmp_path).exists()

    @pytest.mark.parametrize("only_cursor", [True, False])
    def test_partial_state(self, tmp_path: Path, only_cursor: bool) -> None:
        target = cursor_path(tmp_path) if only_cursor else sequences_path(tmp_path)
        _write_lines(target, ["x"])
        assert clear_tool_sequences(tmp_path) == 1
