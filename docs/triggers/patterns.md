# VibeSOP Trigger Patterns - Complete Reference

> **Version**: 2.0.0
> **Last Updated**: 2026-04-04
> **Total Patterns**: 30

---

## Quick Reference

| Category | Patterns | Priority Range |
|----------|----------|----------------|
| 🔒 Security | 5 | 90-100 |
| ⚙️ Config | 5 | 90-100 |
| 🛠️ Dev | 8 | 70-95 |
| 📚 Docs | 6 | 75-90 |
| 📁 Project | 6 | 70-90 |

---

## Security Patterns (5 patterns)

### 1. Security Scan

**Pattern ID**: `security/scan`
**Priority**: 100
**Confidence Threshold**: 0.6

**Description**: Detects security scanning and vulnerability detection requests

**Keywords**:
- English: scan, scanning, security, vulnerability
- Chinese: 漏洞, 扫描

**Regex Patterns**:
- `scan.*security`
- `security.*scan`
- `扫描.*安全`
- `安全.*扫描`
- `vulnerability.*scan`

**Examples**:
- "scan for security vulnerabilities"
- "扫描安全漏洞"
- "check for security issues"
- "security vulnerability scan"

**Action**:
- **Skill**: `/security/scan`
- **Workflow**: `security-review`

---

### 2. Security Analyze

**Pattern ID**: `security/analyze`
**Priority**: 95
**Confidence Threshold**: 0.65

**Description**: Detects security analysis and threat assessment requests

**Keywords**:
- English: analyze, analysis, threat, assess, risk
- Chinese: 分析, 威胁, 风险, 评估

**Regex Patterns**:
- `analyze.*security`
- `security.*analysis`
- `threat.*analysis`
- `分析.*安全`
- `安全.*分析`

**Examples**:
- "analyze security threats"
- "分析安全威胁"
- "assess security risks"
- "threat analysis"

**Action**:
- **Skill**: `/security/analyze`

---

### 3. Security Audit

**Pattern ID**: `security/audit`
**Priority**: 90
**Confidence Threshold**: 0.7

**Description**: Detects security audit and compliance checking requests

**Keywords**:
- English: audit, compliance, check, review
- Chinese: 审计, 合规, 检查

**Regex Patterns**:
- `security.*audit`
- `compliance.*check`
- `安全.*审计`
- `合规.*检查`

**Examples**:
- "run security audit"
- "安全审计"
- "check compliance"
- "security compliance check"

**Action**:
- **Skill**: `/security/audit`

---

### 4. Security Fix

**Pattern ID**: `security/fix`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects security fix and remediation requests

**Keywords**:
- English: fix, patch, remediate, repair
- Chinese: 修复, 补丁, 修补

**Regex Patterns**:
- `fix.*security`
- `security.*fix`
- `patch.*vulnerability`
- `修复.*安全`
- `安全.*修复`

**Examples**:
- "fix security vulnerabilities"
- "修复安全漏洞"
- "patch security issues"
- "remediate threats"

**Action**:
- **Skill**: `/security/fix`

---

### 5. Security Report

**Pattern ID**: `security/report`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects security reporting and documentation requests

**Keywords**:
- English: report, document, summary, findings
- Chinese: 报告, 文档, 总结

**Regex Patterns**:
- `security.*report`
- `vulnerability.*report`
- `generate.*security.*report`
- `安全.*报告`
- `生成.*安全.*报告`

**Examples**:
- "generate security report"
- "生成安全报告"
- "document security findings"
- "security scan report"

**Action**:
- **Skill**: `/security/report`

---

## Config Patterns (5 patterns)

### 6. Config Deploy

**Pattern ID**: `config/deploy`
**Priority**: 100
**Confidence Threshold**: 0.6

**Description**: Detects configuration deployment requests

**Keywords**:
- English: deploy, deployment, apply, push, config
- Chinese: 配置, 部署, 应用, 推送

**Regex Patterns**:
- `deploy.*config`
- `config.*deploy`
- `apply.*config`
- `部署.*配置`
- `配置.*部署`

