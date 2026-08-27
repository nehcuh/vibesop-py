"""Every PLATFORM_CONFIGS check_id must have a _check_platform handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vibesop.cli.commands.verify import PLATFORM_CONFIGS, _check_platform


def test_every_check_id_has_handler(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    for platform, cfg in PLATFORM_CONFIGS.items():
        results = _check_platform(platform)
        assert {r["id"] for r in results} == set(cfg["checks"])
        for r in results:
            assert r["detail"], f"{platform}/{r['id']} unhandled (empty detail)"


def test_pi_checks_pass_on_rendered_layout(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    pi = tmp_path / ".pi"
    (pi / "extensions").mkdir(parents=True)
    (pi / "skills").mkdir()
    (pi / "prompts").mkdir()
    (pi / "extensions" / "vibesop-route.ts").write_text("// route\n", encoding="utf-8")
    (pi / "extensions" / "vibesop-track.ts").write_text("// track\n", encoding="utf-8")

    results = {r["id"]: r for r in _check_platform("pi")}
    for check_id in PLATFORM_CONFIGS["pi"]["checks"]:
        assert results[check_id]["pass"], results[check_id]["detail"]
