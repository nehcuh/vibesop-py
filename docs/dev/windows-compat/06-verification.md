# Windows Compatibility — Final Verification Report

> **Date**: 2026-07-19
> **Host**: Windows 11 (zh-CN, GBK locale), non-privileged shell, Python 3.12.13 (uv-managed), uv 0.11.29

## Test Suite

```
Baseline (before):  88 failed, 4194 passed, 24 skipped
Final (after):       0 failed, 4281 passed, 37 skipped, 15 deselected (164s)
```

- Zero new failures at every phase gate (verified against pristine-baseline diff at P0).
- 37 skips = 23 symlink-probe skips (host lacks Developer Mode/admin; they execute on capable hosts and POSIX CI) + 14 pre-existing skips (unrelated).
- POSIX safety: every src change is a no-op on UTF-8 locales (explicit utf-8), probe is POSIX-successful, exec-bit POSIX branches byte-identical.

## Static Gates

| Gate | Result |
|------|--------|
| `ruff check src tests` | All checks passed |
| `ruff format --check` | Clean |
| `basedpyright` | 0 errors, 45 warnings (exit 3 = pass per Makefile) |

## Smoke Tests (real CLI, this machine)

| Command | Result |
|---------|--------|
| `vibe doctor` | ✨ All checks passed |
| `vibe route "帮我调试这个错误" --yes` | No `gbk`/`Failed to parse` errors; **SCENARIO layer active** (matched `debugging` scenario; previously silently disabled) |
| `vibe skills list` | Lists skills correctly |
| `vibe config` (GBK `~/.vibe/config.toml` present) | Loads via locale fallback + warning (self-poisoned config healed) |

## Environment Setup (new machine recipe)

```powershell
# uv
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# Python 3.12 + deps
uv python install 3.12 && uv venv --python 3.12 && uv sync --extra dev
# Optional: enable Developer Mode for symlink support (else auto copy-fallback)
```

## Production-Readiness Statement

Windows support is now code-enforced (explicit UTF-8 everywhere, probed symlink fallback, platform-guarded permission checks) and test-enforced (`test-windows` CI job, isolated-home suite). Remaining known limitations: symlink-dependent flows require Developer Mode or admin (graceful copy fallback otherwise, with `.vibe-copy-source` marker preserving discovery); hooks require `bash` on PATH (Git Bash).

## CI Confirmation (2026-07-19, post-merge)

- Run 1 (`a275caa`): ubuntu all green; Windows `4302 passed / 1 failed` → caught `_flatten_skill_name` backslash bug (fixed in `ab9c8df`, see `05-review.md` "Post-merge CI catch").
- Run 2 (`ab9c8df`): **all jobs green** — `Test Windows (Python 3.12/3.13)` ✅, ubuntu `Test (3.12/3.13)` ✅, Lint / Type Check / Security / Benchmark ✅.
- Local vs CI delta explained: local host probe-skips symlink tests (no privilege); elevated CI runners execute them — the two environments are complementary, and the pure-function regression test closes the gap for flatten logic.
