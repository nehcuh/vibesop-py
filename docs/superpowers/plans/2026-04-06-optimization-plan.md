# VibeSOP-Py 优化计划

> **Created**: 2026-04-06
> **Updated**: 2026-04-06 (Qwen 反馈后修正)
> **Status**: Ready to Execute
> **Priority**: P0 > P1 > P2

---

## 执行原则

1. **每次只改一件事** — 单个 PR 只解决一个问题
2. **测试先行** — 修改前确保测试能跑
3. **向后兼容** — v4.x 内不破坏公共 API
4. **文档同步** — 代码改动必须同步更新文档

---

## Task 0: 验证测试基线 (Qwen 建议)

**目的**: 确保在开始任何删除操作前，测试是绿色。

```bash
# 运行完整测试套件
uv run pytest --tb=short -q

# 预期: 所有测试通过
# 如果失败，先修复测试再继续
```

**验证方法**:
- [ ] 所有测试通过
- [ ] 记录当前测试数量作为基线

**风险**: 无（只读操作）

---

## P0 级别（本周完成）

### Task 1: 删除 handlers.py 死代码

**问题**: `handlers.py` 定义了 5 个 Handler 类，但没有任何文件引用它们。

**执行步骤**:

```bash
# 1. 验证无引用
grep -r "AITriageHandler\|ExplicitHandler\|ScenarioHandler\|SemanticHandler\|FuzzyHandler" src/ tests/

# 2. 检查导入
grep -r "from.*handlers import\|import.*handlers" src/ tests/

# 3. 确认后删除
rm src/vibesop/core/routing/handlers.py

# 4. 运行测试
uv run pytest tests/ -x -q
```

**验证方法**:
- [ ] 搜索无任何引用
- [ ] 删除后所有测试通过
- [ ] `vibe route` 命令正常工作

**预期结果**: 代码减少 ~270 行，无功能损失

**风险**: 低（死代码）

---

### Task 2: 清理 semantic.py 重叠代码 (已修正)

**问题**: `routing/semantic.py` 和 `matching/tfidf.py` 都实现 TF-IDF，公式不同。

**事实核查** (Qwen):
- `semantic.py` **无任何引用**
- **无相关测试文件** (`test_semantic_matcher.py` 不存在)

**执行步骤**:

```bash
# 1. 二次确认无引用
grep -r "SemanticMatcher\|from.*semantic" src/ tests/

# 2. 确认 unified.py 使用 TFIDFMatcher
grep -n "TFIDFMatcher" src/vibesop/core/routing/unified.py

# 3. 删除 semantic.py
rm src/vibesop/core/routing/semantic.py

# 4. 更新 __init__.py（如果有导出）
# 编辑 src/vibesop/core/routing/__init__.py

# 5. 运行测试
uv run pytest tests/ -x -q
```

**验证方法**:
- [ ] TF-IDF 只有一个实现 (`matching/tfidf.py`)
- [ ] 所有测试通过
- [ ] 文档中无 semantic.py 引用

**预期结果**: 消除 TF-IDF 重复实现，减少 ~400 行代码

**风险**: 低（已确认无引用）

---

### Task 3: 审查并清理 ai_enhancer.py (新增)

**问题**: `ai_enhancer.py` 在 core/ 下，用于 LLM 增强 skill 建议。需审查是否被使用。

**事实**:
- 文件存在: `src/vibesop/core/ai_enhancer.py` (322 行)
- 功能: 用 LLM 改进 skill 名称、描述、分类

**审查步骤**:

```bash
# 1. 检查是否被引用
grep -r "AIEnhancer\|ai_enhancer\|from.*ai_enhancer" src/ tests/ --include="*.py"

# 2. 检查 session_analyzer 是否依赖它
grep -n "AIEnhancer" src/vibesop/core/session_analyzer.py

# 3. 决策:
#    a. 如果未被使用 → 删除或标记为实验性功能
#    b. 如果被使用 → 评估是否应该在 core/ 中
```

**决策标准**:
| 条件 | 动作 |
|------|------|
| 零引用 | 删除 |
| 被 session_analyzer 使用 | 移到 `core/session/` 或标记为 `experimental/` |

**验证方法**:
- [ ] 确认引用情况
- [ ] 采取相应行动

**预期结果**: 明确 ai_enhancer.py 的定位

**风险**: 低（只读操作）

---

### Task 4: 处理 algorithms/ 零引用问题 (新增)

**问题**: `algorithms/` 包当前零外部引用，需要决定保留还是暂时移除。

**事实** (Qwen):
- `algorithms/interview/ambiguity.py` 存在
- `algorithms/ralph/deslop.py` 存在
- **无任何外部引用**

**审查步骤**:

