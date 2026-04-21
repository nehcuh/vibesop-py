# VibeSOP 技能安装快速指南

## 🚀 一键安装流程

### 场景：安装 Tushare 量化技能

#### 第1步：安装技能（超简单）

```bash
# 从官方仓库安装
vibe skill add tushare

# 或从本地文件安装
vibe skill add ./tushare.skill

# 或从 URL 安装
vibe skill add https://skills.vibesop.dev/tushare-1.0.0.skill
```

#### 第2步：交互式配置（智能引导）

安装后会自动进入配置向导：

```
🚀 Smart Skill Installation

Phase 1: Detecting skill...
✓ Detected: Tushare 量化策略
  ID: tushare-quant
  Description: 使用 Tushare API 开发量化交易策略

Phase 2: Security audit...
✓ Security audit passed

Phase 3: Installation scope
? Where should this skill be installed?
  🎯 Project-level (recommended
  🌐 Global (available to all projects)
> [Select with arrow keys]

Phase 4: Installing project...
✓ Installed to: .vibe/skills/tushare-quant

Phase 5: Auto-configuring...
Analyzing skill for auto-configuration...
✓ Category: development
✓ Tags: quant, finance, trading, api
✓ Priority: 70
✓ Routing pattern: tushare|股票|量化|策略

Phase 6: Verifying...
✓ Routing test passed: 帮我获取股票数据
✓ Synced to platform

✨ Installation complete!

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Tushare 量化策略 is now ready to use! ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Test it with:
  vibe route "帮我获取茅台最近一年的股价"

View details:
  vibe skills info tushare-quant
```

#### 第3步：开始使用（零配置）

```bash
# AI 自动路由（推荐）
$ vibe route "帮我开发一个双均线交易策略"

╭─────────────────────────────────────────╮
│ ✅ Matched: tushare-quant              │
│ Confidence: 92%                         │
│ Layer: ai_triage                        │
╰─────────────────────────────────────────╯

# 直接在 AI Agent 中使用
# AI Agent 会自动调用正确的技能
```

---

## 📋 详细流程对比

### ❌ 旧流程（复杂，需要手动配置）

```bash
# 1. 创建技能目录
mkdir -p skills/tushare-quant

# 2. 编写 SKILL.md
cat > skills/tushare-quant/SKILL.md << 'EOF'
...手动编写技能定义...
EOF

# 3. 安全审计
vibe analyze security skills/tushare-quant/

# 4. 手动安装
vibe skills install tushare-quant --source ./skills/tushare-quant/

# 5. 手动配置清单
cat > .vibe/manifest.yaml << 'EOF'
...手动编写配置...
EOF

# 6. 手动配置路由规则
cat > .vibe/policies/task-routing.yaml << 'EOF'
...手动编写路由规则...
EOF

# 7. 验证安装
vibe skills verify tushare-quant

# 8. 同步到平台
vibe build --platform claude-code

# 总共 8 个步骤，容易出错！
```

### ✅ 新流程（一键安装，智能配置）

```bash
# 只需要 1 条命令！
vibe skill add tushare

# 系统自动完成：
# ✓ 检测技能类型
# ✓ 安全审计
# ✓ 询问安装范围
# ✓ 安装技能
# ✓ AI 分析生成配置
# ✓ 自动设置优先级和路由
# ✓ 验证和同步
```

---

## 🎯 智能配置说明

### 自动生成的配置

安装后，系统会自动创建 `.vibe/skills/auto-config.yaml`：

```yaml
skills:
  tushare-quant:
    skill_id: tushare-quant
    priority: 70  # AI 根据技能类别自动设定
    enabled: true
    scope: project
    category: development
    tags:
      - quant
      - finance
      - trading
      - api
    routing:
      patterns:
        - .*tushare.*
        - .*股票.*
        - .*量化.*
        - .*策略.*回测
      priority: 70
    metadata:
      auto_configured: true
      confidence: 0.92
      enhanced_at: "2025-04-20T10:30:00"
```

### AI 配置决策

| 技能类别 | 自动优先级 | 典型使用场景 |
|---------|----------|------------|
| debugging | 80 | 错误、故障修复 |
| development | 70 | 功能开发 |
| deployment | 75 | 部署、发布 |
| security | 85 | 安全检查 |
| testing | 65 | 测试、验证 |
| optimization | 60 | 性能优化 |
| review | 50 | 代码审查 |
| documentation | 40 | 文档编写 |

---

## 🔧 高级选项

### 全局安装

```bash
# 安装到全局（所有项目可用）
vibe skill add tushare --global

# 全局技能存储在 ~/.vibe/skills/
```

### 手动配置模式

```bash
# 禁用自动配置，手动设置
vibe skill add tushare --manual-config

# 交互式配置向导：
? What priority should this skill have?
  🔴 Critical (100) - Always use for matching queries
  🟠 High (75) - Prefer over general skills
  🟡 Medium (50) - Default priority
  🟢 Low (25) - Use only if no better match

? Generate automatic routing rules?
> Yes

? Install dependencies?
> Yes (pip install tushare>=1.2.60)
```

### 强制重新安装

```bash
# 覆盖已存在的技能
vibe skill add tushare --force
```

---

## 📦 创建和分发技能

### 创建 .skill 文件

