"""Base class for platform adapters.

This module provides the abstract base class that all platform
adapters must inherit from, along with shared utility methods.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from vibesop import __version__
from vibesop.adapters.models import Manifest, RenderResult
from vibesop.security import PathSafety, SecurityScanner
from vibesop.security.exceptions import PathTraversalError

logger = logging.getLogger(__name__)

# Marker file identifying a skill directory as vibe-managed.  Written into
# central storage at install time by ``SkillStorage._write_metadata`` and
# into rendered/copied platform dirs by ``write_skill_marker``.
# ``clean_orphan_skills`` only removes dirs carrying this marker.
SKILL_MARKER_FILE = ".vibe-manifest.json"


def write_skill_marker(
    skill_dir: Path,
    skill_id: str,
    source_type: str,
    source_path: str = "",
) -> None:
    """Write a vibe-ownership marker into a rendered/copied skill directory.

    Minimal companion to ``SkillStorage._write_metadata`` (which writes the
    full SkillManifest into central storage).  Rendered platform dirs lack
    full source metadata, so only ownership-identifying fields are written
    and no checksum is fabricated.  Does nothing when a marker already
    exists (e.g. carried over by copytree from central storage) — the
    source marker always wins.

    Args:
        skill_dir: Skill directory receiving the marker
        skill_id: Skill identifier recorded in the marker
        source_type: Origin kind, e.g. "render" or "pack-copy"
        source_path: Optional origin path for copy provenance
    """
    marker_path = skill_dir / SKILL_MARKER_FILE
    if marker_path.exists():
        return
    payload = {
        "id": skill_id,
        "source": {
            "type": source_type,
            "path": source_path,
            "version": None,
            "ref": None,
        },
    }
    marker_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
        """Remove vibe-managed skill directories not present in the manifest.

        After rendering, any skill directory in ``output_dir/skills/``
        whose name does not correspond to a skill in the manifest is
        considered an orphan.  Only vibe-managed orphans are removed —
        a directory is vibe-managed when it contains a
        ``.vibe-manifest.json`` marker, written either at install time
        by :meth:`SkillStorage._write_metadata` or at render/copy time
        by :func:`write_skill_marker`.  Directories without a marker
        are treated as user/third-party content and are skipped
        untouched (counted in a summary log).  Orphan symlinks are
        unlinked as before.

        This prevents stale skills from lingering in platform configs
        after they have been deleted from the registry, without
        deleting user-owned skills in shared directories.

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
        skipped_user_owned = 0
        for item in skills_dir.iterdir():
            if not item.is_dir() and not item.is_symlink():
                continue
            if item.name.startswith("."):
                continue
            if item.name not in expected_dirs:
                if item.is_symlink():
                    # Orphan symlinks are unlinked (existing behavior).
                    try:
                        item.unlink(missing_ok=True)
                        removed.append(item)
                    except OSError as e:
                        logger.debug(f"Failed to remove orphan skill symlink {item}: {e}")
                elif (item / SKILL_MARKER_FILE).exists():
                    # Only remove orphans that vibe manages (marker file
                    # written at install/render/copy time); user-owned
                    # dirs are kept.
                    try:
                        shutil.rmtree(item)
                        removed.append(item)
                    except OSError as e:
                        logger.debug(f"Failed to remove orphan skill dir {item}: {e}")
                else:
                    skipped_user_owned += 1
                    logger.debug(
                        f"Skipping orphan skill dir {item}: no {SKILL_MARKER_FILE}, "
                        "treating as user-owned content"
                    )

        if skipped_user_owned:
            logger.info(
                "Orphan cleanup: skipped %d user-owned skill dir(s) without %s",
                skipped_user_owned,
                SKILL_MARKER_FILE,
            )

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
        # Do NOT resolve the target first: a symlink inside the intended
        # output tree would be followed silently and the safety check would
        # re-anchor at the resolved parent — outside the tree the caller
        # meant to protect. PathSafety works on the lexical path and refuses
        # symlinks in the chain (v7.0.8 layered defense), so pass the
        # unresolved path through.
        # R1 (B1): a caller that cares about links ABOVE the file's parent
        # (e.g. a project tree whose ``skills/`` root was replaced by a
        # symlink into a central install) MUST pass the trusted output root
        # explicitly as base_dir. The no-anchor fallback anchors at the
        # lexical parent and can only refuse symlinks at or below it — a
        # symlinked ancestor above the parent is positionally
        # indistinguishable from a macOS ``/var`` system alias, so it cannot
        # be rejected without a declared trusted root.
        # NOTE: intentionally os.path.abspath (not Path.resolve) — must NOT
        # resolve symlinks, per the lexical-anchor defense above.
        raw_path = Path(os.path.abspath(str(Path(path).expanduser())))  # noqa: PTH100

        if base_dir is None:
            # No explicit caller anchor: anchor at the lexical parent of the
            # *intended* path, so a pre-existing platform skill symlink can
            # no longer redirect the write into a central install (D02).
            anchor = raw_path.parent
            if anchor.is_symlink():
                msg = f"Refusing to write through symlinked directory: {anchor}"
                raise PathTraversalError(
                    message=msg,
                    path=str(path),
                    base_dir=str(anchor),
                )
        else:
            # Caller-declared trusted root: symlinks at or below it on the
            # lexical path are refused by check_traversal below, including
            # ancestors of the file's parent (R1).
            anchor = Path(os.path.abspath(str(Path(base_dir).expanduser())))  # noqa: PTH100

        # Refuse any symlink at or below the anchor on the lexical path —
        # that is where a caller-tree link could redirect the write (D02).
        # Symlinks strictly ABOVE the anchor (e.g. macOS /var -> /private/var)
        # are system-level indirection and are tolerated by re-basing both
        # anchor and path into the resolved world below.
        if not self._path_safety.check_traversal(raw_path, anchor):
            msg = f"Path traversal detected: {path} is not safely contained in {anchor}"
            raise PathTraversalError(
                message=msg,
                path=str(path),
                base_dir=str(anchor),
            )

        anchor_resolved = anchor.resolve()
        rel = os.path.relpath(str(raw_path), str(anchor))
        candidate = Path(os.path.normpath(str(anchor_resolved / rel)))

        # Validate path safety (and create parents inside the validated tree)
        safe_path = self._path_safety.ensure_safe_output_path(
            candidate,
            anchor_resolved,
            create_parents=True,
        )

        # Validate content security if enabled
        if validate_security and self._security_scanner:
            scan_result = self._security_scanner.scan(content)
            if not scan_result.safe:
                msg = f"Content contains security threats: {scan_result.summary}"
                raise ValueError(msg)

        # Write to an exclusively-created temporary file (R2/B1): a fixed
        # ``<target>.tmp`` name could be pre-planted as a symlink, and
        # ``write_text`` would then follow it and overwrite the link target
        # before ``replace`` moved the link over the real file. O_CREAT|O_EXCL
        # on a random name inside the already validated parent directory gives
        # the same never-a-symlink guarantee as mkstemp, while mode 0o666
        # keeps umask-based permissions (mkstemp forces 0600, which silently
        # tightened rendered configs on POSIX).
        import secrets

        fd: int | None = None
        tmp_path = safe_path.parent
        for _ in range(5):
            tmp_path = safe_path.parent / f"{safe_path.name}.{secrets.token_hex(8)}.tmp"
            try:
                fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
                break
            except FileExistsError:
                continue
        if fd is None:
            raise OSError(f"could not exclusively create a temp file for {safe_path}")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            # Atomic rename
            tmp_path.replace(safe_path)
        finally:
            # Clean up temp file only if we still own it (write/replace
            # failed before the rename consumed it).
            tmp_path.unlink(missing_ok=True)

    def _assert_safe_render_path(
        self,
        path: Path,
        base_dir: Path,
        *,
        allow_leaf_symlink: bool = False,
    ) -> None:
        """Validate a render target against the trusted output root BEFORE any
        mkdir/marker/copy side effect (R1/B1 second review).

        Refuses (PathTraversalError) when any component at or below
        ``base_dir`` on the lexical path to ``path`` is a symlink. With
        ``allow_leaf_symlink=True`` the leaf itself is exempt: a pre-existing
        per-skill symlink into a central pack install is a legal
        platform-installed link whose central content must be preserved
        (``_render_skill_content`` keeps the link and skips the central
        rewrite); only the ancestors above the leaf must be real. The skills
        root itself must always be validated with ``allow_leaf_symlink=False``
        — a symlinked skills root is the ancestor-link attack, not a legal
        per-skill link.

        Production ``render_config`` callers must always pass the resolved
        output root as ``base_dir``: the root-less write fallback in
        ``write_file_atomic`` anchors at the direct parent and can only
        protect that parent, never ancestors above it.
        """
        # NOTE: intentionally os.path.abspath (not Path.resolve) — must NOT
        # resolve symlinks, per the lexical-anchor defense in write_file_atomic.
        anchor = Path(os.path.abspath(str(Path(base_dir).expanduser())))  # noqa: PTH100
        check_path = Path(path).parent if allow_leaf_symlink else Path(path)
        raw = Path(os.path.abspath(str(Path(check_path).expanduser())))  # noqa: PTH100

        if not self._path_safety.check_traversal(raw, anchor):
            msg = (
                f"Unsafe render target: {path} crosses a symlinked component "
                f"inside trusted output root {anchor} — refusing before mkdir"
            )
            raise PathTraversalError(
                message=msg,
                path=str(path),
                base_dir=str(anchor),
            )

        # The leaf exemption exists for legal per-skill SYMLINKS into a
        # central install. A directory junction is never one of those (the
        # installer renders real copies on Windows, never junctions), and
        # junctions need no symlink privilege to create — refuse a junction
        # leaf even under the exemption, or every junction-based chain
        # defense upstream is void the moment the junction IS the leaf.
        if allow_leaf_symlink and Path(path).is_junction():
            msg = (
                f"Unsafe render target: {path} is a directory junction inside "
                f"trusted output root {anchor} — junctions are not legal "
                "per-skill links"
            )
            raise PathTraversalError(
                message=msg,
                path=str(path),
                base_dir=str(anchor),
            )

    def _prepare_skill_dir(self, skill_dir: Path) -> None:
        """Make ``skill_dir`` a real directory, recovering dangling leaf links.

        A dangling per-skill symlink (its target was deleted) makes
        ``mkdir(exist_ok=True)`` raise ``FileExistsError`` — the link exists
        but is not a directory. Unlink it first so the render can recreate a
        real directory. The same applies to a dangling Windows junction
        (``is_symlink()`` is False for junctions; ``rmdir`` removes only the
        reparse point, never the target). Live links are left untouched;
        keeping or replacing them is the render path's decision. Call after
        ``_assert_safe_render_path``, before any mkdir.
        """
        if skill_dir.is_symlink():
            if not skill_dir.exists():
                skill_dir.unlink()
        elif skill_dir.is_junction() and not skill_dir.exists():
            skill_dir.rmdir()
        skill_dir.mkdir(parents=True, exist_ok=True)

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
            # manifest version is a config-format constant ("1.0.0") — useless
            # as a deployment-freshness marker. Templates rendering
            # "Generated by VibeSOP vX" must bind vibesop_version (the package
            # version) so `vibe doctor` staleness comparison is meaningful.
            "version": manifest.metadata.version,
            "vibesop_version": __version__,
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
        base_dir: Path | None = None,
    ) -> None:
        """Render skill content from actual skill file or central storage.

        Shared logic for all adapters:
        1. Try to find existing skill content
        2. Try to symlink/copy from installed pack
        3. Fall back to adapter-specific template generation

        Subclasses override ``_fallback_skill_content()`` for step 3.

        Args:
            base_dir: Trusted platform output root declared by the caller
                (``render_config``). Passed to ``write_file_atomic`` so any
                symlink at or below the output root — including ancestors of
                the skill dir, e.g. a project-tree ``skills/`` replaced by a
                link into a central install — is refused instead of silently
                redirecting the write outside the tree (R1/B1).
        """
        import shutil

        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        skill_output_path = skill_dir / "SKILL.md"

        skill_content = self._find_skill_content(skill_id)

        if skill_content:
            skill_content = self._normalize_skill_type(skill_content)
            if skill_dir.is_symlink():
                if skill_dir.exists():
                    # Pre-existing platform skill symlink (typically into a
                    # central pack install). Writing the project-local content
                    # through it would overwrite the shared central SKILL.md
                    # and drop an ownership marker into central storage —
                    # the same "skip the central rewrite" semantics as the
                    # pack-installed branch below (D02). Keep the link, keep
                    # the render idempotent, touch nothing.
                    result.add_file(skill_output_path)
                    return
                # Dangling link: recreate as a real directory below.
                skill_dir.unlink(missing_ok=True)
            self.write_file_atomic(
                skill_output_path, skill_content, validate_security=False, base_dir=base_dir
            )
            # Ownership marker so clean_orphan_skills can reclaim this dir
            # once the skill leaves the manifest.
            try:
                write_skill_marker(skill_dir, skill_id, "render")
            except OSError as e:
                logger.warning("skill rendered but marker write failed for %s: %s", skill_dir, e)
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
                # The two marker writes are deliberately decoupled: a failure
                # of the copy-source marker must not skip the ownership marker
                # (an unmarked copy would never be orphan-cleaned).
                try:
                    from vibesop.core.skills.storage import write_copy_source_marker

                    write_copy_source_marker(skill_dir, resolved_installed)
                except OSError as marker_err:
                    logger.warning(
                        "copy succeeded but copy-source marker write failed for %s: %s",
                        skill_dir,
                        marker_err,
                    )
                try:
                    # Ownership marker for orphan cleanup; keeps the source
                    # marker if copytree already carried one over.
                    write_skill_marker(skill_dir, skill_id, "pack-copy", str(resolved_installed))
                except OSError as marker_err:
                    logger.warning(
                        "copy succeeded but ownership marker write failed for %s: %s",
                        skill_dir,
                        marker_err,
                    )
                result.add_file(skill_output_path)
                return

        # A pre-existing legal per-skill symlink must survive the fallback
        # too — keep the link and skip, mirroring the content paths above;
        # writing through it would trip the write-time leaf-link refusal and
        # abort the whole render. Enforced HERE at the dispatch site so
        # subclass overrides of _fallback_skill_content (Jinja2 templates,
        # pi/claude_code) inherit the contract.
        if skill_dir.is_symlink():
            if skill_dir.exists():
                result.add_file(skill_output_path)
                return
            # Dangling link: drop it so the fallback write recreates a real
            # directory.
            skill_dir.unlink(missing_ok=True)

        self._fallback_skill_content(
            skill,
            skill_output_path,
            result,
            dir_name=dir_name,
            manifest=manifest,
            base_dir=base_dir,
        )

    def _fallback_skill_content(
        self,
        skill: Any,
        skill_output_path: Path,
        result: RenderResult,
        *,
        dir_name: str | None = None,
        manifest: Manifest | None = None,  # noqa: ARG002
        base_dir: Path | None = None,
    ) -> None:
        """Generate fallback skill content when no real content exists.

        Default: use the shared fallback generator. Subclasses (e.g. ClaudeCode)
        override this to use Jinja2 templates instead.

        A pre-existing legal per-skill symlink (typically into a central pack
        install) is kept and left untouched, mirroring the main render path —
        writing through it would both mutate the central content and trip the
        ``write_file_atomic`` leaf-link refusal, aborting the whole render.
        """
        skill_dir = skill_output_path.parent
        if skill_dir.is_symlink():
            if skill_dir.exists():
                result.add_file(skill_output_path)
                return
            # Dangling link: drop it so the write below recreates a real dir.
            skill_dir.unlink(missing_ok=True)

        fallback_content = self._generate_fallback_skill_content(skill, dir_name=dir_name)
        self.write_file_atomic(
            skill_output_path, fallback_content, validate_security=False, base_dir=base_dir
        )
        result.add_file(skill_output_path)
