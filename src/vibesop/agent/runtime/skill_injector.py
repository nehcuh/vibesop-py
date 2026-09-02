"""Skill injector — loads matched skill content into agent context.

Platform-specific injection strategies:
- Claude Code: additionalContext via hook JSON output
- OpenCode: experimental.chat.system.transform
- Kimi CLI: Cannot inject → return ReadFile instruction
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan

logger = logging.getLogger(__name__)

# Not-found placeholder emitted by ``_load_skill_content``; the empty-content
# gate in ``inject_single_skill`` keys on this marker. Producer and gate must
# share one constant — a drifted literal would silently disable the gate and
# let the placeholder text be injected as if it were skill content.
CONTENT_NOT_FOUND_MARKER = "*Skill content not found"


class PlatformType(StrEnum):
    """Supported AI agent platforms."""

    CLAUDE_CODE = "claude-code"
    GROK_BUILD = "grok-build"
    OPENCODE = "opencode"
    KIMI_CLI = "kimi-cli"
    PI = "pi"
    GENERIC = "generic"


class InjectionMethod(StrEnum):
    """How skill content is delivered to the agent."""

    # Direct system prompt modification (OpenCode)
    SYSTEM_PROMPT = "system_prompt"
    # Additional context appended to conversation (Claude Code)
    ADDITIONAL_CONTEXT = "additional_context"
    # Instruction for AI to read skill file (Kimi CLI fallback)
    INSTRUCTION = "instruction"
    # Direct text injection (generic)
    TEXT = "text"


@dataclass
class InjectionResult:
    """Result of skill content injection.

    Attributes:
        method: How the content was/will be injected
        payload: The actual content or injection payload
        skill_id: Which skill was injected
        truncated: Whether content was truncated for length
        content_missing: True when no SKILL.md body could be loaded
        refused_unsafe: True when a body was found but the runtime scan refused it
    """

    method: InjectionMethod
    payload: str | dict[str, Any]
    skill_id: str = ""
    truncated: bool = False
    content_missing: bool = False
    refused_unsafe: bool = False

    @property
    def has_content(self) -> bool:
        """False when the empty-content gate fired (match must not stand).

        Keys on the structured flag, not on user-facing notice wording — a
        reworded ``empty_content_notice`` must not silently disable demotion.
        """
        return not self.content_missing

    @property
    def notice_only(self) -> bool:
        """True when payload is a VibeSOP notice, not a skill body."""
        return self.content_missing or self.refused_unsafe


class SkillInjector:
    """Injects matched skill content into agent context.

    Each platform has different capabilities for context modification:
    - Claude Code: Can inject additionalContext via hook response
    - OpenCode: Can directly modify system prompt via transform hook
    - Kimi CLI: No injection capability → returns instructions for AI

    Example:
        >>> injector = SkillInjector(project_root=".")
        >>> result = injector.inject_single_skill("gstack/review", PlatformType.KIMI_CLI)
        >>> result.method
        <InjectionMethod.INSTRUCTION: 'instruction'>
    """

    # Max characters to inject (to avoid context overflow)
    MAX_INJECT_LENGTH: int = 3000

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        # content-hash → safe? cache for the runtime security scan (avoids
        # re-scanning unchanged skill content on every route).
        self._scan_cache: dict[str, bool] = {}

    def inject_single_skill(
        self,
        skill_id: str,
        platform: PlatformType,
    ) -> InjectionResult:
        """Inject a single skill's content.

        Args:
            skill_id: The matched skill identifier
            platform: Target platform

        Returns:
            InjectionResult with platform-specific payload
        """
        skill_content = self._load_skill_content(skill_id)

        # Empty/placeholder content gate: a registry stub or a missing file is
        # a data problem, not a security finding — report it as such instead
        # of letting the placeholder text (or an empty payload) reach the
        # agent context.
        if not skill_content.strip() or CONTENT_NOT_FOUND_MARKER in skill_content:
            from vibesop.security.runtime_scan import empty_content_notice

            logger.warning(
                "Skill '%s' resolved to no injectable content; skipping injection.", skill_id
            )
            return InjectionResult(
                method=InjectionMethod.TEXT,
                payload=empty_content_notice(skill_id),
                skill_id=skill_id,
                content_missing=True,
            )

        # Runtime security gate: re-scan the loaded content before injecting.
        # The install-time audit is otherwise the ONLY check, so a post-install
        # edit / git-pull / symlink swap would inject unsanitized third-party
        # content into the LLM context. Refuse (inject a notice) if unsafe.
        safe, _scan_source = self._is_content_safe(skill_content)
        if not safe:
            logger.warning(
                "Refusing to inject skill '%s': runtime security scan flagged "
                "the content unsafe (post-install tampering or embedded threat).",
                skill_id,
            )
            from vibesop.security.runtime_scan import unsafe_replacement_notice

            return InjectionResult(
                method=InjectionMethod.TEXT,
                payload=unsafe_replacement_notice(skill_id),
                skill_id=skill_id,
                refused_unsafe=True,
            )

        truncated = False

        if skill_content and len(skill_content) > self.MAX_INJECT_LENGTH:
            skill_content = skill_content[: self.MAX_INJECT_LENGTH]
            truncated = True

        if platform in (PlatformType.CLAUDE_CODE, PlatformType.GROK_BUILD):
            # Grok Build's UserPromptSubmit hook envelope is Claude-shaped
            # (hookSpecificOutput.additionalContext) — same payload format.
            return self._inject_claude_code(skill_id, skill_content, truncated)
        elif platform == PlatformType.OPENCODE:
            return self._inject_opencode(skill_id, skill_content, truncated)
        elif platform == PlatformType.KIMI_CLI:
            return self._inject_kimi_cli(skill_id, skill_content, truncated)
        elif platform == PlatformType.PI:
            return self._inject_pi(skill_id, skill_content, truncated)
        else:
            return self._inject_generic(skill_id, skill_content, truncated)

    def inject_execution_plan(
        self,
        plan: ExecutionPlan,
        platform: PlatformType,
    ) -> InjectionResult:
        """Inject an execution plan for multi-step orchestration.

        Args:
            plan: The execution plan with steps
            platform: Target platform

        Returns:
            InjectionResult with platform-specific payload
        """
        plan_content = self._format_execution_plan(plan)

        if platform in (PlatformType.CLAUDE_CODE, PlatformType.GROK_BUILD):
            # Grok Build's UserPromptSubmit hook envelope is Claude-shaped
            # (hookSpecificOutput.additionalContext) — same as single-skill
            # injection above.
            return InjectionResult(
                method=InjectionMethod.ADDITIONAL_CONTEXT,
                payload={"additionalContext": f"\n\n[VibeSOP Execution Plan]\n{plan_content}\n"},
                skill_id="multi-step-plan",
            )
        elif platform == PlatformType.OPENCODE:
            return InjectionResult(
                method=InjectionMethod.SYSTEM_PROMPT,
                payload=f"<vibesop-plan>\n{plan_content}\n</vibesop-plan>",
                skill_id="multi-step-plan",
            )
        elif platform == PlatformType.KIMI_CLI:
            return InjectionResult(
                method=InjectionMethod.INSTRUCTION,
                payload=plan_content,
                skill_id="multi-step-plan",
            )
        else:
            return InjectionResult(
                method=InjectionMethod.TEXT,
                payload=plan_content,
                skill_id="multi-step-plan",
            )

    def _load_skill_content(self, skill_id: str) -> str:
        """Load skill content from filesystem."""
        path = self._resolve_skill_md(skill_id)
        if path is None:
            return f"# Skill: {skill_id}\n\n{CONTENT_NOT_FOUND_MARKER} at expected locations.*"
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            # UnicodeDecodeError is not an OSError. A GBK/ANSI SKILL.md on
            # Windows would otherwise bubble into handle_query's bare
            # ``except Exception`` and leave skill_id set with empty content.
            return f"# Skill: {skill_id}\n\n{CONTENT_NOT_FOUND_MARKER} at expected locations.*"

    def _resolve_skill_md(self, skill_id: str) -> Path | None:
        """Return the on-disk SKILL.md for *skill_id*, or None.

        v7.3.5 fix (Round 4 P1): previously only checked 3 paths and missed
        the actual install locations for Claude Code (``~/.claude/skills/``)
        and Pi (``~/.pi/agent/skills/``). Also, routing returns the bare
        ``name:`` field from SKILL.md frontmatter (e.g. ``"diagnose"``),
        but installed directory names carry pack prefixes
        (e.g. ``mattpocock-diagnose`` or ``mattpocock-skills-engineering-diagnose``).
        Without suffix matching, injector always fell back to placeholder text.

        Search order (each path is tried with 3 lookup strategies):
        1. ``core/skills/{skill_id}/SKILL.md`` — project-local builtin skills
        2. ``.vibe/skills/{skill_id}/SKILL.md`` — project-local promoted custom
           skills (W4/W5 promote materialization target; nested by skill_id)
        2b. ``skills/{skill_id}/SKILL.md`` — SkillLoader default project root
            (adapters also write here; discovered unless strict_search_paths)
        3. ``~/.claude/skills/{...}/SKILL.md`` — Claude Code target dir
        4. ``~/.pi/agent/skills/{...}/SKILL.md`` — Pi target dir
        5. ``~/.kimi-code/skills/{...}/SKILL.md`` — Kimi Code target dir
        6. ``~/.kimi/skills/{...}/SKILL.md`` — Kimi home install (CandidateManager)
        7. ``~/.config/skills/{...}/SKILL.md`` — central storage (nested layout)
        8. ``~/.config/opencode/skills/{...}/SKILL.md`` — OpenCode install
        9. ``~/.vibe/skills/{skill_id}/SKILL.md`` — global-scope promoted custom
           skills (``skill promote --scope global`` target)

        For each path, lookup strategies are tried in order:
        - Exact nested id: ``{base}/{skill_id}/SKILL.md`` (namespaced ids only —
          the on-disk layout of promoted custom skills)
        - Exact flat id: ``{skill_id.replace('/', '-')}`` (e.g. ``gstack-review``)
        - ``{id}.skill/`` layout: ``{base}/{flat_id}.skill/SKILL.md`` and
          ``{base}/**/{leaf}.skill/SKILL.md`` (project cross-cutting packs)
        - Pack-prefix glob: ``*-{flat_id}`` (e.g. ``mattpocock-diagnosing-bugs``)
        - Nested glob: ``**/{flat_id}/SKILL.md`` in central storage only
          (e.g. ``mattpocock/engineering/diagnosing-bugs``)
        """
        return self._find_skill_md_path(skill_id)

    def _find_skill_md_path(self, skill_id: str) -> Path | None:
        """Walk install layouts; return the first existing SKILL.md."""
        flat_id = skill_id.replace("/", "-")
        home = Path.home()

        from vibesop.utils.bundled import resolve_builtin_skills_dir

        # Keep this a superset of CandidateManager._build_search_paths so a
        # discovered skill is injectable. Extra injector-only roots (pi,
        # kimi-code, global .vibe) stay here for platform installs the
        # router does not currently index.
        candidate_dirs: list[Path] = [
            resolve_builtin_skills_dir(self.project_root),
            self.project_root / ".vibe" / "skills",
            self.project_root / "skills",
            home / ".claude" / "skills",
            home / ".pi" / "agent" / "skills",
            home / ".kimi-code" / "skills",
            home / ".kimi" / "skills",
            home / ".config" / "skills",
            home / ".config" / "opencode" / "skills",
            home / ".vibe" / "skills",
        ]

        def _if_file(path: Path) -> Path | None:
            try:
                if path.is_file():
                    return path
            except OSError:
                return None
            return None

        if "/" in skill_id:
            name_only = skill_id.split("/", 1)[1]
            hit = _if_file(resolve_builtin_skills_dir(self.project_root) / name_only / "SKILL.md")
            if hit is not None:
                return hit

        for base in candidate_dirs:
            if not base.exists():
                continue
            if "/" in skill_id:
                hit = _if_file(base / skill_id / "SKILL.md")
                if hit is not None:
                    return hit
            hit = _if_file(base / flat_id / "SKILL.md")
            if hit is not None:
                return hit
            hit = _if_file(base / f"{flat_id}.skill" / "SKILL.md")
            if hit is not None:
                return hit
            if "/" in skill_id:
                ns, rest = skill_id.split("/", 1)
                hit = _if_file(base / ns / f"{rest}.skill" / "SKILL.md")
                if hit is not None:
                    return hit
            leaf = skill_id.rsplit("/", 1)[-1]
            try:
                for match in base.glob(f"**/{leaf}.skill/SKILL.md"):
                    hit = _if_file(match)
                    if hit is not None:
                        return hit
            except OSError:
                pass
            if base != self.project_root / "core" / "skills":
                try:
                    for candidate in base.glob(f"*-{flat_id}"):
                        hit = _if_file(candidate / "SKILL.md")
                        if hit is not None:
                            return hit
                except OSError:
                    pass

        central = home / ".config" / "skills"
        if central.exists():
            try:
                for match in central.glob(f"**/{flat_id}/SKILL.md"):
                    hit = _if_file(match)
                    if hit is not None:
                        return hit
            except OSError:
                pass
        return None

    def _is_content_safe(self, content: str) -> tuple[bool, str]:
        """Runtime security check of skill content before injection.

        Catches post-install tampering (edit / git-pull / symlink swap) that
        bypasses the install-time audit — without this, modified SKILL.md is
        injected verbatim into the LLM context. Cached by content hash; fails
        closed (a scanner error is treated as unsafe).
        """
        key = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
        cached = self._scan_cache.get(key)
        if cached is not None:
            return cached, "cached"
        from vibesop.security.runtime_scan import is_skill_content_safe

        safe = is_skill_content_safe(content)
        self._scan_cache[key] = safe
        return safe, "scanned"

    def _inject_claude_code(
        self,
        skill_id: str,
        content: str,
        truncated: bool,
    ) -> InjectionResult:
        """Build Claude Code additionalContext payload."""
        context_text = f"""

