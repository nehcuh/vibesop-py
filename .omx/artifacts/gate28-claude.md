# Gate 28 Review — CLI_REFERENCE.md (Loop + M12 Discovery)

**Verdict: PASS_WITH_NITS** — 2 MINOR, 3 NIT. Every flag, default, and subcommand name checks out against the code; no invented capabilities; no removed/renamed surface. Two behavioral claims are subtly wrong and worth one-line fixes. All verification below is `[inspected]` (static read of `loop_cmd.py`, `skill_commands.py`, `core/loop/{models,store,executor,launchd}.py`, `core/observability/{skill_promote,discovery,behavior_consistency}.py`, CHANGELOG `[Unreleased]`); I did not execute the CLI.

## Findings

**1. MINOR — Edit-guard parenthetical is inverted** (docs/user/CLI_REFERENCE.md:1031-1032)
> "(content hash, not mtime, so whitespace-only edits don't count)"

Backwards. The guard compares sha256 of file bytes (`skill_commands.py:2039` vs recorded `draft_sha256`); a whitespace-only edit **changes the hash → counts as an edit → activation is allowed** (`skill_commands.py:2063-2077`: hash differs → "Draft edited since generation" → proceed). What actually "doesn't count" is an mtime-only change (`touch`). As written, users will over-trust the guard (any trailing newline satisfies it). Note the source confusion is in the code comment itself (`skill_commands.py:1856-1858`: "mtime checks are spoofable by whitespace-only edits" — also wrong; whitespace edits update mtime too). Suggested fix: "(content hash, not mtime, so a bare `touch` doesn't count — but any byte change, even whitespace, does)".

**2. MINOR — "launchd job keeps spamming failures every minute" overstates** (CLI_REFERENCE.md:1279-1280)
After quarantine, `load_spec` returns None, so `tick --name X` matches nothing and falls into the no-trigger branch (`loop_cmd.py:891-943`), printing "本轮无到期 loop（0 eligible, 0 skipped）" and **exiting 0**. The job fires every minute but does not fail — the real symptom is a *silent no-op* (arguably worse for diagnosis). The CHANGELOG line 18 makes the identical claim, so fix both together. The actionable content (back up before downgrade; `.corrupt` quarantine naming; `delete` rmtrees the backup) is all correct (`store.py:174-191`, `store.py:75-87`).

**3. NIT — Broken intra-page anchor** (CLI_REFERENCE.md:1289)
Link `#vibe-loop-pause-resume-reset-v810` vs heading `#### \`vibe loop pause\` / \`resume\` / \`reset\` (v8.1.0)` (line 1373). GitHub strips the slashes and keeps both surrounding spaces → anchor is `#vibe-loop-pause--resume--reset-v810` (double hyphens). All other 15 added anchors verified correct, including the `v5.3.0+` → `v530` convention.

**4. NIT — TOC omissions** (CLI_REFERENCE.md:29-43)
`vibe skill discover dismiss` (line 998), `vibe loop pause/resume/reset` (1373), and `vibe loop uninstall-launchd` (1501) have no TOC entries. Reachable via the `vibe loop` subcommand list and "see below" respectively, and the file already has TOC gaps — but the pause/resume/reset heading is only findable through the already-broken link from finding 3.

**5. NIT — uv-whitelist rail phrased as unconditional** (CLI_REFERENCE.md:1493-1495)
"refuses a `uv` binary outside the whitelist … unless `--trust-uv-path`" — the check only runs when **auto-resolving** the default prefix (`loop_cmd.py:1232-1246`). An explicit `--vibe-prefix /any/where/uv` bypasses the whitelist entirely, no warning. One clause ("when auto-resolving the default prefix") would make it accurate.

## Verified correct (spot-list)

- **Defaults/flags, all exact**: `--limit` 100, `--days` None ("no filter", malformed timestamps kept, rec 7-30), `--min-cluster-size` 3, `--min-gold-rate` 0.6, `--behavior-threshold` 0.5 (`behavior_consistency.py:43`), miss knobs 0.7/3/2 (`skill_promote.py:137-146`), `--mute-days` 14 (`discovery.py:90`), `--schedule` `0 0 * * *`, `--max-failures` 3, unstable cutoff 0.30, `HISTORY_HIT_THRESHOLD` 5, preset trio keys.
- **"Exactly one target"** is genuinely XOR — model validator (`models.py:298-309`), not just the CLI `any()` pre-check.
- **Ownership semantics**: pinned only by create/adopt/migrate-ownership (`models.py` field doc, loop_cmd); `_owns` unscoped→True, cwd-inside-root one-directional (`loop_cmd.py:80-102`); list default + `--all` Project column + `(global)` + hidden-count hint; show/pause/resume/reset/delete unfiltered; tick skip line capped at 5 with total, printed before all early returns; `--name`/`--all` bypasses; non-zero exit on any failure; executor runs in owning root (subprocess `cwd` for command targets `executor.py:422-424`, `AgentRuntime(project_root=…)` for routing `loop_cmd.py:1001-1006`); missing root → PERMANENT + adopt/reset suggestion (`executor.py:222-242`).
- **Downgrade mechanics**: `extra="forbid"` on both `LoopSpec` and `LoopState` (`models.py:144,369`), state embeds spec copy, quarantine renames to `.corrupt`, `delete_spec` rmtrees the directory including backups.
- **M12**: 8-char prefix resolution exact→unique→ambiguous-listing-no-mutation in both resolvers; earliest-wins `first_seen_at` with `created_at` fallback (`skill_promote.py:561-568`, `discovery.py:515-516`); four behavior render states incl. `未采集`; guard no-rebaseline on re-promote + legacy `--force`; global activate = cross-project evidence (or `--force`) **and** always-interactive privacy confirm; `--force` forwarded to installer; dismiss/promote/discover-dismiss mechanism split accurate.
- **launchd**: plist invokes `tick --name`, bootstrap `gui/$(id -u)`, bootout→bootstrap refresh, no ownership backfill + mismatch warning, `--keep-plist`, idempotent uninstall; `../loop-setup-guide.md` resolves; Quick Reference rows match; CHANGELOG `[Unreleased]` aligned.

Findings 1 and 2 are the ones I'd ask the author to address before merge; 3-5 are optional polish.
