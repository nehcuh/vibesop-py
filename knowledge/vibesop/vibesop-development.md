---
name: vibesop-development
description: VibeSOP 开发指南 — uv 环境、pytest 测试（约 6300 用例/73% 覆盖率门禁）、ruff/basedpyright/bandit 质量链、GitHub Actions CI（Ubuntu+Windows 双平台门禁）、版本发布流程
type: domain_knowledge
tags:
  - vibesop
  - development
  - testing
  - ci
---

# VibeSOP 开发指南

## 环境与构建

```bash
# 开发环境（一律用 uv，不用 pip）
uv sync --extra dev

# 构建 wheel
uv build

# 安装为 CLI
uv tool install .
```

构建系统 hatchling；CLI 框架 Typer + Rich；校验 Pydantic v2。

## 测试

```bash
uv run pytest                                    # 全量
uv run pytest --cov=src/vibesop --cov-report=term  # 带覆盖率
uv run pytest tests/path/to/test_file.py          # 单文件
uv run pytest -m "not benchmark and not slow"     # 跳过基准/慢测
```

- 规模约 6300+ 用例，**覆盖率门禁 ≥73%（分支覆盖）**
- pytest-xdist 并行加速；pytest-asyncio / pytest-mock 配套
- 注意：个别 embedding 相关测试会触发 HuggingFace 模型下载，离线环境设 `HF_HUB_OFFLINE=1`
- 微基准测试在 CI 共享 runner 上用宽松预算（p95 环境分级），本地跑用严格预算——绝对 µs 阈值在共享 runner 必假警

## 质量链

```bash
uv run ruff check src/ tests/       # lint（行宽 100，双引号，isort）
uv run basedpyright src/            # 严格类型检查
uv run bandit -c pyproject.toml -r src/   # 安全审计
```

编码标准：Python 3.12+ 现代语法（match/case、`X | None`）；所有公开函数带完整类型注解；snake_case/PascalCase/UPPER_CASE 命名；模块 `__all__` 显式导出；Google 风格 docstring；异常统一走 `vibesop.core.exceptions` 层级。

## CI（GitHub Actions）

- 工作流 `.github/workflows/ci.yml`：**Ubuntu + Windows 双平台** × Python 3.12/3.13 矩阵
- Windows job 是 **required gate**——红灯直接阻塞发布链（ci.yml 被 release.yml 以 workflow_call 复用为 ci-gate）
- 两个文档检查器也在门禁内：`check_doc_versions.py`（版本号一致性）与 `check_docs.py`（链接与锚点有效性）
- 经验教训：`continue-on-error` 下 run 级 success 会吞 job 级红灯，数"连续绿"必须查 job 级（`gh run view --json jobs`）

## 版本与发布

- 版本 SoT：`pyproject.toml`；README 徽章、docs 全部由 `check_doc_versions.py` 校验一致（23 个文件）
- CHANGELOG 遵循 Keep a Changelog；发布 = PyPI + GitHub Release 双落地
- 版本号缓升有坑：`uv tool install --force` 不加 `--no-cache` 会复用缓存旧 wheel

## 架构决策与文档

- ADR：`docs/adr/`（架构决策记录）
- 路线图：`ROADMAP.md` 与 `docs/ROADMAP.md`
- 项目记忆：`memory/`（session.md 热层 / project-knowledge.md 暖层 / overview.md 冷层）+ `PROJECT_CONTEXT.md`（会话交接）
- 提交风格：小步、可逆、单一目的（atomic changes）

## 安全工程约定

- 原子写入：临时文件 + rename（AtomicWriter）
- 跨进程锁：sibling lock file 约定（`数据文件名 + ".lock"`），不能锁数据文件本身（Windows 上 rename 撞被锁句柄会 EACCES）
- 外部内容扫描注入/劫持模式；路径校验防 traversal
