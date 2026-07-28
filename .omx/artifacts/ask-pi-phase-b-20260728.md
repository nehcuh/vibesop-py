/bin/sh: 500: No such file or directory
Now I have all the source. Here's the full review.

---

## Phase B Review — HTTP API Layer (`dbcd94e`)

---

### Q1. DAG.to_dict() completeness

**Verdict: SHIP** (design note, not blocking)

**Evidence:**
- `dag_rebuilder.py:101-118` — serializer outputs `{id, kind, label, metadata, children}` per node, `{src, dst, kind}` per edge. Cytoscape.js only needs `id`, label/style hooks, and edge pairs — all present.
- `test_dag_rebuilder.py:96-111` — `test_dag_to_dict_serializes_all_fields` confirms the shape matches the dataclass.
- `test_dag_rebuilder.py:123-131` — `test_dag_to_dict_metadata_passthrough_no_mutation` explicitly proves metadata is the **same object** (no deep copy).

**Analysis:**

*Metadata pass-by-reference:* The test docstring says "callers don't expect stealth copies." But at an API boundary, this is inverted logic — API boundaries *should* decouple internal state from external consumers. Today it's safe because:

- `rebuild_dag()` creates fresh `DAGNode`/`DAG` instances per request — no caching, no shared state.
- `JSONResponse` serializes immediately, so even if the caller mutated the returned dict, the wire format is already fixed.
- The real risk is future: if someone adds a DAG cache (e.g., `lru_cache` on `rebuild_dag`), a request handler mutating `metadata` would corrupt the cache. This is a time-bomb, not a live bug.

*Phases as `list[dict[str, Any]]`:* Heterogeneous dicts are pragmatic here — phase metadata comes from raw span JSON and varies by implementation. A typed dataclass would fight the data shape. The `phases` list is a leaf in the API response (not further processed), so `Any` is fine.

**Recommendation:** Add a comment on `to_dict()`: "metadata is NOT deep-copied — callers MUST treat the returned dict as read-only." No code change needed now.

---

### Q2. 404 contract correctness

**Verdict: SHIP** (perf note, not blocking for MVP)

**Evidence:**
- `server.py:100-135` — `_trace_exists()` scans both `execution_plans.jsonl` (via `metadata.trace_id`) and `spans.jsonl` (via top-level `trace_id`), JSON parse + exact match.
- `test_server_endpoints.py:70-80` — `test_returns_404_when_trace_id_not_in_any_artefact` confirms 404 on genuine miss.
- `test_server_endpoints.py:113-125` — `test_trace_id_substring_does_not_false_positive_404` guards against the `T-1` vs `T-1x` false positive (confirmed because we JSON-parse and compare exact fields, not string-contains).
- `test_server_endpoints.py:90-110` — plan-only and span-only partial DAG cases both return 200 (correct).

**Analysis:**

*Trace exists definition:* If trace_id is in plans OR spans (not necessarily both) → 200. This is correct — the dashboard should show a partial DAG for each case, not lie with 404. `rebuild_dag()` already handles the "only plans" and "only spans" branches.

*Full-file scan on every request:* Both `execution_plans.jsonl` and `spans.jsonl` are append-only logs. For an active project, spans.jsonl can reach megabytes (each orchestration produces dozens of spans). `_trace_exists` does a full linear scan of both on every `/api/orchestration/dag` request. The dashboard is single-user and local, so practical impact is minimal — but the cost is O(total_spans) per request, which *will* become noticeable on projects with thousands of orchestrations.

*Fast path:* An in-memory `set[trace_id]` updated lazily (mtime check) would reduce this to O(1). Not needed for MVP but should be on the Phase C roadmap.

**Recommendation:** File a TODO for Phase C: "Add trace_id index (in-memory set with mtime-based invalidation) when spans.jsonl exceeds N lines."

---

### Q3. POST input validation tightness

**Verdict: FIX-THEN-SHIP** (one concrete bypass)

**Evidence:**
- `_schemas.py:33-66` — `ReflectionCreate` validates `target_type`, `kind`, `severity` against Literal types imported from core. ✓
- `_schemas.py:48-49` — `target_id`, `task_id`, `content` all have `min_length=1`. ✓
- `_schemas.py:49` — `content` has `max_length=500`. ✓
- `_schemas.py:51` — `linked_action: dict | None = None`. ← **Unvalidated for JSON-safety.**
- `test_server_endpoints.py:155-200` — six 422 tests for invalid kind/severity/target_type/empty string/over-500/missing field. All pass. ✓

