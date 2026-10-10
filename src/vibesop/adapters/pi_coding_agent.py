"""Pi Coding Agent platform adapter.

The Pi adapter generates configuration for the Pi coding agent harness,
including AGENTS.md context file, TypeScript extensions for route interception
and session tracking, skill deployments, and prompt templates.

Pi differs from Claude Code in several key ways:
- Uses AGENTS.md instead of CLAUDE.md for context
- Uses TypeScript extensions instead of shell hooks for event interception
- Uses prompt templates (.pi/prompts/) instead of slash commands
- Uses the Agent Skills standard (SKILL.md) for skills
- Has no built-in slash command system — extensions register commands
"""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from vibesop.adapters.models import Manifest, RenderResult
from vibesop.adapters.sdk_based import SdkBasedAdapter

logger = logging.getLogger(__name__)


class PiCodingAgentAdapter(SdkBasedAdapter):
    """Adapter for Pi Coding Agent platform (SDK-based integration pattern)."""

    def __init__(self, project_root: str | Path = ".") -> None:
        super().__init__()
        self._project_root = Path(project_root).resolve()

    cli_binary = "pi"

    @property
    def platform_name(self) -> str:
        return "pi"

    @property
    def config_dir(self) -> Path:
        # Write to project-local .pi/ directory (Pi auto-discovers from here)
        # Note: Pi also auto-discovers from ~/.pi/agent/ globally,
        # but VibeSOP deploys per-project so .pi/ is the right target.
        return self._project_root / ".pi"

    def _get_template_dir(self) -> Path:
        return Path(__file__).parent / "templates" / "pi"

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Pi Coding Agent configuration from manifest."""
        result = self.create_render_result(success=True)

        try:
            # Validate manifest
            errors = self.validate_manifest(manifest)
            if errors:
                for error in errors:
                    result.add_error(error)
                result.success = False
                return result

            # Ensure output directory exists
            output_dir = self.ensure_output_dir(output_dir)

            # Validate the skills root against the trusted output root BEFORE
            # any mkdir — a symlinked skills root must not let mkdir create
            # directories inside a central install (R1/B1).
            skills_root = output_dir / "skills"
            self._assert_safe_render_path(skills_root, output_dir)

            # Create directory structure
            (output_dir / "extensions").mkdir(exist_ok=True)
            skills_root.mkdir(exist_ok=True)
            (output_dir / "prompts").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)

            # Render main AGENTS.md to project root (Pi discovers from cwd/parent dirs)
            self._render_and_write(
                "AGENTS.md.j2",
                self._project_root / "AGENTS.md",
                manifest,
                result,
                validate_security=False,
            )

            # Write project-level AGENTS.md only if different from global (~/.pi/agent/)
            self._render_project_agents_md(manifest, result)

            # Render extensions
            self._render_and_write(
                "extensions/vibesop-route.ts.j2",
                output_dir / "extensions" / "vibesop-route.ts",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "extensions/vibesop-track.ts.j2",
                output_dir / "extensions" / "vibesop-track.ts",
                manifest,
                result,
                validate_security=False,
            )

            # Render settings.json
            self._render_settings_json(output_dir, manifest, result)

            # Render docs
            doc_templates = [
                "session-lifecycle.md.j2",
                "routing-protocol.md.j2",
                "safety.md.j2",
                "skills.md.j2",
                "task-routing.md.j2",
            ]
            for doc_template in doc_templates:
                base_name = doc_template.replace(".j2", "")
                self._render_and_write(
                    f"docs/{doc_template}",
                    output_dir / "docs" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

            # Render prompt templates for vibe commands
            prompt_templates = [
                "vibe-route.md.j2",
                "vibe-install.md.j2",
                "vibe-list.md.j2",
                "vibe-help.md.j2",
                "vibe-orchestrate.md.j2",
            ]
            for template_name in prompt_templates:
                base_name = template_name.replace(".j2", "")
                self._render_and_write(
                    f"prompts/{template_name}",
                    output_dir / "prompts" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

            # Render skill definitions
            for skill in manifest.skills:
                dir_name = skill.id.replace("/", "-")
                skill_dir = skills_root / dir_name
                self._assert_safe_render_path(skill_dir, output_dir, allow_leaf_symlink=True)
                self._prepare_skill_dir(skill_dir)
                self._render_skill_content(
                    skill, skill_dir, result, manifest=manifest, base_dir=output_dir
                )

            # Clean orphan skills not in the current manifest
            self.clean_orphan_skills(manifest, output_dir)

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def render_config_only(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render configuration without skills."""
        result = self.create_render_result(success=True)

        try:
            errors = self.validate_manifest(manifest)
            if errors:
                for error in errors:
                    result.add_error(error)
                result.success = False
                return result

            output_dir = self.ensure_output_dir(output_dir)

            # Create directory structure (no skills/ directory)
            (output_dir / "extensions").mkdir(exist_ok=True)
            (output_dir / "prompts").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)

            # Render main AGENTS.md to project root (Pi discovers from cwd/parent dirs)
            self._render_and_write(
                "AGENTS.md.j2",
                self._project_root / "AGENTS.md",
                manifest,
                result,
                validate_security=False,
            )

            # Write project-level AGENTS.md only if different from global (~/.pi/agent/)
            self._render_project_agents_md(manifest, result)

            # Render extensions
            self._render_and_write(
                "extensions/vibesop-route.ts.j2",
                output_dir / "extensions" / "vibesop-route.ts",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "extensions/vibesop-track.ts.j2",
                output_dir / "extensions" / "vibesop-track.ts",
                manifest,
                result,
                validate_security=False,
            )

            # Render settings.json
            self._render_settings_json(output_dir, manifest, result)

            # Render docs
            doc_templates = [
                "session-lifecycle.md.j2",
                "routing-protocol.md.j2",
                "safety.md.j2",
                "skills.md.j2",
                "task-routing.md.j2",
            ]
            for doc_template in doc_templates:
                base_name = doc_template.replace(".j2", "")
                self._render_and_write(
                    f"docs/{doc_template}",
                    output_dir / "docs" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

            # Render prompt templates
            prompt_templates = [
                "vibe-route.md.j2",
                "vibe-install.md.j2",
                "vibe-list.md.j2",
                "vibe-help.md.j2",
                "vibe-orchestrate.md.j2",
            ]
            for template_name in prompt_templates:
                base_name = template_name.replace(".j2", "")
                self._render_and_write(
                    f"prompts/{template_name}",
                    output_dir / "prompts" / base_name,
                    manifest,
                    result,
                    validate_security=False,
                )

        except Exception as e:
            result.add_error(f"Failed to render configuration: {e}")
            result.success = False

        return result

    def _render_skill_content(
        self,
        skill: Any,
        skill_dir: Path,
        result: RenderResult,
        dir_name: str | None = None,
        manifest: Manifest | None = None,
        base_dir: Path | None = None,
    ) -> None:
        super()._render_skill_content(
            skill,
            skill_dir,
            result,
            dir_name=dir_name,
            manifest=manifest,
            base_dir=base_dir,
        )

        # Namespace external pack skills to avoid name collisions in pi agent.
        # Post-processing keeps the same trusted root so a symlink swapped in
        # after the pre-mkdir validation is still refused at write time.
        self._namespace_skill_name(skill, skill_dir, base_dir=base_dir)

    def _namespace_skill_name(
        self, skill: Any, skill_dir: Path, *, base_dir: Path | None = None
    ) -> None:
        """Prefix external skill names with pack namespace to avoid collisions.

        When multiple packs provide a skill named "qa", the pi agent's flat
        skill registry sees a collision.  Prefixing ``name: qa`` →
        ``name: gstack-qa`` ensures each pack's skills occupy a unique name.

        Also normalizes names to satisfy pi agent's ``[a-z0-9-]+`` rule by
        replacing ``/``, ``_``, and embedded quotes with hyphens.
        """
        skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
        if "/" not in skill_id:
            return  # builtin skill — no namespace needed

        namespace = skill_id.split("/", 1)[0]
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return

        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception:
            return

        if not content.startswith("---"):
            return

        parts = content.split("---", 2)
        if len(parts) < 3:
            return

        import re

        frontmatter = parts[1]

        # Extract current name value
        name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
        if not name_match:
            return

        current_name = name_match.group(1).strip()

        # Strip ALL leading namespace prefixes (handles double-prefix from
        # prior _namespace_skill_name runs: "gstack-gstack/browse" → "browse")
        ns_slash = namespace + "/"
        ns_prefix = namespace + "-"
        while current_name.startswith(ns_prefix) or current_name.startswith(ns_slash):
            if current_name.startswith(ns_slash):
                current_name = current_name[len(ns_slash) :]
            elif current_name.startswith(ns_prefix):
                current_name = current_name[len(ns_prefix) :]

        # Normalize to [a-z0-9-]: replace / _ and embedded quotes with -
        for char in ("/", "_", '"'):
            current_name = current_name.replace(char, "-")

        # Collapse consecutive hyphens
        while "--" in current_name:
            current_name = current_name.replace("--", "-")

        # Strip leading/trailing hyphens
        current_name = current_name.strip("-")

        # Always prefix namespace
        new_name = ns_prefix + current_name

        new_fm = re.sub(
            r"^name:\s*(.+)$",
            f"name: {new_name}",
            frontmatter,
            count=1,
            flags=re.MULTILINE,
        )
        new_content = f"---{new_fm}---{parts[2]}"

        # If the skill DIR is a symlink into a pack/central install (per-skill
        # platform link) we must replace the link with a real directory so we
        # don't mutate the original pack content — a file-level is_symlink
        # check misses this case because SKILL.md inside a linked dir is a
        # regular file, and a plain write_text through it would overwrite the
        # central install. The link target stays untouched; the platform gets
        # a private namespaced copy of the ENTIRE skill dir — copying only
        # SKILL.md would silently drop the pack's auxiliary files
        # (references/, scripts/) from the platform tree.
        #
        # The copy is staged next to the target and swapped in by rename. On
        # POSIX, rename atomically replaces the leaf link itself — no unlink
        # window (a link re-planted by a racer is replaced, never followed).
        # Windows rename refuses an existing target, so the link is dropped
        # first and a re-planted target then fails closed (FileExistsError)
        # instead of being written through. A failed copy leaves the original
        # link intact (on Windows a post-unlink replace failure fails closed
        # without it — the link is re-created on the next render). mkdtemp's
        # 0700 is reset to the rendered-dir norm
        # (0755), the directory-level twin of the write_file_atomic umask fix.
        if skill_dir.is_symlink():
            source_tree = skill_dir.resolve()
            staged = Path(tempfile.mkdtemp(prefix=f".{skill_dir.name}.copy-", dir=skill_dir.parent))
            succeeded = False
            try:
                shutil.copytree(source_tree, staged, symlinks=True, dirs_exist_ok=True)
                staged.chmod(0o755)
                if os.name == "posix":
                    staged.replace(skill_dir)
                else:
                    skill_dir.unlink()
                    staged.replace(skill_dir)
                succeeded = True
            finally:
                if not succeeded:
                    shutil.rmtree(staged, ignore_errors=True)
        elif skill_file.is_symlink():
            # File-level link inside a real dir: replace with a real file.
            skill_file.unlink()

        # Route through the guarded atomic write so the namespace rewrite
        # honors the same trusted output root (refuses symlinks at or below
        # it) instead of a plain write_text that would follow a swapped link.
        self.write_file_atomic(skill_file, new_content, validate_security=False, base_dir=base_dir)

    def _fallback_skill_content(
        self,
        skill: Any,
        skill_output_path: Path,
        result: RenderResult,
        *,
        dir_name: str | None = None,  # noqa: ARG002
        manifest: Manifest | None = None,  # noqa: ARG002
        base_dir: Path | None = None,
    ) -> None:
        from vibesop.adapters._shared import render_skill_md

        content = render_skill_md(skill)
        self.write_file_atomic(
            skill_output_path, content, validate_security=False, base_dir=base_dir
        )
        result.add_file(skill_output_path)

    def _render_project_agents_md(self, manifest: Manifest, result: RenderResult) -> None:
        """Write project-level AGENTS.md if it doesn't exist."""
        project_path = self._project_root / "AGENTS.md"
        config_path = Path("~/.pi/agent").expanduser() / "AGENTS.md"
        if project_path.resolve() != config_path.resolve() and not project_path.exists():
            self._render_and_write(
                "AGENTS.md.project.j2",
                project_path,
                manifest,
                result,
                validate_security=False,
            )

    def _render_settings_json(
        self,
        output_dir: Path,  # interface-conforming override signature
        _manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render settings.json with extension and skill configuration.

        Uses output_dir (the --output target) so deployment is self-contained.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        settings_path = output_dir / "settings.json"

        # Merge with existing settings if present
        settings: dict[str, Any] = {
            "extensions": [
                "extensions/vibesop-route.ts",
                "extensions/vibesop-track.ts",
            ],
            "skills": [
                "skills",
            ],
            "prompts": [
                "prompts",
            ],
        }

        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    # Merge — our keys take precedence
                    merged = {**existing, **settings}
                    settings = merged
            except (json.JSONDecodeError, OSError):
                pass

        self.write_file_atomic(
            settings_path,
            json.dumps(settings, indent=2),
            validate_security=False,
        )
        result.add_file(settings_path)

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json.schemastore.org/pi-settings.json",
            "title": "Pi Coding Agent Settings",
            "type": "object",
            "properties": {
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to extension files",
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to skill directories",
                },
                "prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to prompt template directories",
                },
            },
        }

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install Pi extensions and configuration.

        For Pi, this means ensuring the .pi/ directory has the right
        extensions and skills deployed.
        """
        results: dict[str, bool] = {}

        # Ensure .pi/extensions/ directory exists
        extensions_dir = config_dir / "extensions"
        extensions_dir.mkdir(parents=True, exist_ok=True)

        # Write the route interceptor extension
        route_ext_path = extensions_dir / "vibesop-route.ts"
        try:
            route_content = self._render_extension("vibesop-route.ts.j2")
            self.write_file_atomic(route_ext_path, route_content, validate_security=False)
            results["vibesop-route"] = True
        except Exception as e:
            logger.debug(f"Failed to write vibesop-route.ts: {e}")
            results["vibesop-route"] = False

        # Write the session tracker extension
        track_ext_path = extensions_dir / "vibesop-track.ts"
        try:
            track_content = self._render_extension("vibesop-track.ts.j2")
            self.write_file_atomic(track_ext_path, track_content, validate_security=False)
            results["vibesop-track"] = True
        except Exception as e:
            logger.debug(f"Failed to write vibesop-track.ts: {e}")
            results["vibesop-track"] = False

        return results

    def _render_extension(self, template_name: str) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Render an extension template standalone (without manifest context)."""
        try:
            from vibesop._version import __version__

            env = self._get_template_env()
            template = env.get_template(f"extensions/{template_name}")
            # Markers must bind the package version (vibe doctor freshness
            # compares against it); "0.0.0" would render a permanently stale
            # or unparseable "Generated by VibeSOP v" line.
            context = {
                "version": __version__,
                "vibesop_version": __version__,
            }
            return template.render(**context)
        except Exception as e:
            logger.warning(f"Failed to render extension template {template_name}: {e}")
            return ""
