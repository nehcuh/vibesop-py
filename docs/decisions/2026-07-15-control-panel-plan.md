# VibeSOP Control Panel — RIPER Plan（实施计划）

> 日期：2026-07-15
> 项目：~/Projects/vibesop-py v8.0.0.dev0
> 输入：v3 综合 + 用户布局确认（4 屏，面向小白）
> 约束：FastAPI + React + Vite + Monaco + react-flow + Tree-sitter + Jedi + Langfuse v3 self-hosted（默认禁用）+ OS keychain + 同进程 import + 共享 `~/.vibe/`
> 验收标准：另一个工程师按此文档实现，不需问任何问题

---

## 1. 目录结构

### 1.1 仓库布局（monorepo）

```
vibesop-py/
├── src/vibesop/                    # 现有 Python 包
│   ├── agent/                      # 现有：路由、编排、Squad
│   ├── adapters/                   # 现有：5 个 Agent adapter（claude_code/cursor/opencode/kimi_cli/pi_coding_agent）
│   ├── cli/                        # 现有：typer CLI
│   ├── core/                       # 现有：routing/orchestration/skills
│   └── panel/                      # 【新增】控制面板后端
│       ├── __init__.py
│       ├── app.py                  # FastAPI app factory
│       ├── config.py               # Panel 配置（Pydantic Settings）
│       ├── api/                    # REST + WebSocket 端点
│       │   ├── __init__.py
│       │   ├── agents.py
│       │   ├── tasks.py
│       │   ├── diff.py
│       │   ├── impact.py
│       │   ├── providers.py
│       │   ├── roles.py
│       │   ├── mcps.py
│       │   ├── settings.py
│       │   └── ws.py
│       ├── runtime/                # 任务执行 runtime
│       │   ├── __init__.py
│       │   ├── task_manager.py     # 任务生命周期
│       │   ├── event_bus.py        # Pub/sub（asyncio.Queue）
│       │   ├── execution_bridge.py # 调用现有 AgentRouter
│       │   └── file_watcher.py     # 任务期间的文件变更追踪
│       ├── ast/                    # 【新增】AST 影响分析
│       │   ├── __init__.py
│       │   ├── parser.py           # Tree-sitter 包装
│       │   ├── resolver.py         # 跨文件引用（Jedi for Python）
│       │   ├── impact.py           # 计算影响集
│       │   └── cache.py            # 增量缓存（SQLite）
│       ├── observability/          # Langfuse 集成
│       │   ├── __init__.py
│       │   ├── langfuse_bridge.py  # SDK 装饰器包装
│       │   └── otlp_bridge.py      # P2：OTLP 双轨
│       ├── security/
│       │   ├── __init__.py
│       │   ├── keychain.py         # keyring 包装
│       │   └── token_auth.py       # P1：单 token auth
│       ├── db.py                   # SQLite（panel.db）
│       ├── migrations/
│       │   └── 001_initial.sql
│       └── static/                 # 构建后的 React SPA（gitignored，pip 安装时打包）
│
├── panel-web/                      # 【新增】React 前端（独立 npm 包）
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes.tsx
│       ├── api/                    # REST 客户端（从 OpenAPI 生成）
│       ├── ws/                     # WebSocket 客户端
│       ├── stores/                 # Zustand stores
│       ├── pages/                  # 4 屏
│       │   ├── TaskCenter.tsx
│       │   ├── TaskExecution.tsx
│       │   ├── TaskResult.tsx
│       │   └── Settings.tsx
│       ├── components/
│       │   ├── layout/
│       │   ├── task/
│       │   ├── diff/
│       │   ├── agents/
│       │   ├── roles/
│       │   ├── mcps/
│       │   └── settings/
│       └── lib/
│
├── docker/
│   └── panel-langfuse.yml          # vibe langfuse up 用的 compose
│
├── tests/                          # 现有 + 新增
│   ├── panel/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   └── ...
│
├── pyproject.toml                  # 加 [panel] extras
└── ...
```

### 1.2 pyproject.toml 新增

```toml
[project.optional-dependencies]
panel = [
    "fastapi>=0.115.0,<1.0.0",
    "uvicorn[standard]>=0.32.0,<1.0.0",
    "websockets>=13.0,<15.0",
    "python-multipart>=0.0.12,<1.0.0",  # FastAPI form parsing
    "keyring>=25.0.0,<27.0.0",           # OS keychain
    "tree-sitter>=0.23.0,<1.0.0",
    "tree-sitter-python>=0.23.0,<1.0.0",
    "tree-sitter-javascript>=0.23.0,<1.0.0",
    "tree-sitter-typescript>=0.23.0,<1.0.0",
    "jedi>=0.19.0,<1.0.0",               # Python 跨文件引用
    "langfuse>=2.50.0,<4.0.0",           # Observability
    "watchfiles>=1.0.0,<2.0.0",          # 文件变更监听
    "aiosqlite>=0.20.0,<1.0.0",          # 异步 SQLite
]
```