**Examples**:
- "deploy configuration"
- "部署配置"
- "apply config changes"
- "push configuration to production"

**Action**:
- **Skill**: `/config/deploy`
- **Workflow**: `config-deploy`

---

### 7. Config Validate

**Pattern ID**: `config/validate`
**Priority**: 95
**Confidence Threshold**: 0.6

**Description**: Detects configuration validation requests

**Keywords**:
- English: validate, validation, verify, check
- Chinese: 验证, 校验, 检查

**Regex Patterns**:
- `validate.*config`
- `config.*validation`
- `verify.*config`
- `验证.*配置`
- `配置.*验证`

**Examples**:
- "validate configuration"
- "验证配置"
- "check config validity"
- "verify configuration files"

**Action**:
- **Skill**: `/config/validate`

---

### 8. Config Render

**Pattern ID**: `config/render`
**Priority**: 90
**Confidence Threshold**: 0.6

**Description**: Detects configuration rendering requests

**Keywords**:
- English: render, generate, template, expand
- Chinese: 渲染, 生成, 模板

**Regex Patterns**:
- `render.*config`
- `generate.*config`
- `config.*template`
- `渲染.*配置`
- `生成.*配置`

**Examples**:
- "render configuration files"
- "渲染配置"
- "generate config from template"
- "expand configuration"

**Action**:
- **Skill**: `/config/render`

---

### 9. Config Diff

**Pattern ID**: `config/diff`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects configuration difference requests

**Keywords**:
- English: diff, compare, difference, change
- Chinese: 差异, 比较, 变化

**Regex Patterns**:
- `config.*diff`
- `diff.*config`
- `compare.*config`
- `配置.*差异`
- `比较.*配置`

**Examples**:
- "show config differences"
- "显示配置差异"
- "compare configurations"
- "config diff"

**Action**:
- **Skill**: `/config/diff`

---

### 10. Config Backup

**Pattern ID**: `config/backup`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects configuration backup requests

**Keywords**:
- English: backup, save, archive, snapshot
- Chinese: 备份, 保存, 归档

**Regex Patterns**:
- `backup.*config`
- `config.*backup`
- `save.*config`
- `备份.*配置`
- `配置.*备份`

**Examples**:
- "backup configuration"
- "备份配置"
- "save config files"
- "create config snapshot"

**Action**:
- **Skill**: `/config/backup`

---

## Dev Patterns (8 patterns)

### 11. Dev Build

**Pattern ID**: `dev/build`
**Priority**: 95
**Confidence Threshold**: 0.6

**Description**: Detects build requests

**Keywords**:
- English: build, compile, make, construct
- Chinese: 构建, 编译

**Regex Patterns**:
- `build.*project`
- `compile.*code`
- `make.*build`
- `构建.*项目`
- `编译.*代码`

**Examples**:
- "build the project"
- "构建项目"
- "compile code"
- "run build"

**Action**:
- **Skill**: `/dev/build`

---

### 12. Dev Test

**Pattern ID**: `dev/test`
**Priority**: 95
**Confidence Threshold**: 0.6

**Description**: Detects testing requests

**Keywords**:
- English: test, testing, unit test, integration test
- Chinese: 测试, 单元测试

**Regex Patterns**:
- `run.*test`
- `execute.*test`
- `test.*suite`
- `运行.*测试`
- `执行.*测试`

**Examples**:
- "run tests"
- "运行测试"
- "execute unit tests"
- "run test suite"

**Action**:
- **Skill**: `/dev/test`

---

### 13. Dev Debug

**Pattern ID**: `dev/debug`
**Priority**: 90
**Confidence Threshold**: 0.6

**Description**: Detects debugging requests

**Keywords**:
- English: debug, debugging, troubleshoot, fix error
- Chinese: 调试, 排错, 故障排除

**Regex Patterns**:
- `debug.*code`
- `fix.*error`
- `troubleshoot`
- `调试.*代码`
- `修复.*错误`

**Examples**:
- "debug this error"
- "调试错误"
- "troubleshoot issue"
- "debug code"

