# VibeSOP .skill 文件格式规范

## 概述

`.skill` 文件是 VibeSOP 的**单文件技能分发格式**，包含技能的所有定义和元数据，支持一键安装。

## 文件结构

`.skill` 文件本质上是一个 **gzip 压缩的 tarball** (.tar.gz)，包含以下结构：

```
tushare.skill/
├── SKILL.md           # 技能定义（必需）
├── config.yaml        # 默认配置（可选）
├── requirements.txt   # Python依赖（可选）
├── hooks/
│   ├── pre_install.sh  # 安装前钩子（可选）
│   └── post_install.sh # 安装后钩子（可选）
└── tests/
    └── test_skill.py   # 测试文件（可选）
```

## SKILL.md 格式

```markdown
---
id: tushare-quant
name: Tushare 量化策略
description: 使用 Tushare API 开发和回测量化交易策略
version: 1.0.0
author: Your Name <email@example.com>
namespace: external
tags: [quant, finance, trading, tushare]
skill_type: prompt
trigger_when: 用户需要获取股票数据、开发量化策略或回测交易策略
priority: 75
category: development
routing_patterns:
  - .*tushare.*
  - .*股票.*
  - .*量化.*
  - .*策略.*回测
dependencies:
  - tushare >= 1.2.60
  - pandas >= 1.5.0
env_vars:
  - TUSHARE_TOKEN
---

# Tushare 量化策略开发

## 技能描述

使用 Tushare API 接口开发和回测量化交易策略。

## 主要功能

1. **数据获取**
   - 股票行情数据
   - 财务数据
   - 宏观经济数据

2. **策略开发**
   - 技术指标计算
   - 交易信号生成
   - 风险控制

3. **回测分析**
   - 历史数据回测
   - 收益率计算
   - 风险指标评估

## 使用示例

### 获取股票数据

**用户**: "帮我获取茅台最近一年的股价数据"

**执行**:
```python
import tushare as ts

ts.set_token('your_token')
pro = ts.pro_api()

df = pro.daily(
    ts_code='600519.SH',
    start_date='20240101',
    end_date='20250101'
)
```

### 开发双均线策略

**用户**: "开发一个5日和20日均线策略"

**执行**:
1. 获取历史数据
2. 计算 MA5 和 MA20
3. 生成金叉死叉信号
4. 回测策略收益

## 配置要求

需要在环境变量中配置：
```bash
export TUSHARE_TOKEN=your_token_here
```

## 限制和注意事项

- API 有积分限制
- 建议缓存历史数据
- 注意请求频率控制

---
*Skill Format Version: 1.0*
*Generated: 2025-04-20*
```

## config.yaml 格式（可选）

```yaml
# 默认配置
defaults:
  # 技能优先级
  priority: 75

  # 路由配置
  routing:
    # 自动匹配模式
    auto_patterns: true

    # 自定义模式
    custom_patterns:
      - .*获取.*股票.*
      - .*量化.*策略

  # 执行配置
  execution:
    # 超时时间（秒）
    timeout: 60

    # 最大重试次数
    max_retries: 3

  # 安全配置
  security:
    # 允许的外部 API
    allow_apis:
      - "tushare.pro"

    # 需要的环境变量
    require_env:
      - TUSHARE_TOKEN
```

## requirements.txt 格式（可选）

```
tushare>=1.2.60
pandas>=1.5.0
numpy>=1.23.0
matplotlib>=3.6.0
```

## 钩子脚本（可选）

### pre_install.sh

```bash
#!/bin/bash
# 安装前检查

# 检查 Python 版本
python_version=$(python --version 2>&1 | grep -oP '\d+\.\d+')
if (( $(echo "$python_version < 3.8" | bc -l) )); then
    echo "Error: Python 3.8+ required"
    exit 1
fi

echo "Pre-install checks passed"
```

### post_install.sh

```bash
#!/bin/bash
# 安装后配置

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Checking TUSHARE_TOKEN..."
if [ -z "$TUSHARE_TOKEN" ]; then
    echo "Warning: TUSHARE_TOKEN not set"
    echo "Please set: export TUSHARE_TOKEN=your_token"
fi

echo "Installation complete!"
```

## 创建 .skill 文件

```bash
# 方法1: 手动打包
mkdir -p tushare.skill
cp SKILL.md tushare.skill/
cp config.yaml tushare.skill/
cp requirements.txt tushare.skill/
tar -czf tushare.skill -C tushare.skill .

# 方法2: 使用 vibe 命令（推荐）
vibe skill pack tushare
```

## 验证 .skill 文件

```bash
# 检查文件格式
vibe skill validate tushare.skill

# 查看技能信息
vibe skill info tushare.skill

# 测试安装（不实际安装）
vibe skill test-install tushare.skill --dry-run
```

## 版本控制

建议使用语义化版本号（Semantic Versioning）：
- **MAJOR.MINOR.PATCH** (如 1.2.3)
- MAJOR: 不兼容的 API 变更
- MINOR: 向后兼容的功能新增
- PATCH: 向后兼容的问题修复

## 分发

### 官方技能仓库

```bash
# 发布到官方仓库
vibe skill publish tushare.skill --registry official

# 从官方仓库安装
vibe skill add tushare
```

### 第三方分发

```bash
# 从 URL 安装
vibe skill add https://example.com/skills/tushare.skill

# 从 GitHub 安装
vibe skill add github:user/repo/skills/tushare@v1.0.0
```

## 安全考虑

1. **代码签名**
   ```bash
   # 签名技能
   vibe skill sign tushare.skill --key private.pem

   # 验证签名
   vibe skill verify tushare.skill --key public.pem
   ```

2. **安全审计**
   - 所有技能在安装前自动审计
   - 高风险技能需要用户确认
   - 支持 allow-list 和 block-list

3. **沙箱执行**
   - 技能受限环境执行
   - 文件系统访问控制
   - 网络访问控制

## 示例：完整的 tushare.skill

```bash
# 1. 创建技能目录
mkdir -p tushare.skill

# 2. 创建 SKILL.md
cat > tushare.skill/SKILL.md << 'EOF'
---
id: tushare-quant
name: Tushare 量化策略
description: 使用 Tushare API 开发量化交易策略
version: 1.0.0
author: Your Name
tags: [quant, finance]
priority: 75
---

# Tushare 量化策略

使用 Tushare API 获取股票数据、开发交易策略。
EOF

# 3. 创建配置
cat > tushare.skill/config.yaml << 'EOF'
defaults:
  priority: 75
  routing:
    auto_patterns: true
EOF

# 4. 创建依赖
cat > tushare.skill/requirements.txt << 'EOF'
tushare>=1.2.60
pandas>=1.5.0
EOF

# 5. 打包
tar -czf tushare.skill -C tushare.skill .

# 6. 验证
vibe skill validate tushare.skill

# 7. 安装
vibe skill add tushare.skill
```

---

**规范版本**: 1.0
**最后更新**: 2025-04-20