`vibesop[panel]` 是单一安装命令，包含所有控制面板依赖。普通用户 `pip install vibesop` 不受影响。

### 1.3 CLI 新增子命令（src/vibesop/cli/subcommands/panel.py）

```python
import typer
import uvicorn

app = typer.Typer(help="VibeSOP 控制面板")

@app.command()
def start(
    host: str = "127.0.0.1",
    port: int = 14500,
    reload: bool = False,
    open_browser: bool = True,
):
    """启动控制面板（默认 http://localhost:14500）"""
    if open_browser:
        import threading, webbrowser, time
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(f"http://{host}:{port}")), daemon=True).start()
    uvicorn.run("vibesop.panel.app:app", host=host, port=port, reload=reload)

@app.command()
def langfuse_up():
    """启动 Langfuse（需要 Docker）"""
    # 调用 docker compose -f docker/panel-langfuse.yml up -d
    ...

@app.command()
def langfuse_down():
    """停止 Langfuse"""
    ...
```

用户使用：`vibe panel start`（启动面板，自动开浏览器）。

---

## 2. 数据模型

### 2.1 文件布局

```
~/.vibe/                       # 现有，共享
├── skills/                    # 现有
├── traces/                    # 现有（vibe trace JSONL）
├── sessions/                  # 现有
├── instincts/                 # 现有
└── panel/                     # 【新增】面板专用
    ├── panel.db               # SQLite
    ├── ast-cache/             # AST 增量缓存（按文件 hash 索引）
    ├── tasks/                 # 任务执行日志（每任务一个 JSONL）
    └── config.toml            # 面板配置（langfuse URL / token / 启用状态）
```

### 2.2 SQLite Schema（src/vibesop/panel/migrations/001_initial.sql）

```sql
-- 已安装/检测到的 Agent
CREATE TABLE agents (
    id TEXT PRIMARY KEY,                -- 'claude-code', 'cursor', 'opencode', ...
    display_name TEXT NOT NULL,         -- 'Claude Code'
    category TEXT NOT NULL,             -- 'cli' | 'gui' | 'general'
    adapter TEXT NOT NULL,              -- 对应 vibesop/adapters/{adapter}.py
    executable_path TEXT,               -- 检测到的可执行路径（NULL = 未装）
    config_path TEXT,                   -- 该 Agent 的主配置文件路径
    capabilities TEXT NOT NULL,         -- JSON: ['headless', 'config-only', 'launch-only']
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

-- Provider 配置（API key 不存这里，存 keychain）
CREATE TABLE providers (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    provider_type TEXT NOT NULL,        -- 'openai' | 'anthropic' | 'ollama' | 'kimi' | ...
    base_url TEXT,
    model TEXT,
    api_key_keychain_ref TEXT,          -- keychain 服务名（不存 key 本身）
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(agent_id, provider_type)
);

-- 角色（Prompt + skill/MCP 子集 + 默认 Agent）
CREATE TABLE roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,          -- '后端工程师', '代码审查员'
    description TEXT,
    system_prompt TEXT NOT NULL,
    default_agent_id TEXT REFERENCES agents(id),
    icon TEXT,                          -- emoji
    created_at TEXT NOT NULL
);

CREATE TABLE role_skills (
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,             -- 引用 vibesop 现有 skill ID
    PRIMARY KEY (role_id, skill_id)
);

CREATE TABLE role_mcps (
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    mcp_id TEXT NOT NULL REFERENCES mcps(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, mcp_id)
);

-- MCP 模板库
CREATE TABLE mcps (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,          -- 'filesystem', 'github', 'postgres'
    display_name TEXT NOT NULL,         -- '文件系统', 'GitHub'
    description TEXT,
    icon TEXT,
    config_template TEXT NOT NULL,      -- JSON 模板，含 ${VAR} 占位符
    created_at TEXT NOT NULL
);

CREATE TABLE mcp_agents (
    mcp_id TEXT NOT NULL REFERENCES mcps(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 1,
    synced_at TEXT,                     -- 最后一次 sync 到 Agent config 的时间
    PRIMARY KEY (mcp_id, agent_id)
);

-- 任务
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,                -- UUID
    user_input TEXT NOT NULL,           -- 用户原始输入
    agent_id TEXT REFERENCES agents(id),
    role_id TEXT REFERENCES roles(id),
    workdir TEXT NOT NULL,              -- 任务执行时的工作目录
    status TEXT NOT NULL,               -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    submitted_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    cost_usd REAL,
    token_input INTEGER,
    token_output INTEGER,
    error_message TEXT,
    snapshot_path TEXT                  -- 任务前文件快照（用于 rollback）
);

-- 任务步骤（实时事件流持久化）
CREATE TABLE task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    skill_id TEXT,
    description TEXT NOT NULL,
    status TEXT NOT NULL,               -- 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    started_at TEXT NOT NULL,
    completed_at TEXT,
    output TEXT,                        -- JSON blob
    UNIQUE(task_id, step_number)
);

-- 任务产生的文件变更
CREATE TABLE task_changes (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,            -- 相对 workdir
    change_type TEXT NOT NULL,          -- 'modified' | 'added' | 'deleted'
    diff TEXT NOT NULL,                 -- unified diff
    impact_summary TEXT,                -- JSON: { affected_callers: [...], has_dynamic_dispatch: bool }
    detected_at TEXT NOT NULL
);

-- AST 增量缓存（按文件 hash 索引）
CREATE TABLE ast_cache (
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,            -- blake2b
    language TEXT NOT NULL,             -- 'python' | 'javascript' | ...
    symbols TEXT NOT NULL,              -- JSON: [{name, type, start_line, end_line, ...}]
    parsed_at TEXT NOT NULL,
    PRIMARY KEY (file_path, file_hash)
);

-- 用户使用统计（驱动"最近做过"和"试试这些"）
CREATE TABLE task_history_index (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    quick_action_category TEXT,         -- 'refactor' | 'test' | 'explain' | 'security'
    user_satisfied INTEGER,             -- 1=满意, 0=撤销, NULL=未反馈
    indexed_at TEXT NOT NULL
);
```

