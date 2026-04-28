# VibeSOP 故障排查手册

> **适用版本**: v5.3.0+  
> **最后更新**: 2026-04-17

---

## 快速诊断清单

遇到问题？先跑一遍：

```bash
# 1. 检查安装与健康状态
vibe doctor

# 2. 查看版本与平台信息
vibe --version

# 3. 验证 SkillOS 路由是否正常工作
vibe route "review my code"

# 4. 运行测试套件
uv run pytest --no-header -q
```

如果以上命令全部通过，说明核心系统正常，问题可能出在配置或技能包上。

---

## 1. 路由不准确 / 找不到技能

### 症状
- `vibe route "debug"` 返回了不相关的技能
- 明明安装了技能包，却匹配不到
- 返回 confidence 很低（<0.6）

### 排查步骤

#### 1.1 检查技能是否被加载
```bash
vibe skills list
```
如果技能不在列表中：
- 检查技能文件是否在 `.vibe/skills/` 或 `~/.config/skills/` 下
- 确认 SKILL.md 包含有效的 YAML frontmatter
- 检查 `vibe doctor` 中的 "Skills" 部分是否有加载错误

#### 1.2 检查路由延迟层
启用 debug 日志查看命中了哪一层：
```bash
vibe route "debug" --verbose
```

如果命中了 `Layer 6 (Fuzzy Fallback)`，说明上层匹配都失败了：
- 检查技能的 `intent` 和 `tags` 是否覆盖了常见查询词
- 考虑在 `.vibe/skill-routing.yaml` 中添加 scenario 映射

#### 1.3 显式指定技能
作为临时 workaround，可以直接显式路由：
```bash
vibe route "/systematic-debugging"
```

### 预防措施
- 为自定义技能编写清晰的 `intent` 描述
- 定期运行 `vibe doctor` 检查技能健康状态

---

## 2. 第一次路由很慢 / 冷启动延迟

### 症状
- 第一次运行 `vibe route` 需要 1-3 秒
- 后续查询很快（<50ms）

### 原因
这是预期行为。`UnifiedRouter` 在第一次调用时需要：
1. 扫描并缓存所有技能元数据
2. 初始化 TF-IDF 向量器
3. 可选：加载 EmbeddingMatcher 模型（最耗时）

### 优化方法

#### 2.1 禁用 EmbeddingMatcher（如果不需要）
在 `.vibe/config.yaml` 中：
```yaml
routing:
  matchers:
    embedding:
      enabled: false
```

#### 2.2 预热缓存
在脚本或 CI 中预先触发一次路由：
```bash
# 在后台预热
vibe route "warmup" > /dev/null 2>&1
```

---

## 3. basedpyright / 类型检查报错

### 症状
- `uv run basedpyright src/` 出现 errors
- CI 的 `type-check` job 失败

### 排查步骤

#### 3.1 区分 errors 和 warnings
我们只关注 **errors**。warnings（如 numpy/sentence_transformers 的 `reportMissingImports`）不会影响 CI 通过。

#### 3.2 常见 errors 及修复

| 错误类型 | 原因 | 修复方法 |
|---------|------|---------|
| `reportMissingParameterType` | 函数参数缺少类型注解 | 添加 `: Type` 注解 |
| `reportMissingReturnType` | 函数缺少返回类型 | 添加 `-> Type` |
| `reportMissingTypeArgument` | 泛型缺少类型参数 | 如 `list` -> `list[str]` |
| `reportCallIssue` | 函数调用参数不匹配 | 检查函数签名变更 |

### 本地配置
项目的类型检查配置在 `pyproject.toml` 的 `[tool.pyright]` 段。第三方库缺失 stubs 产生的 noise 已被全局关闭，请勿在单个文件中添加大量 suppression headers。

---

## 4. 测试覆盖率未达标

### 症状
- CI 中 `uv run pytest --cov` 失败，提示 `< 75%`
- 本地只跑部分测试时覆盖率骤降

### 原因
`pyproject.toml` 中配置了 `parallel = true`。如果只跑部分测试，coverage 数据不完整，可能触发失败阈值。

### 解决方法

#### 4.1 跑全量测试
```bash
uv run pytest --no-header -q
```

#### 4.2 清理旧的 coverage 数据
```bash
rm -f .coverage*
uv run pytest --no-header -q
```

#### 4.3 只跑特定模块时忽略覆盖率检查
```bash
uv run pytest tests/core/routing/ --no-cov -q
```

---

## 5. 安装器 / CLI 报错

### 5.1 `vibe install <pack>` 失败

#### 症状
```
Failed to clone https://github.com/... to ~/.claude/skills/...
```

#### 原因
- 网络问题或仓库不存在
- 目标目录已存在且非空
- 没有 git 或网络代理配置错误

#### 修复
```bash
# 1. 确认网络可访问 GitHub
ping github.com

# 2. 清理残留目录后重试
rm -rf ~/.claude/skills/<pack>
vibe install <pack>

# 3. 使用 --force 强制覆盖
vibe install <pack> --force
```

### 5.2 `vibe init` 后配置未生效

#### 原因
平台配置文件（如 `CLAUDE.md`）需要被对应 AI 工具加载。`vibe init` 只生成文件，不控制 AI 工具的读取行为。

#### 修复
- 确认文件放在了正确的位置（Claude Code 需要 `~/.claude/CLAUDE.md`）
- 重启 AI 工具或重新加载会话

---

## 6. 技能加载失败

### 症状
- `vibe skills list` 中缺少某个技能
- 日志中出现 `Failed to load skill from ...`

### 排查步骤

#### 6.1 检查 SKILL.md 格式
必须包含有效的 YAML frontmatter：
```markdown
---
id: my-skill
name: My Skill
description: "What this skill does"
---

# Content here
```

#### 6.2 检查文件扩展名
支持的格式：`.md`、`.yaml`、`.yml`

#### 6.3 开启 debug 日志
```bash
vibe skills list --verbose
# 或
export VIBESOP_LOG_LEVEL=DEBUG
vibe skills list
```

---

## 7. 报告问题

如果以上步骤无法解决，请收集以下信息并提交 Issue：

```bash
# 1. 环境信息
python --version
vibe --version
uv --version

# 2. 健康检查输出
vibe doctor

# 3. 最小复现步骤
# 请提供具体命令和完整错误日志

# 4. 测试状态
uv run pytest --no-header -q
```

提交 Issue 时请使用 `.github/ISSUE_TEMPLATE/` 中的模板。
