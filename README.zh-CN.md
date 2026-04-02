# VibeSOP - Python 版本

> **现代化 Python 实现** 的久经考验的 AI 辅助开发工作流 SOP。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/Pyright-Strict-blue.svg)](https://github.com/microsoft/pyright)

## 🚀 快速开始

```bash
# 克隆并安装
git clone https://github.com/nehcuh/vibesop-py.git && cd vibesop-py

# 使用 uv（推荐 - 比 pip 快 10-100 倍）
uv sync

# 或使用 pip
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 运行 CLI
vibe --help
```

## 🎯 设计理念

- **Python 3.12+**: 利用现代类型系统和性能改进
- **Pydantic v2**: 运行时验证与编译时类型提示
- **uv**: 极速包管理器（Rust 编写）
- **类型安全**: 基于 basedpyright 的严格类型检查
- **现代工具链**: Ruff 进行 linting/formatting（比 flake8/black 快 100 倍）

## 🛠️ 开发

```bash
# 类型检查
uv run pyright

# 代码检查
uv run ruff check

# 自动修复问题
uv run ruff check --fix

# 代码格式化
uv run ruff format

# 运行测试
uv run pytest

# 运行测试并生成覆盖率报告
uv run pytest --cov=src/vibesop --cov-report=html
```

## 📦 项目结构

```
vibesop-py/
├── src/vibesop/              # 包源码
│   ├── cli/                  # CLI 命令 (Typer)
│   ├── core/                 # 核心业务逻辑
│   │   ├── models/           # Pydantic 模型
│   │   ├── routing/          # AI 路由系统
│   │   └── config/           # 配置管理
│   ├── llm/                  # LLM 客户端 (OpenAI, Anthropic)
│   ├── skills/               # 技能管理
│   └── utils/                # 工具函数
├── tests/                    # 测试套件
│   ├── unit/                 # 单元测试
│   └── integration/          # 集成测试
├── scripts/                  # 实用脚本
│   └── sync-core.sh          # 从 Ruby 版本同步核心 YAML
├── pyproject.toml            # 项目配置
└── README.md                 # 本文件
```

## 🔄 迁移状态

这是 Ruby 版本的 **完整重写**，使用现代 Python。

- [x] 项目结构和工具链
- [x] 类型系统设置 (Pydantic v2)
- [x] 核心模型 (Skill, Route, Config)
- [x] CLI 框架 (Typer)
- [x] AI 路由系统
- [x] LLM 客户端
- [ ] 技能管理
- [ ] 记忆系统
- [ ] 检查点系统

## 🎨 核心功能

### AI 驱动的技能路由

```bash
$ vibe route "帮我评审代码"

📥 输入: 帮我评审代码
✅ 匹配: /review (95% 置信度)
   来源: gstack
   层级: AI 分诊
```

### 现代类型安全

```python
from pydantic import BaseModel, Field, field_validator

class SkillRoute(BaseModel):
    """带运行时验证的技能路由结果。"""

    skill_id: str = Field(..., min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    layer: Literal[0, 1, 2, 3, 4]

    @field_validator('skill_id')
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        if not v.startswith('/'):
            raise ValueError('skill_id 必须以 / 开头')
        return v
```

## 📝 开发指南

### 类型安全优先

```python
# ✅ 好: 完整类型注解
def route_request(request: RoutingRequest) -> RoutingResult:
    """将请求路由到合适的技能。"""
    ...

# ❌ 坏: 缺少类型
def route_request(request):
    ...
```

### 所有数据模型使用 Pydantic

```python
from pydantic import BaseModel

class Config(BaseModel):
    """带运行时验证的配置。"""
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

### 异步优先

```python
import asyncio

async def call_llm(prompt: str) -> str:
    """异步调用 LLM。"""
    # 使用 httpx 进行异步 HTTP
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
        return response.json()
```

## 🧪 测试覆盖

```bash
$ uv run pytest
======================== 168 passed in 6.04s =========================

Coverage Report:
- ConfigLoader: 75.89%
- Models: 92.73%
- PreferenceLearner: 93.48%
- Cache: 98.29%
- Router: 74.10%
- FuzzyMatcher: 96.43%
- SemanticMatcher: 93.52%
- Overall: 78.81%
```

## 🤝 贡献

这是 VibeSOP 的 Python 版本。Ruby 版本请参阅 [vibesop](https://github.com/nehcuh/vibesop)。

## 📄 许可证

MIT - 参见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

基于 [vibesop](https://github.com/nehcuh/vibesop) 的久经考验的 Ruby 实现。
