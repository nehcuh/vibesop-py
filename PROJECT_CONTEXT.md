# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-25 S43 [vibesop-py + cmspark] gate44 Windows 409→0 + job 转正 · cmspark 幽灵/回声技能治理 · 验收排程

**Session Summary**:
- gate44（synthesis v2.1 实施）：项1 sibling 锁反模式 9 处清零（`cross_process_lock(数据文件)` → `X.lock`，`with_suffix` 形状按锁身份契约不改名）→ Windows 失败 409→5→0；项2/3/4 平台门控 + 残余清零 + 四头防御；顺带修 `infer_source` 反斜杠归一 + `import-claude` 盘符冒号 2 个产品 bug
- gate44 项5 两段式转正（`775639c`）：连续 3 绿（296c1ae → e875bc7 → a9df194，双 python、各 0 rerun）后摘 `continue-on-error` + 加 `--reruns-delay 1`；**Windows job 现为 required gate，红灯堵发布链**（ci.yml 被 release.yml 复用）；首个 required-gate run 全绿；CHANGELOG 回填（`7af8959`）
- cmspark 幽灵技能修复（`e875bc7`）：W4 promote 物化目录可路由不可注入 → injector 候选目录加 `.vibe/skills`（项目+home）+ per-base nested 匹配；hint 指向真实物化路径；`uv tool install --force` 复用缓存 wheel 必须 `--no-cache`
- cmspark 回声技能 bd1bc217：判定保留（gate32 A1 记录在案的刻意 override）；id 改名 `adversarial-reviewer-dispatch-bd1bc217`（五处同步，备份 /tmp/cmspark-echo-skill-bak-105511）；删 auto-config 死条目；promote 加 agent-echo 非阻断警告（`a9df194`）
- 遗留验收排程：3 个 durable one-shot cron——8-25 17:43 gate42 T+24h / 8-31 18:47 gate42 一周+gate43 T+7 / 9-7 18:47 gate43 T+14

**Key Decisions**:
- 回声簇可提升是设计允许（人工评审对象），处理取"保留+改名+警告"而非 dismiss——bd1bc217 是 gate32 A1 注释点名的合法先例
- 转正计数教训：continue-on-error 下 run 级 success 吞 job 级红灯（3325200 实例）——"连续绿"必须 `gh run view --json jobs` 查 job 级
- auto-config `routing.patterns` 是无消费者死配置（真实路由输入 = skill-index.json query_patterns）；understander 的 `.*关键词.*` 无锚生成问题因修死代码无收益而挂账不修
- gate43 T0 = 8-24 18:42 CST（`~/.grok/rules/routing.md` 重部署 mtime——grok 文案面在全局 ~/.grok/ 非 cmspark 项目文件）；gate42 cutover = span_ts 8-24T09:31Z（outcomes 批簇实测）

**Next Steps**:
1. 三个 durable cron 到期自动跑验收（新增行判定必须 span_ts > cutover，勿用 recorded_at）；产物链 `.omx/artifacts/gate4*-t*-measure.md`
2. gate43 T+7 FAIL 时按 synthesis 回滚条款（revert + 重 build）——cron 提示词已含，勿自行执行
3. 挂账：cursor 死 `_render_route_hook`（gate43 §1.2，独立工作）；understander 黑洞正则生成器（死配置，若未来接通消费者须先修）

### 2026-08-24 S42 [vibesop-py + cmspark] gate42 幻影 reask 治理 + CI 红灯清零 + 8.1.0 发布

**Session Summary**:
- gate42：vibe-cli 自路由 span 被误判为用户重问（cmspark 残余 reask 75% 幻影）→ bridge `_classify`/`_classify_hit` 两处 `later_same_task` 各加 `not rs.is_cli`（gate41 §6 预授权语义收窄）；三 lane 对抗完全收敛；三路评审+确认轮全 PASS
- CI 红灯清零：lint 24 + ruff format 74 文件 → launchd uv 路径 hermetic mock + benchmark 重试 → p95 环境分级预算 CI 500µs/本地 100µs
- 8.1.0 发布：PyPI + GitHub Release（147 commits；tag `18be788`）；cmspark rebuild dry-run 验收预审全过（硬闸 A CLI 触发=0 / 硬闸 B 0.93:1、0.23:1 / sanity 72.2%）

**Key Decisions**:
- 定性走 gate41 §6 授权链（语义收窄），不走"代码违背 docstring"叙事——三路评审一致打回后者
- 绝对 µs 微基准在共享 runner 必假警 → 环境分级预算；`--reruns` 救不了系统性减速

**Next Steps**:
1. cmspark rebuild --apply（已完成于 8-24 晚）+ T+24h 早期检查（→ S43 已排程 cron）
2. gate43：模板文案降级 + Windows fixture 修复（→ S43 已随 gate44 全部落地）
3. 触发器：verdict ≥30 / M3 复检 / 留存池 2026-09-19 / P0-lite 观察期
<!-- handoff:end -->