### 2.3 配置文件（~/.vibe/panel/config.toml）

```toml
[server]
host = "127.0.0.1"
port = 14500
open_browser_on_start = true

[security]
# P1：单 token auth（空 = 不启用）
auth_token = ""

[observability]
# 默认禁用，启用需先 `vibe panel langfuse-up`
backend = "none"  # "none" | "langfuse"

[observability.langfuse]
host = "http://localhost:13000"
public_key = ""
secret_key = ""

[ui]
default_view = "simple"  # "simple" | "detailed"
language = "zh-CN"
```

---

## 3. 后端 API 设计

### 3.1 REST 端点（src/vibesop/panel/api/*.py）

| 方法 | 路径 | 用途 | 关键字段 |
|---|---|---|---|
| GET | `/api/agents` | 列出所有已知 Agent + 检测可用性 | `[{id, display_name, category, available, capabilities}]` |
| GET | `/api/agents/{id}` | Agent 详情 + provider 配置 | `{...agents, provider: {...}}` |
| PUT | `/api/agents/{id}/provider` | 更新 provider 配置 | `{provider_type, base_url?, model?, api_key?}` — api_key 进 keychain |
| POST | `/api/agents/{id}/test` | 测试 Agent 连接 | 返回 `{ok, latency_ms, error?}` |
| GET | `/api/roles` / POST / PATCH / DELETE | 角色 CRUD | `Role` |
| GET | `/api/mcps` / POST / PATCH / DELETE | MCP 模板 CRUD | `Mcp` |
| POST | `/api/mcps/{id}/sync` | 把 MCP 模板 sync 到指定 Agent config | `{agent_id}` |
| POST | `/api/tasks` | 提交任务 | `{user_input, agent_id?, role_id?, workdir?}` |
| GET | `/api/tasks` | 任务列表（分页 + 过滤） | `?status=completed&limit=20` |
| GET | `/api/tasks/{id}` | 任务详情 + 所有 step | `{task, steps[]}` |
| DELETE | `/api/tasks/{id}` | 取消运行中的任务 | |
| GET | `/api/tasks/{id}/changes` | 文件变更列表 | `[{file_path, change_type, diff, impact_summary}]` |
| GET | `/api/tasks/{id}/impact` | AST 影响分析（聚合） | `{affected_files: [...], dynamic_dispatch_warnings: [...]}` |
| POST | `/api/tasks/{id}/rollback` | 撤销任务的所有变更 | |
| GET | `/api/settings` | 读面板配置 | |
| PUT | `/api/settings` | 更新面板配置 | Langfuse 启用/禁用 |
| GET | `/api/quick-actions` | 推荐"试试这些"卡片 | 基于 `task_history_index` 聚合 |
| GET | `/api/skills` | 代理现有 `vibe skills list` | |
| GET | `/api/traces` | 代理现有 `vibe trace list` | |