**Action**:
- **Skill**: `/dev/debug`

---

### 14. Dev Refactor

**Pattern ID**: `dev/refactor`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects refactoring requests

**Keywords**:
- English: refactor, restructure, reorganize, cleanup
- Chinese: 重构, 重组, 清理

**Regex Patterns**:
- `refactor.*code`
- `restructure.*code`
- `code.*cleanup`
- `重构.*代码`
- `清理.*代码`

**Examples**:
- "refactor code"
- "重构代码"
- "restructure project"
- "code cleanup"

**Action**:
- **Skill**: `/dev/refactor`

---

### 15. Dev Lint

**Pattern ID**: `dev/lint`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects linting requests

**Keywords**:
- English: lint, linter, check style, code quality
- Chinese: 代码检查, 风格检查

**Regex Patterns**:
- `run.*lint`
- `lint.*code`
- `check.*style`
- `运行.*lint`
- `代码.*检查`

**Examples**:
- "lint code"
- "运行lint"
- "check code style"
- "run linter"

**Action**:
- **Skill**: `/dev/lint`

---

### 16. Dev Format

**Pattern ID**: `dev/format`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects code formatting requests

**Keywords**:
- English: format, formatter, prettify, beautify
- Chinese: 格式化, 美化

**Regex Patterns**:
- `format.*code`
- `prettify.*code`
- `code.*formatter`
- `格式化.*代码`
- `美化.*代码`

**Examples**:
- "format code"
- "格式化代码"
- "prettify code"
- "run formatter"

**Action**:
- **Skill**: `/dev/format`

---

### 17. Dev Install

**Pattern ID**: `dev/install`
**Priority**: 75
**Confidence Threshold**: 0.6

**Description**: Detects installation requests

**Keywords**:
- English: install, installation, setup, dependencies
- Chinese: 安装, 安装依赖

**Regex Patterns**:
- `install.*dependencies`
- `setup.*project`
- `install.*packages`
- `安装.*依赖`
- `安装.*包`

**Examples**:
- "install dependencies"
- "安装依赖"
- "setup project"
- "install packages"

**Action**:
- **Skill**: `/dev/install`

---

### 18. Dev Clean

**Pattern ID**: `dev/clean`
**Priority**: 70
**Confidence Threshold**: 0.6

**Description**: Detects cleanup requests

**Keywords**:
- English: clean, cleanup, clear, remove
- Chinese: 清理, 清除, 删除

**Regex Patterns**:
- `clean.*project`
- `cleanup.*build`
- `clear.*cache`
- `清理.*项目`
- `清除.*缓存`

**Examples**:
- "clean project"
- "清理项目"
- "cleanup build artifacts"
- "clear cache"

**Action**:
- **Skill**: `/dev/clean`

---

## Docs Patterns (6 patterns)

### 19. Docs Generate

**Pattern ID**: `docs/generate`
**Priority**: 90
**Confidence Threshold**: 0.6

**Description**: Detects documentation generation requests

**Keywords**:
- English: generate, create, documentation, docs
- Chinese: 生成, 创建, 文档

**Regex Patterns**:
- `generate.*docs`
- `create.*documentation`
- `generate.*documentation`
- `生成.*文档`
- `创建.*文档`

**Examples**:
- "generate documentation"
- "生成文档"
- "create API docs"
- "generate README"

**Action**:
- **Skill**: `/docs/generate`

---

### 20. Docs Update

**Pattern ID**: `docs/update`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects documentation update requests

**Keywords**:
- English: update, modify, refresh, revise
- Chinese: 更新, 修改, 刷新

**Regex Patterns**:
- `update.*docs`
- `modify.*documentation`
- `refresh.*docs`
- `更新.*文档`
- "修改.*文档"

**Examples**:
- "update documentation"
- "更新文档"
- "modify docs"
- "refresh README"

**Action**:
- **Skill**: `/docs/update`

---

### 21. Docs Format

**Pattern ID**: `docs/format`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects documentation formatting requests

**Keywords**:
- English: format, formatting, style, layout
- Chinese: 格式化, 排版

