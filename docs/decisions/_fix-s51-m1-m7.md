# Fix Plan — S51 M1–M7 (v1)

> Spec: `docs/decisions/_review-s51-gate45-46-merged.md`
> Window: `e286e67..f6a90fd` (HEAD `f6a90fd`)
> Process: Plan → dual-lane adversarial confirm → TDD execute → verify
> Scope: MAJORs only. MINOR n1–n11 and 8.1.2 C1/C2 stay deferred.

## Locked decisions (do not re-open in implementation)

| ID | Choice | Why |
|----|--------|-----|
| M1 | Allow **space only** in an already-quoted absolute script token. Keep rejecting `` `$%^ `` and unquoted spaces. | Unwrap already grouped `"C:/Users/First Last/..."`. Allowlist is the only reject. Unquoted space would re-open injection. |
| M2a | Add `confidence: float = 0.0` to `ExecutionStep`; PlanBuilder writes the value it already computes; include in `to_dict`/`from_dict`. | `_needs_confirmation` getattr default 0 is why the skip path is test-only. |
| M2b | Auto-proceed **omits** `_record_plan_sequence`. Do **not** write `success=False`. | Promoter needs `success_rate >= 0.8`. False records are anti-signal. Privacy: `success=True` still only from explicit confirm. |
| M2c | CHANGELOG: retract "instinct loop un-starved". Document aha/`--hook` as **out of** plan-sequence learning. | Honest. No third-class schema this patch. |
| M3 | One `resolve_builtin_skills_dir(project_root) -> Path`. Identity = `pyproject.toml` contains `name = "vibesop"` **and** `core/skills/` exists. Order: identified checkout → wheel `builtin_skills` → `__file__`-derived identified checkout. **Drop sys.path scan.** | cmspark inversion class. Any `cwd/core/skills` must not shadow the wheel. |
| M4 | Keep four demos always-on (aha depends on them). Strip steal phrases. Pin pack-owner at **any layer**. SKILLS_GUIDE: demos are P1 aha, not "必须启用 P0". | Option 2 from merged review. `--demos` default-off would kill gate46. |
| M5 | `--platform` default `None`. Resolve: **explicit flag > JSON platform > grok-build**. Probe: Grok camelCase envelope **without** `platform`, Claude via `--platform claude-code`. Deployed Grok JSON command becomes `vibe route --hook --platform grok-build`. | "flag wins" must be true. Default sentinel is the bug. |
| M6 | Align `UV_VERSION` with CI `0.11.19`. After quickstart: `vibe verify` both platforms. Claude: `bash -c` the `settings.json` command from `runner.temp`. Grok: camelCase probe, no `platform` field. Do **not** claim stock Windows user PATH is simulated. | GH Actions cannot fake a stock user PATH; exercise the real hook command shapes. |
| M7 | **Implement** the six pi handlers (do not delete ids). Completeness test: every `PLATFORM_CONFIGS[*].checks` id produces non-empty `detail`. | Silent all-FAIL is worse than a missing-file FAIL. |

Out of scope: C1/C2, n1–n11, Grok JSON PATH prefix (n10 — document only in CHANGELOG known issue).

## Files

- Modify: `src/vibesop/utils/hook_commands.py`, `src/vibesop/utils/bundled.py`
- Modify: `src/vibesop/core/models.py`, `src/vibesop/core/orchestration/plan_builder.py`
- Modify: `src/vibesop/cli/main.py`, `src/vibesop/cli/commands/verify.py`
- Modify: `src/vibesop/agent/runtime/skill_injector.py`
- Modify: `src/vibesop/core/skills/loader.py`, `src/vibesop/core/routing/candidate_manager.py`
- Modify: `src/vibesop/adapters/_content.py`, `src/vibesop/adapters/grok_build.py`
- Modify: `core/skills/code-review/SKILL.md`, `core/skills/test-generation/SKILL.md`
- Modify: `scripts/demo/probe-inject.sh`, `.github/workflows/quickstart-e2e.yml`
- Modify: `CHANGELOG.md`, `docs/SKILLS_GUIDE.md`
- Test: `tests/adapters/test_claude_code.py`, `tests/cli/test_plan_sequence_recording.py`, `tests/cli/test_route_commands.py`, `tests/cli/test_verify_hook_commands.py` (or new `test_verify_check_coverage.py`), `tests/utils/test_bundled.py`, `tests/agent/runtime/test_skill_injector.py`, `tests/core/routing/test_demo_skills.py`

---

### M1 — quoted space in rewrite parser

**Red test** (`tests/adapters/test_claude_code.py`):

```python
def test_rewrites_git_bash_wrapper_spaced_home(self, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    entry = self._entry(
        '"C:/Program Files/Git/bin/bash.exe" '
        '"C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"'
    )
    rewritten = _rewrite_legacy_hook_entry(entry)
    assert rewritten["hooks"][0]["command"] == (
        '"C:/Users/First Last/.claude/hooks/vibesop-mirror-prompt.sh"'
    )

def test_parse_rejects_unquoted_space_and_backtick(self, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert parse_hook_script_command(
        'bash C:/Users/First Last/.claude/hooks/vibesop-route.sh'
    ) is None
    assert parse_hook_script_command(
        'bash "C:/Users/h/.claude/hooks/`id`/vibesop-route.sh"'
    ) is None
```

**Green:** In `parse_hook_script_command`, keep original tokens. After unwrap, if the script token was double-quoted, union `_PATH_ALLOWED` with `{" "}`. Interpreter path is already not allowlisted (Program Files already works).

---

### M2 — ExecutionStep.confidence + honest skip

**Red tests:**

1. Replace `test_ambiguous_only_auto_proceed_records_application_only` with two tests using real `ExecutionStep` (not SimpleNamespace):

```python
from vibesop.core.models import ExecutionStep, StepStatus

def _real_plan(confidences: list[float]):
    steps = [
        ExecutionStep(
            step_id=str(i), step_number=i + 1, skill_id=s,
            confidence=c, status=StepStatus.PENDING,
        )
        for i, (s, c) in enumerate(zip(("a", "b", "c"), confidences, strict=True))
    ]
    return SimpleNamespace(steps=steps)

# (a) all 0.9 + ambiguous_only + TTY → no prompt, stored sequences == []
# (b) one step 0.2 → prompt still fires (select mock called)
```

2. PlanBuilder unit: constructed steps have `confidence` equal to the builder's local variable (existing plan-builder test file if present; else `tests/core/orchestration/`).

**Green:**

- `ExecutionStep.confidence: float = Field(default=0.0, ge=0.0, le=1.0)`
- `to_dict`/`from_dict` include it (`data.get("confidence", 0.0)`)
- `PlanBuilder` `ExecutionStep(..., confidence=confidence)`
- `_orchestration_confirmation_flow`: when skip because not `_needs_confirmation` and not unattended: **do not** call `_record_plan_sequence`
- CHANGELOG Unreleased: replace "instinct loop does not starve" with "auto-proceed does not write sequence telemetry; only explicit confirm writes success=True; aha/`--hook` are out of this loop"

---

### M3 — single builtin skills dir

**API** in `src/vibesop/utils/bundled.py`:

```python
def is_vibesop_checkout(root: Path) -> bool:
    """True iff root is a VibeSOP source tree (not an arbitrary core/skills)."""

def resolve_builtin_skills_dir(project_root: Path | None = None) -> Path:
    """Identified checkout → wheel builtin_skills → __file__ checkout."""
```

Identity: `(root / "core" / "skills").is_dir()` and `name = "vibesop"` appears in `root / "pyproject.toml"`.

**Callers (only these):**

- `SkillLoader._default_search_paths`: drop always-on `project_root/core/skills` and raw `pkg_builtins`. Insert `resolve_builtin_skills_dir(self.project_root)` once.
- `CandidateManager._build_search_paths`: insert that one path; delete the `(pkg, repo) insert(0)` loop and the "exactly one exists" comment.
- `SkillInjector._load_skill_content` builtin strip: `strip_bases = [resolve_builtin_skills_dir(self.project_root)]`. Delete sys.path scan and ad-hoc repo derivation.
- `GrokBuildAdapter._count_builtin_skills`: count dirs in `resolve_builtin_skills_dir()`.
- `find_skill_content`: first look `resolve_builtin_skills_dir(project_root) / name_only / "SKILL.md"`. Keep pack/project `skills/` lookups. Drop `Path(__file__).parent.parent / "core" / "skills"` (that path is `src/vibesop/core/skills`, not repo core).

**Red tests** (`tests/utils/test_bundled.py` + injector):

```python
def test_foreign_core_skills_does_not_shadow_wheel(tmp_path):
    (tmp_path / "core" / "skills" / "code-review").mkdir(parents=True)
    (tmp_path / "core" / "skills" / "code-review" / "SKILL.md").write_text("# FOREIGN\n")
    # no pyproject name=vibesop
    resolved = resolve_builtin_skills_dir(tmp_path)
    assert resolved == bundled_path("builtin_skills") or not (tmp_path / "core" / "skills") == resolved

def test_identified_checkout_wins(tmp_path):
    (tmp_path / "core" / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "vibesop"\n')
    assert resolve_builtin_skills_dir(tmp_path) == tmp_path / "core" / "skills"
```

Rewrite `test_load_skill_builtin_dev_repo_preferred_over_bundle` to require the pyproject identity marker; add a sibling test that foreign `project_root/core/skills` yields bundled content.

`test_load_skill_builtin_via_sys.path_scan`: keep the `__file__` fake site-packages setup; it still hits wheel via `bundled_path`. Rename to `test_load_skill_builtin_from_wheel_bundle`.

---

### M4 — demo keyword steal

**Frontmatter:**

- `core/skills/code-review/SKILL.md`: remove tag `"review my changes"` (keep `"look over my changes"` on triggers).
- `core/skills/test-generation/SKILL.md`: remove trigger `"write tests"` (keep `"write unit tests"`, `"write unit tests for this module"`).

**Fixture** in `test_demo_skills.py`: add `("superpowers", "review")` with tags including `"review my changes"`.

**PACK_OWNED_QUERIES:**

```python
PACK_OWNED_QUERIES = [
    ("write tests", "superpowers/test-driven-development"),
    ("review my changes", "superpowers/review"),
]
```

**Pin:** `assert not str(got).startswith("builtin/")` (any layer). Verified demo queries (`look over my changes before I push`, `write unit tests for this module`) must still hit builtins (existing tests).

**SKILLS_GUIDE:** Builtin blurb: core slash/session-end remain P0; the four aha demos are P1 keyless examples, not "必须启用".

If after tag/trigger strip `write tests` still hits `builtin/commit-message` via levenshtein, **do not weaken the test**. Next-step (same task): levenshtein must not select `builtin/commit-message` for that query when the TDD pack is in the pool — prefer raising last-resort threshold for builtin demos or excluding demo ids from levenshtein. Implement the smallest change that makes the pin hold without breaking `VERIFIED_DEMO_QUERIES`.

---

### M5 — `--platform` None + probe shapes

**CLI** (`cli/main.py` `route`):

```python
hook_platform: str | None = typer.Option(None, "--platform", help="... Flag wins over JSON platform when passed.")
# resolve:
platform = hook_platform or (
    payload.get("platform").strip()
    if isinstance(payload, dict) and isinstance(payload.get("platform"), str)
    else None
) or "grok-build"
```

**Grok JSON** (`grok_build.py` `_render_hook_json`): `"command": "vibe route --hook --platform grok-build"`.

**probe-inject.sh:**

- Stop stuffing `platform` into JSON.
- Claude lane: `$VIBE_BIN route --hook --platform claude-code` with `{"userPrompt":..., "sessionId":"probe-claude"}`.
- Grok lane: `$VIBE_BIN route --hook` with `{"userPrompt":..., "sessionId":"probe-grok"}` (no platform key).
- Drop `2>/dev/null` (n3 adjacent, required for M5/M6 debuggability). Escape JSON via `python -c` json.dumps if `$QUERY` can contain quotes.

**Red tests** (`test_route_commands.py`):

```python
def test_explicit_platform_flag_beats_json_platform(self):
    payload = {"userPrompt": "x", "platform": "claude-code"}
    runner.invoke(app, ["route", "--hook", "--platform", "grok-build"], input=json.dumps(payload))
    assert self.captured["platform"] == "grok-build"

def test_omitted_flag_reads_json_platform(self):
    payload = {"userPrompt": "x", "platform": "claude-code"}
    runner.invoke(app, ["route", "--hook"], input=json.dumps(payload))
    assert self.captured["platform"] == "claude-code"

def test_camelcase_userPrompt_without_platform_defaults_grok(self):
    payload = {"userPrompt": "x", "sessionId": "s"}
    runner.invoke(app, ["route", "--hook"], input=json.dumps(payload))
    assert self.captured["query"] == "x"
    assert self.captured["platform"] == "grok-build"
```

Fix today's `test_hook_mode_camelcase_grok_payload` which still uses `prompt` not `userPrompt` as the grok pin.

---

### M6 — Quickstart E2E host-shaped

`.github/workflows/quickstart-e2e.yml`:

- `UV_VERSION: "0.11.19"`
- After hook-registration grep, add:
  - `vibe verify claude-code -v` and `vibe verify grok-build -v` under scratch HOME (must exit 0).
  - Claude host smoke: parse `~/.claude/settings.json` first vibesop-route command; `bash -c "$cmd"` from `runner.temp` with a `userPrompt` stdin JSON (or whatever the script expects). Script `vibesop-route.sh` reads stdin as the hook event.
  - Replace current probe invocation: keep `working-directory: runner.temp`; Grok envelope without platform (script change covers this).
- Assert grok JSON contains `--platform grok-build` (not only `vibe route --hook` substring).

Windows runner stays `shell: bash` (GH Actions constraint). Comment in the workflow: this is Git-Bash-on-windows-runner, not stock user PATH.

---

### M7 — pi verify handlers

In `_check_platform`, after existing branches:

```python
elif check_id == "agents_md":
    path = project_root / "AGENTS.md"
elif check_id == "extensions_dir":
    path = config_dir / "extensions"
elif check_id == "skills_dir":
    path = config_dir / "skills"
elif check_id == "route_extension":
    path = config_dir / "extensions" / "vibesop-route.ts"
elif check_id == "track_extension":
    path = config_dir / "extensions" / "vibesop-track.ts"
elif check_id == "prompts_dir":
    path = config_dir / "prompts"
```

Each: `exists()` / `is_dir()` as appropriate; detail `Found (...)` or `Missing: {path}`.

**Red test** `tests/cli/test_verify_check_coverage.py`:

```python
def test_every_check_id_has_handler(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from vibesop.cli.commands.verify import PLATFORM_CONFIGS, _check_platform
    for platform, cfg in PLATFORM_CONFIGS.items():
        results = _check_platform(platform)
        assert {r["id"] for r in results} == set(cfg["checks"])
        for r in results:
            assert r["detail"], f"{platform}/{r['id']} unhandled (empty detail)"
```

Today this fails on pi (empty detail). After fix, missing files have `Missing: ...`.

Also: `test_pi_checks_pass_on_rendered_layout(tmp_path)` — mkdir `.pi/extensions`, write dummy ts files, `AGENTS.md`, `.pi/skills`, `.pi/prompts`; assert those six ids pass.

---

## Verification (after all tasks)

```
uv run pytest tests/adapters/test_claude_code.py tests/cli/test_plan_sequence_recording.py tests/cli/test_route_commands.py tests/cli/test_verify_hook_commands.py tests/cli/test_verify_check_coverage.py tests/utils/test_bundled.py tests/agent/runtime/test_skill_injector.py tests/core/routing/test_demo_skills.py tests/core/test_config_manager.py -q
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Then a broader affected slice if green.

## Explicitly not in this plan

- n1 empty-content substring gate
- n10 Grok JSON PATH prefix (CHANGELOG known issue, same class as S45 PATH)
- C1 whitelist canary / C2 substring preserve-matcher
- `--demos` opt-out flag