### 3.2 WebSocket 端点

**`WS /api/ws/tasks/{task_id}`** — 任务事件流

客户端连接后，服务端 push 以下事件直到 task 完成/失败/取消：

```typescript
// 单一 discriminated union
type TaskEvent =
  | { type: 'task.started'; task_id: string; agent_id: string; role_id?: string; planned_steps: Step[] }
  | { type: 'step.started'; step_id: string; step_number: number; description: string }
  | { type: 'step.progress'; step_id: string; message: string; kind: 'info' | 'warning' | 'error' }
  | { type: 'step.completed'; step_id: string; output?: unknown }
  | { type: 'step.failed'; step_id: string; error: string; recoverable: boolean }
  | { type: 'file.changed'; file_path: string; change_type: 'modified'|'added'|'deleted'; diff_preview: string }
  | { type: 'impact.detected'; source_file: string; affected_callers: Array<{ file: string; line: number; snippet: string }> }
  | { type: 'agent.message'; message: string; kind: 'info'|'warning'|'error' }
  | { type: 'cost.update'; cost_usd: number; token_input: number; token_output: number }
  | { type: 'task.completed'; task_id: string; summary: string; cost_usd: number; changes_count: number }
  | { type: 'task.failed'; task_id: string; error: string }
  | { type: 'task.cancelled'; task_id: string };
```

服务端实现：`EventBus`（asyncio.Queue fan-out）。TaskManager publish，所有订阅 task_id 的 WS 连接 receive。

### 3.3 错误模型

```python
# src/vibesop/panel/api/errors.py
class PanelError(Exception):
    status_code: int = 400
    code: str
    user_message_zh: str  # 面向小白的中文错误
    detail: dict = {}

class AgentNotAvailableError(PanelError):
    code = "agent_not_available"
    user_message_zh = "这个 AI 助手还没准备好。点这里去设置 →"

class ProviderNotConfiguredError(PanelError):
    code = "provider_not_configured"
    user_message_zh = "这个 AI 助手还没有配置连接信息。要去配置吗？"

class TaskExecutionError(PanelError):
    code = "task_execution_failed"
    user_message_zh = "AI 在执行任务时遇到了问题。详情：{detail}"
```

FastAPI exception handler 把 PanelError 转 JSON：`{ok: false, code, user_message_zh, detail}`。前端按 `code` 决定跳转到哪个修复入口。

---

## 4. AST 影响分析方案

### 4.1 选型最终确认

| 层 | 工具 | 用途 |
|---|---|---|
| **解析** | Tree-sitter（Python/JS/TS grammar） | 单文件语法树，定位函数/类定义和调用 |
| **跨文件引用（Python）** | **Jedi** | 行业标准（VS Code Python 扩展用），稳定 |
| **跨文件引用（JS/TS）** | **tsserver** 调用（Node 子进程） | P1 起加，MVP 仅 Python |
| **规则匹配（增强）** | **Semgrep**（可选） | 检测 @deprecated / eval / 动态分发 |
| **缓存** | SQLite `ast_cache` 表 | 按 `(file_path, file_hash)` 索引 |

### 4.2 核心模块

```python
# src/vibesop/panel/ast/parser.py
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

_LANGUAGES = {
    'python': Language(tspython.language()),
    # P1 加：'javascript': Language(...), 'typescript': Language(...)
}

def parse(file_path: Path) -> tuple[Tree, str]:
    """Parse a source file. Returns (tree, source_text)."""
    suffix = file_path.suffix.lower()
    lang_name = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript'}.get(suffix)
    if lang_name not in _LANGUAGES:
        raise UnsupportedLanguageError(file_path)
    source = file_path.read_text(encoding='utf-8')
    parser = Parser(_LANGUAGES[lang_name])
    return parser.parse(source.encode()), source

def extract_symbols(tree: Tree, source: str) -> list[Symbol]:
    """Find all top-level function/class/method definitions."""
    # Walk tree, collect (name, type, start_line, end_line, signature)
    ...
```

```python
# src/vibesop/panel/ast/resolver.py
import jedi

def find_callers_python(file_path: Path, line: int, name: str, project_root: Path) -> list[Caller]:
    """Use Jedi to find all callsites of the symbol at (file, line).
    Returns: [{file, line, column, snippet}]"""
    project = jedi.get_default_project()
    script = jedi.Script(path=file_path, project=project)
    refs = script.get_references(line=line, column=0)  # 简化；实际需先定位到 name 的 column
    callers = []
    for ref in refs:
        if ref.module_path == file_path and ref.line == line:
            continue  # skip the definition itself
        callers.append(Caller(
            file=str(ref.module_path),
            line=ref.line,
            column=ref.column,
            snippet=_extract_snippet(ref.module_path, ref.line),
        ))
    return callers
```

