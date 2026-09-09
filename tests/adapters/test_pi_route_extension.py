"""Behavioral regression tests for the Pi route extension template.

2026-09-09 finding: the pi extension conflated hook failure with a clean
no-match — both silently passed the prompt through. Since pi's AGENTS.md
tells the agent "no injection → run `vibe route` yourself", every genuine
no-match paid a second routing round-trip, unlike claude/kimi/grok which
emit a `VibeSOP: No matching skill found` fingerprint the agent recognizes.

These tests run the RENDERED extension under Node (type-stripping) with a
fake ``vibe`` binary and assert the three outcomes stay distinct:

- match    → transform with ``Matched skill:`` injection
- no-match → transform with the no-match fingerprint (no re-route needed)
- failure  → silent ``continue`` (agent falls back to manual `vibe route`)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from vibesop.adapters.models import Manifest, ManifestMetadata
from vibesop.adapters.pi_coding_agent import PiCodingAgentAdapter
from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

from ._vibe_fake_cli import install_fake_vibe

node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

_DRIVER = """\
const handlers = {};
const pi = { on: (event, cb) => { handlers[event] = cb; } };
// Node accepts only file:// URLs for absolute import paths on Windows;
// a bare drive path (e.g. C:/...) is parsed as the 'c:' URL scheme.
const { pathToFileURL } = await import("node:url");
const mod = await import(pathToFileURL(process.argv[2]));
mod.default(pi);
const result = await handlers["input"](
  { text: "please review my code carefully", source: "user" },
  { ui: { notify: () => {} } }
);
console.log(JSON.stringify(result));
"""


@pytest.fixture()
def rendered_extension(tmp_path: Path) -> Path:
    version = subprocess.check_output(["node", "--version"], text=True).strip()
    major, minor = (int(n) for n in version.lstrip("v").split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("Node >= 22.6 required for actual TypeScript execution")
    adapter = PiCodingAgentAdapter(project_root=tmp_path)
    ts = adapter._render_extension("vibesop-route.ts.j2")
    assert ts, "extension template rendered empty"
    ext_path = tmp_path / "vibesop-route.ts"
    ext_path.write_text(ts, encoding="utf-8")

    bin_dir = tmp_path / "bin"
    # Native executable stand-in for the real `vibe` CLI: POSIX shebang
    # script, or a real .exe launcher on Windows so Node's execFileSync can
    # actually spawn it. Behaviour is env-driven (FAKE_VIBE_MODE/RESPONSE).
    install_fake_vibe(bin_dir)

    driver = tmp_path / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    return ext_path


def _run_input_event(ext_path: Path, mode: str) -> dict[str, str]:
    env = dict(os.environ)
    env["FAKE_VIBE_MODE"] = mode
    primary = (
        SkillRoute(skill_id="builtin/session-end", confidence=0.91, layer=RoutingLayer.EXPLICIT)
        if mode == "match"
        else None
    )
    payload = RoutingResult(primary=primary).to_dict()
    # The CLI adds the resolved file path to the serialized routing result.
    payload["skill_file"] = "/tmp/x/SKILL.md" if primary else ""
    env["FAKE_VIBE_RESPONSE"] = json.dumps(payload)
    env["PATH"] = f"{ext_path.parent / 'bin'}{os.pathsep}{env['PATH']}"
    # Fail fast if the actual child PATH resolves anything but the fixture
    # fake (e.g. a real installed `vibe`) — never silently hit the real CLI.
    fake_vibe = ext_path.parent / "bin" / ("vibe.exe" if os.name == "nt" else "vibe")
    resolved = shutil.which("vibe", path=env["PATH"])
    assert resolved is not None, "fake vibe CLI is not resolvable on PATH"
    assert os.path.normcase(Path(resolved)) == os.path.normcase(fake_vibe), (
        f"PATH resolves {resolved!r}; expected fixture fake {fake_vibe!r}"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", str(ext_path.parent / "driver.mjs"), str(ext_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"driver crashed: {proc.stderr}"
    return json.loads(proc.stdout.strip())


@node
def test_match_injects_skill_instruction(rendered_extension: Path) -> None:
    action = _run_input_event(rendered_extension, "match")

    assert action["action"] == "transform"
    assert "## VibeSOP Routing Result" in action["text"]
    assert "Matched skill:" in action["text"]
    assert "builtin/session-end" in action["text"]
    assert "/tmp/x/SKILL.md" in action["text"]


@node
def test_no_match_emits_fingerprint_instead_of_silent_passthrough(
    rendered_extension: Path,
) -> None:
    action = _run_input_event(rendered_extension, "nomatch")

    assert action["action"] == "transform"
    assert "VibeSOP: No matching skill found" in action["text"]
    assert "do NOT re-run `vibe route`" in action["text"]
    # A no-match note must not masquerade as a skill injection.
    assert "Matched skill:" not in action["text"]


@node
def test_hook_failure_stays_silent_and_distinct_from_no_match(
    rendered_extension: Path,
) -> None:
    action = _run_input_event(rendered_extension, "fail")

    # Failure passes through with NO injection — the agent's AGENTS.md
    # fallback (manual `vibe route`) is the degraded path for a broken
    # hook, and it must not be told "no match" when routing never ran.
    assert action == {"action": "continue"}


class TestPiAgentsMdFingerprintCopy:
    """The AGENTS.md routing protocol must list the no-match fingerprint and
    reserve the manual `vibe route` fallback for a missing/failed extension."""

    @pytest.fixture()
    def agents_md(self, tmp_path: Path) -> str:
        adapter = PiCodingAgentAdapter(project_root=tmp_path)
        manifest = Manifest(metadata=ManifestMetadata(platform="pi"))
        result = adapter.render_config_only(manifest, tmp_path / "out")
        assert result.success, result.errors
        return (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    def test_fingerprint_list_includes_no_match(self, agents_md: str) -> None:
        assert "`VibeSOP: No matching skill found`" in agents_md

    def test_fallback_is_for_failure_not_for_no_match(self, agents_md: str) -> None:
        assert "extension not\ninstalled or routing failed" in agents_md
        assert "no skill matched" not in agents_md

    def test_project_template_matches(self, tmp_path: Path) -> None:
        adapter = PiCodingAgentAdapter(project_root=tmp_path)
        manifest = Manifest(metadata=ManifestMetadata(platform="pi"))
        env = adapter._get_template_env()
        context = adapter.get_template_context(manifest)
        rendered = env.get_template("AGENTS.md.project.j2").render(**context)

        assert "`VibeSOP: No matching skill found`" in rendered
        assert "no skill matched" not in rendered
