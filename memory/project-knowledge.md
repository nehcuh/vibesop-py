# VibeSOP Project Knowledge

## Technical Pitfalls

### UTF-8 BOM Silently Breaks TOML Parsing — `encoding="utf-8"` Is Not Enough (2026-07-20)

**Issue**: `~/.vibe/config.toml` 开头有 UTF-8 BOM（`EF BB BF`），`tomllib.loads()` 报 `Invalid statement (at line 1, column 1)`，路由回退到默认配置，LLM provider 失效。

**Root Cause**: Python 的 `Path.write_text(content, encoding="utf-8")` 不写 BOM，但 Windows 编辑器（Notepad）、某些 PowerShell 重定向会自动加 BOM。`read_text_with_fallback()` 正确解码了 BOM 文件（`.decode("utf-8")` 保留 `\ufeff` 在字符串中），但 `tomllib` 不接受以 `\ufeff` 开头的文本。

**Solution**: 在 `load_toml_with_fallback()` 和 `read_text_with_fallback()` 中统一剥离 BOM：
```python
def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text
```
这是跨平台部署的经典坑——文件生成时走 `encoding="utf-8"`（无 BOM），但用户在任何 Windows 编辑器打开保存后就会引入 BOM。

**Files**: `src/vibesop/utils/encoding.py`

### `sys.stdin.isatty()` Is Unreliable on Windows with PTY — `NoConsoleScreenBufferError` (2026-07-20)

**Issue**: Grok Build 给 shell 进程分配了 PTY（`sys.stdin.isatty()` → `True`），但 `prompt_toolkit` 在 Windows 上需要真实控制台屏幕缓冲区（`Win32Output`），PTY 环境下抛 `NoConsoleScreenBufferError`，`vibe route` 的 `questionary.select()` 直接崩溃。

**Root Cause**: `_needs_confirmation()` 用 `sys.stdin.isatty()` 判断是否跳过交互提示，但 PTY（伪终端）也满足 `isatty()`。真正的检测应该是"能否创建 `Win32Output`"，而这只能在调用时才知道。

**Solution**: 用 `try/except Exception` 包裹所有 `questionary` 调用，异常时 fallback 到默认值：
```python
def _safe_questionary_select(message, choices, default="confirm"):
    try:
        return questionary.select(message, choices=choices).ask()
    except Exception:
        logger.warning("Interactive prompt unavailable (no console); auto-selecting %r.", default)
        return default
```
`NoConsoleScreenBufferError` 是 `prompt_toolkit` 内部实现细节的普通 `Exception` 子类，不能精确 `except`（跨版本可能变），所以用 broad catch。

**Files**: `src/vibesop/cli/confirmation.py`, `src/vibesop/cli/main.py`

### Routing Eval Baseline: CN Queries Miss Builtin Management Skills (2026-07-19)

See project-knowledge.md history for details.

### Analytics default-off surprises users
- `_analytics_enabled()` in `unified.py:840` returns `False` by default (opt-in). All `vibe route` calls silently skip `analytics.jsonl` writing unless `[analytics] enabled = true` is in config
- `vibe status` dashboard shows "No routing activity" / "Routing analytics not yet available" even though user has been routing — no error, no hint to enable

### Bootstrap→build gap on community skill packs
- `bootstrap.sh`/`bootstrap.ps1` suggest `vibe build` as next step, but `vibe build` only generates config — it does not trigger `vibe install --auto` for community packs (superpowers, omx, mattpocock)
- Only the deprecated `scripts/vibe-install` script called `_auto_install` after installation
- Fix: add `uv run vibe install --auto` to bootstrap scripts after `uv sync`

### Adversarial review workflow
- Adversarial agent (before execution) catches wrong fix approaches and missing items
- Kimi (external LLM) catches bugs parallel verifiers miss (e.g., Python list[-1] semantics, uncaught exception propagation)
- OrbStack e2e catches host-specific failures that pytest alone doesn't catch
- Each layer catches different error classes — three-layer review is the pattern

### Skill creation patterns
- Use `adversarial-optimization` skill as template for new workflow skills
- Keep SKILL.md lean: frontmatter → prerequisites → phases → anti-patterns
- Single-skill fallback from multi-intent routing is useful for validation

### Codebase-specific pitfalls
- `_shared.py` was 740 lines — split into `_content.py` (skill lifecycle) + `_generation.py` (config/doc output)
- GrokBuildAdapter CANNOT inherit HookBasedAdapter — fundamentally different hook mechanisms (JSON vs shell scripts)
- f-strings are simpler than Jinja2 for inline TOML generation (proportional simplicity)
- Python dicts are better than YAML files for internal routing rules (no I/O, no enum deserialization)

## Reusable Patterns

### Plan → Adversarial → Execute → Verify
1. Write structured plan with exact diffs
2. Spawn adversarial `plan` agent to challenge the plan
3. Execute with `general-purpose` review agent watching
4. At milestones: Kimi code review + OrbStack container e2e
5. Commit atomically after verification

### Atomic refactoring rules
- Do the safe, isolated refactor first to validate test coverage
- Then tackle higher-blast-radius changes with confidence
- Always follow existing patterns (e.g., FileBasedAdapter.render_config pattern for ClaudeCodeAdapter)

### Auto-optimization design
- Don't build new classes when existing subsystems can be composed
- RoutingHealthAnalyzer + FeedbackLoop + SkillSuggestionCollector = full optimization pipeline
- CLI is the integration layer, not a new core module

## Architecture Decisions
- GrokBuildAdapter Liskov fix explicitly rejected — JSON hooks ≠ shell hooks
- understander.py → YAML deferred — data tables as Python dicts are simpler
- init_support.py → Jinja2 deferred — f-strings are better for inline template generation