```python
# src/vibesop/panel/ast/impact.py
class ImpactAnalyzer:
    def __init__(self, db: Connection, workdir: Path):
        self.db = db
        self.workdir = workdir

    async def analyze_changes(self, task_id: str, changes: list[FileChange]) -> ImpactReport:
        """For each modified symbol, find all callers. Aggregate into report."""
        affected = []
        warnings = []
        for change in changes:
            if change.change_type == 'deleted':
                continue
            old_symbols = self._symbols_from_cache(change.file_path, change.old_hash)
            new_symbols = await self._symbols_from_parse(change.file_path)
            changed_symbols = self._diff_symbols(old_symbols, new_symbols)
            for sym in changed_symbols:
                callers = await self._find_callers(change.file_path, sym)
                affected.extend(callers)
                if self._has_dynamic_dispatch(change.file_path, sym):
                    warnings.append(f"{change.file_path}::{sym.name} 可能存在动态调用，建议手动检查")
        return ImpactReport(affected=affected, warnings=warnings)
```

### 4.3 增量缓存

- 任务开始前：对 workdir 内所有 Python 文件 hash → 入 `ast_cache`
- 任务中文件变更：仅重算变更文件
- 任务完成后：调用 `ImpactAnalyzer.analyze_changes(task_id, changes)`
- 调用 Jedi 的部分用 `ProcessPoolExecutor`（CPU 密集，避免阻塞 event loop）

### 4.4 验收标准

测试用例（`tests/panel/unit/test_impact.py`）：

```python
def test_renamed_function_callers_detected():
    """改 utils.py:calculateTotal → utils.py:calculate_total
    应该检测到 order.js 和 invoice.js 中的 5 个 callsites。"""
    # 在 fixtures 目录建一个 mini project
    # 跑 ImpactAnalyzer
    # 断言 affected 包含所有已知 callsites
    ...

def test_dynamic_dispatch_warning():
    """代码含 getattr(obj, 'calculateTotal') 时应产生 warning。"""
    ...

def test_cache_invalidation_on_hash_change():
    """文件 hash 变更时 cache 应失效。"""
    ...
```

---

## 5. 三视图联动协议

### 5.1 联动场景

| 触发 | 文件树 | Monaco diff | 影响列表 | Agent 时间线 |
|---|---|---|---|---|
| 任务提交 | 清空 | 清空 | 清空 | 显示第 1 步 |
| 步骤完成 | — | — | — | 追加步骤 |
| 文件变更 | 新增/更新徽章 | 自动跳到首个变更文件 | 标记「待分析」 | — |
| 任务完成 | 全部徽章稳定 | 显示完整 diff | 自动跑 AST，显示影响 | 显示完成总结 |
| 用户在 Monaco 滚动 | 高亮当前文件 | — | 滚到对应文件影响项 | — |
| 用户点影响项 | — | 跳到该 callsite 行 | 高亮该项 | — |
| 用户点撤销 | 全部清空 | 清空 | 清空 | 标记「已回滚」 |

### 5.2 实现机制

**前端**：单一 Zustand store `taskDetailStore`，包含 `{ task, steps, changes, impact, activeFile, activeLine }`。所有视图都是 pure function of store。

**联动通过 store actions**：
```typescript
// panel-web/src/stores/taskDetailStore.ts
interface TaskDetailState {
  task: Task | null;
  steps: Step[];
  changes: FileChange[];
  impact: ImpactReport | null;
  activeFilePath: string | null;
  activeLineNumber: number | null;
  // actions
  setActiveFile(path: string): void;
  setActiveLine(path: string, line: number): void;
  applyWsEvent(event: TaskEvent): void;
  rollback(): Promise<void>;
}
```

**后端 push**：WS 事件 → `applyWsEvent` reducer → 各视图自动 re-render。无显式 view-to-view 调用。

**性能**：Monaco 滚动事件 throttle 50ms，文件树选中状态用 CSS 不重渲染。

---

## 6. 进程模型

### 6.1 MVP（单用户）

```
[Browser] ↔ HTTP/WS ↔ [uvicorn :14500]
                          │
                          ├── FastAPI app（asyncio event loop）
                          ├── TaskManager（asyncio）
                          ├── EventBus（asyncio.Queue）
                          ├── AST ImpactAnalyzer
                          │    └── ProcessPoolExecutor（Jedi CPU 工作）
                          ├── FileWatcher（watchfiles，asyncio）
                          └── LangfuseBridge（asyncio HTTP）
```

