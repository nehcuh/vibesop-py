# Windows Compatibility — Implementation Log

> **Status**: Complete (2026-07-19)
> **Result**: `88 failed / 4194 passed` → `0 failed / 4281 passed / 37 skipped` (full non-benchmark suite, Windows 11 zh-CN, non-privileged)

## Phase 0 — Design (docs 01–03)

- 4 parallel analysis agents → `01-analysis.md` (6 root-cause buckets, 88 failures).
- Design v1 → adversarial review (2 Blockers, 5 Majors, 7 Minors) → design v2.
- pi agent sign-off on decision points: marker-file pack discovery (A), backslash-escape + posix shlex (B), shared TOML locale-fallback helper (C).

## Phase 1 — P0 production fixes (23 files, +292/−96)

`77 failed` after this phase (12 fixed, 0 new).

- New `utils/encoding.py`: `load_toml_with_fallback` / `read_text_with_fallback` (UTF-8 strict → locale fallback + warning).
- TOML readers migrated: `config/manager.py`, `llm_config.py`, `skills/config_manager.py`, `build.py`, `switch.py`.
- `scenario_layer.py:54` registry.yaml read → utf-8 (**scenario routing no longer silently disabled** on zh-CN Windows).
- `init_support.py` 6 config-template writes → utf-8 (**stops config.toml self-poisoning**).
- shlex: `slash_commands.py` + `slash_command_executor.py` — backslash-escape + `posix=True` (**quotes no longer leak into route queries**).
- fd leaks: `tracker.py` + `badges.py` → `atomic_writer` (**session state / badges now persist on Windows**).
- `storage.py:294` `target_is_directory=True`; `.vibe-copy-source` marker at all copy-fallback sites; `list_skills` marker-gated pack discovery; `safe_rmtree` extracted to utils.
- `agent_runtime.py:183` → `as_posix()` (deterministic hook paths).
- Exec-bit: `hooks/installer.py`, `verify.py` — win32 degrades to `shutil.which("bash")` + non-empty.
- `adapters/base.py` fallback gains logging + partial-copy cleanup.

## Phase 2 — P1 encoding unification (111 files)

`36 failed` after this phase (41 encoding failures eliminated, 0 new).

- src: 77 explicit `encoding="utf-8"` across 38 files; grep-verified zero bare text-IO calls.
- 8 `except` sites gain `UnicodeDecodeError` (tolerate pre-existing GBK cache files; they self-heal to UTF-8 on next write).
- `prompt_chain/validator.py` subprocess readers → utf-8 + `errors="replace"`.
- tests: 436 encoding fixes across 73 files (tokenize-based batch tool, triple-verified).

## Phase 3 — P2 symlink/exec + P3 paths/misc (31 files)

`0 failed` after this phase (23 fixed, 13 probe-skipped on privilege-less host).

- New `utils/symlinks.py`: empirical `can_create_dir_symlink` probe; caches only `True`; `clear_cache()` for tests.
- Probe integrated at 3 creation points (`adapters/base.py`, `pack_installer.py`, `storage.py`).
- `tests/conftest.py`: session-scoped `symlink_supported` fixture; 23 symlink tests use it.
- 12 exec-bit assertions guarded `if sys.platform != "win32":` (line-level, coverage retained).
- Path assertions normalized (`as_posix()` / `Path.parts`); timing flakes pinned deterministically; `skill_auditor.py:577` silent skip gains debug log; `kimi_cli.py:189` merge read → fallback helper.
- New `tests/utils/test_symlinks.py` (8 tests) incl. mock-OSError fallback coverage (pays ROADMAP.md:592 debt).

## Phase 4 — Test isolation + CI + docs (4 files)

`0 failed / 4277 passed` maintained.

- `tests/conftest.py` autouse `_isolated_home` (3 layers: env vars + `Path.home` patch + 11 frozen-ClassVar redirects) — **zero real-user-dir side effects** (verified by filesystem diff).
- `test_executor.py` — explicit auditor injection (import-order dependency removed).
- `ci.yml` — new `test-windows` job (windows-latest, py 3.12/3.13, `--reruns 2`, no cov-gate/codecov, `continue-on-error: true` → flip to required after 2-week observation).
- `QUICKSTART_DEVELOPERS.md` — Windows dev section.

## Phase 5 — Review fixes (this round)

- M1: 6 user-config YAML readers → `read_text_with_fallback` (`config.py`, `manager.py`, `llm_config.py`, `skills/config_manager.py`, `build.py`, `switch.py`) — fixes `vibe config` crash on GBK config.yaml.
- M2: marker read tolerates `UnicodeDecodeError` (`storage.py:67`).
- M3: 4 shlex pin tests (`TestSlashParseWindowsCompat`).
- Minors: `import_rules.py` / `session_cmd.py` user-file reads → fallback; `trust.py` except +`UnicodeDecodeError`; `badges.py` narrowed except; `chmod 0o600` restored post-atomic-write (POSIX privacy parity with mkstemp); probe name gains uuid suffix; marker-write failure keeps successful copy; conftest redirects `AgentEnvironmentDetector.AGENT_CONFIGS`.
- `ruff format` normalized 26 files.

**Final: `0 failed / 4281 passed / 37 skipped`, ruff clean, basedpyright 0 errors. pi verdict: SHIP.**
