"""Tests for hook system."""

from pathlib import Path

from vibesop.hooks import (
    HookPoint,
    ScriptHook,
    TemplateHook,
    create_hook,
    get_hook_definitions,
    is_hook_supported,
)


class TestHookPoint:
    """Test HookPoint enum."""

    def test_get_all(self) -> None:
        """Test getting all hook points."""
        all_points = HookPoint.get_all()

        assert isinstance(all_points, list)
        assert len(all_points) == 3
        assert HookPoint.PRE_SESSION_END in all_points
        assert HookPoint.PRE_TOOL_USE in all_points
        assert HookPoint.POST_SESSION_START in all_points

    def test_get_description(self) -> None:
        """Test getting hook point descriptions."""
        desc = HookPoint.get_description(HookPoint.PRE_SESSION_END)

        assert isinstance(desc, str)
        assert "session ends" in desc.lower()

    def test_is_standard(self) -> None:
        """Test checking if hook point is standard."""
        # Standard hook points
        assert HookPoint.is_standard(HookPoint.PRE_SESSION_END)
        assert HookPoint.is_standard(HookPoint.PRE_TOOL_USE)
        assert HookPoint.is_standard(HookPoint.POST_SESSION_START)


class TestScriptHook:
    """Test ScriptHook functionality."""

    def test_create_script_hook(self) -> None:
        """Test creating a script hook."""
        hook = ScriptHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            script_content="#!/bin/bash\necho 'Test'",
        )

        assert hook.hook_name == "test-hook"
        assert hook.hook_point == HookPoint.PRE_SESSION_END
        assert "Test" in hook.render()

    def test_render_to_file(self, tmp_path: Path) -> None:
        """Test rendering hook to file."""
        hook = ScriptHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            script_content="#!/bin/bash\necho 'Test'",
        )

        output_path = tmp_path / "test-hook.sh"
        hook.render_to_file(output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "#!/bin/bash" in content
        assert "Test" in content

        # Check executable bit was set
        import stat

        st_mode = output_path.stat().st_mode
        assert st_mode & stat.S_IXUSR  # Owner execute permission

    def test_enable_disable(self) -> None:
        """Test enabling and disabling hook."""
        hook = ScriptHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            script_content="echo",
        )

        assert hook.enabled

        hook.disable()
        assert not hook.enabled

        hook.enable()
        assert hook.enabled


class TestTemplateHook:
    """Test TemplateHook functionality."""

    def test_create_template_hook(self, tmp_path: Path) -> None:
        """Test creating a template hook."""
        # Create template file
        template_file = tmp_path / "test_hook.sh.j2"
        template_file.write_text("#!/bin/bash\necho '{{ name }}'")

        hook = TemplateHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            template_path=template_file,
            template_vars={"name": "TestValue"},
        )

        assert hook.hook_name == "test-hook"
        assert "TestValue" in hook.render()

    def test_render_to_file(self, tmp_path: Path) -> None:
        """Test rendering template hook to file."""
        # Create template file
        template_file = tmp_path / "hook.sh.j2"
        template_file.write_text("#!/bin/bash\necho '{{ message }}'")

        hook = TemplateHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            template_path=template_file,
            template_vars={"message": "Hello from hook!"},
        )

        output_path = tmp_path / "hook.sh"
        hook.render_to_file(output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "Hello from hook!" in content


class TestCreateHook:
    """Test create_hook convenience function."""

    def test_create_hook(self) -> None:
        """Test creating hook with convenience function."""
        hook = create_hook(
            "test-hook",
            HookPoint.PRE_SESSION_END,
            "#!/bin/bash\necho 'Test'",
        )

        assert isinstance(hook, ScriptHook)
        assert hook.hook_name == "test-hook"
        assert hook.hook_point == HookPoint.PRE_SESSION_END


class TestGetHookDefinitions:
    """Test get_hook_definitions function."""

    def test_get_claude_code_hooks(self) -> None:
        """Test getting Claude Code hook definitions."""
        definitions = get_hook_definitions("claude-code")

        assert isinstance(definitions, dict)
        assert "pre-session-end" in definitions
        assert len(definitions) > 0

    def test_get_opencode_hooks(self) -> None:
        """Test getting OpenCode hook definitions."""
        definitions = get_hook_definitions("opencode")

        assert isinstance(definitions, dict)
        assert len(definitions) == 0  # OpenCode doesn't support hooks

    def test_get_unknown_platform(self) -> None:
        """Test getting hooks for unknown platform."""
        definitions = get_hook_definitions("unknown-platform")

        assert definitions == {}


class TestIsHookSupported:
    """Test is_hook_supported function."""

    def test_claude_code_supports_pre_session_end(self) -> None:
        """Test Claude Code supports pre-session-end."""
        assert is_hook_supported("claude-code", HookPoint.PRE_SESSION_END)
        assert is_hook_supported("claude-code", HookPoint.PRE_TOOL_USE)

    def test_opencode_no_support(self) -> None:
        """Test OpenCode doesn't support hooks."""
        assert not is_hook_supported("opencode", HookPoint.PRE_SESSION_END)


class TestHookIntegration:
    """Integration tests for hook system."""

    def test_hook_creation_and_rendering(self, tmp_path: Path) -> None:
        """Test complete hook workflow."""
        hook = create_hook(
            "integration-test",
            HookPoint.PRE_SESSION_END,
            "#!/bin/bash\necho 'Integration test'",
        )

        output_path = tmp_path / "integration-test.sh"
        hook.render_to_file(output_path)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_multiple_hooks_same_point(self, tmp_path: Path) -> None:
        """Test multiple hooks at the same hook point."""
        hook1 = create_hook("hook1", HookPoint.PRE_SESSION_END, "#!/bin/bash\necho 'Hook 1'")
        hook2 = create_hook("hook2", HookPoint.PRE_SESSION_END, "#!/bin/bash\necho 'Hook 2'")

        output1 = tmp_path / "hook1.sh"
        output2 = tmp_path / "hook2.sh"

        hook1.render_to_file(output1)
        hook2.render_to_file(output2)

        assert output1.exists()
        assert output2.exists()
        assert "Hook 1" in output1.read_text()
        assert "Hook 2" in output2.read_text()
