"""SDK-based platform adapter — reference implementation for SDK-driven platforms.

SDK-based platforms (e.g. Pi Coding Agent) integrate via native extensions
(TypeScript, Python) instead of shell hooks. The pipeline produces:

  - A main context file (AGENTS.md) with routing protocol
  - extensions/ directory with TypeScript route/track interceptors
  - prompts/ directory with prompt templates for slash commands
  - docs/ directory with on-demand reference documentation
  - settings.json registering extensions, skills, and prompts
  - skills/ directory with skill definitions

Subclasses override:
  - platform_name, config_dir
  - _get_template_dir() — Jinja2 template directory
  - _render_settings_json() — platform-specific extension registration
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import Manifest, RenderResult

logger = logging.getLogger(__name__)


class SdkBasedAdapter(PlatformAdapter):
    """Base class for SDK-based platform integrations.

    Provides Jinja2 template rendering infrastructure and extension
    registration patterns shared by platforms that use native SDK
    extensions for event interception.
    """

    _template_env: Environment | None = None

    # ---- Subclasses MUST override ----
    def _get_template_dir(self) -> Path:
        """Return the path to the platform's Jinja2 template directory."""
        raise NotImplementedError

    @property
    def platform_name(self) -> str:
        raise NotImplementedError

    @property
    def config_dir(self) -> Path:
        raise NotImplementedError

    # ---- Jinja2 template infrastructure ----
    def _get_template_env(self) -> Environment:
        """Lazy-initialize and return the Jinja2 template environment."""
        if self._template_env is None:
            from vibesop.utils.jinja_safety import make_shell_safe_env

            self._template_env = make_shell_safe_env(
                loader=FileSystemLoader(self._get_template_dir()),
                autoescape=select_autoescape(),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._template_env

    def _render_and_write(
        self,
        template_name: str,
        output_path: Path,
        manifest: Manifest,
        result: RenderResult,
        validate_security: bool = True,
        **extra_context: Any,
    ) -> None:
        """Render a Jinja2 template and write it atomically to disk."""
        try:
            env = self._get_template_env()
            template = env.get_template(template_name)
            context = self.get_template_context(manifest)
            context.update(extra_context)
            content = template.render(**context)
            self.write_file_atomic(output_path, content, validate_security=validate_security)
            result.add_file(output_path)
        except Exception as e:
            result.add_error(f"Failed to render {template_name}: {e}")

    # ---- Settings JSON ----
    def _render_settings_json(
        self,
        output_dir: Path,
        _manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render settings.json with extension and skill registration.

        Subclasses should override to register platform-specific extensions.
        """
        settings: dict[str, Any] = {
            "extensions": ["extensions/vibesop-route.ts", "extensions/vibesop-track.ts"],
            "skills": ["skills"],
            "prompts": ["prompts"],
        }

        settings_path = output_dir / "settings.json"
        if settings_path.exists():
            try:
                existing = json.loads(settings_path.read_text())
                if isinstance(existing, dict):
                    settings = {**existing, **settings}
            except (json.JSONDecodeError, OSError):
                pass

        self.write_file_atomic(
            settings_path,
            json.dumps(settings, indent=2),
            validate_security=False,
        )
        result.add_file(settings_path)

    # ---- Extension rendering ----
    def _render_extension(self, template_name: str, version: str = "0.0.0") -> str:
        """Render an extension template standalone (without manifest context)."""
        try:
            env = self._get_template_env()
            template = env.get_template(f"extensions/{template_name}")
            return template.render(version=version)
        except Exception as e:
            logger.warning(f"Failed to render extension template {template_name}: {e}")
            return ""
