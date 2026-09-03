"""gate43: hook_routing split tests for _generation.py copy faces.

The ``hook_routing`` parameter (default False — the failure direction
keeps the CLI channel) selects between the conditional hook-first copy
(platforms with a registered routing hook) and the imperative CLI-first
copy (hook-less platforms).
"""

from __future__ import annotations

from pathlib import Path

from vibesop.adapters._generation import (
    generate_docs_routing,
    generate_slim_agents_index,
    render_docs_files,
)
from vibesop.adapters.grok_build import GrokBuildAdapter

FINGERPRINTS = (
    "VibeSOP routed:",
    "[ACTIVE SKILL:",
    "NEXT STEP (MANDATORY): read",
    "VibeSOP: No matching skill found",
)


class TestSlimAgentsIndexHookRouting:
    def test_hook_true_renders_conditional_copy(self) -> None:
        text = generate_slim_agents_index(hook_routing=True)
        assert "Routing is automatic" in text
        for fp in FINGERPRINTS:
            assert fp in text
        assert 'vibe route "<user_request>"' in text
        assert "**MANDATORY" not in text

    def test_hook_false_keeps_imperative_copy(self) -> None:
        text = generate_slim_agents_index(hook_routing=False)
        assert "MANDATORY: Call `vibe route`" in text
        assert 'vibe route "<user_request>"' in text
        assert "Routing is automatic" not in text

    def test_default_is_false(self) -> None:
        text = generate_slim_agents_index()
        assert "MANDATORY: Call `vibe route`" in text
        assert "Routing is automatic" not in text


class TestDocsRoutingHookRouting:
    def test_hook_true_workflow_is_injection_first(self) -> None:
        text = generate_docs_routing(hook_routing=True)
        assert "**Check injection**" in text
        for fp in FINGERPRINTS:
            assert fp in text
        assert 'vibe route "<user_request>"' in text
        # CLI route is demoted to an explicit fallback step
        assert "**Route** (fallback, only when no injection is present)" in text

    def test_hook_false_keeps_cli_first_workflow(self) -> None:
        text = generate_docs_routing(hook_routing=False)
        assert '1. **Route**: `vibe route "<user_request>"`' in text
        assert "**Check injection**" not in text
        assert "Routing is automatic" not in text

    def test_default_is_false(self) -> None:
        text = generate_docs_routing()
        assert '1. **Route**: `vibe route "<user_request>"`' in text
        assert "**Check injection**" not in text


class TestRenderDocsFilesBundleCallPoint:
    """Pin the bundle call point (_generation.py docs dict): the
    hook_routing argument must actually reach generate_docs_routing,
    otherwise routing.md silently ships the stale CLI-first copy."""

    def test_bundle_forwards_hook_routing_true(self, tmp_path: Path) -> None:
        created = render_docs_files(tmp_path, [], hook_routing=True)
        routing_md = (tmp_path / "docs" / "routing.md").read_text(encoding="utf-8")
        assert "**Check injection**" in routing_md
        assert tmp_path / "docs" / "routing.md" in created

    def test_bundle_default_keeps_cli_first(self, tmp_path: Path) -> None:
        render_docs_files(tmp_path, [])
        routing_md = (tmp_path / "docs" / "routing.md").read_text(encoding="utf-8")
        assert '1. **Route**: `vibe route "<user_request>"`' in routing_md
        assert "**Check injection**" not in routing_md


class TestGrokRoutingRule:
    def test_conditional_grok_variant(self) -> None:
        text = GrokBuildAdapter()._render_routing_rule()
        # Old unconditional imperative is gone
        assert "Before every non-trivial task" not in text
        # Conditional copy: automatic routing + this-turn hook injection
        # semantics (grok injects via hook JSON systemMessage/
        # additionalContext, not necessarily the user prompt body)
        assert "Routing is automatic" in text
        assert "this turn" in text
        assert "hook injection" in text
        for fp in FINGERPRINTS:
            assert fp in text
        # CLI fallback preserved
        assert 'vibe route "<user_request>"' in text
        assert "skill_file" in text
        assert "Do not guess `skills/<id>/SKILL.md`" in text


