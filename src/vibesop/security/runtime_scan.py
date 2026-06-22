"""Runtime security check for skill content before LLM injection.

The install-time audit (`SkillSecurityAuditor`) is the only gate otherwise.
These helpers catch **post-install tampering** (edit / git-pull / symlink swap)
on any path that loads SKILL.md into an agent's context:

- ``SkillInjector.inject_single_skill`` — the `/slash-route` direct-injection
  path (slash-route / hook additionalContext).
- ``PlanExecutor.build_manifest`` — the orchestration path, where each step's
  SKILL.md is embedded into an ``ExecutionManifest`` and later injected into the
  agent prompt by ``StepContextInjector``.

Both must refuse to inject content the runtime scanner flags unsafe. Centralised
here so the two paths can't drift apart.
"""

from __future__ import annotations


def is_skill_content_safe(content: str) -> bool:
    """True if ``content`` passes the runtime ``SecurityScanner``.

    Fail-closed: a scanner error is treated as unsafe (never inject content that
    could not be verified). Callers that want to avoid re-scanning unchanged
    content should cache by content hash — see ``SkillInjector._scan_cache``.
    """
    from vibesop.security.scanner import SecurityScanner

    try:
        return bool(SecurityScanner().scan(content).safe)
    except Exception:
        return False


def unsafe_replacement_notice(skill_id: str) -> str:
    """The notice embedded/injected in place of skill content the runtime scan
    flagged unsafe. Centralised so the slash-injection (SkillInjector) and
    orchestration (PlanExecutor.build_manifest) paths can't drift apart.
    """
    return (
        f"[VibeSOP SECURITY] Skill '{skill_id}' was flagged unsafe by the "
        f"runtime security scan; its content was NOT injected/embedded. It may "
        f"have been modified after install or contains a threat. Re-install or "
        f"audit it before use."
    )