```bash
# 1. 确认零引用
grep -r "from vibesop.core.algorithms\|from vibesop.algorithms" src/ tests/

# 2. 检查是否有计划使用
grep -r "algorithms" docs/ --include="*.md" | grep -E "ambiguity|deslop"

# 3. 决策:
#    a. 保留作为基础设施 → 在 P2 中补充接口文档
#    b. 暂时移除 → 移到 attic/ 或删除
#    c. Phase 2 需要使用 → 在计划中明确调用方式
```

**推荐方案**: 保留但标记为 `@experimental`

**验证方法**:
- [ ] 确认零引用
- [ ] 决定保留/移除
- [ ] 如保留，添加 `__all__` 和 docstring

**风险**: 低（可选功能）

---

### Task 5: 审查 SkillManager.execute_skill() 越界问题 (新增)

**问题**: `SkillManager.execute_skill()` 越界到技能执行，偏离"路由引擎"定位。

**事实**:
- 方法存在: `skills/manager.py:181`
- CLI 中未使用 (`vibe execute` 命令不存在)

**审查步骤**:

```bash
# 1. 检查是否被使用
grep -r "\.execute_skill\|execute_skill(" src/ tests/ --include="*.py"

# 2. 审查实现
# 它是调用 skill.execute(context)，还是 subprocess？

# 3. 决策:
#    a. 如果未被使用 → 删除
#    b. 如果是 subprocess 启动器 → 移到 CLI commands/，移除 manager
#    c. 如果直接执行 → 删除（违反原则）
```

**推荐方案**:
- 未被使用 → 删除
- 如果未来需要 `vibe execute <skill>` → 在 CLI 层实现，不在 core/

**验证方法**:
- [ ] 确认使用情况
- [ ] 采取相应行动

**预期结果**: 消除越界，明确路由引擎边界

**风险**: 低（可能未被使用）

---

### Task 6: 更新 README.md 版本号

**执行步骤**:

```bash
# 1. 更新版本声明
sed -i '' 's/v3\.0\.0/v4.0.0/g' README.md

# 2. 更新 badge
# 找到 [![Version](https://img.shields.io/badge/Version-3.0.0-green.svg)]
# 改为 4.0.0

# 3. 检查其他文档
grep -r "v3\.0\|v3\.0\.0" docs/ | grep -v ".bak" | grep -v "optimization-plan"

# 4. 验证
cat README.md | grep -E "Version|v[0-9]"
```

**验证方法**:
- [ ] README.md 显示 v4.0.0
- [ ] 所有文档版本一致

**风险**: 低

---

### Task 7: 重构 Phase 2 计划 (已修正)

**问题**: Phase 2 计划范围过大，很多模块已被清理。

**事实** (Qwen):
- `interview/`, `ralph/`, `pipeline/`, `plan/` 等已在 v4.0 清理中删除
- 当前只保留 `algorithms/interview/` 和 `algorithms/ralph/`

**执行步骤**:

```bash
# 1. 检查 git status 中已删除的模块
git status | grep -E "interview|ralph|pipeline|plan" | grep "D"

# 2. 确认当前 algorithms/ 状态
ls -la src/vibesop/core/algorithms/

# 3. 更新 Phase 2 计划文档
# - 移除已删除模块的引用
# - 明确 algorithms/ 的定位（基础设施 vs 实验）
# - 更新 SKILL.md 规划（纯提示词）
```

**新的 Phase 2 范围**:

```
core/algorithms/          # 保留 - 基础设施
├── interview/
│   └── ambiguity.py      # 数学公式，可复用
└── ralph/
    └── deslop.py         # AI slop 检测，可复用

core/skills/omx/          # 新建 - 纯提示词
├── deep-interview/SKILL.md
├── ralph/SKILL.md
└── ralplan/SKILL.md
```

**验证方法**:
- [ ] 计划文档与实际代码一致
- [ ] algorithms/ 定位明确

**预期结果**: Phase 2 计划与 v4.0 状态同步

**风险**: 中（需要重新规划）

---

## P1 级别（本月完成）

### Task 8: 评估 8 层路由管道性能 (已修正)

**问题**: 8 层管道可能过度设计，需要实际数据支撑。

**修正** (Qwen):
- `UnifiedRouter` 没有 `.layers` 公开属性
- 需要从 `RoutingResult.routing_path` 收集数据

**执行步骤**:

