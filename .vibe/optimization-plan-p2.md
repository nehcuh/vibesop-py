# VibeSOP P2 Optimization Plan

> Generated: 2026-07-20
> Method: adversarial-optimization workflow

## Batch Summary

| Batch | Items | Effort |
|-------|-------|--------|
| P2-A | Test coverage (atomic_writer, cost_tracker, router_factory, overlay) | 4 items |
| P2-B | Code quality (_shared split, ClaudeCode dedup, GrokBuild refactor) | 3 items |
| P2-C | Cleanup (except:pass, test files, TYPE_CHECKING) | 4 items |

---

## P2-A: Test Coverage

### P2-A1: atomic_writer.py tests
- Test temp-file+rename atomic pattern
- Test failure recovery (partial write, disk full)
- Test permission errors

### P2-A2: cost_tracker.py tests
- Test budget tracking (token counting)
- Test cost estimation across providers
- Test overflow/budget exhaustion

### P2-A3: router_factory.py tests
- Test router creation with valid config
- Test missing config defaults
- Test matcher registration

### P2-A4: builder/overlay.py tests
- Test deep merge of manifests
- Test conflicting keys
- Test empty overlay

---

## P2-B: Code Quality

### P2-B1: _shared.py split
- Extract doc generation → `_doc_gen.py`
- Extract skill utilities → `_skill_util.py`  
- Extract env detection → `_env.py`

### P2-B2: ClaudeCode render_config dedup
- Merge render_config/rendr_config_only with `render_skills` param

### P2-B3: GrokBuildAdapter HookBasedAdapter inherit
- Add `hook_format` param to HookBasedAdapter
- GrokBuild extends HookBasedAdapter(hook_format="json")

---

## P2-C: Cleanup

### P2-C1: except:pass remaining (high-priority ~10 sites)
### P2-C2: merge duplicate test files
### P2-C3: relocate root test files
### P2-C4: TYPE_CHECKING import cleanup

---

## Verification
1. `uv run pytest tests/ -q -m "not benchmark and not slow"`
2. Kimi review at batch completion
3. OrbStack e2e at phase completion
