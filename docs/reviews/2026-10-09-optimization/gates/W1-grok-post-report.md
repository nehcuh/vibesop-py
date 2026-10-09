# W1 Grok independent post-commit gate

- **Verdict**: **APPROVE**
- **Object**: commit `bb0d1147e95019fb3550df76a3fbfe85fd0d4124`
- **Parent**: `e0b83a05037bb99b4157d453f59ea3e66a603a5d`
- **Canonical patch**: `git diff HEAD^ HEAD` = **23685 bytes**, SHA256 **`60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5`**
- **Lane**: Grok, fresh read-only review of `/private/tmp/vibesop-opt-20261009/snapshots/W1-grok-post`
- **Date**: 2026-10-09
- **Host of this lane**: darwin, Python 3.12.13, pytest 9.1.1, pluggy 1.6.0. This is not a Windows run and not a Linux container run.

This verdict is from runs and reads in this lane. Prior Kimi, GLM, and container numbers are cited only where this lane re-executed them or where a receipt was opened and labeled as prior evidence.

## 1. Commit identity

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `bb0d1147e95019fb3550df76a3fbfe85fd0d4124` |
| `git rev-parse HEAD^` | `e0b83a05037bb99b4157d453f59ea3e66a603a5d` |
| `git diff HEAD^ HEAD` bytes / SHA256 | 23685 / `60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5` |
| Same hash in `W1-frozen.json`, `W1-commit-receipt.json`, `W1-post-frozen.json` | match |
| `git archive HEAD` SHA256 | `844dfade37fc5253a21ae8d3374b98dd7fb5f458b125b5e7b417b9cf0ebda7df` (matches `archive_sha256` in the post receipt) |
| Tracked worktree vs HEAD after this review | empty `git diff HEAD` |

Full patch read (472 lines). Seven committed paths:

- `.github/workflows/ci.yml`
- `.github/workflows/quickstart-e2e.yml`
- `CHANGELOG.md`
- `tests/adapters/test_base.py`
- `tests/adapters/test_claude_code.py`
- `tests/adapters/test_kimi_cli.py`
- `tests/adapters/test_pi_coding_agent.py`

No file under `src/` is in the diff. The qualified copy-fallback behavior is existing product code. This commit adds tests, CI observation, and one changelog entry.

`tests/installer/test_skill_installer.py` is in the frozen whitelist and is **not** in the diff. Its blob is identical at parent and HEAD (`a68f4a1c5a35f07f5162a062ed8f55cd67db3815`). It is included in the five-file run because one of the 17 archived case ids lives there.

### Source blobs

Worktree bytes, `git hash-object`, and `git cat-file HEAD:path` agree for all 8 frozen paths. Content SHA256 matches frozen / commit / post receipts:

| Path | SHA256 |
|---|---|
| `.github/workflows/ci.yml` | `5c08e8ff36c3932cee825f534d9fdaaf929a51ae41413862e9e194a82886cfb1` |
| `.github/workflows/quickstart-e2e.yml` | `16fae2ed286e60cbcb533f9398a79fd34a7aaef7b7fd28a9298b649e5d8ab07a` |
| `tests/adapters/test_base.py` | `300f1182265c2390799fe3be8af6c32fee38991a6e493d469c4642b1265ed6fc` |
| `tests/adapters/test_claude_code.py` | `e6e9e5d58c5349996ecc3635e7ed878d22ce9931d26d22444e7584b421d1f361` |
| `tests/adapters/test_kimi_cli.py` | `ef71b9693a833f397b90496e3916e283ca5b163b2e67a0a1df8e1141d903279f` |
| `tests/adapters/test_pi_coding_agent.py` | `db1442a44d8d2230ab097d4fd0167d3638583950df5ff4c1f62d8fec23d7d78d` |
| `tests/installer/test_skill_installer.py` | `39c5cbb70a1699acf7004113d49bf0d555304d3b78e4bcffbd6ebab5374664dc` |
| `CHANGELOG.md` | `c5eb4a199bc7ddb5598c91d425ae9a709a34437cca013f3a8f155b07febbc2f9` |

The same 8 hashes were measured again after every run in this lane. They did not change. Frozen receipt files and the archived invalid plugin (`816d351997fbf27dc2706cc7616760c6c5d74091fb8ed107a9a9ecc6321aea8e`) were not modified.

The worktree also has four **untracked** diagnosis paths (`.omx/artifacts/diagnosis-W1.diff`, `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/`, `docs/plans/2026-10-09-diagnosis-optimization.json`, `docs/plans/2026-10-09-diagnosis-optimization.md`). They are not in HEAD, not in `git archive HEAD`, and not in the patch. This review did not modify them. The verdict is on the commit.

