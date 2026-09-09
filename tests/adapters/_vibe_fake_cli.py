"""Fake native ``vibe`` CLI installable for real Node child processes.

POSIX: shebang script +x. Windows: real console .exe via distlib ScriptMaker
(pip console-script launcher; no shell=True, no .cmd, no template change).
Env-driven behaviour: FAKE_VIBE_MODE=fail exits 1 after "boom" on stderr;
FAKE_VIBE_RESPONSE / ROUTE_RESPONSE is printed to stdout; FAKE_VIBE_CAPTURE_ARGV=1
writes argv[1:] as JSON to argv.json in the CLI's cwd.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_FAKE_VIBE_BODY = '''# -*- coding: utf-8 -*-
"""Fake `vibe` CLI body; installed as vibe (POSIX) / vibe.exe (Windows)."""
import json
import os
import sys


def _capture_argv() -> None:
    if os.environ.get("FAKE_VIBE_CAPTURE_ARGV") != "1":
        return
    dest = os.environ.get("FAKE_VIBE_ARGV", "argv.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(sys.argv[1:], fh)


def main() -> int:
    _capture_argv()
    if os.environ.get("FAKE_VIBE_MODE") == "fail":
        sys.stderr.write("boom\\n")
        sys.stderr.flush()
        return 1
    response = os.environ.get("FAKE_VIBE_RESPONSE", "") or os.environ.get(
        "ROUTE_RESPONSE", ""
    )
    if response:
        sys.stdout.write(response)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def install_fake_vibe(bin_dir: Path, name: str = "vibe") -> Path:
    """Install an executable fake CLI named ``name`` into ``bin_dir``.

    Returns the path Node resolves via PATH (``<bin_dir>/vibe`` on POSIX,
    ``<bin_dir>/vibe.exe`` on Windows).
    """
    bin_dir = Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        return _install_windows_exe(bin_dir, name)
    return _install_posix_script(bin_dir, name)


def _install_posix_script(bin_dir: Path, name: str) -> Path:
    target = bin_dir / name
    target.write_text(f"#!{sys.executable}\n{_FAKE_VIBE_BODY}", encoding="utf-8")
    target.chmod(0o755)
    return target


def _install_windows_exe(bin_dir: Path, name: str) -> Path:
    # distlib is a dev/test dependency already in the lock; its ScriptMaker
    # writes a native launcher .exe (used by pip for console scripts).
    from distlib.scripts import ScriptMaker

    source_dir = bin_dir / "_src"
    source_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / f"{name}.py"
    # First line must look like a python shebang so ScriptMaker's copy path
    # rebuilds the shebang and wraps the body with the launcher instead of
    # copying raw text into a file that is not an executable format.
    source.write_text(f"#!python\n{_FAKE_VIBE_BODY}", encoding="utf-8")
    maker = ScriptMaker(str(source_dir), str(bin_dir))
    maker.executable = sys.executable
    maker.variants = {""}  # only `vibe`, not `vibe-X.Y`
    maker.force = True
    maker.clobber = True
    made = maker.make(f"{name}.py")
    exe = next((Path(p) for p in made if Path(p).name.lower() == f"{name}.exe"), None)
    if exe is None:
        raise RuntimeError(f"distlib failed to produce {name}.exe (wrote {made!r})")
    return exe