**关键决策**：
- 单 worker（`uvicorn --workers 1`）— 本地单用户够用
- AST CPU 工作 offload 到 `ProcessPoolExecutor`（绕开 GIL）
- 文件监听用 `watchfiles`（Rust 后端，asyncio 友好）
- Langfuse SDK 异步，不阻塞

### 6.2 P2（团队部署）

```
[Browser] ↔ Nginx ↔ [uvicorn :14500 (workers=N)]
                          │
                          ├── Redis pub/sub（WS fanout）
                          └── 共享 ~/.vibe/（NFS 或 volume）
```

这是 P2+ 范围，MVP 不做。

---

## 7. Langfuse 集成（路径 B）

### 7.1 模块

```python
# src/vibesop/panel/observability/langfuse_bridge.py
from contextlib import contextmanager
from typing import Optional, Iterator
from langfuse import Langfuse
from langfuse.openai import openai as langfuse_openai
from langfuse.anthropic import anthropic as langfuse_anthropic

class LangfuseBridge:
    def __init__(self, config: PanelConfig):
        self.enabled = config.observability.backend == "langfuse"
        self.client: Optional[Langfuse] = None
        if self.enabled:
            self.client = Langfuse(
                public_key=config.observability.langfuse.public_key,
                secret_key=config.observability.langfuse.secret_key,
                host=config.observability.langfuse.host,
            )

    @contextmanager
    def trace_task(self, task_id: str, user_input: str) -> Iterator[Optional[Trace]]:
        if not self.enabled:
            yield None
            return
        with self.client.trace(id=task_id, name="task", input=user_input) as trace:
            yield trace

    def wrap_llm_client(self, provider: str, original_client):
        """Return a Langfuse-instrumented LLM client, or the original if disabled."""
        if not self.enabled:
            return original_client
        if provider == 'openai':
            return langfuse_openai  # drop-in replacement
        if provider == 'anthropic':
            return langfuse_anthropic
        return original_client
```

### 7.2 装饰点

在 `task_manager.py`：
```python
class TaskManager:
    def __init__(self, bridge: LangfuseBridge, router: AgentRouter, ...):
        self.bridge = bridge
        self.router = router  # 现有 vibesop.agent.AgentRouter

    async def execute_task(self, task: Task) -> TaskResult:
        with self.bridge.trace_task(task.id, task.user_input) as trace:
            # 现有 router 调用，LLM client 通过 bridge.wrap_llm_client 包装
            result = await self.router.orchestrate(
                query=task.user_input,
                agent=task.agent_id,
                callbacks=self._build_callbacks(task, trace),
            )
            return result
```

### 7.3 Langfuse 部署

`docker/panel-langfuse.yml`：
```yaml
services:
  langfuse:
    image: langfuse/langfuse:3
    ports: ["13000:3000"]
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@postgres:5432/langfuse
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      SALT: ${SALT}
      NEXTAUTH_URL: http://localhost:13000
    depends_on: [postgres]
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes: ["langfuse-pg:/var/lib/postgresql/data"]
volumes:
  langfuse-pg:
```

`vibe panel langfuse-up` 自动生成 NEXTAUTH_SECRET / SALT，启动 compose，然后引导用户在 http://localhost:13000 创建项目，把 public_key / secret_key 粘到面板设置里。

---

## 8. 前端架构

### 8.1 技术栈

| 层 | 选型 |
|---|---|
| 框架 | React 19 + TypeScript 5.6 |
| 构建 | Vite 6 |
| 路由 | React Router 7（client-side） |
| 状态 | Zustand 5 |
| 数据获取 | SWR（轻量，比 React Query 更适合面板） |
| 样式 | Tailwind CSS 4 + shadcn/ui（小白友好的默认） |
| 国际化 | react-i18next（zh-CN 默认，en-US 二期） |
| diff | @monaco-editor/react |
| AST 视图 | react-flow（用于详细看的 DAG） |
| 表单 | react-hook-form + zod |

### 8.2 路由（panel-web/src/routes.tsx）

```tsx
const routes = [
  { path: '/', element: <TaskCenter /> },                    // 屏 1
  { path: '/tasks/:id', element: <TaskExecution /> },        // 屏 2
  { path: '/tasks/:id/result', element: <TaskResult /> },    // 屏 3
  { path: '/settings', element: <Settings /> },              // 屏 4
  { path: '/settings/agents/:id', element: <AgentDetail /> },
  { path: '/settings/roles/:id', element: <RoleEditor /> },
];
```

### 8.3 WebSocket hook

