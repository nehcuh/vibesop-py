# VibeSOP-Py v2.0 优化路线图

> **基于与 Oh-My-Codex 的深度对比分析**
> **制定日期**: 2026-04-04
> **当前版本**: 1.0.0 (263+ tests, 6 phases complete)
> **目标版本**: 2.0.0 (Workflow Orchestration Edition)

---

## 📋 执行摘要

### 🎯 核心目标

将 VibeSOP-Py 从 **配置管理框架** 升级为 **完整的工作流编排引擎**，同时保持其在类型安全、安全扫描和模块化设计方面的核心优势。

### 📊 战略定位

```
当前 (v1.0):              目标 (v2.0):
┌─────────────┐          ┌─────────────┐
│  基础设施层  │    →     │  编排引擎层  │
│             │          │             │
│ • 配置生成   │          │ • 配置生成   │
│ • 安全扫描   │          │ • 安全扫描   │
│ • 技能路由   │          │ • 工作流编排 │
│ • Hook系统   │          │ • 状态管理   │
│             │          │ • 多代理协作 │
└─────────────┘          └─────────────┘
```

### 🚀 关键成果

1. **工作流编排引擎**: 支持预定义的工作流管道
2. **智能关键词触发**: 自动技能激活系统
3. **状态持久化**: 完整的会话状态管理
4. **运行时契约**: VIBE_OPERATIONS.md 规范
5. **渐进式多代理**: 从单代理到多代理的平滑演进

---

## 🎯 基于 OMX 对比的改进点

### ✨ 保留的核心优势

| 优势 | 价值 | 保持方式 |
|------|------|----------|
| **严格类型安全** | 运行时验证 + IDE支持 | 继续使用 Pydantic v2 + Pyright |
| **模块化安全扫描** | 45+ patterns, 5种威胁类型 | 保留并扩展 threat detection |
| **原子文件操作** | 防止配置损坏 | 保持 atomic writes |
| **高测试覆盖** | 263+ tests, 85%+ coverage | 目标: 400+ tests, 90%+ coverage |
| **跨平台能力** | Python生态优势 | 继续支持多平台 |

### 🆕 吸收的 OMX 优势

| OMX 优势 | 实现方式 | 优先级 |
|----------|----------|--------|
| **结构化工作流** | WorkflowPipeline 类 | P0 |
| **关键词触发** | KeywordTrigger 系统 | P0 |
| **状态持久化** | StateManager + .vibe/ | P0 |
| **运行时契约** | VIBE_OPERATIONS.md | P1 |
| **验证循环** | VerificationLoop | P1 |
| **会话管理** | SessionManager | P1 |

---

## 🗓️ 分阶段实施计划

### 📅 Phase 1: 工作流编排引擎 (P0, 3周)

**目标**: 实现核心工作流管道系统

#### 1.1 WorkflowPipeline 基础框架 (1周)

**文件结构**:
```
src/vibesop/workflow/
├── __init__.py
├── pipeline.py          # WorkflowPipeline, PipelineStage
├── stages/              # 预定义阶段
│   ├── __init__.py
│   ├── clarify.py       # 澄清阶段
│   ├── plan.py          # 计划阶段
│   ├── execute.py       # 执行阶段
│   └── verify.py        # 验证阶段
└── exceptions.py        # WorkflowError, StageError
```

**核心接口**:
```python
from pydantic import BaseModel, Field
from typing import Protocol, Callable, Any
from enum import Enum

class StageStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class PipelineStage(BaseModel):
    """工作流阶段"""
    name: str = Field(..., min_length=1)
    description: str
    status: StageStatus = StageStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    handler: Callable[..., Any] | None = None
    required: bool = True

    class Config:
        frozen = True  # 不可变，保证线程安全

class WorkflowPipeline(BaseModel):
    """工作流管道"""
    name: str
    description: str
    stages: dict[str, PipelineStage]
    context: dict[str, Any] = Field(default_factory=dict)
    current_stage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_stage(self, stage: PipelineStage) -> None:
        """添加阶段"""

    def execute(self, initial_context: dict[str, Any]) -> WorkflowResult:
        """执行工作流"""

    def get_next_stage(self) -> PipelineStage | None:
        """获取下一个待执行阶段"""

    def skip_stage(self, stage_name: str, reason: str) -> None:
        """跳过阶段"""

    def retry_stage(self, stage_name: str) -> None:
        """重试失败阶段"""

class WorkflowResult(BaseModel):
    """工作流执行结果"""
    success: bool
    completed_stages: list[str]
    failed_stages: list[str]
    skipped_stages: list[str]
    final_context: dict[str, Any]
    execution_time: float
    errors: list[str] = Field(default_factory=list)
```

