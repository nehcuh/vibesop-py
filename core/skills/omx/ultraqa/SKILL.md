---
id: omx/ultraqa
name: UltraQA
description: Autonomous QA cycling with architect diagnosis before fix.
intent: testing
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to run autonomous QA cycles, find and fix bugs systematically
---

# UltraQA — Autonomous QA Cycling

Systematic QA testing with architect diagnosis before any fix.

## Workflow

1. **Discover**: Find all testable surfaces (pages, APIs, workflows)
2. **Test**: Run systematic tests against each surface
3. **Diagnose** (Architect): Before fixing, diagnose root cause
4. **Fix**: Apply targeted fix based on diagnosis
5. **Verify**: Re-run tests to confirm fix
6. **Cycle**: Repeat until no new bugs found

## QA Checklist

- [ ] Critical paths work end-to-end
- [ ] Error states are handled gracefully
- [ ] Edge cases don't crash
- [ ] Performance is acceptable
- [ ] Accessibility basics checked
- [ ] Mobile responsive (if applicable)

## State

Save to `.vibe/state/sessions/{session-id}/ultraqa.json`:
```json
{
  "session_id": "...",
  "cycle": 3,
  "bugs_found": 5,
  "bugs_fixed": 4,
  "bugs_remaining": 1,
  "status": "running"
}
```

## Exit Criteria

- No new bugs found in 2 consecutive cycles
- All critical bugs fixed
- Max cycles (5) reached
