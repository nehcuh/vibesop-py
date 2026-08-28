# Hermetic Routing Benchmark (gate45 P1)

> **Status**: CI hard gate — job `Routing Benchmark (gate)` in `.github/workflows/ci.yml`
> **Contrast**: `Routing Eval (report-only)` (gate38) stays permanently report-only: its
> numbers depend on the machine (locally installed packs, local skill index), so they are
> for humans, never for gating. This benchmark is its hermetic sibling: same entry
> semantics, pinned universe, CI-gateable.

## What it gates

Routing **quality** regressions: router / matcher / threshold / policy changes must not
silently flip dataset entries from pass to fail. Entries are per-query top-1 assertions
(`expect` / `reject` / no-match — see `scripts/eval_routing.py` docstring), so a gate
failure names the exact queries that regressed.

## The hermetic posture

`scripts/eval_routing.py --hermetic` constructs the router so that every
machine-dependent input is neutralized. Order matters; all six steps run before any
query is routed:

1. **cwd → tmp** (`os.chdir`): InstinctLearner and other `.vibe/*` stores resolve
   against the process cwd; the repo root carries a real `.vibe/` that must not leak.
2. **`HOME`/`USERPROFILE` → tmp**: two home-dependent readers would otherwise diverge
   between dev machines and CI — the INDEX layer merges the *global* skill index at
   `Path.home()/.vibe/skill-index.json` (locally built, absent on CI), and config /
   external discovery consults `~`. Both `Path.home()` and `expanduser()` read the env
   at call time, so setting the env var covers both mechanisms. *(Empirically necessary:
   a real HOME changed 6/34 primaries via stale global-index profiles.)*
3. **`load_sentence_transformer` → null**: machines with a warm HF cache would activate
   the semantic_index embedding fallback that CI (no cache) can never take; null forces
   the deterministic TFIDF path.
4. **`RoutingConfig(enable_embedding=False, enable_ai_triage=False)`**: layer toggles
   explicit; CLI-override semantics mean unset fields could otherwise leak from
   `~/.vibe/config`.
5. **SCENARIO layer pinned empty** (`router._scenario_cache = {}`): in an editable
   install it reads empty by accident (the bundled registry only exists in wheels), but
   a wheel-installed env would activate it and silently regenerate the baseline into a
   different universe — pinning makes the posture install-mode-independent. The INDEX
   layer is empty for the same reason (no project index in tmp, global index isolated
   by the tmp HOME).
6. **`CandidateManager.pin_search_paths([builtin_dir, tests/fixtures/benchmark-pack])`**:
   the candidate universe is exactly the checkout builtins plus the checked-in fixture
   pack — no user/project/external discovery, no `candidates_v2.json` disk cache
   (pinned pools are never served from or persisted into a stale cache). The pin is
   irreversible for the instance — benchmark-only seam, never call from long-lived
   processes.

### What is deliberately NOT gated

- **The semantic layers** (embedding, semantic_index embedding fallback, AI triage) and
  **the SCENARIO and INDEX layers** (structurally empty in this posture — see steps 2/5).
  The gate covers keyword / Levenshtein / explicit / TFIDF / fallback routing. Semantic
  quality changes are **not visible anywhere in CI**: the report-only CI job runs the
  same offline posture (no `~/.vibe/config`, no HF cache). Their real surfaces are a
  local embedding-enabled report-only run and the manual docker `e2e_llm_routing`.
- `core/registry.yaml` is fingerprinted although the hermetic router does not consume
  it (its scenario keys are inert here) — a registry-only change triggers one
  semantically empty refresh. Conservative over-approximation, accepted.
- If a future change makes a keyword/TFIDF entry newly pass, the gate exits 0 with a
  "refresh recommended" note — regenerate the baseline to lock the win.

## Baseline

`tests/benchmark/routing_baseline.json` (checked in): per-entry
`{query, expect, reject, primary, layer, ok1}` plus a content fingerprint —
sha256 over `core/registry.yaml`, every `*.md`/`*.yaml`/`*.yml` under the pinned skill
roots, the dataset file, and the canonical posture. **Content-only**: mtimes and
absolute paths are not hashed, so `touch` and a checkout at a different location
(CI vs local) fingerprint identically.

`tests/fixtures/benchmark-pack/` exercises pack-shaped skills *inside* the pinned
universe (distinctive tokens → deterministic keyword routing), so the external-path
code runs in-universe without environment dependence. Entries expecting locally
installed packs (`kimi-gated-fix`, `prompt-chain-validator`) are annotated
`requires_packs: [external]` and become `skipped_env` under the pinned universe.

### Refresh flow

```bash
uv run python scripts/eval_routing.py --hermetic --update-baseline   # write + print fingerprint
uv run python scripts/eval_routing.py --hermetic --check             # must exit 0
```

Refresh whenever the gate exits **3** (stale — registry/skill/dataset content or posture
changed). A deliberate dataset/skill change is a refresh; a suspicious one is a review
flag. Exit **1** (new top-1 fail) is never fixed by refreshing — fix the regression.

**Absorption guard**: `--update-baseline` first compares the incoming entries against
the old baseline and **refuses to write** (exit 1) when the refresh would fold in any
`ok1: true→false` flip — the difference between "the universe changed" and "the router
regressed" is enforced by the tool, not by review discipline. To knowingly absorb such
flips, re-run with `--force` and justify every flip in the PR. Refresh on Linux/macOS;
Windows regeneration has not been A/B-verified (the gate itself runs ubuntu-only).

## Exit codes (`--hermetic --check`)

| code | meaning |
|---|---|
| 0 | no new top-1 fails (primary/layer drift on passing entries warns only) |
| 1 | new top-1 fail(s): entry passed in baseline, fails now — regression |
| 3 | stale baseline: missing/unreadable/schema mismatch, or fingerprint changed |

## Determinism proof (2026-08-28, local)

All [executed] on macOS against `main`:

- `--update-baseline` double run → baseline file **byte-identical**; `--check` exits 0.
- `touch core/registry.yaml` → still exit 0 (mtime-insensitive); content edit to a
  fixture `SKILL.md` → exit 3; revert → exit 0.
- Tampering the baseline (known-fail → `ok1: true`) → exit 1 with
  query/expect/baseline-vs-current detail.
- Env A/B with per-query JSON records (`--json-out`, byte-compared):
  `HOME=fake`, `HF_HOME=fake`, cwd=`/tmp` → **all identical** to the reference run.

## Posture invariants (future changes, re-verify)

- Any layer that introduces recency/mtime boosts or per-machine caches re-opens
  CI-vs-local drift — the env A/B above is the acceptance test.
- Every `load_sentence_transformer` call site must keep its **function-body import**
  (`from vibesop.core.embedding_loader import ...` inside the caller): the hermetic
  patch replaces the module attribute, and a call site hoisted to module scope would
  silently keep the real loader — local-green/CI-red ghost flakes.
- New fingerprint inputs (e.g. matcher config files) must go into
  `compute_fingerprint`, never mtime-based. Symlinked skill files are invisible to the
  fingerprint (by design — pinned roots must be plain checkouts); if symlinked skills
  ever become a supported layout, revisit `_hash_tree`.
- Pure compare/fingerprint logic lives in `src/vibesop/core/routing/benchmark.py`
  (unit-tested in `tests/test_routing_baseline.py`) — keep the script a thin shell.
- The harness assumes a single-shot process (it chdirs and rewrites `HOME`); never
  reuse its construction inside pytest fixtures or long-lived processes.
