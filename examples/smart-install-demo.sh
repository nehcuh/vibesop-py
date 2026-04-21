#!/bin/bash
# VibeSOP 智能技能安装 - 完整使用示例

echo "==================================="
echo "VibeSOP 智能技能安装示例"
echo "场景：安装 Tushare 量化交易技能"
echo "==================================="
echo ""

# === 步骤 1: 初始化项目 ===
echo "📁 步骤 1: 创建量化交易项目"
mkdir -p quant-trading && cd quant-trading
echo "✓ 项目目录创建成功"
echo ""

# === 步骤 2: 初始化 VibeSOP ===
echo "🔧 步骤 2: 初始化 VibeSOP 配置"
vibe init --minimal
echo "✓ VibeSOP 配置完成"
echo ""

# === 步骤 3: 安装 Tushare 技能 ===
echo "📦 步骤 3: 安装 Tushare 量化技能"
echo "执行命令: vibe skill add tushare"
echo ""
echo "------- 安装过程演示 -------"
echo ""
echo "🚀 Smart Skill Installation"
echo ""
echo "Phase 1: Detecting skill..."
echo "✓ Detected: Tushare 量化策略"
echo "  ID: tushare-quant"
echo "  Description: 使用 Tushare API 开发量化交易策略"
echo ""
echo "Phase 2: Security audit..."
echo "✓ Security audit passed"
echo ""
echo "Phase 3: Installation scope"
echo "? Where should this skill be installed?"
echo "  🎯 Project-level (recommended"
echo "  🌐 Global (available to all projects)"
echo "> [User selects: project]"
echo ""
echo "Phase 4: Installing project..."
echo "✓ Installed to: .vibe/skills/tushare-quant"
echo ""
echo "Phase 5: Auto-configuring..."
echo "✓ Category: development"
echo "✓ Tags: quant, finance, trading, api"
echo "✓ Priority: 70"
echo "✓ Routing pattern: tushare|股票|量化|策略"
echo ""
echo "Phase 6: Verifying..."
echo "✓ Routing test passed: 帮我获取股票数据"
echo "✓ Synced to platform"
echo ""
echo "✨ Installation complete!"
echo "------- 安装过程演示结束 -------"
echo ""

# 模拟安装成功
echo "✓ Tushare 技能安装成功"
echo ""

# === 步骤 4: 验证安装 ===
echo "🧪 步骤 4: 验证技能安装"
echo ""
echo "4.1 查看技能信息："
echo "  $ vibe skills info tushare-quant"
echo ""
echo "  输出："
echo "  ╭──────────────────────────────────────────╮"
echo "  │ Tushare 量化策略                          │"
echo "  ├──────────────────────────────────────────┤"
echo "  │ ID: tushare-quant                        │"
echo "  │ Type: prompt                             │"
echo "  │ Version: 1.0.0                           │"
echo "  │ Description: 使用 Tushare API 开发...    │"
echo "  │ Tags: quant, finance, trading            │"
echo "  ╰──────────────────────────────────────────╯"
echo ""

echo "4.2 测试路由："
echo "  $ vibe route \"帮我获取茅台最近一年的股价\""
echo ""
echo "  输出："
echo "  ╭─────────────────────────────────────────╮"
echo "  │ ✅ Matched: tushare-quant              │"
echo "  │ Confidence: 95%                         │"
echo "  │ Layer: ai_triage                        │"
echo "  ╰─────────────────────────────────────────╯"
echo ""

# === 步骤 5: 实际使用 ===
echo "🚀 步骤 5: 开始使用"
echo ""
echo "5.1 获取股票数据："
echo "  User: 帮我获取茅台最近三年的股价数据"
echo "  AI: [自动使用 tushare-quant 技能]"
echo "  [执行代码，获取数据]"
echo ""

echo "5.2 开发交易策略："
echo "  User: 帮我开发一个双均线交易策略"
echo "  AI: [自动使用 tushare-quant 技能]"
echo "  [生成策略代码，回测结果]"
echo ""

echo "5.3 回测策略："
echo "  User: 回测这个策略"
echo "  AI: [自动使用 tushare-quant 技能]"
echo "  [运行回测，生成报告]"
echo ""

# === 步骤 6: 查看自动配置 ===
echo "⚙️  步骤 6: 查看自动生成的配置"
echo ""
echo "配置文件: .vibe/skills/auto-config.yaml"
echo ""
cat << 'EOF'
skills:
  tushare-quant:
    skill_id: tushare-quant
    priority: 70
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
EOF
echo ""

# === 步骤 7: 查看统计 ===
echo "📊 步骤 7: 查看使用统计"
echo ""
echo "7.1 路由统计："
echo "  $ vibe route-stats"
echo ""
echo "  输出："
echo "  Total routes: 15"
echo "  Most used: tushare-quant (8 times)"
echo ""

echo "7.2 偏好学习："
echo "  $ vibe preferences"
echo ""
echo "  输出："
echo "  ✓ Learning from your selections"
echo "  tushare-quant: 92% match rate"
echo ""

# === 完成 ===
echo "==================================="
echo "✅ 安装和配置完成！"
echo ""
echo "下一步："
echo "  1. 配置 TUSHARE_TOKEN 环境变量"
echo "  2. 开始开发量化策略"
echo "  3. 使用 'vibe route' 进行智能路由"
echo ""
echo "文档："
echo "  - vibe skills info tushare-quant"
echo "  - https://docs.vibesop.dev/quant"
echo "==================================="
echo ""
