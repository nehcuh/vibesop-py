# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-07-21 S35 [vibesop-py] 文档审计 + CI 修复 + v8.0.0 发布

**Session Summary**:
- 审计并修复全部 87 个文档文件（版本号、架构、命令引用），归档 11 个历史文件
- Dashboard deps 移入 core，开箱即用
- 修复 3 个 Windows 测试（tick lock + encoding）
- 修复 CI lint（29 errors）和 release workflow（SHA 过期）
- v8.0.0 成功发布到 PyPI

**Key Decisions**:
- Action SHAs: 非安全关键用 version tag（@v2），安全关键可 pin SHA
- Windows 编码: 跨平台代码必须显式 `encoding="utf-8"`
- Dashboard: fastapi/uvicorn 入 core deps，默认安装

**Next Steps**:
- 全局工具重装: `uv tool install --reinstall /path/to/vibesop-py`
- 旧项目需手动创建 config.toml 启用 analytics

### 2026-07-21 S33 [vibesop-py] Bootstrap 技能包自动安装 + Analytics 默认启用

- 修复 bootstrap.sh 未调用 vibe install --auto
- init_support.py 默认 analytics.enabled=true
- 路由 analytics 默认 opt-in → init 模板已修复
<!-- handoff:end -->
