# Project Knowledge

## Technical Pitfalls

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

## Reusable Patterns

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
