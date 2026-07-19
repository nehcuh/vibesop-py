# Windows Compatibility — Adversarial Review (Round 1)

> **Status**: Complete (2026-07-19)
> **Reviewer**: adversarial explore agent, against `02-design.md` v1
> **Result**: 2 Blockers, 5 Majors, 7 Minors — design revised (see `02-design.md` v2 section)

## Blockers

### B1 — GBK fallback hooked at wrong layer

Design v1 planned "strict UTF-8 → UnicodeDecodeError → locale retry" but pointed at YAML-branch readers (`manager.py:98,427`). Actual poisoned-config readers are all `open("rb") + tomllib.load`:
- `core/config/manager.py:93-94`, `core/llm_config.py:75-76`, `core/skills/config_manager.py:281`, `cli/commands/build.py:186`, `cli/commands/switch.py:53`

`UnicodeDecodeError` raises inside tomllib and is swallowed by `manager.py:106` `except Exception`. **Resolution**: fallback implemented as `read_bytes()` → `decode("utf-8")` → on failure `decode(locale.getpreferredencoding())` + warning → `tomllib.loads(text)`, in a shared helper used by all TOML readers.

### B2 — Project-level config also poisoned, wrongly excluded

`init_support.py:58` writes project `.vibe/config.toml` bare; `llm_config.py:54` reads project config **before** global. zh-CN Windows historical projects are equally poisoned. **Resolution**: GBK fallback covers both `~/.vibe/` and project `.vibe/config.{toml,yaml}`.

## Majors

### M1 — posix=True eats unquoted backslashes

`shlex.split('review src\core\skills\storage.py', posix=True)` → `['review', 'srccoreskillsstorage.py']`. Free-text route queries containing Windows paths would regress. **Resolution**: escape backslashes (`\` → `\\`) before `shlex.split(..., posix=True)`; pin behavior with tests (incl. single-quote edge).

### M2 — storage.py:370 copy-fallback fix is not trivial

Copy-fallback dirs resolve to themselves, never under `CENTRAL_SKILLS_DIR` — keeping `relative_to` check = no fix; dropping it = user's own `~/.claude/skills/` dirs misjudged as packs. **Options**: (a) marker file `.vibe-copy-source` written at copy time, checked at discovery; (b) forward-enumerate flat names + byte-compare SKILL.md. **Resolution: option (a)** — simpler, zero false positives; pre-existing copies stay invisible (documented).

### M3 — P1 inventory incomplete (grep-verified)

Missing from v1 list: `core/sessions/tracker.py:211` (same-class bug as P0-4!), `cli/commands/instinct_cmd.py:255,277,291`, `core/skills/understander.py:772,788`, `cli/commands/trace_cmd.py:113`, `cli/commands/skill_commands.py:904,913`, `core/preference.py:219,245`, `installer/analyzer.py:126`, `builder/dynamic_renderer.py:75`, `cli/commands/build.py:190`, `cli/commands/switch.py:57`, `cli/commands/session_cmd.py:177,183,202,215`, `cli/main.py:1463,1473,1494`, `integrations/detector.py:265`, `cli/commands/loop_cmd.py:102`. **Resolution**: merged into P1 batch list; each batch ends with grep-zero verification.

### M4 — HOME isolation needs 3 layers

`Path.home()` doesn't cache, but ~9 modules freeze home into ClassVars at import (`storage.py:84-92`, `pack_installer.py:40-45`, `pack_lock.py:52`, `trust.py:26`, `skills/config_manager.py:93`, `llm_config.py:53-62`, `deploy.py:16-20`, `verify.py:33-69`, `candidate_manager.py:240-243`, `external_loader.py:66-68`, `skill_auditor.py:119-121`, `detector.py:88-90`). Also Git Bash sets `HOME`, which overrides `USERPROFILE` in `ntpath.expanduser`. **Resolution**: autouse fixture = setenv `HOME`+`USERPROFILE` (+`HOMEDRIVE`/`HOMEPATH`) + `monkeypatch.setattr(Path, "home", ...)` + explicit ClassVar redirects (pattern from `tests/installer/conftest.py:16`).

### M5 — probe cache discipline

`lru_cache` on probe: (1) mock-based fallback tests need `cache_clear` in setup; (2) transient failures (Defender) must not cache `False` — cache only `True`; (3) probe residue risk — dot-prefixed name + `try/finally` + `mkdir(parents=True)` first. **Resolution**: all three adopted.

## Minors (adopted)

- m1: `badges.py:128` `except OSError: pass` → use `utils/atomic_writer.write_text` + warning (same for `tracker.py`).
- m2: win32 hook check → `shutil.which("bash")` + non-empty script, more informative than existence-only.
- m3: `base.py:487` — clean partial copytree residue before stub fallback.
- m4: `storage.py` rmtree sites (`:166,283,322,345`) → reuse `pack_installer._safe_rmtree` (readonly-retry) for Windows PermissionError.
- m5: Windows CI job drops `--cov-fail-under` + codecov; adds `--reruns 2`.
- m6: exec-bit assertion sites = 12 (not ~9); `skill_auditor.py:577` silent skip → add debug log.
- m7: fcntl guards confirmed fine.

## Verified Accurate (no change)

P0-1, P0-2, P0-4 (problem), P0-6, P0-7 (direction), P0-8, (e) bucket analysis, junction rejection, 88-failure census (41+13+14+10+3+7).