```bash
# 方法1: 从目录打包
vibe skill pack tushare-quant

# 方法2: 从 SKILL.md 创建
vibe skill create --name tushare-quant \
  --description "使用 Tushare API 开发量化策略" \
  --tags "quant,finance"

# 生成 tushare-quant-1.0.0.skill
```

### 发布技能

```bash
# 发布到官方仓库
vibe skill publish tushare-quant-1.0.0.skill \
  --registry official

# 或发布到 GitHub
vibe skill publish tushare-quant-1.0.0.skill \
  --registry github:user/skills
```

### 分发方式

```bash
# 用户可以从多种来源安装：

# 1. 官方仓库（推荐）
vibe skill add tushare

# 2. 本地文件
vibe skill add ./tushare-quant.skill

# 3. URL
vibe skill add https://example.com/tushare-quant.skill

# 4. Git 仓库
vibe skill add github:user/skills/tushare@v1.0.0
```

---

## 🧪 验证和测试

### 查看技能信息

```bash
$ vibe skills info tushare-quant

╭──────────────────────────────────────────╮
│ Tushare 量化策略                          │
├──────────────────────────────────────────┤
│ ID: tushare-quant                        │
│ Type: prompt                             │
│ Namespace: external                      │
│ Version: 1.0.0                           │
│ Author: Your Name                        │
│ Source: .vibe/skills/tushare-quant       │
├──────────────────────────────────────────┤
│ Description                              │
│ 使用 Tushare API 开发量化交易策略         │
├──────────────────────────────────────────┤
│ Intent                                   │
│ 用户需要获取股票数据、开发量化策略或      │
│ 回测交易策略                              │
├──────────────────────────────────────────┤
│ Tags: quant, finance, trading, api       │
╰──────────────────────────────────────────╯
```

### 测试路由

```bash
# 测试不同的查询
vibe route "获取茅台股价"
vibe route "开发双均线策略"
vibe route "回测我的交易策略"
vibe route "计算夏普比率"

# 查看路由统计
vibe route-stats

# 查看偏好学习
vibe preferences

# 查看最常用技能
vibe top-skills
```

---

## ⚙️ 配置管理

### 查看自动配置

```bash
# 查看所有自动配置
cat .vibe/skills/auto-config.yaml

# 或使用命令
vibe config show --skill tushare-quant
```

### 手动调整配置

```yaml
# 编辑 .vibe/skills/auto-config.yaml
skills:
  tushare-quant:
    priority: 85  # 提高优先级
    routing:
      patterns:
        - .*股票.*  # 添加更多模式
        - .*投资.*
        - .*交易.*
```

### 禁用技能

```bash
# 临时禁用
vibe skill disable tushare-quant

# 永久禁用
vibe skill remove tushare-quant
```

---

## 🎁 实际使用示例

### 在量化项目中使用

```bash
# 初始化量化项目
mkdir quant-strategy && cd quant-strategy
vibe init

# 安装 Tushare 技能
vibe skill add tushare

# 开始使用
vibe route "帮我获取茅台最近三年的股价数据"
# → 匹配到 tushare-quant (95% 置信度)

vibe route "开发一个MACD策略"
# → 匹配到 tushare-quant (90% 置信度)

vibe route "我的策略收益怎么样"
# → 匹配到 tushare-quant (88% 置信度)
```

### 在 Claude Code 中使用

安装后，Claude Code 会自动感知新技能：

```
User: 帮我获取茅台最近一年的股价数据

Claude Code: 我检测到你想使用 Tushare 获取股票数据。
让我使用 tushare-quant 技能来帮你...

[执行技能代码]

User: 再帮我开发一个双均线策略

Claude Code: 好的，我会使用 tushare-quant 技能
来开发5日和20日均线的交易策略...
```

---

## 📊 管理已安装的技能

```bash
# 列出所有技能
vibe skills list --all

# 列出项目技能
vibe skills list

# 检查技能健康
vibe skills health

# 同步到平台
vibe skills sync claude-code

# 查看技能状态
vibe inspect
```

---

## 🚨 故障排除

### 技能未被识别

```bash
# 检查技能是否已安装
vibe skills verify tushare-quant

# 重新安装
vibe skill add tushare --force

# 检查路由配置
vibe route "test" --explain
```

### 路由不匹配

```bash
# 查看路由详情
vibe route "你的查询" --explain

# 调整优先级
vibe config set tushare-quant.priority 85

# 添加自定义路由模式
vibe config add tushare-quant.patterns ".*你的关键词.*"
```

### 依赖问题

```bash
# 检查依赖
vibe skill check-deps tushare-quant

# 安装依赖
pip install -r .vibe/skills/tushare-quant/requirements.txt
```

---

## 🎯 最佳实践

1. **使用官方技能仓库**
   ```bash
   vibe skill add tushare  # 推荐
   # 而不是 vibe skill add https://...
   ```

2. **项目级 vs 全局**
   - 项目特定技能 → 项目级
   - 通用工具技能 → 全局

3. **定期更新**
   ```bash
   vibe skill update tushare
   ```

4. **贡献技能**
   ```bash
   vibe skill publish my-skill --registry official
   ```

---

**总结**：从 8 个手动步骤简化为 1 条命令，AI 自动完成所有配置工作！
