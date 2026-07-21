# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-07-21 (S35) YAML Skill Loader 非 Skill 文件崩溃修复
**Session**: 用户报告 `vibe` 命令崩溃（`version should be a valid string, got int 2` from `.github/dependabot.yml`）。根因：`rglob("*.yml")` 扫描了 Dependabot/CI config 等非 skill YAML 文件。
**Completed**:
- `loader.py` `_load_yaml_skill()`: 新增 pre-filter — `"id" not in data and "name" not in data` → 跳过非 skill YAML
- `parser.py` `build_spec()`: `version=str(data.get("version", "1.0.0"))` — 防御式类型强制
**Verification**: 全量 4372 passed, 0 failed
**Next**: None

### 2026-07-21 (S34) Bootstrap auto-install + Analytics default-on
**Session**: Fix bootstrap scripts to auto-install community skill packs; enable analytics by default.
**Completed**:
- `bootstrap.sh` / `bootstrap.ps1`: added `uv run vibe install --auto` after `uv sync`
- `init_support.py` config templates: added `[analytics] enabled = true`
**Verification**: `vibe route` → `vibe status` correctly shows routing activity
**Next**: None — committed as `a85756e`

<!-- handoff:end -->
