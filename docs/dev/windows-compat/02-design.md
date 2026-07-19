# Windows Compatibility — Implementation Design

> **Status**: v2 — revised after adversarial review (2026-07-19), pending pi sign-off
> **Derived from**: `01-analysis.md`; revisions from `03-adversarial-review.md`
> **Goal**: Full test suite green on Windows (non-privileged, zh-CN locale), no behavior regressions on POSIX, CI gains a Windows gate.

## v2 Revisions (from adversarial review)

1. **GBK fallback layer** (B1/B2): new shared helper (e.g. `utils/encoding.py::load_toml_with_locale_fallback(path)`) implementing `read_bytes()` → `decode("utf-8")` → on `UnicodeDecodeError` `decode(locale.getpreferredencoding())` + `logger.warning` → `tomllib.loads(text)`. Applied to ALL TOML readers (`core/config/manager.py:93`, `core/llm_config.py:75`, `core/skills/config_manager.py:281`, `cli/commands/build.py:186`, `cli/commands/switch.py:53`) for BOTH `~/.vibe/` and project `.vibe/config.{toml,yaml}`. YAML readers get the same try-utf8-then-locale treatment.
2. **shlex** (M1): escape backslashes (`\` → `\\`) before `shlex.split(..., posix=True)` at `slash_commands.py:118` + `slash_command_executor.py:107`; regression tests pin: quoted args, unquoted Windows paths, single-quote edge.
3. **Pack discovery under copy-fallback** (M2): copy sites write marker `.vibe-copy-source` (central source path); `storage.py:list_skills` accepts a real dir only when marker exists and resolves under `CENTRAL_SKILLS_DIR`. Pre-existing copies remain invisible (documented).
4. **P1 inventory** (M3): merged adversarial grep results — 16 additional sites (see 03-adversarial-review.md M3); each batch ends with grep-zero verification.
5. **HOME isolation** (M4): autouse fixture = setenv `HOME`+`USERPROFILE`+`HOMEDRIVE`/`HOMEPATH` + `monkeypatch.setattr(Path, "home", ...)` + explicit ClassVar redirects for the ~12 frozen-at-import modules.
6. **Probe discipline** (M5): cache only `True`; expose `cache_clear`; dot-prefixed probe name + `try/finally` + `mkdir(parents=True)`; tests calling fallback paths must `cache_clear` in setup.
7. **Minors adopted**: atomic_writer for tracker/badges + warning logs; win32 hook check = `shutil.which("bash")` + non-empty script; clean partial copytree before stub; `_safe_rmtree` reused in storage.py; Windows CI without cov-gate/codecov, `--reruns 2`; 12 exec-bit assertion sites; `skill_auditor.py:577` gains debug log.

---

## Guiding Principles

1. **Production bugs before test cosmetics** — 9 real src bugs affect Windows users today.
2. **Explicit encoding everywhere** — project-owned files are always UTF-8; never rely on locale.
3. **Probe, don't assume** — symlink capability is probed empirically (per-directory), never inferred from platform.
4. **Guard assertions, not tests** — exec-bit checks become line-level guards so Windows keeps coverage of everything else.
5. **No POSIX regressions** — every fix must be neutral or beneficial on Linux/macOS; CI ubuntu stays green.

## Phase Plan

### P0 — Production behavior fixes (8 items, ~30 lines)

| # | Location | Fix |
|---|----------|-----|
| P0-1 | `core/routing/scenario_layer.py:54` | `open("r", encoding="utf-8")` |
| P0-2 | `installer/init_support.py:228` (+`:58,73,211-216`) | explicit utf-8 on config template writes |
| P0-3 | `core/skills/slash_commands.py:118`, `agent/runtime/slash_command_executor.py:107` | `shlex.split(..., posix=True)` unconditionally |
| P0-4 | `core/sessions/tracker.py:252-257`, `core/badges.py:124-128` | `os.fdopen(fd, ...)` so the fd is closed before `Path.replace()` (fix WinError 32 silent data loss) |
| P0-5 | `core/skills/storage.py:294` | add `target_is_directory=True`; `storage.py:370` accept real dirs from copy-fallback in pack discovery |
| P0-6 | `agent/runtime/agent_runtime.py:183` | `str(p)` → `p.as_posix()` |
| P0-7 | `hooks/installer.py:276`, `cli/commands/verify.py:183,252` | on win32, degrade exec-bit check to existence check |
| P0-8 | `adapters/base.py:482,487` | log symlink→copy fallback (info); replace bare `except Exception: pass` with warning |

**Acceptance**: `vibe route "帮我调试这个错误"` no longer logs the registry.yaml GBK error; scenario layer active.

### P1 — Encoding unification

Src (by risk):

1. jsonl/data stores with `ensure_ascii=False`: `core/feedback.py` (6), `core/routing/cache.py` (2), `core/routing/candidate_manager.py` (2), `core/routing/conflict.py`, `core/routing/tracer.py` (2), `core/instinct/learner.py` (2), `core/matching/tfidf.py` (2), `core/skills/` stores (featured_registry, ratings, storage, suggestion_collector, trust, external_loader, pack_lock).
2. Config read/write: `core/config/manager.py:98,427`, `core/skills/config_manager.py:284,301`, `core/llm_config.py:78,170`, `cli/commands/config.py:179,189`.
3. Adapter settings reads: `adapters/kimi_cli.py:189`, `claude_code.py:439`, `hook_based.py:163`, `sdk_based.py:112`, `pi_coding_agent.py:406`.
4. SKILL.md/registry IO: `installer/skill_installer.py:178-238`, `installer/installer.py:240`, `core/orchestration/cross_cutting.py:269`, `cli/commands/skills_commands/_discovery.py`, `skill_craft.py`, `instinct_cmd.py:402`, `import_rules.py:91,131`, `verify.py:206`.
5. Remaining bare calls swept via grep; prefer migrating to `utils/atomic_writer` / explicit `encoding="utf-8"`.

User-config fallback (only `~/.vibe/` config files): strict UTF-8 first, on `UnicodeDecodeError` retry with `locale.getpreferredencoding()` + `logger.warning` (no silent rewrite of user files). Project-owned data files stay strict.

Tests: add `encoding="utf-8"` to fixture writes and assertion reads in all failing files (41 failures); sweep remainder opportunistically.

### P2 — Symlink & exec bit

- New `src/vibesop/utils/symlinks.py`: `can_create_dir_symlink(directory)` — empirical probe, `@lru_cache` per directory, handles WinError 1314/1/5. Used at `adapters/base.py:478`, `installer/pack_installer.py:590`, `core/skills/storage.py:293`.
- `tests/conftest.py`: session-scoped `symlink_supported` fixture (same probe). Applied to all symlink tests (incl. `test_skill_storage.py:239,292`, `test_indexer.py:858`, `test_pack_installer.py:311`).
- Exec-bit assertions (~9 sites): `if sys.platform != "win32":` line guard with comment.
- New unit tests mocking `symlink_to` to raise `OSError` → covers fallback on POSIX CI too (pays ROADMAP.md:592 debt).
- Fix `tests/cli/test_skills_cmd.py:168` (`/dev/null` target) and `tests/adapters/test_base.py:354` (add `target_is_directory=True`).

### P3 — Paths & remaining test fixes

- Assertions: `.as_posix()` / `.parts` / `replace(os.sep, "/")` at `test_renderer.py:67`, `test_pack_installer.py:585`, `test_planner.py`, `test_path_safety*.py` (4), `test_prompt_chain_generator.py`.
- `test_agent_runtime.py:155` → compare via `bundled.as_posix()`.
- Timing flakes: replace wall-clock inequality with monkeypatched time or tolerance.

### P4 — Test isolation & CI

- `tests/conftest.py`: autouse fixture redirecting `HOME`/`USERPROFILE` (and `Path.home()` consumers) to tmp per test — eliminates all real-user-dir side effects (`test_renderer.py:59`, `test_skill_storage.py:226`, `test_installer.py:118`).
- `.github/workflows/ci.yml`: add `windows-latest` job (matrix py 3.12/3.13), initially `continue-on-error: true`, flipped to required after two green weeks.
- Docs: `docs/QUICKSTART_DEVELOPERS.md` gains a Windows note (Developer Mode for symlinks, `PYTHONUTF8` optional since code is explicit).

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Encoding sweep touches 100+ sites → churn | Batch by module; grep-verified completeness; full suite after each batch |
| HOME isolation breaks tests relying on real home | Fixture is autouse but overridable; audit failures individually |
| posix=True changes slash parsing of backslash args | Args are queries/pack names, not raw paths; quoted paths survive; fallback `except ValueError` kept |
| Windows CI flaky (Defender) | `continue-on-error` initially; rerun strategy via pytest-rerunfailures (already a dep) |
| `~/.vibe/config.toml` on user machines already GBK | Read-side GBK fallback (P1) repairs transparently; `vibe doctor` note |

## Verification Gates

1. After each phase: `uv run pytest -q -m "not benchmark and not slow"` — failure count must strictly decrease; zero new failures on ubuntu-equivalent reasoning.
2. Final: full suite + `ruff check` + `ruff format --check` + `basedpyright` + smoke (`vibe doctor`, `vibe route`, `vibe skills list`).
3. Review: independent review agents + pi agent sign-off per phase.
