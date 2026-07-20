"""Base class for platform adapters.

This module provides the abstract base class that all platform
adapters must inherit from, along with shared utility methods.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from vibesop.adapters.models import Manifest, RenderResult
from vibesop.security import PathSafety, SecurityScanner

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters.

    Provides a common interface and shared utilities for all
    platform-specific adapters.

    Example:
        class ClaudeCodeAdapter(PlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "claude-code"

            @property
            def config_dir(self) -> Path:
                return Path("~/.claude").expanduser()

            def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
                # Implementation
                ...

            def get_settings_schema(self) -> dict:
                # Implementation
                ...
    """

    # Safety validators
    _path_safety: PathSafety
    _security_scanner: SecurityScanner
    _project_root: Path

    def __init__(self) -> None:
        """Initialize the platform adapter."""
        self._path_safety = PathSafety()
        self._security_scanner = SecurityScanner()
        self._project_root = Path().resolve()

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Platform identifier.

        Returns:
            Unique platform name (e.g., 'claude-code', 'kimi-cli', 'opencode', 'pi')
        """
        ...

    @property
    @abstractmethod
    def config_dir(self) -> Path:
        """Default configuration directory for this platform.

        Returns:
            Path to the default config directory (e.g., ~/.claude)
        """
        ...

    @abstractmethod
    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render platform configuration from manifest.

        This method generates all necessary configuration files
        for the target platform based on the provided manifest.

        Args:
            manifest: Configuration manifest
            output_dir: Directory to write configuration files

        Returns:
            RenderResult with list of created files and any warnings/errors
        """
        ...

    @abstractmethod
    def get_settings_schema(self) -> dict[str, Any]:
        """Get the settings schema for this platform.

        Returns a JSON schema describing the structure of the
        platform's settings file (e.g., settings.json).

        Returns:
            JSON schema as a dictionary
        """
        ...

    def install_hooks(self, _config_dir: Path) -> dict[str, bool]:
        """Install platform-specific hooks.

        Default implementation does nothing. Override this method
        if your platform supports hooks.

        Args:
            config_dir: Configuration directory

        Returns:
            Dictionary mapping hook names to installation status
        """
        return {}

    # CLI binary name for availability detection (override per concrete adapter).
    # Empty string means no PATH-based detection (is_available returns False).
    cli_binary: ClassVar[str] = ""

    # Whether this adapter deploys skills to ``output_dir/skills/`` and
    # should clean orphan skills after rendering.  Set to False for
    # adapters (like Grok Build) that deploy only hooks/rules, not skills,
    # so they don't delete third-party skills in shared directories.
    manages_skills: ClassVar[bool] = True

    def is_available(self) -> bool:
        """Whether this platform's AI Agent CLI is installed and on PATH.

        VibeSOP routes queries and injects skill instructions; the Agent
        (Claude Code, OpenCode, etc.) performs the actual execution. This
        checks whether that Agent is installed.
        """
        import shutil

        return bool(self.cli_binary) and shutil.which(self.cli_binary) is not None

    def detect(self) -> str | None:
        """Absolute path to the Agent CLI binary, or None if not found/unknown."""
        import shutil

        return shutil.which(self.cli_binary) if self.cli_binary else None

    def clean_orphan_skills(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> list[Path]:
        """Remove skill directories not present in the manifest.

        After rendering, any skill directory in ``output_dir/skills/``
        whose name does not correspond to a skill in the manifest is
        considered an orphan and removed.  This prevents stale skills
        from lingering in platform configs after they have been
        deleted from the registry.

        Adapters that do not manage skills (``manages_skills = False``)
        skip cleanup entirely to avoid deleting third-party skills in
        shared directories (e.g. Grok Build's ``~/.grok/skills/``).

        Args:
            manifest: Current configuration manifest
            output_dir: Platform output directory (contains skills/)

        Returns:
            List of paths that were removed
        """
        if not self.manages_skills:
            return []

        import shutil

        skills_dir = Path(output_dir).expanduser().resolve() / "skills"
        if not skills_dir.exists():
            return []

        expected_dirs = {skill.id.replace("/", "-") for skill in manifest.skills}

        removed: list[Path] = []
        for item in skills_dir.iterdir():
            if not item.is_dir() and not item.is_symlink():
                continue
            if item.name.startswith("."):
                continue
            if item.name not in expected_dirs:
                try:
                    if item.is_symlink():
                        item.unlink(missing_ok=True)
                    else:
                        shutil.rmtree(item)
                    removed.append(item)
                except OSError as e:
                    logger.debug(f"Failed to remove orphan skill dir {item}: {e}")

        return removed

    # Utility methods

    def _find_skill_content(self, skill_id: str) -> str | None:
        from vibesop.adapters._shared import find_skill_content

        return find_skill_content(skill_id, self._project_root)

    @staticmethod
    def _normalize_skill_type(content: str) -> str:
        from vibesop.adapters._shared import normalize_skill_type

        return normalize_skill_type(content)

    @staticmethod
    def _generate_fallback_skill_content(skill: Any, dir_name: str | None = None) -> str:
        from vibesop.adapters._shared import generate_fallback_skill_content

        return generate_fallback_skill_content(skill, dir_name=dir_name)

    def validate_manifest(self, manifest: Manifest) -> list[str]:
        """Validate a manifest before rendering.

        Performs basic validation checks on the manifest to ensure
        it's ready for rendering.

        Args:
            manifest: Manifest to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check metadata
        if not manifest.metadata:
            errors.append("Manifest metadata is required")

        # Check platform compatibility
        if manifest.metadata.platform != self.platform_name:
            errors.append(
                f"Manifest platform '{manifest.metadata.platform}' "
                f"does not match adapter platform '{self.platform_name}'"
            )

        # Check security policy
        security_policy = manifest.get_effective_security_policy()
        if security_policy.allow_path_traversal:
            errors.append("Security policy must not allow path traversal")

        return errors

    def ensure_output_dir(self, output_dir: Path) -> Path:
        """Ensure output directory exists and is safe.

        Creates the output directory if it doesn't exist,
        after validating it's safe to write to.

        Args:
            output_dir: Desired output directory

        Returns:
            Path to the validated output directory

        Raises:
            ValueError: If output directory is unsafe
        """
        output_dir = Path(output_dir).expanduser().resolve()

        # Ensure it's safe
        self._path_safety.ensure_safe_output_path(
            output_dir / "dummy.txt",
            output_dir.parent,
            create_parents=True,
        )

        # Create if needed
        output_dir.mkdir(parents=True, exist_ok=True)

        return output_dir

    def write_file_atomic(
        self,
        path: Path,
        content: str,
        validate_security: bool = True,
        base_dir: Path | None = None,
    ) -> None:
        """Write content to file atomically.

        Writes to a temporary file first, then renames to ensure
        atomic operation and prevent corruption.

        Args:
            path: Path to write to
            content: Content to write
            validate_security: Whether to scan content for threats
            base_dir: Base directory for path safety validation

        Raises:
            ValueError: If path is unsafe or content contains threats
            IOError: If write operation fails
        """
        path = Path(path).expanduser().resolve()

        # Determine base directory for safety check
        base_dir = path.parent if base_dir is None else Path(base_dir).expanduser().resolve()

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        # Validate path safety (now that parent exists)
        self._path_safety.ensure_safe_output_path(
            path,
            base_dir,
        )

        # Validate content security if enabled
        if validate_security and self._security_scanner:
            scan_result = self._security_scanner.scan(content)
            if not scan_result.safe:
                msg = f"Content contains security threats: {scan_result.summary}"
                raise ValueError(msg)

        # Write to temporary file
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            # Atomic rename
            tmp_path.replace(path)
        finally:
            # Clean up temp file if it still exists
            tmp_path.unlink(missing_ok=True)

    def render_template_string(
        self,
        template_string: str,
        context: dict[str, Any],
    ) -> str:
        """Render a template string with context.

        Simple template rendering without external dependencies.
        Supports {variable} substitution.

        Args:
            template_string: Template string
            context: Template variables

        Returns:
            Rendered string
        """
        try:
            return template_string.format(**context)
        except KeyError as e:
            msg = f"Missing template variable: {e}"
            raise ValueError(msg) from e

    def get_template_context(self, manifest: Manifest) -> dict[str, Any]:
        """Get standard template context from manifest.

        Extracts common variables that all templates might need.

        Args:
            manifest: Source manifest

        Returns:
            Template context dictionary
        """
        return {
            "manifest": manifest,
            "skills": manifest.skills,
            "policies": manifest.policies,
            "security": manifest.get_effective_security_policy(),
            "routing": manifest.get_effective_routing_policy(),
            "metadata": manifest.metadata,
            "platform": self.platform_name,
            "version": manifest.metadata.version,
            "tool_environment": self._get_tool_environment(),
        }

    def _get_tool_environment(self) -> str:
        """Get tool environment guidance (nvm/uv detection)."""
        from vibesop.adapters._shared import detect_tool_environment

        return detect_tool_environment()

    def create_render_result(
        self,
        success: bool,
        files_created: list[Path] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> RenderResult:
        """Create a RenderResult object.

        Helper method for creating standardized render results.

        Args:
            success: Whether rendering was successful
            files_created: List of files created
            warnings: List of warnings
            errors: List of errors

        Returns:
            RenderResult object
        """
        return RenderResult(
            success=success,
            files_created=files_created or [],
            warnings=warnings or [],
            errors=errors or [],
        )

    def scan_for_threats(self, text: str) -> list[str]:
        """Scan text for security threats.

        Args:
            text: Text to scan

        Returns:
            List of threat descriptions (empty if safe)
        """
        if not self._security_scanner:
            return []

        result = self._security_scanner.scan(text)
        if result.safe:
            return []

        return [f"{t.type.value}: {t.description}" for t in result.threats]

    def is_safe_path(self, path: Path, base_dir: Path) -> bool:
        """Check if a path is safe (no traversal)."""
        return self._path_safety.check_traversal(path, base_dir)

    def _render_skill_content(
        self,
        skill: Any,
        skill_dir: Path,
        result: RenderResult,
        dir_name: str | None = None,
        manifest: Manifest | None = None,
    ) -> None:
        """Render skill content from actual skill file or central storage.

        Shared logic for all adapters:
        1. Try to find existing skill content
        2. Try to symlink/copy from installed pack
        3. Fall back to adapter-specific template generation

        Subclasses override ``_fallback_skill_content()`` for step 3.
        """
        import shutil

        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        skill_output_path = skill_dir / "SKILL.md"

        skill_content = self._find_skill_content(skill_id)

        if skill_content:
            skill_content = self._normalize_skill_type(skill_content)
            self.write_file_atomic(skill_output_path, skill_content, validate_security=False)
            result.add_file(skill_output_path)
            return

        from vibesop.adapters._shared import is_pack_installed

        installed_path = is_pack_installed(skill_id)

        # Fallback: use source_path from skill metadata (set by DynamicSkillDiscovery)
        if not installed_path:
            metadata = getattr(skill, "metadata", None) or (
                skill.get("metadata", {}) if isinstance(skill, dict) else {}
            )
            source_path = metadata.get("source_path", "") if isinstance(metadata, dict) else ""
            if source_path:
                sp = Path(source_path).expanduser()
                if sp.exists() and (sp / "SKILL.md").exists():
                    installed_path = sp

        if installed_path:
            resolved_installed = installed_path.resolve()

            if (
                skill_dir.is_symlink()
                and skill_dir.exists()
                and skill_dir.resolve() == resolved_installed
            ):
                result.add_file(skill_output_path)
                return

            if skill_dir.is_symlink():
                skill_dir.unlink(missing_ok=True)
            elif skill_dir.exists():
                shutil.rmtree(skill_dir)

            from vibesop.utils.symlinks import can_create_dir_symlink

            if can_create_dir_symlink(skill_dir.parent):
                try:
                    skill_dir.symlink_to(resolved_installed, target_is_directory=True)
                    result.add_file(skill_output_path)
                    return
                except OSError as e:
                    logger.info(
                        "symlink unavailable, falling back to copy: %s -> %s (%s)",
                        resolved_installed,
                        skill_dir,
                        e,
                    )
            else:
                logger.info(
                    "symlinks unsupported under %s, copying %s instead",
                    skill_dir.parent,
                    resolved_installed,
                )

            try:
                shutil.copytree(resolved_installed, skill_dir)
            except Exception as copy_err:
                logger.warning(
                    "copy fallback failed: %s -> %s (%s)",
                    resolved_installed,
                    skill_dir,
                    copy_err,
                )
                # Clean up partial copytree residue before writing the stub
                if skill_dir.exists() and not skill_dir.is_symlink():
                    try:
                        shutil.rmtree(skill_dir)
                    except OSError as rm_err:
                        logger.warning("failed to clean partial copy %s: %s", skill_dir, rm_err)
            else:
                # Marker failure must not discard a successful copy — the skill
                # content is usable; it just won't show up in pack discovery.
                try:
                    from vibesop.core.skills.storage import write_copy_source_marker

                    write_copy_source_marker(skill_dir, resolved_installed)
                except OSError as marker_err:
                    logger.warning(
                        "copy succeeded but copy-source marker write failed for %s: %s",
                        skill_dir,
                        marker_err,
                    )
                result.add_file(skill_output_path)
                return

        self._fallback_skill_content(
            skill,
            skill_output_path,
            result,
            dir_name=dir_name,
            manifest=manifest,
        )

    def _fallback_skill_content(
        self,
        skill: Any,
        skill_output_path: Path,
        result: RenderResult,
        *,
        dir_name: str | None = None,
        manifest: Manifest | None = None,  # noqa: ARG002
    ) -> None:
        """Generate fallback skill content when no real content exists.

        Default: use the shared fallback generator. Subclasses (e.g. ClaudeCode)
        override this to use Jinja2 templates instead.
        """
        fallback_content = self._generate_fallback_skill_content(skill, dir_name=dir_name)
        self.write_file_atomic(skill_output_path, fallback_content, validate_security=False)
        result.add_file(skill_output_path)
