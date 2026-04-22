# Project Knowledge

## Technical Pitfalls

### Typer CLI Testing: Function vs App Instance (2026-04-20)

**Issue**: `typer.testing.CliRunner.invoke()` requires a `typer.Typer` app instance or `click.Command`, not a decorated function. When tests import the command function directly from the module, `runner.invoke(func, ["--help"])` raises `AttributeError: 'function' object has no attribute '_add_completion'`.

**Root Cause**: Typer commands are registered via `@app.command()` decorator at module import time. The decorated function loses its Typer metadata when imported directly. Tests must import the Typer app instance instead.

**Solution**:
```python
# ❌ Wrong: Importing the function
from vibesop.cli.commands.skill_add import add
runner.invoke(add, ["--help"])  # AttributeError!

# ✅ Correct: Import the Typer app
from vibesop.cli.commands.skills import skills_app
runner.invoke(skills_app, ["add", "--help"])
```

**File**: `tests/cli/test_skill_add_cmd.py`

---

### Dataclass Refactoring Cascade: Callers Not Updated (2026-04-20)

**Issue**: When a dataclass like `SkillSuggestion` is refactored (fields renamed/removed), all call sites break with `TypeError: unexpected keyword argument`. In large codebases with many new files, these breakages are easy to miss.

**Root Cause**: `skill_add.py` was created referencing an older version of `SkillSuggestion` with fields like `skill_id`, `examples`, `suggested_category`. After `session_analyzer.py` was refactored, these fields no longer existed.

**Solution**:
1. Use `dataclasses.fields()` to validate fields programmatically when interface changes
2. Run full test suite after any shared dataclass change
3. Prefer dataclass inheritance or `**kwargs` with validation for evolving interfaces

**Files**:
- `src/vibesop/core/session_analyzer.py` - `SkillSuggestion` dataclass
- `src/vibesop/cli/commands/skill_add.py` - broken call site

---

### Configuration Generated But Not Read (2026-04-20)

**Issue**: Auto-configuration system generated skill LLM configs and saved them to `.vibe/skills/auto-config.yaml`, but no code existed to read and use these configurations.

**Root Cause**: Implementation focused on generation phase (understander.py) but neglected the consumption phase. The understander module saved configs, but:
- No config loader existed to read `.vibe/skills/auto-config.yaml`
- No integration with existing LLMConfigResolver
- Skills couldn't access their own LLM configurations

**Solution**: Created complete configuration management system:
1. `SkillConfigManager` - manages skill-level configs with CRUD operations
2. Priority fallback strategy - skill → global → env → agent → default
3. CLI commands - `vibe skill config` for user management
4. Python API - `get_skill_llm_config()` for programmatic access

**Key Learning**: Always implement both read and write paths for configuration systems. Generating configs without a reader is incomplete.

**Files**:
- `src/vibesop/core/skills/config_manager.py` (NEW - 450+ lines)
- `src/vibesop/cli/commands/skill_config.py` (NEW - 450+ lines)
- `tests/unit/test_skill_config_manager.py` (NEW - 300+ lines)

---

### Trusted External Skills with Audit Warnings (2026-04-19)

**Issue**: When allowing trusted external skill packs (gstack, superpowers) through security audit despite non-critical threats, tests may fail because they expect `is_safe=True` for all loaded skills.

**Root Cause**: The code intentionally allows trusted skills through with benign warnings (e.g., role-prompting language), but `is_safe` property remains `False` because it's computed from `audit_result.is_safe`.

**Solution**: Update tests to check that loaded skills are either safe OR trusted with non-critical threats:

```python
from vibesop.security.skill_auditor import ThreatLevel

is_trusted_safe = (
    skill.external_metadata.is_safe or
    (skill.external_metadata.is_trusted and
     skill.external_metadata.audit_result and
     skill.external_metadata.audit_result.risk_level != ThreatLevel.CRITICAL)
)
assert is_trusted_safe, "Skill should be safe or trusted with non-critical threats"
```

**File**: `src/vibesop/core/skills/loader.py` lines 161-180

---

### Test Data Mismatch: Registry vs Filesystem Skills (2026-04-19)

**Issue**: Tests trying to instantiate built-in registry skills (e.g., "systematic-debugging") fail because `SkillManager.get_skill_instance()` only works for filesystem skills.

**Root Cause**: Built-in skills are loaded from YAML registry, not filesystem. `loader.instantiate()` returns `None` for registry-only skills.

**Solution**: Use actual filesystem skills with proper namespace:
- ❌ Wrong: `"systematic-debugging"` (registry-only)
- ✅ Correct: `"builtin/systematic-debugging"` (filesystem)
- ✅ Correct: `"gstack/office-hours"` (external pack)