## 2. Authoring client vs model vs product hook contract

Three different things share the words "Claude" and "Kimi". They are not the same actor.

- **Authoring client**: commit trailer `Co-authored-by: Claude Code (GLM-5.3) <noreply@z.ai>`. That is the Claude Code CLI used as the editor client. The model behind that client on this batch is **GLM-5.3** (z.ai backend). It is not an Anthropic model. A second trailer records Kimi Code as co-author. This lane did not call either API.
- **Product hook / CLI contract**: `ClaudeCodeAdapter` renders a Claude Code settings hook whose command runs `bash` on `vibesop-route.sh`. That contract is a shell script plus JSON registration. It does not select or name an LLM. The quickstart observation step only records `bash --version` and raw LF / CRLF / bare-CR counts of that deployed script. It does not inspect or claim a model.
- **Kimi product adapter**: `KimiCliAdapter.render_config` is the platform renderer under test. It is not the Kimi review lane.

`W1-glm-evidence-corrective-complete.md` was read. It says the archived plugin bytes (`pytest_configure(_config)`) were a post-run lint rewrite and never executed a test. This lane treated those bytes only as a negative control. They were not used as a pass.

## 3. Runs executed in this lane

Toolchain: `uv run --extra dev --frozen python -m pytest`, cwd = the snapshot. `HOME` / `USERPROFILE` / `TMPDIR` pointed at `/tmp/vibesop-opt-20261009/probes-grok-w1-post/`. `PYTHONDONTWRITEBYTECODE=1`. Pytest cache provider disabled. No Docker, no network API, no commit, no push.

The valid force-False plugin is this lane's file `probes-grok-w1-post/grok_w1_post_force_false_valid.py` (SHA256 `312f01087b3efa38a57132253a5b01a0b15fb24c703b667d190fd31a1e47f608`). Hook signature is `pytest_configure(config)`. It replaces `vibesop.utils.symlinks.can_create_dir_symlink` with a function that returns False. Loaded only with `PYTHONPATH` + `-p`. It was never written into the repo.

| Run | Result | Exit |
|---|---|---|
| A ambient, five files, no plugin | **171 passed** (0 skipped) in 3.05s | 0 |
| B same five files, valid force-False plugin | **152 passed, 19 skipped** in 1.06s | 0 |
| C 17 archived case ids (`051b9564…`, copied byte-exact), valid plugin | **1 passed, 16 skipped** in 0.45s | 0 |
| D 4 fallback case ids, valid plugin, `-vv` | **4 passed** | 0 |
| E same 17 case ids, copy of frozen invalid plugin `pytest_configure(_config)` | `pluggy.PluginValidationError` at registration. Argument `_config` is not in the hookspec. No collection line, no passed count. | 1 |
| Public IO probe (below) | `ok: true` | 0 |
| `ruff check` on the four modified test files | All checks passed | 0 |
| `scripts/check_ci_decision_source.py` | 10 workflow jobs, 10 registry entries, all `deterministic \| human` | 0 |

Ambient **171 passed and 0 skipped** on this darwin host. Directory symlinks work here. The 16 and 19 skips appear only after the external plugin forces the production probe False. They are not "this host cannot create symlinks."

## 4. Seventeen case ids and the four fallbacks

Archived list order, under the valid plugin. Progress line was `sss.sssssssssssss`: the fourth nodeid passed; the other sixteen skipped with `directory symlinks not supported on this host`.

**1 pass**

- `tests/adapters/test_base.py::TestWriteFileAtomicAncestorSymlink::test_real_dir_write_with_anchor_still_works` (def at line 725). The committed test no longer takes `symlink_supported`. It writes a real directory under the anchor. It is the one case id that must keep running when the probe is False.

**16 skips (malicious-link cases). These skips are not passes.**

