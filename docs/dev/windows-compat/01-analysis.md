# Windows Compatibility — Root Cause Analysis

> **Status**: Complete (2026-07-19)
> **Input**: 4 parallel analysis agents (encoding / symlink+permission / paths+Unix assumptions / failure census+CI)
> **Baseline**: `uv run pytest -q -m "not benchmark and not slow"` on Windows 11, zh-CN locale (GBK), Python 3.12.13, non-privileged shell

## Test Baseline

```
88 failed, 4194 passed, 24 skipped, 15 deselected in 169.67s
```

## Failure Buckets

| Bucket | Count | Nature |
|--------|-------|--------|
| (a) Encoding (GBK vs UTF-8) | 41 | Mixed: real src bugs + test bugs |
| (b) Symlink privilege (WinError 1314) | 13 | Mostly environment, 2 real src bugs |
| (c) Executable bit assertions | 14 | Test-only + 3 src false-positive sites |
| (d) Path separator assertions | 10 | Mostly test-only, 1 src fix |
| (e) shlex quote handling | 3 | Real src behavior bug |
| (f) Other | 7 | 2 real silent-data-loss bugs + flakes |

## (a) Encoding — 41 failures

**Root cause chain**: write without explicit encoding → GBK locale writes GBK bytes → read back as UTF-8 → crash. Both directions exist.

Real source bugs:

- `src/vibesop/core/routing/scenario_layer.py:54` reads `core/registry.yaml` with platform default encoding → GBK decode fails → **scenario routing silently disabled** on zh-CN Windows (`vibe route` falls to fallback-llm). Contrast: `core/config/manager.py:611` already uses utf-8.
- `src/vibesop/installer/init_support.py:228` writes `~/.vibe/config.toml` without encoding; template contains `─` (U+2500) → written as GBK on zh-CN Windows → tomllib (TOML spec mandates UTF-8) can never read it back. **Self-poisoning**: the tool writes a config it cannot read.
- ~116 bare IO calls in src without `encoding=` (30 `read_text()`, 33 `write_text()`, 53 `.open()`). Most dangerous: `core/feedback.py` (6 sites, `ensure_ascii=False` → non-ASCII guaranteed), `core/routing/cache.py:109,180`, `core/instinct/learner.py:170,516`, `core/skills/*` jsonl stores.
- Existing infrastructure underused: `utils/atomic_writer.py` (defaults utf-8), `constants.py:47-54` (`DEFAULT_ENCODING`), `adapters/base.py:309` (`write_file_atomic`, already utf-8).

Test-side bugs (src correct, test wrong):

- `tests/cli/test_analyze_commands.py:33` writes Chinese jsonl via default encoding (GBK); `core/session_analyzer.py:250` correctly reads utf-8 → fixture at fault.
- ~355 bare IO calls in tests; adapter tests read generated hook scripts (`vibesop-route.sh.j2:2` contains `—`) with bare `read_text()` → GBK decode error at byte 52.

## (b) Symlink — 13 failures

- WinError 1314 = missing `SeCreateSymbolicLinkPrivilege` (needs admin or Developer Mode).
- Adapter fallback exists but is **silent**: `adapters/base.py:482` `except OSError → copytree` (no log); `:487` bare `except Exception: pass` can overwrite real content with a stub.
- Real src bugs:
  - `core/skills/storage.py:294` — `symlink_to(skill_path)` **missing `target_is_directory=True`** → even privileged Windows builds a broken file-type link to a directory.
  - `core/skills/storage.py:370` — pack discovery hardcodes `if not entry.is_symlink(): continue` → after copy-fallback, pack skills are **invisible to `vibe skills list`**.
- ROADMAP already tracks the debt: `docs/ROADMAP.md:592` (symlink→copytree fallback lacks tests).
- Junction alternative **rejected**: `Path.is_symlink()` returns False for junctions → breaks all existing checks; junction creation needs subprocess/ctypes.

## (c) Executable bit — 14 failures

- `os.chmod(0o755)` on Windows only toggles the read-only flag; `st_mode & 0o111` is always 0 → assertions fail deterministically.
- Production false-positives: `hooks/installer.py:276` (`verify_hooks`), `cli/commands/verify.py:183,252` → `vibe verify` always misreports on Windows.
- Exec bit is not actually required: all hook registrations invoke `bash <script>` (`claude_code.py:464`, `kimi_cli.py:179`), needing only read permission + bash on PATH.

## (d) Path separators — 10 failures

- Mostly test assertions hardcoding `/` (`tests/builder/test_renderer.py:67`, `tests/installer/test_pack_installer.py:585`, etc.).
- One src fix: `agent/runtime/agent_runtime.py:183` emits `str(p)` (backslashes on Windows, escaped to `\\` in hook JSON) while sibling branches `:184/:187/:189` always emit forward slashes → change to `p.as_posix()` for deterministic cross-platform output.

## (e) shlex — 3 failures (real behavior bug)

- `core/skills/slash_commands.py:118` and `agent/runtime/slash_command_executor.py:107`: `shlex.split(..., posix=(os.name != "nt"))`. `posix=False` **keeps quote characters** → on Windows `/vibe-route "review this"` feeds literal quotes into the routing query, degrading match quality. `posix=True` is a pure lexer choice, platform-independent.

## (f) Other — 7 failures

1. **Silent data loss (2 real bugs)**: `core/sessions/tracker.py:252-257` and `core/badges.py:124-128` — `mkstemp` + `open(fd, closefd=False)` leaks the fd → Windows `Path.replace()` on an open file → WinError 32 → swallowed by `except` → **session state / badges.json never persist on Windows, with no error**.
2. Environment coupling: `tests/installer/test_installer.py:118` reads real `~/.vibe/config.toml`; `tests/builder/test_renderer.py:59` writes real `~/.config/opencode/`; `tests/core/skills/test_skill_storage.py:226` touches real `~/.claude/skills/`.
3. Timing flakes (2): Windows clock granularity (`test_base.py::test_add_message`, `test_conversation.py::test_cleanup_expired`).
4. Defender flake (1): `skill_auditor.py:577-578` silent `except OSError: continue` amplifies transient file locks.

## Test Infrastructure Gaps

- `tests/conftest.py` (86 lines): **zero platform handling** — no skipif, no encoding, no HOME isolation. Only pre-existing Windows special-case: `tests/security/test_path_safety.py:93`.
- `pyproject.toml` pytest config: no platform markers (`--strict-markers` requires registration), no filterwarnings.
- CI (`.github/workflows/ci.yml`): all 5 jobs `ubuntu-latest`; no OS matrix. Docs claim "Cross-Platform: Windows, macOS, Linux compatible" (`docs/PROJECT_STATUS.md:18`) — unenforced.

## Verified Environment Facts

- uv 0.11.29 installed at `~/.local/bin`; Python 3.12.13 via `uv python install`.
- `vibe doctor` passes; `vibe route` works but degrades to fallback-llm due to (a) registry.yaml + config.toml encoding.
- User machine already poisoned: `C:\Users\HuChen\.vibe\config.toml` contains GBK bytes.
