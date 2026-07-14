# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-07-14 (S30) 技能架构梳理、迁移与清理
**Session**: 全面梳理项目技能存储架构，迁移自定义技能到 cross-cutting，清理重复和损坏条目。
**Completed**:
- 梳理 128→116 个技能目录，按命名空间分类（builtin/mattpocock/omx/superpowers/personal）
- 发现三层技能存储架构：~/.config/skills/ → ~/.claude/skills/ → .pi/skills/
- 删除 12 个与 builtin 重复的别名目录 + 6 项重复/损坏
- personal-kimi-gated-fix → cross-cutting/kimi-gated-fix.skill（git 跟踪）
- Fuck_My_Shit_Mountain（364K, 50 文件）→ cross-cutting/fuck-my-shit-mountain.skill
- 配置 cross-cutting namespace（priority 110）自动安装
**Verification**: 3 个 cross-cutting 技能就位，JSON 配置有效
**Next**: git commit + push；验证 vite route 能发现全部 cross-cutting 技能

### 2026-07-09 (S29) audit-T1-merge-and-gitignore-cleanup
**Session**: Closed the 2026-07 audit Immediate scope and cleaned repository state.
**Completed**:
- Merged PR #69 (`fix/pack-lock-f02`) — T1 supply-chain hardening for F-01/F-02/F-03/F-10. Applied Kimi review fixes: trust hash binding gated on `pack_path`, `compute_pack_hash` moved to `PackInstaller`, `protocol.file.allow=never`, `.vibesop-build` added to pack audit extensions, pack-lock tests isolated.
- Verified `make check` green locally and CI all pass (Lint, Type Check, Test 3.12/3.13, Security Scan, Performance Benchmark, CodeQL).
- Created and merged PR #70 — `.gitignore` cleanup ignoring `.claude/`, `.pi/skills/`, and `audit-report-*`. Ran lightweight Kimi dual-lane review; fixed `/audit-report-*` anchoring.
- Synced local `main` with `origin/main` after squash merges.
**Verification**: PR #69 merge commit `7f58746f`; PR #70 merge commit `d3875656`; `git status` clean.
**Next**: Decide whether to continue with the deferred T4/T5/T6 audit batches or address GitHub dependabot alerts.

### 2026-06-14 (S28) path-safety-symlink-toctou-hardening (v7.0.5)
**Session**: Phase 5 (final) from S23 Multi-Agent Squad remediation plan.
**Trigger**: S23 red-team flagged `path_safety.py:121` using `resolve()` which follows symlinks; the code had a comment self-admitting the issue.
**Completed**:
- `src/vibesop/security/path_safety.py`:
  - Module docstring rewritten to document the lexical-vs-resolve asymmetry: `check_traversal` is the adversarial-input gate (lexical only, no symlink following); `check_overlap` / `verify_writable` / `ensure_no_overlap` use resolve() but only operate on already-trusted paths.
  - `check_traversal` rewritten: lexical normalization (`os.path.abspath` + `os.path.normpath`) + per-component `lstat` symlink detection + `os.sep`-suffix prefix-collision-resistant containment check.
  - 3 new helpers: `_lexical_normalize`, `_is_lexically_within`, `_no_symlinks_in_chain`.
  - `validate_filename` adds NUL byte rejection.
  - `ensure_safe_output_path` rejects NUL bytes in the full input path and calls `validate_filename` on the leaf name.
- `tests/security/test_path_safety_symlink.py` (NEW) — 28 tests across 6 suites (TestCheckTraversalSymlinkHardening, TestEnsureSafeOutputPathHardening, TestLexicalNormalize, TestNoSymlinksInChain, TestIsLexicallyWithin, TestValidateFilenameNulHardening). The original S23 red-team PoC (symlink inside base pointing outside) is pinned by `test_symlink_inside_base_pointing_outside_rejected`.
- `CHANGELOG.md` — v7.0.5 section.
**Verification**: 28/28 new tests pass; 400/400 tests in tests/security + tests/installer + tests/hooks + tests/builder pass; basedpyright 0 errors on touched file.
**Plan complete**: S23 Multi-Agent Squad remediation plan now fully closed — Phases 1-5 all delivered (v7.0.1 through v7.0.5). Total: 5 commits, ~130 new tests, 0 new basedpyright errors. Ready to push as v7.0.5 release.

<!-- handoff:end -->