**预定义工作流**:
```python
# src/vibesop/workflow/pipelines.py
WORKFLOW_PIPELINES = {
    "security-review": WorkflowPipeline(
        name="security-review",
        description="安全审查工作流",
        stages={
            "scan": PipelineStage(
                name="scan",
                description="扫描输入内容",
                handler=security_scan_handler
            ),
            "analyze": PipelineStage(
                name="analyze",
                description="分析威胁类型",
                dependencies=["scan"],
                handler=analyze_threats_handler
            ),
            "report": PipelineStage(
                name="report",
                description="生成安全报告",
                dependencies=["analyze"],
                handler=generate_report_handler
            )
        }
    ),

    "config-deploy": WorkflowPipeline(
        name="config-deploy",
        description="配置部署工作流",
        stages={
            "validate": PipelineStage(
                name="validate",
                description="验证配置清单",
                handler=validate_manifest_handler
            ),
            "render": PipelineStage(
                name="render",
                description="渲染配置文件",
                dependencies=["validate"],
                handler=render_config_handler
            ),
            "install": PipelineStage(
                name="install",
                description="安装配置",
                dependencies=["render"],
                handler=install_config_handler
            ),
            "verify": PipelineStage(
                name="verify",
                description="验证安装",
                dependencies=["install"],
                handler=verify_installation_handler
            )
        }
    ),

    "skill-discovery": WorkflowPipeline(
        name="skill-discovery",
        description="技能发现工作流",
        stages={
            "detect": PipelineStage(
                name="detect",
                description="检测集成",
                handler=detect_integrations_handler
            ),
            "catalog": PipelineStage(
                name="catalog",
                description="编目技能",
                dependencies=["detect"],
                handler=catalog_skills_handler
            ),
            "route": PipelineStage(
                name="route",
                description="路由请求",
                dependencies=["catalog"],
                handler=route_request_handler
            )
        }
    )
}
```

**CLI 集成**:
```python
# src/vibesop/cli/main.py
@app.command()
def workflow(
    pipeline_name: str = Argument(..., help="工作流名称"),
    context_file: Path | None = Option(None, "--context", "-c", help="上下文文件"),
    dry_run: bool = Option(False, "--dry-run", help="仅显示执行计划"),
    verbose: bool = Option(False, "--verbose", "-v", help="详细输出")
) -> None:
    """执行预定义工作流"""
    if pipeline_name not in WORKFLOW_PIPELINES:
        raise typer.Exit(f"未知的工作流: {pipeline_name}")

    pipeline = WORKFLOW_PIPELINES[pipeline_name]

    if dry_run:
        print_pipeline_plan(pipeline)
        return

    # 加载上下文
    context = load_context(context_file) if context_file else {}

    # 执行工作流
    result = pipeline.execute(context)

    # 显示结果
    print_workflow_result(result)
```

#### 1.2 工作流状态管理 (1周)

**文件结构**:
```
src/vibesop/workflow/
├── state.py             # WorkflowStateManager
└── storage/             # 状态存储
    ├── __init__.py
    ├── memory.py        # MemoryStorage
    ├── file.py          # FileStorage
    └── base.py          # StorageBackend (ABC)
```

**核心接口**:
```python
from pydantic import BaseModel, Field
from typing import Protocol
from datetime import datetime

class WorkflowState(BaseModel):
    """工作流状态"""
    workflow_name: str
    workflow_id: str = Field(default_factory=lambda: generate_id())
    current_stage: str | None = None
    stage_states: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class StorageBackend(Protocol):
    """存储后端协议"""

    def save(self, state: WorkflowState) -> None:
        """保存状态"""

    def load(self, workflow_id: str) -> WorkflowState | None:
        """加载状态"""

    def list_workflows(self) -> list[WorkflowState]:
        """列出所有工作流状态"""

    def delete(self, workflow_id: str) -> bool:
        """删除状态"""

class WorkflowStateManager:
    """工作流状态管理器"""

    def __init__(self, backend: StorageBackend):
        self.backend = backend

    def create_state(
        self,
        workflow_name: str,
        initial_context: dict[str, Any]
    ) -> WorkflowState:
        """创建新状态"""

    def update_stage(
        self,
        workflow_id: str,
        stage_name: str,
        stage_state: dict[str, Any]
    ) -> None:
        """更新阶段状态"""

    def complete_workflow(self, workflow_id: str) -> None:
        """完成工作流"""

    def fail_workflow(self, workflow_id: str, error: str) -> None:
        """失败工作流"""

    def get_active_workflows(self) -> list[WorkflowState]:
        """获取活动工作流"""
```

**状态存储目录结构**:
```
.vibe/
├── state/
│   ├── workflows/
│   │   ├── {workflow_id}.json
│   │   └── .gitkeep
│   └── sessions/
│       ├── {session_id}.json
│       └── .gitkeep
├── cache/
│   ├── skill_registry.json
│   └── routing_cache.json
└── logs/
    ├── workflow.log
    └── state.log
```

#### 1.3 工作流恢复和重试 (1周)

**核心功能**:
```python
class WorkflowRecoveryManager:
    """工作流恢复管理器"""

    def recover(self, workflow_id: str) -> WorkflowPipeline:
        """恢复中断的工作流"""

    def retry_from_stage(
        self,
        workflow_id: str,
        stage_name: str
    ) -> WorkflowResult:
        """从指定阶段重试"""

    def resume(self, workflow_id: str) -> WorkflowResult:
        """继续执行工作流"""

    def abort(self, workflow_id: str, reason: str) -> None:
        """中止工作流"""
```

**测试覆盖**:
```python
# tests/workflow/test_pipeline.py
def test_simple_workflow_execution():
    """测试简单工作流执行"""

def test_workflow_with_dependencies():
    """测试带依赖关系的工作流"""

def test_workflow_failure_handling():
    """测试工作流失败处理"""

def test_workflow_skip_stage():
    """测试跳过阶段"""

def test_workflow_retry():
    """测试工作流重试"""

def test_workflow_state_persistence():
    """测试状态持久化"""

def test_workflow_recovery():
    """测试工作流恢复"""
```