- `test_base.py::TestWriteFileAtomicSymlinkChain::test_rejects_symlink_chain_without_base_dir`
- `test_base.py::TestWriteFileAtomicSymlinkChain::test_explicit_base_dir_rejects_symlink_escape`
- `test_base.py::TestWriteFileAtomicAncestorSymlink::test_caller_anchor_rejects_ancestor_symlink`
- `test_base.py::TestWriteFileAtomicExclusiveTemp::test_preplanted_tmp_symlink_is_not_followed`
- `test_base.py::TestAssertSafeRenderPath::test_refuses_symlinked_leaf`
- `test_base.py::TestAssertSafeRenderPath::test_refuses_symlinked_ancestor_allows_leaf_link`
- `test_claude_code.py::TestSkillContentSymlinkEscape::test_render_does_not_overwrite_central_install`
- `test_claude_code.py::TestSkillContentAncestorSymlinkEscape::test_render_refuses_symlinked_skills_root`
- `test_claude_code.py::TestSkillRenderRefusesBeforeMkdir::test_refused_render_creates_nothing_in_central`
- `test_kimi_cli.py::TestKimiSkillRenderBoundary::test_ancestor_symlink_refused_before_mkdir`
- `test_kimi_cli.py::TestKimiSkillRenderBoundary::test_existing_central_content_untouched`
- `test_kimi_cli.py::TestKimiSkillRenderBoundary::test_per_skill_link_kept_and_central_untouched`
- `test_pi_coding_agent.py::TestRenderAncestorSymlinkRefused::test_refuses_before_creating_central_dir`
- `test_pi_coding_agent.py::TestRenderAncestorSymlinkRefused::test_existing_central_content_untouched`
- `test_pi_coding_agent.py::TestRenderPerSkillSymlinkPreserved::test_per_skill_link_kept_and_central_untouched`
- `tests/installer/test_skill_installer.py::TestSkillInstallerIdValidation::test_install_rejects_symlinked_namespace_segment`

Each of those sixteen skip sites is the `symlink_supported` guard. None of the four new fallback tests is in that skip list.

**4 fallback passes** (per-nodeid `PASSED` lines):

- `tests/adapters/test_base.py::TestRenderCopyFallbackWithoutSymlinkCapability::test_copy_fallback_real_dir_markers_central_untouched_idempotent`
- `tests/adapters/test_claude_code.py::TestSkillCopyFallbackWithoutSymlinkCapability::test_render_copies_real_dir_and_keeps_central_untouched`
- `tests/adapters/test_kimi_cli.py::TestKimiSkillRenderBoundary::test_copy_fallback_real_dir_and_central_untouched`
- `tests/adapters/test_pi_coding_agent.py::TestRenderCopyFallbackWithoutSymlinkCapability::test_copy_fallback_real_dir_and_central_untouched`

**19-skip split on the five-file force-False run:** the 16 case ids above, plus 3 pre-existing tests that already take `symlink_supported` on the parent (`git grep` on `HEAD^`):

- `test_base.py::TestPlatformAdapterEdgeCases::test_clean_orphan_skills_symlink` (skip at line 450)
- `test_claude_code.py::TestSkillContentRender::test_symlink_preserved_on_second_build` (line 406)
- `test_kimi_cli.py::TestKimiCLISkillContentRender::test_symlink_preserved_on_second_build` (line 463)

16 + 3 = 19. 171 − 19 = 152. The new tests are inside the 152, not inside the 19.

## 5. Public IO under a forced-False probe

Separate from pytest, `probes-grok-w1-post/grok_w1_post_public_io.py` set `HOME` to its own directory, replaced the production probe, and called:

- `ClaudeCodeAdapter.render_config`
- `KimiCliAdapter.render_config`
- `PiCodingAgentAdapter.render_config`
- inherited `PlatformAdapter._render_skill_content`

Each call used its own central directory (`SKILL.md` + `extra.bin`) via `metadata.source_path`, a pre-existing output skill `skills/user-kept/SKILL.md`, a project user skill, and a home skill at `$HOME/.config/skills/user-kept-home/SKILL.md`. The probe call returned False (`can_create_dir_symlink(...) is False`).

Observed for every public adapter, first and second render:

- `success` true, `errors` empty
- skill directory `is_dir` and not a symlink
- flattened name `w1grok-20261009-demo` only; skills directory names are exactly `user-kept` and that flattened name
- copied `SKILL.md` equals the central body; `extra.bin` copied
- `.vibe-copy-source` resolves to that central directory
- `.vibe-manifest.json` `id` is `w1grok-20261009/demo` and `source.type` is `pack-copy`
- central tree hash unchanged; central has neither manifest nor copy-source marker
- second render tree hash equals the first (idempotent) and is still a real directory
- `user-kept` bytes unchanged

The base method recorded `SKILL.md` in `files_created`, wrote `pack-copy` for id `w1grok-base-20261009`, and met the same central / user / idempotence checks.

The whole probe `HOME` tree was unchanged, including the home user skill. The project user skill was unchanged.

This is a darwin branch simulation of the unprivileged probe. It is not Windows proof.

## 6. CI and quickstart

Parent vs HEAD `ci.yml`:

