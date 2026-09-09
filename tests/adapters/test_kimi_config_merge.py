"""Regression tests for KimiCliAdapter._merge_config_with_existing.

The merge must only replace clearly-identifiable VibeSOP hooks and must
preserve user-owned hooks, unknown-but-valid structures, plain settings and
comments. Repeated merges must be idempotent. Unreliably parseable input
must raise instead of silently destroying the user's config.
"""

import tomllib
from pathlib import Path

import pytest

from vibesop.adapters.kimi_cli import KimiCliAdapter

NEW_CONFIG = """# VibeSOP Configuration for Kimi Code CLI

[vibesop.routing]
enable_ai_routing = true

# VibeSOP Auto-Routing Hook
[[hooks]]
event = "UserPromptSubmit"
command = "bash ~/.kimi-code/hooks/vibesop-route.sh"
timeout = 15

[[hooks]]
event = "PostToolUse"
command = "bash ~/.kimi-code/hooks/vibesop-tool-seq.sh"
timeout = 10
"""

VIBESOP_HOOKS = """[[hooks]]
event = "UserPromptSubmit"
command = "bash ~/.kimi-code/hooks/vibesop-route.sh"
timeout = 15

[[hooks]]
event = "PostToolUse"
command = "bash ~/.kimi-code/hooks/vibesop-tool-seq.sh"
timeout = 10
"""

USER_HOOK = """[[hooks]]
event = "PreToolUse"
command = "bash ~/.kimi-code/hooks/my-backup.sh"
timeout = 5
"""


def _merge(tmp_path: Path, existing: str, new_config: str = NEW_CONFIG) -> str:
    config_path = tmp_path / "config.toml"
    config_path.write_text(existing)
    adapter = KimiCliAdapter()
    return adapter._merge_config_with_existing(config_path, new_config)


def _write_crlf(path: Path, text: str, *, trailing_newline: bool = True) -> bytes:
    raw = text.replace("\n", "\r\n")
    if not trailing_newline and raw.endswith("\r\n"):
        raw = raw[:-2]
    data = raw.encode("utf-8")
    path.write_bytes(data)
    return data


def _merge_crlf(tmp_path: Path, existing: str, *, trailing_newline: bool = True) -> str:
    config_path = tmp_path / "config.toml"
    _write_crlf(config_path, existing, trailing_newline=trailing_newline)
    adapter = KimiCliAdapter()
    return adapter._merge_config_with_existing(config_path, NEW_CONFIG)


def _hooks(parsed: dict) -> list[dict]:
    return parsed.get("hooks", [])


class TestMergePreservesUserHooks:
    def test_user_hook_survives_alongside_builtin_hooks(self, tmp_path: Path) -> None:
        existing = (
            "# my personal config\n"
            'default_model = "kimi-for-coding"\n\n' + USER_HOOK + "\n" + VIBESOP_HOOKS
        )
        merged = _merge(tmp_path, existing)
        parsed = tomllib.loads(merged)

        hooks = _hooks(parsed)
        assert len(hooks) == 3
        assert hooks[0]["command"] == "bash ~/.kimi-code/hooks/my-backup.sh"
        commands = [h["command"] for h in hooks]
        assert "bash ~/.kimi-code/hooks/vibesop-route.sh" in commands
        assert "bash ~/.kimi-code/hooks/vibesop-tool-seq.sh" in commands
        assert parsed["default_model"] == "kimi-for-coding"
        assert "# my personal config" in merged

    def test_merge_is_idempotent(self, tmp_path: Path) -> None:
        existing = USER_HOOK + "\n" + VIBESOP_HOOKS
        first = _merge(tmp_path, existing)
        config_path = tmp_path / "config.toml"
        config_path.write_text(first)
        adapter = KimiCliAdapter()
        second = adapter._merge_config_with_existing(config_path, NEW_CONFIG)

        assert len(_hooks(tomllib.loads(second))) == 3
        assert tomllib.loads(second) == tomllib.loads(first)

    def test_no_existing_builtin_hooks(self, tmp_path: Path) -> None:
        existing = '# plain user config\ntheme = "dark"\n\n' + USER_HOOK
        merged = _merge(tmp_path, existing)
        parsed = tomllib.loads(merged)

        hooks = _hooks(parsed)
        assert len(hooks) == 3
        assert hooks[0]["command"] == "bash ~/.kimi-code/hooks/my-backup.sh"
        assert parsed["theme"] == "dark"

    def test_no_hooks_at_all(self, tmp_path: Path) -> None:
        existing = 'default_model = "kimi-for-coding"\n'
        merged = _merge(tmp_path, existing)
        parsed = tomllib.loads(merged)

        assert len(_hooks(parsed)) == 2
        assert parsed["default_model"] == "kimi-for-coding"


