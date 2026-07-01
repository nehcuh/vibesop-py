# 智谱优化工作 — 第三轮评审报告

**评审范围**: commits `d970b19` ~ `f7e328c`（5 commits）  
**基线**: commit `d970b19`（ruff 0 / pyright 7 / 全量测试通过）  
**评审日期**: 2026-05-03

---

## 一、执行摘要

本轮优化聚焦三个主题：
1. **拆分 god module**：`skills_commands.py`（1870 行）→ 6 个子模块
2. **消除 facade**：`core/services/__init__.py` 内联到 `slash_commands.py`
3. **依赖倒置**：打破 `core → llm` 和 `core → security` 的依赖

**总体评价**: 架构方向正确，但依赖倒置实现不完整，引入了**运行时崩溃级 bug**。34 个测试失败，核心路由功能在非 CLI 场景下不可用。

---

## 二、分维度评审

### 2.1 架构设计 ⭐⭐⭐⭐☆ (4/5)

**做得好的地方**

| 改动 | 评价 |
|------|------|
| **skills_commands 拆分** | 优秀。将 1870 行的 god module 拆分为 6 个职责清晰的子模块（`_crud.py`, `_listing.py`, `_discovery.py`, `_config.py`, `_health.py`, `_quality.py`），每个 200-400 行，符合单一职责原则。 |
| **core/services facade 消除** | 合理。原 `services/__init__.py`（212 行）只是一个 thin facade，内联到消费者（`slash_commands.py`）后减少了不必要的抽象层。 |
| **cost_tracker 迁移** | 合理。将 `llm/cost_tracker.py` 的核心逻辑迁移到 `core/routing/cost_tracker.py`，原文件变为 backward-compatible re-export。切断了 `core → llm` 的一条依赖路径。 |
| **Protocols 抽象** | 良好。新增 `core/protocols.py` 定义 `LLMProvider`、`SkillAuditor`、`PathValidator` 三个协议，为依赖倒置提供了契约层。 |

**问题**

| 改动 | 问题 |
|------|------|
| **依赖倒置实现不完整** | `ExternalSkillLoader` 和 `SkillStorage` 用工厂模式替换了直接导入，但工厂注册被放在了 `cli/main.py` 的 `_wire_defaults()` 中。这意味着**非 CLI 场景下（测试、库直接调用、第三方集成）工厂从未注册**，`_auditor` 和 `_path_safety` 为 `None`，触发 `AttributeError`。 |

### 2.2 代码质量 ⭐⭐☆☆☆ (2/5)

**量化退化**

| 指标 | 基线 (d970b19) | 当前 (f7e328c) | 变化 |
|------|---------------|----------------|------|
| ruff src | 0 | 0 | 持平 ✅ |
| basedpyright errors | 7 | 13 | **+6** ❌ |
| routing tests | 458 passed | 424 passed, **34 failed** | **-34** ❌ |
| unit tests | ~390 passed | 382 passed, 4 failed | **-4** ❌ |
| integration tests | 4 passed | 4 passed | 持平 ✅ |

**新增 basedpyright 错误（6 个）**

| # | 文件 | 错误 | 原因 |
|---|------|------|------|
| 1 | `core/skills/external_loader.py:105` | `_DEFAULT_AUDITOR_FACTORY` constant redefinition | pyright 将大写 ClassVar 视为常量，setter 方法对其重新赋值触发报错 |
| 2 | `core/skills/storage.py:108` | `_DEFAULT_PATH_SAFETY` constant redefinition | 同上 |
| 3 | `cli/commands/skills_commands/__init__.py:65` | `SkillManager` unused import | 拆分后遗留的死 import |
| 4 | `cli/commands/skills_commands/__init__.py:65` | `SkillStorage` unused import | 同上 |
| 5 | `llm/cost_tracker.py:7` | `TriageCallRecord` unused import | re-export 文件带入了死 import |
| 6 | `llm/cost_tracker.py:8` | `TriageCostTracker` unused import | 同上 |