---

### 📅 Phase 2: 智能关键词触发系统 (P0, 2周)

**目标**: 实现自动技能激活，类似 OMX 的关键词检测

#### 2.1 KeywordTrigger 核心系统 (1周)

**文件结构**:
```
src/vibesop/triggers/
├── __init__.py
├── detector.py           # KeywordDetector
├── patterns.py           # 关键词模式定义
├── mapper.py             # KeywordToSkillMapper
└── exceptions.py         # TriggerError
```

**核心接口**:
```python
from pydantic import BaseModel, Field
from typing import Literal
import re

class TriggerPattern(BaseModel):
    """触发模式"""
    keywords: list[str] = Field(..., min_length=1)
    skill_id: str
    priority: int = Field(default=0, ge=0, le=100)
    case_sensitive: bool = False
    match_mode: Literal["contains", "exact", "regex"] = "contains"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class TriggerMatch(BaseModel):
    """触发匹配结果"""
    pattern: TriggerPattern
    matched_text: str
    confidence: float
    position: tuple[int, int] | None = None  # (start, end)

class KeywordDetector(BaseModel):
    """关键词检测器"""
    patterns: list[TriggerPattern] = Field(default_factory=list)

    def add_pattern(self, pattern: TriggerPattern) -> None:
        """添加触发模式"""

    def detect(self, text: str) -> list[TriggerMatch]:
        """检测关键词并返回所有匹配"""

    def detect_best(self, text: str) -> TriggerMatch | None:
        """检测并返回最佳匹配（按优先级和置信度）"""

    def remove_pattern(self, skill_id: str) -> bool:
        """移除技能的所有模式"""

class KeywordToSkillMapper(BaseModel):
    """关键词到技能映射器"""
    detector: KeywordDetector
    fallback_skill: str | None = None

    def map_to_skill(self, text: str) -> str | None:
        """将文本映射到技能"""

    def get_trigger_confidence(self, text: str, skill_id: str) -> float:
        """获取触发置信度"""
```

**预定义关键词模式**:
```python
# src/vibesop/triggers/patterns.py
DEFAULT_TRIGGER_PATTERNS = [
    # 安全相关
    TriggerPattern(
        keywords=["scan", "security", "threat", "injection", "malicious"],
        skill_id="/security/scan",
        priority=80,
        confidence=0.85
    ),
    TriggerPattern(
        keywords=["check safety", "validate security", "audit security"],
        skill_id="/security/audit",
        priority=85,
        confidence=0.90
    ),

    # 配置相关
    TriggerPattern(
        keywords=["setup", "configure", "install", "init", "bootstrap"],
        skill_id="/config/setup",
        priority=70,
        confidence=0.80
    ),
    TriggerPattern(
        keywords=["render config", "generate config", "build config"],
        skill_id="/config/render",
        priority=75,
        confidence=0.85
    ),
    TriggerPattern(
        keywords=["deploy config", "apply config"],
        skill_id="/config/deploy",
        priority=75,
        confidence=0.85
    ),

    # 路由相关
    TriggerPattern(
        keywords=["help", "which skill", "best approach", "how to"],
        skill_id="/route/query",
        priority=60,
        confidence=0.75
    ),
    TriggerPattern(
        keywords=["find skill", "search skill", "discover skill"],
        skill_id="/skills/discover",
        priority=65,
        confidence=0.80
    ),

    # 诊断相关
    TriggerPattern(
        keywords=["doctor", "check", "diagnose", "health check"],
        skill_id="/system/doctor",
        priority=70,
        confidence=0.80
    ),
    TriggerPattern(
        keywords=["verify", "validate", "check installation"],
        skill_id="/system/verify",
        priority=70,
        confidence=0.80
    ),

    # 工作流相关
    TriggerPattern(
        keywords=["workflow", "pipeline", "orchestrate"],
        skill_id="/workflow/list",
        priority=60,
        confidence=0.75
    ),
    TriggerPattern(
        keywords=["resume", "recover", "continue"],
        skill_id="/workflow/resume",
        priority=65,
        confidence=0.75
    ),
    TriggerPattern(
        keywords=["abort", "cancel", "stop workflow"],
        skill_id="/workflow/abort",
        priority=70,
        confidence=0.85
    ),
]
```

#### 2.2 CLI 集成和自动触发 (1周)

**增强的 CLI**:
```python
# src/vibesop/cli/main.py
@app.command()
def auto(
    query: str = Argument(..., help="自然语言查询"),
    dry_run: bool = Option(False, "--dry-run", help="仅显示匹配结果"),
    force: bool = Option(False, "--force", help="强制执行，无需确认")
) -> None:
    """自动检测并执行合适的技能/工作流"""
    detector = KeywordDetector(patterns=DEFAULT_TRIGGER_PATTERNS)
    mapper = KeywordToSkillMapper(detector=detector)

    # 检测最佳匹配
    best_match = detector.detect_best(query)

    if best_match:
        console.print(
            f"[green]✓[/green] 匹配到技能: "
            f"[bold cyan]{best_match.pattern.skill_id}[/bold cyan] "
            f"(置信度: {best_match.confidence:.0%})"
        )

        if dry_run:
            return

        if not force:
            confirm = typer.confirm("是否执行此技能?")
            if not confirm:
                raise typer.Exit("已取消")

        # 执行技能
        execute_skill(best_match.pattern.skill_id, query)
    else:
        console.print("[yellow]⚠[/yellow] 未找到匹配的技能")
        console.print("使用 [cyan]vibe route[/cyan] 查看可用技能")
        raise typer.Exit(code=1)
```