class TestNearMissNamesPreserved:
    def test_similar_script_names_not_removed(self, tmp_path: Path) -> None:
        existing = (
            "[[hooks]]\n"
            'event = "UserPromptSubmit"\n'
            'command = "bash ~/.kimi-code/hooks/vibesop-route.sh.bak"\n'
            "\n"
            "[[hooks]]\n"
            'event = "UserPromptSubmit"\n'
            'command = "bash ~/.kimi-code/hooks/my-vibesop-route.sh"\n'
            "\n"
            "[[hooks]]\n"
            'event = "UserPromptSubmit"\n'
            'command = "bash ~/.kimi-code/hooks/vibesop-route.sh --verbose"\n'
            "\n" + VIBESOP_HOOKS
        )
        merged = _merge(tmp_path, existing)
        commands = [h["command"] for h in _hooks(tomllib.loads(merged))]

        assert "bash ~/.kimi-code/hooks/vibesop-route.sh.bak" in commands
        assert "bash ~/.kimi-code/hooks/my-vibesop-route.sh" in commands
        assert "bash ~/.kimi-code/hooks/vibesop-route.sh --verbose" in commands
        assert commands.count("bash ~/.kimi-code/hooks/vibesop-route.sh") == 1
        assert len(commands) == 5

    def test_unknown_fields_on_user_hook_preserved(self, tmp_path: Path) -> None:
        existing = (
            "[[hooks]]\n"
            'event = "PreToolUse"\n'
            'matcher = "Bash"\n'
            'command = "bash ~/lint.sh"\n'
            'name = "my lint gate"\n'
            "\n" + VIBESOP_HOOKS
        )
        merged = _merge(tmp_path, existing)
        hooks = _hooks(tomllib.loads(merged))

        assert hooks[0]["name"] == "my lint gate"
        assert hooks[0]["matcher"] == "Bash"


class TestQuotedAndNestedStructures:
    def test_quoted_hooks_header_handled(self, tmp_path: Path) -> None:
        existing = (
            '[["hooks"]]\n'
            'event = "UserPromptSubmit"\n'
            'command = "bash ~/.kimi-code/hooks/vibesop-route.sh"\n'
            "timeout = 15\n"
            "\n"
            '[["hooks"]]\n'
            'event = "PreToolUse"\n'
            'command = "bash ~/user-hook.sh"\n'
        )
        merged = _merge(tmp_path, existing)
        commands = [h["command"] for h in _hooks(tomllib.loads(merged))]

        assert commands.count("bash ~/.kimi-code/hooks/vibesop-route.sh") == 1
        assert "bash ~/user-hook.sh" in commands
        assert len(commands) == 3

    def test_hook_with_nested_subtable_removed_together(self, tmp_path: Path) -> None:
        existing = (
            USER_HOOK + "\n" + "[[hooks]]\n"
            'event = "UserPromptSubmit"\n'
            'command = "bash ~/.kimi-code/hooks/vibesop-route.sh"\n'
            "\n"
            "[hooks.env]\n"
            'FOO = "bar"\n'
        )
        merged = _merge(tmp_path, existing)
        parsed = tomllib.loads(merged)
        hooks = _hooks(parsed)

        # the orphaned [hooks.env] must not silently re-attach to the user hook
        assert "env" not in hooks[0]
        assert hooks[0]["command"] == "bash ~/.kimi-code/hooks/my-backup.sh"

    def test_nested_subtable_on_user_hook_preserved(self, tmp_path: Path) -> None:
        existing = USER_HOOK + "\n" + '[hooks.env]\nFOO = "bar"\n' + "\n" + VIBESOP_HOOKS
        merged = _merge(tmp_path, existing)
        parsed = tomllib.loads(merged)

        assert parsed["hooks"][0]["env"] == {"FOO": "bar"}


class TestSafetyOnUnreliableInput:
    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('default_model = "unclosed\n[[hooks]]\nevent = "x"\n')
        adapter = KimiCliAdapter()
        with pytest.raises(ValueError, match=r"[Cc]annot"):
            adapter._merge_config_with_existing(config_path, NEW_CONFIG)

    def test_unparseable_hook_block_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('theme = "dark"\n')
        adapter = KimiCliAdapter()
        with pytest.raises(ValueError):
            adapter._merge_config_with_existing(config_path, "[[hooks]]\nnot toml at all = = =\n")

    def test_merged_output_is_always_valid_toml(self, tmp_path: Path) -> None:
        existing = "# comment only\n"
        merged = _merge(tmp_path, existing)
        tomllib.loads(merged)  # must not raise


