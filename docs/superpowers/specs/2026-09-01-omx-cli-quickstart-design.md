# OMX CLI companion on pack install + quickstart

> Date: 2026-09-01
> Status: draft (awaiting user review)
> Scope: `vibe install omx` and `vibe quickstart` install `oh-my-codex` CLI best-effort
> Non-goals: `omx setup`, `vibe doctor` OMX check, default third-party packs, allowScripts

## Problem

VibeSOP's omx pack is a Git clone of skill markdown (`~/.config/skills/omx`). OMX skill bodies (`/omx-autopilot`, `$omx-setup`, …) invoke the **npm CLI** (`omx state`, `omx doctor`). `vibe install omx` never puts `omx` on PATH, so agents report "no omx command" even though `/omx-*` slash skills exist.

Quickstart currently does not install third-party packs by default (adoption block 2: keyless builtin aha). The old "Install skill pack integrations?" prompt is dead: `_ask_install_type` always sets `install_integrations=False`, never `None`.

## Decisions (locked)

1. Attach CLI install to **both** `vibe install omx` and an **opt-in** quickstart question.
2. Quickstart Yes = **omx skill pack + CLI** (not CLI-only).
3. Missing Node/npm or npm failure: **skill pack still succeeds**, yellow warning, **exit 0**.
4. Do **not** run `omx setup` (mutates `AGENTS.md` / `~/.codex`).
5. `vibe quickstart --force`: do **not** ask, do **not** install omx.
6. `vibe doctor` OMX PATH check is **out of this slice**.
7. Do **not** revive the bundled integrations prompt (that would also pull superpowers/mattpocock).
8. npm package: `oh-my-codex@latest`. Do not pin CLI to the Git pack version (currently 0.18.11 vs npm 0.21.2).
9. If `omx` is already on PATH, skip `npm install` (ensure presence, do not surprise-upgrade).
10. Do not enable npm `allowScripts` / postinstall.

## Behavior contract

| Entry | Behavior |
|---|---|
| `vibe install omx` (fresh) | Clone/audit pack as today, then `ensure_omx_cli()`. Pack failure → CLI is not attempted. |
| `vibe install omx` (already installed) | CLI `_install_pack` currently returns `"skipped"` **before** `PackInstaller`. Must still call `ensure_omx_cli()` on that skip path. |
| `vibe install --auto` | omx is in `DEFAULT_AUTO_INSTALL_PACKS`. Fresh install goes through `install_pack`; already-installed skip must also ensure CLI. |
| `vibe install <other pack>` | No CLI step. |
| `vibe install <git-url>` that is not the trusted omx URL | No CLI step. Trusted omx name or `TRUSTED_PACKS["omx"]` URL only. |
| `vibe quickstart` interactive | After hooks question, ask `Install OMX (oh-my-codex skills + CLI)? [y/N]`. Default **No**. Yes → `PackInstaller.install_pack("omx")` (which ensures CLI). No → neither pack nor CLI. |
| `vibe quickstart --force` | `install_omx=False`. CI/no-TTY stays Node-free. |
| No `npm` on PATH | Pack success. Warn: `omx CLI skipped (npm not found). Install Node, then: npm install -g oh-my-codex` |
| `npm install -g` fails / timeout | Pack success. Warn with returncode/stderr tail + the same manual command. |
| `npm` succeeds but `omx` still not on PATH | Warn with global bin hint (`npm prefix -g` + `/bin`). Still exit 0. |
| `omx` already on PATH | Skip npm. Print that CLI is already present. |

`ensure_omx_cli()` is **never** a reason to return `success=False` from pack install or quickstart.

## Architecture

One helper, two call sites. No new CLI command.

```text
ensure_omx_cli()          # installer/omx_cli.py
        ▲
        ├── PackInstaller.install_pack success when pack is omx
        │     (fresh install AND already_installed early-return)
        └── cli/commands/install.py _install_pack
              skip-already-installed branch when pack_name == "omx"
```

Quickstart does **not** call `ensure_omx_cli` directly. Yes → `install_pack("omx")` → helper. Avoids double-wiring.

### Why two call sites

`_install_pack` returns `"skipped"` when the global pack is already installed, **without** entering `PackInstaller.install_pack`. That is the path this machine already hit (`vibe install omx` after skills exist). Helper must run there too.

`PackInstaller.install_pack` is also called from quickstart, slash-install, and market — those never hit the CLI skip branch.

### Idempotency

Second call: `shutil.which("omx")` hits, returns `present` immediately. Safe if both call sites fire.

## Components

### 1. `src/vibesop/installer/omx_cli.py`

Public:

```python
@dataclass(frozen=True)
class OmxCliResult:
    status: Literal["present", "installed", "skipped_no_npm", "failed"]
    detail: str  # user-facing one-liner
    omx_path: str | None = None

def ensure_omx_cli(*, timeout_s: float = 180.0) -> OmxCliResult: ...
def is_omx_pack(pack_name: str, pack_url: str | None = None) -> bool: ...
```

`is_omx_pack`: `pack_name == "omx"` or `pack_url == TRUSTED_PACKS["omx"]`.