**测试覆盖**:
```python
# tests/triggers/test_detector.py
def test_single_keyword_detection():
    """测试单个关键词检测"""

def test_multiple_keywords_detection():
    """测试多个关键词检测"""

def test_priority_selection():
    """测试优先级选择"""

def test_case_insensitive_matching():
    """测试不区分大小写匹配"""

def test_regex_pattern_matching():
    """测试正则表达式匹配"""

def test_no_match_returns_none():
    """测试无匹配返回None"""

def test_confidence_calculation():
    """测试置信度计算"""
```

---

### 📅 Phase 3: 状态持久化和会话管理 (P0, 2周)

**目标**: 实现类似 `.omx/` 的状态管理系统

#### 3.1 StateManager 和存储层 (1周)

**文件结构**:
```
src/vibesop/state/
├── __init__.py
├── manager.py            # StateManager
├── models.py             # 状态数据模型
├── storage/              # 存储后端
│   ├── __init__.py
│   ├── base.py           # StorageBackend (ABC)
│   ├── file.py           # FileSystemStorage
│   ├── memory.py         # MemoryStorage
│   └── git.py            # GitStorage (可选)
└── serializers.py        # 序列化器
```

**核心接口**:
```python
from pydantic import BaseModel, Field
from typing import Any, TypeVar, Generic
from datetime import datetime
from enum import Enum

class StateScope(str, Enum):
    """状态作用域"""
    SESSION = "session"
    WORKFLOW = "workflow"
    GLOBAL = "global"
    TEMPORARY = "temporary"

class StateEntry(BaseModel):
    """状态条目"""
    key: str
    value: Any
    scope: StateScope
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    ttl: int | None = None  # Time to live in seconds
    metadata: dict[str, Any] = Field(default_factory=dict)

class StateManager(BaseModel):
    """状态管理器"""
    storage: StorageBackend
    default_scope: StateScope = StateScope.SESSION

    def get(self, key: str, scope: StateScope | None = None) -> Any:
        """获取状态值"""

    def set(
        self,
        key: str,
        value: Any,
        scope: StateScope | None = None,
        ttl: int | None = None
    ) -> None:
        """设置状态值"""

    def delete(self, key: str, scope: StateScope | None = None) -> bool:
        """删除状态值"""

    def exists(self, key: str, scope: StateScope | None = None) -> bool:
        """检查状态是否存在"""

    def list_keys(self, scope: StateScope | None = None) -> list[str]:
        """列出所有键"""

    def clear_scope(self, scope: StateScope) -> int:
        """清除作用域中的所有状态"""

    def export_state(self, scope: StateScope | None = None) -> dict[str, Any]:
        """导出状态"""

    def import_state(
        self,
        state: dict[str, Any],
        scope: StateScope | None = None
    ) -> None:
        """导入状态"""
```

**文件系统存储实现**:
```python
class FileSystemStorage(StorageBackend):
    """文件系统存储"""

    def __init__(
        self,
        base_dir: Path,
        create_dirs: bool = True
    ):
        self.base_dir = base_dir.expanduser().resolve()
        if create_dirs:
            self.base_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        for scope in StateScope:
            (self.base_dir / scope.value).mkdir(exist_ok=True)

    def _get_path(self, key: str, scope: StateScope) -> Path:
        """获取状态文件路径"""
        safe_key = sanitize_key(key)
        return self.base_dir / scope.value / f"{safe_key}.json"

    def save(self, entry: StateEntry) -> None:
        """保存状态条目"""
        path = self._get_path(entry.key, entry.scope)
        atomic_write(path, entry.model_dump_json(indent=2))

    def load(self, key: str, scope: StateScope) -> StateEntry | None:
        """加载状态条目"""
        path = self._get_path(key, scope)
        if not path.exists():
            return None
        return StateEntry.model_validate_json(path.read_text())

    def delete(self, key: str, scope: StateScope) -> bool:
        """删除状态条目"""
        path = self._get_path(key, scope)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_keys(self, scope: StateScope) -> list[str]:
        """列出作用域中的所有键"""
        scope_dir = self.base_dir / scope.value
        if not scope_dir.exists():
            return []
        return [
            f.stem for f in scope_dir.glob("*.json")
            if f.is_file()
        ]
```

#### 3.2 SessionManager (1周)

**文件结构**:
```
src/vibesop/session/
├── __init__.py
├── manager.py            # SessionManager
├── models.py             # Session, SessionContext
└── history.py            # SessionHistory
```

