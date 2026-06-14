"""Hook-based platform adapter — reference implementation for hook-driven platforms.

Hook-based platforms (e.g. Claude Code) intercept events via shell scripts
registered in settings.json hooks. The pipeline produces:

  - A main context file (CLAUDE.md) with routing protocol
  - rules/ directory with always-loaded behavior rules
  - docs/ directory with on-demand reference documentation
  - hooks/ directory with shell scripts (route interceptor, session tracker)
  - settings.json registering hooks via the platform's hook system
  - skills/ directory with skill definitions

Subclasses override:
  - platform_name, config_dir
  - _get_template_dir() — Jinja2 template directory
  - _render_settings_json() — platform-specific hook registration
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


class HookBasedAdapter(PlatformAdapter):
    """Base class for hook-based platform integrations.

    Provides Jinja2 template rendering infrastructure and hook registration
    patterns shared by platforms that use shell hooks for event interception.
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

    # ---- Hook rendering utilities ----
    def _render_route_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-route.sh hook script using the shared template."""
        try:
            from vibesop.adapters._shared import render_route_hook as _shared_route_hook

            hook_content = _shared_route_hook(
                platform=self.platform_name,
                platform_name=self._get_platform_label(),
                purpose=self._get_hook_purpose(),
                hook_event_name=self._get_hook_event_name(),
                enable_explicit_overrides=self._get_enable_explicit_overrides(),
                enable_orchestration=self._get_enable_orchestration(),
                include_additional_context=self._get_include_additional_context(),
                no_match_message=self._get_no_match_message(),
            )
            hook_path = output_dir / "hooks" / "vibesop-route.sh"
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-route.sh: {e}")

    # ---- Hook configuration (subclasses may override) ----
    def _get_platform_label(self) -> str:
        """Human-readable platform name for hook script headers."""
        return self.platform_name.replace("-", " ").title()

    def _get_hook_purpose(self) -> str:
        """One-line description for the route hook script header."""
        return "Route user queries to VibeSOP skills"

    def _get_hook_event_name(self) -> str:
        """Platform hook event name (e.g. 'UserPromptSubmit')."""
        return ""

    def _get_enable_explicit_overrides(self) -> bool:
        return True

    def _get_enable_orchestration(self) -> bool:
        return True

    def _get_include_additional_context(self) -> bool:
        return False

    def _get_no_match_message(self) -> bool:
        return False

    # ---- Settings JSON ----
    def _render_settings_json(
        self,
        output_dir: Path,
        _manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render settings.json with hook registration.

        Subclasses should override to register platform-specific hooks.
        """
        hooks_dir = output_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        settings: dict[str, Any] = {}

        existing_path = output_dir / "settings.json"
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text())
                if isinstance(existing, dict):
                    settings = existing
            except (json.JSONDecodeError, OSError):
                pass

        settings.setdefault("hooks", {})["UserPromptSubmit"] = [{
            "matcher": "",
            "hooks": [{
                "type": "command",
                "command": f"bash {hooks_dir}/vibesop-route.sh",
            }],
        }]

        settings_path = output_dir / "settings.json"
        self.write_file_atomic(
            settings_path,
            json.dumps(settings, indent=2),
            validate_security=False,
        )
        result.add_file(settings_path)