class TestMergeLexicalBoundaries:
    @pytest.mark.parametrize(
        "user_setting",
        [
            '# TOML multiline strings start with """\n',
            'matcher = \'"""\'\n',
            "matcher = \"'''\"\n",
            "matcher = \"Bash\" # triple literal delimiter: '''\n",
        ],
    )
    def test_quotes_in_comments_or_ordinary_strings_preserve_user_hook(
        self, tmp_path: Path, user_setting: str
    ) -> None:
        existing = USER_HOOK + user_setting + "\n" + VIBESOP_HOOKS
        before = tomllib.loads(existing)
        parsed = tomllib.loads(_merge(tmp_path, existing))
        assert parsed["hooks"][0] == before["hooks"][0]
        assert len(parsed["hooks"]) == 3

    def test_escaped_multiline_delimiter_does_not_expose_fake_header(self, tmp_path: Path) -> None:
        matcher = (
            'matcher = """begin\n'
            'escaped quote: \\"""\n'
            "[hooks.fake]\n"
            "# content, not a comment\n"
            'end"""\n'
        )
        existing = USER_HOOK + matcher + "\n" + VIBESOP_HOOKS
        before = tomllib.loads(existing)
        parsed = tomllib.loads(_merge(tmp_path, existing))
        assert parsed["hooks"][0] == before["hooks"][0]
        assert "fake" not in parsed["hooks"][0]

    def test_multiline_closing_line_starting_hash_is_not_moved_as_comment(
        self, tmp_path: Path
    ) -> None:
        existing = USER_HOOK + 'matcher = """begin\n#end"""\n' + VIBESOP_HOOKS
        parsed = tomllib.loads(_merge(tmp_path, existing))
        assert parsed["hooks"][0]["matcher"] == "begin\n#end"

    @pytest.mark.parametrize("quote_count", [4, 5])
    def test_multiline_closing_literal_quotes_keep_next_table_visible(
        self, tmp_path: Path, quote_count: int
    ) -> None:
        existing = USER_HOOK + 'matcher = """begin\nend' + '"' * quote_count + "\n" + VIBESOP_HOOKS
        before = tomllib.loads(existing)
        parsed = tomllib.loads(_merge(tmp_path, existing))
        assert parsed["hooks"][0] == before["hooks"][0]
        assert len(parsed["hooks"]) == 3


class TestMergeSemanticPreservation:
    def test_owned_subtable_after_unrelated_table_does_not_move_to_user_hook(
        self, tmp_path: Path
    ) -> None:
        existing = (
            USER_HOOK
            + "\n"
            + VIBESOP_HOOKS
            + '\n[providers.demo]\nmodel = "test-model"\n'
            + '\n[hooks.env]\nTARGET = "owned-only"\n'
        )
        before = tomllib.loads(existing)
        assert before["hooks"][-1]["env"] == {"TARGET": "owned-only"}
        parsed = tomllib.loads(_merge(tmp_path, existing))
        assert parsed["hooks"][0] == before["hooks"][0]
        assert all("env" not in hook for hook in parsed["hooks"])
        assert parsed["providers"] == before["providers"]

    def test_unknown_nested_user_tables_and_hook_subtables_survive_repeated_merge(
        self, tmp_path: Path
    ) -> None:
        existing = (
            "# User settings\ncreated = 2026-09-09\n"
            + USER_HOOK
            + "\n[extensions.custom]\nitems = [1, 2, 3]\n"
            + '\n[hooks.env]\nTARGET = "user-only"\n'
            + '\n[[hooks.extra]]\nvalue = "keep me"\n'
            + "\n[extensions.custom.deep]\nenabled = true\n"
            + VIBESOP_HOOKS
        )
        before = tomllib.loads(existing)
        first = _merge(tmp_path, existing)
        second = _merge(tmp_path, first)
        parsed = tomllib.loads(second)
        assert parsed == tomllib.loads(first)
        assert parsed["hooks"][0] == before["hooks"][0]
        assert parsed["extensions"] == before["extensions"]
        assert parsed["created"] == before["created"]
        assert "# User settings" in second

    def test_multiple_hook_elements_in_one_block_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="exactly one hook"):
            KimiCliAdapter._parse_hook_block(
                {"lines": (USER_HOOK + VIBESOP_HOOKS).splitlines()}, "test config"
            )

    @pytest.mark.parametrize("mutation", ["user_hook", "user_setting"])
    def test_semantic_guard_refuses_valid_toml_that_loses_user_data(
        self, tmp_path: Path, monkeypatch, mutation: str
    ) -> None:
        existing = (
            'theme = "dark"\n' + USER_HOOK + '\n[custom]\nvalue = "preserve"\n' + VIBESOP_HOOKS
        )
        config_path = tmp_path / "config.toml"
        config_path.write_text(existing)
        adapter = KimiCliAdapter()
        split = adapter._split_config_blocks

        def damage_blocks(text):
            preamble, blocks = split(text)
            if text == existing:
                index = 0 if mutation == "user_hook" else 1
                blocks.pop(index)
            return preamble, blocks

        monkeypatch.setattr(adapter, "_split_config_blocks", damage_blocks)
        with pytest.raises(ValueError, match="change user configuration"):
            adapter._merge_config_with_existing(config_path, NEW_CONFIG)
        assert config_path.read_text() == existing

    def test_nan_user_setting_survives_semantic_validation(self, tmp_path: Path) -> None:
        import math

        parsed = tomllib.loads(_merge(tmp_path, "score = nan\n" + USER_HOOK))
        assert math.isnan(parsed["score"])