[ACTIVE SKILL: {skill_id}]
You MUST follow this skill's workflow. Do not skip steps.

{content}
{"\n[Content truncated]" if truncated else ""}
"""
        return InjectionResult(
            method=InjectionMethod.ADDITIONAL_CONTEXT,
            payload={"additionalContext": context_text},
            skill_id=skill_id,
            truncated=truncated,
        )

    def _inject_opencode(
        self,
        skill_id: str,
        content: str,
        truncated: bool,
    ) -> InjectionResult:
        """Build OpenCode system prompt fragment."""
        fragment = f"""<vibesop-skill id="{skill_id}">
You MUST follow this skill's workflow. Do not skip steps.

{content}
{"\n[Content truncated]" if truncated else ""}
</vibesop-skill>"""
        return InjectionResult(
            method=InjectionMethod.SYSTEM_PROMPT,
            payload=fragment,
            skill_id=skill_id,
            truncated=truncated,
        )

    def _inject_kimi_cli(
        self,
        skill_id: str,
        _content: str,
        _truncated: bool,
    ) -> InjectionResult:
        """Build Kimi CLI instruction (AI must read skill file itself)."""
        resolved = self._resolve_skill_md(skill_id)
        if resolved is not None:
            instruction = (
                f"请先读取 {resolved.as_posix()} ，"
                f"然后严格按照该 skill 的工作流程执行「{skill_id}」。"
                f"不得跳过任何步骤。"
            )
        else:
            flat_id = skill_id.replace("/", "-")
            instruction = (
                f"请先读取 ~/.kimi-code/skills/{flat_id}/SKILL.md "
                f"（或 .kimi-code/skills/{flat_id}/SKILL.md），"
                f"然后严格按照该 skill 的工作流程执行「{skill_id}」。"
                f"不得跳过任何步骤。"
            )
        return InjectionResult(
            method=InjectionMethod.INSTRUCTION,
            payload=instruction,
            skill_id=skill_id,
        )

    def _inject_pi(
        self,
        skill_id: str,
        skill_content: str,
        truncated: bool = False,
    ) -> InjectionResult:
        """Generate Pi Coding Agent injection payload.

        Pi uses AGENTS.md context + prompt templates. Inject skill content
        as a section the agent should read before proceeding.
        """
        truncation_note = (
            f"\n[Content truncated at {self.MAX_INJECT_LENGTH} chars — "
            "refer to skill file for full content]"
            if truncated
            else ""
        )
        payload = (
            f'<vibesop-skill platform="pi">\n'
            f"## Skill: {skill_id}\n"
            f"Read the SKILL.md for `{skill_id}` before proceeding.\n"
            f"```markdown\n{skill_content}{truncation_note}\n```\n"
            f"</vibesop-skill>"
        )
        return InjectionResult(
            method=InjectionMethod.TEXT,
            payload=payload,
            skill_id=skill_id,
            truncated=truncated,
        )

    def _inject_generic(
        self,
        skill_id: str,
        content: str,
        truncated: bool,
    ) -> InjectionResult:
        """Build generic text injection."""
        text = f"""

