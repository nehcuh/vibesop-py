# VibeSOP Loop — 实测部署指南

> **目的**：Phase 1 实测计划 A —— 验证 `/slash-route use {skill_id}` 在真实 LLM 下的路由可靠性
> **预计耗时**：10 分钟配置 + 24 小时观察
> **文档版本**：2026-06-19（对齐 v8.0.0-dev Phase 1-5）

---

## ⚠️ 已知 v1 限制（先读）

在配置前，请了解当前 Phase 1 的设计限制，避免误判测试结果：

| 限制 | 影响 | 缓解 |
|---|---|---|
| **`/slash-route use {skill_id}` 不走 EXPLICIT layer** | 路由靠 keyword layer 命中 skill_id token，**不是** confidence=1.0 显式调用 | 本次测试正是要验证命中率的真实表现 |
| **`LoopConfig.enabled` 字段未读** | 设环境变量 `VIBE_LOOP_ENABLED=false` 当前**无效果** | 用 `vibe loop pause <name>` 或删 crontab 行做 kill switch |
| **`vibe loop tick` 不内嵌常驻** | 必须由外部 cron/systemd/launchd 每分钟调用一次 | 本文档 §3 提供三种调度器配置 |
| **无 Guard 系统** | 失败时无自动告警，无人工审批门 | 关注 `consecutive_failures`；DEAD 后自动停（`max_failures` 触发） |

---

## 1. 挑选测试任务

| 优先级 | 任务 | 技能 | 风险 |
|---|---|---|---|
| 🥇 | 系统诊断 | `systematic-debugging` | 低（内置技能，零外部依赖） |
| 🥇 | 路由自检 | `slash-route` | 最低（兜底工作流） |
| 🥈 | 代码审查 | `gstack/review` | 中（需安装 gstack） |
| 🥉 | 架构分析 | `superpowers/architect` | 中（需安装 superpowers） |

**建议首测**：`systematic-debugging` —— 内置、必存在、输出结构化，便于判断 `matched_skill` 是否正确填充。

---

## 2. 创建 Loop

```bash
vibe loop create health-check \
  --skill systematic-debugging \
  --schedule "*/30 * * * *" \
  --desc "每 30 分钟项目健康诊断（Phase 1 路由可靠性验证）"
```

> **注意**：当前 LoopSpec 强制三选一（`skill_id` / `query` / `workflow_id`）。
> 不能同时传 `--skill` 和 `--query` —— 这会触发 ValidationError。
> 本次测试目标是验证 `/slash-route use {skill_id}` 路径，所以只用 `--skill`。

**实际输出格式**（参考，不是 Panel）：

```
╭──────────────────────── VibeSOP Loop ─────────────────────────╮
│ ✅ Loop Created                                                  │
│   Name:        health-check                                      │
│   Schedule:    */30 * * * *                                      │
│   Target:      systematic-debugging                              │
│   Status:      🟢 Active                                         │
│   Next Run:    2026-06-19 10:30 UTC                              │
╰──────────────────────────────────────────────────────────────────╯

外部 cron 调用 `vibe loop tick` 即可触发执行。
```

---

## 3. 配置外部调度器

### 3.1 crontab（macOS/Linux 通用）

```bash
crontab -e
```

追加：

```cron
# 每分钟跑一次 vibe loop tick（cron 环境不加载 shell rc，env vars 要显式声明）
ANTHROPIC_API_KEY="sk-ant-..."
* * * * * cd /path/to/vibesop-py && uv run vibe loop tick >> ~/.vibe/loops/tick.log 2>&1
```

验证：

```bash
crontab -l | grep vibe
```

### 3.2 systemd timer（Linux，更可控）

```ini
# /etc/systemd/system/vibesop-loop.service
[Unit]
Description=VibeSOP Loop Tick
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/vibesop-py
Environment=ANTHROPIC_API_KEY=sk-ant-...
Environment=HOME=/home/youruser
ExecStart=uv run vibe loop tick
StandardOutput=append:/home/youruser/.vibe/loops/tick.log
StandardError=append:/home/youruser/.vibe/loops/tick.log
```

```ini
# /etc/systemd/system/vibesop-loop.timer
[Unit]
Description=VibeSOP Loop Tick Timer (every minute)

[Timer]
OnCalendar=minutely
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vibesop-loop.timer
systemctl status vibesop-loop.timer
```

### 3.3 launchd（macOS，替代 cron）

```xml
<!-- ~/Library/LaunchAgents/com.vibesop.looptick.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vibesop.looptick</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>cd /path/to/vibesop-py &amp;&amp; uv run vibe loop tick</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/vibesop-py</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/youruser</string>
        <key>ANTHROPIC_API_KEY</key>
        <string>sk-ant-...</string>
    </dict>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>StandardOutPath</key>
    <string>/Users/youruser/.vibe/loops/tick.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/youruser/.vibe/loops/tick.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.vibesop.looptick.plist
launchctl start com.vibesop.looptick
```