**核心接口**:
```python
class SessionContext(BaseModel):
    """会话上下文"""
    session_id: str
    started_at: datetime
    last_activity: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    user_inputs: list[str] = Field(default_factory=list)
    executed_skills: list[str] = Field(default_factory=list)
    workflow_history: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)

class Session(BaseModel):
    """会话"""
    id: str = Field(default_factory=lambda: generate_id("session"))
    context: SessionContext
    state_manager: StateManager
    active_workflows: list[str] = Field(default_factory=list)

    def record_input(self, user_input: str) -> None:
        """记录用户输入"""

    def record_skill_execution(self, skill_id: str) -> None:
        """记录技能执行"""

    def get_history(self, limit: int = 10) -> list[dict]:
        """获取历史记录"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""

class SessionManager(BaseModel):
    """会话管理器"""
    sessions: dict[str, Session] = Field(default_factory=dict)
    state_manager: StateManager
    current_session_id: str | None = None

    def create_session(self, metadata: dict[str, Any] | None = None) -> Session:
        """创建新会话"""

    def get_current_session(self) -> Session | None:
        """获取当前会话"""

    def set_current_session(self, session_id: str) -> None:
        """设置当前会话"""

    def close_session(self, session_id: str | None = None) -> None:
        """关闭会话"""

    def list_sessions(self) -> list[Session]:
        """列出所有会话"""

    def cleanup_inactive_sessions(self, max_age_hours: int = 24) -> int:
        """清理不活跃的会话"""
```

**会话持久化**:
```bash
# .vibe/state/sessions/
.vibe/state/sessions/
├── {session_id}.json
├── {session_id}.json
└── .gitkeep

# Session JSON structure
{
  "id": "session_abc123",
  "context": {
    "session_id": "session_abc123",
    "started_at": "2026-04-04T10:00:00Z",
    "last_activity": "2026-04-04T10:30:00Z",
    "user_inputs": [
      "帮我评审代码",
      "部署配置"
    ],
    "executed_skills": [
      "/code/review",
      "/config/deploy"
    ]
  },
  "active_workflows": []
}
```

---

### 📅 Phase 4: 运行时契约和验证循环 (P1, 2周)

**目标**: 实现 VIBE_OPERATIONS.md 规范和验证循环

#### 4.1 VIBE_OPERATIONS.md 规范 (1周)

**文件结构**:
```
src/vibesop/contract/
├── __init__.py
├── schema.py              # 契约数据模型
├── validator.py           # 契约验证器
└── templates/             # 契约模板
    └── VIBE_OPERATIONS.md.j2
```

**契约模板**:
```markdown
# VibeSOP Operations Contract

> **Generated by**: VibeSOP-Py v{{ version }}
> **Generated at**: {{ generated_at }}
> **Platform**: {{ platform }}

---

## <operating_principles>

{% for principle in principles %}
- {{ principle }}
{% endfor %}

{% if custom_principles %}
### Custom Principles

{% for principle in custom_principles %}
- {{ principle }}
{% endfor %}
{% endif %}

</operating_principles>

---

## <workflow_protocols>

### Available Workflows

{% for workflow in workflows %}
#### {{ workflow.name }}

**Description**: {{ workflow.description }}
**Stages**: {{ workflow.stages | join(', ') }}
**Usage**: `vibe workflow {{ workflow.name }}`

{% endfor %}

</workflow_protocols>

---

## <verification_rules>

### Completion Criteria

{% for criterion in completion_criteria %}
- {{ criterion }}
{% endfor %}

### Verification Steps

1. **Pre-execution**: {{ verification.pre_execution }}
2. **During execution**: {{ verification.during_execution }}
3. **Post-execution**: {{ verification.post_execution }}

</verification_rules>

---

## <error_handling>

### Error Categories

{% for category in error_categories %}
- **{{ category.name }}**: {{ category.description }}
  - Recovery: {{ category.recovery }}
{% endfor %}

</error_handling>

---

## <state_management>

### State Scope Definitions

- **SESSION**: Temporary state for current session
- **WORKFLOW**: Persistent state across workflow executions
- **GLOBAL**: Cross-session state
- **TEMPORARY**: Ephemeral state with TTL

### State Keys

{% for scope, keys in state_keys.items() %}
#### {{ scope }}

{% for key in keys %}
- `{{ key.name }}`: {{ key.description }}
{% endfor %}

{% endfor %}

</state_management>

---

## <security_policy>

### Threat Detection

**Enabled**: {{ security.threat_detection_enabled }}
**Scan All Inputs**: {{ security.scan_all_inputs }}
**Threat Types**: {{ security.threat_types | join(', ') }}

### Path Safety

**Traversal Protection**: {{ security.path_traversal_protection }}
**Allowed Directories**: {{ security.allowed_directories | join(', ') }}

</security_policy>

---
*End of VIBE_OPERATIONS.md*
```

