# Windows Compatibility — Review Record

> **Status**: Complete (2026-07-19)
> **Reviewers**: 2 independent review agents (production code / test quality) + pi agent (final verdict)

## Round 0 — Design review (pre-implementation)

Adversarial agent on design v1 → 2 Blockers (B1/B2), 5 Majors (M1–M5), 7 Minors → all incorporated into design v2. pi confirmed decision points A/B/C and approved proceeding. See `03-adversarial-review.md`.

## Round 1 — Implementation review (post P0–P4)

### Production code review (agent 1)

| Severity | Finding | Resolution |
|----------|---------|------------|
| Major M1 | YAML user-config readers lacked locale fallback; `config.py:179` crashed on GBK `config.yaml` (Windows regression) | **Fixed** — 6 readers migrated to `read_text_with_fallback` |
| Major M2 | Corrupt `.vibe-copy-source` marker crashed `list_skills` (`UnicodeDecodeError` uncaught) | **Fixed** — `storage.py:67` except broadened |
| Major M3 | Design-required shlex pin tests missing | **Fixed** — `TestSlashParseWindowsCompat` (4 tests, incl. single-quote edge) |
| Minor m1 | atomic_writer gives 0o644 vs mkstemp's 0o600 (POSIX privacy) | **Fixed** — `chmod 0o600` post-write in `badges.py` / `tracker.py` |
| Minor m2/m3 | `import_rules.py:91`, `session_cmd.py:177,202` user files strict UTF-8 → crash on GBK | **Fixed** — fallback helper |
| Nits | trust.py except; badges broad except; probe pid collision; marker-failure discards good copy | **All fixed** |
| Nit (deferred) | atomic_writer fixed tmp name `<target>.tmp` can collide under concurrent writers | **Documented** — pre-existing behavior across 12 call sites; out of scope |

Verified clean: encoding helper semantics, probe discipline, marker validation chain, exec-bit win32 branch, 8 narrow `UnicodeDecodeError` catches, POSIX no-op sweep, ruff/format/basedpyright.

### Test quality review (agent 2)

**Verdict: suite credibility maintained — no weakening for green.** Exhaustive checks:

- All 437 `+encoding=` additions are pure parameter additions; zero assertion/fixture edits.
- 11 win32 guards wrap only POSIX-permission assertions; content assertions still run everywhere.
- 23 probe-skips only where the host lacks symlink privilege (was already skip-or-fail before).
- Modified assertions are semantics-equivalent or stricter (`parents` vs `startswith`).
- Timing pins preserve test intent.
- New tests (symlinks ×8, marker, shlex) assert real production contracts.
- passed→skip: only 2, both home-isolation side effects on environment-dependent tests (`unified_system.py:200`, `quick_commands.py:35`) — documented, acceptable.
- Conftest redirect audit: 11 modules verified against source structure; `AGENT_CONFIGS` gap found (L2) → **fixed**; docstring wording fixed.

## Round 2 — pi final verdict

> **SHIP** — "No critical issues found. 4281 passed / 37 skipped / 0 failed supports the verdict."

pi re-verified: probe caching discipline, uuid probe naming, `safe_rmtree` consolidation, encoding helper scoping, shlex backslash doubling, marker graceful degradation, atomic_writer consolidation with restored 0o600, conftest frozen-ClassVar coverage.

## Round 3 — Grok (xAI) independent review

External reviewer (`xai-grok-pager`, single-turn headless + tools). Verdict: **SHIP**, zero critical findings.

Independently spot-checked and confirmed sound: `encoding.py` (no double-decode path), `symlinks.py` (normcase cache keys, cleanup discipline), marker gate in `list_skills` (bypass requires write access = already trusted), shlex doubling (Linux no-op; no divergent input constructible), atomic_writer migration (strictly better than mkstemp leak), `adapters/base.py` fallback flow (no gap vs old). Test-weakening audit of 5 nontrivial diffs: all pure encoding additions or probe-skips; assertions preserved. POSIX regression check: **zero** (locale fallback is byte-identical on UTF-8 locales).

Caveat: Grok's headless session truncated before it could re-run the full suite itself; suite numbers rest on the three direct runs recorded in `06-verification.md`.

New observations added to deferred items (4) and (5) below.

## Deferred items (tracked, non-blocking)

1. `test-windows` CI job: `continue-on-error: true` → flip to required after 2-week observation (noted in ci.yml comment).
2. atomic_writer tmp-name collision under concurrent writers (pre-existing; needs atomic_writer redesign, affects all 12 call sites).
3. `quick_commands.py:35` — optionally pre-install a skill in isolated home to restore coverage.
4. `quickstart_runner.py:297` — could adopt probe for consistency (behavior already correct via try/except).
5. Conftest frozen-ClassVar redirect list is a maintenance burden: any future module freezing `Path.home()` at import time must be added manually (Grok R3). Consider an import-time lint or a centralized path-registry module.
6. Marker `relative_to` validation is case-sensitive post-`resolve()`; a hand-crafted mixed-case marker could theoretically bypass (requires platform-dir write access — already a trusted operation) (Grok R3).

## Post-merge CI catch (2026-07-19, fixed in follow-up commit)

First real `windows-latest` CI run: **4302 passed, 1 failed** (ubuntu all green —
zero-POSIX-regression claim externally confirmed). The single failure was a
genuine Windows-only production bug the local privilege-less host could not
reach (its symlink tests probe-skipped, CI runners are elevated):

- `pack_installer._flatten_skill_name` replaced only `/`, but `rel_path` comes
  from `Path.relative_to()` (native separators = `\` on Windows) → nested
  "flat" names (`packB-deeply\nested\review`) → `symlink_to` WinError 3.
- Fix: normalize `\` → `/` before flattening; pure-function regression test
  added (`test_flatten_skill_name_normalizes_separators`, runs without
  symlink privilege — closes the probe-skip blind spot for this logic).
- Lesson recorded: probe-skipped tests hide privileged code paths locally;
  prefer extracting pure logic into privilege-free unit tests where possible.