**未修复的遗留错误（3 个）**

- Adapter `_render_skill_content` override 签名不兼容（×3）—— 从第二轮遗留至今

### 2.3 实现逻辑 ⭐⭐☆☆☆ (2/5)

**🚨 严重 bug：运行时崩溃**

```python
# 复现步骤（任何非 CLI 场景）
from vibesop.core.skills.external_loader import ExternalSkillLoader
loader = ExternalSkillLoader()
loader.discover_all()  # AttributeError: 'NoneType' object has no attribute 'audit_skill_file'
```

**根因分析**

```python
# external_loader.py __init__
if auditor is not None:
    self._auditor = auditor
elif type(self)._DEFAULT_AUDITOR_FACTORY is not None:
    self._auditor = type(self)._DEFAULT_AUDITOR_FACTORY(...)
else:
    self._auditor = None  # ← 非 CLI 场景永远走到这里
```

工厂注册仅在 `cli/main.py` 的 `_wire_defaults()` 中完成：

```python
def _wire_defaults():
    from vibesop.security import SkillSecurityAuditor
    ExternalSkillLoader.set_default_auditor_factory(
        lambda strict, root: SkillSecurityAuditor(strict_mode=strict, project_root=root),
    )
```

但 `_wire_defaults()` 只在 CLI 启动时调用。任何直接实例化 `ExternalSkillLoader` 的代码（测试、第三方库、Jupyter notebook）都会得到 `_auditor = None`。

**影响范围**

- 34 个路由测试失败（所有触发技能发现的路径）
- `UnifiedRouter` 在非 CLI 场景下不可用
- `DynamicSkillDiscovery` 在非 CLI 场景下不可用

**修复方案（三选一）**

**方案 A（推荐）：延迟初始化 + 优雅降级**
```python
def _parse_and_audit(self, ...):
    if self._auditor is None:
        # 尝试懒加载默认 auditor
        try:
            from vibesop.security import SkillSecurityAuditor
            self._auditor = SkillSecurityAuditor(...)
        except ImportError:
            pass  # 安全模块可选
    
    if self._auditor is not None:
        audit_result = self._auditor.audit_skill_file(skill_file)
        # ...
    else:
        # 无 auditor 时跳过安全检查
        return self._parse_skill_file(skill_file)
```

**方案 B：自动注册**
在 `external_loader.py` 模块加载时自动尝试注册工厂：
```python
try:
    from vibesop.security import SkillSecurityAuditor
    ExternalSkillLoader.set_default_auditor_factory(
        lambda strict, root: SkillSecurityAuditor(strict_mode=strict, project_root=root),
    )
except ImportError:
    pass
```

**方案 C：构造时必填**
将 `auditor` 设为 `__init__` 的必填参数，强制调用方提供。但这会破坏现有 API 兼容性。

---

## 三、测试状态

### 失败的测试（34 个）

| 测试文件 | 失败数 | 根因 |
|---------|--------|------|
| `tests/core/routing/test_unified_router_branches.py` | 14 | `_auditor` is None |
| `tests/unit/core/routing/test_transparency.py` | 3 | `_auditor` is None |
| `tests/unit/core/routing/` 其他 | 17 | `_auditor` is None |

**所有失败共享同一个堆栈**：
```
candidate_manager._cached_reload_locked
→ skill_loader.discover_all()
→ external_loader.discover_all()
→ external_loader._parse_and_audit()
→ self._auditor.audit_skill_file()  # AttributeError
```

### 通过的测试

- 集成测试 `test_skill_add_flow.py`（4 passed）—— 这些测试显式导入并执行了 CLI 初始化路径
- 单元测试 `test_dynamic_discovery.py`（13 passed）—— 使用了 mock 的 ExternalSkillLoader
- 我补充的路由模块单元测试（299 passed）—— 未触发技能发现路径

---

## 四、关键发现汇总

### 4.1 阻塞性问题（必须修复）