**Regex Patterns**:
- `format.*docs`
- `docs.*formatting`
- `style.*documentation`
- `格式化.*文档`
- "文档.*排版"

**Examples**:
- "format documentation"
- "格式化文档"
- "apply doc style"
- "format docs"

**Action**:
- **Skill**: `/docs/format`

---

### 22. Docs Readme

**Pattern ID**: `docs/readme`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects README-specific requests

**Keywords**:
- English: readme, readme.md, introduction, overview
- Chinese: readme, 简介, 概述

**Regex Patterns**:
- `update.*readme`
- `create.*readme`
- `generate.*readme`
- `更新.*readme`
- "创建.*readme"

**Examples**:
- "update readme"
- "更新readme"
- "create README"
- "generate readme file"

**Action**:
- **Skill**: `/docs/readme`

---

### 23. Docs API

**Pattern ID**: `docs/api`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects API documentation requests

**Keywords**:
- English: api, api docs, endpoint documentation
- Chinese: api, 接口文档

**Regex Patterns**:
- `generate.*api.*docs`
- `api.*documentation`
- `document.*api`
- "生成.*api.*文档"
- "api.*文档"

**Examples**:
- "generate API documentation"
- "生成API文档"
- "document API endpoints"
- "create API docs"

**Action**:
- **Skill**: `/docs/api`

---

### 24. Docs Changelog

**Pattern ID**: `docs/changelog`
**Priority**: 75
**Confidence Threshold**: 0.6

**Description**: Detects changelog requests

**Keywords**:
- English: changelog, changes, history, release notes
- Chinese: 更新日志, 变更历史

**Regex Patterns**:
- `generate.*changelog`
- `update.*changelog`
- `create.*changelog`
- "生成.*更新日志"
- "创建.*changelog"

**Examples**:
- "generate changelog"
- "生成更新日志"
- "update CHANGELOG"
- "create release notes"

**Action**:
- **Skill**: `/docs/changelog`

---

## Project Patterns (6 patterns)

### 25. Project Init

**Pattern ID**: `project/init`
**Priority**: 90
**Confidence Threshold**: 0.6

**Description**: Detects project initialization requests

**Keywords**:
- English: init, initialize, create, new project, setup
- Chinese: 初始化, 创建, 新项目

**Regex Patterns**:
- `init.*project`
- `initialize.*project`
- `create.*new.*project`
- "初始化.*项目"
- "创建.*新项目"

**Examples**:
- "initialize new project"
- "初始化新项目"
- "create new project"
- "setup project"

**Action**:
- **Skill**: `/project/init`

---

### 26. Project Migrate

**Pattern ID**: `project/migrate`
**Priority**: 85
**Confidence Threshold**: 0.6

**Description**: Detects project migration requests

**Keywords**:
- English: migrate, migration, upgrade, update
- Chinese: 迁移, 升级, 更新

**Regex Patterns**:
- `migrate.*project`
- `project.*migration`
- `upgrade.*project`
- "迁移.*项目"
- "升级.*项目"

**Examples**:
- "migrate project"
- "迁移项目"
- "upgrade to new version"
- "project migration"

**Action**:
- **Skill**: `/project/migrate`

---

### 27. Project Audit

**Pattern ID**: `project/audit`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects project audit requests

**Keywords**:
- English: audit, review, analysis, assessment
- Chinese: 审计, 审查, 分析

**Regex Patterns**:
- `project.*audit`
- `audit.*project`
- `project.*review`
- "项目.*审计"
- "审查.*项目"

**Examples**:
- "project audit"
- "项目审计"
- "review project structure"
- "assess project"

**Action**:
- **Skill**: `/project/audit`

---

### 28. Project Upgrade

**Pattern ID**: `project/upgrade`
**Priority**: 80
**Confidence Threshold**: 0.6

**Description**: Detects project upgrade requests

**Keywords**:
- English: upgrade, update dependencies, bump version
- Chinese: 升级, 更新依赖

**Regex Patterns**:
- `upgrade.*dependencies`
- `update.*packages`
- `bump.*version`
- "升级.*依赖"
- "更新.*包"