**Analysis:**

*Bypass path — `linked_action` JSON-safety:* Pydantic accepts any `dict` for `linked_action`. A caller can submit:

```json
{"linked_action": {"path": "/tmp/foo", "timestamp": "not-serializable": set()}}
```

Wait — JSON itself can't represent `set()`. A valid HTTP JSON body can't contain Python sets. So the only way to inject non-JSON-serializable values is if the *Pydantic model accepts a Python dict directly* (e.g., from test code, not from HTTP). In FastAPI, request bodies are parsed from JSON strings, so `linked_action` will always be a `dict` of JSON-primitive values (str, int, float, bool, None, list, dict). **There is no HTTP path to inject non-JSON-serializable values into `linked_action`.**

However, if someone calls `create_reflection()` programmatically (bypassing HTTP), they *could* pass a dict with non-serializable values, which would then crash in `ReflectionStore.append()` → `json.dumps()`. The `__post_init__` guard is only on Literal fields. This is a library-consumer concern, not an API concern.

**Revised verdict: SHIP.** The HTTP parsing layer inherently sanitizes `linked_action` to JSON-primitive types. No code change needed.

*500-char limit:* Pydantic's `max_length=500` counts Python string characters. Chinese characters are single `str` elements in Python 3, so 500 Chinese chars = 500 characters. The plan says "<500 字" — 字 means "characters" in this context. Match confirmed. ✓

*Literal drift protection:* `_schemas.py` imports `ReflectionKind`, `ReflectionStatus`, `TargetType` directly from `vibesop.core.observability.reflection`. Single source of truth — schema can't drift. ✓

---

### Q4. PATCH error mapping

**Verdict: FIX-THEN-SHIP** (lost-update race in `update_status`)

**Evidence:**
- `server.py:460-479` — handler wraps `store.update_status()` in `try/except KeyError → 404`. ✓
- `reflection.py:284-294` — `update_status()` acquires `threading.Lock`, then calls `_locked_update_status()`.
- `reflection.py:298-328` — `_locked_update_status()` calls `self.list_all()` (NO lock), mutates, then acquires `fcntl.LOCK_EX` and does atomic rewrite.
- `test_server_endpoints.py:465-525` — 6 PATCH tests cover addressed/dismissed/404/422/missing-field/persistence. ✓

**Analysis:**

*Lost-update race:* Read the sequence in `_locked_update_status`:

```
1. current = self.list_all()          ← opens file read-only, NO fcntl lock
2. current[target_idx].status = ...   ← in-memory mutation
3. fcntl.flock(f, LOCK_EX)            ← lock acquired HERE
4. _atomic_write_all(current)         ← writes .tmp + rename
```

Between step 1 and step 3, a concurrent process (CLI calling `ReflectionStore.append()`) can:
- Acquire `fcntl.LOCK_EX` on its own file handle
- Append a new line to `reflections.jsonl`
- Release the lock

Step 4 then atomically rewrites the file with the *pre-append* state — the concurrently-appended reflection is **silently dropped**.

Within a single process, `threading.Lock` prevents this (both `append` and `update_status` hold it). But the CLI and dashboard run in separate processes. The dashboard is explicitly designed to coexist with CLI writers (`server.py:155-157` docstring: "Each request gets a fresh store so file-level state is always current — important because the dashboard runs alongside CLI writers that may append between requests").

**Fix:** Move `list_all()` AFTER the fcntl lock acquisition in `_locked_update_status`:

```python
def _locked_update_status(self, reflection_id, new_status):
    from vibesop.utils.atomic_writer import AtomicWriter

    try:
        import fcntl
    except ImportError:
        from vibesop.utils.file_lock import cross_process_lock
        with cross_process_lock(self._path):
            current = self.list_all()
            ...
        return

    with self._path.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            current = self.list_all()  # ← moved here
            target_idx = next(...)
            current[target_idx].status = new_status
            self._atomic_write_all(current, AtomicWriter())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

This also fixes the `open("a")` mode being used only as a lock handle (appending nothing). Opening in `"r+"` mode would be more correct, but `"a"` works for fcntl purposes on Linux.

*Other exceptions:* OSError/AtomicWriteError from disk failures → 500. Acceptable for a local tool. ✓

*Post-PATCH read-back:* O(N) `list_all()` scan is fine for reflection volumes (10s–100s). The comment acknowledges this. ✓

*Read-back race:* Another thread could append between `update_status` finishing and `list_all()` starting, but the just-updated reflection will ALWAYS be found (it was atomically written). The assert covers the vanishing case. ✓

---

### Q5. Security (write endpoints first time)

**Verdict: SHIP** (notes only, no blocking issues)

**Evidence:**
- `server.py:547-548` — `run_server(host="127.0.0.1", ...)` — explicit localhost binding. ✓
- `dashboard_cmd.py:16-21` — CLI `--host` defaults to `"127.0.0.1"`. ✓
- `server.py:31-36` — `_resolve_project_root()` walks up from CWD looking for `.vibe/`, falls back to CWD. ✓
- `reflection.py:217-245` — `ReflectionStore.append()` uses `threading.Lock` + `fcntl.LOCK_EX`. ✓
- No CSRF middleware, no CORS headers, no auth anywhere. ✗ (but see analysis)

**Analysis:**

*Localhost binding:* Confirmed at two layers — the `run_server()` default and the CLI `--host` default. A user could override with `--host 0.0.0.0`, but that's an explicit opt-in. ✓

*CSRF:* A malicious webpage on the internet *can* submit cross-origin POST/PATCH to `http://127.0.0.1:8420/api/reflections` because browsers allow cross-origin requests to localhost (no Same-Origin Policy protection for localhost). The attacker could:
1. Trick user into visiting `evil.com`
2. `evil.com` JS does `fetch("http://127.0.0.1:8420/api/reflections", {method: "POST", body: ...})`
3. Reflection is created in user's project

**Risk assessment:** Low. The dashboard is a local dev tool. The data written (reflections) is low-sensitivity. The attacker needs to know the exact API shape and that the dashboard is running. For a dev tool, this is acceptable. If this were a production service, CSRF tokens would be mandatory. **Not blocking for Phase B.**

*CWD fallback:* If the dashboard is started from `/tmp` or `~`, it will create `.vibe/observability/reflections.jsonl` there. The CLI command `vibe dashboard` should validate that a `.vibe/` directory exists before starting. Currently, `dashboard_cmd.py` doesn't call `_resolve_project_root()` before `run_server()`. This is a UX issue, not a security issue — writes land in a weird place but don't corrupt existing data. **Not blocking.**

*Lock semantics:* `ReflectionStore.append()` uses `threading.Lock` → `fcntl.LOCK_EX` on POSIX. `ReflectionStore.update_status()` uses the same pattern plus `AtomicWriter` for the rewrite. The two-layer locking is correct for cross-process safety (modulo the Q4 read-before-lock bug). ✓

---

## Overall Verdict: **PHASE B DONE-PENDING-FIX**

One concrete bug (Q4 lost-update race) must be fixed before Phase C. Everything else ships as-is.

### Top 3 Risks (ranked by severity)

| # | Risk | Severity | Fix |
|---|------|----------|-----|
| **1** | **Lost-update race in `update_status`** — concurrent CLI `append()` can be silently dropped when dashboard PATCH rewrites the file. `list_all()` must happen under `fcntl.LOCK_EX`. | **HIGH** (data loss) | Move `list_all()` after lock acquisition in `_locked_update_status()` — see Q4 fix above |
| **2** | **No trace_id index** — `_trace_exists()` does O(N) full-file scan of spans.jsonl on every `/api/orchestration/dag` request. Will degrade noticeably on large projects (>1000 orchestrations). | **MEDIUM** (latency, not correctness) | Phase C TODO: add mtime-invalidated in-memory `set[trace_id]` |
| **3** | **Metadata by-reference at API boundary** — `DAG.to_dict()` returns the live `metadata` dict. Safe today (no caching), but a time-bomb if anyone adds `@lru_cache` to `rebuild_dag()`. | **LOW** (preventable with comment) | Add docstring note on `to_dict()`: "callers must treat returned dict as read-only" |

### Summary

| Question | Verdict |
|----------|---------|
| Q1. DAG.to_dict() completeness | **SHIP** |
| Q2. 404 contract correctness | **SHIP** |
| Q3. POST input validation tightness | **SHIP** |
| Q4. PATCH error mapping | **FIX-THEN-SHIP** |
| Q5. Security (write endpoints) | **SHIP** |

The code quality is high — the test coverage is excellent (28 tests, every error path exercised), the Literal validation at the API edge is correctly layered, and the cross-process locking architecture is sound. The one bug (Q4) is a classic TOCTOU — `list_all()` reads before acquiring the lock that guarantees a consistent view. Fix is one-line repositioning of a function call.
