# VibeSOP P0 Optimization Plan

> Generated: 2026-07-20
> Based on: Phase 1 Deep Diagnosis (10 Map + 6 Cross-cut + Synthesize)

---

## Batch Summary

| Batch | Items | Files Changed | Risk |
|-------|-------|---------------|------|
| P0-A | Name collisions (C1-C3) | `miss_counter.py`, `retention.py`, `executor.py`, `suggestion_collector.py`, `cleanup_cmd.py` | Low (rename, no logic change) |
| P0-B | Silent exception (C4) | `loader.py` | Low (add logging) |
| P0-C | JSONL field loss (H6) | `plan_tracker.py` | Medium (adds missing fields) |

---

## P0-A: Fix Name Collisions

### C1: `MissedCluster` in `miss_counter.py`

**Current**: `miss_counter.MissedCluster(hash, count, first, last)`
**Conflicts with**: `missed_query_tracker.MissedCluster(cluster_key, ...)`

**Fix**: Rename to `MissedHashCluster`

```diff
- class MissedCluster:
+ class MissedHashCluster:
```

**Affected files**: `miss_counter.py` only (no external importers)

### C2: `RetentionSuggestion` in `retention.py`

**Current**: Already marked DEPRECATED. Says "Use feedback_loop.RetentionSuggestion instead"

**Fix**: Rename to `DeprecatedRetentionSuggestion` to make deprecation explicit

```diff
- class RetentionSuggestion:
+ class DeprecatedRetentionSuggestion:
```

**Affected files**: `retention.py` only (retention.py already says "backwards compatibility", no importers found)

### C3: `SkillResult` in `executor.py`

**Current**: `executor.SkillResult` shadows `base.SkillResult` — completely different fields

**Fix**: Rename to `SkillExecutionResult`

```diff
- class SkillResult:
+ class SkillExecutionResult:
```

**Affected files**: `executor.py` (check internal references)

---

## P0-B: Fix Silent Exception Swallowing

### C4: `_load_yaml_skill` in `loader.py:382-383`

**Current**: `except (OSError, Exception): pass`

**Fix**: Add `logger.warning()` with file path and exception

```diff
-        except (OSError, Exception):
-            pass
+        except OSError as e:
+            logger.warning("Failed to load YAML skill %s: %s", file_path, e)
+        except Exception as e:
+            logger.warning("Unexpected error loading YAML skill %s: %s", file_path, e)
```

---

## P0-C: Fix JSONL Round-Trip Field Loss

### H6: `plan_tracker._dict_to_plan` in `plan_tracker.py:138-166`

**Current**: Only populates 10 of ~27 ExecutionStep fields
**Missing**: `original_query_segment`, `dependencies`, `can_parallel`, `parallel_group`, `is_verification_step`, `verification_result`, `trust_level`, `dynamic_status`, `loop_iteration`, `contestant_index`, `step_type`, `estimated_risk`, `estimated_file_count`, `source_files`, `assigned_role`, `agent_squad_id`, `role_skills`

**Missing from ExecutionPlan**: `execution_mode`, `workflow_pattern`, `is_dynamic`, `dry_threshold`, `max_reorchestration_rounds`, `reorchestration_history`, `metadata`

**Fix**: Add missing field extraction from dict, with safe defaults

```diff
     def _dict_to_plan(self, data: dict[str, Any]) -> ExecutionPlan:
         steps = [
             ExecutionStep(
                 step_id=s["step_id"],
                 step_number=s["step_number"],
                 skill_id=s["skill_id"],
                 intent=s.get("intent", ""),
                 input_query=s.get("input_query", ""),
                 output_as=s.get("output_as", ""),
                 status=StepStatus(s.get("status", "pending")),
                 result_summary=s.get("result_summary"),
                 started_at=s.get("started_at"),
                 completed_at=s.get("completed_at"),
+                original_query_segment=s.get("original_query_segment", ""),
+                dependencies=s.get("dependencies", []),
+                can_parallel=s.get("can_parallel", False),
+                parallel_group=s.get("parallel_group"),
+                is_verification_step=s.get("is_verification_step", False),
+                verification_result=s.get("verification_result"),
+                trust_level=s.get("trust_level"),
+                dynamic_status=s.get("dynamic_status"),
+                loop_iteration=s.get("loop_iteration"),
+                contestant_index=s.get("contestant_index"),
+                step_type=s.get("step_type"),
+                estimated_risk=s.get("estimated_risk"),
+                estimated_file_count=s.get("estimated_file_count"),
+                source_files=s.get("source_files", []),
+                assigned_role=s.get("assigned_role"),
+                agent_squad_id=s.get("agent_squad_id"),
+                role_skills=s.get("role_skills", []),
             )
             for s in data.get("steps", [])
         ]

         return ExecutionPlan(
             plan_id=data["plan_id"],
             original_query=data.get("original_query", ""),
             steps=steps,
             detected_intents=data.get("detected_intents", []),
             reasoning=data.get("reasoning", ""),
             created_at=data.get("created_at", ""),
             status=PlanStatus(data.get("status", "pending")),
+            execution_mode=data.get("execution_mode"),
+            workflow_pattern=data.get("workflow_pattern"),
+            is_dynamic=data.get("is_dynamic", False),
+            dry_threshold=data.get("dry_threshold"),
+            max_reorchestration_rounds=data.get("max_reorchestration_rounds"),
+            reorchestration_history=data.get("reorchestration_history", []),
+            metadata=data.get("metadata", {}),
         )
```

---

## Verification Plan

Each P0 batch is verified:
1. **Host pytest**: `uv run pytest tests/core/skills/ tests/core/orchestration/ -q`
2. **Kimi code review**: `$KIMI -p "review the diff" --output-format text`
3. **OrbStack e2e**: `$DOCKER run --rm -v "$PWD":/repo -w /repo vibesop-val-base:py3.12 uv run --frozen pytest tests/ -q --no-header -m "not benchmark and not slow"`
4. **Full test suite**: `uv run pytest -q --no-header -m "not benchmark and not slow"`

---

## Execution Order

```
P0-A (rename collisions) → verify → kimi review
  ↓
P0-B (fix silent exception) → verify → kimi review
  ↓
P0-C (fix JSONL fields) → verify → kimi review + OrbStack e2e
```

Each batch commits immediately after verification.
