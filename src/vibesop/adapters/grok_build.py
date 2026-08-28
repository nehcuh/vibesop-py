"""Grok Build platform adapter.

Grok Build natively supports JSON hooks (``~/.grok/hooks/*.json``),
rules (``~/.grok/rules/*.md``), and skills (``~/.grok/skills/``).
This adapter deploys directly to ``~/.grok/`` without depending on
Claude Code compatibility shims.

Key differences from Claude Code adapter:
- JSON hook format (no shell script dependency; works on Windows native exe)
- ``~/.grok/rules/`` for always-loaded rules (Grok-native, not ``~/.claude/rules/``)
- ``~/.grok/skills/`` for skills (Grok-native)
- AGENTS.md is project-level, deployed separately by QuickBuilder
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.adapters.base import PlatformAdapter
from vibesop.adapters.models import RenderResult

if TYPE_CHECKING:
    from vibesop.adapters.models import Manifest

logger = logging.getLogger(__name__)


class GrokBuildAdapter(PlatformAdapter):
    """Adapter for Grok Build platform.

    Deploys only routing rules and JSON hooks — does **not** manage
    ``~/.grok/skills/``, so orphan cleanup is disabled to avoid
    deleting Grok's own builtin skills.

    Hooks deployed: ``vibesop-route.json`` (UserPromptSubmit → routing)
    and, when ``sequences.enabled`` (default true), ``vibesop-tool-seq.json``
    (PostToolUse → tool-sequence capture for M12 behavior evidence, gate33).
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        super().__init__()
        self._project_root = Path(project_root).resolve()

    cli_binary: str = "grok"

    # Grok Build adapter does NOT deploy skills (only rules + hooks).
    # The ``~/.grok/skills/`` directory may contain Grok's own builtin
    # skills — orphan cleanup must not touch them.
    manages_skills: bool = False

    @property
    def platform_name(self) -> str:
        return "grok-build"

    @property
    def config_dir(self) -> Path:
        return Path("~/.grok").expanduser()

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render Grok Build configuration.

        Generates:
          - ~/.grok/rules/routing.md (routing protocol, always loaded)
          - ~/.grok/hooks/vibesop-route.json (UserPromptSubmit hook)
          - ~/.grok/hooks/vibesop-tool-seq.json (PostToolUse capture hook,
            only when ``sequences.enabled`` — gate33)
        """
        result = self.create_render_result(success=True)

        try:
            errors = self.validate_manifest(manifest)
            if errors:
                for error in errors:
                    result.add_error(error)
                result.success = False
                return result

            output_dir.mkdir(parents=True, exist_ok=True)

            # --- rules/ ---
            rules_dir = output_dir / "rules"
            rules_dir.mkdir(exist_ok=True)

            routing_md = rules_dir / "routing.md"
            routing_md.write_text(self._render_routing_rule(), encoding="utf-8")
            result.add_file(routing_md)

            # --- hooks/ ---
            hooks_dir = output_dir / "hooks"
            hooks_dir.mkdir(exist_ok=True)

            hook_file = hooks_dir / "vibesop-route.json"
            hook_file.write_text(self._render_hook_json(), encoding="utf-8")
            result.add_file(hook_file)

            # gate33: PostToolUse tool-sequence capture (M12 behavior
            # evidence). Grok's hook stdin envelope is camelCase
            # (``toolName``/``sessionId`` — NOT Claude's snake_case;
            # gate33 pi BLOCK-1, verified against grok's hooks user guide);
            # ``vibe sequence record-tool`` accepts both casings and is the
            # existing cross-platform capture entry — no shell script
            # needed, keeping this adapter Windows-native.
            if self._sequences_enabled():
                tool_seq_file = hooks_dir / "vibesop-tool-seq.json"
                tool_seq_file.write_text(self._render_tool_seq_hook_json(), encoding="utf-8")
                result.add_file(tool_seq_file)

            result.success = True

        except Exception as e:
            result.add_error(f"Render failed: {e}")
            result.success = False

        return result

    def validate_manifest(self, manifest: Manifest) -> list[str]:
        errors: list[str] = []
        meta = manifest.metadata
        if meta.platform != "grok-build":
            errors.append(f"Platform mismatch: expected 'grok-build', got '{meta.platform}'")
        return errors

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "hooks": {
                    "type": "object",
                    "description": "UserPromptSubmit hook — calls vibe route",
                },
            },
        }

    # -- Private helpers ------------------------------------------------------

    def _count_builtin_skills(self) -> int:
        """Count builtin skill dirs via ``resolve_builtin_skills_dir``.

        Project-root-aware: a foreign ``<root>/core/skills`` never shadows
        the wheel bundle (identity-gated resolution).
        """
        from vibesop.utils.bundled import resolve_builtin_skills_dir

        base = resolve_builtin_skills_dir(self._project_root)
        if not base.is_dir():
            return 0
        return sum(1 for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))

    def _render_routing_rule(self) -> str:
        # Count builtins at render time — a hardcoded number rots on every
        # skill addition (gate46 dual-review NIT).
        builtin_count = self._count_builtin_skills()
        return f"""# VibeSOP Routing Protocol

