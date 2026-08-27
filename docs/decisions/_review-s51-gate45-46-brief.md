# Review Brief — S51 pull `e286e67..f6a90fd` (gate45 + gate46)

> Date: 2026-08-27
> Window: `e286e67` → `f6a90fd` (22 commits, 63 files, +3237/−1736)
> Local HEAD after `git pull --ff-only origin main`: `f6a90fd`
> Mode: three independent adversarial lanes. Do not share findings across lanes.

## One-line claim (author)

Wheel-install builtins no longer empty-route; runtime scan false positives
fixed; confirmation default is `ambiguous_only`; Claude/Grok hook rewrite is
conservative; quickstart now has a keyless dual-platform aha (4 demo skills +
inject preview + parameterized `--hook --platform`); CI + Quickstart E2E green.

## Do not re-open (unless this window made them worse)

Documented 8.1.2 leftovers from S49 (`CHANGELOG.md` Known issue):

- C1: whitelist canary test still missing
- C2: preserve-matcher is still substring-based (rebuild drops user entries
  whose command contains a vibesop substring)

S50 already recorded and (claims) closed: fake dual-platform probe, R7 dual
state, double banner, 14→18 leftover, `write tests` keyword steal.

## Highest-risk files (src)

- `src/vibesop/security/runtime_scan.py`, `src/vibesop/security/scanner.py`
- `src/vibesop/utils/hook_commands.py` (new single source of truth)
- `src/vibesop/cli/commands/verify.py`
- `src/vibesop/agent/runtime/skill_injector.py`, `agent_runtime.py`, `plan_executor.py`
- `src/vibesop/utils/bundled.py` (new)
- `src/vibesop/core/config/manager.py`, `core/routing/candidate_manager.py`, `project_config.py`
- `src/vibesop/installer/quickstart_runner.py`, `cli/commands/quickstart.py`, `cli/main.py`
- `src/vibesop/adapters/grok_build.py`, `adapters/claude_code.py`, `adapters/_content.py`
- `pyproject.toml` hatch force-include; `MANIFEST.in` deleted
- `core/registry.yaml` + 4 new `core/skills/{code-review,commit-message,systematic-debugging,test-generation}/SKILL.md`

## Product claims to falsify

From `CHANGELOG.md` Unreleased:

1. Removing `\n{5,}` heuristic + empty-vs-unsafe split does not let real
   injection through as a data problem.
2. `confirmation_mode` default `always` → `ambiguous_only` does not drop
   learning signal or silently auto-route the wrong skill.
3. Hook rewrite only touches strict `<bash> <script>` + legacy signal.
4. `vibe verify` only scans vibesop hook commands; user PowerShell is not
   flagged; Windows-form vibesop commands on non-win32 still surface.
5. Wheel install (pipx/uv-tool) can route the 4 demo builtins (not empty).
6. Injector builtin ladder: project_root → wheel bundle → repo derive → sys.path.
7. `vibe route --hook --platform` is actually parameterized (not grok-only).
8. Demo `triggers` stay in explicit layer; `tags` do not steal keyword routing
   (`write tests`, `review my changes`, etc.).
9. Grok `routing.md` builtin count is computed, not a stale 50+/14.

## Lane assignments

Each lane writes ONLY its own file. Read the diff yourself via:

```
git diff e286e67..HEAD -- src tests core pyproject.toml .github/workflows
```

Also `git log --oneline e286e67..HEAD` and `CHANGELOG.md` Unreleased.

Do not edit production source. Do not commit. Do not "fix" anything.

Severity: **BLOCKER** (merge/ship stop) / **MAJOR** (must-fix before 8.1.2) /
**MINOR** (nit). Cite `file:line`. Distinguish fact vs suggestion.

End with: verdict `PASS` | `PASS-WITH-NITS` | `NEEDS_FIX` | `BLOCK`, plus
counts.

### Lane A — correctness / security

Write: `docs/decisions/_review-s51-lane-correctness.md`

Attack: logic bugs, injection, path traversal, secrets, race, None paths,
tests that assert the wrong contract, scanner looseness, hook rewrite false
negatives, verify false negatives, packaging omissions.

Verdict also states: P0 count / P1 count.

### Lane B — architecture / devil's advocate

Write: `docs/decisions/_review-s51-lane-architecture.md`

Attack: hidden coupling, dual-mode drift (`hook_commands` lenient vs strict),
injector priority inversion, bundled vs checkout precedence under uv-tool +
cwd-in-clone, confirmation skip vs telemetry, demo skills as product core vs
opt-in, hatch force-include vs deleted MANIFEST.in, strongest argument
against shipping 8.1.2 from this window.

Architectural Status: `CLEAR` | `WATCH` | `BLOCK`.

### Lane C — platform / Windows / routing invariants

Write: `docs/decisions/_review-s51-lane-invariants.md`

Attack this repo's known failure class: platform-registry drift, `_is_configured`
false positives, Windows PATH / Git-Bash / Store python3, grok hook envelope
shape, EXTERNAL_PATHS ClassVar frozen at import, 14 vs 18 builtin count,
Quickstart E2E "dual platform" actually dual, demo tag/trigger keyword steal,
`route --hook` fail-open, wheel builtin empty-route.

## Synthesis rule (orchestrator only, after all three return)

- Any BLOCKER or Architectural BLOCK → REQUEST CHANGES
- Else any MAJOR → REQUEST CHANGES
- Else WATCH or MINOR-only → COMMENT
- APPROVE only if all three lanes returned evidence AND no BLOCKER/MAJOR
  AND architect status is CLEAR
- Missing lane = independent review unavailable, not approval