- Job set unchanged (10): `lint`, `decision-source`, `artifact-links`, `type-check`, `test`, `test-windows`, `security`, `benchmark`, `routing-eval`, `routing-benchmark`. Decision-source script exit 0.
- Ubuntu coverage command still has `--cov-fail-under=73` (one occurrence, unchanged). `pyproject.toml` `fail_under = 73` is outside this commit.
- Marker filter `-m "not benchmark and not slow"` still twice (ubuntu test + Windows full).
- `--reruns 2 --reruns-delay 1` still three times (Windows boundary, Windows full, benchmark). The Windows commands are the parent commands plus ` -ra --junitxml=test-results-windows-{boundary,full}-py${{ matrix.python-version }}.xml`.
- `test-windows` remains `runs-on: windows-latest`, `fail-fast: false`, `python-version: ["3.12", "3.13"]`. Boundary file list and full marker filter are otherwise the parent commands. Both report steps exist in that one job, so each of 3.12 and 3.13 uploads a boundary report and a full report.
- Action pin census: checkout `34e114876b0b11c390a56381ad16ebd13914f8d5` ×10, setup-uv `38f3f104447c67c051c4a08e39b64a148898af3a` ×10, codecov `b9fd7d16f6d7d1b5d2bec1a2887e65ceed900238` ×1, all unchanged. `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02` goes from 1 (parent) to 3 (parent + two Windows steps). No new pin SHA. Both new steps are `if: always()` and have no `continue-on-error`. A failed test step still fails the job. An upload failure can also fail the job; it does not turn a failed pytest into a pass.

`quickstart-e2e.yml`: pins unchanged, still one job, matrix still `ubuntu-latest` and `windows-latest`. The only step-name delta is `Observe Git Bash version + deployed hook line endings (W1)`, inserted after the spaced-home step and before the injection probe. Spaced-home still exits 1 on its own failures. The observation step has no `if: always()`, so a failed spaced-home step skips it and the job stays failed. Inside the observation step, `bash --version | sed -n '1p'` and the byte-count Python are each `|| true`. It prints the first bash version line and, per scratch-home and spaced-home hook, byte length, LF count, CRLF count, and bare CR (`CR - CRLF`). It does not print file contents. The file contains no `${{ secrets` expression. The one new `secrets.` substring is the comment `never secrets.` Quickstart action pins are unchanged. Existing gates are not weakened.

CHANGELOG: one new Changed bullet for W1, placed above the existing B5 bullet. It says the change collects JUnit/skip evidence and Git Bash hook byte diagnostics and qualifies copy fallback without claiming symlink or Windows ACL proof. No other entry is edited.

## 7. Boundaries (do not read these as done)

1. **Native Windows final CI is pending.** This lane did not run `windows-latest`, Git Bash, or the new JUnit upload. Per-test Windows skip/rerun rows and the real LF/CRLF counts do not exist yet.
2. Forced False here is a **darwin simulation** of `can_create_dir_symlink`. It is not a Windows privilege result. The ambient 171-pass run shows this host can create directory symlinks. Passing on darwin does not pass Windows.
3. The **16 malicious-link cases stay REQUIRED-unverified** wherever the capability probe is false, including a future native Windows job that lacks symlink privilege. A skip of those sixteen must not be counted as a pass and must not be masked. Their assertions do not run when skipped. On this host they did run, and passed, only in the ambient lane where the real probe is true.
4. Linux container evidence was **not re-run** (no Docker in this lane). Inspected prior log `logs/W1-final-after-B5-target-container.log` ends in `171 passed`, and its result JSON records the same patch SHA256. That is a prior Linux container result, not this lane, and not Windows.
5. Source-exact integration counts were **not re-run**. Inspected `final-source-integration-match-bb0d1147.json`: head `bb0d1147…`, `changed_source_tests_workflows: []`, docker tests 7829 passed / 26 skipped, host tests 7839 passed / 16 skipped, with changelog/docs explicitly not claimed byte-identical. Those figures are prior receipts.
6. The invalid historical plugin is a negative control only. Exit 1, zero tests. It is not evidence of a pass.

## 8. Constraints kept

No edits to source, tests, changelog, workflows, patch, or receipts. No commit, push, Docker, provider/API call, or subagent. Probes, temp homes, and pytest basetemp stayed under `/tmp/vibesop-opt-20261009/probes-grok-w1-post/`.

**APPROVE** `bb0d1147e95019fb3550df76a3fbfe85fd0d4124` parent `e0b83a05037bb99b4157d453f59ea3e66a603a5d` patch SHA256 `60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5` (23685 bytes).
