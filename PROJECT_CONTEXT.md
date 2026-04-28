# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-28 15:45

**Session**: Claude Code 配置格式修复

**Summary**:
1. 修复 Claude Code 配置生成器 `_render_settings_json` 中的两个格式错误：
   - `"Bash(vibe:* *)"` → 删除（`:*` 前缀通配符不在模式末尾，且已有 `"Bash(vibe:*)"` 覆盖）
   - hooks 结构修正：`{"matcher": "", "command": "..."}` → `{"matcher": "", "hooks": [{"type": "command", "command": "..."}]}`
2. 运行 adapter 测试验证（7 passed, 1 pre-existing failed unrelated）

**Key Discoveries**:
- Claude Code settings.json 中 hooks 必须使用 `matcher` + `hooks` 数组结构，直接使用 `command` 字段会导致 "Expected array, but received undefined"
- Claude Code permissions.allow 中 `:*` 前缀通配符必须出现在整个模式参数的末尾，如 `Bash(vibe:* *)` 是非法的

**Files Modified**:
- `src/vibesop/adapters/claude_code.py` — `_render_settings_json` 方法

**Next Steps**:
- 重新运行 `vibe build` 生成 Claude Code 配置验证修复生效
- 考虑为 adapter 配置输出增加 schema 验证，避免类似格式错误流入用户环境

---

### 2026-04-28 11:00

**Session**: 文档审计 + 测试修复 + PyPI 发布 + instinct skill 部署

**Summary**:
1. **文档全面审计**: 52 处版本不一致/过期引用/缺失覆盖 → 13 文件修复
2. **CLI_REFERENCE.md 补齐**: +6 个新命令文档（status, cleanup, share, discover, end-check, suggestions）
3. **hooks-guide.md 修复**: `vibe deploy` → `vibe build`, `vibe memory flush` → session-end cleanup
4. **3 个测试修复**: `test_no_args_is_help`（exit 0→status）、`test_default_settings`（ollama default）、`test_matcher_layer_skips_duplicate_optimizations`（_apply_optimizations None guard）
5. **PyPI v5.3.0 发布**: `pip install vibesop==5.3.0` 已上线
6. **plan 文件标记完成**: 5 个 plan Draft→✅ Completed
7. **Instinct SKILL.md 重写**: 高层描述→可执行 Python 单行命令
8. **OpenCode 部署**: 6 个独立 skill（/learn, /learn-eval, /instinct-status, /instinct-export, /instinct-import, /evolve）

**Test Status**: 396 CLI+routing+core tests passed, 0 failed, 0 lint errors

**Files Modified**:
- docs/ (8 files): ROADMAP, PROJECT_STATUS, SECURITY, SKILLS_GUIDE, CLI_REFERENCE, hooks-guide, INDEX, version_05, three-layers, cold-start, troubleshooting, workflows
- PROJECT_CONTEXT.md, CLAUDE.md, README.md, .vibe/PROJECT_CONTEXT.md
- pyproject.toml (version 5.2.0→5.3.0)
- tests/test_cli.py, tests/test_models.py, unified.py (3 test fixes)
- core/skills/instinct-learning/SKILL.md (executable commands)
- ~/.config/opencode/skills/{learn,learn-eval,instinct-status,instinct-export,instinct-import,evolve}/SKILL.md (6 OpenCode skills)

**Next Steps**:
- 重启 OpenCode 测试 /learn、/evolve 等命令
- 推送 main（done?）→ 创建 GitHub Release
- v6.0: 上下文感知推荐引擎 v2、独立技能注册中心
<!-- handoff:end -->
