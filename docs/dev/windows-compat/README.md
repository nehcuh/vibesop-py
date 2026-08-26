# Windows Compatibility Initiative

> **Status**: ✅ Complete — Windows production-ready (2026-07-19)
> **Result**: `88 failed / 4194 passed` → `0 failed / 4281 passed / 37 skipped`; ruff + basedpyright clean; pi verdict **SHIP**

Full-suite green on Windows 11 (zh-CN, non-privileged) with zero POSIX regressions and a new `test-windows` CI gate.

## Documents (chronological)

1. [01-analysis.md](01-analysis.md) — Root-cause analysis: 6 failure buckets, 88-failure census, 9 real production bugs
2. [02-design.md](02-design.md) — Implementation design v2 (P0–P4 phases, principles, risks)
3. [03-adversarial-review.md](03-adversarial-review.md) — Pre-implementation adversarial review (2 Blockers, 5 Majors) and resolutions
4. [04-implementation-log.md](04-implementation-log.md) — Phase-by-phase implementation record
5. [05-review.md](05-review.md) — Post-implementation review findings, fixes, deferred items
6. [06-verification.md](06-verification.md) — Final verification report + new-machine setup recipe

## Process

Design → adversarial review → implementation (P0 production bugs → P1 encoding → P2 symlink/exec → P3 paths → P4 isolation/CI) → independent review (production + test quality) → pi agent sign-off at each decision point.

## Key Artifacts

- `src/vibesop/utils/encoding.py` — UTF-8-strict + locale-fallback readers for user-managed configs
- `src/vibesop/utils/symlinks.py` — empirical symlink capability probe (cache-positive-only)
- `.vibe-copy-source` marker — pack discovery under copy-fallback
- `tests/conftest.py` — `_isolated_home` autouse fixture (3-layer), `symlink_supported` probe fixture
- `.github/workflows/ci.yml` — `test-windows` job (observation period, then required)

## 2026-08-26 follow-up (v8.1.1)

CI Windows green still does not prove host hooks work. Grok JSON hooks
need `vibe` on the **user** PATH (`%USERPROFILE%\.local\bin`). See
[platform-invariants.md](../platform-invariants.md).
