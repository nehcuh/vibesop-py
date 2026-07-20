# VibeSOP P1 Optimization Plan

> Generated: 2026-07-20
> Method: adversarial-optimization workflow
> Previous: P0 (6 fixes, commit `684646f`)

---

## Batch Summary

| Batch | Items | Priority | Risk | Estimated Effort |
|-------|-------|----------|------|------------------|
| P1-A | Architecture decoupling (3 items) | HIGH | Medium | 3 files |
| P1-B | Private attribute violations (2 items) | HIGH | Low | 2 files |
| P1-C | Security hardening (3 items) | HIGH | Medium | 3 files |
| P1-D | Correctness fixes (4 items) | MEDIUM | Low-Medium | 5 files |
| P1-E | Integration cleanup (3 items) | MEDIUM | Low | 4 files |

---

## P1-A: Architecture Decoupling

### P1-A1: Extract `RoutingPort` Protocol

**Current**: `orchestration_mixin.py:24-38` defines `_OrchestrationHost` Protocol that mirrors UnifiedRouter's private attributes (`_multi_intent_detector`, `_task_decomposer`, `_plan_builder`, `_triage_service`, `project_root`, `_llm`). `plan_builder.py:158` imports `UnifiedRouter` via `TYPE_CHECKING`.

**Problem**: routing ↔ orchestration bidirectional coupling via lazy imports and Protocol duck typing. Adding a new private attribute to UnifiedRouter silently breaks orchestration.

**Fix**: Extract `SkillCapabilityProvider` and `LLMProvider` protocols into `core/routing/_protocols.py`. Have `PlanBuilder` depend on these interfaces, not router internals.

**Affected files**: `routing/orchestration_mixin.py`, `orchestration/plan_builder.py`, `routing/_protocols.py`, `routing/unified.py`

**Risk**: Medium — changes import graph and dependency direction.

### P1-A2: Extract `CLI_PLATFORMS` Constant

**Current**: `VALID_TARGETS` list duplicated identically in `cli/commands/build.py:42`, `switch.py:35`, `deploy.py:13`. Contains `"superpowers"` which is a skill pack, not a platform.

**Fix**: Move to `vibesop.constants.SUPPORTED_PLATFORMS`. Remove `"superpowers"`. Replace all 3 references.

```diff
# vibesop/constants.py
+ SUPPORTED_PLATFORMS = ["claude-code", "kimi-cli", "opencode", "cursor", "pi", "grok-build"]

# cli/commands/build.py
- VALID_TARGETS = ["claude-code", "kimi-cli", "opencode", "superpowers", "cursor", "pi", "grok-build"]
+ from vibesop.constants import SUPPORTED_PLATFORMS as VALID_TARGETS
```

**Affected files**: `constants.py`, `build.py`, `switch.py`, `deploy.py`

**Risk**: Low — pure refactor, no logic change.

### P1-A3: Extract `_get_configured_platform()` to Shared Utility

**Current**: `_get_configured_platform()` duplicated identically in `build.py:175-196` and `switch.py:38-62`.

**Fix**: Extract to `cli/commands/_utils.py` or `core/config/platform.py`.

**Affected files**: `build.py`, `switch.py`, new shared module

**Risk**: Low — extract-and-delegate.

---

## P1-B: Private Attribute Violations

### P1-B1: Add `set_llm_factory()` to UnifiedRouter

**Current**: `agent/__init__.py:86-88` directly mutates `self._router._llm_factory` and `self._router._triage_service._llm_factory`.

**Fix**: Add public method to `UnifiedRouter`:

```python
# routing/unified.py
def set_llm_factory(self, factory: Any) -> None:
    self._llm_factory = factory
    if self._triage_service:
        self._triage_service._llm_factory = factory
```

**Affected files**: `routing/unified.py`, `agent/__init__.py`

**Risk**: Low — encapsulate existing behavior.

### P1-B2: Add `get_skill_loader()` to UnifiedRouter

