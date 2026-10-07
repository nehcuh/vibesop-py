"""Capture real `vibe` CLI output for the intro video.

Outputs ANSI text files into dist/video/raw/*.ansi.

- `route`: runs against this repo (real routing, real skills).
- `loop` / `candidates` / `promote`: run inside an isolated demo sandbox
  (temporary HOME + throwaway git project) so the user's real loops and
  observability data are never touched. These frames are labelled
  "演示数据" in the video.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dist" / "video" / "raw"
VIBE = REPO / ".venv" / "bin" / "vibe"
PY = REPO / ".venv" / "bin" / "python"
DEMO = Path("/tmp/vibesop-video-demo")
DEMO_HOME = DEMO / "home"
DEMO_PROJ = DEMO / "home" / "Projects" / "shop-api"

REAL_HOME = str(Path.home())


def _env(home: str, columns: int = 100) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "HOME": home,
            "FORCE_COLOR": "1",
            "COLUMNS": str(columns),
            "TERM": "xterm-256color",
            "VIBE_NO_UPDATE_CHECK": "1",
        }
    )
    return env


def _redact(text: str) -> str:
    """Replace home paths with '~', padding so Rich box borders stay aligned."""
    for raw in ("/private" + str(DEMO_HOME), str(DEMO_HOME), REAL_HOME):
        lines = []
        for orig in text.split("\n"):
            line = orig
            if raw in line:
                n = line.count(raw)
                line = line.replace(raw, "~")
                # pad before a closing box border if present, else at end
                pad = " " * ((len(raw) - 1) * n)
                idx = line.rfind("│")
                line = line[:idx] + pad + line[idx:] if idx > 0 else line
            lines.append(line)
        text = "\n".join(lines)
    return text


def run(
    name: str,
    args: list[str],
    cwd: Path,
    home: str,
    columns: int = 100,
    max_lines: int | None = None,
) -> str:
    proc = subprocess.run(
        [str(VIBE), *args],
        cwd=cwd,
        env=_env(home, columns),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    out = _redact(proc.stdout + proc.stderr)
    if max_lines:
        out = "\n".join(out.splitlines()[:max_lines])
    (OUT / f"{name}.ansi").write_text(out, encoding="utf-8")
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out)
    print(f"--- {name} (exit {proc.returncode}, {len(plain.splitlines())} lines)")
    return out


def setup_demo() -> None:
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO_PROJ.mkdir(parents=True)
    (DEMO_PROJ / "pyproject.toml").write_text('[project]\nname = "shop-api"\nversion = "0.1.0"\n')
    subprocess.run(["git", "init", "-q"], cwd=DEMO_PROJ, check=True)

    # Seed candidate pool with representative clusters via the real model.
    seed = f"""
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from vibesop.core.observability.skill_promote import ClusterCandidate, ClusterCandidateStore
now = datetime.now(UTC)
proj = {str(DEMO_PROJ)!r}
other = {str(DEMO_HOME / "Projects" / "admin-web")!r}
store = ClusterCandidateStore(Path(proj) / ".vibe" / "observability")
rows = [
    ("a3f9c21e7b", ["修复 pytest 夹具导致的间歇性失败", "flaky test 反复失败怎么定位"], 9, 0.89,
     ["Grep", "Bash:pytest -x", "Read", "Edit", "Bash:pytest"], {{proj: 6, other: 3}}),
    ("5d20e8a41c", ["发版前检查 CHANGELOG 和版本号", "准备 release"], 7, 0.86,
     ["Read", "Edit", "Bash:uv lock", "Bash:git tag"], {{proj: 7}}),
    ("c81b7f0d93", ["数据库迁移失败回滚", "alembic migration 报错"], 5, 0.80,
     ["Bash:alembic history", "Read", "Edit", "Bash:alembic upgrade"], {{proj: 3, other: 2}}),
]
for cid, queries, n, rate, steps, dist in rows:
    tids = [f"t{{cid}}{{i}}" for i in range(n)]
    c = ClusterCandidate(
        cluster_id=cid + "0" * 30,
        task_ids=tids,
        queries=queries,
        span_count=n,
        gold_rate=rate,
        gold_task_ids=tids[: int(n * rate)],
        created_at=now - timedelta(days=2),
        step_freq={{s: n for s in steps}},
        core_steps=steps,
        project_distribution=dist,
    )
    store.upsert(c)
print("seeded", len(rows))
"""
    subprocess.run([str(PY), "-c", seed], env=_env(str(DEMO_HOME)), check=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. Real routing against this repo.
    run(
        "route",
        ["route", "帮我调试这个报错，测试一直失败", "-y", "--no-replay", "--no-session"],
        cwd=REPO,
        home=REAL_HOME,
        columns=96,
        max_lines=25,
    )

    # 2. Demo sandbox for loop + skill generation.
    setup_demo()
    home = str(DEMO_HOME)
    for preset in ("instinct-assemble", "instinct-promote", "instinct-feedback"):
        run(f"loop_create_{preset}", ["loop", "create", preset, "--preset"], DEMO_PROJ, home)
    run("loop_list", ["loop", "list"], DEMO_PROJ, home, columns=104)
    run(
        "loop_launchd",
        ["loop", "install-launchd", "instinct-promote", "--dry-run"],
        DEMO_PROJ,
        home,
        columns=100,
        max_lines=12,
    )
    run("candidates", ["skill", "candidates"], DEMO_PROJ, home, columns=118)
    run("promote", ["skill", "promote", "a3f9c21e7b"], DEMO_PROJ, home, columns=100, max_lines=7)

    drafts = list((DEMO_PROJ / ".vibe" / "observability" / "skill_drafts").rglob("SKILL.md"))
    if drafts:
        (OUT / "draft_skill.md").write_text(drafts[0].read_text(encoding="utf-8"))
        print(f"--- draft: {drafts[0].relative_to(DEMO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