`ensure_omx_cli` steps:

1. `shutil.which("omx")` → `present`.
2. `shutil.which("npm")` (Windows PATHEXT resolves `npm.cmd`) → else `skipped_no_npm`.
3. `subprocess.run([npm, "install", "-g", "oh-my-codex"], timeout=timeout_s, capture_output=True, text=True, check=False)`.
4. Re-check `which("omx")`. Found → `installed`. Missing → `failed` with prefix-bin hint.
5. Any `TimeoutExpired`, `OSError`, non-zero npm → `failed`. Never raise to caller.

Do not pass `--allow-scripts`. Do not invoke `omx setup` / `omx doctor`.

### 2. `PackInstaller.install_pack`

After a **successful** omx install (both `already_installed` return and fresh `return True, msg`), append helper detail to `msg` (so CLI output already prints it). Do not change the bool.

Failed pack install: do not call helper.

Non-omx packs: no-op.

### 3. `cli/commands/install.py` `_install_pack`

On the `"skipped"` already-installed branch, if `is_omx_pack(pack_name, pack_url)`: call `ensure_omx_cli()` and print the one-liner (green for present/installed, yellow for skipped/failed). Still return `"skipped"` for the **pack** (don't pretend the pack was reinstalled).

### 4. `QuickstartConfig` + `QuickstartRunner`

Add `install_omx: bool` (not `None`). Defaults:

- `_ask_install_type` global/project: `False`
- `--force`: `False`

Interactive, after the hooks question:

```text
Install OMX (oh-my-codex skills + CLI)? [y/N]
```

Yes sets `install_omx=True`. Summary grows an `OMX:` row.

`_execute_installation`: if `install_omx`, call existing `_install_integration("omx")` (which is `install_pack("omx")` + helper) and then the existing `_sync_platform_symlinks` (it already no-ops missing packs). Do not flip `install_integrations` (that would install superpowers/mattpocock).

If both `install_integrations` and `install_omx` are True, omx may be installed twice; second is already-installed + idempotent CLI ensure. Acceptable.

### 5. Docs

- `docs/OMX_GUIDE.md` 启用方法: `vibe install omx` also best-effort installs CLI; missing npm does not fail the pack; `omx setup` is Codex-only and not run.
- `knowledge/vibesop/vibesop-install-quickstart.md`: one sentence on the quickstart OMX prompt (default No).
- `CHANGELOG.md` Unreleased Added.

## Error handling

| Case | Pack / quickstart | User sees |
|---|---|---|
| No npm | success | yellow skip + manual command |
| npm non-zero | success | yellow fail + stderr tail (≤ 8 lines) + manual command |
| npm timeout (180s) | success | yellow timeout + manual command |
| omx binary still missing after npm 0 | success | yellow + `npm prefix -g` bin path |
| KeyboardInterrupt during npm | treat as failed CLI, pack already done; do not swallow if it happens before pack | |

No rollback of a successful Git pack if CLI fails.

## Testing

New `tests/installer/test_omx_cli.py` (all subprocess/which mocked; no network):

1. `omx` already on PATH → `present`, npm not called.
2. no npm → `skipped_no_npm`, npm not called.
3. npm returncode 0 and which finds omx after → `installed`.
4. npm returncode 1 → `failed`, no exception.
5. `TimeoutExpired` → `failed`.
6. `is_omx_pack("omx")` true; `is_omx_pack("superpowers")` false; trusted omx URL true.

`tests/installer/test_pack_installer.py` (or a focused sibling):

7. Successful omx `install_pack` calls `ensure_omx_cli` (patch).
8. Successful superpowers `install_pack` does not.

`tests/cli/test_install_command.py` or pack CLI tests:

9. Already-installed omx skip path still calls `ensure_omx_cli`.

`tests/installer/test_quickstart.py`:

10. Interactive Yes on OMX question → `install_omx True` and `install_pack("omx")` invoked.
11. Empty input → `install_omx False`, omx pack not installed.
12. `--force` / `run(..., force=True)` → no OMX prompt, no omx pack.

Do not add live `npm install -g` in CI.

## Out of scope

- `vibe doctor` / `vibe verify` OMX PATH check
- `omx setup`, Codex hooks, `~/.codex`
- Building CLI from `~/.config/skills/omx` source (unbuilt, no dist)
- Upgrading an existing `omx` binary
- Changing `DEFAULT_AUTO_INSTALL_PACKS`
- Reviving the dead integrations prompt
- Windows-specific npm.cmd branching beyond `shutil.which`

## Success criteria

- Fresh machine with Node: `vibe install omx` leaves `omx` on PATH (or warns if npm prefix bin is not on PATH).
- Fresh machine without Node: `vibe install omx` still installs skills, exit 0, warning names the npm command.
- Already-installed omx pack: `vibe install omx` still attempts CLI (fixes this session's gap).
- `vibe quickstart --force` and default interactive Enter: no omx pack, no npm.
- Interactive Yes: omx skills + CLI ensure.
- No `omx setup` subprocess anywhere in this slice.