**契约生成器**:
```python
class ContractGenerator(BaseModel):
    """契约生成器"""
    template_dir: Path
    version: str
    platform: str

    def generate(
        self,
        output_path: Path,
        custom_config: dict[str, Any] | None = None
    ) -> None:
        """生成 VIBE_OPERATIONS.md"""

    def load_default_config(self) -> dict[str, Any]:
        """加载默认配置"""
        return {
            "version": self.version,
            "platform": self.platform,
            "generated_at": datetime.now().isoformat(),
            "principles": [
                "安全优先：所有外部输入必须经过扫描",
                "原子操作：所有写操作必须是原子的",
                "验证优先：在声称完成前进行验证"
            ],
            "workflows": list(WORKFLOW_PIPELINES.values()),
            "completion_criteria": [
                "所有必需阶段已完成",
                "所有验证已通过",
                "无失败或跳过的阶段",
                "最终上下文包含所需输出"
            ],
            "error_categories": [
                {
                    "name": "ValidationError",
                    "description": "输入验证失败",
                    "recovery": "修正输入并重试"
                },
                {
                    "name": "SecurityError",
                    "description": "安全威胁检测",
                    "recovery": "移除威胁内容或使用白名单"
                },
                {
                    "name": "WorkflowError",
                    "description": "工作流执行失败",
                    "recovery": "从失败的阶段重试或中止"
                }
            ],
            "verification": {
                "pre_execution": "验证输入和前置条件",
                "during_execution": "监控进度和中间结果",
                "post_execution": "验证输出和完成标准"
            },
            "state_keys": {
                "SESSION": [
                    {"name": "current_skill", "description": "当前执行的技能"},
                    {"name": "user_input", "description": "当前用户输入"}
                ],
                "WORKFLOW": [
                    {"name": "active_workflow", "description": "活动工作流ID"},
                    {"name": "workflow_context", "description": "工作流上下文"}
                ],
                "GLOBAL": [
                    {"name": "installed_integrations", "description": "已安装的集成"},
                    {"name": "configuration_hash", "description": "配置文件哈希"}
                ],
                "TEMPORARY": [
                    {"name": "cache_ttl", "description": "缓存过期时间"}
                ]
            },
            "security": {
                "threat_detection_enabled": True,
                "scan_all_inputs": True,
                "threat_types": [
                    "prompt_leakage",
                    "role_hijacking",
                    "instruction_injection",
                    "privilege_escalation",
                    "indirect_injection"
                ],
                "path_traversal_protection": True,
                "allowed_directories": [
                    "~/.claude",
                    "~/.config/claude",
                    ".vibe"
                ]
            }
        }
```

#### 4.2 VerificationLoop 验证循环 (1周)

**文件结构**:
```
src/vibesop/verification/
├── __init__.py
├── loop.py               # VerificationLoop
├── criteria.py           # CompletionCriteria
└── validators.py         # 各类验证器
```

**核心接口**:
```python
from pydantic import BaseModel, Field
from typing import Callable, Any
from enum import Enum

class VerificationStage(str, Enum):
    """验证阶段"""
    PRE_EXECUTION = "pre_execution"
    DURING_EXECUTION = "during_execution"
    POST_EXECUTION = "post_execution"

class CompletionCriteria(BaseModel):
    """完成标准"""
    all_stages_completed: bool = True
    no_failures: bool = True
    verifications_passed: bool = True
    required_outputs_present: list[str] = Field(default_factory=list)
    custom_checks: list[Callable[[dict[str, Any]], bool]] = Field(default_factory=list)

    def validate(self, context: dict[str, Any]) -> tuple[bool, list[str]]:
        """验证完成标准"""
        issues = []

        if self.all_stages_completed:
            if not context.get("all_stages_completed"):
                issues.append("Not all stages are completed")

        if self.no_failures:
            if context.get("failed_stages"):
                issues.append(f"Failed stages: {context['failed_stages']}")

        if self.verifications_passed:
            if not context.get("verifications_passed"):
                issues.append("Verifications not passed")

        for output in self.required_outputs_present:
            if output not in context.get("outputs", {}):
                issues.append(f"Required output missing: {output}")

        for i, check in enumerate(self.custom_checks):
            if not check(context):
                issues.append(f"Custom check {i} failed")

        return len(issues) == 0, issues

class VerificationLoop(BaseModel):
    """验证循环"""
    criteria: CompletionCriteria
    max_iterations: int = Field(default=10, ge=1)
    current_iteration: int = Field(default=0)

    def verify(
        self,
        context: dict[str, Any],
        stage: VerificationStage
    ) -> tuple[bool, list[str]]:
        """执行验证"""

    def should_continue(self) -> bool:
        """检查是否应该继续循环"""

    def iterate(
        self,
        workflow: WorkflowPipeline,
        initial_context: dict[str, Any]
    ) -> WorkflowResult:
        """迭代直到完成标准满足"""

    def verify_pre_execution(self, context: dict[str, Any]) -> None:
        """执行前验证"""

    def verify_during_execution(self, context: dict[str, Any]) -> None:
        """执行中验证"""

    def verify_post_execution(self, context: dict[str, Any]) -> None:
        """执行后验证"""
```

**使用示例**:
```python
# 定义完成标准
criteria = CompletionCriteria(
    all_stages_completed=True,
    no_failures=True,
    verifications_passed=True,
    required_outputs_present=["config_path", "verification_report"]
)

# 创建验证循环
verification_loop = VerificationLoop(
    criteria=criteria,
    max_iterations=5
)

# 在工作流中使用
pipeline = WORKFLOW_PIPELINES["config-deploy"]
result = verification_loop.iterate(pipeline, initial_context)

if result.success:
    console.print("[green]✓[/green] 工作流成功完成")
else:
    console.print("[red]✗[/red] 工作流失败")
    for issue in result.errors:
        console.print(f"  - {issue}")
```

---

### 📅 Phase 5: CLI 用户体验增强 (P1, 1周)

