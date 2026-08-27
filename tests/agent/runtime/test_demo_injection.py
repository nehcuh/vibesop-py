"""Gate46 B2.4: real-pipeline injection self-verification (probe as tests).

Unlike TestRouteHookMode (stubbed AgentRuntime), these run the REAL
routing→injection pipeline and pin the properties the dual-platform probe
asserts: envelope shape, ACTIVE SKILL marker, and on-disk resolution of the
NEXT STEP hint — including from a project_root that is NOT the vibesop repo
(the quickstart demo / real user situation that broke content injection
before the bundled/repo fallback fix).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import pytest

DEMO_QUERY = "help me write a commit message"
EXPECTED_SKILL = "builtin/commit-message"


class TestRealHookPipeline:
    @pytest.fixture(autouse=True)
    def _scratch_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)

    @pytest.mark.parametrize("platform", ["claude-code", "grok-build"])
    def test_demo_query_full_hook_envelope(self, platform: str) -> None:
        """stdin JSON (with platform) → exit 0 → parseable envelope with
        routed marker, injected skill content, and an on-disk NEXT STEP
        path. Both platform lanes must produce the SAME [ACTIVE SKILL]
        contract — grok's envelope is Claude-shaped (gate46 dual-review)."""
        from typer.testing import CliRunner

        from vibesop.cli.main import app

        result = CliRunner().invoke(
            app,
            ["route", "--hook"],
            input=json.dumps({"prompt": DEMO_QUERY, "platform": platform}),
        )
        assert result.exit_code == 0

        # CliRunner merges stderr; the MiniLM tqdm progress bar (cached-model
        # environments) lands before the envelope. Real hooks read stdout
        # only, where the envelope is clean — here, parse from the first '{'.
        raw = result.output
        envelope = json.loads(raw[raw.index("{") :])
        assert "VibeSOP routed:" in envelope.get("systemMessage", "")
        assert EXPECTED_SKILL in envelope.get("systemMessage", "")

        hook_specific = envelope.get("hookSpecificOutput") or {}
        context_text = hook_specific.get("additionalContext") or ""
        assert f"[ACTIVE SKILL: {EXPECTED_SKILL}]" in context_text
        assert "# Commit Message" in context_text, "SKILL.md body must be injected"
        assert hook_specific.get("hookEventName") == "UserPromptSubmit"

        # The NEXT STEP read-path must resolve to a real file for the agent.
        # (It travels in systemMessage; additionalContext carries the body.)
        import re

        hint = re.search(r"read (\S+?SKILL\.md)", envelope.get("systemMessage", ""))
        assert hint is not None, "missing NEXT STEP read instruction"
        assert Path(hint.group(1)).exists(), f"hint path not on disk: {hint.group(1)}"


class TestInjectorBuiltinResolution:
    """Regression: builtin content must load even when project_root is not
    the vibesop repo and site-packages has no bundle (dev-editable case)."""

    def test_loads_builtin_content_outside_repo(self, tmp_path: Path) -> None:
        from vibesop.agent.runtime.skill_injector import SkillInjector

        injector = SkillInjector(project_root=tmp_path)
        content = injector._load_skill_content(EXPECTED_SKILL)
        assert "# Commit Message" in content
        assert "not found" not in content.lower() or "Skill:" not in content[:20]

    def test_wheel_bundle_wins_when_present(self, tmp_path: Path, monkeypatch) -> None:
        """Fake site-packages bundle (pipx layout) is preferred over the
        dev repo copy — proves the wheel resolution lane works."""
        import vibesop

        fake_pkg = tmp_path / "site-packages" / "vibesop"
        skill_dir = fake_pkg / "builtin_skills" / "commit-message"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "# WHEEL BUNDLE COPY\n", encoding="utf-8"
        )
        fake_init = fake_pkg / "__init__.py"
        fake_init.write_text("", encoding="utf-8")
        monkeypatch.setattr(vibesop, "__file__", str(fake_init))

        from vibesop.agent.runtime.skill_injector import SkillInjector

        injector = SkillInjector(project_root=tmp_path)
        content = injector._load_skill_content(EXPECTED_SKILL)
        assert "WHEEL BUNDLE COPY" in content