**Current**: `plan_builder.py:158,700` accesses `self._router._skill_loader` and `self._router._candidate_manager._skill_loader` via `getattr`.

**Fix**: Add public accessor to `UnifiedRouter`:

```python
# routing/unified.py
def get_skill_loader(self) -> Any:
    return self._skill_loader
```

**Affected files**: `routing/unified.py`, `orchestration/plan_builder.py`

**Risk**: Low — encapsulate, no logic change.

---

## P1-C: Security Hardening

### P1-C1: Fix Windows Lock No-Op

**Current**: `cli/commands/loop_cmd.py:93-98` imports `fcntl`, catches `ImportError` on Windows, returns `True`. No cross-process synchronization on Windows.

**Fix**: Use file-based locking on Windows via `msvcrt.locking()` or `os.open(..., O_CREAT | O_EXCL)`.

```python
def _acquire_tick_lock(self, lock_path: Path) -> bool:
    try:
        import fcntl
        self._lock_fd = open(lock_path, "w")
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (ImportError, OSError):
        pass
    # Windows fallback: use file existence as lock
    try:
        self._lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        return True
    except FileExistsError:
        return False
```

**Affected files**: `cli/commands/loop_cmd.py`

**Risk**: Medium — changes locking behavior on Windows.

### P1-C2: Sandbox Bun Fallback

**Current**: `installer/pack_installer.py:515-556` executes `bun run gen:skill-docs` on host when container runtime unavailable and `package.json` has bun scripts. No sandbox, no TTY confirmation.

**Fix**: Require `allow_unsafe_build=True` + interactive TTY for Bun fallback (same gate as build scripts at line 377-389).

```diff
     if has_bun_fallback:
+        if not allow_unsafe_build:
+            raise SecurityError("Bun build requires --allow-unsafe-build flag")
+        if not sys.stdin.isatty():
+            raise SecurityError("Bun build requires interactive terminal")
         logger.warning("Running bun build on host (no container available)")
```

**Affected files**: `installer/pack_installer.py`

**Risk**: Medium — changes behavior, may break existing installs without `--allow-unsafe-build`.

### P1-C3: Wrap LLMConfig.api_key in SecretStr

**Current**: `core/llm_config.py:340-350` stores API key as plain `str` in `LLMConfig` dataclass. No `__repr__` override — key leaks in logs, error messages, serialization.

**Fix**: Use Pydantic `SecretStr`:

```python
from pydantic import SecretStr

@dataclass
class LLMConfig:
    api_key: SecretStr | None = None
    
    def get_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key.get_secret_value()
        return None
```

**Affected files**: `core/llm_config.py`, all callers of `.api_key`

**Risk**: Medium — API change, all consumers must use `.get_api_key()`.

---

## P1-D: Correctness Fixes

### P1-D1: Fix skill_installer Registry Substring Match

**Current**: `installer/skill_installer.py:241` uses `skill_id not in line` — substring match. Uninstalling `review` removes `code-review`, `review-gate`, etc.

**Fix**: Parse YAML, structurally remove from skills list:

```python
data = yaml.safe_load(content)
data["skills"] = [s for s in data.get("skills", []) if s != skill_id]
```

**Affected files**: `installer/skill_installer.py`

**Risk**: Low — structural edit replaces string match.

### P1-D2: Fix _restore_snapshot No-Op

**Current**: `transactional.py:136-139` base class only checks snapshot exists — no actual restore.

**Fix**: Raise `NotImplementedError` to force subclasses to implement:

```python
def _restore_snapshot(self, snapshot_id: str) -> None:
    raise NotImplementedError("Subclasses must implement _restore_snapshot")
```

**Affected files**: `installer/transactional.py`

**Risk**: Low — only `FileTransactionalInstaller` calls it, and it overrides correctly.

### P1-D3: Fix reorchestrator Goals-Met Heuristic

