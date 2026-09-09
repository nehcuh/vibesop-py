"""Execute generated routing code against a fake CLI, without the real user config."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from vibesop.adapters.pi_coding_agent import PiCodingAgentAdapter
from vibesop.core.models import RoutingResult

from ._vibe_fake_cli import install_fake_vibe


@pytest.fixture
def route_runtime(tmp_path: Path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node with TypeScript type stripping required")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    major, minor = (int(n) for n in version.lstrip("v").split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("Node >= 22.6 required for actual TypeScript execution")
    # Native executable stand-in for the real `vibe` CLI: a POSIX shebang
    # script, or a real .exe launcher on Windows (distlib ScriptMaker) so
    # Node's execFile/spawn can really run it and we keep a true child
    # process with argv capture and side-effect checks.
    install_fake_vibe(tmp_path)

    def run(source: str, driver: str, payload: object, prompt: str = "review this task"):
        (tmp_path / "route.ts").write_text(source, encoding="utf-8")
        (tmp_path / "driver.mjs").write_text(driver, encoding="utf-8")
        env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
        env.update(
            ROUTE_RESPONSE=json.dumps(payload),
            TEST_PROMPT=prompt,
            FAKE_VIBE_CAPTURE_ARGV="1",
        )
        # Fail fast if the actual child PATH resolves anything but the fixture
        # fake (e.g. a real installed `vibe`) — never silently hit the real CLI.
        fake_vibe = tmp_path / ("vibe.exe" if os.name == "nt" else "vibe")
        resolved = shutil.which("vibe", path=env["PATH"])
        assert resolved is not None, "fake vibe CLI is not resolvable on PATH"
        assert os.path.normcase(Path(resolved)) == os.path.normcase(fake_vibe), (
            f"PATH resolves {resolved!r}; expected fixture fake {fake_vibe!r}"
        )
        result = subprocess.run(
            [node, "--experimental-strip-types", "driver.mjs"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        return json.loads(result.stdout), json.loads((tmp_path / "argv.json").read_text())

    return run


def _pi_source() -> str:
    return PiCodingAgentAdapter()._render_extension("vibesop-route.ts.j2")


PI_DRIVER = """
import register from './route.ts';
const handlers = {};
register({on: (event, callback) => {handlers[event] = callback;}});
console.log(JSON.stringify(await handlers.input({text: process.env.TEST_PROMPT, source: 'user'}, {})));
"""


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        None,
        {"has_match": "false"},
        {"has_match": True},
        {"has_match": True, "primary": {"skill_id": 42}},
    ],
)
def test_pi_malformed_result_is_failure_not_completed_no_match(route_runtime, payload):
    result, _ = route_runtime(_pi_source(), PI_DRIVER, payload)
    assert result == {"action": "continue"}
    assert "text" not in result


@pytest.mark.parametrize("platform", ["pi", "opencode"])
def test_input_is_one_literal_argument_without_shell_side_effects(
    route_runtime, tmp_path, platform
):
    prompt = 'review"; touch harmless-proof; #\n$(touch other-proof) `touch third-proof` \\ end'
    if platform == "pi":
        source, driver = _pi_source(), PI_DRIVER
        prefix = ["route", "--json", "--yes"]
    else:
        template = (
            Path(__file__).parents[2]
            / "src/vibesop/adapters/templates/opencode/plugin/vibesop/index.ts"
        )
        text = template.read_text()
        function = re.search(r"async function routeWithVibeSOP\(.*?\n\}", text, re.DOTALL)
        assert function
        import_line = next(line for line in text.splitlines() if 'from "child_process"' in line)
        source = import_line + "\nexport " + function.group()
        driver = """import {routeWithVibeSOP} from './route.ts';
console.log(JSON.stringify(await routeWithVibeSOP(process.env.TEST_PROMPT, 'session')));"""
        prefix = ["route", "--conversation", "session", "--json"]
    payload = RoutingResult(query=prompt).to_dict()
    _, args = route_runtime(source, driver, payload, prompt)
    assert args == [*prefix, prompt]
    assert not any(
        (tmp_path / name).exists() for name in ("harmless-proof", "other-proof", "third-proof")
    )