class TestWindowsCrlfFiles:
    """Merge must work on real CRLF bytes (Windows default write_text)."""

    def test_crlf_user_hook_survives_alongside_builtin_hooks(self, tmp_path: Path) -> None:
        existing = (
            "# my personal config\n"
            'default_model = "kimi-for-coding"\n\n' + USER_HOOK + "\n" + VIBESOP_HOOKS
        )
        merged = _merge_crlf(tmp_path, existing)
        parsed = tomllib.loads(merged)

        hooks = _hooks(parsed)
        assert len(hooks) == 3
        assert hooks[0]["command"] == "bash ~/.kimi-code/hooks/my-backup.sh"
        commands = [h["command"] for h in hooks]
        assert "bash ~/.kimi-code/hooks/vibesop-route.sh" in commands
        assert "bash ~/.kimi-code/hooks/vibesop-tool-seq.sh" in commands
        assert parsed["default_model"] == "kimi-for-coding"
        assert "# my personal config" in merged

    def test_crlf_without_trailing_newline(self, tmp_path: Path) -> None:
        existing = (
            "# my personal config\n"
            'default_model = "kimi-for-coding"\n\n' + USER_HOOK + "\n" + VIBESOP_HOOKS
        )
        merged = _merge_crlf(tmp_path, existing, trailing_newline=False)
        parsed = tomllib.loads(merged)

        assert len(_hooks(parsed)) == 3
        assert parsed["default_model"] == "kimi-for-coding"

    def test_crlf_merge_is_idempotent(self, tmp_path: Path) -> None:
        existing = USER_HOOK + "\n" + VIBESOP_HOOKS
        first = _merge_crlf(tmp_path, existing)
        config_path = tmp_path / "config.toml"
        # Simulate the production writer (write_file_atomic uses text-mode
        # write_text): on Windows every LF is re-translated to CRLF, so the
        # merged text must be bare-LF for the roundtrip to stay valid.
        config_path.write_text(first, encoding="utf-8", newline="\r\n")
        adapter = KimiCliAdapter()
        second = adapter._merge_config_with_existing(config_path, NEW_CONFIG)

        assert len(_hooks(tomllib.loads(second))) == 3
        assert tomllib.loads(second) == tomllib.loads(first)

    def test_crlf_nested_subtable_comments_and_multiline_string(self, tmp_path: Path) -> None:
        existing = (
            "# user comment\n" + USER_HOOK + '\n[hooks.env]\nFOO = "bar"\n'
            '\nmatcher = """begin\nend"""\n' + VIBESOP_HOOKS
        )
        merged = _merge_crlf(tmp_path, existing)
        parsed = tomllib.loads(merged)

        # matcher follows [hooks.env], so TOML attaches it to that subtable;
        # the CRLF inside the multiline string normalizes to LF on parse.
        assert parsed["hooks"][0]["env"] == {"FOO": "bar", "matcher": "begin\nend"}
        assert "# user comment" in merged
        assert len(parsed["hooks"]) == 3

    def test_crlf_invalid_toml_fails_closed_without_writing(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        before = _write_crlf(config_path, 'default_model = "unclosed\n[[hooks]]\nevent = "x"\n')
        adapter = KimiCliAdapter()
        with pytest.raises(ValueError, match=r"[Cc]annot"):
            adapter._merge_config_with_existing(config_path, NEW_CONFIG)
        assert config_path.read_bytes() == before