**目标**: 提升命令行界面和交互体验

#### 5.1 增强的输出格式

**改进点**:
1. **彩色输出**: 使用 Rich 库增强视觉效果
2. **进度条**: 长时间操作显示进度
3. **表格格式**: 结构化数据以表格显示
4. **交互式选择**: 使用 questionary 进行交互式输入

**实现示例**:
```python
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# 彩色输出
console.print("[green]✓[/green] 配置已安装")
console.print("[red]✗[/red] 验证失败")
console.print("[yellow]⚠[/yellow] 警告：检测到潜在问题")

# 进度条
with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    console=console
) as progress:
    task = progress.add_task("安装配置...", total=100)
    for i in range(100):
        progress.update(task, advance=1)
        time.sleep(0.02)

# 表格格式
table = Table(title="可用工作流")
table.add_column("名称", style="cyan")
table.add_column("描述", style="white")
table.add_column("阶段数", style="yellow")

for name, workflow in WORKFLOW_PIPELINES.items():
    table.add_row(name, workflow.description, str(len(workflow.stages)))

console.print(table)
```

#### 5.2 交互式命令

**新增命令**:
```bash
# 交互式工作流执行
vibe workflow --interactive

# 会话管理
vibe session list
vibe session show <session-id>
vibe session resume <session-id>
vibe session close

# 状态检查
vibe state get <key> [--scope <scope>]
vibe state set <key> <value> [--scope <scope>]
vibe state list [--scope <scope>]
vibe state export [--output <file>]
vibe state import <file>

# 契约管理
vibe contract generate [--output <path>]
vibe contract validate <path>
```

---

### 📅 Phase 6: 性能优化和测试覆盖 (P1, 1周)

**目标**: 提升性能并确保测试覆盖

#### 6.1 性能优化

**优化点**:
1. **缓存**: LRU 缓存技能路由结果
2. **并发**: 异步执行独立阶段
3. **索引**: 为状态存储建立索引

**实现**:
```python
from functools import lru_cache
import asyncio

class OptimizedWorkflowPipeline(WorkflowPipeline):
    """优化的工作流管道"""

    @lru_cache(maxsize=128)
    def get_stage_cached(self, stage_name: str) -> PipelineStage:
        """缓存阶段获取"""
        return self.stages[stage_name]

    async def execute_async(
        self,
        initial_context: dict[str, Any]
    ) -> WorkflowResult:
        """异步执行工作流"""
        # 并发执行独立阶段
        independent_stages = self._get_independent_stages()
        await asyncio.gather(*[
            self._execute_stage_async(stage, initial_context)
            for stage in independent_stages
        ])
```

#### 6.2 测试覆盖目标

**目标指标**:
- 总测试数: 400+ tests
- 代码覆盖率: 90%+
- 关键模块覆盖率: 95%+

**新增测试**:
```python
# tests/workflow/test_pipeline.py (40 tests)
# tests/triggers/test_detector.py (30 tests)
# tests/state/test_manager.py (30 tests)
# tests/session/test_manager.py (25 tests)
# tests/contract/test_generator.py (20 tests)
# tests/verification/test_loop.py (25 tests)
# tests/integration/test_workflow_e2e.py (30 tests)
# tests/performance/test_benchmarks.py (10 tests)

总计: 210 新测试
现有测试: 263 tests
目标总计: 473+ tests
```

---

## 📅 Phase 7: 文档和示例 (P2, 1周)

**目标**: 完善文档和提供实用示例

#### 7.1 文档结构

```
docs/
├── README.md                    # 项目主文档
├── v2-overview.md              # v2.0 总览
├── workflows/                   # 工作流文档
│   ├── introduction.md
│   ├── built-in-workflows.md
│   ├── custom-workflows.md
│   └── best-practices.md
├── guides/                      # 用户指南
│   ├── getting-started.md
│   ├── workflow-orchestration.md
│   ├── state-management.md
│   └── verification-loops.md
├── api/                         # API 文档
│   ├── workflow.md
│   ├── triggers.md
│   ├── state.md
│   └── verification.md
└── examples/                    # 示例
    ├── simple-workflow.py
    ├── custom-triggers.py
    ├── state-persistence.py
    └── verification-loop.py
```

#### 7.2 示例代码

**工作流示例**:
```python
# examples/simple-workflow.py
from vibesop.workflow import WorkflowPipeline, PipelineStage
from vibesop.verification import VerificationLoop, CompletionCriteria

# 定义工作流
pipeline = WorkflowPipeline(
    name="my-workflow",
    description="简单的工作流示例",
    stages={
        "stage1": PipelineStage(
            name="stage1",
            description="第一阶段",
            handler=lambda ctx: {"output": "done"}
        ),
        "stage2": PipelineStage(
            name="stage2",
            description="第二阶段",
            dependencies=["stage1"],
            handler=lambda ctx: {"result": ctx["output"]}
        )
    }
)

# 执行工作流
result = pipeline.execute({"input": "data"})

# 带验证循环
criteria = CompletionCriteria(
    all_stages_completed=True,
    no_failures=True
)
verification_loop = VerificationLoop(criteria=criteria)
result = verification_loop.iterate(pipeline, {"input": "data"})
```

---

## 🎯 版本发布计划