**File**: `tests/integration/test_external_skill_execution.py` line 58

---

### Performance Regression from Logging Overhead (2026-04-19)

**Issue**: Adding `logger.warning()` calls for 23+ trusted skills during loading caused 8% performance regression (50 QPS → 46 QPS).

**Root Cause**: Even at WARNING level, logging has overhead. When called for every trusted skill during discovery, it accumulates.

**Solution**:
1. Remove logging entirely for expected cases (trusted skills with non-critical threats)
2. Or use DEBUG level for informational messages
3. Adjust performance targets to account for enhanced security

**Optimized Code**:
```python
# Before: 23+ logger.warning() calls
if ext_metadata.audit_result.risk_level != ThreatLevel.CRITICAL:
    logger.warning(...)  # Overhead!

# After: No logging for expected cases
if ext_metadata.audit_result.risk_level == ThreatLevel.CRITICAL:
    continue
# Skip logging - trusted skills are expected
```

**File**: `src/vibesop/core/skills/loader.py` line 170

---

### Narrowing Bare `except Exception` Safely (2026-04-21)

**Pattern**: When replacing bare `except Exception` with specific types, always include custom exception classes in the catch tuple.

**Problem**: Custom exceptions like `SkillNotFoundError` (inherits `VibeSOPError` → `Exception`) or `SkillExecutionError` (inherits `Exception`) are easy to miss when narrowing. Tests that relied on the broad catch will fail with uncaught exceptions.

**Detection Workflow**:
```python
# ❌ Wrong: only catches built-in exceptions
except (OSError, ValueError):
    return None  # SkillNotFoundError escapes!

# ✅ Correct: include custom exceptions explicitly
except (SkillNotFoundError, KeyError, ValueError, OSError):
    return None
```

**Key Insight**: After narrowing bare excepts, run the FULL test suite — not just the modified files. Custom exceptions often only surface in integration tests.

**Files**: `src/vibesop/core/skills/manager.py`, `tests/integration/test_external_skills_real.py`

---

### Pydantic V2 `ConfigDict` Migration (2026-04-21)

**Pattern**: When converting dataclasses to Pydantic V2 BaseModel, use `model_config = ConfigDict(...)` instead of nested `class Config:`.

**Problem**: `class Config:` triggers `PydanticDeprecatedSince20` warning in V2 and will be removed in V3.

**Example**:
```python
from pydantic import BaseModel, ConfigDict, Field

# ❌ Deprecated
class MyModel(BaseModel):
    class Config:
        frozen = False

# ✅ Correct
class MyModel(BaseModel):
    model_config = ConfigDict(frozen=False)
```

**Files**: `src/vibesop/core/routing/layers.py`

---

## Reusable Patterns

### Interface Drift Detection via Full Test Run (2026-04-20)

**Pattern**: After refactoring shared classes/functions, always run the FULL test suite — not just the modified file's tests.

**Problem**: Refactoring `SkillSuggestion` dataclass passes its own unit tests, but breaks `skill_add.py` which uses it. Similarly, changing `AuditResult` fields breaks `skill_add.py` security audit handling.

**Detection Workflow**:
```python
# 1. Make the refactoring change
@dataclass
class SkillSuggestion:
    skill_name: str
    description: str
    # Removed: skill_id, examples, suggested_category

# 2. Run tests for the modified module ONLY (NOT enough)
pytest tests/unit/test_session_analyzer.py  # Passes!

# 3. Run FULL suite to catch drift (REQUIRED)
pytest  # FAILS: skill_add.py uses removed fields
```

**Key Insight**: Interface changes are silent killers. Unit tests of the modified module pass, but integration points fail. Full suite execution is the only reliable detection method.

**Automation**: Add pre-commit hook or CI check that runs full test suite on any `src/` file change.

---

### Skill Auto-Configuration Pipeline (2026-04-20)

**Pattern**: Automatic skill understanding and configuration without external LLM dependency.

**Components**:
1. **Rule Engine** - Predefined category → config mappings
2. **Keyword Analyzer** - TF-IDF extraction with stop words filtering
3. **Configuration Generator** - Merges rules + analysis into config
4. **Confidence Scoring** - Calculates confidence based on feature quality

**Workflow**:
```python
# 1. Analyze skill content
analysis = KeywordAnalyzer.analyze(skill_description)

# 2. Apply category rules
category = CategoryRules.infer_category(metadata, content)
category_config = CategoryRules.get_config(category)

# 3. Generate routing patterns
patterns = _generate_routing_patterns(metadata, analysis)

# 4. Calculate priority
priority = _calculate_priority(metadata, analysis)

# 5. Save configuration
configurator.save_config(config, output_dir)
```

