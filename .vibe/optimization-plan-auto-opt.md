# Auto-Optimization Engine Plan

> Goal: Build background auto-optimization that reads routing data and self-tunes

## Architecture

```
.vibe/analytics.jsonl  ──→  AutoOptimizer  ──→  OptimizationService
.vibe/ai_triage_log.jsonl                            PreferenceBooster
                                                      FeedbackLoop
                                                      SkillClusterIndex
```

## What to Build

### 1. AutoOptimizer (`core/auto_optimizer.py`)
- Reads routing health from `RoutingHealthAnalyzer`
- Identifies optimization opportunities:
  a) High-miss skills → suggest disabling or deprecating
  b) Frequently-missed query clusters → suggest new skills
  c) High-cost AI triage → recommend keyword tuning
  d) High-latency skills → flag for review
- Applies optimizations via existing services (PreferenceBooster, FeedbackLoop)
- Produces an OptimizationReport

### 2. CLI command (`vibe optimize`)
- `vibe optimize` — show recommendations
- `vibe optimize --apply` — apply safe auto-optimizations
- `vibe optimize --dry-run` — show what would change

### 3. Auto-optimization loop (`vibe loop create`)
- Creates a scheduled loop that runs `vibe optimize --apply` periodically
- Reports results after each run

## Safety Constraints
- Never disable skills with < 3 evaluations
- Never auto-enable previously disabled skills
- Log all changes to `.vibe/optimization-log.jsonl`
- Dry-run by default; --apply explicitly required

## Verification
1. Unit tests for AutoOptimizer decision logic
2. End-to-end test with synthetic analytics data
3. Kimi code review
4. OrbStack container e2e
