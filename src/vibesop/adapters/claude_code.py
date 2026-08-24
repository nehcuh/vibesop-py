"""Claude Code platform adapter.

Refactored in v5.5.0 to inherit from HookBasedAdapter, sharing Jinja2
template infrastructure with the hook-based adapter reference pattern.
"""

import logging
from pathlib import Path
from typing import Any

from vibesop.adapters.hook_based import HookBasedAdapter
from vibesop.adapters.models import Manifest, RenderResult

logger = logging.getLogger(__name__)

_ROUTE_HOOK_MARKER = "vibesop-route.sh"
_MIRROR_PROMPT_HOOK_MARKER = "vibesop-mirror-prompt.sh"


def _hook_entry_matches(entry: Any, marker: str) -> bool:
    """Return True if any hook command in a settings.json entry contains marker."""
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(isinstance(hook, dict) and marker in str(hook.get("command", "")) for hook in hooks)


def strip_route_hook_from_layer(
    *,
    current_settings: Path,
    other_dir: Path,
    write_atomic: Any,
    warn: Any,
) -> None:
    """Remove vibesop-route.sh UserPromptSubmit entries from ``other_dir``.

    Shared by the adapter (post-render) and the deploy command (post-copy) so
    both writers converge to a single registration layer (gate41 MAJOR-2).
    ``write_atomic(path, content)`` persists the rewritten settings;
    ``warn(message)`` surfaces what happened. No-op when the other layer has
    no route-hook entries (or the file is missing / unparsable / same file).
    """
    import json

    other_settings = other_dir / "settings.json"
    if other_settings.resolve() == current_settings.resolve() or not other_settings.exists():
        return

    try:
        other = json.loads(other_settings.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        warn(f"Could not parse {other_settings} ({e}); skipping route-hook dedup across layers")
        return
    if not isinstance(other, dict):
        return

    other_hooks = other.get("hooks")
    if not isinstance(other_hooks, dict):
        return
    prompt_hooks = other_hooks.get("UserPromptSubmit")
    if not isinstance(prompt_hooks, list):
        return

    kept = [entry for entry in prompt_hooks if not _hook_entry_matches(entry, _ROUTE_HOOK_MARKER)]
    removed = len(prompt_hooks) - len(kept)
    if removed == 0:
        return

    if kept:
        other_hooks["UserPromptSubmit"] = kept
    else:
        other_hooks.pop("UserPromptSubmit", None)
    if not other_hooks:
        other.pop("hooks", None)
    write_atomic(other_settings, json.dumps(other, indent=2))

    # Report whether the other layer's (now unregistered) route script
    # forwards SESSION_ID — stale templates produce session-less spans.
    script_path = other_dir / "hooks" / _ROUTE_HOOK_MARKER
    try:
        script_text = script_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        script_note = "not found"
    except OSError:
        script_note = "unreadable"
    else:
        script_note = (
            "forwards SESSION_ID"
            if "SESSION_ID" in script_text
            else "does NOT forward SESSION_ID (stale template)"
        )

    warn(
        "Duplicate route-hook registration resolved: wrote "
        f"{current_settings}; removed {removed} vibesop-route.sh "
        f"UserPromptSubmit {'entry' if removed == 1 else 'entries'} from "
        f"{other_settings}. Other-layer script {script_path}: {script_note}."
    )


def _tool_seq_project_root(output_dir: Path) -> str:
    """Derive the project root a tool-seq hook should capture against.

    The hook lands in ``<output_dir>/hooks/``; mirroring the script's own
    ``_HOOK_DIR/../..`` convention, the project root (where ``.vibe/`` lives)
    is the parent of the config dir — e.g. ``<project>/.claude`` →
    ``<project>``, ``~/.claude`` → ``~`` (global capture, consistent with the
    global ``~/.vibe`` config location).
    """
    return str(output_dir.resolve().parent)


class ClaudeCodeAdapter(HookBasedAdapter):
    """Adapter for Claude Code platform."""

    def __init__(self, project_root: str | Path = ".") -> None:
        super().__init__()
        self._project_root = Path(project_root).resolve()

    cli_binary = "claude"

    @property
    def platform_name(self) -> str:
        return "claude-code"

    @property
    def config_dir(self) -> Path:
        return Path("~/.claude").expanduser()

    def build_prompt_chain(
        self,
        prompts: list[Any],
        output_dir: str | Path,
    ) -> str:
        """Write prompt chain files and a README for Claude Code.

        Args:
            prompts: List of PromptFile objects from PromptChainGenerator.
            output_dir: Target directory (usually .vibe/prompts).

        Returns:
            Path to the generated README.md.
        """
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)

        # Write each prompt file
        for pf in prompts:
            path = target / pf.filename
            self.write_file_atomic(path, pf.content, validate_security=False)

        # Generate README
        readme = self._generate_chain_readme(prompts)
        readme_path = target / "README.md"
        self.write_file_atomic(readme_path, readme, validate_security=False)
        return str(readme_path)

    def _generate_chain_readme(self, prompts: list[Any]) -> str:
        """Generate execution guide README from prompt chain."""
        from vibesop._version import __version__

        lines = [
            "# Prompt Chain — Execution Guide",
            "",
            "This directory contains a multi-phase prompt chain generated by VibeSOP.",
            "Execute each phase **in order**, verifying the checklist before proceeding.",
            "",
            "## Execution Order",
            "",
        ]

        for pf in prompts:
            phase_label = "Final" if pf.phase == -1 else f"Phase {pf.phase}"
            lines.append(f"### {phase_label}: {pf.name}")
            lines.append(f"File: `{pf.filename}`")
            if pf.prerequisites:
                lines.append("**Prerequisites:**")
                for p in pf.prerequisites:
                    lines.append(f"- [ ] {p}")
            lines.append("")

        lines.extend(
            [
                "## How to Execute",
                "",
                "1. Open each phase file in order",
                "2. Follow the instructions in the file",
                "3. Verify the checklist at the end of each phase",
                "4. Run `vibe route '<sub-task>'` when you need to dynamically select a skill",
                "",
                "```bash",
                "# Quick start: copy first phase to clipboard",
                "cat phase-0-*.md | pbcopy",
                "# Then paste into Claude Code",
                "```",
                "",
                "---",
                f"*Generated by VibeSOP {__version__}*",
            ]
        )

        return "\n".join(lines)

    # ---- Template directory ----
    def _get_template_dir(self) -> Path:
        return Path(__file__).parent / "templates" / "claude-code"

    # ---- Hook configuration overrides ----
    def _get_hook_purpose(self) -> str:
        return "Trigger VibeSOP routing and inject skill context"

    def _get_hook_event_name(self) -> str:
        return "UserPromptSubmit"

    def _get_include_additional_context(self) -> bool:
        return True

    def _get_no_match_message(self) -> bool:
        return True

    def _sequences_enabled(self) -> bool:
        """Read the ``sequences.enabled`` switch (default true).

        Same reading pattern as ``suggestions.enabled`` — env vars arrive as
        raw strings. Fail-open on config errors: capture is local-only
        telemetry, and a broken config must not silently disable it.
        """
        try:
            from vibesop.core.config.manager import ConfigManager

            enabled = ConfigManager(self._project_root).get("sequences.enabled", True)
            if isinstance(enabled, str):  # env vars are returned as raw strings
                enabled = enabled.strip().lower() in ("true", "1", "yes", "on")
            return bool(enabled)
        except Exception:
            logger.debug("sequences.enabled lookup failed, defaulting to enabled")
            return True

    def _conversation_mirror_enabled(self) -> bool:
        """Read the ``conversation_mirror.enabled`` switch (default false).

        Unlike ``sequences.enabled`` (default true), conversation mirror is
        opt-in: it captures user prompts verbatim, which may contain secrets,
        so the user must explicitly enable. Fail-closed on config errors —
        a broken config must not silently flip capture on.
        """
        try:
            from vibesop.core.config.manager import ConfigManager

            enabled = ConfigManager(self._project_root).get("conversation_mirror.enabled", False)
            if isinstance(enabled, str):  # env vars are returned as raw strings
                enabled = enabled.strip().lower() in ("true", "1", "yes", "on")
            return bool(enabled)
        except Exception:
            logger.debug("conversation_mirror.enabled lookup failed, defaulting to disabled")
            return False

    def render_config(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render full Claude Code configuration: config + skills."""
        result = self.render_config_only(manifest, output_dir)
        if not result.success:
            return result

        (output_dir / "skills").mkdir(exist_ok=True)

        # Render skill definitions — copy actual content from core/skills/
        for skill in manifest.skills:
            dir_name = skill.id.replace("/", "-")
            skill_dir = output_dir / "skills" / dir_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            self._render_skill_content(skill, skill_dir, result, manifest=manifest)

        return result

    def render_config_only(self, manifest: Manifest, output_dir: Path) -> RenderResult:
        """Render configuration without skills."""
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

            # Create directory structure (no skills/ directory)
            (output_dir / "rules").mkdir(exist_ok=True)
            (output_dir / "docs").mkdir(exist_ok=True)
            (output_dir / "hooks").mkdir(exist_ok=True)

            # Render main CLAUDE.md
            self._render_and_write(
                "CLAUDE.md.j2",
                output_dir / "CLAUDE.md",
                manifest,
                result,
                validate_security=False,
            )

            # Write project-level CLAUDE.md (Claude Code reads ./CLAUDE.md with highest priority)
            self._render_project_claude_md(manifest, result)

            # Render rules (always-loaded)
            self._render_and_write(
                "rules/behaviors.md.j2",
                output_dir / "rules" / "behaviors.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/routing.md.j2",
                output_dir / "rules" / "routing.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "rules/memory-flush.md.j2",
                output_dir / "rules" / "memory-flush.md",
                manifest,
                result,
                validate_security=False,
            )

            # Render docs (on-demand)
            self._render_and_write(
                "docs/routing-protocol.md.j2",
                output_dir / "docs" / "routing-protocol.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "docs/session-lifecycle.md.j2",
                output_dir / "docs" / "session-lifecycle.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "docs/safety.md.j2",
                output_dir / "docs" / "safety.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "docs/skills.md.j2",
                output_dir / "docs" / "skills.md",
                manifest,
                result,
                validate_security=False,
            )
            self._render_and_write(
                "docs/task-routing.md.j2",
                output_dir / "docs" / "task-routing.md",
                manifest,
                result,
                validate_security=False,
            )

            # Render settings.json
            self._render_settings_json(output_dir, manifest, result)

            # Render Agent Runtime hook scripts
            self._render_route_hook(output_dir, result)
            self._render_track_hook(output_dir, result)
            self._render_tool_seq_hook(output_dir, result)
            self._render_conversation_mirror_hooks(output_dir, result)

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
    ) -> None:
        super()._render_skill_content(
            skill,
            skill_dir,
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
        dir_name: str | None = None,  # noqa: ARG002
        manifest: Manifest | None = None,  # noqa: ARG002
    ) -> None:
        from vibesop.adapters._shared import render_skill_md

        content = render_skill_md(skill)
        self.write_file_atomic(skill_output_path, content, validate_security=False)
        result.add_file(skill_output_path)

    def _render_project_claude_md(self, manifest: Manifest, result: RenderResult) -> None:
        """Write project-level CLAUDE.md if it doesn't exist."""
        project_path = self._project_root / "CLAUDE.md"
        config_path = Path("~/.claude").expanduser() / "CLAUDE.md"
        if project_path.resolve() != config_path.resolve() and not project_path.exists():
            self._render_and_write(
                "CLAUDE.md.project.j2",
                project_path,
                manifest,
                result,
                validate_security=False,
            )

    def _render_settings_json(
        self,
        output_dir: Path,
        _manifest: Manifest,
        result: RenderResult,
    ) -> None:
        """Render settings.json with actual configuration values."""
        import json

        hooks_dir = output_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        settings: dict[str, Any] = {}

        # Preserve existing env/model, and keep existing non-route
        # UserPromptSubmit entries (e.g. conversation mirror) — merge
        # semantics instead of overwriting the hooks key wholesale; the
        # route hook entry itself is refreshed below.
        existing_path = output_dir / "settings.json"
        preserved_prompt_hooks: list[Any] = []
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and "env" in existing:
                    settings["env"] = existing["env"]
                if isinstance(existing, dict) and "model" in existing:
                    settings["model"] = existing["model"]
                if isinstance(existing, dict):
                    existing_hooks = existing.get("hooks")
                    if isinstance(existing_hooks, dict):
                        prompt_hooks = existing_hooks.get("UserPromptSubmit")
                        if isinstance(prompt_hooks, list):
                            preserved_prompt_hooks = [
                                entry
                                for entry in prompt_hooks
                                if not _hook_entry_matches(entry, _ROUTE_HOOK_MARKER)
                            ]
            except (json.JSONDecodeError, OSError):
                pass

        # Permissions for vibe commands
        settings["permissions"] = {
            "allow": [
                "Bash(vibe *)",
                "Bash(vibe:*)",
                "Bash(~/.claude/hooks/*)",
            ]
        }

        # Register the VibeSOP routing hook, merging with preserved non-route
        # UserPromptSubmit entries (route entry refreshed in place).
        settings["hooks"] = {
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"bash {hooks_dir}/vibesop-route.sh",
                        }
                    ],
                },
                *preserved_prompt_hooks,
            ]
        }

        # Register the P3 tool-sequence capture hook (PostToolUse: tool name +
        # timestamp + session id only, never tool_input).
        if self._sequences_enabled():
            settings["hooks"]["PostToolUse"] = [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"bash {hooks_dir}/vibesop-tool-seq.sh",
                        }
                    ],
                }
            ]

        # Register the conversation-mirror hooks (UserPromptSubmit for
        # real-time prompt mirroring, SessionEnd for transcript import).
        # Opt-in — captures user prompts verbatim, which may contain secrets.
        if self._conversation_mirror_enabled():
            # Skip if a mirror entry was preserved from an earlier build —
            # repeated builds must not accumulate duplicate entries.
            if not any(
                _hook_entry_matches(entry, _MIRROR_PROMPT_HOOK_MARKER)
                for entry in settings["hooks"]["UserPromptSubmit"]
            ):
                settings["hooks"]["UserPromptSubmit"].append(
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"bash {hooks_dir}/vibesop-mirror-prompt.sh",
                            }
                        ],
                    }
                )
            settings["hooks"]["SessionEnd"] = [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"bash {hooks_dir}/vibesop-mirror-session-end.sh",
                        }
                    ],
                }
            ]

        settings_path = output_dir / "settings.json"
        self.write_file_atomic(
            settings_path,
            json.dumps(settings, indent=2),
            validate_security=False,
        )
        result.add_file(settings_path)

        # Enforce single-layer route-hook registration: strip vibesop-route.sh
        # entries from the counterpart layer (user <-> project) so a prompt
        # never fires the route hook twice.
        self._strip_other_layer_route_hook(output_dir, result)

    def _strip_other_layer_route_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Remove vibesop-route.sh UserPromptSubmit entries from the other layer.

        Both ``~/.claude/settings.json`` (user level, deploy.py default) and
        ``<project>/.claude/settings.json`` (project level, ``vibe build``)
        registering the route hook makes Claude Code fire it twice per prompt
        (double route spans + double context injection). After writing the
        current layer, strip route-hook entries from the counterpart layer;
        all other entries (env/model/mirror/PostToolUse) are left untouched.
        """
        # gate41 impl-review MAJOR-1 (claude+pi): strip ONLY when output_dir is
        # one of the two real registration layers. ``vibe build`` without
        # --output stages into .vibe/dist/<target> — treating that as "project
        # layer" would strip the user's live ~/.claude registration and leave
        # both layers unregistered (hook silently dead). Staging/foreign output
        # dirs never trigger the strip.
        user_config_dir = Path("~/.claude").expanduser()
        project_config_dir = self._project_root / ".claude"
        resolved_output = output_dir.resolve()
        if resolved_output == user_config_dir.resolve():
            other_dir = project_config_dir
        elif resolved_output == project_config_dir.resolve():
            other_dir = user_config_dir
        else:
            return

        current_settings = (output_dir / "settings.json").resolve()
        strip_route_hook_from_layer(
            current_settings=current_settings,
            other_dir=other_dir,
            write_atomic=lambda p, c: self.write_file_atomic(p, c, validate_security=False),
            warn=result.add_warning,
        )

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
            "title": "Claude Code Settings",
            "type": "object",
            "properties": {
                "allowedCommands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of allowed commands",
                },
                "allowedTools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of allowed tools",
                },
                "permissions": {
                    "type": "object",
                    "properties": {
                        "network": {"type": "boolean"},
                        "filesystem": {
                            "type": "object",
                            "properties": {
                                "read": {"type": "array", "items": {"type": "string"}},
                                "write": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
                "hooks": {
                    "type": "object",
                    "properties": {
                        "preSessionEnd": {"type": "string"},
                        "postSessionStart": {"type": "string"},
                    },
                },
            },
        }

    def _render_track_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-track.sh hook script."""
        try:
            env = self._get_template_env()
            template = env.get_template("hooks/vibesop-track.sh.j2")
            hook_content = template.render(version="5.2.0")
            hook_path = output_dir / "hooks" / "vibesop-track.sh"
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-track.sh: {e}")

    def _render_tool_seq_hook(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render the vibesop-tool-seq.sh PostToolUse capture hook (P3)."""
        if not self._sequences_enabled():
            return
        try:
            from vibesop._version import __version__

            env = self._get_template_env()
            template = env.get_template("hooks/vibesop-tool-seq.sh.j2")
            hook_content = template.render(
                version=__version__,
                project_root=_tool_seq_project_root(output_dir),
            )
            hook_path = output_dir / "hooks" / "vibesop-tool-seq.sh"
            self.write_file_atomic(hook_path, hook_content, validate_security=False)
            hook_path.chmod(0o755)
            result.add_file(hook_path)
        except Exception as e:
            result.add_warning(f"Failed to write vibesop-tool-seq.sh: {e}")

    def _render_conversation_mirror_hooks(
        self,
        output_dir: Path,
        result: RenderResult,
    ) -> None:
        """Render both conversation-mirror hook scripts (prompt + session-end).

        Opt-in via ``conversation_mirror.enabled`` (default false). Both
        templates share the same project-root resolution as the tool-seq
        hook — see ``_tool_seq_project_root``.
        """
        if not self._conversation_mirror_enabled():
            return
        try:
            from vibesop._version import __version__

            env = self._get_template_env()
            project_root = _tool_seq_project_root(output_dir)
            for template_name, out_name in (
                ("hooks/vibesop-mirror-prompt.sh.j2", "vibesop-mirror-prompt.sh"),
                ("hooks/vibesop-mirror-session-end.sh.j2", "vibesop-mirror-session-end.sh"),
            ):
                try:
                    template = env.get_template(template_name)
                    hook_content = template.render(
                        version=__version__,
                        project_root=project_root,
                    )
                    hook_path = output_dir / "hooks" / out_name
                    self.write_file_atomic(hook_path, hook_content, validate_security=False)
                    hook_path.chmod(0o755)
                    result.add_file(hook_path)
                except Exception as e:
                    result.add_warning(f"Failed to write {out_name}: {e}")
        except Exception as e:
            result.add_warning(f"Failed to render conversation-mirror hooks: {e}")

    def install_hooks(self, config_dir: Path) -> dict[str, bool]:
        """Install Claude Code hooks."""
        results: dict[str, bool] = {}

        # Install pre-session-end hook. Mirrors the Jinja template at
        # src/vibesop/hooks/templates/pre-session-end.sh.j2 — kept inline
        # here because this adapter predates the HookInstaller refactor.
        # If you change one, change the other.
        hook_path = config_dir / "hooks" / "pre-session-end.sh"
        try:
            hook_content = """#!/bin/bash
# Pre-session-end hook for Claude Code
# Closes the instinct-learning loop: mines the session for patterns and
# promotes matured candidates into skill suggestions.

set -e

echo "[pre-session-end] Session ending at $(date)"

if ! command -v vibe &> /dev/null; then
    echo "[pre-session-end] VibeSOP CLI not found, skipping instinct learning"
    exit 0
fi

# Locate the session jsonl (Claude Code stores under .claude/projects/).
session_file="${VIBE_SESSION_FILE:-}"
if [ -z "$session_file" ]; then
    session_file=$(find .claude/projects/-* -name "*.jsonl" -type f \\
        -printf '%T@ %p\\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
fi

# (a) Mine the session for repeated tool patterns -> skill suggestions.
if [ -n "$session_file" ] && [ -f "$session_file" ]; then
    echo "[pre-session-end] Analyzing session: $(basename "$session_file")"
    vibe analyze session "$session_file" || true
else
    vibe analyze session || true
fi

# (b) Promote any sequence candidates that matured during this session.
echo "[pre-session-end] Evaluating instinct candidates"
vibe instinct eval || true

echo "[pre-session-end] Instinct learning complete"
exit 0
"""
            hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(hook_path, hook_content, validate_security=False)

            # Make executable
            hook_path.chmod(0o755)

            results["pre-session-end"] = True
        except Exception as e:
            logger.debug(f"Failed to install pre-session-end hook: {e}")
            results["pre-session-end"] = False
            # Note: error but don't fail

        # Install Agent Runtime route hook (uses shared template)
        route_hook_path = config_dir / "hooks" / "vibesop-route.sh"
        try:
            from vibesop.adapters._shared import render_route_hook as _shared_route_hook

            route_content = _shared_route_hook(
                platform="claude-code",
                platform_name="Claude Code",
                purpose="Trigger VibeSOP routing and inject skill context",
                hook_event_name="UserPromptSubmit",
                enable_explicit_overrides=True,
                enable_orchestration=True,
                include_additional_context=True,
                no_match_message=True,
            )
            route_hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(route_hook_path, route_content, validate_security=False)
            route_hook_path.chmod(0o755)
            results["vibesop-route"] = True
        except Exception as e:
            logger.debug(f"Failed to install vibesop-route hook: {e}")
            results["vibesop-route"] = False

        # Install Agent Runtime track hook
        track_hook_path = config_dir / "hooks" / "vibesop-track.sh"
        try:
            env = self._get_template_env()
            template = env.get_template("hooks/vibesop-track.sh.j2")
            track_content = template.render(version="5.2.0")
            track_hook_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file_atomic(track_hook_path, track_content, validate_security=False)
            track_hook_path.chmod(0o755)
            results["vibesop-track"] = True
        except Exception as e:
            logger.debug(f"Failed to install vibesop-track hook: {e}")
            results["vibesop-track"] = False

        # Install P3 tool-sequence capture hook (PostToolUse), unless disabled
        if self._sequences_enabled():
            tool_seq_hook_path = config_dir / "hooks" / "vibesop-tool-seq.sh"
            try:
                from vibesop._version import __version__

                env = self._get_template_env()
                template = env.get_template("hooks/vibesop-tool-seq.sh.j2")
                tool_seq_content = template.render(
                    version=__version__,
                    project_root=_tool_seq_project_root(config_dir),
                )
                tool_seq_hook_path.parent.mkdir(parents=True, exist_ok=True)
                self.write_file_atomic(
                    tool_seq_hook_path, tool_seq_content, validate_security=False
                )
                tool_seq_hook_path.chmod(0o755)
                results["vibesop-tool-seq"] = True
            except Exception as e:
                logger.debug(f"Failed to install vibesop-tool-seq hook: {e}")
                results["vibesop-tool-seq"] = False

        # Install conversation-mirror hooks (opt-in: prompts may contain secrets)
        if self._conversation_mirror_enabled():
            from vibesop._version import __version__

            env = self._get_template_env()
            project_root = _tool_seq_project_root(config_dir)
            for template_name, out_name, key in (
                (
                    "hooks/vibesop-mirror-prompt.sh.j2",
                    "vibesop-mirror-prompt.sh",
                    "vibesop-mirror-prompt",
                ),
                (
                    "hooks/vibesop-mirror-session-end.sh.j2",
                    "vibesop-mirror-session-end.sh",
                    "vibesop-mirror-session-end",
                ),
            ):
                hook_path = config_dir / "hooks" / out_name
                try:
                    template = env.get_template(template_name)
                    content = template.render(
                        version=__version__,
                        project_root=project_root,
                    )
                    hook_path.parent.mkdir(parents=True, exist_ok=True)
                    self.write_file_atomic(hook_path, content, validate_security=False)
                    hook_path.chmod(0o755)
                    results[key] = True
                except Exception as e:
                    logger.debug(f"Failed to install {out_name} hook: {e}")
                    results[key] = False

        return results