```typescript
// panel-web/src/ws/useTaskEvents.ts
export function useTaskEvents(taskId: string) {
  const applyEvent = useTaskDetailStore(s => s.applyWsEvent);
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:14500/api/ws/tasks/${taskId}`);
    ws.onmessage = (e) => {
      const event: TaskEvent = JSON.parse(e.data);
      applyEvent(event);
    };
    return () => ws.close();
  }, [taskId, applyEvent]);
}
```

### 8.4 API client（从 OpenAPI 自动生成）

```bash
# 在 panel-web/ 目录
npm run gen:api  # 调用 openapi-typescript 从 /openapi.json 生成 types
```

---

## 9. 测试策略

### 9.1 后端测试（pytest，已有框架）

```
tests/panel/
├── unit/
│   ├── test_ast_parser.py        # Tree-sitter 各语言 fixture
│   ├── test_ast_resolver.py      # Jedi callsite detection
│   ├── test_impact_aggregator.py
│   ├── test_event_bus.py
│   ├── test_keychain.py
│   └── test_config.py
├── integration/
│   ├── test_api_agents.py        # FastAPI TestClient
│   ├── test_api_tasks.py         # 提交任务 → WS 事件流 → 完成
│   ├── test_api_diff.py
│   ├── test_api_impact.py
│   ├── test_api_providers.py     # 含 keychain round-trip
│   ├── test_api_roles.py
│   ├── test_api_mcps.py
│   └── test_api_settings.py
└── e2e/
    ├── test_task_lifecycle.py    # 完整提交 → 执行 → 看 diff → 撤销
    └── test_langfuse_integration.py