**Current**: `reorchestrator.py:128-142` checks `completed_steps >= intent_count`, not whether completed steps correspond to intents.

**Fix**: Check that completed steps match detected intents, not just count:

```python
def _check_goals_met(self, plan, accumulated_results) -> bool:
    completed_intents = set()
    for step in plan.steps:
        if step.status.value == "completed" and step.intent:
            completed_intents.add(step.intent)
    return completed_intents.issuperset(set(plan.detected_intents))
```

**Affected files**: `orchestration/reorchestrator.py`

**Risk**: Low — stricter check, may surface previously-"passed" cases.

### P1-D4: Unify ConflictResolver Default Strategies

**Current**: `conflict.py:348` adds 4 strategies; `router_factory.py:146` adds 5 (includes `ExplicitOverrideStrategy`).

**Fix**: Add `ExplicitOverrideStrategy` to default constructor:

```python
def _setup_default_strategies(self) -> None:
    self.add_strategy(ExplicitOverrideStrategy())
    self.add_strategy(ConfidenceGapStrategy())
    self.add_strategy(NamespacePriorityStrategy())
    self.add_strategy(RecencyStrategy())
    self.add_strategy(FallbackStrategy())
```

**Affected files**: `routing/conflict.py`

**Risk**: Low — aligns defaults.

---

## P1-E: Integration Cleanup

### P1-E1: Fix CLI-to-CLI Coupling

**Current**: `config.py:101` imports `_resolve_platforms` from `install.py` — CLI command imports from another CLI command.

**Fix**: Move `_resolve_platforms` to `core/config/platform.py` or `utils/platforms.py`.

**Affected files**: `config.py`, `install.py`, new shared module

**Risk**: Low — extract and delegate.

### P1-E2: Replace agent/ ValueError with VibeSOPError

**Current**: `step_runner.py:146` raises `ValueError` for plan-not-found; `agent/__init__.py:404` raises `ValueError` for single-intent queries.

**Fix**: Add `PlanNotFoundError`, `SingleIntentRoutingError` to `core/exceptions.py`.

```python
# core/exceptions.py
class PlanNotFoundError(VibeSOPError):
    pass

class SingleIntentRoutingError(VibeSOPError):
    pass
```

**Affected files**: `core/exceptions.py`, `agent/step_runner.py`, `agent/__init__.py`

**Risk**: Low — more specific exceptions, no behavior change.

### P1-E3: Update GrokBuildAdapter stale Field

**Current**: `adapters/grok_build.py` has `manages_skills = False` without documented rationale. Liskov violation (bypasses HookBasedAdapter hierarchy) — deferred to P2.

**Fix for this batch**: Add docstring explaining why GrokBuild doesn't manage skills + doesn't inherit from HookBasedAdapter.

```python
class GrokBuildAdapter(PlatformAdapter):
    """Grok Build platform adapter.

    Note: GrokBuild does NOT inherit from HookBasedAdapter because it uses
    JSON-based hooks (not shell scripts). Skills are managed by VibeSOP
    core rather than the platform adapter.
    """
```

**Affected files**: `adapters/grok_build.py`

**Risk**: Low — documentation only. Full hierarchy refactor deferred to P2.

---

## Verification Plan

Each batch is verified:
1. **Host pytest**: `uv run pytest <targets> -q --no-header`
2. **Full suite**: `uv run pytest -q --no-header -m "not benchmark and not slow"`
3. **Kimi code review**: `$KIMI -p "review the diff" --output-format text`
4. **OrbStack e2e**: at batch group completion

## Execution Order

```
P1-A (architecture decoupling) → verify → kimi
  ↓
P1-B (private attr violations) → verify → kimi
  ↓
P1-C (security hardening) → verify → kimi
  ↓
P1-D (correctness fixes) → verify → kimi
  ↓
P1-E (integration cleanup) → verify → kimi + OrbStack e2e
```

Each batch commits immediately after verification.
