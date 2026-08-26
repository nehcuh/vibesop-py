# Platform registry and install-status invariants

> **Version**: 8.1.1
> **Updated**: 2026-08-26

These rules exist because the 8.1.0 release shipped with Docker e2e green while
`vibe quickstart` on Windows could not list Grok Build, dumped YAML
tracebacks, reported "No hooks available" after a successful install,
and Grok JSON hooks could not find `vibe` on PATH.

## What went wrong

1. **Docker e2e is Linux + `vibe` on PATH + empty home.** It cannot see
   Windows user PATH, Git-Bash vs JSON hooks, or a stock
   `~/.kimi-code/config.toml` that already exists.
2. **Platform identity was copied into 6+ registries** that drifted.
   Tests asserted `len(platforms) >= 2`, so dropping grok-build could
   not fail CI.
3. **`_is_configured` meant "any of these filenames exist."** Host-native
   `config.toml` (Kimi, Grok) and `settings.json` (Pi) counted as a
   VibeSOP install, so `install()` skipped hook deploy.
4. **A PATH fix in bash hooks was not promoted to an invariant.**
   `.sh.j2` prepends `$HOME/.local/bin`. Grok JSON, Pi `execSync`, and
   the OpenCode plugin call bare `vibe` and inherited none of that.

## Invariants (test these; do not re-derive)

1. **Single platform set.** These must agree, or the delta must be
   explicit and tested:
   - `vibesop.constants.SUPPORTED_PLATFORMS`
   - `VibeSOPInstaller._platforms`
   - `ConfigRenderer._adapters`
   - `verify.PLATFORM_CONFIGS`
   - `QuickstartRunner._supported_platforms` (derived from installer)
   Never assert `len(...) >= 2` for platform lists. Use set equality or
   `>= SUPPORTED_PLATFORMS` with a named exemption.

2. **Installed means a VibeSOP marker, not the host's own config.**
   `_is_configured(dir, platform)` must look for `vibesop-route.*` (or
   grok `rules/routing.md`). A stock Kimi `config.toml` or Pi
   `settings.json` is **not** configured.

3. **Hooks that spawn `vibe` must find it.** JSON / Node / TS hooks do
   not get the bash PATH prefix. Windows: `uv tool` puts `vibe.exe` in
   `%USERPROFILE%\.local\bin` — that directory must be on the **user**
   PATH, and Grok/Pi must be restarted after PATH changes. Verify with
   `vibe verify grok-build` (`vibe_on_path` check) and a real stdin hook
   subprocess, not file-existence alone.

4. **`vibe verify` check_ids must have handlers.** Declaring
   `agents_md` / `extensions_dir` in `PLATFORM_CONFIGS` without a
   matching `check_id` branch in `_check_platform` is a silent all-FAIL.

## Host smoke (not optional for adapter changes)

After changing any adapter or installer:

```bash
uv tool install --reinstall --force --no-cache .
vibe build <platform> --output <that platform's real config dir>
vibe verify <platform> -v
# For hooks that exec vibe: feed a UserPromptSubmit JSON on stdin.
```

Docker e2e remains required. It does **not** replace this smoke.

## Related

- `memory/project-knowledge.md` — Platform Registry Drift (2026-08-26)
- `docs/user/troubleshooting.md` — `vibe` not on PATH / false "installed"
- `tests/cli/test_platform_registry_sync.py` — set-membership guards
