# 跨平台会话智能路由 - 实现总结

> **日期**: 2026-04-18
> **特性**: 跨平台会话智能路由
> **状态**: ✅ 已实现（实验性）
> **版本**: v4.3.0

## 用户反馈

用户指出："不仅仅是 claude code 哦，我们还适配了 opencode，未来还可能适配其他平台"

这是一个重要的架构考虑。VibeSOP 是一个**跨平台路由引擎**，不应该只针对 Claude Code 实现。

## 架构重新设计

### 问题

初始实现依赖于 Claude Code 的 hooks 系统，这会导致：
- ❌ OpenCode 无法使用（不支持 hooks）
- ❌ 未来平台无法集成
- ❌ 违反平台无关性原则

### 解决方案

创建**平台抽象层**，使会话跟踪功能跨平台：

```python
class SessionTracker(ABC):
    """平台无关的会话跟踪接口"""
    
    @abstractmethod
    def record_tool_use(self, tool_name: str, skill: str | None = None) -> None:
        """记录工具使用"""
        pass
    
    @abstractmethod
    def check_reroute(self, user_message: str) -> RoutingSuggestion:
        """检查是否需要重新路由"""
        pass
```

**两种实现**：

1. **`HookBasedSessionTracker`** - 用于 Claude Code
   - 通过 PreToolUse hook 自动跟踪
   - 无需手动干预
   - 内存状态（仅当前会话）

2. **`GenericSessionTracker`** - 用于 OpenCode 和其他平台
   - 通过 CLI 命令手动跟踪
   - 持久化状态（保存到 ~/.vibesop/session-state.json）
   - 适用于任何平台

### 平台检测

自动检测并选择合适的跟踪器：

```python
def get_tracker(platform: str = "auto") -> SessionTracker:
    """获取适合平台的会话跟踪器"""
    if platform == "auto":
        platform = _detect_platform()
    
    if platform == "claude-code":
        return HookBasedSessionTracker(...)
    else:
        return GenericSessionTracker(...)
```

**检测逻辑**：
- 检测 `CLAUDE_SESSION_FILE` 环境变量或 `~/.claude/` 目录 → Claude Code
- 检测 `~/.opencode/` 目录 → OpenCode
- 其他 → Generic（适用于任何平台）

## 跨平台支持矩阵

| 平台 | 状态 | 自动路由 | Hooks | 会话跟踪 |
|------|------|----------|-------|----------|
| **Claude Code** | ✅ 完整支持 | ✅ 是 | ✅ 是 | ✅ 自动 |
| **OpenCode** | ✅ 基础支持 | ✅ 是 | ❌ 否 | ⚠️ 手动 |
| **Cursor** | 🚧 计划中 | - | - | - |
| **Continue.dev** | 🚧 计划中 | - | - | - |
| **Aider** | 🚧 计划中 | - | - | - |
| **通用** | ✅ 总是可用 | ✅ 是 | ❌ 否 | ⚠️ 手动 |

## 使用方式

### Claude Code（自动）

```bash
# 启用自动跟踪
vibe session enable-tracking
vibe build claude-code  # 安装 hooks

# 一切自动进行
```

**工作原理**：
- PreToolUse hook 在每次工具使用前触发
- 自动记录工具使用
- 定期检查重新路由机会
- 直接向 Claude Code 输出建议

### OpenCode（手动）

```bash
# 手动记录工具使用
vibe session record-tool --tool "read" --skill "systematic-debugging"

# 检查重新路由建议
vibe session check-reroute "设计新架构" --skill "systematic-debugging"
```

**状态持久化**：
- 会话状态保存到 `~/.vibesop/session-state.json`
- 重启后可以恢复
- 跨会话记录工具历史

### 其他平台（手动）

```bash
# 任何平台都可以使用通用跟踪器
vibe session record-tool --tool "read" --skill "systematic-debugging"
vibe session check-reroute "设计新架构" --skill "systematic-debugging"
```

## 新增组件

### 1. `src/vibesop/core/sessions/tracker.py` (410 行)

**平台抽象层**：
- `SessionTracker` - 抽象基类
- `HookBasedSessionTracker` - 基于 hooks 的实现（Claude Code）
- `GenericSessionTracker` - 通用实现（OpenCode、其他）
- `get_tracker()` - 工厂函数，自动检测平台
- `_detect_platform()` - 平台检测

### 2. `src/vibesop/core/sessions/__init__.py` (更新)

**导出新接口**：
```python
from vibesop.core.sessions import (
    SessionTracker,
    GenericSessionTracker,
    HookBasedSessionTracker,
    get_tracker,
)
```

### 3. `tests/core/sessions/test_tracker.py` (219 行)

**19 个测试**，覆盖：
- `GenericSessionTracker` 测试
- `HookBasedSessionTracker` 测试
- 平台检测测试
- 工厂函数测试

**测试结果**: 19/19 通过 ✅

### 4. `docs/architecture/cross-platform-support.md` (新建)

