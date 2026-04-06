"""Base classes for hooks.

This module provides the abstract base class that all hooks
must implement, along with utility functions.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from vibesop.hooks.points import HookPoint


class Hook(ABC):
    """Abstract base class for all hooks.

    Hooks represent executable code that runs at specific points
    in the AI assistant workflow.

    Example:
        >>> class MemoryFlushHook(Hook):
        ...     @property
        ...     def hook_name(self) -> str:
        ...         return "memory-flush"
        ...
        ...     def render(self) -> str:
        ...         return "#!/bin/bash\\necho 'Flushing memory...'"
    """

    def __init__(self) -> None:
        """Initialize the hook."""
        self._enabled: bool = True

    @property
    @abstractmethod
    def hook_name(self) -> str:
        """Get hook name.

        Returns:
            Unique hook identifier
        """
        ...

    @property
    @abstractmethod
    def hook_point(self) -> HookPoint:
        """Get the hook point this hook attaches to.

        Returns:
            HookPoint enum value
        """
        ...

    @abstractmethod
    def render(self) -> str:
        """Render the hook script content.

        Returns:
            Hook script as a string
        """
        ...

    def render_to_file(
        self,
        output_path: Path,
    ) -> None:
        """Render hook and write to file.

        Args:
            output_path: Path to write the hook script

        Raises:
            IOError: If write operation fails
        """
        output_path = Path(output_path)
        content = self.render()

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write hook script
        output_path.write_text(content, encoding="utf-8")

        # Make executable if it's a script
        if content.startswith("#!"):
            output_path.chmod(0o755)

    def enable(self) -> None:
        """Enable the hook."""
        self._enabled = True

    def disable(self) -> None:
        """Disable the hook."""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if hook is enabled.

        Returns:
            True if enabled, False otherwise
        """
        return self._enabled


class ScriptHook(Hook):
    """Base class for script-based hooks.

    Provides a simple way to create hooks from static scripts
    or templates.

    Example:
        >>> hook = ScriptHook(
        ...     hook_name="my-hook",
        ...     hook_point=HookPoint.PRE_SESSION_END,
        ...     script_content="#!/bin/bash\\necho 'Hello'"
        ... )
    """

    def __init__(
        self,
        hook_name: str,
        hook_point: HookPoint,
        script_content: str,
    ) -> None:
        """Initialize the script hook.

        Args:
            hook_name: Unique hook identifier
            hook_point: Hook point this hook attaches to
            script_content: Hook script content
        """
        super().__init__()  # Initialize _enabled from base class
        self._hook_name = hook_name
        self._hook_point = hook_point
        self._content = script_content

    @property
    def hook_name(self) -> str:
        """Get hook name.

        Returns:
            Hook name
        """
        return self._hook_name

    @property
    def hook_point(self) -> HookPoint:
        """Get hook point.

        Returns:
            HookPoint enum value
        """
        return self._hook_point

    def render(self) -> str:
        """Render the hook script.

        Returns:
            Hook script content
        """
        return self._content


class TemplateHook(Hook):
    """Base class for template-based hooks.

    Hooks that render from Jinja2 templates,
    allowing for dynamic content generation.

    Example:
        >>> hook = TemplateHook(
        ...     hook_name="my-hook",
        ...     hook_point=HookPoint.PRE_SESSION_END,
        ...     template_path="hooks/my_hook.sh.j2",
        ...     template_vars={"name": "value"}
        ... )
    """

    def __init__(
        self,
        hook_name: str,
        hook_point: HookPoint,
        template_path: Path,
        template_vars: dict[str, str] | None = None,
    ) -> None:
        """Initialize the template hook.

        Args:
            hook_name: Unique hook identifier
            hook_point: Hook point this hook attaches to
            template_path: Path to Jinja2 template
            template_vars: Variables for template rendering
        """
        super().__init__()  # Initialize _enabled from base class
        from jinja2 import Environment, FileSystemLoader

        self._hook_name = hook_name
        self._hook_point = hook_point
        self._template_path = Path(template_path)
        self._vars = template_vars or {}

        # Setup Jinja2 environment
        template_dir = self._template_path.parent
        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
        )

    @property
    def hook_name(self) -> str:
        """Get hook name.

        Returns:
            Hook name
        """
        return self._hook_name

    @property
    def hook_point(self) -> HookPoint:
        """Get hook point.

        Returns:
            HookPoint enum value
        """
        return self._hook_point

    def render(self) -> str:
        """Render the hook from template.

        Returns:
            Rendered hook script
        """
        template = self._env.get_template(self._template_path.name)
        return template.render(**self._vars)


def create_hook(
    hook_name: str,
    hook_point: HookPoint,
    script_content: str,
) -> ScriptHook:
    """Create a simple script hook.

    Convenience function for creating ScriptHook instances.

    Args:
        hook_name: Unique hook identifier
        hook_point: Hook point for this hook
        script_content: Hook script content

    Returns:
        ScriptHook instance

    Example:
        >>> hook = create_hook(
        ...     "memory-flush",
        ...     HookPoint.PRE_SESSION_END,
        ...     "#!/bin/bash\\necho 'Flushing...'"
        ... )
    """
    return ScriptHook(
        hook_name=hook_name,
        hook_point=hook_point,
        script_content=script_content,
    )