```bash
# 1. 创建基准测试文件（修正版）
cat > tests/benchmarks/test_routing_layers.py << 'EOF'
"""路由管道性能基准测试"""
import pytest
import time
from vibesop.core.routing import UnifiedRouter
from vibesop.core.models import RoutingLayer

# 真实查询样本（100+）
QUERY_SAMPLES = [
    "帮我调试这个 bug", "帮我调试", "debug error", "fix bug",
    "扫描安全漏洞", "review code", "部署应用", "创建新功能",
    "重构代码", "optimize", "测试", "test", "review", "refactor",
    # ... 扩展到 100+ 样本
]

@pytest.mark.benchmark
def test_layer_performance():
    """测试每层的命中率和延迟"""
    router = UnifiedRouter()

    # 使用 RoutingLayer 枚举作为 key
    layer_stats = {layer: {"hits": 0, "times": []} for layer in RoutingLayer}

    for query in QUERY_SAMPLES:
        start = time.perf_counter()
        result = router.route(query)
        elapsed = (time.perf_counter() - start) * 1000

        # 从 routing_path 收集数据
        for layer in result.routing_path:
            layer_stats[layer]["hits"] += 1
            layer_stats[layer]["times"].append(elapsed)

    # 分析结果
    total = len(QUERY_SAMPLES)
    for layer, data in layer_stats.items():
        hits = data["hits"]
        hit_rate = hits / total * 100 if total > 0 else 0
        avg_time = sum(data["times"]) / len(data["times"]) if data["times"] else 0
        p95 = sorted(data["times"])[int(len(data["times"]) * 0.95)] if len(data["times"]) > 20 else 0

        print(f"{layer.value}: {hit_rate:.1f}% hit rate, {avg_time:.2f}ms avg, {p95:.2f}ms p95")
EOF

# 2. 运行基准测试
uv run pytest tests/benchmarks/test_routing_layers.py -v -s

# 3. 生成报告
```

**分析维度** (修正后):
| 层级 | 命中率 | P50 延迟 | P95 延迟 | 成本 |
|------|--------|----------|----------|------|
| AI Triage | ?% | ?ms | ?ms | $0.001/次 |
| Explicit | ?% | <1ms | <1ms | $0 |
| Scenario | ?% | <1ms | <1ms | $0 |
| Keyword | ?% | <1ms | <1ms | $0 |
| TF-IDF | ?% | ~5ms | ?ms | $0 |
| Embedding | ?% | ~20ms | ?ms | $0 |
| Levenshtein | ?% | ~10ms | ?ms | $0 |

**决策标准**:
- 如果 AI Triage 命中率 < 20%，考虑禁用
- 如果 Embedding 命中率 < 5%，考虑移除
- 如果 Keyword + TF-IDF 覆盖 > 90%，其他层可选

**验证方法**:
- [ ] 有 100+ 真实查询样本
- [ ] 每层有明确的命中率数据
- [ ] 有优化建议报告

**预期结果**: 数据驱动的管道精简决策

**风险**: 中（需要收集真实数据）

---

### Task 9: 设计技能包健康度监控机制 (已修正)

**问题**: 外部技能包依赖风险，缺少健康监控。

**修正** (Qwen):
- 原计划依赖 GitHub API (`days_since_update`, `open_issues`)
- 这需要 API token，且不适用于所有技能包

**新方案**: 本地健康检查 + 可选的 GitHub 检查

**执行步骤**:

```bash
# 1. 创建健康检查模块（修正版）
cat > src/vibesop/integrations/health_monitor.py << 'EOF'
"""技能包健康度监控 - 本地检查为主"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass
class HealthStatus:
    name: str
    version: str
    install_date: datetime
    health: str  # healthy, warning, critical, unknown
    reasons: list[str]
    has_errors: bool

class SkillHealthMonitor:
    def __init__(self, project_root: Path = Path(".")):
        self.project_root = project_root
        self.skills_dir = project_root / ".config" / "skills"

    def check_local_health(self, skill_pack: str) -> HealthStatus:
        """检查本地技能包健康度（无需 GitHub API）"""
        pack_dir = self.skills_dir / skill_pack

        if not pack_dir.exists():
            return HealthStatus(
                name=skill_pack,
                version="unknown",
                install_date=datetime.now(),
                health="critical",
                reasons=["技能包未安装"],
                has_errors=True,
            )

        reasons = []
        has_errors = False

        # 检查 SKILL.md 文件
        skill_files = list(pack_dir.glob("*/SKILL.md"))
        if not skill_files:
            reasons.append("无 SKILL.md 文件")
            has_errors = True

        # 检查是否有语法错误
        for skill_file in skill_files:
            try:
                skill_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                reasons.append(f"{skill_file.name} 编码错误")
                has_errors = True

        # 判断健康状态
        if has_errors:
            health = "critical"
        elif len(reasons) > 0:
            health = "warning"
        else:
            health = "healthy"

        return HealthStatus(
            name=skill_pack,
            version="unknown",  # 可从 SKILL.md 读取
            install_date=datetime.fromtimestamp(pack_dir.stat().st_mtime),
            health=health,
            reasons=reasons,
            has_errors=has_errors,
        )

    def check_all_local(self) -> dict[str, HealthStatus]:
        """检查所有已安装技能包的本地健康度"""
        if not self.skills_dir.exists():
            return {}

        results = {}
        for pack_dir in self.skills_dir.iterdir():
            if pack_dir.is_dir():
                results[pack_dir.name] = self.check_local_health(pack_dir.name)

        return results
EOF

# 2. 创建 CLI 命令
cat > src/vibesop/cli/commands/health_cmd.py << 'EOF'
"""vibe skills health 命令"""
import typer
from pathlib import Path
from vibesop.integrations.health_monitor import SkillHealthMonitor

app = typer.Typer()

@app.command()
def health(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """显示技能包健康状态"""
    monitor = SkillHealthMonitor(project_root=Path.cwd())
    results = monitor.check_all_local()

    if not results:
        typer.echo("未找到已安装的技能包")
        return

    for name, status in sorted(results.items()):
        emoji = {
            "healthy": "✅",
            "warning": "⚠️",
            "critical": "❌",
            "unknown": "❓",
        }.get(status.health, "❓")

        typer.echo(f"{emoji} {name} - {status.health}")

        if verbose and status.reasons:
            for reason in status.reasons:
                typer.echo(f"  - {reason}")
EOF

# 3. 测试
uv run vibe skills health
uv run vibe skills health --verbose
```

