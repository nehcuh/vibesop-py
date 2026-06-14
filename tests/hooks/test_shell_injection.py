"""Tests for jinja2 shell / Python injection hardening (v7.0.1 Phase 2).

Background: VibeSOP renders .sh hook scripts and inline Python snippets
via Jinja2. Prior to Phase 2, user-controllable variables like ``platform``
and ``hook_event_name`` were rendered into Python single-quoted string
literals inside a ``python3 -c "..."`` block — a Python code injection
vector. Other variables flowed into shell echo statements unescaped.

These tests pin the three-layer defense:
1. ``pyquote`` filter — escapes for Python single-quoted literals
2. ``shellquote`` filter — wraps via ``shlex.quote`` for shell context
3. ``shellvar`` filter — reduces to ``[A-Za-z0-9_-]`` only
"""

from __future__ import annotations

import pytest

from vibesop.utils.jinja_safety import (
    make_shell_safe_env,
    pyquote,
    shellquote,
    shellvar,
)


class TestPyquoteFilter:
    """pyquote: Python single-quoted string literal safety."""

    def test_plain_value_passes_through(self) -> None:
        assert pyquote("claude-code") == "claude-code"

    def test_single_quote_is_escaped(self) -> None:
        assert pyquote("a'b") == "a\\'b"

    def test_backslash_is_doubled(self) -> None:
        assert pyquote("a\\b") == "a\\\\b"

    def test_double_quote_passes_through(self) -> None:
        # Double quotes are safe inside Python single-quoted literals.
        assert pyquote('a"b') == 'a"b'

    def test_none_becomes_empty(self) -> None:
        assert pyquote(None) == ""

    def test_newline_rejected(self) -> None:
        # Newlines would break out of the one-line literal.
        with pytest.raises(ValueError, match="newline"):
            pyquote("a\nb")

    def test_carriage_return_rejected(self) -> None:
        with pytest.raises(ValueError, match="carriage return"):
            pyquote("a\rb")

    def test_nul_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match="NUL"):
            pyquote("a\x00b")

    def test_python_injection_attempt_is_neutralized(self) -> None:
        """The classic `'; os.system(...); '` attack must not survive pyquote."""
        malicious = "claude'; __import__('os').system('rm -rf ~'); x='"
        safe = pyquote(malicious)
        # The single quotes that would close the literal are now escaped.
        assert "'" not in safe.replace("\\'", "")
        # Specifically: each ' becomes \', so the rendered Python literal
        # would parse as a single string, not as `string + code + string`.
        rendered = f"'{safe}'"
        # Verify by attempting to compile the rendered literal.
        import ast

        tree = ast.parse(rendered, mode="eval")
        assert isinstance(tree.body, ast.Constant)
        assert tree.body.value == malicious


class TestShellquoteFilter:
    """shellquote: shlex.quote wrapper."""

    def test_plain_value_passes_through(self) -> None:
        assert shellquote("claude-code") == "claude-code"

    def test_space_is_quoted(self) -> None:
        # shlex.quote wraps values with special chars in single quotes.
        assert shellquote("hello world") == "'hello world'"

    def test_single_quote_is_escaped_via_arithmetic(self) -> None:
        # shlex.quote handles embedded single quotes via the 'x'y'z' trick.
        result = shellquote("a'b")
        assert result == "'a'\"'\"'b'"

    def test_shell_metacharacters_are_neutralized(self) -> None:
        malicious = "; rm -rf ~ #"
        safe = shellquote(malicious)
        # The rendered value, when used as a shell token, evaluates to the
        # literal string rather than executing the embedded commands.
        assert safe.startswith("'") or "\\" in safe
        assert "$()" not in safe  # no unescaped expansion

    def test_none_becomes_empty_quotes(self) -> None:
        # Empty shellquote is '' (two single quotes) — safer than empty.
        assert shellquote(None) == "''"


class TestShellvarFilter:
    """shellvar: reduce to identifier-only characters."""

    def test_plain_value_passes_through(self) -> None:
        assert shellvar("claude-code") == "claude-code"

    def test_underscore_kept(self) -> None:
        assert shellvar("user_prompt") == "user_prompt"

    def test_dot_replaced_with_underscore(self) -> None:
        assert shellvar("1.2.3") == "1_2_3"

    def test_shell_metacharacters_stripped(self) -> None:
        malicious = "v1.0; rm -rf ~"
        safe = shellvar(malicious)
        # Only [A-Za-z0-9_-] survives; everything else (including ;, space, ~)
        # is replaced with underscore (regex is greedy: consecutive invalid
        # chars collapse to a single _).
        assert ";" not in safe
        assert " " not in safe
        assert "~" not in safe
        assert safe == "v1_0_rm_-rf_"

    def test_empty_becomes_single_underscore(self) -> None:
        assert shellvar("") == "_"
        assert shellvar(None) == "_"
        assert shellvar(";;;") == "_"


