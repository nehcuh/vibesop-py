# 项目清理报告

**日期**: 2026-04-05  
**项目**: VibeSOP-Py  
**范围**: 冗余文档、测试、代码、配置

---

## 🗑️ 建议删除项

### 1. 备份文件（立即删除）

| 文件 | 大小 | 原因 |
|------|------|------|
| `src/vibesop/core/checkpoint/manager.py.bak` | 10KB | 完全重复的备份文件 |

**命令**:
```bash
rm src/vibesop/core/checkpoint/manager.py.bak
```

---

### 2. 冗余文档（建议删除）

| 文件 | 大小 | 状态 | 原因 |
|------|------|------|------|
| `docs/DEEP_REVIEW_REPORT.md` | 11KB | 🔴 删除 | 被 V2 版本完全取代 |
| `INTEGRATION_PROGRESS_REPORT.md` | 4KB | 🟡 可选删除 | Phase 3 报告已包含所有内容 |
| `PHASE2_COMPLETION_REPORT.md` | 6KB | 🟡 可选删除 | Phase 3 报告已包含所有内容 |

**理由**:
- `DEEP_REVIEW_REPORT.md` 是初版，V2 版本扩展了 50% 内容且更全面
- Phase 2 和 Progress 报告是中间状态，Phase 3 报告是最终完整版
- 保留 `ARCHITECTURE_INTEGRATION_PLAN.md` 和 `ARCHITECTURE_INTEGRATION_COMPLETE.md` 作为对照有价值

**命令**:
```bash
rm docs/DEEP_REVIEW_REPORT.md
# 可选:
# rm INTEGRATION_PROGRESS_REPORT.md
# rm PHASE2_COMPLETION_REPORT.md
```

---

### 3. 冗余测试文件（建议合并或删除）

#### 高优先级

| 文件 | 大小 | 操作 | 理由 |
|------|------|------|------|
| `tests/hooks/test_installer.py` | 36 lines | 🔴 删除 | 被 `test_hook_installer.py` 完全覆盖 |

**命令**:
```bash
rm tests/hooks/test_installer.py
```

#### 中优先级（可考虑合并）

| 文件1 | 文件2 | 建议 |
|-------|-------|------|
| `tests/cli/test_build.py` | `tests/cli/test_build_command.py` | 合并到 test_build_command.py |
| `tests/workflow/test_models_unified.py` | `tests/workflow/test_models.py` | 合并到 test_models.py |

---

### 4. 嵌套/重复目录

| 路径 | 大小 | 操作 | 理由 |
|------|------|------|------|
| `.vibe/.vibe/cache/` | 80KB | 🔴 删除 | 错误的嵌套目录结构 |

**命令**:
```bash
rm -rf .vibe/.vibe/
```

---

### 5. 运行时生成的缓存（应加入 .gitignore）

| 路径 | 类型 | 操作 |
|------|------|------|
| `.vibe/cache/` | 运行时缓存 | 加入 .gitignore |
| `.vibe/state/` | 运行时状态 | 加入 .gitignore |
| `.vibe/preferences.json` | 用户偏好 | 已在 .gitignore |
| `.experiment/` | 实验数据 | 加入 .gitignore |
| `htmlcov/` | 覆盖率报告 | 已在 .gitignore |
| `coverage.xml` | 覆盖率数据 | 已在 .gitignore |

**检查 .gitignore**:
```bash
# 应包含:
.vibe/cache/
.vibe/state/
.experiment/
```

---

## ⚠️ 过时但仍需保留（用于兼容）

### 1. 弃用但仍需支持的代码

| 文件/模块 | 状态 | 移除版本 | 当前用途 |
|-----------|------|----------|----------|
| `vibe auto` 命令 | 🟡 已弃用 | v4.0.0 | 向后兼容，显示迁移提示 |
| `vibesop.triggers` 模块 | 🟡 已弃用 | v4.0.0 | 显示 DeprecationWarning |
| `route-select` 命令 | 🟡 已弃用 | v4.0.0 | 向后兼容 |

**建议**: 这些不应删除，直到 v4.0.0 发布。它们有明确的弃用警告。

### 2. 旧版本迁移文档

| 文件 | 状态 |
|------|------|
| `docs/MIGRATION_V3.md` | ✅ 保留 - 用户可能仍在迁移中 |

---

## 📝 需要更新的文档

### 1. README.md 可能需要更新

检查是否包含:
- [ ] 新的 `vibe autonomous-experiment` 命令
- [ ] 新的 `vibe instinct` 命令
- [ ] 外部技能执行的说明

### 2. CHANGELOG.md

需要添加 v3.1.0 条目:
```markdown
## v3.1.0 (2026-04-05)

### Features
- External skill execution (superpowers, gstack)
- Autonomous experiment system
- Instinct learning

### CLI
- New: `vibe autonomous-experiment`
- New: `vibe instinct`
```

---

## 🔧 建议的清理脚本

创建一个清理脚本 `scripts/cleanup.sh`:

```bash
#!/bin/bash
# cleanup.sh - Clean up redundant files

echo "Cleaning up redundant files..."

# 1. Remove backup files
rm -f src/vibesop/core/checkpoint/manager.py.bak
echo "✓ Removed backup files"

# 2. Remove redundant docs (optional - uncomment if needed)
# rm -f docs/DEEP_REVIEW_REPORT.md
# rm -f INTEGRATION_PROGRESS_REPORT.md
# rm -f PHASE2_COMPLETION_REPORT.md
# echo "✓ Removed redundant documentation"

# 3. Remove redundant tests (optional - review first)
# rm -f tests/hooks/test_installer.py
# echo "✓ Removed redundant tests"

# 4. Remove nested directory
rm -rf .vibe/.vibe/
echo "✓ Removed nested .vibe directory"

# 5. Clean Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "✓ Cleaned Python cache"

echo "Cleanup complete!"
```

---

## 📊 清理影响统计

| 类别 | 文件数 | 节省空间 | 风险 |
|------|--------|----------|------|
| 备份文件 | 1 | 10KB | 🟢 无风险 |
| 冗余文档 | 1-3 | 15-25KB | 🟡 低（保留 Phase 3）|
| 冗余测试 | 1-3 | ~200 lines | 🟡 低（保留主要测试）|
| 嵌套目录 | 1 | 80KB | 🟢 无风险 |
| **总计** | **4-8** | **~100KB+** | **低** |

---

## ✅ 清理检查清单

### 立即执行（无风险）
- [ ] `rm src/vibesop/core/checkpoint/manager.py.bak`
- [ ] `rm -rf .vibe/.vibe/`
- [ ] `rm tests/hooks/test_installer.py`

### 可选执行（需确认）
- [ ] 删除 `docs/DEEP_REVIEW_REPORT.md`
- [ ] 合并测试文件
- [ ] 更新 README.md
- [ ] 更新 CHANGELOG.md

### 不应执行（保持兼容）
- [ ] ~~删除弃用命令（等 v4.0.0）~~
- [ ] ~~删除弃用模块（等 v4.0.0）~~

---

## 🎯 优先级建议

**P0 (立即)**: 删除备份文件和嵌套目录
**P1 (本周)**: 删除/合并冗余测试
**P2 (本月)**: 更新文档，删除冗余报告文件
**P3 (v4.0.0)**: 移除弃用的命令和模块

---

**生成时间**: 2026-04-05  
**报告状态**: 待审核