**跨平台架构文档**，包括：
- 平台支持矩阵
- 架构设计
- 适配器模式
- 会话跟踪跨平台实现
- 未来平台路线图

### 5. 更新的文档

- `docs/user/session-intelligent-routing.md`
  - 添加平台特定部分
  - Claude Code 集成
  - OpenCode 集成
  - 通用平台使用
  - 更新限制和未来增强

- `README.md`
  - 更新会话智能路由部分
  - 说明跨平台支持
  - Claude Code 自动 vs OpenCode 手动

## 架构原则

### 核心统一

```python
# 这些在所有平台上工作方式相同
from vibesop.core.routing import UnifiedRouter
from vibesop.core.sessions import get_tracker

router = UnifiedRouter()
tracker = get_tracker()  # 自动检测平台

result = router.route("调试这个错误")  # 所有平台相同
suggestion = tracker.check_reroute("设计新架构")  # 平台适配
```

### 展示层平台特定

```python
# Claude Code
vibe build claude-code  # → CLAUDE.md, rules/, hooks/

# OpenCode
vibe build opencode     # → config.yaml, skills/

# 通用
vibe session record-tool  # 所有平台可用
vibe session check-reroute  # 所有平台可用
```

## 未来平台集成

### 如何添加新平台

1. **创建适配器**
```python
class NewPlatformAdapter(PlatformAdapter):
    def platform_name(self) -> str:
        return "new-platform"
    
    def render_config(self, manifest, output_dir):
        # 生成平台特定配置
        pass
```

2. **添加 hooks 支持**（如果平台支持）
```python
HOOK_DEFINITIONS = {
    "new-platform": {
        "pre-tool-use": {
            "file": "hooks/pre-tool-use.sh",
            "executable": True,
        },
    },
}
```

3. **更新 `get_tracker()`**
```python
if platform == "new-platform" and has_hooks:
    return HookBasedSessionTracker(...)
else:
    return GenericSessionTracker(...)
```

### 平台路线图

**Phase 1: 当前平台** (v4.3.0) ✅
- ✅ Claude Code - 完整支持 + hooks
- ✅ OpenCode - 基础支持，手动跟踪

**Phase 2: 增强 OpenCode** (v4.4.0)
- [ ] OpenCode 添加 hooks 支持
- [ ] OpenCode 自动会话跟踪
- [ ] OpenCode 特定优化

**Phase 3: 新平台** (v4.5.0+)
- [ ] Cursor 支持
- [ ] Continue.dev 支持
- [ ] Aider 支持
- [ ] 平台特定 UI 集成

## 关键改进

### 之前（仅 Claude Code）

```python
# 只能用于 Claude Code
tracker = SessionContext()  # 依赖 hooks
```

### 现在（跨平台）

```python
# 自动检测平台
tracker = get_tracker()  # Claude Code → HookBasedSessionTracker
                         # OpenCode → GenericSessionTracker
                         # 其他 → GenericSessionTracker

# 或明确指定
tracker = get_tracker(platform="claude-code")
tracker = get_tracker(platform="opencode")
tracker = get_tracker(platform="generic")
```

## 测试覆盖

```
tests/core/sessions/
├── test_context.py (18 个测试) ✅
│   ├── ToolUseEvent 测试
│   ├── SessionContext 测试
│   ├── ContextChange 检测测试
│   └── 集成场景测试
└── test_tracker.py (19 个测试) ✅
    ├── GenericSessionTracker 测试
    ├── HookBasedSessionTracker 测试
    ├── 平台检测测试
    └── 工厂函数测试

总计: 37 个测试全部通过 ✅
```

## 文件清单

### 新增文件 (4)
1. `src/vibesop/core/sessions/tracker.py` - 平台抽象层
2. `tests/core/sessions/test_tracker.py` - 跟踪器测试
3. `docs/architecture/cross-platform-support.md` - 跨平台架构文档
4. `docs/superpowers/summaries/2026-04-18-cross-platform-routing.md` - 本总结

### 修改文件 (3)
1. `src/vibesop/core/sessions/__init__.py` - 添加平台抽象导出
2. `docs/user/session-intelligent-routing.md` - 添加跨平台使用说明
3. `README.md` - 更新会话智能路由部分

## 总结

通过创建平台抽象层，VibeSOP 的会话智能路由功能现在：

✅ **支持 Claude Code** - 自动 hooks 集成
✅ **支持 OpenCode** - 手动 CLI 集成
✅ **支持任何平台** - 通用跟踪器
✅ **可扩展** - 易于添加新平台
✅ **经过测试** - 37 个测试全部通过
✅ **文档完善** - 跨平台架构文档

这确保了 VibeSOP 作为**跨平台路由引擎**的定位，而不是某个特定平台的工具。

---

**实现完成**: 所有组件实现、测试通过（37/37）、文档完善
**准备就绪**: 跨平台使用
**状态**: 实验性 - API 可能根据使用反馈调整