=== SKILL: {skill_id} ===
{content}
{"\n[Content truncated]" if truncated else ""}
=== END SKILL ===
"""
        return InjectionResult(
            method=InjectionMethod.TEXT,
            payload=text,
            skill_id=skill_id,
            truncated=truncated,
        )

    def _format_execution_plan(self, plan: ExecutionPlan) -> str:
        """Format an execution plan for agent consumption.

        Groups steps by parallel batches and marks dependencies.
        Includes reasoning transparency for debugging and user understanding.
        """
        lines = [
            f"# 执行计划: {plan.original_query}",
            "",
        ]

        # Transparency: show detected intents and reasoning
        if plan.detected_intents:
            lines.extend(
                [
                    "## 检测到的意图",
                    ", ".join(f"- {intent}" for intent in plan.detected_intents),
                    "",
                ]
            )

        if plan.reasoning:
            lines.extend(
                [
                    "## 分解理由",
                    plan.reasoning,
                    "",
                ]
            )

        lines.extend(
            [
                f"## 执行模式: {plan.execution_mode.value}",
                "",
                "你必须按以下步骤执行。每完成一步，报告结果后再继续下一步。",
                "",
            ]
        )

        # Get parallel groups for visualization
        groups = plan.get_parallel_groups()

        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                lines.extend(
                    [
                        f"## 步骤 {step.step_number}: {step.intent}",
                        f"- 使用 skill: {step.skill_id}",
                        f"- 任务: {step.input_query}",
                        f"- 输出变量: {step.output_as}",
                        "",
                        f"完成此步骤后，请明确声明：『步骤 {step.step_number} 完成，"
                        f"输出已保存到 {step.output_as}』",
                        "",
                    ]
                )
            else:
                lines.append(f"## 并行步骤组 {group_num}")
                lines.append("以下步骤可以并行执行：")
                for step in group:
                    lines.extend(
                        [
                            "",
                            f"### 步骤 {step.step_number}: {step.intent}",
                            f"- 使用 skill: {step.skill_id}",
                            f"- 任务: {step.input_query}",
                        ]
                    )
                lines.extend(
                    [
                        "",
                        f"所有并行步骤完成后，请明确声明：『并行组 {group_num} 全部完成』",
                        "",
                    ]
                )

        lines.extend(
            [
                "",
                "---",
                "执行规则:",
                "1. 严格按照步骤顺序执行",
                "2. 每步必须读取对应的 SKILL.md",
                "3. 每步完成后明确报告",
                "4. 如果某步失败，报告错误并询问是否继续",
            ]
        )

        return "\n".join(lines)


__all__ = [
    "InjectionMethod",
    "InjectionResult",
    "PlatformType",
    "SkillInjector",
]