GUESSED_FLAT_PATHS = (
    "skills/<matched-skill>/SKILL.md",
    "skills/<skill-id>/SKILL.md",
)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "vibesop" / "adapters" / "templates"


def _assert_no_guessed_flat_skill_path(text: str, name: str) -> None:
    for needle in GUESSED_FLAT_PATHS:
        assert needle not in text, f"{name} still tells the agent to guess {needle}"
    assert "skill_file" in text, f"{name}: missing skill_file"
    lowered = text.lower()
    assert "do not guess" in lowered, f"{name}: missing do-not-guess instruction"


class TestGeneratedCopyDoesNotGuessFlatSkillPath:
    """Fail-closed copy: after route/inject, agents must follow skill_file /
    NEXT STEP, never hunt skills/<id>/SKILL.md."""

    def test_slim_agents_index(self) -> None:
        for hook in (True, False):
            _assert_no_guessed_flat_skill_path(
                generate_slim_agents_index(hook_routing=hook),
                f"slim AGENTS.md hook_routing={hook}",
            )

    def test_docs_routing(self) -> None:
        for hook in (True, False):
            _assert_no_guessed_flat_skill_path(
                generate_docs_routing(hook_routing=hook),
                f"docs/routing.md hook_routing={hook}",
            )

    def test_grok_routing_rule(self) -> None:
        _assert_no_guessed_flat_skill_path(
            GrokBuildAdapter()._render_routing_rule(),
            "grok routing rule",
        )

    def test_cursor_opencode_kimi_readmes(self) -> None:
        from vibesop.adapters.cursor import CursorAdapter
        from vibesop.adapters.kimi_cli import KimiCliAdapter
        from vibesop.adapters.models import Manifest, ManifestMetadata
        from vibesop.adapters.opencode import OpenCodeAdapter

        skill_meta = ManifestMetadata(platform="kimi-cli", version="1.0.0")
        manifest = Manifest(metadata=skill_meta, skills=[])
        faces = {
            "kimi README": KimiCliAdapter()._generate_readme(manifest),
            "cursor README": CursorAdapter()._generate_readme(
                Manifest(metadata=ManifestMetadata(platform="cursor", version="1.0.0"), skills=[])
            ),
            "opencode README": OpenCodeAdapter()._generate_readme(
                Manifest(
                    metadata=ManifestMetadata(platform="opencode", version="1.0.0"),
                    skills=[],
                )
            ),
        }
        for name, text in faces.items():
            _assert_no_guessed_flat_skill_path(text, name)
            assert "read skills/systematic-debugging/SKILL.md" not in text, name
            assert "read skills/session-end/SKILL.md" not in text, name
            assert 'vibe route --slash "/session-end"' not in text, name

    def test_claude_and_pi_routing_templates(self) -> None:
        rels = (
            "claude-code/CLAUDE.md.j2",
            "claude-code/rules/routing.md.j2",
            "claude-code/docs/routing-protocol.md.j2",
            "claude-code/docs/session-lifecycle.md.j2",
            "pi/docs/routing-protocol.md.j2",
        )
        for rel in rels:
            text = (TEMPLATES_DIR / rel).read_text(encoding="utf-8")
            _assert_no_guessed_flat_skill_path(text, rel)
            assert "read skills/session-end/SKILL.md" not in text, rel

    def test_session_lifecycle_doc_does_not_guess(self) -> None:
        from vibesop.adapters._generation import generate_docs_session_lifecycle

        text = generate_docs_session_lifecycle()
        assert "read skills/session-end/SKILL.md" not in text
        assert 'vibe route --slash "/session-end"' not in text
        assert "vibe skills info builtin/session-end" in text
        assert "Do not guess `skills/session-end/SKILL.md`" in text
        assert "skill_file" in text

    def test_slash_route_skill_does_not_guess_flat_path(self) -> None:
        skill = (
            Path(__file__).resolve().parents[2] / "core" / "skills" / "slash-route" / "SKILL.md"
        )
        text = skill.read_text(encoding="utf-8")
        _assert_no_guessed_flat_skill_path(text, "slash-route SKILL.md")