**Accuracy**: 75-85% confidence based on category clarity

**Files**: `src/vibesop/core/skills/understander.py` (680 lines)

---

### UltraQA Autonomous Testing Cycle

**Pattern**: Systematic QA testing with architect diagnosis before fixes.

**Workflow**:
1. **Discover**: Run test suite to find all bugs
2. **Diagnose**: Analyze root causes before fixing (architect review)
3. **Fix**: Apply targeted fixes based on diagnosis
4. **Verify**: Re-run tests to confirm fixes
5. **Cycle**: Repeat until no new bugs found

**Example**:
```bash
# Discover bugs
pytest --tb=no -q

# Diagnose each bug with architect review
# Read code, understand intent, identify root cause

# Apply targeted fixes
# Verify each fix individually
pytest tests/path/to/test.py
```

**Key Principle**: Never fix without diagnosis. Prevents thrashing and ensures correct solutions.

---

## Architecture Decisions

### Trusted External Skills Security Model (2026-04-19)

**Decision**: Allow trusted external skill packs (gstack, superpowers) through security audit despite non-critical threats, while blocking CRITICAL threats.

**Rationale**:
- Trusted packs contain legitimate role-prompting language that triggers benign role-hijacking heuristics
- Example: "You are a code reviewer" triggers the rule, but is not actual hijacking
- CRITICAL threats (privilege escalation, jailbreaks) are always blocked
- Users explicitly install these packs and trust them

**Implementation**:
```python
if ext_metadata.is_trusted and ext_metadata.audit_result:
    if ext_metadata.audit_result.risk_level != ThreatLevel.CRITICAL:
        # Allow through with no logging (expected case)
        pass
    else:
        continue  # Block CRITICAL threats even for trusted packs
```

**Trade-offs**:
- ✅ Pros: Allows legitimate trusted packs, reduces false positives
- ⚠️ Cons: Requires updating test expectations, small performance overhead (~8%)
- 🎯 Decision: Security correctness > performance, optimize logging later

**Files**:
- `src/vibesop/core/skills/loader.py` (lines 161-180)
- `src/vibesop/security/rules.py` (removed overly broad pattern)
- `tests/integration/test_external_skill_execution.py` (updated test expectations)

---

### Skill-Level LLM Configuration Architecture (2026-04-20)

**Decision**: Implement skill-level LLM configuration with 5-tier fallback strategy instead of relying solely on global configuration.

**Rationale**:
- Different skills have different LLM requirements (e.g., code review needs precision, brainstorming needs creativity)
- Users want granular control over which LLM each skill uses
- Automatic configuration generation reduces setup time
- Fallback strategy ensures robustness

**Priority Order**:
1. Skill-level config (.vibe/skills/auto-config.yaml)
2. Global config (.vibe/config.yaml)
3. Environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
4. Agent environment (Claude Code, Cursor, etc.)
5. Default configuration

**Implementation**:
```python
class SkillConfigManager:
    @classmethod
    def get_skill_llm_config(cls, skill_id: str) -> LLMConfig | None:
        # 1. Try skill-level config
        skill_config = cls._load_skill_config_from_file(skill_id)
        if skill_config and skill_config.requires_llm:
            return LLMConfig(...)

        # 2. Fallback to global config
        resolver = LLMConfigResolver()
        return resolver.resolve_llm_config(prefer_agent=True)
```

**Trade-offs**:
- ✅ Pros: Maximum flexibility, automatic configuration, robust fallback
- ⚠️ Cons: More complex configuration system, requires documentation
- 🎯 Decision: Flexibility and UX > simplicity

**Files**:
- `src/vibesop/core/skills/config_manager.py` (450+ lines)
- `src/vibesop/cli/commands/skill_config.py` (450+ lines)
- `src/vibesop/core/skills/understander.py` (auto-config integration)

---

### Lazy-Loaded Attributes and `hasattr()` Interaction (2026-04-21)

**Issue**: Setting a lazy-loaded attribute to `None` in `__init__` breaks code that uses `hasattr()` or `getattr(obj, "attr", None)` for existence checks.

**Root Cause**: When `self._skill_loader = None` is set in `__init__`, `hasattr(self, "_skill_loader")` returns `True`, causing the lazy-loading branch to be skipped. Later code tries to use `None._skill_cache` and fails.

**Solution**: Do NOT set lazy-loaded attributes in `__init__` when the injected value is `None`. Let the attribute remain absent so `hasattr()` / `getattr()` fallbacks work correctly.

