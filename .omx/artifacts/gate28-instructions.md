# Gate 28 review — CLI_REFERENCE.md gap fill (loop + M12 discovery commands)

You are an independent senior reviewer. The attached diff adds two sections to `docs/user/CLI_REFERENCE.md` (repo: /Users/huchen/Projects/vibesop-py, Python CLI `vibe`):

1. A new `## Autonomous Loops` section covering `vibe loop` (create/list/show/pause/resume/reset/delete/adopt/migrate-ownership/tick/install-launchd/uninstall-launchd) including this week's ownership semantics (project_root pinning, list/tick ownership filtering, --all hatches, the extra="forbid" downgrade-quarantine warning).
2. M12 discovery commands under Skills Management: `vibe skill scan-candidates` / `candidates` / `discover` (+ dismiss/--mute/--history) / `promote` (--scope/--activate edit guard/--force) / `dismiss`, including the 8-char prefix resolution, First seen column, and behavior_evidence states (consistent/divergent/unavailable/未采集).

Your job: **verify the docs against the ACTUAL CODE**, not the prose. Ground truth sources: `src/vibesop/cli/commands/loop_cmd.py`, `src/vibesop/cli/commands/skill_commands.py` (and `uv run vibe loop <sub> --help` / `uv run vibe skill <sub> --help` if you want to execute). CHANGELOG.md [Unreleased] entries describe the same changes.

Check:
1. Every flag/subcommand mentioned exists with the documented name and default (e.g. scan --limit default 100, --behavior-threshold default 0.5, mute-days 14).
2. Every behavioral claim matches the code (ownership filter semantics, skip-line cap 5, edit-guard hash behavior, prefix resolution order, First seen fallback, downgrade quarantine mechanism naming `.corrupt`).
3. Nothing the diff documents was removed/renamed. No invented capabilities.
4. TOC anchors and internal links are consistent with the file's conventions.
5. Anything user-misleading (overpromise, wrong default, wrong exit behavior).

Output: verdict PASS / PASS_WITH_NITS / BLOCK + numbered findings with severity + line refs. Be adversarial; do not rubber-stamp.
