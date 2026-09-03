"""Tests for the 'vibe doctor' command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import vibesop.cli.main as main_module
from vibesop import __version__
from vibesop.cli.main import app

runner = CliRunner()


def _hermetic_layout(monkeypatch, tmp_path: Path) -> Path:
    """Point the freshness check at an empty tmp config dir; return it."""
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    monkeypatch.setattr(
        main_module,
        "_ALWAYS_LOADED_LAYOUT",
        {"claude-code": (config_dir, ("CLAUDE.md", "rules/routing.md", "docs/skills.md"))},
    )
    central = tmp_path / "central"
    central.mkdir()
    monkeypatch.setattr(main_module, "_CENTRAL_SKILLS_DIR", central)
    return config_dir


class TestDoctorCommand:
    """Tests for vibe doctor command."""

    def test_doctor_runs_successfully(self, monkeypatch, tmp_path: Path) -> None:
        """Doctor completes without crashing (exit 0/1, never a traceback)."""
        _hermetic_layout(monkeypatch, tmp_path)
        result = runner.invoke(app, ["doctor"])

        assert result.exit_code in (0, 1)
        assert len(result.stdout) > 0

    def test_doctor_shows_python_version(self, monkeypatch, tmp_path: Path) -> None:
        """Doctor command shows Python version."""
        _hermetic_layout(monkeypatch, tmp_path)
        result = runner.invoke(app, ["doctor"])

        assert result.exit_code in (0, 1)
        assert "Python" in result.stdout or "python" in result.stdout


class TestAlwaysLoadedLayoutContract:
    """Pin the real layout: scanned rel paths must track what builds render."""

    def test_session_lifecycle_scanned_where_rendered(self) -> None:
        """claude-code/kimi-cli/opencode/pi all render docs/session-lifecycle.md
        and carry the session-end wording — the doctor must scan it there."""
        for platform in ("claude-code", "kimi-cli", "opencode", "pi"):
            assert "docs/session-lifecycle.md" in main_module._ALWAYS_LOADED_LAYOUT[platform][1], (
                f"{platform} renders docs/session-lifecycle.md but doctor does not scan it"
            )

    def test_cursor_absent_until_buildable(self) -> None:
        """`vibe build cursor` renders nothing (ConfigRenderer rejects it), so a
        cursor entry would print a redeploy command that silently no-ops."""
        assert "cursor" not in main_module._ALWAYS_LOADED_LAYOUT

    def test_opencode_routing_doc_scanned(self) -> None:
        """opencode renders docs/routing.md (historically carried guess-path
        copy); kimi-cli already scans its own — the two must stay in parity."""
        assert "docs/routing.md" in main_module._ALWAYS_LOADED_LAYOUT["opencode"][1]
        assert "docs/routing.md" in main_module._ALWAYS_LOADED_LAYOUT["kimi-cli"][1]

    def test_layout_shape(self) -> None:
        for config_dir, rel_paths in main_module._ALWAYS_LOADED_LAYOUT.values():
            assert isinstance(config_dir, Path)
            assert all(isinstance(r, str) and r for r in rel_paths)
            assert rel_paths, "every platform entry must scan at least one file"


class TestScanGuessPathResidue:
    """_scan_guess_path_residue: command-guess wording vs current prohibition."""

    def test_old_guess_command_flagged(self) -> None:
        assert main_module._scan_guess_path_residue(
            "then read `skills/<matched-skill>/SKILL.md` and follow its steps."
        )

    def test_old_pi_guess_command_flagged(self) -> None:
        assert main_module._scan_guess_path_residue(
            "Then read the matched skill file at `.pi/skills/<matched-skill>/SKILL.md`."
        )

    def test_skill_id_command_flagged(self) -> None:
        assert main_module._scan_guess_path_residue(
            "1. Read the recommended skill file: `skills/<skill-id>/SKILL.md`"
        )

    def test_prohibition_not_flagged(self) -> None:
        assert not main_module._scan_guess_path_residue(
            "then read the SKILL.md path from the routing result (`skill_file` in "
            "JSON, or the `SKILL.md:` / `NEXT STEP` line). Do not guess "
            "`skills/<id>/SKILL.md`."
        )

    def test_prohibition_split_across_lines_not_flagged(self) -> None:
        assert not main_module._scan_guess_path_residue(
            "or `vibe skills info <skill-id>` (Source file). Do not guess\n`skills/<id>/SKILL.md`."
        )

    def test_pi_generated_tree_reference_not_flagged(self) -> None:
        assert not main_module._scan_guess_path_residue(
            "Generated-tree copies live at `.pi/skills/<skill-id>/SKILL.md`. Do not "
            "guess a path without the `.pi/` prefix."
        )

    def test_old_session_end_concrete_path_flagged(self) -> None:
        assert main_module._scan_guess_path_residue(
            "1. Read the session-end skill: `.pi/skills/session-end/SKILL.md`"
        )

    def test_old_track_extension_hardcode_flagged(self) -> None:
        assert main_module._scan_guess_path_residue(
            "Use the `read` tool to load `.pi/skills/builtin-session-end/SKILL.md` "
            "and follow its instructions exactly."
        )

    def test_new_session_end_wording_not_flagged(self) -> None:
        assert not main_module._scan_guess_path_residue(
            "Run `vibe skills info builtin/session-end`, read the printed Source "
            "file (`skill_file`). Do not guess `.pi/skills/session-end/SKILL.md`."
        )

    def test_real_source_path_not_flagged(self) -> None:
        """Absolute/real session-end Source paths (what `vibe skills info`
        prints) are not guesses — only standalone relative command paths are."""
        assert not main_module._scan_guess_path_residue(
            "Source file: /Users/x/Projects/vibesop-py/core/skills/session-end/SKILL.md"
        )
        assert not main_module._scan_guess_path_residue(
            "installed at ~/.claude/skills/session-end/SKILL.md"
        )


class TestCheckAlwaysLoadedFreshness:
    """Deployment-freshness check over patched layout/central dirs."""

    def test_fresh_deployment_passes(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = _hermetic_layout(monkeypatch, tmp_path)
        (config_dir / "CLAUDE.md").write_text(
            f"routing: follow `skill_file` from results\n\n*Generated by VibeSOP v{__version__}*",
            encoding="utf-8",
        )
        ok, msg = main_module._check_always_loaded_freshness()
        assert ok, msg
        assert "1 always-loaded files current" in msg

    def test_guess_residue_fails_with_redeploy_hint(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = _hermetic_layout(monkeypatch, tmp_path)
        (config_dir / "CLAUDE.md").write_text(
            "then read `skills/<matched-skill>/SKILL.md` and follow its steps.",
            encoding="utf-8",
        )
        ok, msg = main_module._check_always_loaded_freshness()
        assert not ok
        assert "guess-path wording" in msg
        assert "vibe build claude-code" in msg
        assert str(config_dir) in msg

    def test_stale_version_marker_fails(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = _hermetic_layout(monkeypatch, tmp_path)
        (config_dir / "CLAUDE.md").write_text(
            "clean wording\n\n*Generated by VibeSOP v0.0.1*", encoding="utf-8"
        )
        ok, msg = main_module._check_always_loaded_freshness()
        assert not ok
        assert "deployed v0.0.1" in msg

    def test_nested_rules_file_scanned(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = _hermetic_layout(monkeypatch, tmp_path)
        (config_dir / "CLAUDE.md").write_text(
            f"clean\n\n*Generated by VibeSOP v{__version__}*", encoding="utf-8"
        )
        rules = config_dir / "rules"
        rules.mkdir()
        (rules / "routing.md").write_text(
            "1. Read `skills/<matched-skill>/SKILL.md`", encoding="utf-8"
        )
        ok, msg = main_module._check_always_loaded_freshness()
        assert not ok
        assert "routing.md" in msg

    def test_central_slash_skill_residue_fails_with_sync_hint(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        _hermetic_layout(monkeypatch, tmp_path)
        slash = tmp_path / "central" / "slash-route"
        slash.mkdir()
        (slash / "SKILL.md").write_text(
            "- **Next step**: read `skills/<matched-skill>/SKILL.md`", encoding="utf-8"
        )
        ok, msg = main_module._check_always_loaded_freshness()
        assert not ok
        assert "slash-route" in msg
        assert "vibe skills sync" in msg

    def test_no_deployments_passes(self, monkeypatch, tmp_path: Path) -> None:
        _hermetic_layout(monkeypatch, tmp_path)
        ok, msg = main_module._check_always_loaded_freshness()
        assert ok, msg
        assert "0 always-loaded files current" in msg

    def test_doctor_reports_residue_as_advisory(self, monkeypatch, tmp_path: Path) -> None:
        """Residue surfaces as a ⚠️ line; exit code is driven by hard-red
        checks only (Deployment Freshness is advisory)."""
        config_dir = _hermetic_layout(monkeypatch, tmp_path)
        (config_dir / "CLAUDE.md").write_text(
            "then read `skills/<matched-skill>/SKILL.md`", encoding="utf-8"
        )
        result = runner.invoke(app, ["doctor"])
        assert "Deployment Freshness" in result.stdout
        assert "guess-path wording" in result.stdout
        assert "redeploy" in result.stdout


class TestDoctorExitAggregation:
    """Exit-code semantics: hard-red checks fail, advisory ⚠️ checks warn."""

    @staticmethod
    def _checks(**override: bool) -> list[tuple[str, tuple[bool, str]]]:
        base = {
            "Python version": True,
            "Dependencies": True,
            "Configuration": True,
            "LLM Provider": True,
            "Platform Integrations": True,
            "Hook Status": True,
            "Skill Health": True,
            "Deployment Freshness": True,
        }
        base.update(override)
        return [(name, (ok, "msg")) for name, ok in base.items()]

    def test_all_green_exits_ok(self) -> None:
        assert main_module._doctor_exit_ok(self._checks())

    def test_yellow_only_failure_stays_ok(self) -> None:
        assert main_module._doctor_exit_ok(
            self._checks(**{"Deployment Freshness": False, "Hook Status": False})
        )

    def test_red_failure_fails(self) -> None:
        assert not main_module._doctor_exit_ok(self._checks(**{"Skill Health": False}))

    def test_doctor_exits_zero_when_only_advisory_red(self, monkeypatch, tmp_path: Path) -> None:
        """End-to-end pin: advisory failures (freshness residue, no hooks)
        must not fail `vibe doctor`; only hard-red checks drive exit 1."""
        config_dir = _hermetic_layout(monkeypatch, tmp_path)
        (config_dir / "CLAUDE.md").write_text(
            "then read `skills/<matched-skill>/SKILL.md`", encoding="utf-8"
        )
        for red_check in (
            "_check_python_version",
            "_check_dependencies",
            "_check_config",
            "_check_llm_provider",
            "_check_skill_health",
        ):
            monkeypatch.setattr(main_module, red_check, lambda: (True, "ok"))
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "All checks passed" in result.stdout