class TestSafeTextFilter:
    """safe_text: strip shell-breaking chars, keep readable text."""

    def test_plain_value_passes_through(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        assert safe_text("Claude Code") == "Claude Code"
        assert safe_text("Kimi CLI") == "Kimi CLI"
        assert safe_text("v1.2.3") == "v1.2.3"

    def test_semicolon_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        # ; would chain shell commands — must be stripped.
        assert safe_text("a; b") == "a b"

    def test_dollar_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        # $ would trigger variable expansion in double-quoted strings.
        assert safe_text("a$HOME") == "aHOME"

    def test_backtick_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        # Backtick triggers command substitution.
        assert safe_text("a`whoami`b") == "awhoamib"

    def test_double_quote_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        # " would break out of a double-quoted echo argument.
        assert safe_text('a"; rm -rf ~; echo "') == "a rm -rf ~ echo "

    def test_ampersand_and_pipe_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        assert safe_text("a & b | c") == "a  b  c"

    def test_angle_brackets_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        assert safe_text("a > /etc/passwd < /dev/null") == "a  /etc/passwd  /dev/null"

    def test_newline_stripped(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        # A newline in a comment would terminate the comment line.
        assert safe_text("line1\nline2") == "line1line2"

    def test_tilde_kept(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        # ~ is only expanded at the start of an unquoted shell word. In
        # comments and double-quoted echo args it's inert, so we keep it
        # for readability.
        assert safe_text("~/path") == "~/path"

    def test_none_becomes_empty(self) -> None:
        from vibesop.utils.jinja_safety import safe_text

        assert safe_text(None) == ""


class TestMakeShellSafeEnv:
    """Factory: registers all three filters on a fresh Environment."""

    def test_filters_registered(self) -> None:
        env = make_shell_safe_env()
        assert "shellquote" in env.filters
        assert "pyquote" in env.filters
        assert "shellvar" in env.filters

    def test_finalize_converts_none_to_empty(self) -> None:
        env = make_shell_safe_env()
        template = env.from_string("{{ value }}")
        assert template.render(value=None) == ""

    def test_kwargs_forwarded(self) -> None:
        env = make_shell_safe_env(trim_blocks=True, lstrip_blocks=True)
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True

    def test_filters_usable_in_template(self) -> None:
        env = make_shell_safe_env()
        template = env.from_string("{{ x|shellquote }} | {{ y|pyquote }} | {{ z|shellvar }}")
        out = template.render(x="a b", y="c'd", z="1.0; evil")
        # shellquote('a b') == "'a b'", pyquote("c'd") == "c\\'d",
        # shellvar("1.0; evil") == "1_0_evil"
        assert "'a b'" in out
        assert "c\\'d" in out
        assert "1_0_evil" in out


class TestRouteHookTemplateInjection:
    """End-to-end: the vibesop-route.sh.j2 template must resist injection."""

    def test_platform_python_injection_neutralized(self) -> None:
        """The classic `platform='...'; os.system('rm -rf ~'); x='...'` attack."""
        from vibesop.adapters._shared import render_route_hook

        malicious_platform = "claude'; __import__('os').system('pwned'); x='"
        rendered = render_route_hook(
            platform=malicious_platform,
            platform_name="Test",
            hook_event_name="UserPromptSubmit",
        )
        # The rendered output must contain the escaped version, not the raw
        # malicious string, in the Python literal context.
        # Specifically: platform='...' should escape the embedded quotes.
        assert "platform='claude\\'; __import__(\\'os\\').system(\\'pwned\\'); x=\\''" in rendered
        # The bare unescaped injection must NOT appear in executable position.
        assert "__import__('os')" not in rendered

    def test_hook_event_name_python_injection_neutralized(self) -> None:
        from vibesop.adapters._shared import render_route_hook

        malicious = "x'; eval('evil'); y='"
        rendered = render_route_hook(
            platform="claude-code",
            platform_name="Test",
            hook_event_name=malicious,
        )
        assert "eval('evil')" not in rendered

    def test_platform_name_shell_injection_neutralized(self) -> None:
        """Comment-header injection must not produce shell-breaking chars."""
        from vibesop.adapters._shared import render_route_hook

        malicious_name = "Claude; rm -rf ~; # $HOME"
        rendered = render_route_hook(
            platform="claude-code",
            platform_name=malicious_name,
            hook_event_name="",
        )
        # safe_text strips shell-breaking chars (`;`, `$`, backtick, `"`,
        # `<`, `>`, `&`, control chars) but keeps spaces, letters, `~`, `#`.
        # `~` is preserved because it's NOT expanded inside comments or
        # double-quoted echo args — it's only a threat at start of an
        # unquoted shell word, which neither context is.
        comment_line = next(
            (line for line in rendered.splitlines() if "VibeSOP route hook for" in line),
            "",
        )
        # Critical: no `;` (would chain commands), no `$` (would expand vars),
        # no backtick (would substitute commands).
        assert ";" not in comment_line
        assert "$" not in comment_line
        assert "`" not in comment_line
        assert '"' not in comment_line

    def test_version_string_sanitized_to_identifier(self) -> None:
        from vibesop.adapters._shared import render_route_hook

        malicious_version = "1.0.0; rm -rf ~"
        rendered = render_route_hook(
            platform="claude-code",
            platform_name="Test",
            version=malicious_version,
        )
        # The version is rendered into a comment line. The template's own
        # bash code contains semicolons (e.g. `INPUT=$(cat); QUERY=""`), so
        # we check the specific rendered line, not the whole script.
        version_line = next(
            (line for line in rendered.splitlines() if "Generated by VibeSOP" in line),
            "",
        )
        assert version_line, "Version comment line should exist"
        # safe_text strips shell-breaking chars (`;`, `$`, etc.) but keeps
        # dots, spaces, and `~` (the latter is safe in comment context).
        assert ";" not in version_line
        assert "$" not in version_line
        assert "1.0.0" in version_line  # version digits and dots survive


class TestHookInstallerTemplateInjection:
    """End-to-end: HookInstaller must also resist injection."""

    def test_hook_installer_uses_safe_env(self) -> None:
        """HookInstaller.template_env must have shellquote/pyquote/shellvar filters."""
        from vibesop.hooks.installer import HookInstaller

        installer = HookInstaller()
        env = installer.template_env
        assert "shellquote" in env.filters
        assert "pyquote" in env.filters
        assert "shellvar" in env.filters


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