```

### 9.2 前端测试

- Vitest + React Testing Library：组件单元
- Playwright：4 屏关键流程 E2E
- MSW：mock REST + WS

### 9.3 关键测试场景（必须通过）

1. **首次启动**：`vibe panel` → 自动检测 Agent → 显示 Screen 1
2. **提交任务**：输入"重命名 calculateTotal" → 自动选 Claude → Screen 2 实时更新 → Screen 3 显示 diff
3. **影响分析准确**：fixtures 项目里改函数 → 检测到所有 callsites（已知 ground truth）
4. **撤销**：点「👎 不满意」→ 文件回滚到任务前状态
5. **Langfuse 启用**：默认禁用 → 启用 → 任务跑完 → Langfuse 看到 trace
6. **小白术语**：UI 含 "AI 助手/身份/工具箱/观察台"，无 "Agent/MCP/Provider"
7. **空状态**：未配置任何 Agent → Screen 1 显示引导卡片而非错误
8. **API key 安全**：providers 表查询无 key 字段，keychain 单独验证

---

## 10. 分阶段交付（Phase 1 = MVP）

### Phase 1.1 — 后端骨架 + Agent 检测（验收：`curl /api/agents` 列出 5 adapter）

- [ ] 建 `src/vibesop/panel/` 目录
- [ ] FastAPI app factory（CORS、错误处理、静态文件挂载）
- [ ] SQLite migration 001
- [ ] `db.py` 异步连接池
- [ ] `api/agents.py` GET：从现有 `vibesop.adapters` 检测已装 Agent
- [ ] CLI 子命令 `vibe panel start`
- [ ] 测试：TestClient GET /api/agents 返回正确结构

### Phase 1.2 — 前端骨架 + Screen 1 静态（验收：访问 localhost:14500 看到 Screen 1）

- [ ] 建 `panel-web/`，Vite + React + TS + Tailwind
- [ ] 构建脚本：`npm run build` → 输出到 `src/vibesop/panel/static/`
- [ ] FastAPI 在生产模式挂载 `static/` 为 SPA（fallback to index.html）
- [ ] Screen 1 TaskCenter 静态版（无交互）
- [ ] shadcn/ui 装好，主色调定义
- [ ] 中文文案初版

### Phase 1.3 — 任务提交 + WS 事件流（验收：提交任务，Screen 2 实时显示步骤）

- [ ] `runtime/event_bus.py`：asyncio.Queue pub/sub
- [ ] `runtime/task_manager.py`：调用现有 `AgentRouter.orchestrate`，hook 进 event_bus
- [ ] `runtime/execution_bridge.py`：把 router callback 转 WS event
- [ ] `api/tasks.py` POST + GET
- [ ] `api/ws.py` WS endpoint
- [ ] 前端 Screen 2 + useTaskEvents hook
- [ ] 测试：fixture 一个简单任务，断言 WS 收到完整事件序列

### Phase 1.4 — Diff viewer（验收：任务完成后 Screen 3 显示 diff）

- [ ] `runtime/file_watcher.py`：watchfiles 监听 workdir
- [ ] 任务前快照机制（git stash 风格）
- [ ] `api/diff.py` GET /tasks/{id}/changes
- [ ] 前端 Monaco diff 集成
- [ ] 前端 FileTree 组件
- [ ] Screen 3 「简单看」+「详细看」切换
- [ ] 测试：跑任务改文件，断言 diff 正确

### Phase 1.5 — AST 影响分析（验收：改函数，Screen 3 显示所有 callsites）

- [ ] `ast/parser.py` Tree-sitter 包装
- [ ] `ast/resolver.py` Jedi callsite 查询
- [ ] `ast/impact.py` 聚合
- [ ] `ast/cache.py` SQLite 增量缓存
- [ ] ProcessPoolExecutor offload
- [ ] `api/impact.py` GET /tasks/{id}/impact
- [ ] 前端 ImpactList 组件（小白版：勾选清单）
- [ ] 前端 ImpactDAG 组件（详细版，react-flow，P1.5b）
- [ ] fixtures mini-project 测试用例
- [ ] 测试：rename 函数，断言检测到全部 callsites

### Phase 1.6 — Provider 管理 + keychain（验收：UI 改 Claude provider，配置文件同步更新）

- [ ] `security/keychain.py` keyring 包装
- [ ] `api/providers.py` PUT + test
- [ ] 写入 5 个 Agent 的 config 文件（每个 adapter 一个 writer）
- [ ] Screen 4 Settings → AI 助手 section
- [ ] ProviderForm 组件
- [ ] 测试：改 provider → 读 config 文件 → 断言正确

### Phase 1.7 — Roles + MCPs（验收：UI 创建角色，分配 skill，应用到任务）

- [ ] `api/roles.py` CRUD
- [ ] `api/mcps.py` CRUD + sync
- [ ] MCP config 写入各 Agent config（adapter 各自实现 sync_to_config）
- [ ] Screen 4 身份 + 工具箱 section
- [ ] 测试：role create → assign skill → 在 task 中使用

### Phase 1.8 — Langfuse 集成（验收：启用后任务 trace 在 Langfuse 可见）

- [ ] `observability/langfuse_bridge.py`
- [ ] 装饰 TaskManager.execute_task
- [ ] LLM client wrapping（OpenAI / Anthropic）
- [ ] CLI `vibe panel langfuse-up / langfuse-down`
- [ ] `docker/panel-langfuse.yml`
- [ ] Screen 4 观察台 section
- [ ] 测试：启用 → 跑任务 → Langfuse API 查 trace

### Phase 1.9 — 撤销 + 快捷动作 + 文档（验收：小白用户完成完整流程）

- [ ] `api/tasks.py` POST /rollback：从快照恢复文件
- [ ] Screen 3 「👎 不满意」按钮
- [ ] Screen 1 「最近做过」+「试试这些」
- [ ] 空状态、错误状态 polish
- [ ] docs/control-panel.md 用户文档（小白向）
- [ ] docs/control-panel-dev.md 开发文档

### Phase 2 (P1)
- AST 多语言（JS/TS via tsserver）
- 单 token auth + token 验证 middleware
- docker compose for team deploy（多 worker + Redis）
- Langfuse 路径 C（OTLP bridge）
- Skill marketplace 浏览页

### Phase 3+ (P2)
- 性能优化（大仓库）
- 更多 Agent adapter
- 国际化（en-US）
- 移动端友好（responsive）

---

## 11. 风险与回退

| 风险 | 概率 | 影响 | 回退 |
|---|---|---|---|
| Jedi callsite 检测不准（动态分发） | 高 | 影响分析 false negative | 文档化"已知限制"，用 warning 标记可疑符号 |
| Monaco 在大文件 diff 卡顿 | 中 | 体验差 | 限制 diff 文件大小，超限降级为 unified text |
| Langfuse v3 self-host bug | 低 | trace 丢失 | 路径 B 失败时降级到 JSONL（现有 `vibe trace`） |
| WS 连接断开（用户休眠） | 高 | 事件丢失 | 客户端重连 + 服务端补发（按 task_id 查 task_steps 表） |
| Tree-sitter grammar 版本漂移 | 低 | 解析失败 | pin 版本，CI 跑 grammar 兼容性测试 |
| 小白用户配错 provider | 高 | 任务全失败 | ProviderForm 内置「测试连接」按钮 + 错误兜底 |

---

## 12. 完成 RIPER Plan 的 Exit Criteria

- [ ] 用户确认本计划（特别是 9 节测试场景）
- [ ] 所有「新增文件」路径明确
- [ ] 所有「关键决策」有理由 + 备选
- [ ] 工程师能从 Phase 1.1 开始，按 Phase 顺序执行，每个 Phase 有独立验收

确认后进 RIPER Execute（从 Phase 1.1 开始）。