---

## 4. 验证调度器生效

```bash
# 等 1-2 分钟后查看 tick 日志
tail -f ~/.vibe/loops/tick.log
```

**实际输出格式**（每分钟一行）：

```
本轮无可触发 loop（1 eligible, 0 skipped）。        # 非整 30 分钟时
▶ Ticking health-check...                            # 整 30 分钟时
  ✅ systematic-debugging (1.23s)

Tick 完成: 1 触发, 1 成功, 0 失败
```

**手动触发验证**（不等 cron）：

```bash
# 干跑 —— 只看哪些 loop 会被触发，不执行
vibe loop tick --dry-run
# 预期:
# 1 个 loop 会被触发 (dry-run):
#   • health-check — systematic-debugging

# 实际触发一次
vibe loop tick
# 预期:
# ▶ Ticking health-check...
#   ✅ systematic-debugging (X.XXs)
#
# Tick 完成: 1 触发, 1 成功, 0 失败
```

---

## 5. 观察指标（24 小时）

### 5.1 核心判定（Phase 1 路由可靠性）

| 指标 | ✅ 合格 | ⚠️ 告警 | ❌ 失败 |
|---|---|---|---|
| `matched_skill` 非空率 | ≥ 90% | 50–90% | < 50% |
| `output_summary` 有内容率 | ≥ 80% | 50–80% | < 50% |
| 连续失败停摆次数 | 0 | 1 次 DEAD | ≥ 2 次 DEAD |
| `error` 内容 | 无 | LLM 超时 | `"no matching skill"` |

### 5.2 观察命令

```bash
# 全局视图
vibe loop list

# 单 loop 详情 + recent_runs
vibe loop show health-check

# tick 日志
tail -30 ~/.vibe/loops/tick.log

# 原始 state（JSON）
cat ~/.vibe/loops/health-check/state.json | python3 -m json.tool
```

### 5.3 24 小时观察表

| 时间点 | total_runs | consecutive_failures | status | matched_skill 命中 | 备注 |
|---|---|---|---|---|---|
| T+1h  |   |   |   |   |   |
| T+4h  |   |   |   |   |   |
| T+8h  |   |   |   |   |   |
| T+24h |   |   |   |   |   |

---

## 6. 判定树（24 小时后）

```
vibe loop show health-check
│
├─ matched_skill 非空 + output_summary 有内容
│   └─ ✅ 基础通 → Phase 2 按 C → B → D 推进
│
├─ 反复 "no matching skill found"，skill 明明存在
│   └─ ❌ /slash-route 失效 → 必须先修 dispatch（加真 EXPLICIT 入口）
│       └─ 暂停 Phase 2，先打 v8.1 dispatch 修复
│
├─ 偶尔命中偶尔不命中
│   └─ ⚠️ keyword layer 不稳定 → 在 Phase 2 前加 fallback
│       └─ 一起定修复方案
│
└─ tick 日志为空 / cron 不触发
    └─ ❌ 调度器配置错误
        └─ 检查 crontab / systemd timer / launchd plist
```

---

## 7. LLM 配置

**本文档不重复 LLM 配置细节** —— 完整指南见：

👉 [`docs/SKILL_LLM_CONFIG_GUIDE.md`](SKILL_LLM_CONFIG_GUIDE.md)

要点：
- API key 优先通过 `~/.vibe/config.toml` 的 `[llm]` 段配置
- cron/systemd 环境不加载 shell rc，需在调度器配置里显式声明 env vars
- 不确定 env var 名时，参考上述指南（`VIBESOP_LLM_PROVIDER` 或 `VIBE_LLM_PROVIDER` 取决于加载路径）

---

## 8. 安全 & 清理

- `state.json` 不存储 LLM API key（key 从环境 / config.toml 读取）
- `tick.log` 可能含 query 原文与路由决策 —— **不要提交到 git**（`.gitignore` 已配置）
- 紧急停止：
  - 单 loop：`vibe loop pause <name>`
  - 全局：注释 / 删除 crontab 行 / `launchctl unload` / `systemctl stop`
- 测试结束后清理：
  ```bash
  vibe loop delete health-check --force
  ```

---

## 9. 后续阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | models / store / scheduler / executor / CLI | ✅ 完成（147 tests passing） |
| **Phase 1 实测 A** | **本文档 —— 24 小时真实环境验证** | **🔄 进行中** |
| Phase 2-C | 内置 daemon（`vibe loop daemon start/stop`） | 待 A 结果 |
| Phase 2-B | Guard 系统（人工审批 + 通知 + Dead man's switch） | 待 A 结果 |
| Phase 2-D | `vibe loop logs --json` + `vibe loop dashboard` | 待 A 结果 |

判定标准见 §6。A 结果决定 C/B/D 的优先级排序。