```python
# ❌ Wrong: breaks hasattr check
class UnifiedRouter:
    def __init__(self, skill_loader=None):
        self._skill_loader = skill_loader  # None breaks hasattr!

    def _get_candidates(self):
        if self._skill_loader is None:  # AttributeError if not set
            self._skill_loader = SkillLoader(...)

# ✅ Correct: only set when actually provided
class UnifiedRouter:
    def __init__(self, skill_loader=None):
        if skill_loader is not None:
            self._skill_loader = skill_loader

    def _get_candidates(self):
        if getattr(self, "_skill_loader", None) is None:
            self._skill_loader = SkillLoader(...)
```

**Files**: `src/vibesop/core/routing/unified.py`

---

### Class-Level Caching Breaks Test Isolation (2026-04-21)

**Issue**: Adding a `_global_candidates_cache` class variable to `UnifiedRouter` to share loaded skill candidates across instances caused **48 test failures**.

**Root Cause**: Tests that install/modify skills expect a fresh router with fresh candidates. When router instances share a global cache, tests see stale data from previous tests.

**Example Failure**:
```python
# Test 1: Install a new skill
vibe skill add my-skill
router1 = UnifiedRouter()
router1.route("my skill")  # Works (caches candidates)

# Test 2: Check routing
router2 = UnifiedRouter()
router2.route("my skill")  # FAILS - uses Test 1's stale cache
```

**Solution**: Keep candidate caching at instance level only. For performance optimization:
1. Accept slower tests (current: ~4 min for full suite)
2. Use `pytest-xdist` for parallel execution (~39s with `-n auto`)
3. Mark slow tests with `@pytest.mark.slow` and exclude from fast suite

**Key Insight**: Global/mutable class-level state is almost always wrong in testable code. Prefer instance-level caching + external parallelization.

**Files**: `src/vibesop/core/routing/unified.py` (reverted after 48 failures)

---

### Test Assumption: `skills[0]` is Fragile (2026-04-21)

**Issue**: `test_get_skill_definition` used `skills[0]` assuming the first discovered skill has a workflow definition. When skills are loaded in different order (e.g., project-level YAML files added), the first skill may be a prompt type with no workflow, causing `get_skill_definition()` to return `None`.

**Root Cause**: Test assumed stable skill ordering and type. Skill discovery order depends on filesystem traversal and search paths.

**Solution**: Use a known stable skill with guaranteed workflow:
```python
# ❌ Fragile: assumes first skill has workflow
skill_id = skills[0]["id"]
result = manager.get_skill_definition(skill_id)
assert result is not None  # FAILS if first skill is prompt type

# ✅ Robust: use known skill with workflow
skill_id = "gstack/freeze"  # Known to have workflow
result = manager.get_skill_definition(skill_id)
assert result is not None
```

**File**: `tests/core/skills/test_manager_integration.py`

---

## Reusable Patterns

### Parallel Test Execution with pytest-xdist (2026-04-21)

**Pattern**: Use `pytest-xdist` with `-n auto` for dramatically faster test feedback during development.

**Before**: `uv run pytest` → 255s (~4 min)
**After**: `uv run pytest -n auto --no-cov` → 39s (~6.6x faster)

**Makefile Target**:
```makefile
test-fast:
	uv run pytest -n auto --no-cov -q -m "not benchmark and not slow"
```

**Caveats**:
1. Coverage collection doesn't work well with xdist (use `--no-cov` for fast runs)
2. Benchmark tests may fail under parallel load (exclude with `-m "not benchmark"`)
3. Tests that write to shared files may conflict (mark as `@pytest.mark.slow`)

**Files**: `Makefile`, `pyproject.toml` (dev dependency)

---

### Backward-Compat Proxy Methods with Deprecation Notes (2026-04-21)

**Pattern**: When extracting methods from a large class into sub-services, keep thin proxy methods with explicit deprecation notes instead of immediately removing them.

**Why**: Tests and external callers may directly invoke these methods. Immediate removal causes widespread breakage.

**Example**:
```python
class UnifiedRouter:
    # Backward compatibility proxies for extracted services
    # These thin wrappers are kept for test compatibility and will be
    # removed in a future major version.

    def _try_ai_triage(self, query, candidates, context=None):
        """Proxy to TriageService (kept for backward compatibility)."""
        if self._llm is not None:
            self._triage_service._llm = self._llm
        return self._triage_service.try_ai_triage(query, candidates, context)
```

**Migration Path**:
1. Extract methods to sub-service
2. Keep proxy methods with deprecation docstrings
3. Update tests to call sub-service directly (gradual)
4. Remove proxy methods in next major version

**Files**: `src/vibesop/core/routing/unified.py`
