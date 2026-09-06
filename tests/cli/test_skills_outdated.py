"""CLI tests for ``vibe skills outdated``.

The command is exercised standalone (registered on a bare Typer app) with
``update_checker.check_pack_updates`` mocked — no git, no network, no real
``~/.config/skills`` reads.
"""

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from vibesop.cli.commands.skills_commands._health import outdated
from vibesop.core.skills import update_checker
from vibesop.core.skills.update_checker import PackUpdateStatus

runner = CliRunner()

SHA_A = "a" * 40
SHA_B = "b" * 40


@pytest.fixture
def outdated_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(outdated)
    return app


def _status(name: str, state: str) -> PackUpdateStatus:
    return PackUpdateStatus(
        pack_name=name,
        source_url=f"https://github.com/u/{name}",
        installed_sha=SHA_B,
        remote_sha=SHA_A,
        state=state,
        checked_at="2026-09-07T00:00:00+00:00",
    )


def _patch_statuses(
    monkeypatch: pytest.MonkeyPatch, statuses: list[PackUpdateStatus]
) -> list[bool]:
    """Mock check_pack_updates; returns the captured ``refresh`` flag calls."""
    seen: list[bool] = []

    def fake_check(
        *, refresh: bool = False, store: object = None, ttl_seconds: int = 86400
    ) -> list[PackUpdateStatus]:
        seen.append(refresh)
        return statuses

    monkeypatch.setattr(update_checker, "check_pack_updates", fake_check)
    return seen


def test_update_available_shows_upgrade_hint(
    outdated_app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_statuses(monkeypatch, [_status("mattpocock", "update_available")])
    result = runner.invoke(outdated_app, [])
    assert result.exit_code == 0, result.output
    assert "update available" in result.output
    assert "vibe install mattpocock --upgrade" in result.output
    assert "1 pack(s) can be upgraded." in result.output


def test_up_to_date_and_unknown_render(
    outdated_app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_statuses(
        monkeypatch,
        [_status("superpowers", "up_to_date"), _status("omx", "unknown")],
    )
    result = runner.invoke(outdated_app, [])
    assert result.exit_code == 0, result.output
    assert "superpowers" in result.output
    assert "up to date" in result.output
    assert "omx" in result.output
    assert "unknown" in result.output
    assert "can be upgraded" not in result.output


def test_no_locks_message(outdated_app: typer.Typer, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_statuses(monkeypatch, [])
    result = runner.invoke(outdated_app, [])
    assert result.exit_code == 0, result.output
    assert "No installed packs" in result.output


def test_json_output_is_parseable(
    outdated_app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_statuses(monkeypatch, [_status("demo", "update_available")])
    result = runner.invoke(outdated_app, ["--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data[0]["pack_name"] == "demo"
    assert data[0]["state"] == "update_available"


def test_refresh_flag_passed_through(
    outdated_app: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _patch_statuses(monkeypatch, [])
    runner.invoke(outdated_app, [])
    runner.invoke(outdated_app, ["--refresh"])
    assert seen == [False, True]