**健康度标准（本地）**:

| 状态 | 条件 |
|------|------|
| healthy ✅ | SKILL.md 存在，无编码错误 |
| warning ⚠️ | 有小问题但不影响使用 |
| critical ❌ | 无 SKILL.md 或编码错误 |

**未来扩展** (可选):
- 添加 GitHub API 检查（需要 token）
- 检查技能包最后更新时间
- 检查已知 issues

**验证方法**:
- [ ] `vibe skills health` 命令正常工作
- [ ] 能检测本地技能包健康度
- [ ] 不依赖 GitHub API

**预期结果**: 用户能了解技能包状态

**风险**: 低（本地检查，无外部依赖）

---

## P2 级别（下季度）

### Task 10: algorithms/ 接口文档

**执行步骤**:
1. 为每个算法添加 docstring
2. 创建 `docs/algorithms.md` 说明调用方式
3. 添加使用示例

### Task 11: 冷启动策略

**执行步骤**:
1. 定义默认路由权重（无历史数据时）
2. 创建内置查询-技能映射表
3. 文档说明冷启动行为

### Task 12: 冲突解决规则重构

**执行步骤**:
1. 分析现有硬编码规则
2. 设计通用冲突解决策略
3. 实现基于优先级/命名空间/时间的自动解决

---

## 执行时间表

| 周 | 任务 | 预计时间 | 状态 |
|----|------|----------|------|
| W1 D1 | Task 0: 验证测试基线 | 15 min | ⏳ |
| W1 D1 | Task 1: 删除 handlers.py | 1 hour | ⏳ |
| W1 D1 | Task 2: 清理 semantic.py | 2 hours | ⏳ |
| W1 D2 | Task 3: 审查 ai_enhancer.py | 1 hour | ⏳ |
| W1 D2 | Task 4: 处理 algorithms/ 零引用 | 1 hour | ⏳ |
| W1 D3 | Task 5: 审查 execute_skill() | 1 hour | ⏳ |
| W1 D3 | Task 6: 更新 README 版本 | 30 min | ⏳ |
| W1 D4 | Task 7: 重构 Phase 2 计划 | 2 hours | ⏳ |
| W2 | Task 8: 路由管道性能评估 | 1 day | ⏳ |
| W3 | Task 9: 健康度监控 | 2 days | ⏳ |
| Q2 | Task 10-12: P2 任务 | - | ⏳ |

---

## 成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 死代码行数 | ~270 (handlers.py) | 0 |
| TF-IDF 实现数 | 2 | 1 |
| 文档版本一致性 | 不一致 | 100% |
| 路由延迟 P95 | 未知 | < 50ms |
| 技能包健康可见性 | 无 | 完全可见 |
| 核心模块零引用模块 | 2-3 | 0 |

---

## Qwen 反馈修正记录

| 问题 | 原计划 | 修正后 |
|------|--------|--------|
| Task 2 未提测试文件 | - | 已确认无测试文件 |
| Task 3 范围过大 | 审查所有执行模块 | 已修正为同步当前状态 |
| Task 5 使用不存在属性 | `router.layers` | 使用 `RoutingLayer` 枚举 |
| Task 6 依赖 GitHub API | `days_since_update`, `open_issues` | 改为本地检查 |
| 遗漏 Task 0 | - | 新增测试基线验证 |
| 遗漏 ai_enhancer.py | - | 新增 Task 3 |
| 遗漏 algorithms/ 零引用 | - | 新增 Task 4 |
| 遗漏 execute_skill() 越界 | - | 新增 Task 5 |

---

*本文档是活文档，随执行进度更新。*
