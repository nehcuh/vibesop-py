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