### 📦 v2.0.0-alpha.1 (预计 6 周后)

**包含功能**:
- ✅ Phase 1: 工作流编排引擎
- ✅ Phase 2: 智能关键词触发

**测试状态**:
- 单元测试: 350+ tests
- 集成测试: 30+ tests
- 代码覆盖率: 88%+

### 📦 v2.0.0-beta.1 (预计 8 周后)

**包含功能**:
- ✅ Phase 1-3: 工作流 + 触发 + 状态管理
- ✅ Phase 5: CLI 用户体验增强

**测试状态**:
- 单元测试: 400+ tests
- 集成测试: 40+ tests
- 代码覆盖率: 90%+

### 📦 v2.0.0 (预计 10 周后)

**包含功能**:
- ✅ All Phases: 完整功能集
- ✅ Phase 7: 完整文档和示例

**测试状态**:
- 总测试数: 473+ tests
- 代码覆盖率: 90%+
- 性能基准测试通过

---

## 📊 成功指标

### 技术指标

| 指标 | 当前 (v1.0) | 目标 (v2.0) | 提升 |
|------|------------|------------|------|
| 总测试数 | 263 | 473+ | +80% |
| 代码覆盖率 | 85% | 90%+ | +5% |
| 工作流数量 | 0 | 10+ | ∞ |
| 关键词模式 | 0 | 30+ | ∞ |
| 状态存储 | 无 | 完整 | ∞ |

### 功能指标

| 功能 | v1.0 | v2.0 |
|------|------|------|
| 配置生成 | ✅ | ✅ |
| 安全扫描 | ✅ | ✅ |
| 技能路由 | ✅ | ✅ 增强 |
| 工作流编排 | ❌ | ✅ |
| 关键词触发 | ❌ | ✅ |
| 状态持久化 | ❌ | ✅ |
| 验证循环 | ❌ | ✅ |
| 会话管理 | ❌ | ✅ |
| 运行时契约 | ❌ | ✅ |

### 用户体验指标

| 指标 | v1.0 | v2.0 |
|------|------|------|
| CLI 命令数 | 8 | 15+ |
| 交互式命令 | 1 | 5+ |
| 输出格式 | 基础 | 增强 (Rich) |
| 文档完整性 | 中等 | 完整 |

---

## 🚨 风险和缓解措施

### 风险 1: 向后兼容性

**风险**: v2.0 重大变更可能破坏现有用户工作流

**缓解措施**:
1. 维护 v1.x 分支至少 6 个月
2. 提供详细的迁移指南
3. 在 v2.0 中支持 v1.x 配置格式
4. 添加弃用警告而非直接移除功能

### 风险 2: 性能下降

**风险**: 新增功能可能影响性能

**缓解措施**:
1. 建立性能基准测试
2. 在每个阶段进行性能分析
3. 使用异步和缓存优化
4. 提供性能分析工具

### 风险 3: 测试覆盖不足

**风险**: 新功能测试覆盖不够

**缓解措施**:
1. TDD 开发方法
2. 每个功能至少 20+ 测试
3. 集成测试覆盖关键路径
4. 持续集成强制测试通过

### 风险 4: 用户学习曲线

**风险**: 新功能增加学习难度

**缓解措施**:
1. 保持 CLI 简单命令可用
2. 提供交互式向导
3. 完整的文档和示例
4. 视频教程

---

## 📝 优先级总结

### P0 - 必须有 (Must Have)
- ✅ Phase 1: 工作流编排引擎 (3周)
- ✅ Phase 2: 智能关键词触发 (2周)
- ✅ Phase 3: 状态持久化 (2周)

**时间**: 7周
**价值**: 核心功能，区分于 v1.0

### P1 - 应该有 (Should Have)
- ✅ Phase 4: 运行时契约 (2周)
- ✅ Phase 5: CLI 增强 (1周)
- ✅ Phase 6: 性能优化 (1周)

**时间**: 4周
**价值**: 用户体验和性能提升

### P2 - 可以有 (Nice to Have)
- ⭐ Phase 7: 文档和示例 (1周)

**时间**: 1周
**价值**: 用户采用和社区增长

---

## 🗓️ 总体时间表

```
Week 1-3:  Phase 1 - 工作流编排引擎
Week 4-5:  Phase 2 - 智能关键词触发
Week 6-7:  Phase 3 - 状态持久化
           ──────────────────────
           v2.0.0-alpha.1 发布
Week 8-9:  Phase 4 - 运行时契约
Week 10:   Phase 5 - CLI 增强
Week 11:   Phase 6 - 性能优化
           ──────────────────────
           v2.0.0-beta.1 发布
Week 12:   Phase 7 - 文档和示例
           ──────────────────────
           v2.0.0 正式发布
```

**总计**: 12 周 (约 3 个月)

---

## 🎉 结语

这个路线图将 VibeSOP-Py 从一个优秀的**配置管理框架**升级为一个强大的**工作流编排引擎**，同时保持其在类型安全、安全扫描和模块化设计方面的核心优势。

通过借鉴 Oh-My-Codex 的优秀实践，并结合 Python 生态系统的优势，VibeSOP-Py v2.0 将成为 AI 辅助开发领域的领先工具。

---

**文档版本**: 1.0
**最后更新**: 2026-04-04
**维护者**: VibeSOP-Py Team