| # | 问题 | 严重性 | 文件 |
|---|------|--------|------|
| 1 | `_auditor` 为 None 导致运行时崩溃 | **🔴 P0** | `core/skills/external_loader.py` |
| 2 | `_path_safety` 为 None 可能导致同类崩溃 | **🟡 P1** | `core/skills/storage.py` |

### 4.2 高优先级问题

| # | 问题 | 修复工作量 |
|---|------|-----------|
| 3 | `_DEFAULT_AUDITOR_FACTORY` 常量重定义 pyright 错误 | 改为小写 `_default_auditor_factory` |
| 4 | `_DEFAULT_PATH_SAFETY` 常量重定义 pyright 错误 | 同上 |
| 5 | `skills_commands/__init__.py` 死 import ×2 | 删除 2 行 |
| 6 | `llm/cost_tracker.py` 死 import ×2 | 删除 2 行 |

### 4.3 中优先级（遗留问题）

| # | 问题 | 说明 |
|---|------|------|
| 7 | Adapter override 签名不兼容 ×3 | 第二轮遗留，不影响运行时，但类型检查不通过。（2026-07 更新：Phase 1 已修复 `_render_skill_content` 的 2 处 override——签名对齐 base；`_render_extension` 为有意设计保留 ignore） |

---

## 五、与第二轮的对比

| 维度 | 第二轮 (d970b19) | 第三轮 (f7e328c) | 评价 |
|------|-----------------|-----------------|------|
| ruff | 0 | 0 | ✅ 保持 |
| basedpyright | 7 | 13 | ❌ +6 新增 |
| routing tests | 458 passed | 424 passed, 34 failed | ❌ 严重退化 |
| unit tests | ~390 passed | 382 passed, 4 failed | ❌ 轻度退化 |
| 代码行数 | ~56k | ~56k | 持平 |
| 模块结构 | skills_commands 单文件 | skills_commands 子包 | ✅ 改进 |
| 依赖方向 | core → llm/security | core ← protocols | ✅ 架构改进 |

---

## 六、结论与建议

### 总体结论

本轮优化在**架构层面有实质性进步**（god module 拆分、facade 消除、依赖倒置），但**依赖倒置的实现方式有致命缺陷**——将工厂注册藏在 CLI 初始化路径中，导致库的核心功能在非 CLI 场景下完全不可用。

这是一个经典的"依赖注入但未完成"反模式：提取了接口，但没有提供默认实现或懒加载机制。

### 行动建议

**立即执行（P0，阻塞）**：
1. **修复 `_auditor` None 崩溃**：在 `external_loader.py` 的 `_parse_and_audit` 中添加 `None` 检查，并尝试懒加载默认 `SkillSecurityAuditor`
2. **检查 `_path_safety` 同类问题**：`storage.py` 是否有相同的 `None` 崩溃风险
3. **运行全量测试验证**：`pytest tests/`

**本周执行（P1）**：
4. 重命名 `_DEFAULT_AUDITOR_FACTORY` → `_default_auditor_factory`（修复 pyright 报错）
5. 重命名 `_DEFAULT_PATH_SAFETY` → `_default_path_safety`
6. 清理死 import（skills_commands/__init__.py、llm/cost_tracker.py）

**本月执行（P2）**：
7. 修复 Adapter override 签名不兼容（3 处）
8. 为 `skills_commands/` 子包补充单元测试

### 评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | 4/5 | 拆分和依赖倒置方向正确 |
| 代码质量 | 2/5 | 引入了运行时崩溃和类型错误 |
| 实现逻辑 | 2/5 | 依赖注入未完成，破坏了非 CLI 场景 |
| 测试覆盖 | 1/5 | 34 个测试失败，核心功能不可用 |
| **综合** | **2.3/5** | **架构进步被实现缺陷严重拖累** |

---

*评审完成。关键问题：外部加载器的 auditor 注入未完成，导致非 CLI 场景下所有技能发现路径崩溃。*
