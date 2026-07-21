
### S35 (2026-07-21 01:30~05:10) [vibesop-py] 文档全审计 + Dashboard 依赖重构 + 修复 CI → v8.0.0 PyPI 发布

- [x] **文档全审计**：87 个 MD 文件逐行检查，发现版本分裂（15+ 文件声称 4.x~6.2，实际 8.0.0）、测试数矛盾（2,972 vs 4,066）、架构描述不一致（10 层 vs 4 阶段级联）
- [x] **文档修复**：归档 11 个历史文件、删除 2 个重复文件、更新 26 个文件（版本号、pip→uv、10 层→4 阶段级联、测试数统一）
- [x] **Dashboard 依赖**：`fastapi` + `uvicorn` 从 optional extra 移入 core deps，全局安装后 `vibe dashboard` 开箱即用
- [x] **修复 CI**：29 个 ruff lint 错误（含格式）、3 个 Windows 测试失败（atomic_writer 编码 + tick lock FileExistsError + lock 文件残留）
- [x] **PyPI 发布 v8.0.0**：Release workflow SHA 过期 → 改为 version tag；PyPI Trusted Publisher 配置通过；全 8 CI job 绿色
- [x] **cmspark analytics**：`vibe init` 旧项目无 config.toml → analytics 默认 false → dashboard 空；手动创建 config 启用

**Key Discoveries**:
1. GitHub Actions 的 pinned SHA 会被 GC，非安全关键 action 应用 version tag（`@v2`、`@release/v1`）
2. Windows 上 `Path.read_text()` 默认编码是 locale（CP1252），非 UTF-8 → 跨平台必须显式 encoding
3. Windows 上 `O_CREAT | O_EXCL` 锁文件 close 后残留磁盘 → 需显式 unlink
4. `softprops/action-gh-release` v2.6.2 SHA 和 v2.2.0 SHA 全部不可解析 → `@v2` tag 是唯一稳的

**Next Steps**:
- Dashboard 全局工具重装：`uv tool install --reinstall /path/to/vibesop-py`
- 后续版本升级时确保 config.toml 中的 analytics 设置不被覆盖

**Recorded**: yes — 3 technical pitfalls + 1 reusable pattern → project-knowledge.md

### S35 (2026-07-21 01:30~05:10) [vibesop-py] 文档全审计 + Dashboard 依赖重构 + 修复 CI → v8.0.0 PyPI 发布

- [x] **文档全审计**：87 个 MD 文件逐行检查，发现版本分裂（15+ 文件声称 4.x~6.2，实际 8.0.0）、测试数矛盾（2,972 vs 4,066）、架构描述不一致（10 层 vs 4 阶段级联）
- [x] **文档修复**：归档 11 个历史文件、删除 2 个重复文件、更新 26 个文件（版本号、pip→uv、10 层→4 阶段级联、测试数统一）
- [x] **Dashboard 依赖**：fastapi + uvicorn 从 optional extra 移入 core deps，全局安装后 vibe dashboard 开箱即用
- [x] **修复 CI**：29 个 ruff lint 错误（含格式）、3 个 Windows 测试失败（atomic_writer 编码 + tick lock FileExistsError + lock 文件残留）
- [x] **PyPI 发布 v8.0.0**：Release workflow SHA 过期 → 改为 version tag；PyPI Trusted Publisher 配置通过；全 8 CI job 绿色
- [x] **cmspark analytics**：vibe init 旧项目无 config.toml → analytics 默认 false → dashboard 空；手动创建 config 启用

**Key Discoveries**:
1. GitHub Actions 的 pinned SHA 会被 GC，非安全关键 action 应用 version tag（@v2、@release/v1）
2. Windows 上 Path.read_text() 默认编码是 locale（CP1252），非 UTF-8 → 跨平台必须显式 encoding
3. Windows 上 O_CREAT|O_EXCL 锁文件 close 后残留磁盘 → 需显式 unlink
4. softprops/action-gh-release 多个版本 SHA 全部不可解析 → @v2 tag 是唯一稳的

**Next Steps**:
- Dashboard 全局工具重装：uv tool install --reinstall /path/to/vibesop-py
- 后续版本升级时确保 config.toml 中的 analytics 设置不被覆盖

**Recorded**: yes — 3 technical pitfalls + 1 reusable pattern → project-knowledge.md
