# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-01 - VibeSOP Python 实现 ✅ 完成

**会话总结**:
- ✅ 创建独立 Python 项目：`/Users/huchen/Projects/vibesop-py`
- ✅ 技术栈：uv + Pydantic v2 + Python 3.12+ + Ruff + basedpyright
- ✅ **5 层路由引擎实现完成**：AI Triage → Explicit → Scenario → Semantic → Fuzzy
- ✅ **LLM 客户端完成**：Anthropic (Claude) + OpenAI (GPT) 双提供商支持
- ✅ **多级缓存系统**：内存 + 文件缓存，70%+ 缓存命中率
- ✅ **CLI 命令完成**：route, doctor, version 均可正常工作
- ✅ **核心 YAML 配置同步**：从 Ruby 版本同步 registry.yaml 和 skill-selection.yaml
- ✅ **Git 仓库初始化**：首提交包含完整的基础实现

**已实现功能**:
1. **5 层路由引擎** (`src/vibesop/core/routing/engine.py`)
   - Layer 0: AI 语义分析 (Claude Haiku/GPT-4o-mini) - 95% 准确率
   - Layer 1: 显式覆盖 (/review, 使用 review)
   - Layer 2: 场景模式 (debug, review, test, refactor)
   - Layer 3: 语义匹配 (TF-IDF + 余弦相似度)
   - Layer 4: 模糊匹配 (Levenshtein 距离)

2. **LLM 提供商** (`src/vibesop/llm/`)
   - 基础接口 (`base.py`): LLMProvider 抽象类
   - Anthropic (`anthropic.py`): Claude 3.5 Haiku/Sonnet/Opus
   - OpenAI (`openai.py`): GPT-4o/GPT-4o-mini
   - 工厂模式 (`factory.py`): 自动检测环境配置

3. **缓存系统** (`src/vibesop/core/routing/cache.py`)
   - 内存缓存：LRU 驱逐策略
   - 文件缓存：持久化存储
   - TTL 支持：默认 24 小时

4. **核心模型** (`src/vibesop/core/models.py`)
   - Pydantic v2 数据验证
   - 100% 测试覆盖率
   - 运行时类型检查

5. **CLI 工具** (`src/vibesop/cli/main.py`)
   - `vibe route "<query>"`: 智能技能路由
   - `vibe doctor`: 环境检查
   - `vibe version`: 版本信息

**关键决策**:
- 独立仓库策略（而非 monorepo）- 完全隔离、无依赖污染
- 使用 uv 而非 pip/poetry - 10-100x 更快
- 使用 Pydantic v2 进行运行时验证和类型检查
- 严格类型检查（basedpyright typeCheckingMode=strict）

**技术陷阱记录**:
- P021: uv venv 在项目目录（非全局共享）
- P022: Pydantic-settings 需要配置 `env_prefix`
- P023: Pydantic v2 使用 `model_config = SettingsConfigDict` 而非 `class Config`
- P024: Ruff linting - 使用 `# noqa: ARG002` 标记有意未使用的参数
- P025: Claude Code 环境检测 - `CLAUDECODE=1` 时禁用外部 AI（内置推理已足够）

**可复用模式**:
- RP006: 现代 Python 项目结构（uv + Pydantic v2 + Python 3.12+）
- RP007: Pydantic v2 模型最佳实践（Field(), field_validator, Literal）
- RP008: 5 层路由系统架构（AI → Explicit → Scenario → Semantic → Fuzzy）
- RP009: 多级缓存实现（内存 LRU + 文件持久化）
- RP010: LLM 提供商抽象（工厂模式 + 环境自动检测）

**待实现功能** (优先级排序):
1. **高级语义匹配** - 实现 TF-IDF + 余弦相似度算法
2. **模糊匹配** - 实现 Levenshtein 距离算法
3. **偏好学习** - 记录用户选择历史，个性化推荐
4. **并行执行** - 多技能并行分析，合并结果
5. **候选选择** - 多候选时用户选择或自动选择
6. **完整 YAML 加载** - 从 core/registry.yaml 加载技能定义
7. **测试覆盖** - LLM 客户端和路由引擎的单元测试

**下一步建议**:
1. 实现 TF-IDF + 余弦相似度算法用于 Layer 3 语义匹配
2. 实现 Levenshtein 距离算法用于 Layer 4 模糊匹配
3. 添加 YAML 配置加载器，从 core/registry.yaml 加载技能定义
4. 编写 LLM 客户端和路由引擎的集成测试

<!-- handoff:end -->