> **Generated by VibeSOP** — Grok Build native adapter

## Routing

Routing is automatic when the `vibesop-route` hook is installed. If this
turn's hook injection — the `systemMessage`/`additionalContext` the hook
adds to the turn context — contains `VibeSOP routed:`, `[ACTIVE SKILL:`,
`NEXT STEP (MANDATORY): read`, or `VibeSOP: No matching skill found`,
routing has already run for this turn: follow that result and do NOT
re-run `vibe route`.

If no such injection is present on this turn (hook not installed or
failed), call `vibe route` to find the best skill:

```bash
vibe route "<user_request>"
```

Then read the matched skill's SKILL.md and follow its instructions.

## How It Works

1. You type a request in Grok Build.
2. The `vibesop-route` hook intercepts it via `UserPromptSubmit`.
3. `vibe route` matches the best skill from the built-in pool ({builtin_count} skills; grows
   with `vibe install <pack>`).
4. The skill's instructions are injected into your context.

## Supported Commands

| Command | Purpose |
|---------|---------|
| `vibe route "<query>"` | Match best skill for a query |
| `vibe skills list` | List installed skills |
| `vibe doctor` | Check environment health |

## Session Lifecycle

When the user signals session end ("that's all", "收工", `/session-end`, etc.),
run `session-end` to flush session state.

For full documentation: read `docs/routing-protocol.md` in the VibeSOP project.
"""

    @staticmethod
    def _render_hook_json() -> str:
        # No ``matcher`` on UserPromptSubmit — Grok ignores it with a warning
        # (those events always fire). Empty matcher is the Claude-style form.
        hook_config = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "vibe route --hook --platform grok-build",
                                "timeout": 30,
                            }
                        ],
                    }
                ],
            },
        }
        return json.dumps(hook_config, indent=2) + "\n"

    def _sequences_enabled(self) -> bool:
        """Read the ``sequences.enabled`` switch (default true).

        Same reading pattern as the kimi/claude adapters — env vars arrive
        as raw strings. Fail-open on config errors: capture is local-only
        telemetry, and a broken config must not silently disable it.
        """
        try:
            from vibesop.core.config.manager import ConfigManager

            enabled = ConfigManager(self._project_root).get("sequences.enabled", True)
            if isinstance(enabled, str):  # env vars are returned as raw strings
                enabled = enabled.strip().lower() in ("true", "1", "yes", "on")
            return bool(enabled)
        except Exception:
            logger.debug("sequences.enabled lookup failed, defaulting to enabled", exc_info=True)
            return True

    @staticmethod
    def _render_tool_seq_hook_json() -> str:
        """PostToolUse capture hook (gate33).

        Empty matcher = all tools (behavior evidence needs the full
        sequence, not just edits). The capture command is observation-only:
        ``record-tool`` persists only tool name + timestamp + session id
        (never tool_input) and always exits 0, so a capture failure can
        never block the host agent. No ``statusMessage`` — capture should
        be invisible.
        """
        hook_config = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "vibe sequence record-tool",
                                "timeout": 10,
                            }
                        ],
                    }
                ],
            },
        }
        return json.dumps(hook_config, indent=2) + "\n"