**Examples**:
- "upgrade dependencies"
- "升级依赖"
- "update packages"
- "bump version"

**Action**:
- **Skill**: `/project/upgrade`

---

### 29. Project Clean

**Pattern ID**: `project/clean`
**Priority**: 75
**Confidence Threshold**: 0.6

**Description**: Detects project cleanup requests

**Keywords**:
- English: clean, cleanup, remove, delete
- Chinese: 清理, 删除, 移除

**Regex Patterns**:
- `clean.*project`
- `cleanup.*workspace`
- `remove.*files`
- "清理.*项目"
- "删除.*文件"

**Examples**:
- "clean project"
- "清理项目"
- "cleanup workspace"
- "remove unused files"

**Action**:
- **Skill**: `/project/clean`

---

### 30. Project Status

**Pattern ID**: `project/status`
**Priority**: 70
**Confidence Threshold**: 0.6

**Description**: Detects project status requests

**Keywords**:
- English: status, check, info, information
- Chinese: 状态, 检查, 信息

**Regex Patterns**:
- `project.*status`
- `check.*project`
- `project.*info`
- "项目.*状态"
- "检查.*项目"

**Examples**:
- "project status"
- "项目状态"
- "check project"
- "show project info"

**Action**:
- **Skill**: `/project/status`

---

## Usage Examples

### Finding Patterns

```python
from vibesop.triggers import DEFAULT_PATTERNS

# List all security patterns
security_patterns = [
    p for p in DEFAULT_PATTERNS
    if p.category.value == "security"
]

for pattern in security_patterns:
    print(f"{pattern.pattern_id}: {pattern.name}")
    print(f"  Priority: {pattern.priority}")
    print(f"  Examples: {', '.join(pattern.examples[:2])}")
```

### Pattern Matching

```python
from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS

detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

# Test which pattern matches
queries = [
    "scan for security vulnerabilities",
    "deploy configuration",
    "run tests",
    "generate documentation",
    "init new project"
]

for query in queries:
    match = detector.detect_best(query)
    if match:
        print(f"'{query}' → {match.pattern_id} ({match.confidence:.2%})")
```

### Custom Confidence Thresholds

```python
# High-priority patterns have higher default confidence
high_priority = [p for p in DEFAULT_PATTERNS if p.priority >= 90]
print(f"High priority patterns: {len(high_priority)}")

# Patterns with lower confidence threshold
permissive = [p for p in DEFAULT_PATTERNS if p.confidence_threshold <= 0.5]
print(f"Permissive patterns: {len(permissive)}")
```

---

## Pattern Selection Guide

### When to Use Which Pattern

| Query Type | Best Pattern | Why |
|------------|-------------|-----|
| "scan security" | `security/scan` | High priority (100), exact keywords |
| "check security" | `security/scan` | Semantic match to scan |
| "deploy config" | `config/deploy` | High priority (100), config+deploy |
| "run tests" | `dev/test` | Direct keyword match |
| "generate docs" | `docs/generate` | Direct keyword match |
| "init project" | `project/init` | Direct keyword match |

### Priority Ordering

Patterns are checked in priority order (100 → 1):

```
1. Priority 100: security/scan, config/deploy
2. Priority 95: security/analyze, dev/build, dev/test
3. Priority 90: security/audit, config/validate, dev/debug
4. Priority 80-85: Other specialized patterns
5. Priority 70-75: General purpose patterns
```

---

## Extending Patterns

See [API Documentation](./api.md) for how to create custom patterns.

```python
from vibesop.triggers.models import TriggerPattern, PatternCategory

custom_pattern = TriggerPattern(
    pattern_id="myapp/deploy",
    name="MyApp Deploy",
    description="Deploy MyApp to production",
    category=PatternCategory.CONFIG,
    keywords=["deploy", "myapp", "production"],
    skill_id="/myapp/deploy",
    priority=95,
    confidence_threshold=0.6,
    examples=["deploy myapp", "myapp to production"]
)
```

---

*Last updated: 2026-04-04*
